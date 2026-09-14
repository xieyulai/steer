"""HUMAN_GUIDANCE.md 批次基线与 G-HUMAN 校验（auto-run 运维护栏）。"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from lib.human_guidance_roadmap import count_roadmap_phases
from lib.runtime_activity import (  # noqa: F401 — re-export
    auto_run_active,
    detect_runtime_activity,
    pid_alive as _pid_alive,
    train_in_progress,
)

BASELINE_BASENAME = ".human-guidance-baseline.json"
HUMAN_REL = "HUMAN_GUIDANCE.md"

G_HUMAN_INSTALL_FILES: tuple[str, ...] = (
    "scripts/human_guidance_gate.py",
    "scripts/lib/human_guidance_gate.py",
    "scripts/lib/human_guidance_roadmap.py",
    "scripts/refresh-human-guidance-baseline.sh",
)


class AutoRunActiveError(RuntimeError):
    """当 auto-run batch 仍活跃时调用 refresh baseline 会抛出。"""


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def baseline_path(repo_root: Path) -> Path:
    return repo_root.resolve() / "saved" / BASELINE_BASENAME


def human_path(repo_root: Path) -> Path:
    return repo_root.resolve() / HUMAN_REL


def verify_g_human_install(repo_root: Path) -> str | None:
    """G-HUMAN 加固文件齐套且可 import；缺则返回 WARN 说明。"""
    root = repo_root.resolve()
    missing = [rel for rel in G_HUMAN_INSTALL_FILES if not (root / rel).is_file()]
    if missing:
        return (
            "G-HUMAN 文件缺失: "
            + ", ".join(missing)
            + " — 运行 governance-sync"
        )
    scripts = root / "scripts"
    path_snapshot = sys.path.copy()
    try:
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        # noqa: F401 — 验证从 repo scripts 上下文可导入
        from lib.human_guidance_gate import post_round_enforce  # noqa: F401
        from lib.human_guidance_roadmap import count_roadmap_phases  # noqa: F401
    except Exception as exc:
        return f"G-HUMAN import 失败: {exc}"
    finally:
        sys.path[:] = path_snapshot

    cli = root / "scripts" / "human_guidance_gate.py"
    if cli.is_file():
        text = cli.read_text(encoding="utf-8", errors="replace")
        if "post-round-enforce" not in text:
            return "human_guidance_gate.py CLI 缺少 post-round-enforce"
    return None


def _git_head_short(repo_root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if out.returncode == 0:
            return (out.stdout or "").strip()
    except OSError:
        pass
    return ""


def load_baseline(repo_root: Path) -> dict[str, Any] | None:
    p = baseline_path(repo_root)
    if not p.is_file():
        return None
    try:
        raw = json.loads(_read_text(p))
        return raw if isinstance(raw, dict) else None
    except Exception:
        return None


def write_baseline(repo_root: Path) -> dict[str, Any] | None:
    root = repo_root.resolve()
    hp = human_path(root)
    if not hp.is_file():
        return None
    saved = root / "saved"
    saved.mkdir(parents=True, exist_ok=True)
    text = _read_text(hp)
    payload: dict[str, Any] = {
        "path": HUMAN_REL,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "git_head": _git_head_short(root),
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "n_phases": count_roadmap_phases(text),
    }
    baseline_path(root).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def refresh_baseline(repo_root: Path) -> dict[str, Any] | None:
    if auto_run_active(repo_root):
        raise AutoRunActiveError(
            "REFUSE: auto-run batch 活跃，禁止 refresh baseline；须停 batch 后由人恢复 "
            "HUMAN 再 refresh"
        )
    return write_baseline(repo_root)


@dataclass
class EnforceAction:
    kind: str  # "commit_revert" | "ws_revert" | "skip"
    detail: str


def restore_from_baseline(repo_root: Path) -> tuple[bool, str]:
    baseline = load_baseline(repo_root)
    if not baseline:
        return False, "no baseline"
    hp = human_path(repo_root)
    git_head = str(baseline.get("git_head") or "").strip()
    if git_head:
        proc = subprocess.run(
            ["git", "checkout", git_head, "--", HUMAN_REL],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            msg = ((proc.stderr or "") + (proc.stdout or "")).strip()
            return False, msg or "git checkout failed"
    expected = str(baseline.get("sha256") or "")
    if hp.is_file() and file_sha256(hp) == expected:
        return True, "restored"
    return False, f"sha mismatch after restore (expected {expected[:8]}…)"


_DEFAULT_G_HUMAN_COMMIT_ENV = {
    "GIT_AUTHOR_NAME": "auto-nn",
    "GIT_AUTHOR_EMAIL": "auto-nn@local",
    "GIT_COMMITTER_NAME": "auto-nn",
    "GIT_COMMITTER_EMAIL": "auto-nn@local",
}


def post_round_enforce(
    repo_root: Path,
    *,
    run: int = 0,
    env_override: Mapping[str, str] | None = None,
) -> list[EnforceAction]:
    """轮末 enforcement：最近一次 commit / 工作区若 drift HUMAN，则按 baseline 恢复并可有修复 commit。"""
    actions: list[EnforceAction] = []
    baseline = load_baseline(repo_root)
    if not baseline:
        return [EnforceAction("skip", "no baseline")]

    def _needs_restore() -> bool:
        hp = human_path(repo_root)
        if not hp.is_file():
            return False
        return file_sha256(hp) != str(baseline.get("sha256") or "")

    commit_touched = False
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD~1"],
        cwd=str(repo_root),
        capture_output=True,
    )
    if proc.returncode == 0:
        diff = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        if diff.returncode == 0 and any(
            ln.strip() == HUMAN_REL for ln in (diff.stdout or "").splitlines()
        ):
            hp = human_path(repo_root)
            head_sha = file_sha256(hp) if hp.is_file() else ""
            if head_sha != str(baseline.get("sha256") or ""):
                commit_touched = True

    ws_dirty = subprocess.run(
        ["git", "diff", "--name-only", "--", HUMAN_REL],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--", HUMAN_REL],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    ws_changed = bool((ws_dirty.stdout or "").strip() or (staged.stdout or "").strip())

    if not commit_touched and not (ws_changed and _needs_restore()):
        return [EnforceAction("skip", "ok")]

    ok, msg = restore_from_baseline(repo_root)
    if not ok:
        kind = "commit_revert" if commit_touched else "ws_revert"
        return [EnforceAction(kind, f"FAILED: {msg}")]

    enf_kind = "commit_revert" if commit_touched else "ws_revert"
    actions.append(EnforceAction(enf_kind, msg))

    commit_env = (
        dict(env_override)
        if env_override is not None
        else {**os.environ, **_DEFAULT_G_HUMAN_COMMIT_ENV}
    )

    if commit_touched or ws_changed:
        subprocess.run(
            ["git", "add", HUMAN_REL],
            cwd=str(repo_root),
            check=True,
            env=commit_env,
        )
        dq = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=str(repo_root),
            env=commit_env,
        )
        if dq.returncode != 0:
            subprocess.run(
                [
                    "git",
                    "commit",
                    "-m",
                    "chore(g-human): revert agent HUMAN_GUIDANCE drift\n\n"
                    f"auto-run run={run}; baseline restore.",
                ],
                cwd=str(repo_root),
                check=True,
                env=commit_env,
            )
    return actions


def batch_hint_lines(repo_root: Path) -> list[str]:
    """Soft WARN lines for human-guidance edits; empty if nothing notable."""
    root = repo_root.resolve()
    lines: list[str] = []
    baseline = load_baseline(root)
    hp = human_path(root)

    if baseline is not None:
        lines.append(
            "[human-guidance] WARN: 检测到 auto-run 批次基线 "
            "(saved/.human-guidance-baseline.json)。"
        )
        if hp.is_file() and file_sha256(hp) != str(baseline.get("sha256") or ""):
            lines.append(
                "[human-guidance] WARN: HUMAN_GUIDANCE.md 相对 baseline 已 drift；"
                "后续 auto-run 轮次 G-HUMAN 会拦截 Agent。"
            )

    runtime = detect_runtime_activity(root)
    if runtime.auto_run_active and runtime.auto_run_pid is not None:
        lines.append(
            "[human-guidance] WARN: 检测到 auto-run batch 活跃"
            f"（pid={runtime.auto_run_pid}）。"
        )
    elif runtime.auto_run_active:
        lines.append("[human-guidance] WARN: 检测到 auto-run batch 活跃。")

    if runtime.train_active:
        detail = runtime.train_detail
        lines.append(
            "[human-guidance] WARN: 检测到训练可能进行中"
            + (f"（{detail}）" if detail else "")
            + "。"
        )

    if lines:
        lines.extend(
            [
                "[human-guidance] 改路线图前推荐：停 ./auto-nn-run.sh → 改文件 → "
                "validate → git commit → 重开 batch（新 baseline）。",
                "[human-guidance] auto-run 活跃时禁止 refresh-human-guidance-baseline.sh；"
                "须停 batch 后恢复文件。",
            ]
        )
    return lines


def check_human_guidance(repo_root: Path) -> str | None:
    """Return error message if drift; None if OK or skip."""
    if os.environ.get("NN_GUARD_HUMAN_GUIDANCE", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return None
    root = repo_root.resolve()
    hp = human_path(root)
    if not hp.is_file():
        return None
    baseline = load_baseline(root)
    if not baseline:
        return None
    current = file_sha256(hp)
    expected = str(baseline.get("sha256") or "")
    if not expected:
        return None
    if current == expected:
        return None
    gh = str(baseline.get("git_head") or "").strip()
    checkout_ref = gh if gh else "HEAD"
    return (
        "HUMAN_GUIDANCE.md 相对批次基线已变更（仅人可改）。"
        "停 ./auto-nn-run.sh → "
        f"git checkout {checkout_ref} -- HUMAN_GUIDANCE.md "
        "（或从备份恢复）→ 确认 sha 与 saved/.human-guidance-baseline.json 一致 → 重开 batch。"
        "auto-run 活跃时禁止 refresh-human-guidance-baseline.sh。"
    )


def doctor_status(repo_root: Path) -> tuple[str, str]:
    """Return (level, message) for nn-doctor: PASS/WARN/SKIP."""
    install_err = verify_g_human_install(repo_root)
    if install_err:
        return "WARN", install_err

    root = repo_root.resolve()
    hp = human_path(root)
    if not hp.is_file():
        return "SKIP", "无 HUMAN_GUIDANCE.md"
    baseline = load_baseline(root)
    if not baseline:
        return "WARN", "无 saved/.human-guidance-baseline.json（未跑 auto-run batch？）"
    if file_sha256(hp) != str(baseline.get("sha256") or ""):
        gh = str(baseline.get("git_head") or "").strip()
        checkout_ref = gh if gh else "HEAD"
        return (
            "WARN",
            "HUMAN 相对 baseline drift — 停 ./auto-nn-run.sh → "
            f"git checkout {checkout_ref} -- HUMAN_GUIDANCE.md "
            "（禁止 refresh-human-guidance-baseline.sh；轮末 post-round-enforce "
            "会 revert Agent commit）",
        )
    n = baseline.get("n_phases", "?")
    return "PASS", f"baseline OK（n_phases={n}）"
