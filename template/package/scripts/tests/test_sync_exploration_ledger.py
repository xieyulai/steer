"""sync_exploration_ledger：探索空间写入 TSV exploration_space。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

PKG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PKG))
sys.path.insert(0, str(PKG / "scripts"))

from sync_exploration_ledger import (  # noqa: E402
    cell_from_fingerprint,
    normalize_depth,
    should_apply_cell_update,
    sync_repo,
)
from experiment import ExperimentBase  # noqa: E402


def test_normalize_depth_aliases():
    assert normalize_depth("extend") == "derived"
    assert normalize_depth("novel") == "novel"
    assert normalize_depth("different") == "different"
    assert normalize_depth("ambiguous") == ""


def test_should_apply_cell_update_default_only_different_to_novel():
    assert should_apply_cell_update("", "C-novel", backfill_all=False) is False
    assert should_apply_cell_update("C-routine", "C-novel", backfill_all=False) is False
    assert should_apply_cell_update("C-different", "C-novel", backfill_all=False) is True
    assert should_apply_cell_update("C-different", "B-novel", backfill_all=False) is False
    assert should_apply_cell_update("C-different", "C-different", backfill_all=False) is False
    assert should_apply_cell_update("", "A-routine", backfill_all=True) is True


def test_cell_prefers_attested_depth_for_novel():
    fp = {"primary_tier": "B", "effective_depth": "different", "depth": "different"}
    assert cell_from_fingerprint(fp) == "B-different"
    assert cell_from_fingerprint(fp, attested_depth="novel") == "B-novel"


def test_cell_from_fingerprint_rejects_tier_e():
    fp = {"primary_tier": "E", "effective_depth": "routine", "depth": "routine"}
    assert cell_from_fingerprint(fp) == ""


def test_ledger_pins_exploration_space(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "nn-config.yaml").write_text(
        yaml.safe_dump({"ledger": {"watchlist": ["LR"]}}),
        encoding="utf-8",
    )

    class C(ExperimentBase):
        @property
        def metric_keys(self):
            return {"acc": "maximize"}

    keys = C().ledger_context_keys
    assert "exploration_space" in keys
    assert "baseline_tag" in keys
    assert "exploration_space" in C()._default_tsv_columns()


def test_class_attr_ledger_keys_still_get_overlay_columns(tmp_path, monkeypatch):
    """Contract 用类属性盖掉 property 时，表头仍须含系统 overlay 列。"""
    monkeypatch.chdir(tmp_path)

    class C(ExperimentBase):
        metric_keys = {"acc": "maximize"}
        ledger_context_keys = ("LR",)  # 类属性覆盖 property

    cols = C()._default_tsv_columns()
    assert "exploration_space" in cols
    assert "untrained" in cols
    assert "baseline_tag" in cols
    assert "LR" in cols


def test_append_tsv_row_upgrades_missing_exploration_space(tmp_path, monkeypatch):
    """旧表头无 exploration_space 时，append 后自动补列且格子有值。"""
    monkeypatch.chdir(tmp_path)
    runs = tmp_path / "_runs"
    runs.mkdir()
    tsv = runs / "results.tsv"
    tsv.write_text(
        "experiment\tscenario_id\tacc\tLR\tbaseline_tag\telapsed_sec\tgit_commit\texp_dir\tdescription\tnotes\ttimestamp\n"
        "old\tdefault\t0.1\t0.01\tnone\t1\tabc\t_runs/exp/old\td\t\t2026-01-01T00:00:00Z\n",
        encoding="utf-8",
    )

    class C(ExperimentBase):
        metric_keys = {"acc": "maximize"}
        ledger_context_keys = ("LR",)

    C().append_tsv_row(
        {"acc": 0.9},
        repo_root=tmp_path,
        experiment="new",
        description="d",
        exp_dir="_runs/exp/new",
        elapsed_sec=2.0,
        ledger_context={
            "LR": 0.02,
            "exploration_space": "C-novel",
            "untrained": "0",
            "baseline_tag": "none",
        },
    )
    lines = tsv.read_text(encoding="utf-8").splitlines()
    header = lines[0].split("\t")
    assert "exploration_space" in header
    assert "untrained" in header
    idx = header.index("exploration_space")
    # 新行格子有值
    assert lines[-1].split("\t")[idx] == "C-novel"
    # 旧行补空格
    assert lines[1].split("\t")[idx] == ""
    uidx = header.index("untrained")
    assert lines[-1].split("\t")[uidx] == "0"
    assert lines[1].split("\t")[uidx] == ""


def test_sync_patches_tsv_and_jsonl(tmp_path):
    runs = tmp_path / "_runs"
    runs.mkdir()
    exp_name = "20260728_000000_1_s0of1_run"
    exp_dir = tmp_path / "_runs" / "exp" / exp_name
    exp_dir.mkdir(parents=True)
    tsv = runs / "results.tsv"
    tsv.write_text(
        "experiment\tscenario_id\tacc\tbaseline_tag\texploration_space\telapsed_sec\tgit_commit\texp_dir\tdescription\tnotes\ttimestamp\n"
        f"{exp_name}\ts1\t0.9\tnone\tC-different\t1\tabc\t{exp_dir}\tdesc\t\t2026-01-01T00:00:00Z\n",
        encoding="utf-8",
    )
    jsonl = runs / "results.jsonl"
    jsonl.write_text(
        json.dumps(
            {
                "experiment": exp_name,
                "exp_dir": str(exp_dir),
                "scenario_id": "s1",
                "acc": 0.9,
                "exploration_space": "C-different",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    saved = tmp_path / "saved"
    saved.mkdir()
    (saved / "innovation_fingerprint.json").write_text(
        json.dumps(
            {
                "primary_tier": "C",
                "effective_depth": "different",
                "depth": "different",
                "candidate_exp_dirs": [str(exp_dir)],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (saved / "innovation_audit.json").write_text(
        json.dumps({"attested_depth": "novel"}, ensure_ascii=False),
        encoding="utf-8",
    )

    stats = sync_repo(tmp_path, backfill_all=False)
    assert stats["tsv"] >= 1
    text = tsv.read_text(encoding="utf-8")
    assert "exploration_space" in text.splitlines()[0]
    assert "C-novel" in text
    jl = json.loads(jsonl.read_text(encoding="utf-8").splitlines()[0])
    assert jl.get("exploration_space") == "C-novel"


def test_default_sync_does_not_fill_empty_cell(tmp_path):
    runs = tmp_path / "_runs"
    runs.mkdir()
    exp_name = "empty_cell_run"
    exp_dir = tmp_path / "_runs" / "exp" / exp_name
    exp_dir.mkdir(parents=True)
    tsv = runs / "results.tsv"
    tsv.write_text(
        "experiment\tscenario_id\tacc\texploration_space\texp_dir\n"
        f"{exp_name}\ts1\t0.9\t\t{exp_dir}\n",
        encoding="utf-8",
    )
    saved = tmp_path / "saved"
    saved.mkdir()
    (saved / "innovation_fingerprint.json").write_text(
        json.dumps(
            {
                "primary_tier": "B",
                "effective_depth": "different",
                "depth": "different",
                "candidate_exp_dirs": [str(exp_dir)],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (saved / "innovation_audit.json").write_text(
        json.dumps({"attested_depth": "novel"}, ensure_ascii=False),
        encoding="utf-8",
    )
    stats = sync_repo(tmp_path, backfill_all=False)
    assert stats["tsv"] == 0
    row = tsv.read_text(encoding="utf-8").splitlines()[1].split("\t")
    # experiment, scenario_id, acc, exploration_space, exp_dir
    assert row[3] == ""


def test_backfill_all_from_history(tmp_path):
    runs = tmp_path / "_runs"
    runs.mkdir()
    exp_name = "hist_run_a"
    exp_dir = tmp_path / "_runs" / "exp" / exp_name
    exp_dir.mkdir(parents=True)
    tsv = runs / "results.tsv"
    tsv.write_text(
        "experiment\tscenario_id\tacc\texp_dir\n"
        f"{exp_name}\ts1\t0.1\t{exp_dir}\n",
        encoding="utf-8",
    )
    saved = tmp_path / "saved"
    saved.mkdir()
    (saved / "fingerprint_history.jsonl").write_text(
        json.dumps(
            {
                "primary_tier": "A",
                "effective_depth": "routine",
                "depth": "routine",
                "candidate_exp_dirs": [str(exp_dir)],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    stats = sync_repo(tmp_path, backfill_all=True)
    assert stats["tsv"] >= 1
    assert "A-routine" in tsv.read_text(encoding="utf-8")
