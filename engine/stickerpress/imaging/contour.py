"""alpha 通道 → 矢量刀版轮廓（die-cut CutContour）。

这一步决定了产物是不是"真 SVG"。只把 PNG 塞进 <image> 里的 SVG 对印厂毫无用处——
模切机需要的是一条**闭合矢量路径**告诉它刀往哪走。

流程：
    alpha → 二值化 → 填洞 → 向外偏移（留白边）→ 高斯平滑去锯齿
          → Moore 邻域边界追踪 → RDP 抽稀 → Catmull-Rom 转三次贝塞尔

不依赖 OpenCV / scikit-image，只用 numpy + scipy，方便嵌进任何服务。
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

import numpy as np
from scipy import ndimage

Point = Tuple[float, float]

# Moore 邻域，顺时针：W, NW, N, NE, E, SE, S, SW
_MOORE = [(-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1)]


def build_cut_mask(alpha: np.ndarray, threshold: int = 24,
                   offset_px: int = 0, smooth_sigma: float = 2.0) -> np.ndarray:
    """由 alpha 生成用于追踪刀版的二值掩膜。"""
    mask = alpha > threshold
    mask = ndimage.binary_fill_holes(mask)
    if offset_px > 0:
        st = np.ones((2 * offset_px + 1, 2 * offset_px + 1), dtype=bool)
        mask = ndimage.binary_dilation(mask, structure=st)
    # 闭运算填掉毛刺凹槽，再高斯软化 —— 模切刀走不了像素级锯齿
    mask = ndimage.binary_closing(mask, structure=np.ones((5, 5), dtype=bool))
    if smooth_sigma > 0:
        soft = ndimage.gaussian_filter(mask.astype(np.float32), sigma=smooth_sigma)
        mask = soft > 0.5
    mask = ndimage.binary_fill_holes(mask)
    return mask


def trace_outer_boundary(mask: np.ndarray, max_steps: int = 400_000) -> List[Point]:
    """Moore 邻域边界追踪，返回外轮廓像素点序列（顺时针，(x, y)）。"""
    if not mask.any():
        return []
    # 只追最大连通域，避免被残留碎片带偏
    labels, n = ndimage.label(mask)
    if n > 1:
        sizes = ndimage.sum(mask, labels, index=range(1, n + 1))
        mask = labels == (int(np.argmax(sizes)) + 1)

    padded = np.pad(mask, 1, mode="constant", constant_values=False)
    ys, xs = np.nonzero(padded)
    start_i = int(np.argmin(ys * padded.shape[1] + xs))
    start = (int(xs[start_i]), int(ys[start_i]))

    def solid(p: Point) -> bool:
        x, y = int(p[0]), int(p[1])
        return padded[y, x]

    contour: List[Point] = [start]
    current = start
    # 起点是行优先扫描的第一个前景点，其西侧必为背景
    backtrack_idx = 0
    second: Point | None = None

    for step in range(max_steps):
        found = False
        for k in range(1, 9):
            idx = (backtrack_idx + k) % 8
            dx, dy = _MOORE[idx]
            cand = (current[0] + dx, current[1] + dy)
            if solid(cand):
                # 新的 backtrack 方向 = 从 cand 看回 current
                bx, by = current[0] - cand[0], current[1] - cand[1]
                backtrack_idx = _MOORE.index((bx, by))
                current = cand
                found = True
                break
        if not found:
            break  # 孤立像素

        if second is None:
            second = current
            contour.append(current)
            continue

        # Jacob 停止条件：再次以相同朝向经过起点
        if current == start:
            break
        contour.append(current)

    # 去掉 padding 偏移
    return [(float(x - 1), float(y - 1)) for x, y in contour]


def rdp(points: Sequence[Point], epsilon: float) -> List[Point]:
    """Ramer–Douglas–Peucker 折线抽稀（迭代实现，避免深递归）。"""
    pts = list(points)
    if len(pts) < 3:
        return pts
    keep = np.zeros(len(pts), dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    arr = np.asarray(pts, dtype=np.float64)

    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        p0, p1 = arr[i], arr[j]
        seg = p1 - p0
        L = np.hypot(*seg)
        sub = arr[i + 1:j]
        if L < 1e-9:
            d = np.hypot(*(sub - p0).T)
        else:
            d = np.abs(seg[0] * (p0[1] - sub[:, 1]) - (p0[0] - sub[:, 0]) * seg[1]) / L
        m = int(np.argmax(d))
        if d[m] > epsilon:
            k = i + 1 + m
            keep[k] = True
            stack.append((i, k))
            stack.append((k, j))
    return [pts[i] for i in range(len(pts)) if keep[i]]


def _resample_closed(points: Sequence[Point], step: float) -> List[Point]:
    """按弧长均匀重采样闭合折线，让后续平滑更稳定。"""
    pts = list(points)
    if len(pts) < 3:
        return pts
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    arr = np.asarray(pts, dtype=np.float64)
    seg = np.hypot(*np.diff(arr, axis=0).T)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = cum[-1]
    if total < 1e-6:
        return pts[:-1]
    n = max(int(total / max(step, 1e-6)), 8)
    targets = np.linspace(0, total, n, endpoint=False)
    xs = np.interp(targets, cum, arr[:, 0])
    ys = np.interp(targets, cum, arr[:, 1])
    return list(zip(xs.tolist(), ys.tolist()))


def to_bezier_path(points: Sequence[Point], tension: float = 1.0,
                   precision: int = 3) -> str:
    """闭合折线 → 三次贝塞尔 SVG path（Catmull-Rom 转 Bezier）。"""
    pts = list(points)
    n = len(pts)
    if n < 3:
        return ""
    f = f"{{:.{precision}f}}"

    def fmt(p: Point) -> str:
        return f"{f.format(p[0])} {f.format(p[1])}"

    d = [f"M {fmt(pts[0])}"]
    k = tension / 6.0
    for i in range(n):
        p0 = pts[(i - 1) % n]
        p1 = pts[i]
        p2 = pts[(i + 1) % n]
        p3 = pts[(i + 2) % n]
        c1 = (p1[0] + (p2[0] - p0[0]) * k, p1[1] + (p2[1] - p0[1]) * k)
        c2 = (p2[0] - (p3[0] - p1[0]) * k, p2[1] - (p3[1] - p1[1]) * k)
        d.append(f"C {fmt(c1)}, {fmt(c2)}, {fmt(p2)}")
    d.append("Z")
    return " ".join(d)


def alpha_to_cut_path(
    alpha: np.ndarray,
    offset_px: int = 0,
    simplify_px: float = 1.6,
    resample_px: float = 7.0,
    smooth_sigma: float = 2.0,
) -> Tuple[str, List[Point]]:
    """一步到位：alpha → (SVG path d 字符串, 轮廓点)。坐标单位仍是像素。"""
    mask = build_cut_mask(alpha, offset_px=offset_px, smooth_sigma=smooth_sigma)
    raw = trace_outer_boundary(mask)
    if len(raw) < 8:
        h, w = alpha.shape
        rect = [(0.0, 0.0), (w - 1.0, 0.0), (w - 1.0, h - 1.0), (0.0, h - 1.0)]
        return to_bezier_path(rect), rect
    simple = rdp(raw, epsilon=simplify_px)
    even = _resample_closed(simple, step=resample_px)
    return to_bezier_path(even), even


def transform_path_points(points: Sequence[Point], scale: float,
                          dx: float, dy: float) -> List[Point]:
    """像素坐标 → 版面毫米坐标。"""
    return [(x * scale + dx, y * scale + dy) for x, y in points]


def polygon_area(points: Sequence[Point]) -> float:
    if len(points) < 3:
        return 0.0
    arr = np.asarray(points, dtype=np.float64)
    x, y = arr[:, 0], arr[:, 1]
    return float(abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0)


def min_distance_between(a: Sequence[Point], b: Sequence[Point],
                         sample: int = 120) -> float:
    """两条轮廓之间的最小距离（抽样近似），用于校验刀版间距。"""
    if not a or not b:
        return float("inf")
    A = np.asarray(a, dtype=np.float64)
    B = np.asarray(b, dtype=np.float64)
    if len(A) > sample:
        A = A[np.linspace(0, len(A) - 1, sample).astype(int)]
    if len(B) > sample:
        B = B[np.linspace(0, len(B) - 1, sample).astype(int)]
    d = np.sqrt(((A[:, None, :] - B[None, :, :]) ** 2).sum(axis=2))
    return float(d.min())
