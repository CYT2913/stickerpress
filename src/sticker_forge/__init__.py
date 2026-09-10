"""零依赖 A5 六枚贴纸装配器。

设计约束（来自 AGENTS.md 0.1.1）：``preflight`` / ``assemble`` / ``verify``
三条命令不得引入任何第三方运行依赖，也不得访问网络。因此本包只用标准库，
自行解析位图尺寸、拼装 SVG、复核成品几何。

需要 AI 生成、色度键抠图、异形刀线和 VLM 合规审核时，走 ``engine/``
（那一层依赖 Pillow / numpy / scipy），两层的印刷规格由 ``spec.py`` 与
``engine/stickerpress/config.py`` 保持同值。
"""

from .spec import SheetSpec, A5_WIDTH_MM, A5_HEIGHT_MM
from .source import SourceFile, load_source, copy_source
from .rights import Rights, RightsError, load_rights
from .assemble import AssembleResult, assemble_sheet
from .verify import VerifyReport, verify_sheet

__all__ = [
    "SheetSpec", "A5_WIDTH_MM", "A5_HEIGHT_MM",
    "SourceFile", "load_source", "copy_source",
    "Rights", "RightsError", "load_rights",
    "AssembleResult", "assemble_sheet",
    "VerifyReport", "verify_sheet",
]

__version__ = "0.2.0"
