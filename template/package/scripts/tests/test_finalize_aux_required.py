"""finalize_run 强制合同声明的辅指标须有真值（禁假缺）。"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiment import ExperimentBase


class _AuxStub(ExperimentBase):
    @property
    def metric_keys(self) -> dict[str, str]:
        return {"acc": "maximize"}

    @property
    def auxiliary_keys(self) -> dict[str, str]:
        return {"forgetting": "minimize"}

    def report_train_artifacts(self, *args, **kwargs):
        return {}

    def save_checkpoint(self, *args, **kwargs):
        return None


@pytest.fixture()
def _skip_env(monkeypatch):
    monkeypatch.setenv("NN_SKIP_POST_EVAL", "1")
    monkeypatch.setenv("NN_SNAPSHOT_CODE", "0")


def test_finalize_run_missing_aux_raises(tmp_path, _skip_env):
    inst = _AuxStub.__new__(_AuxStub)
    exp_dir = tmp_path / "e"
    exp_dir.mkdir()
    with pytest.raises(ValueError, match="forgetting"):
        inst.finalize_run(
            repo_root=tmp_path,
            cfg={},
            timer=types.SimpleNamespace(elapsed=0.0),
            best_state=None,
            exp_dir=exp_dir,
            experiment="t",
            precomputed_official_metrics={"acc": 0.9},
        )


def test_finalize_run_aux_zero_passes(tmp_path, _skip_env):
    inst = _AuxStub.__new__(_AuxStub)
    exp_dir = tmp_path / "e"
    exp_dir.mkdir()
    metrics = {"acc": 0.9, "forgetting": 0.0}
    with patch.object(inst, "report_train_artifacts") as report:
        inst.finalize_run(
            repo_root=tmp_path,
            cfg={},
            timer=types.SimpleNamespace(elapsed=0.0),
            best_state=None,
            exp_dir=exp_dir,
            experiment="t",
            precomputed_official_metrics=metrics,
        )
    assert report.call_args.args[0] == metrics
