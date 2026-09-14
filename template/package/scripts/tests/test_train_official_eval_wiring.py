"""Ticket 03 — 训末双路径：真实 Contract + Workspace 经 dispatch_test_call。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PKG = Path(__file__).resolve().parents[2]
_SCRIPTS = _PKG / "scripts"
for _p in (str(_PKG), str(_SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from contract import Contract
from scripts.lib.train_branch import dispatch_test_call, resolve_official_adapter_runner
from scripts.lib.train_branch_types import MetricsShape
from workspace import (
    Workspace,
    _KIND_REGISTRY,
    _MECH_REGISTRY,
    get_workspace_kind,
    register_workspace_kind,
)


@pytest.fixture(autouse=True)
def _reset_registries():
    _KIND_REGISTRY.clear()
    _MECH_REGISTRY.clear()
    yield
    _KIND_REGISTRY.clear()
    _MECH_REGISTRY.clear()


def test_resolve_evaluate_learner_never_reads_adapter_runner_attr():
    """评模型：即便属性一读就炸，resolve 也不得触碰。"""

    class BoomWS:
        @property
        def adapter_runner(self):
            raise AssertionError("evaluate-learner must not read adapter_runner")

    assert resolve_official_adapter_runner(is_evaluate_runner=False, ws=BoomWS()) is None


def test_resolve_evaluate_runner_reads_explicit_attr():
    ws = Workspace()
    expected = {"val_accuracy": 0.55}
    ws.adapter_runner = lambda: expected
    runner = resolve_official_adapter_runner(is_evaluate_runner=True, ws=ws)
    assert runner is not None
    assert runner() == expected


def test_evaluate_learner_dispatch_with_runner_none():
    contract = Contract()
    ws = Workspace()
    ws.adapter_runner = lambda: {"val_accuracy": 0.99}

    with pytest.raises(NotImplementedError, match="请根据你的项目实现 test"):
        dispatch_test_call(
            contract=contract,
            learner=object(),
            ws=ws,
            metrics_shape=MetricsShape.EVALUATE_LEARNER,
            shared_context={},
            adapter_runner=resolve_official_adapter_runner(
                is_evaluate_runner=False, ws=ws,
            ),
        )


def test_evaluate_runner_with_explicit_attr_returns_metrics():
    contract = Contract()
    expected = {"val_accuracy": 0.55}

    @register_workspace_kind(MetricsShape.EVALUATE_RUNNER)
    def build_external_cli_workspace(cfg):
        w = Workspace()
        w.adapter_runner = lambda: expected
        return w

    ws = build_external_cli_workspace({})
    assert get_workspace_kind(ws.__workspace_name__) is MetricsShape.EVALUATE_RUNNER

    metrics = dispatch_test_call(
        contract=contract,
        learner=None,
        ws=ws,
        metrics_shape=get_workspace_kind(ws.__workspace_name__),
        shared_context={},
        adapter_runner=resolve_official_adapter_runner(
            is_evaluate_runner=True, ws=ws,
        ),
    )
    assert metrics == expected


def test_evaluate_runner_missing_attr_raises_value_error():
    contract = Contract()
    ws = Workspace()
    assert ws.adapter_runner is None

    with pytest.raises(ValueError, match="adapter_runner"):
        dispatch_test_call(
            contract=contract,
            learner=None,
            ws=ws,
            metrics_shape=MetricsShape.EVALUATE_RUNNER,
            shared_context={},
            adapter_runner=resolve_official_adapter_runner(
                is_evaluate_runner=True, ws=ws,
            ),
        )


def test_train_py_uses_resolve_helper_not_dict_get():
    train_src = (_PKG / "train.py").read_text(encoding="utf-8")
    assert 'getattr(ws, "get"' not in train_src
    assert "resolve_official_adapter_runner" in train_src
