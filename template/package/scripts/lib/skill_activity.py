"""统一技能活动 log — append-only `.auto-nn/skill-activity.jsonl`。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOG_NAME = "skill-activity.jsonl"
SCHEMA_VERSION = 1
CONFIG_SECTION = "safety"
CONFIG_KEY = "skill_activity_log"


def activity_log_path(repo_root: Path) -> Path:
    return repo_root.resolve() / ".auto-nn" / LOG_NAME


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def is_enabled(repo_root: Path) -> bool:
    """Read safety.skill_activity_log; default True if missing or unreadable."""
    cfg_path = repo_root.resolve() / "nn-config.yaml"
    if not cfg_path.is_file():
        return True
    try:
        import yaml

        cfg = yaml.safe_load(_read_text(cfg_path)) or {}
        section = cfg.get(CONFIG_SECTION) or {}
        raw = section.get(CONFIG_KEY)
        if raw is None:
            return True
        return bool(raw)
    except Exception:
        return True


def append_activity(
    repo_root: Path,
    *,
    skill: str,
    phase: str,
    summary: str = "",
    lock: str = "",
    user: str = "",
    ask: str = "",
    options: str = "",
    artifacts: list[str] | None = None,
    session_id: str = "",
    force: bool = False,
) -> bool:
    """Append one JSONL line. Returns False if logging disabled (no write)."""
    if not force and not is_enabled(repo_root):
        return False
    path = activity_log_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "ts": _now_iso(),
        "skill": skill.strip(),
        "phase": phase.strip(),
        "summary": summary.strip(),
        "lock": lock.strip(),
        "user": user.strip(),
        "ask": ask.strip(),
        "options": options.strip(),
        "artifacts": [a.strip() for a in (artifacts or []) if a.strip()],
        "session_id": session_id.strip(),
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return True


def count_entries(repo_root: Path) -> int:
    path = activity_log_path(repo_root)
    if not path.is_file():
        return 0
    n = 0
    for line in _read_text(path).splitlines():
        if line.strip():
            n += 1
    return n


def read_entries(repo_root: Path, *, limit: int = 50) -> list[dict[str, Any]]:
    path = activity_log_path(repo_root)
    if not path.is_file():
        return []
    lines = [ln for ln in _read_text(path).splitlines() if ln.strip()]
    tail = lines[-limit:] if limit > 0 else lines
    out: list[dict[str, Any]] = []
    for line in tail:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def format_recent_markdown(repo_root: Path, *, limit: int = 15) -> str:
    entries = read_entries(repo_root, limit=limit)
    if not entries:
        return "（无 skill-activity 记录）"
    lines = ["## 自上次以来 · 技能活动（.auto-nn/skill-activity.jsonl）", ""]
    for e in entries:
        skill = e.get("skill", "?")
        phase = e.get("phase", "?")
        summary = e.get("summary") or e.get("lock") or "—"
        ts = e.get("ts", "")
        lines.append(f"- `{ts}` **{skill}** ({phase}) — {summary}")
    return "\n".join(lines)


def reset_log(repo_root: Path) -> None:
    """Truncate activity log (factory greenfield)."""
    path = activity_log_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")
