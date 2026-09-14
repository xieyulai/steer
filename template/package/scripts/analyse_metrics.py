#!/usr/bin/env python3
"""只读数值分析：MA-1～MA-7（供 /auto-nn-analyse 与单测共用）。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lib.metric_analysis import build_analyse_report  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Analyse _runs/results.tsv metrics (MA-1～MA-7)")
    ap.add_argument("--repo-root", type=Path, default=Path.cwd(), help="业务仓根目录")
    ap.add_argument("--format", choices=("markdown", "json"), default="markdown")
    ap.add_argument(
        "--since-analyse",
        action="store_true",
        help="按 journal.analyse.tsv_row_count 切片 MA-3（无游标则全量）",
    )
    ap.add_argument(
        "--quiet",
        action="store_true",
        help="仅输出 MA-1；有增量时 MA-3；撞墙/高噪声 MA-7；有上次建议时 MA-6；跳过 MA-2/4/5",
    )
    args = ap.parse_args()
    root = args.repo_root.resolve()

    report = build_analyse_report(
        root, since_analyse=args.since_analyse, quiet=args.quiet
    )
    for w in report.warnings:
        print(w, file=sys.stderr)

    if args.format == "json":
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(report.markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
