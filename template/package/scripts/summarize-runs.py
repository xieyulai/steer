#!/usr/bin/env python3
"""只读台账摘要：plateau / reflect 门禁 / best row（供 /auto-nn-analyse 与 auto-run 共用）。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lib.run_ledger_summary import (  # noqa: E402
    agent_config,
    build_summary,
    format_brief,
    format_keeper_status,
    format_roadmap_status,
    reflect_gate_decision,
    roadmap_status,
)
from lib.reflect_index import format_audit_lines  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Summarize _runs/results.tsv for analyse / reflect gate")
    ap.add_argument("--repo-root", type=Path, default=Path.cwd(), help="业务仓根目录")
    ap.add_argument("--format", choices=("brief", "json", "markdown"), default="brief")
    ap.add_argument("--reflect-gate", action="store_true", help="输出 auto-run 同款 run:R* / skip:* 一行")
    ap.add_argument("--roadmap-status", action="store_true", help="输出路线图阶段推断（与 auto-run 注入同源）")
    ap.add_argument(
        "--keeper-status",
        action="store_true",
        help="输出分场景 keeper / TSV best / plateau（focus 场景带 *）",
    )
    ap.add_argument(
        "--reflect-index-health",
        action="store_true",
        help="输出 REFLECT_INDEX 账本健康（PASS:/FAIL:/WARN: 行，供 nn-doctor）",
    )
    ap.add_argument(
        "--reflect-brief",
        action="store_true",
        help="输出 REFLECT-BRIEF（pending + 最近 consumed 历史）",
    )
    ap.add_argument("--run", type=int, default=1, help="reflect-gate 用轮次号（占位，与 auto-run 一致）")
    args = ap.parse_args()
    root = args.repo_root.resolve()

    if args.keeper_status:
        print("\n".join(format_keeper_status(root)))
        return 0

    if args.roadmap_status:
        print(format_roadmap_status(roadmap_status(root)))
        return 0

    if args.reflect_gate:
        plateau_n, interval = agent_config(root)
        print(reflect_gate_decision(root, args.run, interval, plateau_n))
        return 0

    if args.reflect_index_health:
        for line in format_audit_lines(root):
            print(line)
        return 0

    if args.reflect_brief:
        from lib.reflect_brief import format_reflect_brief  # noqa: WPS433

        print(format_reflect_brief(root), end="")
        return 0

    summary = build_summary(root, run=args.run)
    if args.format == "json":
        print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    elif args.format == "markdown":
        d = summary.to_dict()
        print("## 台账摘要（summarize-runs）")
        for k, v in d.items():
            if k == "aux_empty_rates" and v:
                print(f"- **{k}**: {v}")
            else:
                print(f"- **{k}**: {v}")
    else:
        print(format_brief(summary, repo_root=root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
