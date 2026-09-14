"""TDD tests for lib/metric_units (Layer 1).

覆盖:UnitKind 类型 / METRIC_UNITS 静态表 / metric_unit 查+fallback+warning /
normalize_to 双向 + None / _safe_metric None+非数。
"""
from __future__ import annotations

import logging
import math

import pytest

from lib.metric_units import (
    METRIC_UNITS,
    UnitKind,
    _safe_metric,
    metric_unit,
    normalize_to,
)


# ── UnitKind / METRIC_UNITS 静态表 ──────────────────────────────────
def test_unitkind_literal():
    # 静态检查:type alias 应是 Literal
    assert metric_unit("val_accuracy") in ("ratio", "percent")
    assert metric_unit("loss") in ("ratio", "percent")


def test_metric_units_table_has_seven_common_metrics():
    assert len(METRIC_UNITS) >= 7
    # percent 类的样例
    assert METRIC_UNITS["val_accuracy"] == "percent"
    assert METRIC_UNITS["f1"] == "percent"
    assert METRIC_UNITS["top1"] == "percent"
    # ratio 类的样例
    assert METRIC_UNITS["loss"] == "ratio"
    assert METRIC_UNITS["perplexity"] == "ratio"
    assert METRIC_UNITS["forgetting"] == "ratio"


# ── metric_unit — 查+fallback+warning ──────────────────────────────
def test_metric_unit_known_returns_table_value():
    assert metric_unit("val_accuracy") == "percent"
    assert metric_unit("loss") == "ratio"


def test_metric_unit_unknown_falls_back_to_ratio(caplog):
    caplog.set_level(logging.WARNING)
    result = metric_unit("never_seen_metric_xyz")
    assert result == "ratio"
    # 警告含 metric 名
    assert any("never_seen_metric_xyz" in r.message for r in caplog.records)


def test_metric_unit_none_returns_ratio():
    assert metric_unit(None) == "ratio"


# ── normalize_to — 跨单位归一 ───────────────────────────────────────
@pytest.mark.parametrize(
    "value,unit,target,expected",
    [
        (0.93, "percent", "ratio", 0.0093),
        (43.46, "percent", "ratio", 0.4346),
        (93.0, "percent", "ratio", 0.93),
        (0.0093, "ratio", "percent", 0.93),
        (0.4346, "ratio", "percent", 43.46),
        (0.93, "ratio", "ratio", 0.93),
        (93.0, "percent", "percent", 93.0),
    ],
)
def test_normalize_to_directions(value, unit, target, expected):
    assert normalize_to(value, unit, target) == pytest.approx(expected)


def test_normalize_to_none_passes_through():
    assert normalize_to(None, "percent", "ratio") is None
    assert normalize_to(None, "ratio", "percent") is None
    # 同单位 None 也透传
    assert normalize_to(None, "ratio", "ratio") is None


def test_normalize_to_unknown_target_raises():
    with pytest.raises(ValueError):
        normalize_to(1.0, "ratio", "wrong_unit")


# ── _safe_metric — None-safe 取值 ──────────────────────────────────
def test_safe_metric_none_returns_default():
    assert _safe_metric(None) == 0.0


def test_safe_metric_none_with_custom_default():
    assert _safe_metric(None, default=0.93) == 0.93


def test_safe_metric_non_numeric_returns_default():
    assert _safe_metric("abc") == 0.0
    assert _safe_metric("abc", default=0.5) == 0.5
    # 非数值若非 str,也是 default
    assert _safe_metric({"k": 1}) == 0.0
    assert _safe_metric([1, 2, 3]) == 0.0


def test_safe_metric_passes_through_numbers():
    assert _safe_metric(0.93) == 0.93
    assert _safe_metric(43.46) == 43.46
    assert _safe_metric(0) == 0.0
    assert _safe_metric(43) == 43.0
    # int 自动转 float
    assert isinstance(_safe_metric(43), float)


def test_safe_metric_filters_nan_and_inf():
    assert _safe_metric(float("nan")) == 0.0
    assert _safe_metric(float("inf")) == 0.0
    assert _safe_metric(float("-inf")) == 0.0


def test_safe_metric_string_number_passes():
    # 业务仓常见 "0.93" 字符串值(TSV string cell)
    assert _safe_metric("0.93") == 0.93
    assert _safe_metric("43.46") == 43.46