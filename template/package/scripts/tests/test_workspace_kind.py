"""TDD tests for workspace_kind registry (Layer 3 第一半)。

覆盖:register_workspace_kind 装饰器签名/get_workspace_kind 默认 MetricsShape.EVALUATE_LEARNER
/重复注册覆盖语义。
"""
from __future__ import annotations

import pytest

from scripts.lib.train_branch_types import MetricsShape
from workspace import (
    _KIND_REGISTRY,
    get_workspace_kind,
    register_workspace_kind,
)


@pytest.fixture(autouse=True)
def _reset_registry():
    """每个 case 后清空 — 避免污染其他测试。"""
    _KIND_REGISTRY.clear()
    yield
    _KIND_REGISTRY.clear()


# ── register + get 双工(enum 版)────────────────────────────────
def test_register_supervised_then_get_returns_supervised():
    @register_workspace_kind(MetricsShape.EVALUATE_LEARNER)
    def build_my_workspace():
        return "ws"

    assert get_workspace_kind("build_my_workspace") == MetricsShape.EVALUATE_LEARNER


def test_register_adapter_then_get_returns_adapter():
    @register_workspace_kind(MetricsShape.EVALUATE_RUNNER)
    def build_other_workspace():
        return "ws"

    assert get_workspace_kind("build_other_workspace") == MetricsShape.EVALUATE_RUNNER


def test_get_unknown_workspace_defaults_to_evaluate_learner():
    # 未注册的 workspace → 默认 MetricsShape.EVALUATE_LEARNER (向后兼容 v1.23.0)
    assert get_workspace_kind("never_registered_workspace_xyz") == MetricsShape.EVALUATE_LEARNER


def test_register_overrides_existing_kind():
    @register_workspace_kind(MetricsShape.EVALUATE_LEARNER)
    def build_dup():
        return "ws1"

    @register_workspace_kind(MetricsShape.EVALUATE_RUNNER)
    def build_dup():
        return "ws2"

    # 后注册的覆盖前者
    assert get_workspace_kind("build_dup") == MetricsShape.EVALUATE_RUNNER


def test_register_legacy_string_emits_deprecation_warning():
    """v1.33.0 改动:老字符串 ("supervised") 仍接受,但发 DeprecationWarning。"""
    import warnings

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        @register_workspace_kind("supervised")
        def build_legacy_str():
            return "ws"

        assert any(issubclass(x.category, DeprecationWarning) for x in w)
    assert get_workspace_kind("build_legacy_str") == MetricsShape.EVALUATE_LEARNER


def test_register_legacy_string_adapter():
    """"adapter" 老字符串走 from_legacy 归一为 EVALUATE_RUNNER。"""
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)

        @register_workspace_kind("adapter")
        def build_legacy_adapter():
            return "ws"

    assert get_workspace_kind("build_legacy_adapter") == MetricsShape.EVALUATE_RUNNER


def test_get_workspace_kind_is_pure_lookup():
    """get_workspace_kind 不应副作用修改 registry。"""

    @register_workspace_kind(MetricsShape.EVALUATE_LEARNER)
    def build_x():
        return None

    get_workspace_kind("build_x")
    get_workspace_kind("build_x")
    # registry 内仍然只有 build_x
    assert "build_x" in _KIND_REGISTRY


# ── training_mech 注册表(维度 A,对称 metrics_shape)─────────────
from workspace import (
    _MECH_REGISTRY,
    get_training_mech,
)
from scripts.lib.train_branch_types import TrainingMech


@pytest.fixture(autouse=True)
def _reset_mech_registry():
    _MECH_REGISTRY.clear()
    yield
    _MECH_REGISTRY.clear()


def test_get_training_mech_unregistered_defaults_to_native():
    assert get_training_mech("never_registered_xyz") == TrainingMech.NATIVE


def test_register_workspace_kind_records_training_mech_default_native():
    @register_workspace_kind(MetricsShape.EVALUATE_LEARNER)
    def build_ws_a():
        return "ws"

    # 不传 training_mech → 默认 NATIVE
    assert get_training_mech("build_ws_a") == TrainingMech.NATIVE
    assert get_workspace_kind("build_ws_a") == MetricsShape.EVALUATE_LEARNER


def test_register_workspace_kind_accepts_training_mech_kwarg():
    @register_workspace_kind(MetricsShape.EVALUATE_RUNNER, training_mech=TrainingMech.IN_PROCESS)
    def build_lightning():
        return "ws"

    assert get_training_mech("build_lightning") == TrainingMech.IN_PROCESS
    assert get_workspace_kind("build_lightning") == MetricsShape.EVALUATE_RUNNER


def test_get_training_mech_is_pure_lookup():
    @register_workspace_kind(MetricsShape.EVALUATE_LEARNER, training_mech=TrainingMech.SUBPROCESS)
    def build_cli():
        return None

    get_training_mech("build_cli")
    assert "build_cli" in _MECH_REGISTRY
    assert _MECH_REGISTRY["build_cli"] == TrainingMech.SUBPROCESS
