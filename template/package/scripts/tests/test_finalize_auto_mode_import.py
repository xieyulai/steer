"""Task 2: finalize_round 缺 lib.auto_mode 时硬失败，其它 Exception 仍软警告。"""
from __future__ import annotations

import builtins
import json
import sys
from pathlib import Path

import pytest

_PKG_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_PKG_ROOT / "scripts"))

from experiment import ExperimentBase  # noqa: E402


class _FinalizeRoundStub(ExperimentBase):
    @property
    def metric_keys(self) -> dict[str, str]:
        return {"acc": "maximize"}


def _write_exp_dir(repo_root: Path) -> Path:
    exp_dir = repo_root / "_runs" / "exp" / "run1"
    exp_dir.mkdir(parents=True)
    (exp_dir / "results.json").write_text(
        json.dumps({"metrics": {"acc": 0.9}, "elapsed_sec": 1.0, "experiment": "t"}),
        encoding="utf-8",
    )
    runs = repo_root / "_runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "results.tsv").write_text("", encoding="utf-8")
    return exp_dir


def _patch_finalize_heavy(monkeypatch, inst: ExperimentBase) -> None:
    monkeypatch.setenv("NN_APPEND_RESULTS_TSV", "0")
    monkeypatch.setenv("NN_APPEND_RESULTS_JSONL", "0")
    monkeypatch.setattr(
        inst,
        "_build_evaluation_result",
        lambda *args, **kwargs: {"keep_suggestion": False, "reason": "test"},
    )
    monkeypatch.setattr(inst, "_append_repo_ledger_row", lambda *args, **kwargs: None)
    import experiment as exp_mod

    monkeypatch.setattr(exp_mod, "_update_wall_hit_streak", lambda *args, **kwargs: None)
    monkeypatch.setattr(exp_mod, "write_repo_round_decision", lambda *args, **kwargs: None)
    monkeypatch.setattr(exp_mod, "clear_train_pid", lambda *args, **kwargs: None)


def test_finalize_round_auto_mode_import_error_raises(tmp_path, monkeypatch):
    """lib.auto_mode 导入失败 → RuntimeError（含 governance-sync 提示）。"""
    exp_dir = _write_exp_dir(tmp_path)
    inst = _FinalizeRoundStub.__new__(_FinalizeRoundStub)
    _patch_finalize_heavy(monkeypatch, inst)

    real_import = builtins.__import__

    def _block_auto_mode(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "lib.auto_mode":
            raise ModuleNotFoundError("No module named 'lib.auto_mode'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _block_auto_mode)

    with pytest.raises(RuntimeError, match=r"auto_mode|governance-sync"):
        inst.finalize_round([exp_dir], repo_root=tmp_path)


def test_finalize_round_paradigm_mismatch_other_exception_soft(tmp_path, monkeypatch, capsys):
    """check_paradigm_mismatch 非 ImportError → 软警告，finalize_round 仍完成。"""
    exp_dir = _write_exp_dir(tmp_path)
    inst = _FinalizeRoundStub.__new__(_FinalizeRoundStub)
    _patch_finalize_heavy(monkeypatch, inst)

    import lib.auto_mode as auto_mode_mod

    def _boom(_root):
        raise ValueError("paradigm probe failed")

    monkeypatch.setattr(auto_mode_mod, "check_paradigm_mismatch", _boom)
    monkeypatch.setattr(auto_mode_mod, "check_and_promote_auto", lambda _root: {})

    inst.finalize_round([exp_dir], repo_root=tmp_path)

    err = capsys.readouterr().err
    assert "paradigm_mismatch" in err
    assert "决策仍 OK" in err


def test_finalize_round_promote_other_exception_soft(tmp_path, monkeypatch, capsys):
    """check_and_promote_auto 非 ImportError → 软警告，finalize_round 仍完成。"""
    exp_dir = _write_exp_dir(tmp_path)
    inst = _FinalizeRoundStub.__new__(_FinalizeRoundStub)
    _patch_finalize_heavy(monkeypatch, inst)

    import lib.auto_mode as auto_mode_mod

    monkeypatch.setattr(auto_mode_mod, "check_paradigm_mismatch", lambda _root: False)

    def _boom(_root):
        raise RuntimeError("promote yaml corrupt")

    monkeypatch.setattr(auto_mode_mod, "check_and_promote_auto", _boom)

    inst.finalize_round([exp_dir], repo_root=tmp_path)

    err = capsys.readouterr().err
    assert "auto promote" in err
    assert "不阻塞决策" in err
