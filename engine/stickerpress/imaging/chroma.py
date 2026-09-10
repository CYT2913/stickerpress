"""色度键抠图（chroma key）。

生成模型不会真的输出带 alpha 通道的 PNG——直接要求"透明背景"时，它会把
Photoshop 那种灰白棋盘格**画**出来。所以本流水线改用色度键：强制模型在
纯品红 #FF00FF 上作画，再由本模块把背景键掉。

相比绿幕，品红在 HSV 里是一个"宠物 / 人像 / 卡通"几乎不会踩到的极端点，
误伤率更低（绿幕会误伤植物、绿衣服、绿色彩带）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np
from PIL import Image
from scipy import ndimage

from ..config import CHROMA_KEY_RGB


@dataclass
class KeyResult:
    rgba: Image.Image
    #: 背景像素占比，用于判断"是不是真的按要求画在品红上"
    background_ratio: float
    #: 是否检测到有效的色度键背景
    keyed: bool
    note: str = ""


def _distance_to_key(arr: np.ndarray, key: Tuple[int, int, int]) -> np.ndarray:
    """每个像素到键色的欧氏距离。"""
    k = np.array(key, dtype=np.float32)
    return np.sqrt(((arr.astype(np.float32) - k) ** 2).sum(axis=2))


def key_out(
    image: Image.Image,
    key_rgb: Tuple[int, int, int] = CHROMA_KEY_RGB,
    hard: float = 72.0,
    soft: float = 118.0,
    despill: bool = True,
) -> KeyResult:
    """把键色背景变成透明。

    :param hard: 距离小于该值 → 判定为纯背景（alpha=0）
    :param soft: 距离大于该值 → 判定为纯前景（alpha=255）；两者之间线性过渡，
                 用于保留抗锯齿边缘，避免刀版轮廓出现锯齿。
    :param despill: 是否做溢色抑制（去掉主体边缘沾上的品红光晕）

    关键设计：**只有与画布边缘连通的背景才会被去掉**。这样即使主体内部
    真的出现了一块接近键色的颜色，也不会被打穿成洞。
    """
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    dist = _distance_to_key(rgb, key_rgb)

    bgish = dist < soft
    # 与边缘连通性约束
    labels, n = ndimage.label(bgish)
    if n > 0:
        edge_labels = set(labels[0, :]) | set(labels[-1, :]) | set(labels[:, 0]) | set(labels[:, -1])
        edge_labels.discard(0)
        if edge_labels:
            connected = np.isin(labels, list(edge_labels))
        else:
            connected = np.zeros_like(bgish)
    else:
        connected = np.zeros_like(bgish)

    alpha = np.clip((dist - hard) / max(soft - hard, 1e-6), 0.0, 1.0)
    alpha = np.where(connected, alpha, 1.0)          # 非连通区域强制不透明
    alpha_u8 = (alpha * 255).astype(np.uint8)

    bg_ratio = float((alpha_u8 < 8).mean())

    out_rgb = rgb.astype(np.float32)
    if despill:
        # 品红溢色抑制：品红的特征是 R、B 高而 G 低。
        # 对 (R+B)/2 明显高于 G 的像素，把 R、B 往 G 拉回一部分。
        rb = (out_rgb[..., 0] + out_rgb[..., 2]) / 2.0
        spill = np.clip(rb - out_rgb[..., 1], 0, None)
        edge = (alpha > 0.02) & (alpha < 0.99)
        k = np.where(edge, 0.85, 0.0).astype(np.float32)
        out_rgb[..., 0] -= spill * k
        out_rgb[..., 2] -= spill * k
        out_rgb = np.clip(out_rgb, 0, 255)

    rgba = np.dstack([out_rgb.astype(np.uint8), alpha_u8])
    return KeyResult(
        rgba=Image.fromarray(rgba, mode="RGBA"),
        background_ratio=bg_ratio,
        keyed=bg_ratio > 0.15,
        note=f"背景占比 {bg_ratio:.1%}",
    )


def ensure_rgba(image: Image.Image) -> Image.Image:
    """若图片已自带有效 alpha（用户直接上传透明 PNG），则跳过色度键。"""
    if image.mode == "RGBA":
        a = np.asarray(image.getchannel("A"))
        if a.min() < 16 and (a < 16).mean() > 0.1:
            return image
    return key_out(image).rgba
