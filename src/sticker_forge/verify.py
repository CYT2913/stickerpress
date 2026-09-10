"""对已产出的 SVG 做独立复核。

这一层刻意 **不信任装配器**：它重新打开成品文件、按 XML 解析，逐条核对
AGENTS.md 0.5 的验收项。装配器和验证器共享 spec 常量，但不共享几何计算，
所以装配逻辑写错时验证器能抓到。

能自动核验的：尺寸、数量、闭合刀线、图层、间距、边距、自包含性。
**不能** 自动核验的：内容合规（有没有商标 / 可识别人物 / 隐私信息）。
那一项由 ``needs_human`` 显式列出，绝不因为"检查跑绿了"就当成过了。
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from .spec import CUT_SPOT_NAME, CUT_STROKE, CUT_STROKE_MM, PRINT_DPI_MIN, SheetSpec

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"

_NUM = re.compile(r"-?\d+(?:\.\d+)?")


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""

    def __str__(self) -> str:
        return f"[{'ok' if self.passed else 'FAIL'}] {self.name}：{self.detail}"


@dataclass
class VerifyReport:
    checks: List[Check] = field(default_factory=list)
    needs_human: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failed(self) -> List[Check]:
        return [c for c in self.checks if not c.passed]

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append(Check(name, passed, detail))

    def to_text(self) -> str:
        lines = [str(c) for c in self.checks]
        if self.needs_human:
            lines.append("")
            lines.append("以下项无法自动判定，必须人工复检：")
            lines += [f"  - {x}" for x in self.needs_human]
        return "\n".join(lines)


def _mm(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    m = _NUM.search(value)
    return float(m.group()) if m else None


def _tag(el) -> str:
    return el.tag.split("}")[-1]


#: 每个路径命令消耗的参数个数
_ARGC = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}

_CMD = re.compile(r"([MmLlHhVvCcSsQqTtAaZz])|(-?\d*\.?\d+(?:[eE][-+]?\d+)?)")


def _path_points(d: str) -> List[Tuple[float, float]]:
    """把路径 d 解析成一串坐标点。

    支持 M/L/H/V/C/S/Q/T/A/Z 的绝对与相对写法。刻意手写而不是用现成库：
    这一层不能有第三方依赖，而且验证器必须独立于装配器实现，
    否则装配逻辑写错时验证器会跟着一起错。

    贝塞尔的控制点也计入。对 bbox 而言这是保守的（包围盒只会更大不会更小），
    用于净距判断偏安全；本装配器产出的圆角矩形不含贝塞尔，结果是精确的。
    """
    tokens = _CMD.findall(d)
    pts: List[Tuple[float, float]] = []
    cx = cy = 0.0
    sx = sy = 0.0
    cmd: Optional[str] = None
    args: List[float] = []

    def flush() -> None:
        nonlocal cx, cy, sx, sy, args
        if cmd is None:
            args = []
            return
        up = cmd.upper()
        rel = cmd.islower()
        n = _ARGC[up]
        if n == 0:
            cx, cy = sx, sy
            args = []
            return
        i = 0
        first = True
        while i + n <= len(args):
            chunk = args[i:i + n]
            if up == "H":
                cx = cx + chunk[0] if rel else chunk[0]
            elif up == "V":
                cy = cy + chunk[0] if rel else chunk[0]
            else:
                # 贝塞尔的控制点也记进来（保守 bbox）
                pairs = [(chunk[k], chunk[k + 1]) for k in range(0, n - 1, 2)] \
                    if up != "A" else [(chunk[5], chunk[6])]
                for px, py in pairs[:-1]:
                    pts.append((cx + px, cy + py) if rel else (px, py))
                ex, ey = pairs[-1]
                cx = cx + ex if rel else ex
                cy = cy + ey if rel else ey
            pts.append((cx, cy))
            if up == "M" and first:
                sx, sy = cx, cy
                # 后续隐式坐标按 L 处理
                if rel:
                    pass
            first = False
            i += n
        args = []

    for c, num in tokens:
        if c:
            flush()
            cmd = c
            if c.upper() == "Z":
                flush()
                cmd = None
        else:
            args.append(float(num))
    flush()
    return pts


def _path_bbox(d: str) -> Optional[Tuple[float, float, float, float]]:
    pts = _path_points(d)
    if not pts:
        return None
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)



def _gap(a, b) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    dx = max(bx0 - ax1, ax0 - bx1, 0.0)
    dy = max(by0 - ay1, ay0 - by1, 0.0)
    return (dx * dx + dy * dy) ** 0.5


def verify_sheet(svg_path, spec: Optional[SheetSpec] = None,
                 expect_count: Optional[int] = None) -> VerifyReport:
    spec = spec or SheetSpec()
    expect_count = expect_count or spec.slots
    p = Path(svg_path)
    rep = VerifyReport()

    if not p.exists():
        rep.add("成品文件存在", False, f"找不到 {p}")
        return rep

    text = p.read_text(encoding="utf-8")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        rep.add("SVG 可解析", False, str(exc))
        return rep
    rep.add("SVG 可解析", True, f"{p.name}，{len(text) / 1e6:.1f} MB")

    # --- 1. 画布尺寸 --------------------------------------------------------
    w = _mm(root.get("width"))
    h = _mm(root.get("height"))
    vb = [float(x) for x in _NUM.findall(root.get("viewBox") or "")]
    size_ok = (w is not None and h is not None
               and abs(w - spec.canvas_w_mm) < 0.01
               and abs(h - spec.canvas_h_mm) < 0.01)
    vb_ok = (len(vb) == 4 and abs(vb[2] - spec.canvas_w_mm) < 0.01
             and abs(vb[3] - spec.canvas_h_mm) < 0.01)
    rep.add("画布尺寸与 viewBox 一致", size_ok and vb_ok,
            f"width/height = {w}×{h} mm，viewBox = {vb}；"
            f"期望 {spec.canvas_w_mm:g}×{spec.canvas_h_mm:g} mm")

    # --- 2. 贴纸数量 --------------------------------------------------------
    images = [e for e in root.iter() if _tag(e) == "image"]
    rep.add("贴纸位图数量", len(images) == expect_count,
            f"{len(images)} 张（要求 {expect_count}）")

    # --- 3. 刀版图层 --------------------------------------------------------
    cut_layer = None
    for g in root.iter():
        if _tag(g) == "g" and g.get("id") == CUT_SPOT_NAME:
            cut_layer = g
            break
    if cut_layer is None:
        rep.add(f"{CUT_SPOT_NAME} 图层存在", False, "未找到该图层")
        cut_paths = []
    else:
        stroke = (cut_layer.get("stroke") or "").upper()
        sw = _mm(cut_layer.get("stroke-width"))
        rep.add(f"{CUT_SPOT_NAME} 图层存在", True,
                f'stroke={stroke}, stroke-width={sw}, fill={cut_layer.get("fill")}')
        rep.add("刀线专色与线宽", stroke == CUT_STROKE
                and sw is not None and abs(sw - CUT_STROKE_MM) < 1e-3,
                f"期望 {CUT_STROKE} / {CUT_STROKE_MM}mm（0.25pt），"
                f"实际 {stroke} / {sw}mm")
        rep.add("刀线不填充", (cut_layer.get("fill") or "").lower() == "none",
                "fill 必须为 none，否则模切层会被当成印刷图形")
        cut_paths = [e for e in cut_layer.iter() if _tag(e) == "path"]

    rep.add("刀线数量", len(cut_paths) == expect_count,
            f"{len(cut_paths)} 条（要求 {expect_count}）")

    ds = [e.get("d") or "" for e in cut_paths]
    closed = [d.strip().upper().endswith("Z") for d in ds]
    rep.add("刀线闭合", all(closed) and bool(closed),
            f"{sum(closed)}/{len(closed)} 条以 Z 收口")

    # --- 4. 间距与安全边距 --------------------------------------------------
    bbs = [b for b in (_path_bbox(d) for d in ds) if b]
    if len(bbs) >= 2:
        gap = min(_gap(bbs[i], bbs[j])
                  for i in range(len(bbs)) for j in range(i + 1, len(bbs)))
        rep.add("刀线最小净距", gap >= spec.min_knife_gap_mm - 1e-6,
                f"{gap:.2f} mm（门槛 {spec.min_knife_gap_mm} mm）")
    if bbs:
        margin = min(min(x0, y0, spec.canvas_w_mm - x1, spec.canvas_h_mm - y1)
                     for x0, y0, x1, y1 in bbs)
        rep.add("安全边距", margin >= spec.safe_margin_mm - 1e-6,
                f"{margin:.2f} mm（门槛 {spec.safe_margin_mm} mm）")

        sides = [(x1 - x0, y1 - y0) for x0, y0, x1, y1 in bbs]
        shortest = min(min(a, b) for a, b in sides)
        longest = max(max(a, b) for a, b in sides)
        rep.add("单枚尺寸", shortest >= spec.piece_hard_min_mm
                and longest <= spec.piece_max_mm + 1e-6,
                f"{shortest:.1f} ~ {longest:.1f} mm"
                f"（硬下限 {spec.piece_hard_min_mm}，上限 {spec.piece_max_mm}）")

    # --- 5. 自包含性 --------------------------------------------------------
    external = []
    for e in root.iter():
        for key in ("href", f"{{{XLINK_NS}}}href"):
            v = e.get(key)
            if v and not v.startswith("data:") and not v.startswith("#"):
                external.append(v[:60])
    rep.add("无外部资源依赖", not external,
            "全部位图以 data URI 内嵌" if not external
            else f"发现外链：{external}")

    # --- 6. 有效分辨率 ------------------------------------------------------
    # 位图的实际像素在 data URI 里；这里只能核对"声明的毫米尺寸"，
    # 像素维度由装配期记录进 delivery-report.md。
    rep.needs_human.append(
        f"有效分辨率：装配期已按 ≥{PRINT_DPI_MIN} dpi 卡口，"
        f"复核请看 delivery-report.md 的 placements 表")
    rep.needs_human.append(
        "内容合规：成品是否含未授权品牌 / 版权角色 / 可识别人物 / 隐私信息 / "
        "受保护建筑或艺术品——必须逐枚肉眼复检，工具不下结论")
    rep.needs_human.append(
        "打开测试：把 SVG 复制到另一台机器 / 另一个目录打开，确认不缺图不缺字体")

    return rep


__all__ = ["Check", "VerifyReport", "verify_sheet"]
