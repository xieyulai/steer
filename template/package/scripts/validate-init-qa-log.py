#!/usr/bin/env python3
"""校验 `.auto-nn/init-qa-log.md` 完整性。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lib.init_qa_log import validate


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate init Q&A log")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--require-closed",
        action="store_true",
        help="F1 签字后须已 close",
    )
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    res = validate(args.repo_root.resolve(), require_closed=args.require_closed)
    if not args.quiet:
        for w in res.warnings:
            print(f"WARN: {w}", file=sys.stderr)
        for e in res.errors:
            print(f"FAIL: {e}", file=sys.stderr)
        if res.ok and not res.warnings:
            print(f"PASS: init-qa-log entries={res.entry_count} closed={res.closed}")
    if res.errors:
        return 1
    if res.warnings:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
