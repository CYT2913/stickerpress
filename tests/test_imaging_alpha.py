"""产线层背景透明化的回归测试。

为什么单独一个文件：装配层（forge.py / src/sticker_forge）刻意零第三方依赖，
而这里要测的 chroma / segment 依赖 PIL + numpy + scipy。没装依赖时整体 skip，
保证 `python3 -m unittest discover -s tests` 在纯净环境下照样能跑。

核心回归点：**真透明 PNG 不能再被色度键毁掉**。
早期 pipeline 无条件调用 key_out()，convert("RGB") 把 alpha 丢掉，
背景变不透明，6 张贴纸粘成 1 个连通域。见 CHANGELOG 2026-09-12。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from PIL import Image, ImageDraw

    from engine.stickerpress.imaging.chroma import (
        alpha_stats, has_usable_alpha, key_out, looks_like_painted_checkerboard,
        prepare_rgba,
    )
    from engine.stickerpress.imaging.segment import split_sheet
    HAVE_ENGINE_DEPS = True
except ImportError:  # pragma: no cover
    HAVE_ENGINE_DEPS = False


W, H = 600, 900
CIRCLE_R = 100


def _draw_six(img: "Image.Image", fill=(240, 170, 90, 255)) -> None:
    d = ImageDraw.Draw(img)
    for r in range(3):
        for c in range(2):
            cx, cy = 150 + c * 300, 150 + r * 300
            d.ellipse([cx - CIRCLE_R, cy - CIRCLE_R, cx + CIRCLE_R, cy + CIRCLE_R],
                      fill=fill, outline=(255, 255, 255, 255), width=6)


def _sheet_real_alpha() -> "Image.Image":
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    _draw_six(img)
    return img


def _sheet_magenta() -> "Image.Image":
    img = Image.new("RGBA", (W, H), (255, 0, 255, 255))
    _draw_six(img)
    return img.convert("RGB")


def _sheet_painted_checkerboard(square: int = 12) -> "Image.Image":
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for y in range(0, H, square):
        for x in range(0, W, square):
            if (x // square + y // square) % 2 == 0:
                d.rectangle([x, y, x + square - 1, y + square - 1], fill=(204, 204, 204))
    _draw_six(img, fill=(240, 170, 90))
    return img


@unittest.skipUnless(HAVE_ENGINE_DEPS, "缺少 PIL / numpy / scipy，跳过产线层影像测试")
class TestAlphaPassthrough(unittest.TestCase):
    """自带真 alpha 的输入必须原样直通，不许被色度键破坏。"""

    def test_real_alpha_is_detected(self):
        img = _sheet_real_alpha()
        self.assertTrue(has_usable_alpha(img))
        s = alpha_stats(img)
        self.assertTrue(s["has_alpha_channel"])
        self.assertGreater(s["transparent_ratio"], 0.4)

    def test_prepare_rgba_passes_through(self):
        res = prepare_rgba(_sheet_real_alpha())
        self.assertEqual(res.mode, "alpha")
        self.assertTrue(res.keyed)
        self.assertGreater(res.background_ratio, 0.4)

    def test_real_alpha_splits_into_six(self):
        """回归：这里曾经只切出 1 张。"""
        res = prepare_rgba(_sheet_real_alpha())
        pieces, _ = split_sheet(res.rgba, expected=6, rows=3)
        self.assertEqual(len(pieces), 6)

    def test_key_out_would_have_destroyed_it(self):
        """固化那个 bug 的现场：直接 key_out 会把真透明图毁掉。

        这条测试保证以后没人"顺手"把 pipeline 改回 key_out()。
        """
        res = key_out(_sheet_real_alpha())
        self.assertEqual(res.mode, "chroma")
        self.assertLess(res.background_ratio, 0.05)
        pieces, _ = split_sheet(res.rgba, expected=6, rows=3)
        self.assertNotEqual(len(pieces), 6)


@unittest.skipUnless(HAVE_ENGINE_DEPS, "缺少 PIL / numpy / scipy，跳过产线层影像测试")
class TestChromaFallback(unittest.TestCase):
    """没有 alpha 时退回品红色度键，行为不变。"""

    def test_magenta_uses_chroma(self):
        img = _sheet_magenta()
        self.assertFalse(has_usable_alpha(img))
        res = prepare_rgba(img)
        self.assertEqual(res.mode, "chroma")
        self.assertTrue(res.keyed)
        self.assertGreater(res.background_ratio, 0.4)

    def test_magenta_splits_into_six(self):
        res = prepare_rgba(_sheet_magenta())
        pieces, _ = split_sheet(res.rgba, expected=6, rows=3)
        self.assertEqual(len(pieces), 6)

    def test_interior_key_colour_is_not_punched_through(self):
        """主体内部出现品红时不能被打穿成洞：只键掉与边缘连通的背景。"""
        img = Image.new("RGBA", (W, H), (255, 0, 255, 255))
        _draw_six(img)
        d = ImageDraw.Draw(img)
        d.ellipse([150 - 30, 150 - 30, 150 + 30, 150 + 30], fill=(255, 0, 255, 255))
        res = prepare_rgba(img.convert("RGB"))
        pieces, _ = split_sheet(res.rgba, expected=6, rows=3)
        self.assertEqual(len(pieces), 6)


@unittest.skipUnless(HAVE_ENGINE_DEPS, "缺少 PIL / numpy / scipy，跳过产线层影像测试")
class TestFakeTransparency(unittest.TestCase):
    """画出来的棋盘格是最危险的一种：看着透明，印出来带格子。"""

    def test_painted_checkerboard_is_flagged(self):
        self.assertTrue(looks_like_painted_checkerboard(_sheet_painted_checkerboard()))

    def test_real_alpha_is_not_flagged(self):
        self.assertFalse(looks_like_painted_checkerboard(_sheet_real_alpha()))

    def test_magenta_is_not_flagged(self):
        self.assertFalse(looks_like_painted_checkerboard(_sheet_magenta()))

    def test_note_explains_the_failure(self):
        res = prepare_rgba(_sheet_painted_checkerboard())
        self.assertFalse(res.keyed)
        self.assertIn("假透明", res.note)


if __name__ == "__main__":
    unittest.main()
