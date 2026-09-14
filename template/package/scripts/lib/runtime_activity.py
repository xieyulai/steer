"""运行态检测：auto-run batch、训练进行中、train_pid 文件（analyse / doctor / batch-hint 共用）。"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

AUTO_RUN_PID_BASENAME = ".auto-run-active.pid"
TRAIN_PID_BASENAME = ".train_pid"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(_read_text(path))
        return raw if isinstance(raw, dict) else None
    except Exception:
        return None


def _exp_dirs_newest_first(repo_root: Path, *, limit: int = 8) -> list[Path]:
    exp_root = repo_root / "_runs" / "exp"
    if not exp_root.is_dir():
        return []
    dirs = [p for p in exp_root.iterdir() if p.is_dir()]
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return dirs[:limit]


def auto_run_active(repo_root: Path) -> bool:
    """auto-run batch 是否在跑：NN_AUTO_RUN_ACTIVE 或 saved 下活跃 pid。"""
    active, _ = _auto_run_state(repo_root)
    return active


def _auto_run_state(repo_root: Path) -> tuple[bool, int | None]:
    root = repo_root.resolve()
    raw = os.environ.get("NN_AUTO_RUN_ACTIVE", "").strip().lower()
    pf = root / "saved" / AUTO_RUN_PID_BASENAME
    if raw in ("1", "true", "yes"):
        if pf.is_file():
            try:
                pid = int(pf.read_text(encoding="utf-8").strip())
            except ValueError:
                return True, None
            return pid_alive(pid), pid if pid_alive(pid) else None
        return True, None
    if not pf.is_file():
        return False, None
    try:
        pid = int(pf.read_text(encoding="utf-8").strip())
    except ValueError:
        return False, None
    alive = pid_alive(pid)
    return alive, pid if alive else None


def train_in_progress(repo_root: Path) -> tuple[bool, str]:
    """Heuristic: latest exp dirs missing train_done with live train_status pid."""
    report = _scan_train_exp(repo_root)
    if report is None:
        return False, ""
    return True, report[1]


def _scan_train_exp(repo_root: Path) -> tuple[int | None, str] | None:
    """仅当 train_status.pid 仍存活时视为训练中。

    有 status、无 done、pid 已死的孤儿目录不算活跃（避免误报「运行中」）。
    """
    for exp in _exp_dirs_newest_first(repo_root):
        if (exp / "train_done.json").is_file():
            continue
        status = _load_json(exp / "train_status.json")
        if not status:
            continue
        pid = status.get("pid")
        if isinstance(pid, int) and pid_alive(pid):
            phase = str(status.get("phase") or "training")
            return pid, f"{exp.name}（pid={pid}, phase={phase}）"
    return None


def list_stale_train_dirs(repo_root: Path, *, limit: int = 8) -> list[str]:
    """有 train_status、无 train_done、pid 已死（或无合法 pid）的孤儿实验目录名。"""
    stale: list[str] = []
    for exp in _exp_dirs_newest_first(repo_root, limit=limit):
        if (exp / "train_done.json").is_file():
            continue
        status = _load_json(exp / "train_status.json")
        if not status:
            continue
        pid = status.get("pid")
        if isinstance(pid, int) and pid_alive(pid):
            continue
        stale.append(exp.name)
    return stale


def _train_pid_file_alive(repo_root: Path) -> int | None:
    data = _load_json(repo_root.resolve() / "saved" / TRAIN_PID_BASENAME)
    if not data:
        return None
    pid = data.get("pid")
    if isinstance(pid, int) and pid_alive(pid):
        return pid
    return None


@dataclass
class RuntimeActivityReport:
    auto_run_active: bool
    auto_run_pid: int | None
    train_active: bool
    train_detail: str
    train_pid_file_alive: int | None
    stale_train_dirs: list[str] | None = None


def detect_runtime_activity(repo_root: Path) -> RuntimeActivityReport:
    root = repo_root.resolve()
    ar_active, ar_pid = _auto_run_state(root)
    train_active = False
    train_detail = ""
    scanned = _scan_train_exp(root)
    if scanned is not None:
        train_active = True
        train_detail = scanned[1]
    tp = _train_pid_file_alive(root)
    return RuntimeActivityReport(
        auto_run_active=ar_active,
        auto_run_pid=ar_pid,
        train_active=train_active,
        train_detail=train_detail,
        train_pid_file_alive=tp,
        stale_train_dirs=list_stale_train_dirs(root),
    )


def any_runtime_active(report: RuntimeActivityReport) -> bool:
    return bool(
        report.auto_run_active
        or report.train_active
        or report.train_pid_file_alive is not None
    )


def _doctor_message(report: RuntimeActivityReport) -> str:
    parts: list[str] = []
    if report.auto_run_active:
        if report.auto_run_pid is not None:
            parts.append(f"auto-run batch pid={report.auto_run_pid}")
        else:
            parts.append("auto-run batch 活跃")
    if report.train_active:
        parts.append(f"train {report.train_detail}" if report.train_detail else "train 进行中")
    if report.train_pid_file_alive is not None:
        tp = report.train_pid_file_alive
        train_pids = set()
        if report.train_active and "pid=" in report.train_detail:
            m = re.search(r"pid=(\d+)", report.train_detail)
            if m:
                train_pids.add(int(m.group(1)))
        if tp not in train_pids:
            parts.append(f"train_pid={tp}")
    return "; ".join(parts)


def doctor_runtime_status(repo_root: Path) -> tuple[str, str]:
    report = detect_runtime_activity(repo_root)
    if not any_runtime_active(report):
        return "PASS", "无活跃 auto-run / 训练"
    return "WARN", _doctor_message(report)


def format_runtime_markdown(repo_root: Path) -> str:
    report = detect_runtime_activity(repo_root)
    if not any_runtime_active(report):
        return ""
    lines = ["## 运行态", ""]
    if report.auto_run_active:
        if report.auto_run_pid is not None:
            lines.append(f"- **auto-run batch**：活跃（pid={report.auto_run_pid}）")
        else:
            lines.append("- **auto-run batch**：活跃")
    if report.train_active:
        detail = report.train_detail or "进行中"
        lines.append(f"- **训练**：{detail}")
    if report.train_pid_file_alive is not None:
        tp = report.train_pid_file_alive
        show = True
        if report.train_active and f"pid={tp}" in report.train_detail:
            show = False
        if show:
            lines.append(f"- **train_pid 文件**：pid={tp} 存活")
    lines.extend(
        [
            "",
            "> 台账可能未闭合；本次 analyse 为只读参考，勿并行改代码或开新训。",
        ]
    )
    return "\n".join(lines) + "\n"


def format_runtime_oneline(repo_root: Path) -> str | None:
    report = detect_runtime_activity(repo_root)
    if not any_runtime_active(report):
        return None
    tags: list[str] = []
    if report.auto_run_active:
        tags.append("auto-run")
    if report.train_active or report.train_pid_file_alive is not None:
        tags.append("train")
    pid_bits: list[str] = []
    if report.auto_run_pid is not None:
        pid_bits.append(f"batch={report.auto_run_pid}")
    if report.train_pid_file_alive is not None:
        pid_bits.append(f"train={report.train_pid_file_alive}")
    suffix = f" ({', '.join(pid_bits)})" if pid_bits else ""
    return f"runtime={','.join(tags)}{suffix}"
