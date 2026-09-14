"""训后收尾 + 训练结果归一（三种 TrainingMech 共用）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
TEMPLATE_PKG = SCRIPTS.parent


@pytest.fixture
def import_paths():
    paths = [str(TEMPLATE_PKG), str(SCRIPTS)]
    for p in paths:
        if p not in sys.path:
            sys.path.insert(0, p)
    yield
    for p in paths:
        if p in sys.path:
            sys.path.remove(p)


def _full_result(**overrides):
    base = {
        "best_state": None,
        "best_metrics": {},
        "best_epoch": 0,
        "last_completed_epoch": 0,
    }
    base.update(overrides)
    return base


def test_normalize_requires_four_keys(import_paths):
    from scripts.lib.train_branch import normalize_training_result

    with pytest.raises(ValueError, match="缺键"):
        normalize_training_result({"best_state": None})


def test_normalize_defaults_stop_reason(import_paths):
    from scripts.lib.train_branch import normalize_training_result

    out = normalize_training_result(_full_result(last_completed_epoch=2))
    assert out["stop_reason"] == "mech_complete"
    assert out["last_completed_epoch"] == 2


def test_normalize_keeps_explicit_stop_reason(import_paths):
    from scripts.lib.train_branch import normalize_training_result

    out = normalize_training_result(
        _full_result(stop_reason="early_stop_patience", best_epoch=3)
    )
    assert out["stop_reason"] == "early_stop_patience"
    assert out["best_epoch"] == 3


def test_normalize_rejects_non_dict_metrics(import_paths):
    from scripts.lib.train_branch import normalize_training_result

    with pytest.raises(ValueError, match="best_metrics"):
        normalize_training_result(_full_result(best_metrics="nope"))


def test_finalize_writes_train_done_and_calls_checkpoint(import_paths, tmp_path):
    from scripts.lib.train_branch import finalize_training_loop_artifacts

    learner = object()
    result = _full_result(
        best_epoch=2,
        last_completed_epoch=3,
        stop_reason="mech_complete",
    )
    with patch(
        "experiment.apply_checkpoint_policy_to_learner",
        autospec=True,
    ) as ckpt:
        payload = finalize_training_loop_artifacts(
            exp_dir=tmp_path,
            learner=learner,
            repo_root=tmp_path,
            cfg={},
            epochs_configured=10,
            result=result,
        )
    done = json.loads((tmp_path / "train_done.json").read_text(encoding="utf-8"))
    assert done["training_loop_finished"] is True
    assert done["last_completed_epoch"] == 3
    assert done["best_epoch"] == 2
    assert done["stop_reason"] == "mech_complete"
    assert payload["stop_reason"] == "mech_complete"
    ckpt.assert_called_once()
    assert ckpt.call_args.args[0] is learner
    assert ckpt.call_args.kwargs["best_state"] is None


def test_dispatch_then_finalize_in_process_defaults_stop_reason(import_paths, tmp_path):
    """接线：IN_PROCESS 无 stop_reason → 出口默认 mech_complete；finalize 写入同一值。"""
    from scripts.lib.train_branch import dispatch_training, finalize_training_loop_artifacts
    from scripts.lib.train_branch_types import TrainingMech

    def run_native():
        raise AssertionError("must not call native")

    def run_in_process():
        return {
            "best_state": {"w": 1},
            "best_metrics": {"acc": 0.5},
            "best_epoch": 1,
            "last_completed_epoch": 1,
        }

    result = dispatch_training(
        training_mech=TrainingMech.IN_PROCESS,
        run_native=run_native,
        run_in_process=run_in_process,
    )
    assert result["stop_reason"] == "mech_complete"
    with patch("experiment.apply_checkpoint_policy_to_learner") as ckpt:
        finalize_training_loop_artifacts(
            exp_dir=tmp_path,
            learner=MagicMock(),
            repo_root=tmp_path,
            cfg={},
            epochs_configured=5,
            result=result,
        )
    done = json.loads((tmp_path / "train_done.json").read_text(encoding="utf-8"))
    assert done["stop_reason"] == "mech_complete"
    ckpt.assert_called_once()
    assert len(list(tmp_path.glob("train_done.json"))) == 1


def test_dispatch_native_preserves_stop_reason_into_train_done(import_paths, tmp_path):
    from scripts.lib.train_branch import dispatch_training, finalize_training_loop_artifacts
    from scripts.lib.train_branch_types import TrainingMech

    def run_native():
        return {
            "best_state": None,
            "best_metrics": {},
            "best_epoch": 0,
            "last_completed_epoch": 4,
            "stop_reason": "early_stop_patience",
        }

    result = dispatch_training(
        training_mech=TrainingMech.NATIVE,
        run_native=run_native,
    )
    assert result["stop_reason"] == "early_stop_patience"
    with patch("experiment.apply_checkpoint_policy_to_learner"):
        finalize_training_loop_artifacts(
            exp_dir=tmp_path,
            learner=MagicMock(),
            repo_root=tmp_path,
            cfg={},
            epochs_configured=4,
            result=result,
        )
    done = json.loads((tmp_path / "train_done.json").read_text(encoding="utf-8"))
    assert done["last_completed_epoch"] == 4
    assert done["stop_reason"] == "early_stop_patience"
