"""A5 台纸印刷规格。

与 ``engine/stickerpress/config.py`` 同值。两处都改动时，
``tests/test_forge.py::TestSpecParity`` 会比对，防止两层悄悄跑偏。

单位统一毫米。SVG 用户单位 = 1mm（由 viewBox 绑定物理尺寸），
这样刀版坐标可以被模切机直接按毫米解读。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

#: ISO A5 成品尺寸
A5_WIDTH_MM = 148.0
A5_HEIGHT_MM = 210.0

#: 商业印刷有效分辨率门槛
PRINT_DPI_MIN = 300

#: 页脚追溯带高度，写作业号 / 源文件指纹，不计入贴纸可用区
FOOTER_BAND_MM = 10.0

#: 模切专色约定。Roland / 拓美等设备识别名为 CutContour 的专色路径。
CUT_SPOT_NAME = "CutContour"
CUT_STROKE = "#FF00FF"

#: 印厂约定刀线 0.25 pt。本文件用户单位是 mm，必须换算：
#: 直接写 0.25 会得到 0.71 pt，2.8 倍过粗，模切机可能按粗线中心偏移下刀。
PT_TO_MM = 25.4 / 72.0
CUT_STROKE_PT = 0.25
CUT_STROKE_MM = round(CUT_STROKE_PT * PT_TO_MM, 4)  # ≈ 0.0882


@dataclass(frozen=True)
class SheetSpec:
    """A5 六枚 kiss-cut 台纸的版面规格。"""

    page_w_mm: float = A5_WIDTH_MM
    page_h_mm: float = A5_HEIGHT_MM

    #: kiss-cut 台纸默认无出血：所有图形内缩在安全边距内，
    #: 没有任何元素跨过成品边，因此不需要出血，SVG 根元素即 A5 成品尺寸。
    bleed_mm: float = 0.0

    #: 内容距成品边的最小距离
    safe_margin_mm: float = 10.0

    cols: int = 2
    rows: int = 3

    #: 相邻格位之间的间距
    gutter_mm: float = 8.0

    #: 相邻刀线的最小净距（验收门槛）
    min_knife_gap_mm: float = 8.0

    #: 单枚成品尺寸：建议区间与硬下限（任一方向）
    piece_min_mm: float = 22.0
    piece_max_mm: float = 62.0
    piece_hard_min_mm: float = 20.0

    #: 贴纸在格位内的内缩，保证刀线之间留出净距
    cell_pad_mm: float = 1.6

    #: 圆角刀线的圆角半径
    corner_r_mm: float = 4.0

    @property
    def slots(self) -> int:
        return self.cols * self.rows

    @property
    def canvas_w_mm(self) -> float:
        return self.page_w_mm + 2 * self.bleed_mm

    @property
    def canvas_h_mm(self) -> float:
        return self.page_h_mm + 2 * self.bleed_mm

    def cell_boxes(self) -> List[Tuple[float, float, float, float]]:
        """6 个格位的 (x, y, w, h)，原点在画布左上角。"""
        ox = self.bleed_mm + self.safe_margin_mm
        oy = self.bleed_mm + self.safe_margin_mm
        usable_w = self.page_w_mm - 2 * self.safe_margin_mm
        usable_h = self.page_h_mm - 2 * self.safe_margin_mm - FOOTER_BAND_MM
        cw = (usable_w - (self.cols - 1) * self.gutter_mm) / self.cols
        ch = (usable_h - (self.rows - 1) * self.gutter_mm) / self.rows
        return [
            (ox + c * (cw + self.gutter_mm), oy + r * (ch + self.gutter_mm), cw, ch)
            for r in range(self.rows)
            for c in range(self.cols)
        ]

    def fit(self, cell: Tuple[float, float, float, float],
            img_px: Tuple[int, int]) -> Tuple[float, float, float, float]:
        """等比缩放一张位图到格位内，返回 (x, y, w, h)。"""
        cx, cy, cw, ch = cell
        aw = cw - 2 * self.cell_pad_mm
        ah = ch - 2 * self.cell_pad_mm
        iw, ih = img_px
        if iw <= 0 or ih <= 0:
            raise ValueError(f"位图尺寸非法：{img_px}")
        s = min(aw / iw, ah / ih)
        w, h = iw * s, ih * s
        return cx + (cw - w) / 2, cy + (ch - h) / 2, w, h


DEFAULT_SPEC = SheetSpec()
