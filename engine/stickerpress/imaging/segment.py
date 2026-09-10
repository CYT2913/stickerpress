"""把一张"六宫格贴纸大图"切成 6 张独立贴纸。

不用固定网格硬切——模型排布总有偏移，硬切会把耳朵、尾巴切掉。
改成对 alpha 通道做连通域分析，让每张贴纸自己"说"它在哪，
再按阅读顺序（从上到下、从左到右）编号。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

import numpy as np
from PIL import Image
from scipy import ndimage


@dataclass
class StickerPiece:
    index: int                       # 1..N，阅读顺序
    image: Image.Image               # 裁切后的 RGBA
    bbox: Tuple[int, int, int, int]  # 在原大图中的 (x0, y0, x1, y1)
    area_px: int                     # 不透明像素数
    centroid: Tuple[float, float]

    @property
    def size(self) -> Tuple[int, int]:
        return self.image.size

    @property
    def fill_ratio(self) -> float:
        w, h = self.image.size
        return self.area_px / max(w * h, 1)


def _reading_order(pieces: List[StickerPiece], rows: int) -> List[StickerPiece]:
    """按"先分行、行内再排左右"排序，容忍每行贴纸的高低错位。"""
    if not pieces:
        return []
    ys = np.array([p.centroid[1] for p in pieces])
    order = np.argsort(ys)
    sorted_pieces = [pieces[i] for i in order]

    per_row = max(1, int(round(len(sorted_pieces) / max(rows, 1))))
    out: List[StickerPiece] = []
    for i in range(0, len(sorted_pieces), per_row):
        band = sorted_pieces[i:i + per_row]
        band.sort(key=lambda p: p.centroid[0])
        out.extend(band)
    for i, p in enumerate(out, start=1):
        p.index = i
    return out


def split_sheet(
    rgba: Image.Image,
    expected: int = 6,
    rows: int = 3,
    alpha_threshold: int = 24,
    min_area_ratio: float = 0.004,
    pad_px: int = 6,
    merge_gap_px: int = 9,
) -> Tuple[List[StickerPiece], List[str]]:
    """切分。返回 (贴纸列表, 诊断信息)。

    :param merge_gap_px: 形态学闭运算半径。贴纸里的悬浮元素（比如飘出去的爱心、
        彩带、Zzz）本来是独立连通域，用闭运算先把它们和主体粘起来，
        避免被当成 6 张之外的碎片。
    """
    diagnostics: List[str] = []
    a = np.asarray(rgba.getchannel("A"))
    H, W = a.shape
    mask = a > alpha_threshold

    if merge_gap_px > 0:
        st = np.ones((merge_gap_px, merge_gap_px), dtype=bool)
        grouped = ndimage.binary_closing(mask, structure=st)
        grouped = ndimage.binary_dilation(grouped, structure=st)
    else:
        grouped = mask

    labels, n = ndimage.label(grouped)
    diagnostics.append(f"连通域初检：{n} 个")
    if n == 0:
        return [], diagnostics + ["未检出任何主体，抠图可能失败"]

    sizes = ndimage.sum(mask, labels, index=range(1, n + 1))
    min_area = min_area_ratio * H * W
    keep = [i + 1 for i, s in enumerate(sizes) if s >= min_area]
    dropped = n - len(keep)
    if dropped:
        diagnostics.append(f"剔除 {dropped} 个面积过小的碎片（阈值 {min_area:.0f}px）")

    # 面积从大到小，多余的碎片不参与
    keep.sort(key=lambda lb: sizes[lb - 1], reverse=True)
    if len(keep) > expected:
        diagnostics.append(f"检出 {len(keep)} 个主体，多于预期 {expected}，保留面积最大的 {expected} 个")
        keep = keep[:expected]

    pieces: List[StickerPiece] = []
    for lb in keep:
        sel = labels == lb
        ys, xs = np.nonzero(sel)
        x0 = max(int(xs.min()) - pad_px, 0)
        x1 = min(int(xs.max()) + 1 + pad_px, W)
        y0 = max(int(ys.min()) - pad_px, 0)
        y1 = min(int(ys.max()) + 1 + pad_px, H)

        crop = rgba.crop((x0, y0, x1, y1)).copy()
        # 只保留属于本连通域的像素，抹掉邻居探进来的部分
        local = sel[y0:y1, x0:x1]
        ca = np.asarray(crop.getchannel("A")).copy()
        ca[~local] = 0
        crop.putalpha(Image.fromarray(ca))

        pieces.append(StickerPiece(
            index=0,
            image=crop,
            bbox=(x0, y0, x1, y1),
            area_px=int((ca > alpha_threshold).sum()),
            centroid=(float(xs.mean()), float(ys.mean())),
        ))

    pieces = _reading_order(pieces, rows=rows)
    diagnostics.append(f"最终切出 {len(pieces)} 张贴纸")
    return pieces, diagnostics
