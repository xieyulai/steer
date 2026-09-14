"""TSV baseline_tag 检索：plain / reference。"""
from __future__ import annotations

from pathlib import Path

from lib.baseline_anchors_status import (
    has_plain_baseline_tag,
    has_reference_baseline_tag,
)


def test_no_tsv_means_no_plain(tmp_path: Path):
    assert has_plain_baseline_tag(tmp_path) is False


def test_missing_column_means_no_plain(tmp_path: Path):
    runs = tmp_path / "_runs"
    runs.mkdir()
    (runs / "results.tsv").write_text("run_id\tacc\n1\t0.5\n", encoding="utf-8")
    assert has_plain_baseline_tag(tmp_path) is False


def test_plain_row_detected(tmp_path: Path):
    runs = tmp_path / "_runs"
    runs.mkdir()
    (runs / "results.tsv").write_text(
        "run_id\tbaseline_tag\n1\tnone\n2\tplain\n", encoding="utf-8"
    )
    assert has_plain_baseline_tag(tmp_path) is True
    assert has_reference_baseline_tag(tmp_path) is False


def test_scenario_filter(tmp_path: Path):
    runs = tmp_path / "_runs"
    runs.mkdir()
    (runs / "results.tsv").write_text(
        "run_id\tscenario_id\tbaseline_tag\n"
        "1\ta\tplain\n"
        "2\tb\tnone\n",
        encoding="utf-8",
    )
    assert has_plain_baseline_tag(tmp_path, scenario_id="a") is True
    assert has_plain_baseline_tag(tmp_path, scenario_id="b") is False
    assert has_plain_baseline_tag(tmp_path) is True  # 全表


def test_reference_row_detected(tmp_path: Path):
    runs = tmp_path / "_runs"
    runs.mkdir()
    (runs / "results.tsv").write_text(
        "run_id\tbaseline_tag\n1\treference\n", encoding="utf-8"
    )
    assert has_reference_baseline_tag(tmp_path) is True
