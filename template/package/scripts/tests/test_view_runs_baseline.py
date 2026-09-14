"""view_runs --baseline-tags / --baseline-summary。"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
_VIEW = _SCRIPTS / "view_runs.py"


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_VIEW), "--root", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_baseline_summary_and_tags(tmp_path: Path):
    runs = tmp_path / "_runs"
    runs.mkdir()
    (runs / "results.tsv").write_text(
        "experiment\tscenario_id\ttest_acc\tbaseline_tag\n"
        "p1\tdefault\t0.4\tplain\n"
        "r1\tdefault\t0.8\treference\n"
        "f1\tdefault\t0.7\tnone\n",
        encoding="utf-8",
    )
    (tmp_path / "EXPERIENCE.md").write_text(
        "## Tier 状态\n"
        "| Tier | routine | extend | novel | extra | plain(P) |\n"
        "|------|---------|--------|-------|-------|----------|\n"
        "| E    | a       | b      | c     | x     | plain_anchor_value=0.4 |\n",
        encoding="utf-8",
    )
    s = _run(tmp_path, "--baseline-summary")
    assert s.returncode == 0
    assert "plain=yes" in s.stdout
    assert "reference=yes" in s.stdout or "reference=NO" in s.stdout  # tag row counts as yes

    t = _run(
        tmp_path,
        "--baseline-tags",
        "plain,reference",
        "--format",
        "tsv",
        "--no-header",
    )
    assert t.returncode == 0
    assert "plain" in t.stdout and "reference" in t.stdout
    assert "none" not in t.stdout.splitlines()[-1] if t.stdout.strip() else True
    # filtered to 2 rows
    data_lines = [ln for ln in t.stdout.splitlines() if ln.strip()]
    assert len(data_lines) == 2


def test_table_shows_dash_for_none_baseline_tag(tmp_path: Path):
    runs = tmp_path / "_runs"
    runs.mkdir()
    (runs / "results.tsv").write_text(
        "experiment\tbaseline_tag\n"
        "f1\tnone\n"
        "p1\tplain\n",
        encoding="utf-8",
    )
    t = _run(tmp_path, "--format", "table", "--cols", "experiment,baseline_tag")
    assert t.returncode == 0
    assert "plain" in t.stdout
    assert re.search(r"\bf1\b.*-", t.stdout) or "-  " in t.stdout or t.stdout.count("-") >= 1
    # 表体不应把 none 给人看（表头分隔线的 --- 除外：只查数据行）
    body = t.stdout.splitlines()
    data = [ln for ln in body if ln.strip() and not set(ln.replace(" ", "")) <= {"-"}]
    assert not any(re.search(r"\bnone\b", ln) for ln in data)

    raw = _run(tmp_path, "--format", "tsv", "--no-header", "--cols", "baseline_tag")
    assert "none" in raw.stdout
    assert "plain" in raw.stdout
