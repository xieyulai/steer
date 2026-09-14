"""finalize_round：多槽每个 exp_dir 各入主台账一行；同 dir 二次 finalize 不双写。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PKG_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PKG_ROOT))
sys.path.insert(0, str(_PKG_ROOT / "scripts"))

from experiment import ExperimentBase  # noqa: E402
from lib.round_ledger_closure import find_unfinalized_multi_slot  # noqa: E402


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


def _mk_slot(repo: Path, name: str, acc: float) -> Path:
    exp = repo / "_runs" / "exp" / name
    exp.mkdir(parents=True)
    (exp / "results.json").write_text(
        json.dumps({"metrics": {"acc": acc}, "elapsed_sec": 1.0}),
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


def test_finalize_round_appends_one_row_per_slot(tmp_path, monkeypatch):
    _setup_repo(tmp_path)
    runs = tmp_path / "_runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "results.tsv").write_text("", encoding="utf-8")
    (runs / "results.jsonl").write_text("", encoding="utf-8")

    d0 = _mk_slot(tmp_path, "20260724_120000_1_s0of3_a", 0.5)
    d1 = _mk_slot(tmp_path, "20260724_120000_1_s1of3_b", 0.9)  # keeper
    d2 = _mk_slot(tmp_path, "20260724_120000_1_s2of3_c", 0.7)

    inst = _Stub.__new__(_Stub)
    _patch_round_side_effects(monkeypatch, inst)
    inst.finalize_round([d0, d1, d2], repo_root=tmp_path)

    jsonl = (runs / "results.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(jsonl) == 3
    names = {Path(json.loads(line)["exp_dir"]).name for line in jsonl}
    assert names == {d0.name, d1.name, d2.name}

    tsv_rows = [
        ln for ln in (runs / "results.tsv").read_text(encoding="utf-8").splitlines()[1:]
        if ln.strip()
    ]
    assert len(tsv_rows) == 3

    assert find_unfinalized_multi_slot(tmp_path) == []


def test_finalize_round_skips_duplicate_exp_dir(tmp_path, monkeypatch, capsys):
    _setup_repo(tmp_path)
    runs = tmp_path / "_runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "results.tsv").write_text("", encoding="utf-8")
    (runs / "results.jsonl").write_text("", encoding="utf-8")

    d0 = _mk_slot(tmp_path, "20260724_120000_1_s0of2_a", 0.4)
    d1 = _mk_slot(tmp_path, "20260724_120000_1_s1of2_b", 0.8)

    inst = _Stub.__new__(_Stub)
    _patch_round_side_effects(monkeypatch, inst)
    inst.finalize_round([d0, d1], repo_root=tmp_path)
    inst.finalize_round([d0, d1], repo_root=tmp_path)

    jsonl = [
        ln
        for ln in (runs / "results.jsonl").read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    assert len(jsonl) == 2
    err = capsys.readouterr().err
    assert "跳过" in err or "已入账" in err or "skip" in err.lower()
