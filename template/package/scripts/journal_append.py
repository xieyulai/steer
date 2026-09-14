#!/usr/bin/env python3
"""追加 experiment journal 事件（round / analyse）。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lib.experiment_journal import append_analyse, append_round  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Append experiment journal round/analyse event")
    ap.add_argument("--repo-root", type=Path, default=Path.cwd(), help="业务仓根目录")
    ap.add_argument("--event", choices=("round", "analyse"), required=True)
    ap.add_argument("--apply", action="store_true", help="写入 saved/experiment_journal.json")
    ap.add_argument("--note", default="", help="round entry 可选 note（≤500 字符）")
    ap.add_argument("--summary", default="", help="analyse entry 摘要")
    ap.add_argument(
        "--recommendation-json",
        default="",
        help='analyse last_recommendation JSON，如 \'{"tier_hint":"B","summary":"…"}\'',
    )
    args = ap.parse_args()
    root = args.repo_root.resolve()

    if args.event == "round":
        result = append_round(
            root,
            apply=args.apply,
            note=args.note.strip() or None,
        )
        print(json.dumps({"facts": result["facts"], "entry": result["entry"]}, ensure_ascii=False, indent=2))
    else:
        result = append_analyse(
            root,
            apply=args.apply,
            summary=args.summary,
            recommendation_json=args.recommendation_json or None,
        )
        print(
            json.dumps(
                {"analyse": result["analyse"], "entry": result["entry"]},
                ensure_ascii=False,
                indent=2,
            )
        )

    if not args.apply:
        print("(dry-run: 未写盘；加 --apply 写入)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
