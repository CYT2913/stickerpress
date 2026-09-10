"""StickerPress —— 照片转 A5 实体贴纸台纸的合规生产引擎。"""

__version__ = "1.0.0"

from .config import SheetSpec, StyleSpec, STYLE_LIBRARY, get_style  # noqa: E402

__all__ = ["__version__", "SheetSpec", "StyleSpec", "STYLE_LIBRARY", "get_style"]
