"""v1.33.0 — train.py 双路径 dispatcher 单测(metrics_shape 双形态覆盖)。

策略: 不真起 train.py 训练,monkey-patch contract + ws 即可。
覆盖:
  - 老字符串 "supervised"/"adapter"/"mammoth_cl" 走 MetricsShape.from_legacy() 归一(expand 阶段)
  - 新 enum 字面值 MetricsShape.EVALUATE_LEARNER/EVALUATE_RUNNER 直接走主路径
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PKG = ROOT / "template" / "package"
SCRIPTS = TEMPLATE_PKG / "scripts"


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


# ── EVALUATE_LEARNER 路径(enum 字面值,新代码主形态) ──────────────
def test_evaluate_learner_enum_calls_contract_test_with_learner(import_paths):
    from scripts.lib.train_branch import dispatch_test_call
    from scripts.lib.train_branch_types import MetricsShape

    contract = MagicMock()
    ws = MagicMock()
    ws.get = MagicMock(return_value=None)
    learner = object()

    metrics = dispatch_test_call(
        contract=contract, learner=learner, ws=ws,
        metrics_shape=MetricsShape.EVALUATE_LEARNER,
        shared_context={"k": "v"}, adapter_runner=None,
    )

    contract.test.assert_called_once_with(learner, ws, shared_context={"k": "v"})
    assert ws.get.call_count == 0


def test_evaluate_learner_via_cfg_default_does_not_read_adapter_runner(import_paths):
    from scripts.lib.train_branch import dispatch_test_call
    from scripts.lib.train_branch_types import MetricsShape

    contract = MagicMock()
    ws = MagicMock()
    learner = object()
    fake_runner = MagicMock(return_value={"val_accuracy": 0.93})
    ws.get = MagicMock(return_value=fake_runner)

    dispatch_test_call(
        contract=contract, learner=learner, ws=ws,
        metrics_shape=MetricsShape.EVALUATE_LEARNER,
        shared_context={}, adapter_runner=None,
    )

    contract.test.assert_called_once_with(learner, ws, shared_context={})
    ws.get.assert_not_called()


# ── EVALUATE_RUNNER 路径 ────────────────────────────────────────
def test_evaluate_runner_enum_calls_test_with_learner_none_and_runner(import_paths):
    from scripts.lib.train_branch import dispatch_test_call
    from scripts.lib.train_branch_types import MetricsShape

    contract = MagicMock()
    ws = MagicMock()
    fake_runner = MagicMock(return_value={"val_accuracy": 43.46})

    metrics = dispatch_test_call(
        contract=contract, learner=None, ws=ws,
        metrics_shape=MetricsShape.EVALUATE_RUNNER,
        shared_context={"k": "v"}, adapter_runner=fake_runner,
    )

    contract.test.assert_called_once_with(
        None, ws, shared_context={"k": "v"}, adapter_runner=fake_runner
    )


def test_evaluate_runner_without_runner_raises_value_error(import_paths):
    from scripts.lib.train_branch import dispatch_test_call
    from scripts.lib.train_branch_types import MetricsShape

    contract = MagicMock()
    ws = MagicMock()

    with pytest.raises(ValueError, match="adapter_runner"):
        dispatch_test_call(
            contract=contract, learner=None, ws=ws,
            metrics_shape=MetricsShape.EVALUATE_RUNNER,
            shared_context={}, adapter_runner=None,
        )


# ── legacy 字符串 → from_legacy 兼容(expand 阶段保留) ──────────────
def test_legacy_supervised_string_still_works_with_warning(import_paths):
    """老 "supervised" 字符串 → from_legacy 归一 → EVALUATE_LEARNER。"""
    from scripts.lib.train_branch import dispatch_test_call

    contract = MagicMock()
    ws = MagicMock()
    learner = object()

    with pytest.warns(DeprecationWarning, match="supervised"):
        dispatch_test_call(
            contract=contract, learner=learner, ws=ws,
            metrics_shape="supervised",
            shared_context={}, adapter_runner=None,
        )

    contract.test.assert_called_once_with(learner, ws, shared_context={})


def test_legacy_adapter_string_still_works_with_warning(import_paths):
    from scripts.lib.train_branch import dispatch_test_call

    contract = MagicMock()
    ws = MagicMock()
    fake_runner = MagicMock(return_value={"x": 1.0})

    with pytest.warns(DeprecationWarning, match="adapter"):
        dispatch_test_call(
            contract=contract, learner=None, ws=ws,
            metrics_shape="adapter",
            shared_context={}, adapter_runner=fake_runner,
        )

    contract.test.assert_called_once_with(
        None, ws, shared_context={}, adapter_runner=fake_runner,
    )


def test_legacy_mammoth_cl_string_maps_to_evaluate_learner(import_paths):
    """业务仓 mammoth_cl 字符串 → from_legacy → EVALUATE_LEARNER;framework_kind 另由 workspace 声明。"""
    from scripts.lib.train_branch import dispatch_test_call

    contract = MagicMock()
    ws = MagicMock()
    learner = object()

    with pytest.warns(DeprecationWarning, match="mammoth_cl"):
        dispatch_test_call(
            contract=contract, learner=learner, ws=ws,
            metrics_shape="mammoth_cl",
            shared_context={}, adapter_runner=None,
        )

    contract.test.assert_called_once_with(learner, ws, shared_context={})


def test_legacy_unknown_string_raises_value_error(import_paths):
    from scripts.lib.train_branch import dispatch_test_call

    contract = MagicMock()
    ws = MagicMock()
    learner = object()

    with pytest.raises(ValueError, match="hybrid"):
        dispatch_test_call(
            contract=contract, learner=learner, ws=ws,
            metrics_shape="hybrid",
            shared_context={}, adapter_runner=None,
        )


# ── dispatch_training(维度 A — 训练调度分流,对照 dispatch_test_call)─────
def test_dispatch_training_native_calls_run_native(import_paths):
    from scripts.lib.train_branch import dispatch_training
    from scripts.lib.train_branch_types import TrainingMech

    sentinel = {
        "ran": False,
        "ret": {
            "best_state": None,
            "best_metrics": {},
            "best_epoch": 0,
            "last_completed_epoch": 3,
        },
    }

    def run_native():
        sentinel["ran"] = True
        return sentinel["ret"]

    result = dispatch_training(training_mech=TrainingMech.NATIVE, run_native=run_native)
    assert sentinel["ran"] is True
    assert result["last_completed_epoch"] == 3
    assert result["stop_reason"] == "mech_complete"


def test_dispatch_training_normalizes_string_member_name_and_value(import_paths):
    """YAML cfg workspace.training_mech 产出 str;成员名与值都归一为 NATIVE 并触发 run_native
    (对照 dispatch_test_call 的 MetricsShape.from_legacy 字符串归一)。"""
    from scripts.lib.train_branch import dispatch_training

    for mech_str in ("NATIVE", "native"):  # 成员名 / 值
        state = {"ran": False}

        def run_native():
            state["ran"] = True
            return {
                "best_state": None,
                "best_metrics": {},
                "best_epoch": 0,
                "last_completed_epoch": 0,
            }

        result = dispatch_training(training_mech=mech_str, run_native=run_native)
        assert state["ran"] is True, f"{mech_str!r} 未触发 run_native"
        assert result["best_state"] is None
        assert result["stop_reason"] == "mech_complete"


@pytest.mark.parametrize(
    "mech_str,match",
    [
        ("IN_PROCESS", "IN_PROCESS"),
        ("in_process", "IN_PROCESS"),
        ("SUBPROCESS", "SUBPROCESS"),
        ("subprocess", "SUBPROCESS"),
    ],
)
def test_dispatch_training_string_deferred_mechs_raise_not_implemented(import_paths, mech_str, match):
    """字符串形态的 ③④ 归一后，未注入对应 callable 时 NotImplementedError，
    而非落到 ValueError「不支持」——这是本块字符串归一的要点。"""
    from scripts.lib.train_branch import dispatch_training

    with pytest.raises(NotImplementedError, match=match):
        dispatch_training(training_mech=mech_str, run_native=lambda: None)


def test_dispatch_training_in_process_raises_not_implemented(import_paths):
    from scripts.lib.train_branch import dispatch_training
    from scripts.lib.train_branch_types import TrainingMech

    with pytest.raises(NotImplementedError, match="IN_PROCESS"):
        dispatch_training(training_mech=TrainingMech.IN_PROCESS, run_native=lambda: None)


def test_dispatch_training_subprocess_raises_not_implemented(import_paths):
    from scripts.lib.train_branch import dispatch_training
    from scripts.lib.train_branch_types import TrainingMech

    with pytest.raises(NotImplementedError, match="SUBPROCESS"):
        dispatch_training(training_mech=TrainingMech.SUBPROCESS, run_native=lambda: None)


def test_dispatch_training_in_process_calls_injected(import_paths):
    from scripts.lib.train_branch import dispatch_training
    from scripts.lib.train_branch_types import TrainingMech

    sentinel = {"ran": False}

    def run_in_process():
        sentinel["ran"] = True
        return {
            "best_state": None,
            "best_metrics": {"acc": 0.9},
            "best_epoch": 1,
            "last_completed_epoch": 1,
        }

    result = dispatch_training(
        training_mech=TrainingMech.IN_PROCESS,
        run_native=lambda: (_ for _ in ()).throw(AssertionError("must not call native")),
        run_in_process=run_in_process,
    )
    assert sentinel["ran"] is True
    assert result["best_metrics"]["acc"] == 0.9
    assert result["stop_reason"] == "mech_complete"


def test_dispatch_training_subprocess_calls_injected(import_paths):
    from scripts.lib.train_branch import dispatch_training
    from scripts.lib.train_branch_types import TrainingMech

    def run_subprocess():
        return {
            "best_state": None,
            "best_metrics": {"acc": 0.8},
            "best_epoch": 2,
            "last_completed_epoch": 2,
        }

    result = dispatch_training(
        training_mech=TrainingMech.SUBPROCESS,
        run_native=lambda: (_ for _ in ()).throw(AssertionError("must not call native")),
        run_subprocess=run_subprocess,
    )
    assert result["best_epoch"] == 2
    assert result["stop_reason"] == "mech_complete"


def test_run_subprocess_training_reads_json(import_paths, tmp_path):
    import sys

    from scripts.lib.train_branch import run_subprocess_training

    result_path = tmp_path / "out.json"
    payload = {
        "best_metrics": {"val_accuracy": 0.91},
        "best_epoch": 3,
        "last_completed_epoch": 5,
    }
    cmd = [
        sys.executable,
        "-c",
        f"import json,pathlib; pathlib.Path({str(result_path)!r}).write_text("
        f"json.dumps({payload!r}), encoding='utf-8')",
    ]
    out = run_subprocess_training(cmd=cmd, result_path=result_path, cwd=tmp_path)
    assert out["best_metrics"]["val_accuracy"] == 0.91
    assert out["best_epoch"] == 3
    assert out["last_completed_epoch"] == 5
    assert out["best_state"] is None


def test_invoke_framework_train_and_resolve_subprocess(import_paths, tmp_path):
    from scripts.lib.train_branch import (
        invoke_framework_train,
        resolve_subprocess_cmd_and_result,
        run_subprocess_training,
    )

    class FakeWs:
        def framework_train(self, **kwargs):
            assert "learner" in kwargs
            return {
                "best_state": None,
                "best_metrics": {"m": 1.0},
                "best_epoch": 0,
                "last_completed_epoch": 0,
            }

        def framework_subprocess_cmd(self, exp_dir):
            import sys

            p = exp_dir / "r.json"
            return [
                sys.executable,
                "-c",
                "import json,pathlib; pathlib.Path(%r).write_text("
                "json.dumps({'best_metrics': {'m': 0.5}}), encoding='utf-8')"
                % (str(p),),
            ]

        framework_result_path = "r.json"

    ws = FakeWs()
    got = invoke_framework_train(ws, learner=object())
    assert got["best_metrics"]["m"] == 1.0

    cmd, result_path = resolve_subprocess_cmd_and_result(ws, tmp_path)
    assert result_path == tmp_path / "r.json"
    out = run_subprocess_training(cmd=cmd, result_path=result_path, cwd=tmp_path)
    assert out["best_metrics"]["m"] == 0.5


def test_dispatch_training_bad_mech_raises_value_error(import_paths):
    from scripts.lib.train_branch import dispatch_training

    with pytest.raises(ValueError, match="不支持"):
        dispatch_training(training_mech="bogus", run_native=lambda: None)
