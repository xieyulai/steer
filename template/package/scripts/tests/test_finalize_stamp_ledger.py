"""finalize_round：入账前写入 exploration_space（overlay，不从 cfg 取）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PKG))
sys.path.insert(0, str(PKG / "scripts"))

from experiment import ExperimentBase  # noqa: E402
from lib.exploration_stamp import StampResult  # noqa: E402


class _Stub(ExperimentBase):
    @property
    def metric_keys(self) -> dict[str, str]:
        return {"acc": "maximize"}


def _setup_repo(repo: Path) -> None:
    (repo / "README.md").write_text(
        "## 场景清单\n\n| 场景 ID | 说明 |\n| --- | --- |\n| default | demo |\n",
        encoding="utf-8",
    )
    (repo / "nn-config.yaml").write_text(
        "profile: default\nagent:\n  scenario_default: default\n",
        encoding="utf-8",
    )


def _mk_slot(repo: Path, name: str, *, acc: float = 0.5, elapsed: float = 10.0) -> Path:
    exp = repo / "_runs" / "exp" / name
    exp.mkdir(parents=True)
    (exp / "results.json").write_text(
        json.dumps({"metrics": {"acc": acc}, "elapsed_sec": elapsed}),
        encoding="utf-8",
    )
    (exp / "train_done.json").write_text("{}", encoding="utf-8")
    (exp / "config.json").write_text(
        json.dumps({"LR": 0.1, "baseline_tag": "none", "scenario_id": "default"}),
        encoding="utf-8",
    )
    return exp


def _patch_round_side_effects(monkeypatch, inst: ExperimentBase) -> None:
    monkeypatch.setattr(
        inst,
        "_build_evaluation_result",
        lambda *a, **k: {"keep_suggestion": False, "reason": "test"},
    )
    import experiment as exp_mod

    monkeypatch.setattr(exp_mod, "_update_wall_hit_streak", lambda *a, **k: None)
    monkeypatch.setattr(exp_mod, "clear_train_pid", lambda *a, **k: None)
    import lib.auto_mode as am

    monkeypatch.setattr(am, "check_paradigm_mismatch", lambda _r: False)
    monkeypatch.setattr(am, "check_and_promote_auto", lambda _r: {})


def _tsv_col(tsv_text: str, col: str) -> list[str]:
    lines = [ln for ln in tsv_text.splitlines() if ln.strip()]
    assert lines, "empty tsv"
    hdr = lines[0].split("\t")
    idx = hdr.index(col)
    return [ln.split("\t")[idx] for ln in lines[1:]]


def test_finalize_smoke_writes_empty_exploration_space(tmp_path, monkeypatch):
    _setup_repo(tmp_path)
    runs = tmp_path / "_runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "results.tsv").write_text("", encoding="utf-8")
    (runs / "results.jsonl").write_text("", encoding="utf-8")

    d0 = _mk_slot(tmp_path, "20260829_smoke_s0of1", elapsed=10.0)
    monkeypatch.setenv("NN_SMOKE", "1")

    def _fake_stamp(*_a, **_k):
        return StampResult(cell="", untrained=True, reasons=["untrained"])

    monkeypatch.setattr("lib.exploration_stamp.compute_stamp", _fake_stamp)

    inst = _Stub.__new__(_Stub)
    _patch_round_side_effects(monkeypatch, inst)
    inst.finalize_round([d0], repo_root=tmp_path)

    tsv_text = (runs / "results.tsv").read_text(encoding="utf-8")
    cells = _tsv_col(tsv_text, "exploration_space")
    assert cells == [""]
    # smoke 入账：untrained=1，不 raise
    untrained = _tsv_col(tsv_text, "untrained")
    assert untrained == ["1"]


def test_finalize_trained_writes_untrained_zero(tmp_path, monkeypatch):
    _setup_repo(tmp_path)
    runs = tmp_path / "_runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "results.tsv").write_text("", encoding="utf-8")
    (runs / "results.jsonl").write_text("", encoding="utf-8")

    d0 = _mk_slot(tmp_path, "20260829_train_u0", elapsed=10.0)
    monkeypatch.setenv("NN_SMOKE", "0")

    def _fake_stamp(*_a, **_k):
        return StampResult(cell="A-routine", untrained=False, reasons=["first_in_scenario"])

    monkeypatch.setattr("lib.exploration_stamp.compute_stamp", _fake_stamp)

    inst = _Stub.__new__(_Stub)
    _patch_round_side_effects(monkeypatch, inst)
    inst.finalize_round([d0], repo_root=tmp_path)

    tsv_text = (runs / "results.tsv").read_text(encoding="utf-8")
    assert _tsv_col(tsv_text, "exploration_space") == ["A-routine"]
    assert _tsv_col(tsv_text, "untrained") == ["0"]


def test_finalize_trained_writes_exploration_space_cell(tmp_path, monkeypatch):
    _setup_repo(tmp_path)
    runs = tmp_path / "_runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "results.tsv").write_text("", encoding="utf-8")
    (runs / "results.jsonl").write_text("", encoding="utf-8")

    d0 = _mk_slot(tmp_path, "20260829_train_s0of1", elapsed=10.0)
    monkeypatch.setenv("NN_SMOKE", "0")

    def _fake_stamp(*_a, **_k):
        return StampResult(cell="A-routine", untrained=False, reasons=["first_in_scenario"])

    monkeypatch.setattr("lib.exploration_stamp.compute_stamp", _fake_stamp)

    inst = _Stub.__new__(_Stub)
    _patch_round_side_effects(monkeypatch, inst)
    inst.finalize_round([d0], repo_root=tmp_path)

    cells = _tsv_col((runs / "results.tsv").read_text(encoding="utf-8"), "exploration_space")
    assert cells == ["A-routine"]


def test_finalize_trained_empty_cell_raises(tmp_path, monkeypatch):
    _setup_repo(tmp_path)
    runs = tmp_path / "_runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "results.tsv").write_text("", encoding="utf-8")
    (runs / "results.jsonl").write_text("", encoding="utf-8")

    d0 = _mk_slot(tmp_path, "20260829_empty_s0of1", elapsed=10.0)
    monkeypatch.delenv("NN_SMOKE", raising=False)

    def _fake_stamp(*_a, **_k):
        return StampResult(cell="", untrained=False, reasons=["bad"])

    monkeypatch.setattr("lib.exploration_stamp.compute_stamp", _fake_stamp)

    inst = _Stub.__new__(_Stub)
    _patch_round_side_effects(monkeypatch, inst)
    with pytest.raises(RuntimeError, match="正式训练未写出探索格子"):
        inst.finalize_round([d0], repo_root=tmp_path)
