"""A5 印刷级 SVG 排版引擎。

产出的不是"把 PNG 塞进 SVG"，而是一份印厂可以直接开工的文件：

* 画布 154×216mm = A5 成品 148×210mm + 四周 3mm 出血，viewBox 以毫米为用户单位
* ``artwork``    图层：6 张贴纸位图（base64 内嵌，无外链依赖）
* ``CutContour`` 图层：6 条闭合矢量刀版路径，只描边不填充，走模切机
* ``marks``      图层：四角裁切标记
* ``trace``      图层：作业号 / 合规指纹 / 策略版本，实体成品可溯源
* ``guides``     图层：安全区参考线，默认隐藏，不影响印刷
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw

from ..config import FOOTER_BAND_MM, SheetSpec
from ..imaging.contour import (
    alpha_to_cut_path, min_distance_between, to_bezier_path, transform_path_points,
)

Point = Tuple[float, float]

#: 模切专色约定。Roland / 拓美等设备识别名为 CutContour 的专色路径；
#: 在 SVG 里用 100% 品红描边表达，并在 metadata 中声明用途。
CUT_STROKE = "#FF00FF"

#: 刀线线宽。印厂约定是 0.25 pt；本文件的用户单位是 mm，必须换算，
#: 直接写 0.25 会得到 0.71 pt —— 2.8 倍过粗，模切机可能按粗线中心偏移下刀。
PT_TO_MM = 25.4 / 72.0
CUT_STROKE_PT = 0.25
CUT_STROKE_W = round(CUT_STROKE_PT * PT_TO_MM, 4)  # ≈ 0.0882 mm

#: 贴纸在格位内的内缩，防止相邻刀版贴太近
CELL_PAD_MM = 1.6

#: 位图重采样上限，超过就下采样——控制 SVG 体积，同时远高于 300dpi 印刷门槛
TARGET_DPI_CAP = 400


@dataclass
class Placement:
    index: int
    x_mm: float
    y_mm: float
    w_mm: float
    h_mm: float
    src_px: Tuple[int, int]
    effective_dpi: float
    cut_points_mm: List[Point] = field(default_factory=list)
    cut_path_d: str = ""
    area_ratio: float = 0.0     # 贴纸占格位面积比
    label: str = ""

    def to_dict(self) -> Dict:
        return {
            "index": self.index,
            "x_mm": round(self.x_mm, 2),
            "y_mm": round(self.y_mm, 2),
            "w_mm": round(self.w_mm, 2),
            "h_mm": round(self.h_mm, 2),
            "src_px": list(self.src_px),
            "effective_dpi": round(self.effective_dpi, 1),
            "area_ratio": round(self.area_ratio, 3),
            "label": self.label,
        }


@dataclass
class SheetBuildResult:
    svg: str
    placements: List[Placement]
    min_knife_gap_mm: float
    min_effective_dpi: float


def _b64_png(im: Image.Image) -> str:
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _fit(cell: Tuple[float, float, float, float], img_px: Tuple[int, int],
         pad: float) -> Tuple[float, float, float, float]:
    """等比缩放贴纸到格位内，返回 (x, y, w, h)（mm）。"""
    cx, cy, cw, ch = cell
    aw, ah = cw - 2 * pad, ch - 2 * pad
    iw, ih = img_px
    s = min(aw / iw, ah / ih)
    w, h = iw * s, ih * s
    return cx + (cw - w) / 2, cy + (ch - h) / 2, w, h


def build_sheet_svg(
    pieces: Sequence,                    # List[StickerPiece]
    spec: Optional[SheetSpec] = None,
    job_id: str = "",
    fingerprint: str = "",
    policy_version: str = "",
    title: str = "StickerPress A5 贴纸台纸",
    brand: str = "StickerPress",
    labels: Optional[Sequence[str]] = None,
    cut_offset_px: int = 0,
) -> SheetBuildResult:
    spec = spec or SheetSpec()
    cells = spec.cell_boxes()
    n = min(len(pieces), spec.slots)

    placements: List[Placement] = []
    images_b64: List[str] = []

    for i in range(n):
        piece = pieces[i]
        im: Image.Image = piece.image
        cell = cells[i]
        x, y, w, h = _fit(cell, im.size, CELL_PAD_MM)

        # 控制体积：把位图重采样到不超过 TARGET_DPI_CAP
        max_px_w = int(round(w / 25.4 * TARGET_DPI_CAP))
        if im.size[0] > max_px_w > 32:
            ratio = max_px_w / im.size[0]
            im = im.resize((max_px_w, max(1, int(round(im.size[1] * ratio)))),
                           Image.LANCZOS)

        import numpy as np
        alpha = np.asarray(im.getchannel("A"))
        _, pts_px = alpha_to_cut_path(
            alpha,
            offset_px=cut_offset_px,
            simplify_px=max(1.0, im.size[0] / 500.0),
            resample_px=max(4.0, im.size[0] / 110.0),
            smooth_sigma=max(1.2, im.size[0] / 400.0),
        )
        scale = w / im.size[0]           # mm per px
        pts_mm = transform_path_points(pts_px, scale, x, y)
        d = to_bezier_path(pts_mm)

        eff_dpi = im.size[0] / (w / 25.4) if w > 0 else 0.0
        placements.append(Placement(
            index=i + 1, x_mm=x, y_mm=y, w_mm=w, h_mm=h,
            src_px=im.size, effective_dpi=eff_dpi,
            cut_points_mm=pts_mm, cut_path_d=d,
            area_ratio=(w * h) / (cell[2] * cell[3]),
            label=(labels[i] if labels and i < len(labels) else f"贴纸 {i+1}"),
        ))
        images_b64.append(_b64_png(im))

    # 刀版最小净距
    gap = float("inf")
    for a in range(len(placements)):
        for b in range(a + 1, len(placements)):
            gap = min(gap, min_distance_between(placements[a].cut_points_mm,
                                                placements[b].cut_points_mm))
    if gap == float("inf"):
        gap = 0.0
    min_dpi = min((p.effective_dpi for p in placements), default=0.0)

    svg = _render_svg(spec, placements, images_b64, job_id, fingerprint,
                      policy_version, title, brand)
    return SheetBuildResult(svg=svg, placements=placements,
                            min_knife_gap_mm=gap, min_effective_dpi=min_dpi)


# ---------------------------------------------------------------------------


def _render_svg(spec: SheetSpec, placements: List[Placement], images_b64: List[str],
                job_id: str, fingerprint: str, policy_version: str,
                title: str, brand: str) -> str:
    W, H = spec.canvas_w_mm, spec.canvas_h_mm
    bl = spec.bleed_mm
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    o: List[str] = []
    a = o.append
    a('<?xml version="1.0" encoding="UTF-8"?>')
    a(f'<!-- {brand} · A5 die-cut sticker sheet -->')
    a('<!-- 图层说明 / Layers: artwork=印刷图案, CutContour=模切刀版(专色, 只描边不印), '
      'marks=裁切标记, trace=溯源信息, guides=参考线(默认隐藏) -->')
    a(f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
      f'xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
      f'width="{W}mm" height="{H}mm" viewBox="0 0 {W} {H}" '
      f'version="1.1">')

    a(f'  <title>{_esc(title)}</title>')
    a(f'  <desc>A5 {spec.page_w_mm}x{spec.page_h_mm}mm + {bl}mm bleed · '
      f'{len(placements)} die-cut stickers · job={_esc(job_id)} · '
      f'compliance={_esc(fingerprint)} · policy={_esc(policy_version)}</desc>')
    a('  <metadata>')
    a('    <cutcontour xmlns="urn:stickerpress:print" spot-color-name="CutContour" '
      'usage="die-cut" printed="false" unit="mm"/>')
    a('  </metadata>')

    # ---- 背景（出血满版白底）--------------------------------------------
    a(f'  <g id="substrate" inkscape:groupmode="layer" inkscape:label="substrate">')
    a(f'    <rect x="0" y="0" width="{W}" height="{H}" fill="#FFFFFF"/>')
    a('  </g>')

    # ---- 图案层 ----------------------------------------------------------
    a('  <g id="artwork" inkscape:groupmode="layer" inkscape:label="artwork">')
    for p, b64 in zip(placements, images_b64):
        a(f'    <image id="sticker-{p.index}" '
          f'x="{p.x_mm:.3f}" y="{p.y_mm:.3f}" '
          f'width="{p.w_mm:.3f}" height="{p.h_mm:.3f}" '
          f'preserveAspectRatio="none" image-rendering="optimizeQuality" '
          f'xlink:href="data:image/png;base64,{b64}" '
          f'href="data:image/png;base64,{b64}"/>')
    a('  </g>')

    # ---- 刀版层 ----------------------------------------------------------
    a('  <g id="CutContour" inkscape:groupmode="layer" inkscape:label="CutContour" '
      f'fill="none" stroke="{CUT_STROKE}" stroke-width="{CUT_STROKE_W}" '
      'stroke-linejoin="round" data-spot-color="CutContour" data-print="false">')
    for p in placements:
        if p.cut_path_d:
            a(f'    <path id="cut-{p.index}" d="{p.cut_path_d}"/>')
    a('  </g>')

    # ---- 裁切标记 --------------------------------------------------------
    # 只有存在出血时才需要裁切标记：标记本身要画在出血区里。
    # kiss-cut 台纸（bleed=0）的成品边就是纸边，画标记反而会被印上去。
    if bl > 0:
        a('  <g id="marks" inkscape:groupmode="layer" inkscape:label="marks" '
          'stroke="#000000" stroke-width="0.2">')
        m = min(4.0, bl)
        tx0, ty0 = bl, bl
        tx1, ty1 = bl + spec.page_w_mm, bl + spec.page_h_mm
        for (cx, cy, sx, sy) in [(tx0, ty0, -1, -1), (tx1, ty0, 1, -1),
                                 (tx0, ty1, -1, 1), (tx1, ty1, 1, 1)]:
            a(f'    <line x1="{cx + sx * 0.8:.2f}" y1="{cy:.2f}" '
              f'x2="{cx + sx * m:.2f}" y2="{cy:.2f}"/>')
            a(f'    <line x1="{cx:.2f}" y1="{cy + sy * 0.8:.2f}" '
              f'x2="{cx:.2f}" y2="{cy + sy * m:.2f}"/>')
        a('  </g>')

    # ---- 溯源信息 --------------------------------------------------------
    fy = bl + spec.page_h_mm - spec.safe_margin_mm - FOOTER_BAND_MM / 2 + 2.2
    left = bl + spec.safe_margin_mm
    right = bl + spec.page_w_mm - spec.safe_margin_mm
    a('  <g id="trace" inkscape:groupmode="layer" inkscape:label="trace" '
      'font-family="Helvetica, Arial, sans-serif" fill="#9AA0A6">')
    a(f'    <line x1="{left}" y1="{fy - 5.2:.2f}" x2="{right}" y2="{fy - 5.2:.2f}" '
      f'stroke="#E3E6EA" stroke-width="0.25"/>')
    a(f'    <text x="{left}" y="{fy:.2f}" font-size="2.6" letter-spacing="0.08">'
      f'{_esc(brand)} · A5 {spec.page_w_mm:g}×{spec.page_h_mm:g}mm · '
      f'{len(placements)} stickers · {now}</text>')
    a(f'    <text x="{right}" y="{fy:.2f}" font-size="2.6" text-anchor="end" '
      f'letter-spacing="0.08">JOB {_esc(job_id)} · CHK {_esc(fingerprint)} · '
      f'P{_esc(policy_version)}</text>')
    a('  </g>')

    # ---- 参考线（默认隐藏）----------------------------------------------
    a('  <g id="guides" inkscape:groupmode="layer" inkscape:label="guides" '
      'style="display:none" fill="none">')
    a(f'    <rect x="{bl}" y="{bl}" width="{spec.page_w_mm}" height="{spec.page_h_mm}" '
      f'stroke="#00A3FF" stroke-width="0.2" stroke-dasharray="2 1.2"/>')
    a(f'    <rect x="{bl + spec.safe_margin_mm}" y="{bl + spec.safe_margin_mm}" '
      f'width="{spec.page_w_mm - 2 * spec.safe_margin_mm}" '
      f'height="{spec.page_h_mm - 2 * spec.safe_margin_mm}" '
      f'stroke="#22C55E" stroke-width="0.2" stroke-dasharray="1.2 1.2"/>')
    a('  </g>')

    a('</svg>')
    return "\n".join(o)


# ---------------------------------------------------------------------------
# 预览图（给用户在下单前看效果，不参与印刷）
# ---------------------------------------------------------------------------

def render_preview(pieces: Sequence, placements: Sequence[Placement],
                   spec: Optional[SheetSpec] = None, dpi: int = 150,
                   show_cut: bool = True) -> Image.Image:
    spec = spec or SheetSpec()
    k = dpi / 25.4
    W = int(round(spec.canvas_w_mm * k))
    H = int(round(spec.canvas_h_mm * k))
    canvas = Image.new("RGB", (W, H), "#FFFFFF")

    for piece, p in zip(pieces, placements):
        w = max(1, int(round(p.w_mm * k)))
        h = max(1, int(round(p.h_mm * k)))
        im = piece.image.resize((w, h), Image.LANCZOS)
        canvas.paste(im, (int(round(p.x_mm * k)), int(round(p.y_mm * k))), im)

    d = ImageDraw.Draw(canvas)
    if show_cut:
        for p in placements:
            if len(p.cut_points_mm) >= 3:
                pts = [(x * k, y * k) for x, y in p.cut_points_mm]
                d.line(pts + [pts[0]], fill=(255, 0, 255), width=max(1, dpi // 150))

    bl = spec.bleed_mm
    d.rectangle([bl * k, bl * k, (bl + spec.page_w_mm) * k, (bl + spec.page_h_mm) * k],
                outline=(0, 163, 255), width=max(1, dpi // 200))
    return canvas
