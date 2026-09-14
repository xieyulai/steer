"""v1.33.0 — train_branch_types.py 单测(13 case)。"""
from __future__ import annotations

import warnings

import pytest

from scripts.lib.train_branch_types import (
    FrameworkKind,
    MetricsShape,
    TrainingMech,
    WorkspaceKind,
)


# ── MetricsShape enum 边界 ─────────────────────────────────────────
def test_metrics_shape_enum_values():
    assert {m.value for m in MetricsShape} == {"evaluate_learner", "evaluate_runner"}
    assert MetricsShape.EVALUATE_LEARNER.value == "evaluate_learner"
    assert MetricsShape.EVALUATE_RUNNER.value == "evaluate_runner"


def test_metrics_shape_from_legacy_supervised_warns():
    with pytest.warns(DeprecationWarning, match="supervised"):
        result = MetricsShape.from_legacy("supervised")
    assert result is MetricsShape.EVALUATE_LEARNER


def test_metrics_shape_from_legacy_adapter_warns():
    with pytest.warns(DeprecationWarning, match="adapter"):
        result = MetricsShape.from_legacy("adapter")
    assert result is MetricsShape.EVALUATE_RUNNER


def test_metrics_shape_from_legacy_mammoth_cl_warns():
    with pytest.warns(DeprecationWarning, match="mammoth_cl"):
        result = MetricsShape.from_legacy("mammoth_cl")
    assert result is MetricsShape.EVALUATE_LEARNER


def test_metrics_shape_from_legacy_unknown_raises():
    with pytest.raises(ValueError, match="hybrid"):
        MetricsShape.from_legacy("hybrid")


def test_metrics_shape_from_legacy_non_string_raises():
    with pytest.raises(ValueError, match="仅接受 str"):
        MetricsShape.from_legacy(42)  # type: ignore[arg-type]


# ── TrainingMech / FrameworkKind 边界 ──────────────────────────────
def test_training_mech_has_three_values():
    assert {m.value for m in TrainingMech} == {"subprocess", "in_process", "native"}


def test_framework_kind_includes_six_values():
    assert {k.value for k in FrameworkKind} == {
        "mammoth", "lightning", "hf_trainer", "timm", "avalanche", "unknown",
    }


def test_framework_kind_from_module_hint_mammoth():
    assert FrameworkKind.from_module_hint("mammoth_models", None) is FrameworkKind.MAMMOTH
    assert FrameworkKind.from_module_hint(None, "mammoth") is FrameworkKind.MAMMOTH


def test_framework_kind_from_module_hint_lightning_variants():
    assert FrameworkKind.from_module_hint("pytorch_lightning_trainer", None) is FrameworkKind.LIGHTNING
    assert FrameworkKind.from_module_hint("lit_module", "lightning") is FrameworkKind.LIGHTNING


def test_framework_kind_from_module_hint_unknown_returns_unknown():
    assert FrameworkKind.from_module_hint(None, None) is FrameworkKind.UNKNOWN
    assert FrameworkKind.from_module_hint("my_custom_loop", None) is FrameworkKind.UNKNOWN


# ── WorkspaceKind 别名 ──────────────────────────────────────────────
def test_workspace_kind_alias_is_metrics_shape():
    assert WorkspaceKind is MetricsShape


# ── mammoth_cl 业务仓语义 ───────────────────────────────────────────
def test_mammoth_cl_maps_to_evaluate_learner_with_warning():
    """业务仓 mammoth_cl 字面值 → EVALUATE_LEARNER + 标弃用;framework_kind 由业务仓 workspace 显式声明。"""
    with warnings.catch_warnings():
        warnings.simplefilter("always")
        with pytest.warns(DeprecationWarning):
            shape = MetricsShape.from_legacy("mammoth_cl")
    assert shape is MetricsShape.EVALUATE_LEARNER