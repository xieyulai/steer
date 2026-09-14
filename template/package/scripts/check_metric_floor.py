#!/usr/bin/env python3
"""explore 期 metric 底线护栏：读 nn-config agent.explore.metric_floor + best focus 行。

仅当 resolve_exploration().skip_goal_stop 且 explore.metric_floor 已设时判定。

exit code（与 auto-nn-run.sh 的契约）：
  0 = FLOOR_OK     （best focus 主指标未破底线）
  1 = FLOOR_BREACH （破线；auto-run 仅 WARN，不 break）
  2 = NO_FLOOR     （非 explore 有效态或未配 metric_floor）

用法：python3 scripts/check_metric_floor.py [repo_root]   # 默认 cwd
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lib.run_ledger_summary import floor_progress  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    repo_root = Path(args[0]).resolve() if args else Path.cwd().resolve()

    info = floor_progress(repo_root)
    if info is None:
        print("NO_FLOOR")
        return 2

    mk = info["metric"]
    floor = info["floor"]
    val = info["current"]
    sid = info["scenario_id"]

    if val is None:
        print(
            f"WARN: focus 场景 {sid!r} 无有效 TSV 行或缺主指标（{_runs_label(repo_root)}）",
            file=sys.stderr,
        )
        return 1

    if info["breached"]:
        gap = info["gap"] or abs(floor - val)
        print(f"FLOOR_BREACH {mk}={val} floor={floor} (差 {gap:.6g})")
        return 1
    print(f"FLOOR_OK {mk}={val} floor={floor}")
    return 0


def _runs_label(repo_root: Path) -> str:
    p = repo_root / "_runs" / "results.tsv"
    return str(p.relative_to(repo_root)) if p.is_file() else "_runs/results.tsv(缺)"


if __name__ == "__main__":
    raise SystemExit(main())
