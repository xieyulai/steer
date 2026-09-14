"""check_brief.py — 默认参照五段。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
_BRIEF = _SCRIPTS / "check_brief.py"


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_BRIEF), "--root", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _seed_minimal(repo: Path) -> None:
    (repo / "README.md").write_text(
        "## 场景清单\n\n"
        "| 场景 ID | 说明 |\n"
        "| --- | --- |\n"
        "| seq | demo |\n"
        "| cls | demo2 |\n",
        encoding="utf-8",
    )
    (repo / "nn-config.yaml").write_text(
        "agent:\n"
        "  scenario_default: seq\n"
        "  scenario_active: seq,cls\n"
        "goal:\n"
        "  target: 0.9\n"
        "  metric: test_acc\n"
        '  op: ">="\n'
        "  policy: focus\n",
        encoding="utf-8",
    )
    runs = repo / "_runs"
    runs.mkdir()
    (runs / "results.tsv").write_text(
        "experiment\tscenario_id\ttest_acc\tbaseline_tag\n"
        "p1\tseq\t0.4\tplain\n"
        "r1\tseq\t0.85\treference\n"
        "k1\tseq\t0.88\tnone\n",
        encoding="utf-8",
    )
    saved = repo / "saved"
    saved.mkdir()
    exp = runs / "exp" / "k1"
    exp.mkdir(parents=True)
    (saved / "keepers.json").write_text(
        '{"seq": {"keeper_exp_dir": "' + str(exp) + '"}}\n',
        encoding="utf-8",
    )


def test_check_brief_five_sections(tmp_path: Path):
    _seed_minimal(tmp_path)
    r = _run(tmp_path)
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "## check-brief" in out
    assert "focus: seq" in out
    assert "scenarios: inventory=seq,cls" in out
    assert "active=seq,cls" in out
    assert "goal:" in out and "NO_GOAL" not in out
    assert "baseline:" in out and "plain=yes" in out
    assert "keeper:" in out
    assert "seq" in out
    assert "audit: (无)" in out
    assert "e_feedback: (无)" in out


def test_check_brief_empty_repo_placeholders(tmp_path: Path):
    r = _run(tmp_path)
    assert r.returncode == 0, r.stderr
    assert "focus: (无)" in r.stdout
    assert "goal: NO_GOAL" in r.stdout
    assert "baseline:" in r.stdout
    assert "audit: (无)" in r.stdout
    assert "e_feedback: (无)" in r.stdout


def test_check_brief_e_feedback_pending_count(tmp_path: Path):
    from lib.e_feedback_store import append_event

    _seed_minimal(tmp_path)
    append_event(
        tmp_path,
        kind="shout",
        proposed="改主指标",
        why_abcd_insufficient="官方测试口径扫不动",
        ask="开闸改主指标",
        quote="建议改题",
        experiment="k1",
        source="reflect",
        round_hint=1,
    )
    r = _run(tmp_path)
    assert r.returncode == 0, r.stderr
    assert "e_feedback: pending=1 deferred=0" in r.stdout


def test_check_brief_audit_with_card(tmp_path: Path):
    from lib.audit_core import write_index_entry

    _seed_minimal(tmp_path)
    card_dir = tmp_path / "saved" / "audit" / "t1_seq"
    card_dir.mkdir(parents=True)
    (card_dir / "card.json").write_text(
        '{"attested_depth": "novel", "repro_ok": true}\n', encoding="utf-8"
    )
    exp = tmp_path / "_runs" / "exp" / "k1"
    write_index_entry(
        tmp_path,
        scenario_id="seq",
        card_dir=str(card_dir),
        audited_exp_dir=str(exp),
        config_sha256="aa",
    )
    r = _run(tmp_path)
    assert r.returncode == 0, r.stderr
    assert "audit:" in r.stdout
    assert "current" in r.stdout
    assert "saved/audit/t1_seq" in r.stdout
    assert "focus: seq" in r.stdout
    assert "goal:" in r.stdout
    assert "baseline:" in r.stdout
    assert "keeper:" in r.stdout
