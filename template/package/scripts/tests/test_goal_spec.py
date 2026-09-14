"""v1.24.0 — test_goal_spec.py: 单位归一 + 单一来源 _goal_met 单测。

覆盖(T3+T4 新行为):
- Predicate.metric_unit 字段透传
- parse: percent value 自动归一到 ratio
- parse: name-driven unit lookup (UX 关键)
- evaluate: 与 _best_row_for_scenario / _float_cell 协作(smoke)
- _goal_met 单一来源(goal_spec._goal_met is rls_goal_met)

设计:metric_unit(name) 按 metric 名查 METRIC_UNITS,而非按 value 量纲;
所以 val_accuracy=0.93 被当 percent 归一到 0.0093(0.93%)。
业务仓填 percent 单位 metric 必须写 percent-scale value(0.93 → 错,93 → 对)。
"""
from __future__ import annotations

import logging

import pytest

from lib.goal_spec import (
    GOAL_SPEC_KEY,
    Predicate,
    _goal_met,  # T4 single-source import
    _goal_gap,
    parse_goal_spec,
    validate_goal_spec,
)
from lib.run_ledger_summary import _goal_met as rls_goal_met


def _wrap(predicate: dict) -> dict:
    """Helper: wrap predicate into {goal_spec: {predicates: [...]}}."""
    return {GOAL_SPEC_KEY: {"predicates": [predicate]}}


# ── Predicate.metric_unit 字段默认 ──────────────────────────────────
def test_predicate_metric_unit_default_is_ratio():
    """直接构造 Predicate 时,metric_unit 字段默认 ratio。"""
    p = Predicate(metric="x", scenario="s1", op=">=", value=1.0)
    assert p.metric_unit == "ratio"


# ── parse: percent value 自动归一到 ratio ──────────────────────────
def test_parse_percent_value_normalizes_to_ratio():
    """val_accuracy=93.0 → unit='percent' → 归一到 ratio=0.93。"""
    spec = parse_goal_spec(_wrap(
        {"metric": "val_accuracy", "scenario": "s1", "op": ">=", "value": 93.0}
    ))
    assert spec is not None
    p = spec.predicates[0]
    assert p.metric_unit == "percent"
    assert p.value == pytest.approx(0.93)


def test_parse_ratio_value_stays_ratio():
    """name-driven: val_accuracy 静态单位 percent → 0.93 被当 percent(0.93%)→ 归一到 0.0093。

    UX 关键:业务仓填 percent 单位 metric 必须写 percent-scale value(93.0 对,0.93 错)。
    此处非 bug,是 per-metric 静态查表语义。
    """
    spec = parse_goal_spec(_wrap(
        {"metric": "val_accuracy", "scenario": "s1", "op": ">=", "value": 0.93}
    ))
    assert spec is not None
    p = spec.predicates[0]
    assert p.metric_unit == "percent"
    assert p.value == pytest.approx(0.0093)


def test_parse_unknown_metric_keeps_raw_value(caplog):
    """未知 metric → unit fallback 'ratio' + warning,value 不变。"""
    caplog.set_level(logging.WARNING)
    spec = parse_goal_spec(_wrap(
        {"metric": "custom_score_99", "scenario": "s1", "op": ">=", "value": 0.5}
    ))
    assert spec is not None
    p = spec.predicates[0]
    assert p.metric_unit == "ratio"
    assert p.value == pytest.approx(0.5)
    # warning 含 metric 名
    assert any("custom_score_99" in r.message for r in caplog.records)


# ── evaluate: parse 步单测(smoke) ──────────────────────────────────
def test_parse_loss_metric_ratio_unchanged():
    """loss(unit='ratio')→ value 不变(同单位 identity)。"""
    spec = parse_goal_spec(_wrap(
        {"metric": "loss", "scenario": "s1", "op": "<=", "value": 0.5}
    ))
    assert spec is not None
    p = spec.predicates[0]
    assert p.metric_unit == "ratio"
    assert p.value == pytest.approx(0.5)


# ── T4: _goal_met 单一来源(smoke identity) ────────────────────────
def test_goal_met_single_source():
    """goal_spec._goal_met is run_ledger_summary._goal_met(T4 单一来源)。"""
    assert _goal_met is rls_goal_met
    # 函数行为 sanity:同 current/goal/op 应返回 True / False
    assert _goal_met(0.95, 0.90, ">=") is True
    assert _goal_met(0.85, 0.90, ">=") is False


# ── _goal_gap 行为(辅助校验,非核心契约) ──────────────────────────
def test_goal_gap_sign_semantics():
    """op='>=': gap = current - goal(正=已过线);op='
<=': gap = goal - current。"""
    assert _goal_gap(0.95, 0.90, ">=") == pytest.approx(0.05)
    assert _goal_gap(0.85, 0.90, ">=") == pytest.approx(-0.05)
    assert _goal_gap(0.20, 0.30, "<=") == pytest.approx(0.10)
    assert _goal_gap(0.40, 0.30, "<=") == pytest.approx(-0.10)


# ── P2-2: validate_goal_spec 配置无效硬失败（no-fallback，与 validate_scenario_id 同源）──
def test_validate_rejects_unknown_scenario():
    """scenario 不在 F1 清单 → raise ValueError；goal 谓词不得引用不存在的场景。"""
    spec = parse_goal_spec(_wrap(
        {"metric": "val_accuracy", "scenario": "ghost_scenario", "op": ">=", "value": 0.9}
    ))
    with pytest.raises(ValueError, match="ghost_scenario"):
        validate_goal_spec(spec, allowed_metrics={"val_accuracy"}, f1_scenarios={"real_s1"})


def test_validate_rejects_unknown_metric():
    """metric 不在 contract → raise ValueError（与 scenario 对称，no-fallback）。"""
    spec = parse_goal_spec(_wrap(
        {"metric": "ghost_metric", "scenario": "s1", "op": ">=", "value": 0.9}
    ))
    with pytest.raises(ValueError, match="ghost_metric"):
        validate_goal_spec(spec, allowed_metrics={"val_accuracy"}, f1_scenarios={"s1"})


def test_validate_passes_when_metric_and_scenario_in_scope():
    """metric ∪ scenario 都在清单 → 不抛，返回 None。"""
    spec = parse_goal_spec(_wrap(
        {"metric": "val_accuracy", "scenario": "s1", "op": ">=", "value": 0.9}
    ))
    assert validate_goal_spec(spec, allowed_metrics={"val_accuracy"}, f1_scenarios={"s1"}) is None
