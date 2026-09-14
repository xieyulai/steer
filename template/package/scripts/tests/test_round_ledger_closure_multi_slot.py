"""#6：multi-slot 未入账检测真源 = round_ledger_closure（统一正则 + resolve）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))


def _train_done(exp: Path) -> None:
    exp.mkdir(parents=True, exist_ok=True)
    (exp / "train_done.json").write_text("{}", encoding="utf-8")


def _jsonl(repo: Path, dirs: list[Path], *, relative: bool = False) -> None:
    (repo / "_runs").mkdir(parents=True, exist_ok=True)
    rows = []
    for d in dirs:
        rows.append({"exp_dir": str(d.relative_to(repo)) if relative else str(d.resolve())})
    (repo / "_runs" / "results.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n",
        encoding="utf-8",
    )


def test_find_unfinalized_matches_allocate_style_without_run_suffix(tmp_path):
    """allocate 风格 ..._s0of2_pid 无强制 _run 后缀，旧 _run$ 正则会漏。"""
    from lib.round_ledger_closure import find_unfinalized_multi_slot

    exp = tmp_path / "_runs" / "exp" / "run_20260718_120000_1_s0of2_exp"
    _train_done(exp)
    gaps = find_unfinalized_multi_slot(tmp_path)
    assert gaps == [exp.resolve()]


def test_find_unfinalized_ignores_single_slot(tmp_path):
    from lib.round_ledger_closure import find_unfinalized_multi_slot

    _train_done(tmp_path / "_runs" / "exp" / "exp_s0of1_x_run")
    assert find_unfinalized_multi_slot(tmp_path) == []


def test_find_unfinalized_resolve_matches_relative_jsonl(tmp_path):
    from lib.round_ledger_closure import find_unfinalized_multi_slot

    exp0 = tmp_path / "_runs" / "exp" / "exp_s0of2_aaaa_run"
    exp1 = tmp_path / "_runs" / "exp" / "exp_s1of2_bbbb_run"
    _train_done(exp0)
    _train_done(exp1)
    _jsonl(tmp_path, [exp0], relative=True)
    gaps = find_unfinalized_multi_slot(tmp_path)
    assert [p.name for p in gaps] == ["exp_s1of2_bbbb_run"]


def test_cli_matches_lib(tmp_path):
    import subprocess

    from lib.round_ledger_closure import find_unfinalized_multi_slot

    exp = tmp_path / "_runs" / "exp" / "exp_s0of2_cccc_run"
    _train_done(exp)
    helper = SCRIPTS / "check_multi_slot_finalize.py"
    proc = subprocess.run(
        [sys.executable, str(helper), "--repo-root", str(tmp_path)],
        capture_output=True, text=True, timeout=10,
    )
    lib_names = {p.name for p in find_unfinalized_multi_slot(tmp_path)}
    assert proc.returncode == 1
    assert "exp_s0of2_cccc_run" in proc.stdout
    assert lib_names == {"exp_s0of2_cccc_run"}
