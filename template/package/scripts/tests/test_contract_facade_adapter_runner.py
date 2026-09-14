"""Ticket 01 — Contract 门面转发 adapter_runner（真实 Contract 对象）。

Seam: Contract.test（研究合同官方评估入口）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PKG = Path(__file__).resolve().parents[2]
_SCRIPTS = _PKG / "scripts"
for _p in (str(_PKG), str(_SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.fixture
def contract_instance():
    from contract import Contract

    return Contract()


def test_facade_accepts_adapter_runner_and_returns_runner_metrics(contract_instance):
    """评 runner：门面接受 adapter_runner，指标来自 runner（不 TypeError）。"""
    expected = {"val_accuracy": 0.42}

    def runner():
        return expected

    result = contract_instance.test(
        None,
        object(),
        shared_context={},
        adapter_runner=runner,
    )
    assert result == expected


def test_facade_evaluate_learner_without_runner_kw_still_reaches_implementation(
    contract_instance,
):
    """评模型：不传 adapter_runner 时行为与修前一致（骨架 NotImplementedError）。"""
    with pytest.raises(NotImplementedError, match="请根据你的项目实现 test"):
        contract_instance.test(object(), object(), shared_context={})
