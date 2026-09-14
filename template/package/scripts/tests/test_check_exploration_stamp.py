"""check_exploration_stamp：空格 WARN/FAIL、禁 E-、e_feedback schema。"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS))

from check_exploration_stamp import (  # noqa: E402
    CELL_RE,
    Issue,
    aggregate_severity,
    check_e_feedback_file,
    check_tsv_rows,
    collect_unregistered_issues,
    format_unregistered_report,
    parse_elapsed,
    parse_row_date,
    parse_since_date,
    unregistered_changed_keys,
)


def _tsv(repo: Path, body: str) -> Path:
    runs = repo / "_runs"
    runs.mkdir(parents=True, exist_ok=True)
    p = runs / "results.tsv"
    p.write_text(body, encoding="utf-8")
    return p


def _run_cli(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(_SCRIPTS / "check_exploration_stamp.py"),
            "--check",
            "--repo-root",
            str(repo),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_parse_elapsed_missing_is_zero():
    assert parse_elapsed({}) == 0.0
    assert parse_elapsed({"elapsed_sec": ""}) == 0.0
    assert parse_elapsed({"elapsed_sec": "12.5"}) == 12.5


def test_parse_row_date_iso():
    assert parse_row_date("2026-08-20T12:00:00+00:00") == date(2026, 8, 20)
    assert parse_row_date("2026-08-20") == date(2026, 8, 20)
    assert parse_row_date("") is None
    assert parse_row_date("bogus") is None


def test_cell_regex_abcd_only():
    assert CELL_RE.match("A-routine")
    assert CELL_RE.match("D-novel")
    assert not CELL_RE.match("E-routine")
    assert not CELL_RE.match("A-extend")
    assert not CELL_RE.match("")


def test_e_prefix_fail():
    issues = check_tsv_rows(
        [
            {
                "experiment": "e1",
                "elapsed_sec": "10",
                "exploration_space": "E-routine",
                "timestamp": "2026-08-29T00:00:00+00:00",
            }
        ],
        since=date(2026, 8, 1),
    )
    assert any(i.severity == "FAIL" and "E-" in i.message for i in issues)


def test_empty_untrained_ok():
    issues = check_tsv_rows(
        [
            {
                "experiment": "u1",
                "elapsed_sec": "0.4",
                "exploration_space": "",
                "timestamp": "2026-08-29T00:00:00+00:00",
            }
        ],
        since=date(2026, 8, 1),
    )
    assert issues == []


def test_empty_untrained_flag_long_clock_ok():
    """墙钟≥1s 但 untrained=1（典型 smoke）→ 空格不得 FAIL。"""
    issues = check_tsv_rows(
        [
            {
                "experiment": "smoke1",
                "elapsed_sec": "10",
                "exploration_space": "",
                "untrained": "1",
                "timestamp": "2026-08-29T00:00:00+00:00",
            }
        ],
        since=date(2026, 8, 1),
    )
    assert issues == []


def test_empty_trained_before_since_warn():
    issues = check_tsv_rows(
        [
            {
                "experiment": "old",
                "elapsed_sec": "10",
                "exploration_space": "",
                "timestamp": "2026-07-01T00:00:00+00:00",
            }
        ],
        since=date(2026, 8, 1),
    )
    assert len(issues) == 1
    assert issues[0].severity == "WARN"


def test_empty_trained_on_or_after_since_fail():
    issues = check_tsv_rows(
        [
            {
                "experiment": "new",
                "elapsed_sec": "10",
                "exploration_space": "",
                "timestamp": "2026-08-15T00:00:00+00:00",
            }
        ],
        since=date(2026, 8, 1),
    )
    assert len(issues) == 1
    assert issues[0].severity == "FAIL"


def test_empty_trained_no_since_warn():
    issues = check_tsv_rows(
        [
            {
                "experiment": "any",
                "elapsed_sec": "10",
                "exploration_space": "",
                "timestamp": "2026-08-29T00:00:00+00:00",
            }
        ],
        since=None,
    )
    assert len(issues) == 1
    assert issues[0].severity == "WARN"


def test_valid_cell_pass():
    issues = check_tsv_rows(
        [
            {
                "experiment": "ok",
                "elapsed_sec": "10",
                "exploration_space": "B-derived",
                "timestamp": "2026-08-29T00:00:00+00:00",
            }
        ],
        since=date(2026, 8, 1),
    )
    assert issues == []


def test_invalid_cell_fail():
    issues = check_tsv_rows(
        [
            {
                "experiment": "bad",
                "elapsed_sec": "10",
                "exploration_space": "A-extend",
                "timestamp": "2026-08-29T00:00:00+00:00",
            }
        ],
        since=date(2026, 8, 1),
    )
    assert any(i.severity == "FAIL" for i in issues)


def test_e_feedback_bad_json_fail(tmp_path: Path):
    p = tmp_path / "_runs" / "analysis" / "e_feedback.jsonl"
    p.parent.mkdir(parents=True)
    p.write_text("{not json\n", encoding="utf-8")
    issues = check_e_feedback_file(p)
    assert any(i.severity == "FAIL" for i in issues)


def test_e_feedback_missing_fields_fail(tmp_path: Path):
    p = tmp_path / "_runs" / "analysis" / "e_feedback.jsonl"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"id": "E1", "kind": "shout"}) + "\n", encoding="utf-8")
    issues = check_e_feedback_file(p)
    assert any(i.severity == "FAIL" for i in issues)


def test_e_feedback_ok(tmp_path: Path):
    p = tmp_path / "_runs" / "analysis" / "e_feedback.jsonl"
    p.parent.mkdir(parents=True)
    rec = {
        "id": "E20260829_001",
        "kind": "shout",
        "resolution": {"status": "pending"},
    }
    p.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    assert check_e_feedback_file(p) == []


def test_aggregate_fail_wins():
    assert aggregate_severity([Issue("WARN", "a"), Issue("FAIL", "b")]) == "FAIL"
    assert aggregate_severity([Issue("WARN", "a")]) == "WARN"
    assert aggregate_severity([]) == "PASS"


def test_cli_first_line_prefix(tmp_path: Path):
    _tsv(
        tmp_path,
        "experiment\telapsed_sec\texploration_space\ttimestamp\n"
        "x\t10\tE-routine\t2026-08-29T00:00:00+00:00\n",
    )
    (tmp_path / ".auto-nn").mkdir()
    (tmp_path / ".auto-nn" / "exploration-stamp-since").write_text(
        "2026-08-01\n", encoding="utf-8"
    )
    r = _run_cli(tmp_path)
    assert r.returncode == 0
    first = r.stdout.splitlines()[0]
    assert first.startswith("FAIL:")


def test_cli_historical_empty_warn(tmp_path: Path):
    _tsv(
        tmp_path,
        "experiment\telapsed_sec\texploration_space\ttimestamp\n"
        "old\t10\t\t2026-07-01T00:00:00+00:00\n",
    )
    (tmp_path / ".auto-nn").mkdir()
    (tmp_path / ".auto-nn" / "exploration-stamp-since").write_text(
        "2026-08-01\n", encoding="utf-8"
    )
    r = _run_cli(tmp_path)
    first = r.stdout.splitlines()[0]
    assert first.startswith("WARN:")


def test_parse_since_date(tmp_path: Path):
    p = tmp_path / "exploration-stamp-since"
    p.write_text("2026-08-15\n", encoding="utf-8")
    assert parse_since_date(p) == date(2026, 8, 15)
    assert parse_since_date(tmp_path / "missing") is None


# --- unregistered_config_keys -------------------------------------------------


_FAKE_CATALOG = {
    "primary_keys": {"LOSS": {"tier": "C", "table": "objectives"}},
    "scalar_keys": ["LR", "SEED"],
    "ignore_config_keys": ["scenario_id", "git_commit"],
}


def test_unregistered_changed_keys_warns_unknown():
    prev = {"LOSS": "ce", "LR": 0.1, "MYSTERY_KNOB": 1}
    cur = {"LOSS": "ce", "LR": 0.1, "MYSTERY_KNOB": 2}
    assert unregistered_changed_keys(prev, cur, _FAKE_CATALOG) == ["MYSTERY_KNOB"]


def test_unregistered_changed_keys_registered_ok():
    prev = {"LOSS": "ce", "LR": 0.1, "scenario_id": "a"}
    cur = {"LOSS": "focal", "LR": 0.01, "scenario_id": "b"}
    assert unregistered_changed_keys(prev, cur, _FAKE_CATALOG) == []


def test_unregistered_changed_keys_new_key_counts():
    prev = {"LOSS": "ce"}
    cur = {"LOSS": "ce", "WEIRD_ALPHA": 0.5}
    assert unregistered_changed_keys(prev, cur, _FAKE_CATALOG) == ["WEIRD_ALPHA"]


def test_collect_unregistered_no_tsv_pass(tmp_path: Path):
    assert collect_unregistered_issues(tmp_path, catalog=_FAKE_CATALOG) == []


def test_collect_unregistered_empty_catalog_pass(tmp_path: Path):
    assert collect_unregistered_issues(tmp_path, catalog={}) == []


def _two_trained_exps(repo: Path, prev_cfg: dict, cur_cfg: dict) -> None:
    """写两行已训 TSV + 各自 config.json。"""
    d0 = repo / "_runs" / "exp" / "e0"
    d1 = repo / "_runs" / "exp" / "e1"
    d0.mkdir(parents=True)
    d1.mkdir(parents=True)
    (d0 / "config.json").write_text(json.dumps(prev_cfg), encoding="utf-8")
    (d1 / "config.json").write_text(json.dumps(cur_cfg), encoding="utf-8")
    _tsv(
        repo,
        "experiment\texp_dir\telapsed_sec\tscenario_id\n"
        f"e0\t_runs/exp/e0\t10\ts1\n"
        f"e1\t_runs/exp/e1\t12\ts1\n",
    )


def test_collect_unregistered_warns_on_mystery(tmp_path: Path):
    _two_trained_exps(
        tmp_path,
        {"LOSS": "ce", "LR": 0.1},
        {"LOSS": "ce", "LR": 0.1, "MYSTERY_KNOB": 9},
    )
    issues = collect_unregistered_issues(tmp_path, catalog=_FAKE_CATALOG)
    assert len(issues) == 1
    assert issues[0].severity == "WARN"
    assert "MYSTERY_KNOB" in issues[0].message


def test_collect_unregistered_all_registered_pass(tmp_path: Path):
    _two_trained_exps(
        tmp_path,
        {"LOSS": "ce", "LR": 0.1},
        {"LOSS": "focal", "LR": 0.05},
    )
    assert collect_unregistered_issues(tmp_path, catalog=_FAKE_CATALOG) == []


def test_format_unregistered_report_prefixes():
    assert format_unregistered_report([]).startswith("PASS:")
    assert format_unregistered_report(
        [Issue("WARN", "未登记: X")]
    ).startswith("WARN:")


def test_cli_check_unregistered_warn(tmp_path: Path):
    _two_trained_exps(
        tmp_path,
        {"LOSS": "ce"},
        {"LOSS": "ce", "ORPHAN_KEY": True},
    )
    # 无种子 catalog 时用 -- 仍应能跑；此处注入假 catalog 路径不便，
    # 用 collect 已覆盖；CLI 无 TSV 变更键时 PASS。
    r = subprocess.run(
        [
            sys.executable,
            str(_SCRIPTS / "check_exploration_stamp.py"),
            "--check-unregistered",
            "--repo-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    # 种子 catalog 不含 ORPHAN_KEY → WARN；或空 catalog → PASS
    first = r.stdout.splitlines()[0]
    assert first.startswith("PASS:") or first.startswith("WARN:")
    if first.startswith("WARN:"):
        assert "ORPHAN_KEY" in r.stdout


def test_cli_check_unregistered_no_tsv_pass(tmp_path: Path):
    r = subprocess.run(
        [
            sys.executable,
            str(_SCRIPTS / "check_exploration_stamp.py"),
            "--check-unregistered",
            "--repo-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    assert r.stdout.splitlines()[0].startswith("PASS:")
