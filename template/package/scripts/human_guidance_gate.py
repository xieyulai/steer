#!/usr/bin/env python3
"""HUMAN_GUIDANCE 批次基线：write-baseline / check / refresh。"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lib.human_guidance_gate import (  # noqa: E402
    AutoRunActiveError,
    batch_hint_lines,
    check_human_guidance,
    doctor_status,
    post_round_enforce,
    refresh_baseline,
    write_baseline,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="HUMAN_GUIDANCE batch baseline gate")
    ap.add_argument("--repo-root", type=Path, default=Path.cwd())
    ap.add_argument(
        "action",
        choices=(
            "write-baseline",
            "check",
            "refresh",
            "doctor",
            "batch-hint",
            "post-round-enforce",
        ),
        nargs="?",
        default=None,
    )
    ap.add_argument(
        "--run",
        type=int,
        default=None,
        help=(
            "轮次序号（传给 post_round_enforce 修复 commit）；"
            "未设置时读取 NN_AUTO_RUN_ROUND，默认 0"
        ),
    )
    ap.add_argument("--write-baseline", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--doctor", action="store_true")
    ap.add_argument("--batch-hint", action="store_true")
    args = ap.parse_args()
    root = args.repo_root.resolve()

    action = args.action
    if args.write_baseline:
        action = "write-baseline"
    elif args.check:
        action = "check"
    elif args.refresh:
        action = "refresh"
    elif args.doctor:
        action = "doctor"
    elif args.batch_hint:
        action = "batch-hint"
    if action is None:
        action = "check"

    if action == "write-baseline":
        payload = write_baseline(root)
        if payload is None:
            print("SKIP: no HUMAN_GUIDANCE.md")
            return 0
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if action == "refresh":
        try:
            payload = refresh_baseline(root)
        except AutoRunActiveError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        if payload is None:
            print("SKIP: no HUMAN_GUIDANCE.md", file=sys.stderr)
            return 1
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if action == "doctor":
        level, msg = doctor_status(root)
        print(f"{level}: {msg}")
        return 0 if level in ("PASS", "SKIP") else 0

    if action == "batch-hint":
        hints = batch_hint_lines(root)
        if hints:
            for line in hints:
                print(line, file=sys.stderr)
        else:
            print("OK: no batch-activity hints")
        return 0

    if action == "post-round-enforce":
        run_n = args.run
        if run_n is None:
            try:
                run_n = int(os.environ.get("NN_AUTO_RUN_ROUND", "0") or "0")
            except ValueError:
                run_n = 0
        actions = post_round_enforce(root, run=run_n)
        for a in actions:
            if a.kind != "skip":
                print(f"G-HUMAN-{a.kind.upper()}: {a.detail}", file=sys.stderr)
        return 0

    err = check_human_guidance(root)
    if err:
        print(f"FAIL: {err}", file=sys.stderr)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
