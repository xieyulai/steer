"""Ticket 02 — 工作区显式 adapter_runner + 注册时戳 __workspace_name__。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PKG = Path(__file__).resolve().parents[2]
_SCRIPTS = _PKG / "scripts"
for _p in (str(_PKG), str(_SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scripts.lib.train_branch_types import MetricsShape
from workspace import (
    Workspace,
    _KIND_REGISTRY,
    _MECH_REGISTRY,
    create_workspace,
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


def test_workspace_has_explicit_adapter_runner_default_none():
    ws = create_workspace({})
    assert hasattr(ws, "adapter_runner")
    assert ws.adapter_runner is None


def test_register_stamps_workspace_name_on_built_instance():
    @register_workspace_kind(MetricsShape.EVALUATE_RUNNER)
    def build_external_cli_workspace(cfg):
        return Workspace()

    ws = build_external_cli_workspace({})
    assert getattr(ws, "__workspace_name__", None) == "build_external_cli_workspace"
    assert get_workspace_kind(ws.__workspace_name__) == MetricsShape.EVALUATE_RUNNER


def test_bare_class_name_workspace_is_not_the_only_runner_hit():
    """注册键是 build 名；裸类名 Workspace 默认仍为评模型。"""
    @register_workspace_kind(MetricsShape.EVALUATE_RUNNER)
    def build_external_cli_workspace(cfg):
        return Workspace()

    build_external_cli_workspace({})
    assert get_workspace_kind("Workspace") == MetricsShape.EVALUATE_LEARNER
    assert get_workspace_kind("build_external_cli_workspace") == MetricsShape.EVALUATE_RUNNER


def test_stamp_failure_raises_not_swallowed():
    """戳名失败必须上抛（no-fallback），不得静默退回类名查表。"""

    class Frozen:
        __slots__ = ()

    @register_workspace_kind(MetricsShape.EVALUATE_RUNNER)
    def build_frozen(_cfg):
        return Frozen()

    with pytest.raises((AttributeError, TypeError)):
        build_frozen({})
