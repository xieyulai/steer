"""#2：finalize_run 只吃 precomputed_official_metrics；无 contract.test / checkpoint 回退。"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiment import ExperimentBase


class _Stub(ExperimentBase):
    @property
    def metric_keys(self) -> dict[str, str]:
        return {"primary": "acc"}

    def report_train_artifacts(self, *args, **kwargs):
        return {}

    def save_checkpoint(self, *args, **kwargs):
        return None


@pytest.fixture()
def _skip_env(monkeypatch):
    monkeypatch.setenv("NN_SKIP_POST_EVAL", "1")
    monkeypatch.setenv("NN_SNAPSHOT_CODE", "0")


def test_finalize_run_requires_precomputed(tmp_path, _skip_env):
    inst = _Stub.__new__(_Stub)
    exp_dir = tmp_path / "e"
    exp_dir.mkdir()
    with pytest.raises(ValueError, match="precomputed_official_metrics"):
        inst.finalize_run(
            repo_root=tmp_path,
            cfg={},
            timer=types.SimpleNamespace(elapsed=0.0),
            best_state=None,
            exp_dir=exp_dir,
            experiment="t",
            precomputed_official_metrics=None,
        )


def test_finalize_run_uses_precomputed_without_contract_test(tmp_path, _skip_env):
    inst = _Stub.__new__(_Stub)
    exp_dir = tmp_path / "e"
    exp_dir.mkdir()
    metrics = {"acc": 0.42}
    contract = MagicMock()
    with patch.object(inst, "report_train_artifacts") as report:
        inst.finalize_run(
            repo_root=tmp_path,
            cfg={},
            timer=types.SimpleNamespace(elapsed=0.0),
            best_state=None,
            exp_dir=exp_dir,
            experiment="t",
            contract=contract,
            ws=MagicMock(),
            learner=MagicMock(),
            shared_context={},
            precomputed_official_metrics=metrics,
        )
    contract.test.assert_not_called()
    assert report.call_args.args[0] == metrics


def test_finalize_run_does_not_apply_checkpoint(tmp_path, _skip_env):
    inst = _Stub.__new__(_Stub)
    exp_dir = tmp_path / "e"
    exp_dir.mkdir()
    with patch(
        "experiment.apply_checkpoint_policy_to_learner",
        autospec=True,
    ) as ckpt:
        inst.finalize_run(
            repo_root=tmp_path,
            cfg={},
            timer=types.SimpleNamespace(elapsed=0.0),
            best_state={"w": 1},
            exp_dir=exp_dir,
            experiment="t",
            contract=MagicMock(),
            ws=MagicMock(),
            learner=MagicMock(),
            shared_context={},
            precomputed_official_metrics={"acc": 1.0},
        )
    ckpt.assert_not_called()
