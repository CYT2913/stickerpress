#!/usr/bin/env python3
"""把引擎的 policy.yaml 同步成 Web 操作台用的 policy.json。

策略只有一份真源。操作台不允许自己维护一套类目表——否则会出现
"页面上写着拦截、引擎实际放行"这种最危险的风控失配。

用法：
    python3 tools/sync_policy.py
"""

from __future__ import annotations

import json
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "stickerpress" / "compliance" / "policy.yaml"
DST = ROOT.parent / "console" / "src" / "lib" / "compliance" / "policy.json"


def main() -> int:
    if not SRC.exists():
        print(f"[x] 找不到策略源文件：{SRC}", file=sys.stderr)
        return 1
    data = yaml.safe_load(SRC.read_text(encoding="utf-8"))
    if not DST.parent.exists():
        print(f"[!] 目标目录不存在，跳过：{DST.parent}")
        return 0
    DST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[ok] policy_version={data['policy_version']} "
          f"categories={len(data['categories'])} -> {DST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
