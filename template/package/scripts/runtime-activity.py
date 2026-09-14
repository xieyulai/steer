#!/usr/bin/env python3
"""运行态检测 CLI（analyse / nn-doctor 共用）。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lib.runtime_activity import (  # noqa: E402
    doctor_runtime_status,
    format_runtime_markdown,
    format_runtime_oneline,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Detect active auto-run batch / training")
    ap.add_argument("--repo-root", type=Path, default=Path.cwd())
    ap.add_argument(
        "--format",
        choices=("doctor", "markdown", "oneline"),
        default="markdown",
        help="doctor: PASS/WARN 一行；markdown/oneline：空闲无输出",
    )
    args = ap.parse_args()
    root = args.repo_root.resolve()

    if args.format == "doctor":
        level, msg = doctor_runtime_status(root)
        print(f"{level}: {msg}")
    elif args.format == "oneline":
        line = format_runtime_oneline(root)
        if line:
            print(line)
    else:
        text = format_runtime_markdown(root)
        if text:
            print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
