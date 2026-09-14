# template/package/scripts/tests/test_audit_core.py
import json
from pathlib import Path

import pytest

from lib.audit_core import (
    ablation_config,
    ablation_drop_exceeds,
    extra_seeds,
    pick_target,
    pooled_std,
    repro_tolerance,
    resolve_fingerprint_baseline,
)


def test_extra_seeds_include_original():
    assert extra_seeds(42, 5) == [42, 43, 44, 45, 46]
    assert extra_seeds(2**32 - 1, 2) == [2**32 - 1, 0]


def test_repro_tolerance_near_best_wins():
    assert repro_tolerance(0.5, 0.01) == 0.01
    assert repro_tolerance(0.5, 0.0) == max(0.5 * 0.01, 1e-4)


def test_ablation_config_only_named_keys():
    full = {"LOSS": "poly", "LR": 0.1, "SEED": 1}
    base = {"LOSS": "ce", "LR": 0.1, "SEED": 1}
    out = ablation_config(full, base, ["LOSS"])
    assert out["LOSS"] == "ce"
    assert out["LR"] == 0.1
    assert out["SEED"] == 1


def test_pooled_std_and_drop_gate():
    sp = pooled_std(0.01, 5, 0.01, 5)
    assert abs(sp - 0.01) < 1e-9
    assert ablation_drop_exceeds(0.50, 0.01, 5, 0.40, 0.01, 5, "maximize") is True
    assert ablation_drop_exceeds(0.50, 0.01, 5, 0.495, 0.01, 5, "maximize") is False
    assert ablation_drop_exceeds(0.5, 0.0, 1, 0.4, 0.0, 1, "maximize") is None


def test_pick_target_from_keepers(tmp_path: Path):
    exp = tmp_path / "_runs" / "exp" / "best"
    exp.mkdir(parents=True)
    (exp / "config.json").write_text(json.dumps({"SEED": 7, "LOSS": "ce"}), encoding="utf-8")
    (exp / "results.json").write_text(
        json.dumps({"primary_metric": {"test_acc": 0.9}}), encoding="utf-8",
    )
    saved = tmp_path / "saved"
    saved.mkdir()
    (saved / "keepers.json").write_text(
        json.dumps({"seq": {"scenario_id": "seq", "keeper_exp_dir": "_runs/exp/best"}}),
        encoding="utf-8",
    )
    (tmp_path / "nn-config.yaml").write_text(
        "agent:\n  scenario_default: seq\nkeep:\n  near_best_abs: 0\n",
        encoding="utf-8",
    )
    t = pick_target(tmp_path)
    assert t.scenario_id == "seq"
    assert t.original_seed == 7
    assert t.audited_exp_dir.endswith("best")
    assert t.original_primary == 0.9


def test_pick_target_reads_metrics_sgcs(tmp_path: Path):
    """CSI 成绩文件只有 metrics.sgcs，没有 primary_metric。"""
    exp = tmp_path / "_runs" / "exp" / "best"
    exp.mkdir(parents=True)
    (exp / "config.json").write_text(json.dumps({"SEED": 42}), encoding="utf-8")
    (exp / "results.json").write_text(
        json.dumps({"metrics": {"cos_sim_mean": 0.1, "sgcs": 0.49448}}),
        encoding="utf-8",
    )
    saved = tmp_path / "saved"
    saved.mkdir()
    (saved / "keepers.json").write_text(
        json.dumps({"seq": {"scenario_id": "seq", "keeper_exp_dir": "_runs/exp/best"}}),
        encoding="utf-8",
    )
    (tmp_path / "nn-config.yaml").write_text(
        "agent:\n  scenario_default: seq\ngoal:\n  metric: sgcs\n",
        encoding="utf-8",
    )
    (tmp_path / "contract").mkdir()
    (tmp_path / "contract" / "__init__.py").write_text("", encoding="utf-8")
    t = pick_target(tmp_path)
    assert t.original_primary == 0.49448


def _keeper_repo(tmp_path: Path, *, write_results: bool, results_payload=None) -> None:
    exp = tmp_path / "_runs" / "exp" / "best"
    exp.mkdir(parents=True)
    (exp / "config.json").write_text(json.dumps({"SEED": 7, "LOSS": "ce"}), encoding="utf-8")
    if write_results:
        payload = {} if results_payload is None else results_payload
        (exp / "results.json").write_text(json.dumps(payload), encoding="utf-8")
    saved = tmp_path / "saved"
    saved.mkdir()
    (saved / "keepers.json").write_text(
        json.dumps({"seq": {"scenario_id": "seq", "keeper_exp_dir": "_runs/exp/best"}}),
        encoding="utf-8",
    )
    (tmp_path / "nn-config.yaml").write_text(
        "agent:\n  scenario_default: seq\nkeep:\n  near_best_abs: 0\n",
        encoding="utf-8",
    )


def test_pick_target_missing_results_json_raises(tmp_path: Path):
    _keeper_repo(tmp_path, write_results=False)
    with pytest.raises(FileNotFoundError, match="results.json"):
        pick_target(tmp_path)


def test_pick_target_missing_primary_raises(tmp_path: Path):
    _keeper_repo(tmp_path, write_results=True, results_payload={})
    with pytest.raises(ValueError, match="primary_metric"):
        pick_target(tmp_path)


def test_fingerprint_baseline_prefers_reference(tmp_path: Path):
    for name, tag in (("ref", "reference"), ("pl", "plain")):
        d = tmp_path / "_runs" / "exp" / name
        d.mkdir(parents=True)
        (d / "config.json").write_text(json.dumps({"SEED": 1, "baseline_tag": tag}), encoding="utf-8")
    tsv = tmp_path / "_runs" / "results.tsv"
    tsv.parent.mkdir(parents=True, exist_ok=True)
    tsv.write_text(
        "experiment\tscenario_id\tbaseline_tag\texp_dir\n"
        "a\tseq\treference\t_runs/exp/ref\n"
        "b\tseq\tplain\t_runs/exp/pl\n",
        encoding="utf-8",
    )
    (tmp_path / "nn-config.yaml").write_text("agent:\n  scenario_default: seq\n", encoding="utf-8")
    p, kind = resolve_fingerprint_baseline(tmp_path, "seq")
    assert kind == "reference"
    assert p is not None and p.name == "ref"
