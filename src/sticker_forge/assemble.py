"""把 6 张已审核的透明贴纸资产装配成一份 A5 印刷 SVG。

输出的 SVG 是自包含的：位图全部以 data URI 内嵌，脱离工作目录仍可打开，
不依赖任何本地或远程外部资源（AGENTS.md 0.3 / 0.5.5 的硬要求）。

刀线形状为圆角矩形。这是一个 **刻意的保守选择**：圆角矩形的几何完全由
placement 决定，间距、安全边距、闭合性都能在装配期算准并复核。异形轮廓
需要从 alpha 通道追边界，那属于 ``engine/`` 那一层（依赖 numpy/scipy）。
不要在这里手改 SVG 绕过检查。
"""

from __future__ import annotations

import base64
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .imagesize import MIME, read_size
from .spec import (
    CUT_SPOT_NAME, CUT_STROKE, CUT_STROKE_MM, CUT_STROKE_PT,
    FOOTER_BAND_MM, PRINT_DPI_MIN, SheetSpec,
)

Box = Tuple[float, float, float, float]


@dataclass
class Placement:
    index: int
    x_mm: float
    y_mm: float
    w_mm: float
    h_mm: float
    src_px: Tuple[int, int]
    src_name: str
    effective_dpi: float
    label: str = ""

    def to_dict(self) -> Dict:
        return {
            "index": self.index,
            "source": self.src_name,
            "x_mm": round(self.x_mm, 2),
            "y_mm": round(self.y_mm, 2),
            "w_mm": round(self.w_mm, 2),
            "h_mm": round(self.h_mm, 2),
            "src_px": list(self.src_px),
            "effective_dpi": round(self.effective_dpi, 1),
            "label": self.label,
        }


@dataclass
class AssembleResult:
    svg: str
    placements: List[Placement] = field(default_factory=list)
    min_knife_gap_mm: float = 0.0
    min_margin_mm: float = 0.0
    min_effective_dpi: float = 0.0
    target_dpi: Optional[float] = None
    auto_shrunk_count: int = 0

    def to_dict(self) -> Dict:
        return {
            "min_knife_gap_mm": round(self.min_knife_gap_mm, 2),
            "min_margin_mm": round(self.min_margin_mm, 2),
            "min_effective_dpi": round(self.min_effective_dpi, 1),
            "target_dpi": round(self.target_dpi, 1) if self.target_dpi is not None else None,
            "auto_shrunk_count": self.auto_shrunk_count,
            "placements": [p.to_dict() for p in self.placements],
        }


def _esc(s) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _round_rect_d(x: float, y: float, w: float, h: float, r: float) -> str:
    """闭合圆角矩形路径。以 Z 收口，保证模切机拿到的是闭合轮廓。"""
    r = max(0.0, min(r, w / 2, h / 2))
    f = lambda v: f"{v:.3f}"  # noqa: E731
    return (
        f"M {f(x + r)} {f(y)} "
        f"H {f(x + w - r)} A {f(r)} {f(r)} 0 0 1 {f(x + w)} {f(y + r)} "
        f"V {f(y + h - r)} A {f(r)} {f(r)} 0 0 1 {f(x + w - r)} {f(y + h)} "
        f"H {f(x + r)} A {f(r)} {f(r)} 0 0 1 {f(x)} {f(y + h - r)} "
        f"V {f(y + r)} A {f(r)} {f(r)} 0 0 1 {f(x + r)} {f(y)} Z"
    )


def _gap(a: Box, b: Box) -> float:
    """两个轴对齐矩形的最小净距（相交为 0）。"""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    dx = max(bx - (ax + aw), ax - (bx + bw), 0.0)
    dy = max(by - (ay + ah), ay - (by + bh), 0.0)
    return (dx * dx + dy * dy) ** 0.5


