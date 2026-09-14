#!/usr/bin/env python3
"""auto-loop goal 停止条件判定：全局默认 + 按场景覆盖（见 per-scenario-goal spec）。

exit code（与 auto-nn-run.sh 的契约）：
  0 = GOAL_MET / GOAL_MET_ALL
  1 = GOAL_PENDING
  2 = NO_GOAL / GOAL_SKIPPED_EXPLORE

用法：python3 scripts/check_goal.py [repo_root]
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lib.run_ledger_summary import (  # noqa: E402
    _best_row_for_scenario,
    _float_cell,
    _goal_gap,
    _goal_met,
    _load_agent_section,
    _load_goal_section,
    effective_goal,
    goal_stop_mode,
    goals_in_scope,
    has_any_configured_goal,
    goal_config,
)
from lib.goal_spec import (  # noqa: E402
    evaluate_goal_spec,
    format_goal_spec_matrix_lines,
    format_goal_spec_progress,
    parse_goal_spec,
    validate_goal_spec,
)
from lib.scenario_inventory import load_scenario_ids  # noqa: E402


def _runs_label(repo_root: Path) -> str:
    p = repo_root / "_runs" / "results.tsv"
    return str(p.relative_to(repo_root)) if p.is_file() else "_runs/results.tsv(缺)"


def _try_load_contract(repo_root: Path):
    """尝试 import contract；失败返 None。"""
    import importlib.util
    p = repo_root / "contract" / "__init__.py"
    if not p.is_file():
        return None
    try:
        spec = importlib.util.spec_from_file_location("contract", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.Contract
    except Exception:
        return None


def _check_one_scenario(
    repo_root: Path,
    sid: str,
    gv: float,
    mk: str,
    op: str,
) -> tuple[bool, str, bool]:
    """返回 (met, detail_line, had_data_issue)。"""
    row = _best_row_for_scenario(repo_root, sid, mk)
    if row is None:
        print(
            f"WARN: scenario {sid!r} 无 TSV 行（{_runs_label(repo_root)}）",
            file=sys.stderr,
        )
        return False, f"  {sid}: (无 TSV 行)  pending", True
    val = _float_cell(row, mk)
    if val is None:
        print(
            f"WARN: scenario {sid!r} best 行缺主指标列 {mk!r}",
            file=sys.stderr,
        )
        return False, f"  {sid}: (缺 {mk})  pending", True
    if _goal_met(val, gv, op):
        return True, f"  {sid}: {mk}={val} {op} {gv}  met", False
    gap = _goal_gap(val, gv, op)
    return False, f"  {sid}: {mk}={val} {op} {gv}  pending (gap {gap:.6g})", False


def _check_focus_only(repo_root: Path) -> int:
    goal_value, mk, op, sid = goal_config(repo_root)
    if goal_value is None:
        print("NO_GOAL")
        return 2
    met, detail, _ = _check_one_scenario(repo_root, sid, goal_value, mk, op)
    if met:
        row = _best_row_for_scenario(repo_root, sid, mk)
        val = _float_cell(row or {}, mk)
        print(f"GOAL_MET focus {sid} {mk}={val} {op} {goal_value}")
        return 0
    row = _best_row_for_scenario(repo_root, sid, mk)
    if row is None or _float_cell(row, mk) is None:
        return 1
    val = _float_cell(row, mk)
    gap = abs(_goal_gap(float(val), goal_value, op))
    print(f"GOAL_PENDING focus {sid} {mk}={val} {op} {goal_value} (差 {gap:.6g})")
    return 1


def _check_all_in_scope(repo_root: Path) -> int:
    goal = _load_goal_section(repo_root)
    _, mk, op, _ = goal_config(repo_root)
    sids = goals_in_scope(repo_root)
    tracked: list[tuple[str, float]] = []
    for sid in sids:
        gv = effective_goal(goal, sid)
        if gv is not None:
            tracked.append((sid, gv))
    if not tracked:
        print("NO_GOAL")
        return 2
    met_count = 0
    details: list[str] = []
    for sid, gv in tracked:
        met, detail, _ = _check_one_scenario(repo_root, sid, gv, mk, op)
        details.append(detail)
        if met:
            met_count += 1
    total = len(tracked)
    if met_count == total:
        print(f"GOAL_MET_ALL {met_count}/{total} met")
        for d in details:
            print(d)
        return 0
    print(f"GOAL_PENDING all_in_scope {met_count}/{total} met")
    for d in details:
        print(d)
    return 1


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    repo_root = Path(args[0]).resolve() if args else Path.cwd().resolve()

    try:
        from lib.experiment_mode import resolve_exploration

        if resolve_exploration(repo_root).skip_goal_stop:
            print("GOAL_SKIPPED_EXPLORE")
            return 2
    except (ImportError, KeyError):
        # KeyError = 未迁移配置（无 exploration_mode，非 explore 档）→ 正常走 goal 检查
        pass

    agent = _load_agent_section(repo_root)

    # ── v3 路径（goal_spec 仍走 agent.*；v4 不迁移 goal_spec）──
    try:
        spec = parse_goal_spec(agent)
    except ValueError as e:
        print(f"ERROR: goal_spec 解析失败: {e}", file=sys.stderr)
        # 解析失败 → 视同 NO_GOAL（不阻断 batch；等 doctor WARN 提醒）
        return 2

    if spec is not None:
        # 静态校验
        from lib.run_ledger_summary import metric_key

        # 收集 allowed_metrics：contract.metric_key + auxiliary_keys
        c = _try_load_contract(repo_root)
        allowed: set[str] = {metric_key(repo_root)}
        if c is not None:
            for k in (getattr(c, "auxiliary_keys", {}) or {}).keys():
                allowed.add(k)
        f1 = set(load_scenario_ids(repo_root) or [])
        try:
            validate_goal_spec(spec, allowed_metrics=allowed, f1_scenarios=f1)
        except ValueError as e:
            print(f"ERROR: goal_spec 配置无效: {e}", file=sys.stderr)
            print(
                "ERROR: 谓词引用了不存在的 metric 或 scenario;"
                "请核对 contract.metric_keys ∪ auxiliary_keys 与 README 场景清单",
                file=sys.stderr,
            )
            return 2
        # 评估
        try:
            result = evaluate_goal_spec(spec, repo_root)
        except Exception as e:
            print(f"ERROR: goal_spec 评估失败: {e}", file=sys.stderr)
            return 2
        # 输出
        total = len(result.in_scope_scenarios)
        met_n = len(result.met_scenarios)
        if result.status == "MET":
            print(f"GOAL_MET_ALL {met_n}/{total} scenarios met")
            for sid in result.in_scope_scenarios:
                for r in result.per_scenario[sid]:
                    p = r.predicate
                    print(f"  {sid}: {p.metric}={r.current:.6g} {p.op} {p.value:.6g}  met")
            return 0
        else:
            print(f"GOAL_PENDING {met_n}/{total} scenarios met")
            for sid in result.in_scope_scenarios:
                for r in result.per_scenario[sid]:
                    p = r.predicate
                    if r.error:
                        print(f"  {sid}: {p.metric}  {r.error}  pending")
                    else:
                        gap_s = f"gap={r.gap:+.6g}" if r.gap is not None else "-"
                        print(f"  {sid}: {p.metric}={r.current:.6g} {p.op} {p.value:.6g}  pending ({gap_s})")
            return 1

    # ── v2 路径（goal.target / goal.policy）──
    goal = _load_goal_section(repo_root)
    mode = goal_stop_mode(goal)
    if mode == "strict":
        if not has_any_configured_goal(goal):
            print("NO_GOAL")
            return 2
        return _check_all_in_scope(repo_root)

    goal_value, _, _, sid = goal_config(repo_root)
    if goal_value is None:
        print("NO_GOAL")
        return 2
    return _check_focus_only(repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
