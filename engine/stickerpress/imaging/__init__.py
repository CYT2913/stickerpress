"""影像处理子系统：色度键抠图、六宫格切分、刀版轮廓矢量化、生成后端。"""

from .chroma import KeyResult, key_out, ensure_rgba
from .segment import StickerPiece, split_sheet
from .contour import (
    alpha_to_cut_path, build_cut_mask, min_distance_between,
    polygon_area, to_bezier_path, transform_path_points,
)
from .provider import (
    GenerationRequest, GenerationResult, StickerProvider,
    AimeImageProvider, SheetFileProvider, build_prompt, build_provider,
)

__all__ = [
    "KeyResult", "key_out", "ensure_rgba",
    "StickerPiece", "split_sheet",
    "alpha_to_cut_path", "build_cut_mask", "min_distance_between",
    "polygon_area", "to_bezier_path", "transform_path_points",
    "GenerationRequest", "GenerationResult", "StickerProvider",
    "AimeImageProvider", "SheetFileProvider", "build_prompt", "build_provider",
]
