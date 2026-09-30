# tests/test_source_probe.py
"""D4.1: source_probe——源对齐题可机读现状静态提取(宁缺毋假)。"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "template" / "package" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import source_probe as SP  # noqa: E402


def test_probe_reads_split_consts_and_metric_keys(tmp_path):
    src = tmp_path / "src"
    (src / "contract").mkdir(parents=True)
    (src / "contract" / "prepare_data.py").write_text(
        "SEED = 42\nTRAIN_RATIO = 0.8\n_EPOCHS = 3\nNOT_ASKED = 'x'\n", encoding="utf-8")
    (src / "contract" / "metrics.py").write_text(
        "METRIC_KEYS = ['nmse', 'sinr']\nAUXILIARY_KEYS = ['loss']\n", encoding="utf-8")
    data = SP.probe(src)
    assert data["D2-data-split"] == {"constants": {"SEED": 42, "TRAIN_RATIO": 0.8}}
    assert data["E1-metrics"] == {"metric_keys": ["nmse", "sinr"], "auxiliary_keys": ["loss"]}
    assert data["I1-train-consumes"] is None


def test_probe_missing_contract_all_null(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    data = SP.probe(src)
    for slug in ("D2-data-split", "E1-metrics", *SP.MANUAL_SLUGS):
        assert data[slug] is None, slug
    assert len(data["notes"]) >= 7


def test_probe_cli_json(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    r = subprocess.run(
        [sys.executable, str(SCRIPTS / "source_probe.py"), "--source-root", str(src)],
        capture_output=True, text=True, check=False)
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert data["source_root"].endswith("src")
