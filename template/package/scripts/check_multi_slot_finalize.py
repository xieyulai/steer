#!/usr/bin/env python3
"""L3-D1: 多槽 finalize 门禁 CLI — 真源 ``lib.round_ledger_closure.find_unfinalized_multi_slot``。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.round_ledger_closure import find_unfinalized_multi_slot  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(
        description="L3-D1 multi-slot finalize gate: 列出已 train_done 但未入账的 multi-slot exp"
    )
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    args = ap.parse_args()
    unfinalized = find_unfinalized_multi_slot(args.repo_root.resolve())
    if not unfinalized:
        print("OK: no unfinalized multi-slot runs")
        return 0
    for exp_dir in unfinalized:
        print(f"UNFINALIZED: {exp_dir.name}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
