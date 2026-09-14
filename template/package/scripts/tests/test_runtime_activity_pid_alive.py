"""runtime_activity：训练活跃仅认存活 pid（孤儿 status 不算 busy）。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from lib.runtime_activity import (  # noqa: E402
    any_runtime_active,
    detect_runtime_activity,
    list_stale_train_dirs,
    train_in_progress,
)


def _write_exp(repo: Path, name: str, *, pid: int | None, done: bool = False) -> Path:
    exp = repo / "_runs" / "exp" / name
    exp.mkdir(parents=True)
    if pid is not None:
        (exp / "train_status.json").write_text(
            json.dumps({"pid": pid, "phase": "training"}),
            encoding="utf-8",
        )
    if done:
        (exp / "train_done.json").write_text("{}", encoding="utf-8")
    return exp


def test_dead_pid_status_is_idle_not_active(tmp_path: Path):
    (tmp_path / "saved").mkdir()
    # 极大且必不存在的 pid
    dead = 2_147_483_646
    assert not Path(f"/proc/{dead}").exists()
    _write_exp(tmp_path, "20260725_orphan_dead", pid=dead, done=False)

    active, detail = train_in_progress(tmp_path)
    assert active is False
    assert detail == ""

    report = detect_runtime_activity(tmp_path)
    assert report.train_active is False
    assert any_runtime_active(report) is False
    assert "20260725_orphan_dead" in (report.stale_train_dirs or [])
    assert list_stale_train_dirs(tmp_path) == ["20260725_orphan_dead"]


def test_live_pid_status_is_active(tmp_path: Path, monkeypatch):
    (tmp_path / "saved").mkdir()
    live = os.getpid()
    _write_exp(tmp_path, "20260725_live_train", pid=live, done=False)

    active, detail = train_in_progress(tmp_path)
    assert active is True
    assert "pid=" in detail
    assert str(live) in detail

    report = detect_runtime_activity(tmp_path)
    assert report.train_active is True
    assert any_runtime_active(report) is True
    assert report.stale_train_dirs == []


def test_done_exp_skipped_even_with_status(tmp_path: Path):
    (tmp_path / "saved").mkdir()
    live = os.getpid()
    _write_exp(tmp_path, "20260725_done", pid=live, done=True)
    report = detect_runtime_activity(tmp_path)
    assert report.train_active is False
    assert any_runtime_active(report) is False


def test_auto_run_pid_file_alive(tmp_path: Path):
    saved = tmp_path / "saved"
    saved.mkdir()
    pid = os.getpid()
    (saved / ".auto-run-active.pid").write_text(str(pid), encoding="utf-8")
    report = detect_runtime_activity(tmp_path)
    assert report.auto_run_active is True
    assert report.auto_run_pid == pid
    assert any_runtime_active(report) is True
