"""离线单元测试：零依赖、不联网、不落交付目录。

覆盖四类回归：
  1. 原图字节与哈希保全
  2. 权利声明的拦截（缺省即拒绝，是这个产品的法律底线）
  3. 装配几何：6 枚、闭合刀线、净距、边距、自包含
  4. 装配器与验证器对 spec 的解读一致
"""

import base64
import io
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sticker_forge import (  # noqa: E402
    RightsError, assemble_sheet, copy_source, load_rights, load_source, verify_sheet,
)
from sticker_forge.imagesize import read_size  # noqa: E402
from sticker_forge.rights import evaluate  # noqa: E402
from sticker_forge.spec import CUT_STROKE_MM, SheetSpec  # noqa: E402


def make_png(w: int, h: int) -> bytes:
    """手搓一张 w×h 的 RGBA PNG。测试不引入 Pillow。"""
    raw = b"".join(b"\x00" + b"\xff\x00\x00\xff" * w for _ in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


def make_jpeg(w: int, h: int) -> bytes:
    """最小可解析的 JPEG 头（只需被尺寸解析器读懂）。"""
    return (b"\xff\xd8\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
            + b"\xff\xc0" + struct.pack(">H", 17) + b"\x08"
            + struct.pack(">HH", h, w) + b"\x03" + b"\x00" * 9
            + b"\xff\xd9")


GOOD_RIGHTS = {
    "declared_by": "测试客户",
    "declared_at": "2026-09-10",
    "owns_photo_copyright": "yes",
    "commercial_use_granted": "yes",
    "identifiable_people": "no",
    "third_party_ip": "no",
}


class TestImageSize(unittest.TestCase):
    def test_png(self):
        self.assertEqual(read_size(make_png(120, 80)), ("png", 120, 80))

    def test_jpeg(self):
        self.assertEqual(read_size(make_jpeg(300, 200)), ("jpeg", 300, 200))

    def test_rejects_garbage(self):
        with self.assertRaises(ValueError):
            read_size(b"definitely not an image")

    def test_detects_lying_extension(self):
        """扩展名写 .png、内容是 JPEG，必须被记为备注而不是静默通过。"""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "photo.png"
            p.write_bytes(make_jpeg(1200, 900))
            src = load_source(p)
            self.assertEqual(src.fmt, "jpeg")
            self.assertTrue(any("扩展名" in n for n in src.notes), src.notes)


class TestSource(unittest.TestCase):
    def test_hash_and_byte_identical_copy(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            data = make_png(1200, 900)
            photo = d / "holiday.png"
            photo.write_bytes(data)

            src = load_source(photo)
            self.assertEqual(src.size_bytes, len(data))

            out = d / "delivery"
            copied = copy_source(src, out)
            self.assertEqual(copied.name, "source-original.png")
            self.assertEqual(copied.read_bytes(), data,
                             "原图副本必须与输入逐字节一致")
            self.assertEqual(load_source(copied).sha256, src.sha256)

    def test_rejects_missing_and_empty(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):
                load_source(Path(d) / "nope.png")
            empty = Path(d) / "empty.png"
            empty.write_bytes(b"")
            with self.assertRaises(ValueError):
                load_source(empty)

    def test_flags_low_resolution(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "tiny.png"
            p.write_bytes(make_png(320, 240))
            self.assertTrue(any("300dpi" in n or "短边" in n
                                for n in load_source(p).notes))


class TestRights(unittest.TestCase):
    def test_complete_declaration_passes(self):
        self.assertTrue(evaluate(GOOD_RIGHTS).ok)

    def test_missing_field_blocks(self):
        for key in ("owns_photo_copyright", "commercial_use_granted",
                    "identifiable_people", "third_party_ip"):
            raw = dict(GOOD_RIGHTS)
            raw.pop(key)
            r = evaluate(raw)
            self.assertFalse(r.ok, f"{key} 缺失时必须拦截")
            self.assertTrue(any(key in b for b in r.blockers))

    def test_unknown_is_not_yes(self):
        """'unknown' / '待确认' 绝不能被读成授权。"""
        for word in ("unknown", "n/a", "待确认", "", "maybe", "?"):
            raw = dict(GOOD_RIGHTS, commercial_use_granted=word)
            self.assertFalse(evaluate(raw).ok, f"{word!r} 不应被当作已授权")

    def test_people_without_release_blocks(self):
        raw = dict(GOOD_RIGHTS, identifiable_people="yes")
        r = evaluate(raw)
        self.assertFalse(r.ok)
        self.assertTrue(any("portrait_release" in b for b in r.blockers))

        raw["portrait_release"] = "no"
        self.assertFalse(evaluate(raw).ok)

        raw["portrait_release"] = "yes"
        r = evaluate(raw)
        self.assertTrue(r.ok)
        self.assertTrue(r.warnings, "依赖用户声明时必须留下警示")

    def test_ip_without_license_blocks(self):
        raw = dict(GOOD_RIGHTS, third_party_ip="yes")
        self.assertFalse(evaluate(raw).ok)

    def test_missing_declarer_blocks(self):
        raw = dict(GOOD_RIGHTS)
        raw["declared_by"] = ""
        self.assertFalse(evaluate(raw).ok)

    def test_missing_file_raises(self):
        with self.assertRaises(RightsError):
            load_rights(Path(tempfile.gettempdir()) / "no-such-rights.json")


class TestAssemble(unittest.TestCase):
    def _artworks(self, d: Path, n: int = 6, px: int = 900):
        out = []
        for i in range(1, n + 1):
            p = d / f"sticker_{i:02d}.png"
            p.write_bytes(make_png(px, px))
            out.append(p)
        return out

    def test_requires_exactly_six(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for n in (0, 5, 7):
                with self.assertRaises(ValueError, msg=f"{n} 张应被拒绝"):
                    assemble_sheet(self._artworks(Path(tempfile.mkdtemp()), n))

    def test_geometry_and_layers(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            r = assemble_sheet(self._artworks(d), order_id="T-1",
                               source_sha256="a" * 64)
            spec = SheetSpec()

            self.assertEqual(len(r.placements), 6)
            self.assertGreaterEqual(r.min_knife_gap_mm, spec.min_knife_gap_mm)
            self.assertGreaterEqual(r.min_margin_mm, spec.safe_margin_mm)
            self.assertGreaterEqual(r.min_effective_dpi, 300)

            svg = r.svg
            self.assertIn(f'width="{spec.page_w_mm:g}mm"', svg)
            self.assertIn(f'height="{spec.page_h_mm:g}mm"', svg)
            self.assertIn('id="CutContour"', svg)
            self.assertEqual(svg.count("<image "), 6)
            self.assertEqual(svg.count("<path id=\"cut-"), 6)
            self.assertIn(f'stroke-width="{CUT_STROKE_MM}"', svg)

    def test_cutlines_are_closed(self):
        with tempfile.TemporaryDirectory() as d:
            r = assemble_sheet(self._artworks(Path(d)))
            import re
            ds = re.findall(r'<path id="cut-\d+" d="([^"]+)"', r.svg)
            self.assertEqual(len(ds), 6)
            for d_attr in ds:
                self.assertTrue(d_attr.strip().endswith("Z"),
                                "每条刀线都必须闭合")

    def test_self_contained_no_external_refs(self):
        with tempfile.TemporaryDirectory() as d:
            r = assemble_sheet(self._artworks(Path(d)))
            import re
            for href in re.findall(r'href="([^"]+)"', r.svg):
                self.assertTrue(href.startswith("data:"),
                                f"发现外链依赖：{href[:60]}")

    def test_rejects_low_resolution_assets(self):
        """资产像素不足以支撑 300dpi 时必须拒绝，而不是默默印糊。"""
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError) as ctx:
                assemble_sheet(self._artworks(Path(d), px=120))
            self.assertIn("dpi", str(ctx.exception))

    def test_target_dpi_auto_shrinks_low_resolution_assets(self):
        """低像素资产可通过缩小实体尺寸达到目标 dpi，不得插值放大。"""
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            arts = self._artworks(d, px=500)
            natural = assemble_sheet(arts, strict=False)
            adjusted = assemble_sheet(arts, target_dpi=300)

            self.assertLess(natural.min_effective_dpi, 300)
            self.assertAlmostEqual(adjusted.min_effective_dpi, 300, places=6)
            self.assertEqual(adjusted.auto_shrunk_count, 6)
            self.assertEqual(adjusted.target_dpi, 300)
            for before, after in zip(natural.placements, adjusted.placements):
                self.assertLess(after.w_mm, before.w_mm)
                self.assertLess(after.h_mm, before.h_mm)
                self.assertEqual(after.src_px, before.src_px)

            layout = adjusted.to_dict()
            self.assertEqual(layout["target_dpi"], 300.0)
            self.assertEqual(layout["auto_shrunk_count"], 6)
            for placement, cell in zip(adjusted.placements, SheetSpec().cell_boxes()):
                cx, cy, cw, ch = cell
                self.assertAlmostEqual(placement.x_mm + placement.w_mm / 2,
                                       cx + cw / 2, places=6)
                self.assertAlmostEqual(placement.y_mm + placement.h_mm / 2,
                                       cy + ch / 2, places=6)

    def test_target_dpi_only_shrinks_assets_that_need_it(self):
        """高分资产必须保持原尺寸，混合输入只缩低分项。"""
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            arts = []
            for i, px in enumerate((900, 500, 900, 500, 900, 500), 1):
                p = d / f"sticker_{i:02d}.png"
                p.write_bytes(make_png(px, px))
                arts.append(p)

            natural = assemble_sheet(arts, strict=False)
            adjusted = assemble_sheet(arts, target_dpi=300)

            self.assertEqual(adjusted.auto_shrunk_count, 3)
            self.assertGreaterEqual(adjusted.min_effective_dpi, 300)
            for i, (before, after) in enumerate(
                    zip(natural.placements, adjusted.placements)):
                if i % 2 == 0:
                    self.assertAlmostEqual(after.w_mm, before.w_mm)
                    self.assertAlmostEqual(after.h_mm, before.h_mm)
                else:
                    self.assertLess(after.w_mm, before.w_mm)
                    self.assertLess(after.h_mm, before.h_mm)

    def test_target_dpi_rejects_size_below_hard_minimum(self):
        """不能为了凑 dpi 把贴纸缩到 20mm 硬下限以下。"""
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError) as ctx:
                assemble_sheet(self._artworks(Path(d), px=120), target_dpi=300)
            self.assertIn("硬下限", str(ctx.exception))

    def test_target_dpi_must_meet_print_minimum(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError) as ctx:
                assemble_sheet(self._artworks(Path(d)), target_dpi=299)
            self.assertIn("不低于印刷门槛", str(ctx.exception))

    def test_target_dpi_must_be_finite(self):
        with tempfile.TemporaryDirectory() as d:
            arts = self._artworks(Path(d))
            for value in (float("nan"), float("inf"), float("-inf")):
                with self.subTest(value=value):
                    with self.assertRaisesRegex(ValueError, "有限数"):
                        assemble_sheet(arts, target_dpi=value)

    def test_cli_target_dpi_reaches_manifest_report_and_stdout(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            photo = d / "photo.png"
            photo.write_bytes(make_png(1200, 900))
            artwork_dir = d / "artworks"
            artwork_dir.mkdir()
            arts = self._artworks(artwork_dir, px=500)
            self.assertEqual(len(arts), 6)
            rights = d / "rights.json"
            rights.write_text(json.dumps(GOOD_RIGHTS), encoding="utf-8")
            outdir = d / "outputs" / "ORDER-CLI"

            proc = subprocess.run([
                sys.executable, str(ROOT / "forge.py"), "assemble", str(photo),
                "--artwork-dir", str(artwork_dir), "--rights", str(rights),
                "--outdir", str(outdir), "--target-dpi", "300",
            ], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
               env={**os.environ, "PYTHONIOENCODING": "utf-8"}, check=False)
            stdout = proc.stdout.decode("utf-8", errors="replace")
            stderr = proc.stderr.decode("utf-8", errors="replace")

            self.assertEqual(proc.returncode, 0, stderr)
            self.assertIn("目标 dpi : 300（自动缩小 6/6 枚）", stdout)
            manifest = json.loads((outdir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["layout"]["target_dpi"], 300.0)
            self.assertEqual(manifest["layout"]["auto_shrunk_count"], 6)
            report = (outdir / "delivery-report.md").read_text(encoding="utf-8")
            self.assertIn("自动缩小目标", report)
            self.assertIn("300 dpi", report)
            self.assertIn("缩小 6/6 枚", report)

            rejected_outdir = d / "outputs" / "REJECTED"
            rejected = subprocess.run([
                sys.executable, str(ROOT / "forge.py"), "assemble", str(photo),
                "--artwork-dir", str(artwork_dir), "--rights", str(rights),
                "--outdir", str(rejected_outdir), "--target-dpi", "299",
            ], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
               env={**os.environ, "PYTHONIOENCODING": "utf-8"}, check=False)
            self.assertEqual(rejected.returncode, 2)
            self.assertFalse(rejected_outdir.exists(),
                             "参数或装配校验失败时不得留下原图副本或半套交付")

    def test_each_bitmap_embedded_exactly_once(self):
        """每张位图只能内嵌一份。

        曾经同时写 xlink:href 和 SVG2 的 href，两个属性各存一份完整 data URI，
        400dpi 台纸凭空多出十几 MB。这里按 base64 载荷计数卡住回归。
        """
        import re
        with tempfile.TemporaryDirectory() as d:
            r = assemble_sheet(self._artworks(Path(d)))
            self.assertEqual(len(re.findall(r"base64,", r.svg)), 6,
                             "6 张贴纸应当只有 6 段 base64 载荷")
            self.assertEqual(len(re.findall(r"<image", r.svg)), 6)
            self.assertNotIn(' href="data:', r.svg,
                             "不要再写与 xlink:href 重复的 href 属性")


class TestVerify(unittest.TestCase):
    def _build(self, d: Path) -> Path:
        arts = []
        for i in range(6):
            p = d / f"a{i}.png"
            p.write_bytes(make_png(900, 900))
            arts.append(p)
        r = assemble_sheet(arts, order_id="V-1", source_sha256="b" * 64)
        svg = d / "sheet.svg"
        svg.write_text(r.svg, encoding="utf-8")
        return svg

    def test_verifier_accepts_own_output(self):
        with tempfile.TemporaryDirectory() as d:
            rep = verify_sheet(self._build(Path(d)))
            self.assertTrue(rep.ok, rep.to_text())
            self.assertTrue(rep.needs_human,
                            "内容合规必须始终列为人工复检，不能被自动判绿")

    def test_verifier_catches_tampering(self):
        """手改 SVG 绕过检查必须被抓到。"""
        with tempfile.TemporaryDirectory() as d:
            svg = self._build(Path(d))
            text = svg.read_text(encoding="utf-8")

            # 1) 删掉一条刀线
            broken = text.replace('<path id="cut-6"', '<rect id="cut-6-dead"', 1)
            svg.write_text(broken, encoding="utf-8")
            self.assertFalse(verify_sheet(svg).ok)

            # 2) 改成外链位图
            broken = text.replace("data:image/png;base64,", "https://cdn.example/x.png#", 1)
            svg.write_text(broken, encoding="utf-8")
            rep = verify_sheet(svg)
            self.assertFalse(rep.ok)
            self.assertTrue(any("外部资源" in c.name for c in rep.failed))

            # 3) 改画布尺寸
            broken = text.replace('width="148mm"', 'width="210mm"', 1)
            svg.write_text(broken, encoding="utf-8")
            self.assertFalse(verify_sheet(svg).ok)

    def test_verifier_reports_missing_file(self):
        rep = verify_sheet(Path(tempfile.gettempdir()) / "nope.svg")
        self.assertFalse(rep.ok)


class TestSpecParity(unittest.TestCase):
    """零依赖层与 engine/ 层的印刷规格必须同值。

    两层各自实现几何，如果常量偷偷跑偏，会出现"本地验收过了、
    引擎产出的版却不合规"这种最难查的问题。
    """

    def test_engine_config_matches(self):
        engine_cfg = ROOT / "engine" / "stickerpress" / "config.py"
        if not engine_cfg.exists():
            self.skipTest("engine/ 未安装")
        ns = {}
        src = engine_cfg.read_text(encoding="utf-8")
        # 不 import engine（它依赖 numpy/PIL），只取字面量
        import re
        def grab(name, text=src):
            m = re.search(rf"^\s*{name}: float = ([\d.]+)", text, re.M)
            return float(m.group(1)) if m else None

        spec = SheetSpec()
        for name, mine in (("bleed_mm", spec.bleed_mm),
                           ("safe_margin_mm", spec.safe_margin_mm),
                           ("gutter_mm", spec.gutter_mm),
                           ("min_knife_gap_mm", spec.min_knife_gap_mm),
                           ("piece_min_mm", spec.piece_min_mm),
                           ("piece_max_mm", spec.piece_max_mm),
                           ("piece_hard_min_mm", spec.piece_hard_min_mm)):
            theirs = grab(name)
            self.assertIsNotNone(theirs, f"engine/config.py 未找到 {name}")
            self.assertAlmostEqual(mine, theirs, places=4,
                                   msg=f"{name} 两层不一致：{mine} vs {theirs}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
