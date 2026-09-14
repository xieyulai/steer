"""立尺：唯一性、换尺 destamp、中点挑行。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.baseline_stamp import (
    pick_midpoint_reference,
    stamp_tag,
    tagged_rows,
)


def _exp(root: Path, name: str, cfg: dict, primary: float) -> Path:
    d = root / "_runs" / "exp" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    (d / "results.json").write_text(
        json.dumps({"primary_metric": {"test_acc": primary}, "metrics": {"test_acc": primary}}),
        encoding="utf-8",
    )
    return d


def _ledger(root: Path, rows: list[tuple[str, str, str, str, str]]) -> None:
    """rows: experiment, scenario, tag, exp_dir, test_acc"""
    runs = root / "_runs"
    runs.mkdir(parents=True, exist_ok=True)
    lines = ["experiment\tscenario_id\tbaseline_tag\texp_dir\ttest_acc"]
    for r in rows:
        lines.append("\t".join(r))
    (runs / "results.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _keepers(root: Path, sid: str, exp_dir: str) -> None:
    saved = root / "saved"
    saved.mkdir(exist_ok=True)
    (saved / "keepers.json").write_text(
        json.dumps({sid: {"scenario_id": sid, "keeper_exp_dir": exp_dir}}),
        encoding="utf-8",
    )


def test_second_plain_without_replace_rejected(tmp_path: Path):
    p1 = _exp(tmp_path, "p1", {"SEED": 1, "SCENARIO_ID": "seq"}, 0.3)
    p2 = _exp(tmp_path, "p2", {"SEED": 2, "SCENARIO_ID": "seq"}, 0.31)
    _ledger(
        tmp_path,
        [
            ("p1", "seq", "plain", "_runs/exp/p1", "0.3"),
            ("p2", "seq", "none", "_runs/exp/p2", "0.31"),
        ],
    )
    with pytest.raises(ValueError, match="已有"):
        stamp_tag(tmp_path, exp_dir=str(p2), tag="plain")


def test_replace_destamps_old_row(tmp_path: Path):
    p1 = _exp(tmp_path, "p1", {"SEED": 1, "SCENARIO_ID": "seq", "baseline_tag": "plain"}, 0.3)
    p2 = _exp(tmp_path, "p2", {"SEED": 2, "SCENARIO_ID": "seq", "baseline_tag": "none"}, 0.31)
    _ledger(
        tmp_path,
        [
            ("p1", "seq", "plain", "_runs/exp/p1", "0.3"),
            ("p2", "seq", "none", "_runs/exp/p2", "0.31"),
        ],
    )
    out = stamp_tag(tmp_path, exp_dir=str(p2), tag="plain", replace=True)
    assert out["ok"] is True
    assert tagged_rows(tmp_path, "seq", "plain")[0]["exp_dir"].endswith("p2")
    cfg1 = json.loads((p1 / "config.json").read_text(encoding="utf-8"))
    cfg2 = json.loads((p2 / "config.json").read_text(encoding="utf-8"))
    assert cfg1["baseline_tag"] == "none"
    assert cfg2["baseline_tag"] == "plain"
    tsv = (tmp_path / "_runs" / "results.tsv").read_text(encoding="utf-8")
    assert tsv.count("plain") == 1


def test_midpoint_excludes_keeper_and_plain(tmp_path: Path):
    _exp(tmp_path, "plain", {"SEED": 1, "SCENARIO_ID": "seq"}, 0.2)
    _exp(tmp_path, "mid", {"SEED": 2, "SCENARIO_ID": "seq"}, 0.5)
    _exp(tmp_path, "keep", {"SEED": 3, "SCENARIO_ID": "seq"}, 0.8)
    _ledger(
        tmp_path,
        [
            ("plain", "seq", "plain", "_runs/exp/plain", "0.2"),
            ("mid", "seq", "none", "_runs/exp/mid", "0.5"),
            ("keep", "seq", "none", "_runs/exp/keep", "0.8"),
        ],
    )
    _keepers(tmp_path, "seq", "_runs/exp/keep")
    picked = pick_midpoint_reference(tmp_path, "seq", metric_key_name="test_acc", direction="maximize")
    assert picked["exp_dir"].endswith("mid")
    assert picked["target"] == pytest.approx(0.5)


def test_midpoint_rejects_without_plain(tmp_path: Path):
    _exp(tmp_path, "a", {"SEED": 1, "SCENARIO_ID": "seq"}, 0.4)
    _ledger(tmp_path, [("a", "seq", "none", "_runs/exp/a", "0.4")])
    _keepers(tmp_path, "seq", "_runs/exp/a")
    with pytest.raises(ValueError, match="朴素下界"):
        pick_midpoint_reference(tmp_path, "seq", metric_key_name="test_acc")


def test_cannot_stamp_keeper_as_reference(tmp_path: Path):
    k = _exp(tmp_path, "keep", {"SEED": 1, "SCENARIO_ID": "seq"}, 0.9)
    _exp(tmp_path, "plain", {"SEED": 1, "SCENARIO_ID": "seq"}, 0.2)
    _ledger(
        tmp_path,
        [
            ("plain", "seq", "plain", "_runs/exp/plain", "0.2"),
            ("keep", "seq", "none", "_runs/exp/keep", "0.9"),
        ],
    )
    _keepers(tmp_path, "seq", "_runs/exp/keep")
    with pytest.raises(ValueError, match="当前最好"):
        stamp_tag(tmp_path, exp_dir=str(k), tag="reference", source="ledger_midpoint")


def _metric_cfg(root: Path) -> None:
    (root / "nn-config.yaml").write_text("goal:\n  metric: test_acc\n", encoding="utf-8")


def _source_repo(root: Path) -> Path:
    src = root / "upstream"
    src.mkdir()
    nn = root / ".auto-nn"
    nn.mkdir(exist_ok=True)
    (nn / "migration-source").write_text(str(src) + "\n", encoding="utf-8")
    return src


def _candidate_not_keeper(root: Path, name: str, primary: float) -> Path:
    """单独放一行当前最好，避免候选被当成自己比自己。"""
    _exp(root, "keep", {"SEED": 9, "SCENARIO_ID": "seq", "baseline_tag": "none"}, 0.99)
    cand = _exp(root, name, {"SEED": 1, "SCENARIO_ID": "seq", "baseline_tag": "none"}, primary)
    _ledger(
        root,
        [
            (name, "seq", "none", f"_runs/exp/{name}", str(primary)),
            ("keep", "seq", "none", "_runs/exp/keep", "0.99"),
        ],
    )
    _keepers(root, "seq", "_runs/exp/keep")
    return cand


def test_literature_stamp_without_calibration_leaves_tsv_untouched(tmp_path: Path):
    _metric_cfg(tmp_path)
    _source_repo(tmp_path)
    cand = _candidate_not_keeper(tmp_path, "dla", 0.878)
    tsv_before = (tmp_path / "_runs" / "results.tsv").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="校准"):
        stamp_tag(tmp_path, exp_dir=str(cand), tag="reference", source="literature")
    tsv_after = (tmp_path / "_runs" / "results.tsv").read_text(encoding="utf-8")
    assert tsv_after == tsv_before
    cfg = json.loads((cand / "config.json").read_text(encoding="utf-8"))
    assert cfg["baseline_tag"] == "none"


def test_literature_stamp_over_tolerance_rejected(tmp_path: Path):
    _metric_cfg(tmp_path)
    _source_repo(tmp_path)
    (tmp_path / "saved").mkdir(exist_ok=True)
    (tmp_path / "saved" / "source_calibration.json").write_text(
        json.dumps({"schema_version": 1, "source_cal_value": 0.95}), encoding="utf-8"
    )
    cand = _candidate_not_keeper(tmp_path, "dla", 0.87)
    with pytest.raises(ValueError, match="容差"):
        stamp_tag(tmp_path, exp_dir=str(cand), tag="reference", source="literature")
    tsv = (tmp_path / "_runs" / "results.tsv").read_text(encoding="utf-8")
    assert "\treference\t" not in tsv
    cfg = json.loads((cand / "config.json").read_text(encoding="utf-8"))
    assert cfg["baseline_tag"] == "none"


def test_literature_stamp_within_tolerance_anchors_port_value(tmp_path: Path):
    _metric_cfg(tmp_path)
    _source_repo(tmp_path)
    (tmp_path / "saved").mkdir(exist_ok=True)
    (tmp_path / "saved" / "source_calibration.json").write_text(
        json.dumps({"schema_version": 1, "source_cal_value": 0.95}), encoding="utf-8"
    )
    cand = _candidate_not_keeper(tmp_path, "dla", 0.948)
    out = stamp_tag(tmp_path, exp_dir=str(cand), tag="reference", source="literature")
    assert out["ok"] is True
    assert out["primary"] == pytest.approx(0.948)
    anchor = json.loads((tmp_path / "saved" / "reference_anchor.json").read_text(encoding="utf-8"))
    assert anchor["reference_anchor_value"] == pytest.approx(0.948)
    assert anchor["source"] == "literature"
    tsv = (tmp_path / "_runs" / "results.tsv").read_text(encoding="utf-8")
    assert "reference" in tsv


def test_midpoint_stamp_does_not_need_calibration(tmp_path: Path):
    _metric_cfg(tmp_path)
    _source_repo(tmp_path)
    cand = _candidate_not_keeper(tmp_path, "mid", 0.5)
    out = stamp_tag(tmp_path, exp_dir=str(cand), tag="reference", source="ledger_midpoint")
    assert out["ok"] is True
    assert tagged_rows(tmp_path, "seq", "reference")[0]["exp_dir"].endswith("mid")
