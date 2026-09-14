#!/usr/bin/env python3
"""check_brief.py — auto-nn-check 默认参照摘要（只读）。

固定六段键（机器稳定键，Agent 翻译成说人话后再贴表）：
  focus / scenarios / goal / baseline / keeper / audit
  无审查卡片时 audit 仍占位：audit: (无)

用法：
  python3 scripts/check_brief.py [repo_root]
  python3 scripts/check_brief.py --root .
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lib.audit_core import injection_for_scenario  # noqa: E402
from lib.baseline_anchors_status import assess_baseline_anchors  # noqa: E402
from lib.run_ledger_summary import (  # noqa: E402
    format_goal_matrix_lines,
    format_goal_progress_line,
    format_keeper_status,
)
from lib.scenario_inventory import (  # noqa: E402
    focus_scenario_id,
    load_scenario_active,
    load_scenario_ids,
)


def render_check_brief(repo_root: Path) -> list[str]:
    """返回 stdout 行（无尾换行）。缺件用显式占位，不静默跳过段。"""
    root = repo_root.resolve()
    lines: list[str] = ["## check-brief"]

    focus = focus_scenario_id(root) or "(无)"
    lines.append(f"focus: {focus}")

    inventory = load_scenario_ids(root)
    active = load_scenario_active(root)
    inv_s = ",".join(inventory) if inventory else "(空)"
    act_s = ",".join(active) if active else "(未设)"
    lines.append(f"scenarios: inventory={inv_s} active={act_s}")

    goal_line = format_goal_progress_line(root)
    if goal_line:
        lines.append(f"goal: {goal_line}")
    else:
        lines.append("goal: NO_GOAL")
    for ml in format_goal_matrix_lines(root):
        lines.append(f"goal_matrix: {ml}")

    st = assess_baseline_anchors(root)
    lines.append(
        "baseline: "
        f"plain={'yes' if st.has_plain else 'NO'} "
        f"reference={'yes' if st.has_reference else 'NO'} "
        f"tag_col={'yes' if st.baseline_tag_col else 'NO'} "
        f"rows(plain/ref/other)={st.plain_tag_rows}/{st.reference_tag_rows}/{st.none_tag_rows}"
    )
    if st.missing:
        lines.append(f"baseline_missing: {','.join(st.missing)}")

    for kl in format_keeper_status(root):
        lines.append(f"keeper: {kl}")

    sid = "" if focus == "(无)" else str(focus).strip()
    inj = injection_for_scenario(root, sid) if sid else None
    if inj:
        lines.append(f"audit: {inj.get('status') or ''} {inj.get('card_dir') or '(无)'}".rstrip())
    else:
        lines.append("audit: (无)")

    from lib.e_feedback_store import summarize as e_summarize

    lines.append(e_summarize(root))

    return lines


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="auto-nn-check 默认参照摘要（只读）")
    p.add_argument(
        "repo_root_pos",
        nargs="?",
        default=None,
        help="业务仓根（与 --root 二选一；默认 cwd）",
    )
    p.add_argument("--root", default=None, help="业务仓根（覆盖位置参数）")
    args = p.parse_args(argv)

    raw = args.root or args.repo_root_pos or "."
    root = Path(raw).resolve()
    if not root.is_dir():
        print(f"[check_brief] 不是目录: {root}", file=sys.stderr)
        return 2

    for line in render_check_brief(root):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