def assemble_sheet(
    artworks: Sequence[Path],
    spec: Optional[SheetSpec] = None,
    order_id: str = "",
    source_sha256: str = "",
    labels: Optional[Sequence[str]] = None,
    brand: str = "StickerPress",
    title: str = "A5 六枚模切贴纸台纸",
    strict: bool = True,
    target_dpi: Optional[float] = None,
) -> AssembleResult:
    """装配 A5 台纸。

    ``strict=True`` 时，任何几何验收项不达标都会直接抛错而不是产出问题文件——
    宁可不交付，也不交付一份印出来才发现连刀的版。
    """
    spec = spec or SheetSpec()
    paths = [Path(p) for p in artworks]

    if target_dpi is not None:
        target_dpi = float(target_dpi)
        if not math.isfinite(target_dpi) or target_dpi < PRINT_DPI_MIN:
            raise ValueError(
                f"目标 dpi 必须是有限数且不低于印刷门槛 {PRINT_DPI_MIN}dpi")

    if len(paths) != spec.slots:
        raise ValueError(
            f"需要正好 {spec.slots} 张贴纸资产，实际收到 {len(paths)} 张。"
            f"不足不排版，也不用高风险元素凑数（AGENTS.md 0.6）。")

    cells = spec.cell_boxes()
    placements: List[Placement] = []
    b64s: List[Tuple[str, str]] = []
    auto_shrunk_count = 0

    for i, (p, cell) in enumerate(zip(paths, cells)):
        if not p.exists():
            raise FileNotFoundError(f"贴纸资产不存在：{p}")
        data = p.read_bytes()
        fmt, iw, ih = read_size(data)
        x, y, w, h = spec.fit(cell, (iw, ih))
        dpi = iw / (w / 25.4) if w > 0 else 0.0
        if target_dpi is not None and dpi < target_dpi:
            scale = dpi / target_dpi
            w *= scale
            h *= scale
            cx, cy, cw, ch = cell
            x = cx + (cw - w) / 2
            y = cy + (ch - h) / 2
            dpi = iw / (w / 25.4)
            auto_shrunk_count += 1
        placements.append(Placement(
            index=i + 1, x_mm=x, y_mm=y, w_mm=w, h_mm=h,
            src_px=(iw, ih), src_name=p.name, effective_dpi=dpi,
            label=(labels[i] if labels and i < len(labels) else f"贴纸 {i + 1}"),
        ))
        b64s.append((MIME[fmt], base64.b64encode(data).decode("ascii")))

    boxes = [(p.x_mm, p.y_mm, p.w_mm, p.h_mm) for p in placements]
    gap = min((_gap(boxes[a], boxes[b])
               for a in range(len(boxes)) for b in range(a + 1, len(boxes))),
              default=0.0)
    margin = min(min(bx, by, spec.canvas_w_mm - (bx + bw), spec.canvas_h_mm - (by + bh))
                 for bx, by, bw, bh in boxes)
    min_dpi = min(p.effective_dpi for p in placements)

    if strict:
        problems = []
        if gap < spec.min_knife_gap_mm - 1e-6:
            problems.append(f"刀线最小净距 {gap:.2f}mm < 门槛 {spec.min_knife_gap_mm}mm")
        if margin < spec.safe_margin_mm - 1e-6:
            problems.append(f"安全边距 {margin:.2f}mm < 门槛 {spec.safe_margin_mm}mm")
        required_dpi = target_dpi or PRINT_DPI_MIN
        if min_dpi + 1e-6 < required_dpi:
            problems.append(
                f"最低有效分辨率 {min_dpi:.0f}dpi < 门槛 {required_dpi:g}dpi；"
                f"请提供更高像素的资产")
        small = [p.index for p in placements
                 if min(p.w_mm, p.h_mm) < spec.piece_hard_min_mm]
        if small:
            problems.append(f"第 {small} 枚短边小于硬下限 {spec.piece_hard_min_mm}mm")
        big = [p.index for p in placements if max(p.w_mm, p.h_mm) > spec.piece_max_mm + 1e-6]
        if big:
            problems.append(f"第 {big} 枚长边超过 {spec.piece_max_mm}mm")
        if problems:
            raise ValueError("版面未通过印刷验收：\n  - " + "\n  - ".join(problems))

    svg = _render(spec, placements, b64s, order_id, source_sha256, brand, title)
    return AssembleResult(svg=svg, placements=placements, min_knife_gap_mm=gap,
                          min_margin_mm=margin, min_effective_dpi=min_dpi,
                          target_dpi=target_dpi,
                          auto_shrunk_count=auto_shrunk_count)


