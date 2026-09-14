#!/usr/bin/env python3
"""CLI: reflect 运行时检查（auto-nn-update 硬门禁 / nn-doctor reflect_runtime）。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.reflect_runtime_check import format_lines, run_check  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Check reflect runtime deps (no LLM/CUDA)")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="业务仓根目录（默认 cwd）",
    )
    args = parser.parse_args()
    ok, failures = run_check(args.repo_root)
    for line in format_lines(ok, failures):
        print(line, file=sys.stderr if line.startswith("FAIL:") else sys.stdout)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
