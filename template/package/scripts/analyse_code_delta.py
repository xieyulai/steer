#!/usr/bin/env python3
"""只读代码增量检查：CD-1～CD-7（WARN → stderr，exit 0）。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lib.code_delta import build_code_delta_report  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Analyse code delta since last analyse (CD-1～CD-7)")
    ap.add_argument("--repo-root", type=Path, default=Path.cwd())
    ap.add_argument(
        "--quiet",
        action="store_true",
        help="无 CD WARN 且 SKIP 时不输出 stdout",
    )
    args = ap.parse_args()
    root = args.repo_root.resolve()

    report = build_code_delta_report(root)
    for w in report.warnings:
        print(w, file=sys.stderr)
    for info in report.info_lines:
        if not args.quiet:
            print(info, file=sys.stderr)

    if args.quiet and (report.skipped or not report.warnings):
        return 0

    print("### 代码增量（analyse_code_delta）")
    if report.skipped:
        print(f"SKIP: {report.skip_reason}")
        return 0

    print(f"git range: {report.git_range}")
    if report.scoped_files:
        print("changed (train.py workspace/):")
        for path in report.scoped_files:
            print(path)
    else:
        print("changed (train.py workspace/): (无)")

    if report.all_files and report.all_files != report.scoped_files:
        extra = [f for f in report.all_files if f not in report.scoped_files]
        if extra:
            print("other changed:")
            for path in extra:
                print(path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
