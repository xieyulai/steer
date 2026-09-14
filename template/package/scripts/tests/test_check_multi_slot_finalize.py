"""L3-D1: check_multi_slot_finalize.py 多槽 finalize 门禁单测。

覆盖 5 场景：
  1. 无 _runs/exp → 0 (OK)
  2. 1 个 single-slot (_s0of1_) 已 train_done → 0 (单槽不算 multi)
  3. 2 个 multi-slot (_s0of2_ + _s1of2_) 都 train_done + jsonl 都入 → 0 (PASS)
  4. 2 个 multi-slot train_done + jsonl 只入 1 个 → 1 (gap)
  5. 2 个 multi-slot train_done + jsonl 都缺 → 1 (gap，列 2 个)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
_HELPER = _SCRIPTS / "check_multi_slot_finalize.py"


def _write_train_done(exp_dir: Path) -> None:
    exp_dir.mkdir(parents=True, exist_ok=True)
    (exp_dir / "train_done.json").write_text(
        json.dumps({"epoch": 5, "metric": {"top1_accuracy": 0.9}}),
        encoding="utf-8",
    )


def _write_jsonl(repo_root: Path, exp_dirs: list[Path]) -> None:
    (repo_root / "_runs").mkdir(parents=True, exist_ok=True)
    jsonl_path = repo_root / "_runs" / "results.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for d in exp_dirs:
            f.write(json.dumps({"exp_dir": str(d.resolve())}) + "\n")


def _run_check(repo_root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_HELPER), "--repo-root", str(repo_root)],
        capture_output=True, text=True, timeout=10,
    )


# ── 场景 1：无 _runs/exp ─────────────────────────────────────────────

def test_no_exp_dir_returns_ok(tmp_path):
    """无 _runs/exp 时返回 0（无 multi-slot 可检）"""
    result = _run_check(tmp_path)
    assert result.returncode == 0, f"FAIL rc={result.returncode} stdout={result.stdout!r}"
    assert "OK" in result.stdout


# ── 场景 2：单槽不算 multi ──────────────────────────────────────────

def test_single_slot_dir_ignored(tmp_path):
    """_s0of1_ 是单槽命名（N=1 < 2），不算 multi-slot → 0"""
    _write_train_done(tmp_path / "_runs" / "exp" / "exp_s0of1_20260708_aaaaa_run")
    result = _run_check(tmp_path)
    assert result.returncode == 0, f"FAIL rc={result.returncode} stdout={result.stdout!r}"


# ── 场景 3：2 个 multi-slot 都 finalize ─────────────────────────────

def test_all_multi_slot_finalized_returns_ok(tmp_path):
    """2 个 multi-slot 都 train_done 且 jsonl 都有 → 0"""
    exp0 = tmp_path / "_runs" / "exp" / "exp_s0of2_20260708_aaaaa_run"
    exp1 = tmp_path / "_runs" / "exp" / "exp_s1of2_20260708_bbbbb_run"
    _write_train_done(exp0)
    _write_train_done(exp1)
    _write_jsonl(tmp_path, [exp0, exp1])
    result = _run_check(tmp_path)
    assert result.returncode == 0, f"FAIL rc={result.returncode} stdout={result.stdout!r}"


# ── 场景 4：1 个 finalize + 1 个 gap ────────────────────────────────

def test_partial_finalize_returns_gap(tmp_path):
    """2 个 multi-slot，jsonl 只入 1 个 → 1 + 列出 unfinalized 那个"""
    exp0 = tmp_path / "_runs" / "exp" / "exp_s0of2_20260708_aaaaa_run"
    exp1 = tmp_path / "_runs" / "exp" / "exp_s1of2_20260708_bbbbb_run"
    _write_train_done(exp0)
    _write_train_done(exp1)
    _write_jsonl(tmp_path, [exp0])  # exp1 缺
    result = _run_check(tmp_path)
    assert result.returncode == 1, f"FAIL rc={result.returncode} stdout={result.stdout!r}"
    assert "UNFINALIZED" in result.stdout
    assert "exp_s1of2_20260708_bbbbb_run" in result.stdout
    assert "exp_s0of2_20260708_aaaaa_run" not in result.stdout  # 已入账的不该报


# ── 场景 5：2 个都缺 finalize ──────────────────────────────────────

def test_no_jsonl_returns_all_unfinalized(tmp_path):
    """2 个 multi-slot train_done + 0 jsonl → 1 + 列 2 个"""
    exp0 = tmp_path / "_runs" / "exp" / "exp_s0of2_20260708_aaaaa_run"
    exp1 = tmp_path / "_runs" / "exp" / "exp_s1of2_20260708_bbbbb_run"
    _write_train_done(exp0)
    _write_train_done(exp1)
    result = _run_check(tmp_path)
    assert result.returncode == 1, f"FAIL rc={result.returncode} stdout={result.stdout!r}"
    assert "UNFINALIZED" in result.stdout
    # 顺序按 name 排序：s0of2_... < s1of2_...
    lines = [l for l in result.stdout.splitlines() if l.startswith("UNFINALIZED:")]
    assert len(lines) == 2, f"应列 2 行, 实得 {len(lines)}: {result.stdout!r}"
    assert "exp_s0of2" in lines[0]
    assert "exp_s1of2" in lines[1]


# ── 场景 6：multi-slot dir 但没 train_done → 忽略 ─────────────────────

def test_multi_slot_dir_without_train_done_ignored(tmp_path):
    """_s0of2_ 目录但 train_done.json 缺失 → 不算完成 → 0"""
    (tmp_path / "_runs" / "exp" / "exp_s0of2_20260708_aaaaa_run").mkdir(parents=True)
    result = _run_check(tmp_path)
    assert result.returncode == 0, f"FAIL rc={result.returncode} stdout={result.stdout!r}"
