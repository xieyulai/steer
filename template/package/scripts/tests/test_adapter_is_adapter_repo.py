"""is_evaluate_runner_repo / is_adapter_repo 别名：runner 出分形态判定。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

from lib.adapter_accept import is_adapter_repo, is_evaluate_runner_repo


def _write_cfg(root: Path, metrics_shape: str | None, *, watchlist: list[str] | None = None) -> None:
    data: dict = {"profile": "default", "ledger": {"watchlist": watchlist or ["LR"]}}
    if metrics_shape is not None:
        data["workspace"] = {"metrics_shape": metrics_shape}
    (root / "nn-config.yaml").write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")


def test_metrics_shape_evaluate_runner(tmp_path: Path):
    _write_cfg(tmp_path, "EVALUATE_RUNNER")
    assert is_evaluate_runner_repo(tmp_path) is True
    assert is_adapter_repo(tmp_path) is True  # 兼容别名


def test_metrics_shape_legacy_adapter_string(tmp_path: Path):
    _write_cfg(tmp_path, "adapter")
    assert is_evaluate_runner_repo(tmp_path) is True
    assert is_adapter_repo(tmp_path) is True


def test_metrics_shape_evaluate_learner_not_runner(tmp_path: Path):
    _write_cfg(tmp_path, "EVALUATE_LEARNER")
    assert is_evaluate_runner_repo(tmp_path) is False
    assert is_adapter_repo(tmp_path) is False


def test_no_config_no_workspace_not_runner(tmp_path: Path):
    assert is_evaluate_runner_repo(tmp_path) is False
    assert is_adapter_repo(tmp_path) is False


def test_registry_evaluate_runner_without_yaml_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    scripts_lib = Path(__file__).resolve().parents[1] / "lib"
    (tmp_path / "scripts" / "lib").mkdir(parents=True)
    for name in ("train_branch_types.py", "adapter_accept.py", "nn_config.py", "migrate_goal_schema.py"):
        src = scripts_lib / name
        if src.is_file():
            (tmp_path / "scripts" / "lib" / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "workspace").mkdir()
    (tmp_path / "workspace" / "__init__.py").write_text(
        """
from lib.train_branch_types import MetricsShape

_KIND_REGISTRY = {}
_MECH_REGISTRY = {}

def register_workspace_kind(kind, *, training_mech=None):
    import warnings
    if isinstance(kind, str):
        kind = MetricsShape.from_legacy(kind)
    def _decorator(build_fn):
        _KIND_REGISTRY[build_fn.__name__] = kind
        def _wrapped(*args, **kwargs):
            ws = build_fn(*args, **kwargs)
            if ws is not None and not isinstance(ws, (str, bytes, int, float, bool)):
                setattr(ws, "__workspace_name__", build_fn.__name__)
            return ws
        _wrapped.__name__ = build_fn.__name__
        return _wrapped
    return _decorator

def get_workspace_kind(workspace_name: str) -> MetricsShape:
    return _KIND_REGISTRY.get(workspace_name, MetricsShape.EVALUATE_LEARNER)

@register_workspace_kind(MetricsShape.EVALUATE_RUNNER)
def build_external_cli_workspace(cfg):
    return object()
""",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.syspath_prepend(str(tmp_path / "scripts"))
    saved = {
        name: mod
        for name, mod in list(sys.modules.items())
        if name == "workspace" or name.startswith("workspace.")
    }
    for name in saved:
        sys.modules.pop(name, None)
    try:
        assert is_evaluate_runner_repo(tmp_path) is True
        assert is_adapter_repo(tmp_path) is True
    finally:
        for name in list(sys.modules):
            if name == "workspace" or name.startswith("workspace."):
                sys.modules.pop(name, None)
        sys.modules.update(saved)
