"""背景透明化：优先直接用 alpha，拿不到 alpha 时才做色度键（chroma key）。

**入口是 prepare_rgba()，不要直接调 key_out()。**

两条路径：

1. **输入自带真 alpha** —— 现在的图像模型（含 ChatGPT 的图像生成）是可以
   直接输出带 alpha 通道的透明 PNG 的。这种情况下什么都不用做：直接进
   alpha 连通域切分，边缘质量比色度键更好，也没有溢色问题。这是首选路径。

2. **输入没有可用 alpha** —— 退回色度键：让模型在纯品红 #FF00FF 上作画，
   本模块把背景键掉。相比绿幕，品红在 HSV 里是"宠物 / 人像 / 卡通"几乎
   不会踩到的极端点，误伤率更低（绿幕会误伤植物、绿衣服、绿色彩带）。

色度键是**兜底**，不是首选。它存在的真正理由是第三种情况：模型把
Photoshop 那种灰白棋盘格**当图案画出来**了——看着像透明，其实整幅不透明。
这种"假透明"用 looks_like_painted_checkerboard() 检出，必须重新出图或
走色度键，不能硬跑（棋盘格会被当成贴纸主体的一部分印出来）。

历史注记：早期版本认定"模型不会输出真 alpha"，pipeline 无条件调用
key_out()，导致真透明 PNG 的 alpha 被 convert("RGB") 丢掉、背景变不透明、
6 张贴纸粘成 1 个连通域。见 CHANGELOG 2026-09-12。
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
    #: 背景（全透明）像素占比
    background_ratio: float
    #: 背景是否可信：alpha 直通时看透明占比，色度键时看键出占比
    keyed: bool
    note: str = ""
    #: "alpha" = 输入自带 alpha 直通；"chroma" = 做了色度键
    mode: str = "chroma"


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
        note=f"色度键背景占比 {bg_ratio:.1%}",
        mode="chroma",
    )


#: 判定"自带 alpha 可用"的门槛：至少这么多比例的像素是全透明的。
#: 六宫格贴纸大图的背景通常占 40%~70%，取 10% 已经很宽松。
MIN_ALPHA_BG_RATIO = 0.10


def alpha_stats(image: Image.Image) -> dict:
    """统计 alpha 通道情况，供诊断与人工判断使用。"""
    has_channel = image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info
    if not has_channel:
        return {"has_alpha_channel": False, "transparent_ratio": 0.0,
                "semi_ratio": 0.0, "opaque_ratio": 1.0}
    a = np.asarray(image.convert("RGBA").getchannel("A"))
    total = a.size
    return {
        "has_alpha_channel": True,
        "transparent_ratio": float((a < 16).sum() / total),
        "semi_ratio": float(((a >= 16) & (a < 240)).sum() / total),
        "opaque_ratio": float((a >= 240).sum() / total),
    }


def has_usable_alpha(image: Image.Image,
                     min_bg_ratio: float = MIN_ALPHA_BG_RATIO) -> bool:
    """输入是否已经带了可用的真 alpha。"""
    s = alpha_stats(image)
    return bool(s["has_alpha_channel"] and s["transparent_ratio"] > min_bg_ratio)


def looks_like_painted_checkerboard(image: Image.Image,
                                     border_frac: float = 0.06) -> bool:
    """启发式判断"假透明"：把 Photoshop 棋盘格当图案画出来了。

    特征是画面**没有**可用 alpha，但边缘一圈是近灰色、且只在两个亮度档位之间
    规律交替。只用于提示人工复核，不作为拦截依据——真实的灰白格纹贴纸背景
    也可能命中。
    """
    if has_usable_alpha(image):
        return False

    rgb = np.asarray(image.convert("RGB"), dtype=np.int16)
    h, w = rgb.shape[:2]
    bw = max(4, int(min(h, w) * border_frac))
    border = np.concatenate([
        rgb[:bw, :, :].reshape(-1, 3), rgb[-bw:, :, :].reshape(-1, 3),
        rgb[:, :bw, :].reshape(-1, 3), rgb[:, -bw:, :].reshape(-1, 3),
    ])

    # 1) 近灰：三通道彼此接近
    spread = border.max(axis=1) - border.min(axis=1)
    if float((spread <= 12).mean()) < 0.9:
        return False

    # 2) 双色阶：亮度集中在两个档位，且两档都占相当比例
    lum = border.mean(axis=1)
    hist, edges = np.histogram(lum, bins=32, range=(0, 255))
    top2 = np.argsort(hist)[-2:]
    if hist[top2].sum() / max(len(lum), 1) < 0.85:
        return False
    gap = abs(float(edges[top2[0]]) - float(edges[top2[1]]))
    # 棋盘格两档灰度差通常在 15~60 之间；差太小是纯色底，差太大是黑白图案
    return 8.0 <= gap <= 80.0


def prepare_rgba(image: Image.Image,
                 key_rgb: Tuple[int, int, int] = CHROMA_KEY_RGB) -> KeyResult:
    """**统一入口**：拿到一张大图，返回可直接做 alpha 连通域切分的 RGBA。

    自带真 alpha 就直通（首选），否则退回色度键（兜底）。

    直通比色度键更可取：没有溢色、没有 hard/soft 阈值带来的边缘损失，
    也不要求模型服从"必须画品红底"这条额外指令。
    """
    if has_usable_alpha(image):
        s = alpha_stats(image)
        return KeyResult(
            rgba=image.convert("RGBA"),
            background_ratio=s["transparent_ratio"],
            keyed=True,
            note=(f"输入自带 alpha，跳过色度键；透明 {s['transparent_ratio']:.1%}、"
                  f"半透明边缘 {s['semi_ratio']:.1%}"),
            mode="alpha",
        )

    res = key_out(image, key_rgb=key_rgb)
    if not res.keyed and looks_like_painted_checkerboard(image):
        res.note += "；疑似把棋盘格画成了图案（假透明），需重新出图"
    return res


def ensure_rgba(image: Image.Image) -> Image.Image:
    """prepare_rgba 的简写，只要图不要诊断信息。"""
    return prepare_rgba(image).rgba
