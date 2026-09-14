"""baseline_anchors_status + analyse_metrics 基线尺子节。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.baseline_anchors_status import assess_baseline_anchors, format_baseline_anchors_markdown
from lib.metric_analysis import build_analyse_report


def _exp_plain(root: Path, value: float | None) -> None:
    p_cell = "-" if value is None else f"plain_anchor_value={value}"
    (root / "EXPERIENCE.md").write_text(
        "## Tier 状态\n"
        "| Tier | routine | extend | novel | extra | plain(P) |\n"
        "|------|---------|--------|-------|-------|----------|\n"
        f"| E    | a       | b      | c     | x     | {p_cell} |\n",
        encoding="utf-8",
    )


def test_assess_missing_both(tmp_path: Path):
    _exp_plain(tmp_path, None)
    st = assess_baseline_anchors(tmp_path)
    assert st.missing == ["plain", "reference"]
    assert any("/auto-nn-plain" in r for r in st.recommendations)
    ref_rec = next(r for r in st.recommendations if "公开对照" in r or "reference" in r)
    assert "/auto-nn-reference" in ref_rec
    assert "/auto-nn-manual-run" not in ref_rec
    md = format_baseline_anchors_markdown(st)
    assert "**缺**" in md


def test_assess_missing_reference_only_when_plain_present(tmp_path: Path):
    _exp_plain(tmp_path, 0.42)
    st = assess_baseline_anchors(tmp_path)
    assert st.missing == ["reference"]
    assert not any("/auto-nn-plain" in r for r in st.recommendations)
    ref_rec = next(r for r in st.recommendations if "公开对照" in r or "reference" in r)
    assert "/auto-nn-reference" in ref_rec
    assert "/auto-nn-manual-run" not in ref_rec


def test_assess_plain_and_ref_number(tmp_path: Path):
    _exp_plain(tmp_path, 0.5)
    exp = tmp_path / "EXPERIENCE.md"
    exp.write_text(
        exp.read_text(encoding="utf-8")
        + "\n## 基线锚点（external reference）\n\n- reference_anchor_value: 0.9\n",
        encoding="utf-8",
    )
    st = assess_baseline_anchors(tmp_path)
    assert st.has_plain and st.has_reference_number
    assert st.missing == []


def test_assess_reference_run_from_tsv(tmp_path: Path):
    _exp_plain(tmp_path, 0.4)
    runs = tmp_path / "_runs"
    runs.mkdir()
    (runs / "results.tsv").write_text(
        "run_id\tbaseline_tag\n1\tnone\n2\treference\n", encoding="utf-8"
    )
    st = assess_baseline_anchors(tmp_path)
    assert st.has_reference_run
    assert "reference" not in st.missing


def test_assess_recommends_source_cal_when_source_repo_present(tmp_path: Path):
    _exp_plain(tmp_path, 0.42)
    src = tmp_path / "upstream"
    src.mkdir()
    nn = tmp_path / ".auto-nn"
    nn.mkdir()
    (nn / "migration-source").write_text(str(src) + "\n", encoding="utf-8")
    st = assess_baseline_anchors(tmp_path)
    assert st.missing == ["reference"]
    assert any("先本机跑原仓" in r for r in st.recommendations)
    assert any("/auto-nn-reference" in r for r in st.recommendations)


def test_analyse_report_includes_baseline_section(tmp_path: Path):
    _exp_plain(tmp_path, None)
    # minimal so build_analyse_report does not crash hard
    (tmp_path / "_runs").mkdir()
    (tmp_path / "_runs" / "results.tsv").write_text(
        "experiment\tscenario_id\ttest_acc\n"
        "e1\tdefault\t0.5\n",
        encoding="utf-8",
    )
    (tmp_path / "nn-config.yaml").write_text(
        "profile: supervised\nexploration_mode: optimize\n", encoding="utf-8"
    )
    report = build_analyse_report(tmp_path, quiet=True)
    assert "## 基线尺子" in report.markdown
    assert "baseline_anchors" in report.sections
    assert "plain" in report.sections["baseline_anchors"]["missing"]
    assert any("基线尺子缺口" in w for w in report.warnings)
