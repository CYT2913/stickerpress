#!/usr/bin/env python3
"""检查一张图能不能直接进产线：有没有真 alpha、是不是"假透明"、能切出几张。

用法：
    python3 engine/tools/check_alpha.py <图片路径> [更多图片...]
    python3 engine/tools/check_alpha.py sheet.png --expect 6

判断依据说明：
- **真透明**：文件带 alpha 通道，且有足够比例的像素是全透明的。可以直通产线。
- **假透明**：看着是灰白棋盘格，但那是模型把棋盘格**画**出来了，整幅不透明。
  必须重新出图，或改用品红背景走色度键。
- **不透明**：普通白底 / 彩底图。要么重新出图要求透明，要么用品红背景。

依赖 PIL / numpy / scipy（产线层依赖，非装配层）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("需要 Pillow：pip install pillow numpy scipy")

from engine.stickerpress.imaging.chroma import (  # noqa: E402
    alpha_stats, has_usable_alpha, looks_like_painted_checkerboard, prepare_rgba,
)
from engine.stickerpress.imaging.segment import split_sheet  # noqa: E402


def check(path: Path, expect: int) -> bool:
    print(f"\n=== {path.name} ===")
    try:
        img = Image.open(path)
    except Exception as e:
        print(f"  [x] 打不开：{type(e).__name__}: {e}")
        return False

    w, h = img.size
    print(f"  尺寸      : {w} × {h} px（{w * h / 1e6:.1f} MP）")
    print(f"  PIL mode  : {img.mode}")

    s = alpha_stats(img)
    if not s["has_alpha_channel"]:
        print("  alpha 通道: ✗ 没有")
    else:
        print(f"  alpha 通道: ✓ 有")
        print(f"  全透明    : {s['transparent_ratio']:.1%}")
        print(f"  半透明边缘: {s['semi_ratio']:.1%}")
        print(f"  不透明    : {s['opaque_ratio']:.1%}")

    usable = has_usable_alpha(img)
    fake = looks_like_painted_checkerboard(img)

    if usable:
        print("  结论      : ✅ 真透明，可直通产线（不需要品红背景）")
    elif fake:
        print("  结论      : ❌ 疑似假透明——棋盘格是画出来的，整幅不透明")
        print("              棋盘格会被当成贴纸的一部分印出来。请重新出图，")
        print("              或改用纯品红 #FF00FF 背景走色度键。")
    elif s["has_alpha_channel"]:
        print(f"  结论      : ⚠️ 有 alpha 通道但全透明像素只占 "
              f"{s['transparent_ratio']:.1%}（门槛 10%）")
        print("              可能是背景没抠干净，或保存时被合并成了不透明底。")
    else:
        print("  结论      : ⚠️ 不透明图。若背景是纯品红可走色度键，否则请重新出图。")

    # 实际跑一遍产线的前两步，看能不能切出预期张数
    try:
        res = prepare_rgba(img)
        pieces, diag = split_sheet(res.rgba, expected=expect, rows=3)
        mark = "✅" if len(pieces) == expect else "❌"
        print(f"  透明化方式: {'alpha 直通' if res.mode == 'alpha' else '色度键'}"
              f"（{res.note}）")
        print(f"  切分结果  : {mark} {len(pieces)} / {expect} 张")
        for d in diag:
            print(f"              · {d}")
        if len(pieces) != expect:
            print("              贴纸之间可能粘连（间隙不够）或有元素贴到画面边缘。")
        return len(pieces) == expect
    except Exception as e:
        print(f"  切分结果  : ❌ 异常 {type(e).__name__}: {e}")
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="检查图片透明度与可切分性")
    ap.add_argument("images", nargs="+", type=Path)
    ap.add_argument("--expect", type=int, default=6, help="期望切出的贴纸数，默认 6")
    args = ap.parse_args()

    ok = [check(p, args.expect) for p in args.images]
    total, good = len(ok), sum(ok)
    print(f"\n{'-' * 46}\n合计：{good}/{total} 张可直接进产线")
    return 0 if good == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
