"""TDD tests for Contract._safe_metric + Contract.default_metrics (Layer 2).

mock Strategy:不依赖 ExperimentBase 完整初始化,直接用 Contract 实例。
Contract 已暴露 _safe_metric 为 property + default_metrics 骨架方法。
"""
from __future__ import annotations

import math

import pytest

from contract import Contract


@pytest.fixture
def contract_instance() -> Contract:
    return Contract()


# ── _safe_metric Property ──────────────────────────────────────────
def test_safe_metric_property_none_returns_zero(contract_instance):
    """None 输入默认返回 0.0"""
    assert contract_instance._safe_metric(None) == 0.0


def test_safe_metric_property_none_with_default(contract_instance):
    """None 输入可指定 default"""
    assert contract_instance._safe_metric(None, default=0.93) == 0.93


def test_safe_metric_property_passes_through(contract_instance):
    """合法数值(包括字符串数字)直接 passthrough"""
    assert contract_instance._safe_metric(0.93) == 0.93
    assert contract_instance._safe_metric(43.46) == 43.46
    assert contract_instance._safe_metric("0.93") == 0.93


def test_safe_metric_property_filters_nan_inf(contract_instance):
    """NaN / inf 被过滤回 default(0.0)"""
    assert contract_instance._safe_metric(float("nan")) == 0.0
    assert contract_instance._safe_metric(float("inf")) == 0.0
    assert contract_instance._safe_metric(-float("inf")) == 0.0


def test_safe_metric_property_non_numeric_returns_default(contract_instance):
    """非数(字符串/对象/list) → 默认值"""
    assert contract_instance._safe_metric("abc") == 0.0
    assert contract_instance._safe_metric("abc", default=0.5) == 0.5
    assert contract_instance._safe_metric([1, 2, 3]) == 0.0


# ── default_metrics Skeleton ───────────────────────────────────────
def test_default_metrics_returns_none_for_empty_context(contract_instance):
    """空 context 返回 None (未实现场景)"""
    assert contract_instance.default_metrics({}) is None


def test_default_metrics_returns_none_for_none_context(contract_instance):
    """None context 返回 None"""
    assert contract_instance.default_metrics(None) is None  # type: ignore[arg-type]
