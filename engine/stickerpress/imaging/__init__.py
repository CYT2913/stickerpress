"""影像处理子系统：背景透明化、六宫格切分、刀版轮廓矢量化、生成后端。"""

from .chroma import (
    KeyResult, alpha_stats, ensure_rgba, has_usable_alpha, key_out,
    looks_like_painted_checkerboard, prepare_rgba,
)
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
    "KeyResult", "prepare_rgba", "key_out", "ensure_rgba",
    "alpha_stats", "has_usable_alpha", "looks_like_painted_checkerboard",
    "StickerPiece", "split_sheet",
    "alpha_to_cut_path", "build_cut_mask", "min_distance_between",
    "polygon_area", "to_bezier_path", "transform_path_points",
    "GenerationRequest", "GenerationResult", "StickerProvider",
    "AimeImageProvider", "SheetFileProvider", "build_prompt", "build_provider",
]
