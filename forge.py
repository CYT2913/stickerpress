#!/usr/bin/env python3
"""StickerPress 本地装配器。

零依赖、无网络。三条命令：

    preflight   只校验来源照片、记录 SHA-256。不产出、不上传。
    assemble    由六张已审核资产 + 权利声明产出正式交付。
    verify      对已产出的 SVG 独立复核 AGENTS.md 0.5 的验收项。

需要"照片 → AI 生成贴纸 → 抠图 → 异形刀线 → 合规审核"的完整链路时，
走 engine/（依赖 Pillow / numpy / scipy），见 engine/README 与 docs/。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from sticker_forge import (  # noqa: E402
    RightsError, assemble_sheet, copy_source, load_rights, load_source, verify_sheet,
)
from sticker_forge.report import build_report  # noqa: E402
from sticker_forge.rights import TEMPLATE  # noqa: E402
from sticker_forge.spec import SheetSpec  # noqa: E402

ARTWORK_EXT = (".png", ".jpg", ".jpeg", ".webp")


def _collect_artworks(d: Path) -> list:
    if not d.exists() or not d.is_dir():
        raise FileNotFoundError(f"资产目录不存在：{d}")
    files = sorted(p for p in d.iterdir()
                   if p.is_file() and p.suffix.lower() in ARTWORK_EXT)
    if not files:
        raise FileNotFoundError(
            f"{d} 下没有可用资产；支持 {', '.join(ARTWORK_EXT)}")
    return files


# ---------------------------------------------------------------------------


def cmd_preflight(args) -> int:
    src = load_source(args.photo)
    print(f"文件      : {src.path.name}")
    print(f"字节数    : {src.size_bytes:,}")
    print(f"SHA-256   : {src.sha256}")
    print(f"格式/尺寸 : {src.fmt} · "
          f"{f'{src.width}×{src.height} px' if src.width else '尺寸未解析'}")
    if src.notes:
        print("\n预检备注：")
        for n in src.notes:
            print(f"  - {n}")

    if args.rights:
        try:
            rights = load_rights(args.rights)
        except RightsError as exc:
            print(f"\n[权利] {exc}", file=sys.stderr)
            return 2
        print(f"\n权利检查  : {'通过' if rights.ok else '未通过'}")
        for b in rights.blockers:
            print(f"  [拦截] {b}")
        for w in rights.warnings:
            print(f"  [注意] {w}")
        if not rights.ok:
            return 2
    else:
        print("\n未提供 --rights：装配阶段必须提供权利声明，否则不会产出印刷文件。")
        print("模板：python forge.py rights-template > rights.json")

    print("\n预检完成。未产出任何文件，未访问网络。")
    return 0


def cmd_rights_template(args) -> int:
    print(json.dumps(TEMPLATE, ensure_ascii=False, indent=2))
    return 0


def cmd_assemble(args) -> int:
    spec = SheetSpec()
    outdir = Path(args.outdir)
    order_id = args.order_id or outdir.name

    src = load_source(args.photo)
    rights = load_rights(args.rights)

    outdir.mkdir(parents=True, exist_ok=True)
    copied = copy_source(src, outdir)

    if not rights.ok:
        # 权利未确认：只留原图副本和一份说明拒绝原因的报告，不产出印刷文件。
        report = build_report(order_id, src, rights, spec,
                              source_copy_name=copied.name)
        (outdir / "delivery-report.md").write_text(report, encoding="utf-8")
        print("权利检查未通过，已拒绝产出印刷文件：", file=sys.stderr)
        for b in rights.blockers:
            print(f"  - {b}", file=sys.stderr)
        print(f"\n已写出：{outdir / 'delivery-report.md'}", file=sys.stderr)
        return 2

    artworks = _collect_artworks(Path(args.artwork_dir))
    labels = args.labels.split(",") if args.labels else None
    result = assemble_sheet(artworks, spec=spec, order_id=order_id,
                            source_sha256=src.sha256, labels=labels)

    svg_path = outdir / "a5-six-stickers.svg"
    svg_path.write_text(result.svg, encoding="utf-8")

    verify = verify_sheet(svg_path, spec=spec)
    report = build_report(order_id, src, rights, spec, result, verify,
                          source_copy_name=copied.name, svg_name=svg_path.name)
    (outdir / "delivery-report.md").write_text(report, encoding="utf-8")
    (outdir / "manifest.json").write_text(
        json.dumps({
            "order_id": order_id,
            "source": src.to_dict(),
            "rights": rights.to_dict(),
            "layout": result.to_dict(),
            "verify_passed": verify.ok,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"交付目录 : {outdir}")
    print(f"  {svg_path.name}")
    print(f"  {copied.name}")
    print("  delivery-report.md")
    print("  manifest.json")
    print(f"\n刀线净距 : {result.min_knife_gap_mm:.2f} mm")
    print(f"安全边距 : {result.min_margin_mm:.2f} mm")
    print(f"最低 dpi : {result.min_effective_dpi:.0f}")
    print(f"\n自动验收 : {'全部通过' if verify.ok else '存在未通过项'}")
    for c in verify.failed:
        print(f"  [FAIL] {c.name}：{c.detail}")
    print("\n以下项工具不下结论，交付前必须人工复检：")
    for x in verify.needs_human:
        print(f"  - {x}")
    return 0 if verify.ok else 1


def cmd_verify(args) -> int:
    rep = verify_sheet(args.svg, spec=SheetSpec())
    print(rep.to_text())
    return 0 if rep.ok else 1


# ---------------------------------------------------------------------------


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="forge.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("preflight", help="校验来源照片并记录 SHA-256")
    p.add_argument("photo")
    p.add_argument("--rights", help="权利声明 JSON（可选，但装配时必填）")
    p.set_defaults(func=cmd_preflight)

    p = sub.add_parser("rights-template", help="打印权利声明 JSON 模板")
    p.set_defaults(func=cmd_rights_template)

    p = sub.add_parser("assemble", help="由六张已审核资产产出 A5 交付")
    p.add_argument("photo")
    p.add_argument("--artwork-dir", required=True, help="含 6 张已审核资产的目录")
    p.add_argument("--rights", required=True, help="权利声明 JSON")
    p.add_argument("--outdir", required=True, help="交付输出目录")
    p.add_argument("--order-id", default="", help="订单号，默认取 outdir 目录名")
    p.add_argument("--labels", default="", help="六枚贴纸的中文标签，逗号分隔")
    p.set_defaults(func=cmd_assemble)

    p = sub.add_parser("verify", help="独立复核已产出的 SVG")
    p.add_argument("svg")
    p.set_defaults(func=cmd_verify)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except (RightsError, FileNotFoundError, ValueError) as exc:
        print(f"[x] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
