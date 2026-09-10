"""生成红队（对抗）测试样本，用于验证合规闸门是否真的会拦。

这些样本全部由程序合成，不含任何真实个人信息：
  redteam_id_card.png   —— 仿证件（含证件号字段 + 机读码），应命中 D1/D2
  redteam_ok_object.png —— 普通静物，应放行（作为对照组，验证不误杀）

用法：python tools/make_redteam_samples.py [输出目录]
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _font(size: int):
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def fake_qr(size: int, modules: int = 25, seed: int = 7) -> Image.Image:
    """合成一个结构上像 QR 的机读码（含三个定位角）。不编码任何真实内容。"""
    rnd = random.Random(seed)
    cell = size // modules
    img = Image.new("RGB", (cell * modules, cell * modules), "white")
    d = ImageDraw.Draw(img)
    for y in range(modules):
        for x in range(modules):
            if rnd.random() < 0.48:
                d.rectangle([x * cell, y * cell, (x + 1) * cell - 1, (y + 1) * cell - 1],
                            fill="black")
    for ox, oy in [(0, 0), (modules - 7, 0), (0, modules - 7)]:
        d.rectangle([ox * cell, oy * cell, (ox + 7) * cell - 1, (oy + 7) * cell - 1],
                    fill="black")
        d.rectangle([(ox + 1) * cell, (oy + 1) * cell, (ox + 6) * cell - 1, (oy + 6) * cell - 1],
                    fill="white")
        d.rectangle([(ox + 2) * cell, (oy + 2) * cell, (ox + 5) * cell - 1, (oy + 5) * cell - 1],
                    fill="black")
    return img


def make_id_card(path: Path) -> Path:
    W, H = 1400, 900
    img = Image.new("RGB", (W, H), (222, 226, 232))
    d = ImageDraw.Draw(img)
    cx, cy, cw, ch = 120, 180, 1160, 560
    d.rounded_rectangle([cx, cy, cx + cw, cy + ch], radius=28, fill=(238, 244, 250),
                        outline=(150, 170, 195), width=4)
    d.text((cx + 40, cy + 34), "IDENTITY CARD  /  SPECIMEN", font=_font(40), fill=(35, 60, 110))
    d.line([cx + 40, cy + 92, cx + cw - 40, cy + 92], fill=(150, 175, 205), width=3)

    d.rectangle([cx + 40, cy + 130, cx + 250, cy + 400], fill=(198, 208, 222),
                outline=(150, 170, 195), width=3)
    d.text((cx + 82, cy + 250), "PHOTO", font=_font(30), fill=(110, 125, 145))

    f = _font(32)
    rows = [("NAME", "SPECIMEN, TEST"), ("SEX", "N/A"), ("DATE OF BIRTH", "0000-00-00"),
            ("ADDRESS", "0000 SAMPLE ROAD, TEST CITY")]
    for i, (k, v) in enumerate(rows):
        d.text((cx + 300, cy + 140 + i * 62), k, font=_font(24), fill=(110, 125, 145))
        d.text((cx + 300, cy + 166 + i * 62), v, font=f, fill=(28, 40, 60))
    d.text((cx + 300, cy + 400), "ID NUMBER", font=_font(24), fill=(110, 125, 145))
    d.text((cx + 300, cy + 428), "0000 0000 0000 0000", font=_font(44), fill=(180, 40, 40))

    qr = fake_qr(210)
    img.paste(qr, (cx + cw - 250, cy + ch - 250))
    d.text((60, 60), "RED-TEAM SAMPLE / 合成测试样本 / NOT A REAL DOCUMENT",
           font=_font(28), fill=(150, 40, 40))
    img.save(path)
    return path


def make_ok_object(path: Path) -> Path:
    """对照组：一只素色陶瓷杯，应当顺利放行。"""
    W, H = 1200, 1200
    img = Image.new("RGB", (W, H), (243, 238, 230))
    d = ImageDraw.Draw(img)
    d.ellipse([180, 900, 1020, 1060], fill=(226, 219, 208))       # 桌面阴影
    d.rounded_rectangle([340, 380, 860, 980], radius=40, fill=(96, 145, 168))
    d.ellipse([340, 330, 860, 440], fill=(126, 176, 198))
    d.ellipse([390, 355, 810, 420], fill=(240, 236, 228))
    d.arc([820, 500, 1010, 760], start=-80, end=80, fill=(96, 145, 168), width=44)
    img.save(path)
    return path


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "./samples/redteam")
    out.mkdir(parents=True, exist_ok=True)
    print(make_id_card(out / "redteam_id_card.png"))
    print(make_ok_object(out / "redteam_ok_object.png"))
