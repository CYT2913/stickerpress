"""StickerPress 全局配置：印刷规格、版面参数、生成参数。

所有长度单位统一使用毫米（mm）。SVG 用户单位 = 1mm（通过 viewBox 绑定物理尺寸），
这样刀版轮廓的数值可以直接被印厂/切割机按毫米解读。
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Tuple


# --------------------------------------------------------------------------
# 印刷规格
# --------------------------------------------------------------------------

#: ISO A5 成品尺寸（mm）
A5_WIDTH_MM = 148.0
A5_HEIGHT_MM = 210.0

#: 输出栅格图的分辨率下限。300dpi 是商业印刷的通用门槛，
#: 低于该值时流水线会给出 WARN（不阻断，但会写进质检报告）。
PRINT_DPI_MIN = 300


def mm_to_px(mm: float, dpi: int = PRINT_DPI_MIN) -> int:
    """毫米 → 像素（按给定 dpi）。"""
    return int(round(mm / 25.4 * dpi))


@dataclass
class SheetSpec:
    """A5 贴纸台纸的版面规格。"""

    #: 成品尺寸
    page_w_mm: float = A5_WIDTH_MM
    page_h_mm: float = A5_HEIGHT_MM

    #: 出血。kiss-cut 台纸的默认值是 0：所有图形都内缩在安全边距里，
    #: 没有任何元素跨过成品边，因此不需要出血，SVG 根元素即 A5 成品尺寸。
    #: 只有改成"满版印刷 + 图案出血到边"的款式时才需要设为 3.0。
    bleed_mm: float = 0.0

    #: 安全边距：内容距成品边的最小距离，防裁切误差吃掉图形。
    safe_margin_mm: float = 10.0

    #: 版面栅格：2 列 × 3 行 = 6 张贴纸
    cols: int = 2
    rows: int = 3

    #: 贴纸之间的最小间距（刀版之间的"桥"，太近会导致排废）
    gutter_mm: float = 8.0

    #: 单张贴纸的刀版轮廓与相邻刀版的最小净距（质检阈值）
    min_knife_gap_mm: float = 8.0

    #: 单枚贴纸的建议尺寸区间与硬下限（任一方向）
    piece_min_mm: float = 22.0
    piece_max_mm: float = 62.0
    piece_hard_min_mm: float = 20.0

    #: 白色模切描边宽度（die-cut keyline），贴纸外圈那圈白边
    keyline_mm: float = 1.2

    @property
    def slots(self) -> int:
        return self.cols * self.rows

    @property
    def canvas_w_mm(self) -> float:
        """含出血的画布宽度。"""
        return self.page_w_mm + 2 * self.bleed_mm

    @property
    def canvas_h_mm(self) -> float:
        return self.page_h_mm + 2 * self.bleed_mm

    def cell_boxes(self) -> List[Tuple[float, float, float, float]]:
        """返回 6 个贴纸格位的 (x, y, w, h)，坐标系原点在**出血框左上角**。

        版面自上而下预留一条 footer 带用于印刷追溯信息（作业号 / 合规指纹），
        这条带不计入贴纸可用区。
        """
        ox = self.bleed_mm + self.safe_margin_mm
        oy = self.bleed_mm + self.safe_margin_mm

        usable_w = self.page_w_mm - 2 * self.safe_margin_mm
        usable_h = self.page_h_mm - 2 * self.safe_margin_mm - FOOTER_BAND_MM

        cell_w = (usable_w - (self.cols - 1) * self.gutter_mm) / self.cols
        cell_h = (usable_h - (self.rows - 1) * self.gutter_mm) / self.rows

        boxes = []
        for r in range(self.rows):
            for c in range(self.cols):
                x = ox + c * (cell_w + self.gutter_mm)
                y = oy + r * (cell_h + self.gutter_mm)
                boxes.append((x, y, cell_w, cell_h))
        return boxes


#: 页脚追溯带高度（mm）
FOOTER_BAND_MM = 10.0


# --------------------------------------------------------------------------
# 生成参数
# --------------------------------------------------------------------------

#: 色度键背景色。选纯品红是因为它在 HSV 空间里是一个几乎不会与
#: "宠物 / 人像 / 卡通" 主体撞色的极端点（H≈300°, S=100%, V=100%），
#: 比绿幕更安全（绿幕会误伤植物、绿色衣物、彩带）。
CHROMA_KEY_RGB = (255, 0, 255)


@dataclass
class StyleSpec:
    """贴纸美术风格。商业化时这一层就是"款式 SKU"。"""

    key: str
    name_zh: str
    #: 注入到生成提示词的风格描述
    art_direction: str
    #: 六格表情脚本（保证一套贴纸情绪不重复）
    expressions: List[str] = field(default_factory=list)
    #: 对应的中文标签，用于报告与前端展示
    expressions_zh: List[str] = field(default_factory=lambda: list(DEFAULT_EXPRESSIONS_ZH))

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT_EXPRESSIONS = [
    "happy laughing with eyes closed",
    "sleepy and curled up, eyes closed, a small floating sleep bubble (no letters)",
    "surprised, wide eyes, small exclamation marks",
    "in love, heart-shaped eyes, floating hearts",
    "grumpy and pouting, small huff clouds",
    "celebrating, arms up, colorful confetti",
]

DEFAULT_EXPRESSIONS_ZH = ["开心大笑", "困困睡觉", "震惊", "心动", "生气鼓包", "撒花庆祝"]

STYLE_LIBRARY = {
    "kawaii": StyleSpec(
        key="kawaii",
        name_zh="日系 Q 版",
        art_direction=(
            "chibi kawaii cartoon, bold flat vector illustration, clean thick outlines, "
            "bright saturated colors, soft cel shading"
        ),
        expressions=DEFAULT_EXPRESSIONS,
    ),
    "papercut": StyleSpec(
        key="papercut",
        name_zh="厚涂剪纸风",
        art_direction=(
            "thick painterly cut-paper collage look, layered flat shapes, rich texture, "
            "warm retro color palette, strong silhouette"
        ),
        expressions=DEFAULT_EXPRESSIONS,
    ),
    "retro": StyleSpec(
        key="retro",
        name_zh="复古印刷风",
        art_direction=(
            "1990s retro print sticker aesthetic, halftone dots, limited 4-color palette, "
            "slight registration offset, bold black keylines"
        ),
        expressions=DEFAULT_EXPRESSIONS,
    ),
    "watercolor": StyleSpec(
        key="watercolor",
        name_zh="水彩绘本风",
        art_direction=(
            "soft watercolor storybook illustration, gentle pastel washes, visible paper grain, "
            "delicate ink linework"
        ),
        expressions=DEFAULT_EXPRESSIONS,
    ),
}


def get_style(key: str) -> StyleSpec:
    if key not in STYLE_LIBRARY:
        raise KeyError(f"未知风格 '{key}'，可选：{', '.join(STYLE_LIBRARY)}")
    return STYLE_LIBRARY[key]
