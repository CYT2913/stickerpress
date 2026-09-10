"""零依赖位图头解析：只读出宽高和真实格式，不解码像素。

装配器唯一需要位图的地方是"按原始宽高比放进格位"，因此没必要为了
读两个整数就把 Pillow 拉进运行依赖。同时这一步也顺带做了格式校验：
扩展名说自己是 PNG、内容却不是，会在这里被抓住。
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Tuple

#: 允许的贴纸资产格式（与 AGENTS.md 的输入契约一致）
SUPPORTED = ("png", "jpeg", "webp")

MIME = {"png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp"}


class ImageFormatError(ValueError):
    pass


def _png(b: bytes) -> Tuple[int, int]:
    # signature(8) + len(4) + 'IHDR'(4) + width(4) + height(4)
    if len(b) < 24 or b[12:16] != b"IHDR":
        raise ImageFormatError("PNG 缺少 IHDR 块")
    w, h = struct.unpack(">II", b[16:24])
    return w, h


def _jpeg(b: bytes) -> Tuple[int, int]:
    i, n = 2, len(b)
    while i + 9 < n:
        if b[i] != 0xFF:
            i += 1
            continue
        marker = b[i + 1]
        # SOF0..SOF15，跳过 DHT(C4) / JPG(C8) / DAC(CC) 这三个非 SOF
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            h, w = struct.unpack(">HH", b[i + 5:i + 9])
            return w, h
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        seg = struct.unpack(">H", b[i + 2:i + 4])[0]
        i += 2 + seg
    raise ImageFormatError("JPEG 未找到 SOF 段")


def _webp(b: bytes) -> Tuple[int, int]:
    if len(b) < 30 or b[8:12] != b"WEBP":
        raise ImageFormatError("WebP 头部不完整")
    chunk = b[12:16]
    if chunk == b"VP8X":
        w = int.from_bytes(b[24:27], "little") + 1
        h = int.from_bytes(b[27:30], "little") + 1
        return w, h
    if chunk == b"VP8L":
        bits = int.from_bytes(b[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8 ":
        if b[23:26] != b"\x9d\x01\x2a":
            raise ImageFormatError("WebP(VP8) 缺少关键帧同步码")
        w = struct.unpack("<H", b[26:28])[0] & 0x3FFF
        h = struct.unpack("<H", b[28:30])[0] & 0x3FFF
        return w, h
    raise ImageFormatError(f"不支持的 WebP 子格式：{chunk!r}")


def sniff_format(b: bytes) -> str:
    if b.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if b.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if b.startswith(b"RIFF") and b[8:12] == b"WEBP":
        return "webp"
    raise ImageFormatError("无法识别的图像格式；仅支持 PNG / JPEG / WebP")


def read_size(data: bytes) -> Tuple[str, int, int]:
    """返回 (format, width, height)。"""
    fmt = sniff_format(data)
    w, h = {"png": _png, "jpeg": _jpeg, "webp": _webp}[fmt](data)
    if w <= 0 or h <= 0:
        raise ImageFormatError(f"解析出的尺寸非法：{w}x{h}")
    return fmt, w, h


def read_size_file(path: Path) -> Tuple[str, int, int]:
    return read_size(Path(path).read_bytes())
