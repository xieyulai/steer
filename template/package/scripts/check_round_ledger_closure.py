#!/usr/bin/env python3
"""CLI: 轮末台账闭合检查（auto-nn-run reflect 前）。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.round_ledger_closure import format_lines, run_check  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Check unfinalized multi-slot runs and ledger drift")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--all-time",
        action="store_true",
        help="不限制 batch 时间窗（默认仅 saved/.batch_start_epoch 之后）",
    )
    parser.add_argument("--jsonl-tsv-warn-diff", type=int, default=10)
    parser.add_argument("--jsonl-tsv-fail-diff", type=int, default=50)
    args = parser.parse_args()
    result = run_check(
        args.repo_root,
        since_batch_start=not args.all_time,
        jsonl_tsv_warn_diff=args.jsonl_tsv_warn_diff,
        jsonl_tsv_fail_diff=args.jsonl_tsv_fail_diff,
    )
    for line in format_lines(result):
        stream = sys.stderr if line.startswith(("FAIL:", "WARN:")) else sys.stdout
        print(line, file=stream)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
