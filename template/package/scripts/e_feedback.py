#!/usr/bin/env python3
"""Change-proposal CLI: pending / resolve.

Usage:
  python3 scripts/e_feedback.py pending --repo-root .
  python3 scripts/e_feedback.py resolve --id E20260829_001 --status rejected --by <name> --note "…" --repo-root .
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lib.e_feedback_store import (  # noqa: E402
    load_records,
    pending_count,
    resolve,
    summarize,
)


def cmd_pending(repo_root: Path) -> int:
    print(summarize(repo_root))
    print(f"pending_count={pending_count(repo_root)}")
    for rec in load_records(repo_root):
        status = (rec.get("resolution") or {}).get("status")
        if status == "pending":
            print(json.dumps(rec, ensure_ascii=False))
    return 0


def cmd_resolve(repo_root: Path, eid: str, status: str, note: str, by: str) -> int:
    # `by` is a label the caller supplies. Never invent "human".
    actor = by.strip()
    if not actor:
        print("ERROR: --by 不能为空", file=sys.stderr)
        return 2
    try:
        updated = resolve(repo_root, eid, status, note=note, by=actor)
    except KeyError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    print(json.dumps(updated, ensure_ascii=False))
    return 0


def _add_repo_root(p: argparse.ArgumentParser) -> None:
    p.add_argument("--repo-root", default=".", help="项目根")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="改题待办 e_feedback：pending / resolve")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_pending = sub.add_parser("pending", help="列出 pending 记录与摘要")
    _add_repo_root(p_pending)

    p_resolve = sub.add_parser(
        "resolve",
        help="写下处置标记（不改合同、不开训）",
    )
    _add_repo_root(p_resolve)
    p_resolve.add_argument("--id", required=True, help="记录 id，如 E20260829_001")
    p_resolve.add_argument(
        "--status",
        required=True,
        choices=["adopted", "rejected", "deferred"],
    )
    p_resolve.add_argument(
        "--by",
        required=True,
        help="谁写下这条标记。只是备注；不传就不会写成 human",
    )
    p_resolve.add_argument("--note", default="", help="决议说明")

    args = parser.parse_args(argv)
    root = Path(args.repo_root).resolve()
    if args.cmd == "pending":
        return cmd_pending(root)
    if args.cmd == "resolve":
        return cmd_resolve(root, args.id, args.status, args.note, args.by)
    parser.error(f"未知子命令 {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
