#!/usr/bin/env python3
"""扫 TSV exploration_space 列 RDDN 旧词（extend→derived）。

供 nn-doctor innovation_vocab 检查 + 业务仓自查。核心逻辑在
``lib.innovation_audit.find_legacy_depth_in_tsv``；本脚本只做 CLI 包装。

用法:
  python3 scripts/check_innovation_vocab.py --check --repo-root .
    → 只读检查, 输出 ``PASS:`` / ``FAIL:`` 供 nn-doctor 解析
  python3 scripts/check_innovation_vocab.py --repo-root .
    → 打印命中详情 (TSV 行号 + experiment + 旧词→建议)
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.innovation_audit import find_legacy_depth_in_tsv  # noqa: E402


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repo-root", type=Path, default=Path.cwd(), help="业务仓根 (默认 cwd)")
    p.add_argument("--check", action="store_true",
                   help="只读检查模式: 输出 PASS:/FAIL: 供 nn-doctor")
    args = p.parse_args()

    hits = find_legacy_depth_in_tsv(args.repo_root.resolve())

    if args.check:
        if not hits:
            print("PASS: TSV exploration_space 列无 RDDN 旧词 (extend 等)")
            return 0
        print(f"FAIL: {len(hits)} 行 exploration_space 含旧词 (RDDN 正名 extend→derived):")
        for h in hits[:10]:
            print(f"  L{h['row']} {h['experiment']}: {h['exploration_space']} → {h['suggest']}")
        if len(hits) > 10:
            print(f"  ... 共 {len(hits)} 行")
        return 0

    if not hits:
        print("[innovation-vocab] 无旧词命中")
        return 0
    print(f"[innovation-vocab] {len(hits)} 行旧词命中:")
    for h in hits:
        print(f"  L{h['row']}\t{h['experiment']}\t{h['exploration_space']}\t{h['legacy']}→{h['suggest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
