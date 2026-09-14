"""v3 goal_spec: 纯函数（parse/validate/evaluate/format）。

设计原则（见 2026-06-28 spec）：
- 纯函数：只读 dict 输入，输出 dataclass；不触 nn-config.yaml / TSV
- 容错：parse 抛 ValueError（调用方转 doctor WARN）
- 容错：evaluate 数据缺失写 PredicateResult.error，不阻断
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lib.metric_units import UnitKind, metric_unit, normalize_to  # noqa: E402
from lib.run_ledger_summary import _best_row_for_scenario, _float_cell, _goal_met  # noqa: E402  # ★ v1.24.0 单一来源 _goal_met

# 共享常量（其他模块也引用）
GOAL_SPEC_KEY = "goal_spec"
COMBINE_PER_SCENARIO_ALL_OF = "per_scenario_all_of"
SUPPORTED_COMBINES = (COMBINE_PER_SCENARIO_ALL_OF,)
SUPPORTED_OPS = (">=", "<=")

# 让 `from lib.goal_spec import ...` 可工作（其他 lib 文件也这样做）
_LIB_DIR = Path(__file__).resolve().parent
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))


@dataclass(frozen=True)
class Predicate:
    """单条目标谓词。"""
    metric: str
    scenario: str
    op: str       # ">=" | "<="
    value: float  # 归一化到 ratio(percent → ratio 后存)
    metric_unit: UnitKind = "ratio"   # ★ v1.24.0 新增 — 业务仓填 percent 自动归一


@dataclass(frozen=True)
class GoalSpec:
    """v3 goal_spec 解析结果。"""
    combine: str
    predicates: tuple[Predicate, ...]


@dataclass
class PredicateResult:
    """单谓词评估结果。"""
    predicate: Predicate
    met: bool
    current: float | None
    gap: float | None
    error: str | None


@dataclass
class GoalSpecResult:
    """整套 goal_spec 评估结果。"""
    spec: GoalSpec
    per_scenario: dict[str, list[PredicateResult]]
    in_scope_scenarios: tuple[str, ...]
    met_scenarios: tuple[str, ...]
    pending_scenarios: tuple[str, ...]
    status: str   # "MET" | "PENDING"


def parse_goal_spec(agent: dict[str, Any]) -> GoalSpec | None:
    """从 agent 段解析 goal_spec；未配 / 空 → None。

    Raises:
        ValueError: 字段类型错（op 非法、value 非数值、combine 不支持等）。
    """
    raw = agent.get(GOAL_SPEC_KEY)
    if not isinstance(raw, dict) or not raw:
        return None

    predicates_raw = raw.get("predicates", [])
    if not predicates_raw:
        return None

    combine = raw.get("combine", COMBINE_PER_SCENARIO_ALL_OF)
    if combine not in SUPPORTED_COMBINES:
        raise ValueError(f"goal_spec.combine 不支持: {combine!r}（支持: {SUPPORTED_COMBINES}）")

    predicates: list[Predicate] = []
    for i, p in enumerate(predicates_raw):
        if not isinstance(p, dict):
            raise ValueError(f"goal_spec.predicates[{i}] 不是 dict: {p!r}")
        metric = str(p.get("metric", "")).strip()
        scenario = str(p.get("scenario", "")).strip()
        op = str(p.get("op", "")).strip()
        value_raw = p.get("value")

        if not metric:
            raise ValueError(f"goal_spec.predicates[{i}].metric 缺失")
        if not scenario:
            raise ValueError(f"goal_spec.predicates[{i}].scenario 缺失")
        if op not in SUPPORTED_OPS:
            raise ValueError(f"goal_spec.predicates[{i}].op={op!r} 不支持（支持: {SUPPORTED_OPS}）")
        if not isinstance(value_raw, (int, float)) or isinstance(value_raw, bool):
            raise ValueError(f"goal_spec.predicates[{i}].value={value_raw!r} 非数值")

        unit = metric_unit(metric)
        norm_value = normalize_to(float(value_raw), unit, "ratio")
        predicates.append(
            Predicate(metric=metric, scenario=scenario, op=op, value=float(norm_value), metric_unit=unit)
        )

    return GoalSpec(combine=combine, predicates=tuple(predicates))


def validate_goal_spec(
    spec: GoalSpec,
    *,
    allowed_metrics: set[str],
    f1_scenarios: set[str],
) -> None:
    """静态校验；配置无效 → raise ValueError（no-fallback，与 validate_scenario_id 同源）。

    metric 不在 contract.metric_keys ∪ auxiliary_keys / scenario 不在 F1 场景清单
    → 该谓词将无法匹配 TSV 列，属配置错误，硬失败（不兜底、不静默 WARN）。
    这让「写 TSV / 写 KEEP / 读 goal」三条链共用同一场景权威（README 清单）。
    """
    for p in spec.predicates:
        if p.metric not in allowed_metrics:
            raise ValueError(
                f"goal_spec 谓词 metric={p.metric!r} 不在 contract.metric_key ∪ auxiliary_keys；"
                f"该谓词将无法匹配 TSV 列（scenario={p.scenario!r}）"
            )
        if p.scenario not in f1_scenarios:
            raise ValueError(
                f"goal_spec 谓词 scenario={p.scenario!r} 不在 F1 manifest 场景清单"
            )
    return None


# ★ v1.24.0: _goal_gap 故意不复用 run_ledger_summary._goal_gap
# — v3 formatter 用 "gap=+X" 表达「超出多少」(正数=已过线),
#   v2 (run_ledger_summary) 用 "差" 表达「还差多少」(正数=未过);
#   同号语义相反,统一会改 formatter 输出,属 v2 锁。
def _goal_gap(current: float, goal: float, op: str) -> float:
    """距离 goal 的差距（正数 = 已过线，负数 = 未过）。"""
    return (current - goal) if op == ">=" else (goal - current)


def _per_scenario_metric_direction(repo_root: Path, metric: str) -> str:
    """列级方向：主指标用 contract.metric_direction；auxiliary 同主方向。"""
    from lib.run_ledger_summary import metric_key, metric_direction

    if metric == metric_key(repo_root):
        return metric_direction(repo_root)
    return metric_direction(repo_root)  # aux 暂同主方向（v3.1 可加 auxiliary_keys[col] 精确化）


def evaluate_goal_spec(
    spec: GoalSpec,
    repo_root: Path,
) -> GoalSpecResult:
    """评估整套 goal_spec；数据缺失写 PredicateResult.error，不抛。"""
    root = Path(repo_root).resolve()
    per_scenario: dict[str, list[PredicateResult]] = {}
    in_scope: list[str] = []
    seen: set[str] = set()

    for p in spec.predicates:
        if p.scenario not in seen:
            seen.add(p.scenario)
            in_scope.append(p.scenario)
            per_scenario[p.scenario] = []
        direction = _per_scenario_metric_direction(root, p.metric)
        row = _best_row_for_scenario(root, p.scenario, p.metric, direction)
        if row is None:
            per_scenario[p.scenario].append(
                PredicateResult(
                    predicate=p, met=False, current=None, gap=None,
                    error=f"scenario={p.scenario!r} 无 TSV 行（_runs/results.tsv）",
                )
            )
            continue
        val = _float_cell(row, p.metric)
        if val is None:
            per_scenario[p.scenario].append(
                PredicateResult(
                    predicate=p, met=False, current=None, gap=None,
                    error=f"scenario={p.scenario!r} best 行缺主指标列 {p.metric!r}",
                )
            )
            continue
        # val 是 TSV 行原值（evaluate 现查 metric_unit 而非复用 parse 时缓存）
        current_val = normalize_to(val, metric_unit(p.metric), "ratio")
        met = _goal_met(current_val, p.value, p.op)
        gap = _goal_gap(current_val, p.value, p.op)
        per_scenario[p.scenario].append(
            PredicateResult(predicate=p, met=met, current=val, gap=gap, error=None)
        )

    met_scenarios: list[str] = []
    pending_scenarios: list[str] = []
    for sid in in_scope:
        # per-scenario all-of：该场景所有谓词 met 才算该场景 met
        all_met = all(r.met for r in per_scenario[sid])
        if all_met:
            met_scenarios.append(sid)
        else:
            pending_scenarios.append(sid)

    status = "MET" if len(met_scenarios) == len(in_scope) else "PENDING"
    return GoalSpecResult(
        spec=spec,
        per_scenario=per_scenario,
        in_scope_scenarios=tuple(in_scope),
        met_scenarios=tuple(met_scenarios),
        pending_scenarios=tuple(pending_scenarios),
        status=status,
    )


def _format_predicate_short(r: PredicateResult) -> str:
    p = r.predicate
    if r.error:
        return f"{p.metric}: ({r.error})"
    op_sym = "≥" if p.op == ">=" else "≤"
    check = "✓" if r.met else "✗"
    return f"{p.metric}: {r.current:.6g} {op_sym} {p.value:.6g} {check}"


def format_goal_spec_progress(result: GoalSpecResult) -> str | None:
    """Run Context 注入单行/多行摘要。"""
    if not result.in_scope_scenarios:
        return None
    total = len(result.in_scope_scenarios)
    met_n = len(result.met_scenarios)
    lines = [
        f"goal_spec: {result.spec.combine} {met_n}/{total} scenarios met",
    ]
    for sid in result.in_scope_scenarios:
        preds = result.per_scenario[sid]
        met_count = sum(1 for r in preds if r.met)
        tag = "met" if sid in result.met_scenarios else "pending"
        details = "; ".join(_format_predicate_short(r) for r in preds)
        lines.append(f"  - scenario={sid} {tag}={met_count}/{len(preds)}  ({details})")
    return "\n".join(lines)


def format_goal_spec_matrix_lines(result: GoalSpecResult) -> list[str]:
    """`show --all` 矩阵输出（每 scenario 一块）。"""
    lines: list[str] = []
    for sid in result.in_scope_scenarios:
        lines.append(f"scenario={sid}")
        for r in result.per_scenario[sid]:
            p = r.predicate
            if r.error:
                lines.append(f"  {p.metric}  {r.error}  INVALID")
                continue
            met_s = "met" if r.met else "pending"
            gap_s = f"gap={r.gap:+.6g}" if r.gap is not None else "-"
            lines.append(
                f"  {p.metric}  current={r.current:.6g}  goal={p.value:.2f}  "
                f"op={p.op!r}  {met_s}  {gap_s}"
            )
        sid_tag = "met" if sid in result.met_scenarios else "pending"
        met_n = sum(1 for r in result.per_scenario[sid] if r.met)
        lines.append(f"  → {met_n}/{len(result.per_scenario[sid])} {sid_tag}")
    total = len(result.in_scope_scenarios)
    met_n = len(result.met_scenarios)
    lines.append(f"overall: {met_n}/{total} scenarios met")
    return lines
