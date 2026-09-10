"""StickerPress 命令行入口。

用法示例：

    # 最简：一张照片 → A5 六贴纸台纸
    python -m stickerpress.cli run photo.jpg -o ./out

    # 多张参考照 + 指定风格 + 主体描述
    python -m stickerpress.cli run a.jpg b.jpg --style retro --subject "我家的橘色博美" -o ./out

    # 跳过 AI 生成，直接排版一张现成的六宫格大图（返单重印 / 离线调试）
    python -m stickerpress.cli run photo.jpg --sheet sheet.png -o ./out

    # 查看当前生效的合规策略
    python -m stickerpress.cli policy
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from . import __version__
from .compliance import Action, build_reviewer, load_policy
from .config import SheetSpec, STYLE_LIBRARY
from .imaging import AimeImageProvider, SheetFileProvider
from .pipeline import StickerPressPipeline

_ICON = {"pass": "✅ 放行", "mitigate": "✅ 放行（已自动处置）",
         "review": "⚠️ 转人工复核", "block": "⛔ 拦截"}


def _cmd_run(args: argparse.Namespace) -> int:
    policy = load_policy(args.policy_file) if args.policy_file else load_policy()

    if args.sheet:
        provider = SheetFileProvider(args.sheet)
    else:
        provider = AimeImageProvider(resolution=args.resolution)
        if not provider.available:
            print("✗ 未找到可用的图像生成后端。请用 --sheet 指定一张现成的六宫格大图。",
                  file=sys.stderr)
            return 2

    reviewer = build_reviewer("off" if args.no_review else "auto")
    if args.no_review:
        print("⚠️  已关闭模型审核（--no-review），策略将按 fail_mode 降级处理\n")
    elif not reviewer.available:
        print("⚠️  未找到多模态审核器，合规闸门将按 fail_mode 降级处理\n")

    pipeline = StickerPressPipeline(
        policy=policy, provider=provider, reviewer=reviewer,
        spec=SheetSpec(bleed_mm=args.bleed, gutter_mm=args.gutter),
        operator=args.operator,
    )

    n = [0]

    def progress(msg: str) -> None:
        n[0] += 1
        print(f"  [{n[0]}] {msg} …", flush=True)

    print(f"StickerPress v{__version__} · 策略 {policy.policy_version}")
    print(f"输入 {len(args.photos)} 张照片 · 风格 {args.style} · 输出 {args.outdir}\n")

    res = pipeline.run(
        photos=[Path(p) for p in args.photos],
        outdir=Path(args.outdir),
        style_key=args.style,
        subject_hint=args.subject,
        job_id=args.job_id,
    )

    print()
    print("─" * 62)
    print(f"作业号 {res.job_id}    合规指纹 {res.fingerprint}")
    print(f"裁决：{_ICON.get(res.decision.value, res.decision.value)}"
          f"    可否下单印刷：{'是' if res.printable else '否'}")
    if res.quality:
        print(f"质检：{res.quality.get('sticker_count')} 张 · "
              f"最低 {res.quality.get('min_effective_dpi')} dpi · "
              f"刀版净距 {res.quality.get('min_knife_gap_mm')} mm")
    print("─" * 62)
    if res.svg_path:
        print(f"A5 台纸 : {res.svg_path}")
        print(f"预览图  : {res.preview_path}")
        print(f"原图    : {res.outdir / 'originals'} （{len(res.original_paths)} 张，已脱敏）")
        print(f"单张贴纸: {res.outdir / 'stickers'} （{len(res.sticker_paths)} 张）")
    print(f"审计    : {res.audit_path}")
    print(f"报告    : {res.report_path}")

    if res.decision == Action.BLOCK:
        return 3
    if res.decision == Action.REVIEW:
        return 1
    return 0


def _cmd_policy(args: argparse.Namespace) -> int:
    p = load_policy(args.policy_file) if args.policy_file else load_policy()
    print(f"策略版本 {p.policy_version}（{p.updated_at}）  owner={p.owner}")
    print(f"指纹 {p.fingerprint()}   fail_mode={p.fail_mode}\n")
    print(f"{'类目':<26}{'编码':<6}{'严重度':<8}{'处置':<10}生效闸门")
    print("-" * 78)
    for c in p.categories:
        gates = ",".join(g.value for g in c.gates)
        print(f"{c.name:<24}{c.code:<8}{c.severity:<9}{c.action.value:<11}{gates}")
    print(f"\n负向护栏 {len(p.guardrails_negative)} 条 · 敏感词 {len(p.keyword_blocklist)} 个")
    print(f"质量门槛：≥{p.quality.min_effective_dpi}dpi · "
          f"刀版净距≥{p.quality.min_knife_gap_mm}mm · "
          f"必须 {p.quality.required_sticker_count} 张")
    return 0


def _cmd_styles(_: argparse.Namespace) -> int:
    for k, s in STYLE_LIBRARY.items():
        print(f"{k:<12}{s.name_zh}")
        print(f"            {s.art_direction}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="stickerpress",
        description="照片 → A5 六贴纸印刷台纸（含合规风控与刀版矢量）",
    )
    ap.add_argument("--version", action="version", version=f"StickerPress {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="跑一次完整生产作业")
    r.add_argument("photos", nargs="+", help="输入照片（1 张或多张）")
    r.add_argument("-o", "--outdir", default="./out", help="输出目录（默认 ./out）")
    r.add_argument("--style", default="kawaii", choices=list(STYLE_LIBRARY),
                   help="贴纸风格")
    r.add_argument("--subject", default="", help="主体描述，如「我家的橘色博美」")
    r.add_argument("--sheet", default=None, help="跳过 AI，直接排版指定的六宫格大图")
    r.add_argument("--resolution", default="4k", choices=["1k", "2k", "4k"],
                   help="生成分辨率（默认 4k，保证 300dpi 印刷）")
    r.add_argument("--bleed", type=float, default=3.0, help="出血 mm（默认 3）")
    r.add_argument("--gutter", type=float, default=6.0, help="贴纸间距 mm（默认 6）")
    r.add_argument("--job-id", default=None, help="指定作业号")
    r.add_argument("--operator", default=getpass.getuser(), help="操作人")
    r.add_argument("--policy-file", default=None, help="自定义策略 YAML")
    r.add_argument("--no-review", action="store_true", help="关闭模型审核（仅调试）")
    r.set_defaults(func=_cmd_run)

    p = sub.add_parser("policy", help="查看当前生效的合规策略")
    p.add_argument("--policy-file", default=None)
    p.set_defaults(func=_cmd_policy)

    s = sub.add_parser("styles", help="列出可用风格")
    s.set_defaults(func=_cmd_styles)
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
