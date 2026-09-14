#!/usr/bin/env python3
"""CLI：GPU 三档快照（exclusive / shareable / busy）。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.gpu_snapshot import (  # noqa: E402
    assign_slots,
    build_snapshot,
    format_gpu_table_lines,
    format_slot_assignment_lines,
    free_csv,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", type=Path, default=Path.cwd())
    ap.add_argument(
        "--snapshot-file",
        type=Path,
        default=None,
        help="已生成的 JSON 快照文件（跳过 nvidia-smi 重探）",
    )
    ap.add_argument(
        "--format",
        choices=("json", "free-csv", "legacy-free", "md-table", "assign"),
        default="json",
    )
    ap.add_argument("--assign-slots", type=int, default=0, help="--format assign 时并行槽数")
    args = ap.parse_args()
    if args.snapshot_file and args.snapshot_file.is_file():
        snap = json.loads(args.snapshot_file.read_text(encoding="utf-8"))
    else:
        snap = build_snapshot(args.repo_root.resolve())

    if args.format in ("free-csv", "legacy-free"):
        print(free_csv(snap))
        return 0
    if args.format == "md-table":
        print("\n".join(format_gpu_table_lines(snap)))
        return 0
    if args.format == "assign":
        n = max(1, int(args.assign_slots or 1))
        slots = assign_slots(snap, n)
        print(json.dumps({"n_slots": n, "assignments": slots}, ensure_ascii=False))
        return 0
    print(json.dumps(snap, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
