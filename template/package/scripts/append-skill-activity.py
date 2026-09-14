#!/usr/bin/env python3
"""Append 统一技能活动 log → `.auto-nn/skill-activity.jsonl`。

受 nn-config.yaml `safety.skill_activity_log` 控制（默认 true）。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lib.skill_activity import (
    activity_log_path,
    append_activity,
    count_entries,
    format_recent_markdown,
    is_enabled,
)


def _parse_artifacts(raw: str) -> list[str]:
    if not raw.strip():
        return []
    return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Append/read skill activity log")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_append = sub.add_parser("append", help="追加一条活动记录")
    p_append.add_argument("--repo-root", type=Path, default=Path.cwd())
    p_append.add_argument("--skill", required=True, help="如 auto-nn-modify")
    p_append.add_argument(
        "--phase",
        choices=("start", "confirm", "end"),
        required=True,
    )
    p_append.add_argument("--summary", default="")
    p_append.add_argument("--lock", default="")
    p_append.add_argument("--user", default="")
    p_append.add_argument("--ask", default="")
    p_append.add_argument("--options", default="")
    p_append.add_argument("--artifacts", default="", help="逗号分隔路径")
    p_append.add_argument("--session-id", default="")
    p_append.add_argument(
        "--force",
        action="store_true",
        help="忽略开关仍写入（测试/维护）",
    )

    p_status = sub.add_parser("status", help="开关与条数")
    p_status.add_argument("--repo-root", type=Path, default=Path.cwd())

    p_recent = sub.add_parser("recent", help="读最近 N 条")
    p_recent.add_argument("--repo-root", type=Path, default=Path.cwd())
    p_recent.add_argument("--limit", type=int, default=15)
    p_recent.add_argument(
        "--format",
        choices=("markdown", "jsonl"),
        default="markdown",
    )

    args = parser.parse_args()
    root = args.repo_root.resolve()

    if args.cmd == "append":
        if not args.force and not is_enabled(root):
            print("SKIP: safety.skill_activity_log=false", file=sys.stderr)
            return 0
        wrote = append_activity(
            root,
            skill=args.skill,
            phase=args.phase,
            summary=args.summary,
            lock=args.lock,
            user=args.user,
            ask=args.ask,
            options=args.options,
            artifacts=_parse_artifacts(args.artifacts),
            session_id=args.session_id,
            force=args.force,
        )
        if wrote:
            print(f"OK: appended → {activity_log_path(root)}")
        elif args.force:
            print(f"OK: appended (force) → {activity_log_path(root)}")
        return 0

    if args.cmd == "status":
        enabled = is_enabled(root)
        n = count_entries(root)
        print(
            f"enabled={str(enabled).lower()} "
            f"path={activity_log_path(root).relative_to(root)} "
            f"entries={n}"
        )
        return 0

    if args.cmd == "recent":
        if args.format == "jsonl":
            from lib.skill_activity import read_entries

            for rec in read_entries(root, limit=args.limit):
                import json

                print(json.dumps(rec, ensure_ascii=False))
        else:
            print(format_recent_markdown(root, limit=args.limit))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