def _render(spec: SheetSpec, placements: List[Placement],
            b64s: List[Tuple[str, str]], order_id: str, source_sha256: str,
            brand: str, title: str) -> str:
    W, H = spec.canvas_w_mm, spec.canvas_h_mm
    bl = spec.bleed_mm
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    short_hash = (source_sha256 or "")[:12]

    o: List[str] = []
    a = o.append
    a('<?xml version="1.0" encoding="UTF-8"?>')
    a(f'<!-- {brand} · A5 kiss-cut sticker sheet · order={order_id or "-"} -->')
    a('<!-- 图层 / Layers: substrate=底纸, artwork=印刷图案, '
      'CutContour=模切刀版(专色,只描边不印刷), trace=溯源, guides=参考线(默认隐藏) -->')
    a(f'<svg xmlns="http://www.w3.org/2000/svg" '
      f'xmlns:xlink="http://www.w3.org/1999/xlink" '
      f'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
      f'width="{W:g}mm" height="{H:g}mm" viewBox="0 0 {W:g} {H:g}" version="1.1">')
    a(f'  <title>{_esc(title)}</title>')
    a(f'  <desc>A5 {spec.page_w_mm:g}x{spec.page_h_mm:g}mm · {len(placements)} kiss-cut '
      f'stickers · order={_esc(order_id)} · source-sha256={_esc(short_hash)}</desc>')
    a('  <metadata>')
    a(f'    <cutcontour xmlns="urn:stickerpress:print" spot-color-name="{CUT_SPOT_NAME}" '
      f'usage="kiss-cut" printed="false" unit="mm" stroke-pt="{CUT_STROKE_PT}"/>')
    a('  </metadata>')

    a('  <g id="substrate" inkscape:groupmode="layer" inkscape:label="substrate">')
    a(f'    <rect x="0" y="0" width="{W:g}" height="{H:g}" fill="#FFFFFF"/>')
    a('  </g>')

    a('  <g id="artwork" inkscape:groupmode="layer" inkscape:label="artwork">')
    for p, (mime, b64) in zip(placements, b64s):
        uri = f"data:{mime};base64,{b64}"
        # 只写 xlink:href，不再同时写 SVG2 的 href：
        # 两个属性各存一份完整 data URI 会让文件体积翻倍（400dpi 台纸多出十几 MB），
        # 而 Illustrator / 印厂 RIP 认 xlink:href，主流浏览器也仍然兼容它。
        a(f'    <image id="sticker-{p.index}" '
          f'x="{p.x_mm:.3f}" y="{p.y_mm:.3f}" '
          f'width="{p.w_mm:.3f}" height="{p.h_mm:.3f}" '
          f'preserveAspectRatio="none" image-rendering="optimizeQuality" '
          f'xlink:href="{uri}"/>')
    a('  </g>')

    a(f'  <g id="{CUT_SPOT_NAME}" inkscape:groupmode="layer" '
      f'inkscape:label="{CUT_SPOT_NAME}" fill="none" stroke="{CUT_STROKE}" '
      f'stroke-width="{CUT_STROKE_MM}" stroke-linejoin="round" '
      f'data-spot-color="{CUT_SPOT_NAME}" data-print="false">')
    for p in placements:
        d = _round_rect_d(p.x_mm, p.y_mm, p.w_mm, p.h_mm, spec.corner_r_mm)
        a(f'    <path id="cut-{p.index}" d="{d}"/>')
    a('  </g>')

    fy = bl + spec.page_h_mm - spec.safe_margin_mm - FOOTER_BAND_MM / 2 + 2.2
    left = bl + spec.safe_margin_mm
    right = bl + spec.page_w_mm - spec.safe_margin_mm
    a('  <g id="trace" inkscape:groupmode="layer" inkscape:label="trace" '
      'font-family="Helvetica, Arial, sans-serif" fill="#9AA0A6">')
    a(f'    <line x1="{left:g}" y1="{fy - 5.2:.2f}" x2="{right:g}" y2="{fy - 5.2:.2f}" '
      f'stroke="#E3E6EA" stroke-width="0.25"/>')
    a(f'    <text x="{left:g}" y="{fy:.2f}" font-size="2.6" letter-spacing="0.08">'
      f'{_esc(brand)} · A5 {spec.page_w_mm:g}×{spec.page_h_mm:g}mm · '
      f'{len(placements)} stickers · {now}</text>')
    a(f'    <text x="{right:g}" y="{fy:.2f}" font-size="2.6" text-anchor="end" '
      f'letter-spacing="0.08">ORDER {_esc(order_id or "-")} · '
      f'SRC {_esc(short_hash or "-")}</text>')
    a('  </g>')

    a('  <g id="guides" inkscape:groupmode="layer" inkscape:label="guides" '
      'style="display:none" fill="none">')
    a(f'    <rect x="{bl:g}" y="{bl:g}" width="{spec.page_w_mm:g}" '
      f'height="{spec.page_h_mm:g}" stroke="#00A3FF" stroke-width="0.2" '
      f'stroke-dasharray="2 1.2"/>')
    a(f'    <rect x="{bl + spec.safe_margin_mm:g}" y="{bl + spec.safe_margin_mm:g}" '
      f'width="{spec.page_w_mm - 2 * spec.safe_margin_mm:g}" '
      f'height="{spec.page_h_mm - 2 * spec.safe_margin_mm:g}" '
      f'stroke="#22C55E" stroke-width="0.2" stroke-dasharray="1.2 1.2"/>')
    a('  </g>')
    a('</svg>')
    return "\n".join(o) + "\n"


__all__ = ["Placement", "AssembleResult", "assemble_sheet"]
