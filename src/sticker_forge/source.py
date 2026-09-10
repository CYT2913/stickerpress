"""来源照片的校验、哈希与字节级副本。

交付契约要求 ``source-original.<ext>`` 与用户输入 **逐字节相同**：
不重编码、不改 EXIF、不改扩展名。用户后续要主张权属、要重印、要核对
"你们交付的是不是我给的那张"，靠的就是这份副本和它的 SHA-256。
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

from .imagesize import read_size, sniff_format

#: 允许的来源照片扩展名（HEIC 允许收，但本层不解尺寸）
ALLOWED_SUFFIX = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}

#: 来源照片尺寸下限。低于这个像素量，做到 A5 上的贴纸必然糊。
MIN_SOURCE_PX = 640


@dataclass
class SourceFile:
    path: Path
    size_bytes: int
    sha256: str
    fmt: str
    width: int
    height: int
    notes: list

    @property
    def suffix(self) -> str:
        return self.path.suffix.lower()

    def to_dict(self) -> dict:
        return {
            "filename": self.path.name,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "format": self.fmt,
            "width": self.width,
            "height": self.height,
            "notes": list(self.notes),
        }


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def load_source(path) -> SourceFile:
    """读取来源照片并做预检。不修改任何文件。"""
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"来源照片不存在：{p}")
    if p.suffix.lower() not in ALLOWED_SUFFIX:
        raise ValueError(
            f"不支持的来源格式 '{p.suffix}'；允许：{', '.join(sorted(ALLOWED_SUFFIX))}")

    size = p.stat().st_size
    if size == 0:
        raise ValueError(f"来源照片是空文件：{p}")

    digest = sha256_file(p)
    head = p.read_bytes()[:1 << 16]
    notes: list = []

    try:
        fmt, w, h = read_size(head)
    except Exception as exc:
        # HEIC/HEIF 走不到这里也没关系：不解尺寸不影响字节级留档，
        # 但必须显式记录"未能核验"，不能假装核验过了。
        fmt, w, h = (p.suffix.lower().lstrip("."), 0, 0)
        notes.append(f"未能解析图像尺寸（{exc}）；已按字节留档，尺寸需人工确认")
    else:
        declared = p.suffix.lower().lstrip(".")
        declared = "jpeg" if declared == "jpg" else declared
        if declared != fmt:
            notes.append(f"扩展名声明 {declared}，实际内容是 {fmt}")
        if min(w, h) < MIN_SOURCE_PX:
            notes.append(
                f"来源短边仅 {min(w, h)}px（建议 ≥{MIN_SOURCE_PX}px），"
                f"放到 A5 贴纸尺寸可能不足 300dpi")

    return SourceFile(path=p, size_bytes=size, sha256=digest,
                      fmt=fmt, width=w, height=h, notes=notes)


def copy_source(src: SourceFile, outdir) -> Path:
    """把来源照片逐字节复制到交付目录，并复核哈希一致。"""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    dst = outdir / f"source-original{src.suffix}"
    shutil.copyfile(src.path, dst)

    got = sha256_file(dst)
    if got != src.sha256:
        dst.unlink(missing_ok=True)
        raise IOError(f"原图副本哈希不一致：期望 {src.sha256}，实际 {got}")
    return dst


__all__ = ["SourceFile", "load_source", "copy_source", "sha256_file",
           "sniff_format", "ALLOWED_SUFFIX", "MIN_SOURCE_PX"]
