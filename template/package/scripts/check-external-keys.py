#!/usr/bin/env python3
"""D2: 启动时一次性 key check banner CLI。

用法:
    python scripts/check-external-keys.py [--repo-root <path>] [--skip-keycheck]

输出格式(对齐 doctor row 风格):
    [external-keys] ✓ SERPER_API_KEY  ✓ GITHUB_TOKEN  ✗ OPENAI_API_KEY  ✗ ANTHROPIC_API_KEY

任何缺 → stderr 打一条 WARN 行,不阻断(返回 0)。
可通过 NN_SKIP_KEYCHECK=1 或 --skip-keycheck 静默跳过。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# 让 from lib.external.config import ... 在 scripts/ 直跑时也工作
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lib.external.config import KEY_VARS, check_external_keys  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="D2 external-keys banner")
    p.add_argument("--repo-root", default=".",
                   help="业务仓根(用于 .env 解析);默认 cwd")
    p.add_argument("--skip-keycheck", action="store_true",
                   help="静默 PASS,不打 banner (escape hatch)")
    args = p.parse_args()

    if args.skip_keycheck or os.environ.get("NN_SKIP_KEYCHECK") == "1":
        return 0

    repo_root = Path(args.repo_root).resolve()

    result = check_external_keys(repo_root=repo_root)

    parts: list[str] = []
    missing: list[str] = []
    for var in KEY_VARS:
        ok = result.get(var, False)
        mark = "✓" if ok else "✗"
        parts.append(f"{mark} {var}")
        if not ok:
            missing.append(var)

    print(f"[external-keys] {'  '.join(parts)}")
    if missing:
        print(f"[external-keys] WARN: 缺 {len(missing)} 个 key: {', '.join(missing)}",
              file=sys.stderr)
        print("[external-keys] WARN: 部分 external 通道将 silent skip",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())