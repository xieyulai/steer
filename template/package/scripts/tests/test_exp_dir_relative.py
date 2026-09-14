"""v2.7.4: 实验地址相对化 — keepers.json / TSV / jsonl 存相对 repo_root。

回归保证：换机/换用户/cp 到 sandbox 后路径不断链；绝对路径只活在内存。
"""
from __future__ import annotations

import json
from pathlib import Path

import sys
_REPO_ROOT = Path(__file__).resolve().parents[2]  # scripts/tests/ → package 根
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from experiment import ExperimentBase, _to_repo_rel, write_saved_keeper_pointer  # noqa: E402


# ── _to_repo_rel helper ─────────────────────────────────────────────

def test_to_repo_rel_abs_in_repo_becomes_relative(tmp_path):
    p = tmp_path / "_runs" / "exp" / "r1"
    p.mkdir(parents=True)
    assert _to_repo_rel(tmp_path, p) == "_runs/exp/r1"


def test_to_repo_rel_already_relative_idempotent(tmp_path):
    assert _to_repo_rel(tmp_path, "_runs/exp/r1") == "_runs/exp/r1"


def test_to_repo_rel_abs_outside_repo_kept_absolute(tmp_path):
    outside = tmp_path.parent / "other_repo_exp"
    outside.mkdir(exist_ok=True)
    result = _to_repo_rel(tmp_path, outside)
    assert Path(result).is_absolute(), "repo 外的绝对路径应保留(跨 repo 数据)"


def test_to_repo_rel_empty_returns_empty(tmp_path):
    assert _to_repo_rel(tmp_path, "") == ""
    assert _to_repo_rel(tmp_path, None) == ""


def test_to_repo_rel_no_repo_root_keeps_absolute(tmp_path):
    p = tmp_path / "x"
    assert Path(_to_repo_rel(None, p)).is_absolute()


# ── append_tsv_row 写相对 ────────────────────────────────────────────

class _FakeBase:
    metric_key = "val_acc"
    metric_direction = "maximize"
    metric_keys = {"val_acc": "maximize"}  # _build_notes_cell → _known_ledger_metric_keys 需
    auxiliary_keys = {}
    ledger_context_keys: list = []  # append_tsv_row 经 _effective_ledger_context_keys 合并

    def _default_tsv_columns(self):
        return ["experiment", "exp_dir", "val_acc"]

    append_tsv_row = ExperimentBase.append_tsv_row
    _effective_ledger_context_keys = ExperimentBase._effective_ledger_context_keys


def test_append_tsv_row_writes_relative_exp_dir(tmp_path):
    repo = tmp_path
    tsv = repo / "_runs" / "results.tsv"
    tsv.parent.mkdir(parents=True)
    exp_dir_abs = repo / "_runs" / "exp" / "20260730_120000_r1"
    exp_dir_abs.mkdir(parents=True)

    _FakeBase().append_tsv_row(
        repo_root=repo, experiment="r1", description="t",
        exp_dir=str(exp_dir_abs), metrics={"val_acc": 0.9}, elapsed_sec=10.0,
        notes="t",  # 绕过 _build_notes_cell(它需 contract.auxiliary_keys 等一堆属性)
    )

    lines = tsv.read_text(encoding="utf-8").splitlines()
    header = lines[0].split("\t")
    data_row = lines[1].split("\t")
    assert data_row[header.index("exp_dir")] == "_runs/exp/20260730_120000_r1"


# ── append_jsonl_record 写相对 ───────────────────────────────────────

def test_append_jsonl_record_writes_relative_exp_dir(tmp_path):
    repo = tmp_path
    jsonl = repo / "_runs" / "results.jsonl"
    jsonl.parent.mkdir(parents=True)
    exp_dir_abs = repo / "_runs" / "exp" / "r2"
    exp_dir_abs.mkdir(parents=True)
    train_mat = exp_dir_abs / "train.mat"
    train_mat.write_bytes(b"x")

    class _B(_FakeBase):
        append_jsonl_record = ExperimentBase.append_jsonl_record

    _B().append_jsonl_record(
        repo_root=repo, experiment="r2", exp_dir=str(exp_dir_abs),
        metrics={"val_acc": 0.8}, elapsed_sec=5.0, train_mat_path=str(train_mat),
        notes="t",  # 绕过 _build_notes_cell
    )

    rec = json.loads(jsonl.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert rec["exp_dir"] == "_runs/exp/r2", f"jsonl exp_dir 应相对; 实际={rec['exp_dir']!r}"
    assert rec["train_mat_path"] == "_runs/exp/r2/train.mat"


# ── write_saved_keeper_pointer 写相对 ────────────────────────────────

def test_write_saved_keeper_pointer_writes_relative(tmp_path):
    repo = tmp_path
    exp_dir_abs = repo / "_runs" / "exp" / "r3"
    exp_dir_abs.mkdir(parents=True)
    (exp_dir_abs / "best_model.pt").write_bytes(b"x")

    write_saved_keeper_pointer(
        repo_root=repo, scenario_id="scen_a",
        keeper_exp_dir=str(exp_dir_abs), experiment="r3",
    )

    entry = json.loads((repo / "saved" / "keepers.json").read_text(encoding="utf-8"))["scen_a"]
    assert entry["keeper_exp_dir"] == "_runs/exp/r3"
    assert entry["best_model_path"] == "_runs/exp/r3/best_model.pt"


# ── sync_ledger _normalize_exp_dir 方向反转 ──────────────────────────

def test_sync_ledger_normalize_returns_relative(tmp_path):
    from sync_ledger import _normalize_exp_dir
    repo = tmp_path
    abs_in = repo / "_runs" / "exp" / "r4"
    abs_in.mkdir(parents=True)
    assert _normalize_exp_dir(repo, str(abs_in)) == "_runs/exp/r4", "绝对→相对"
    assert _normalize_exp_dir(repo, "_runs/exp/r4") == "_runs/exp/r4", "相对幂等"
    outside = tmp_path.parent / "outside_exp"
    outside.mkdir(exist_ok=True)
    assert Path(_normalize_exp_dir(repo, str(outside))).is_absolute()
