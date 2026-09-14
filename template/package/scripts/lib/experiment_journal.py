"""Experiment journal：双指针（facts / analyse）+ entries FIFO。"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.ledger_anchor import focus_scenario_id
from lib.run_ledger_summary import (
    _float_cell,
    metric_key,
    round_decision_status,
    tsv_rows,
)

JOURNAL_BASENAME = "experiment_journal.json"
SCHEMA_VERSION = 1
_GIT_SCOPE_PATHS = ("train.py", "workspace/")
_DEFAULT_MAX_ENTRIES = 200
_NOTE_MAX_LEN = 500


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def journal_path(repo_root: Path) -> Path:
    return repo_root.resolve() / "saved" / JOURNAL_BASENAME


def _journal_max_entries(repo_root: Path) -> int:
    cfg_path = repo_root / "nn-config.yaml"
    if not cfg_path.is_file():
        return _DEFAULT_MAX_ENTRIES
    try:
        import yaml

        cfg = yaml.safe_load(_read_text(cfg_path)) or {}
        raw = (cfg.get("agent") or {}).get("journal_max_entries")
        if raw is not None:
            return max(1, int(raw))
    except Exception:
        pass
    return _DEFAULT_MAX_ENTRIES


def empty_journal() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "facts": {
            "tsv_row_count": 0,
            "last_experiment": "",
            "last_git_head": "",
            "last_scenario_id": "",
            "updated_at": "",
        },
        "analyse": {
            "tsv_row_count": 0,
            "git_head": "",
            "focus_scenario_id": "",
            "updated_at": "",
            "last_recommendation": None,
        },
        "reflect": None,
        "entries": [],
    }


def read_journal(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        return empty_journal()
    try:
        data = json.loads(_read_text(p))
        if not isinstance(data, dict):
            return empty_journal()
    except Exception:
        return empty_journal()
    base = empty_journal()
    base["schema_version"] = int(data.get("schema_version") or SCHEMA_VERSION)
    for section in ("facts", "analyse"):
        if isinstance(data.get(section), dict):
            base[section].update(data[section])
    entries = data.get("entries")
    base["entries"] = entries if isinstance(entries, list) else []
    reflect = data.get("reflect")
    if isinstance(reflect, dict):
        base["reflect"] = reflect
    elif reflect is None:
        base["reflect"] = None
    return base


def write_journal(path: Path | str, data: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, p)


def _data_rows(repo_root: Path) -> list[dict[str, str]]:
    return [r for r in tsv_rows(repo_root) if r.get("experiment") != "preflight_check"]


def _git_is_repo(repo_root: Path) -> bool:
    return (repo_root / ".git").exists()


def _git_head_short(repo_root: Path) -> str:
    if not _git_is_repo(repo_root):
        return ""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            return (proc.stdout or "").strip()
    except OSError:
        pass
    return ""


def _git_diff_name_only(repo_root: Path, since: str, until: str) -> list[str]:
    if not since or not until or not _git_is_repo(repo_root):
        return []
    try:
        proc = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "diff",
                "--name-only",
                since,
                until,
                "--",
                *_GIT_SCOPE_PATHS,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return []
        return [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    except OSError:
        return []


def _row_decision(row: dict[str, str]) -> str:
    notes = str(row.get("notes") or "").strip()
    if notes:
        return notes
    decision = str(row.get("decision") or row.get("round_decision") or "").strip()
    return decision or "-"


def _cap_entries(entries: list[dict[str, Any]], max_entries: int) -> list[dict[str, Any]]:
    if len(entries) <= max_entries:
        return entries
    return entries[-max_entries:]


def _build_round_entry(
    repo_root: Path,
    *,
    note: str | None,
    prev_git_head: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    rows = _data_rows(repo_root)
    mk = metric_key(repo_root)
    git_head = _git_head_short(repo_root)
    if not rows:
        facts = {
            "tsv_row_count": 0,
            "last_experiment": "",
            "last_git_head": git_head,
            "last_scenario_id": "",
            "updated_at": _utc_now_iso(),
        }
        entry: dict[str, Any] = {
            "ts": facts["updated_at"],
            "kind": "round",
            "experiment": "",
            "decision": "-",
            "metric_key": mk,
            "metric_value": None,
            "git_head": git_head,
            "changed_files": [],
            "scenario_id": "",
        }
        if note:
            entry["note"] = note[:_NOTE_MAX_LEN]
        return facts, entry

    last = rows[-1]
    experiment = str(last.get("experiment") or "").strip()
    scenario_id = str(last.get("scenario_id") or "").strip() or "default"
    metric_value = _float_cell(last, mk)
    decision = round_decision_status(repo_root) or _row_decision(last)
    changed = _git_diff_name_only(repo_root, prev_git_head, git_head) if prev_git_head else []

    facts = {
        "tsv_row_count": len(rows),
        "last_experiment": experiment,
        "last_git_head": git_head,
        "last_scenario_id": scenario_id,
        "updated_at": _utc_now_iso(),
    }
    entry = {
        "ts": facts["updated_at"],
        "kind": "round",
        "experiment": experiment,
        "decision": decision,
        "metric_key": mk,
        "metric_value": metric_value,
        "git_head": git_head,
        "changed_files": changed,
        "scenario_id": scenario_id,
    }
    if note:
        entry["note"] = note[:_NOTE_MAX_LEN]
    return facts, entry


def append_round(
    repo_root: Path | str,
    *,
    apply: bool = False,
    note: str | None = None,
) -> dict[str, Any]:
    """更新 facts 并追加 kind=round entry；不修改 analyse。"""
    root = Path(repo_root).resolve()
    path = journal_path(root)
    journal = read_journal(path)
    prev_analyse = dict(journal.get("analyse") or {})
    prev_git = str((journal.get("facts") or {}).get("last_git_head") or "").strip()

    facts, entry = _build_round_entry(root, note=note, prev_git_head=prev_git)
    journal["facts"] = facts
    journal["analyse"] = prev_analyse
    entries = list(journal.get("entries") or [])
    entries.append(entry)
    journal["entries"] = _cap_entries(entries, _journal_max_entries(root))

    result = {
        "path": str(path),
        "applied": False,
        "facts": facts,
        "entry": entry,
        "analyse_unchanged": prev_analyse,
    }
    if apply:
        write_journal(path, journal)
        result["applied"] = True
    return result


def append_analyse(
    repo_root: Path | str,
    *,
    apply: bool = False,
    summary: str = "",
    recommendation_json: dict[str, Any] | str | None = None,
) -> dict[str, Any]:
    """更新 analyse 游标并追加 kind=analyse entry；不修改 facts。"""
    root = Path(repo_root).resolve()
    path = journal_path(root)
    journal = read_journal(path)
    prev_facts = dict(journal.get("facts") or {})

    rows = _data_rows(root)
    git_head = _git_head_short(root)
    focus = focus_scenario_id(root) or "default"
    ts = _utc_now_iso()

    rec: dict[str, Any] | None = None
    if isinstance(recommendation_json, str) and recommendation_json.strip():
        try:
            parsed = json.loads(recommendation_json)
            rec = parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            rec = None
    elif isinstance(recommendation_json, dict):
        rec = recommendation_json

    analyse = {
        "tsv_row_count": len(rows),
        "git_head": git_head,
        "focus_scenario_id": focus,
        "updated_at": ts,
        "last_recommendation": rec,
    }
    entry: dict[str, Any] = {
        "ts": ts,
        "kind": "analyse",
        "tsv_row_count": len(rows),
        "git_head": git_head,
        "focus_scenario_id": focus,
    }
    if summary:
        entry["summary"] = summary.strip()
    if rec:
        entry["last_recommendation"] = rec

    journal["facts"] = prev_facts
    journal["analyse"] = analyse
    entries = list(journal.get("entries") or [])
    entries.append(entry)
    journal["entries"] = _cap_entries(entries, _journal_max_entries(root))

    result = {
        "path": str(path),
        "applied": False,
        "analyse": analyse,
        "entry": entry,
        "facts_unchanged": prev_facts,
    }
    if apply:
        write_journal(path, journal)
        result["applied"] = True
    return result


def reset_journal_for_runs_clear(
    repo_root: Path | str,
    *,
    keep_analyse: bool = False,
    apply: bool = False,
) -> dict[str, Any]:
    """C3 runs+journal：entries=[]，facts 对齐当前 TSV；可选保留 analyse 游标。"""
    root = Path(repo_root).resolve()
    path = journal_path(root)
    prev = read_journal(path) if path.is_file() else empty_journal()
    prev_analyse = dict(prev.get("analyse") or {})

    rows = _data_rows(root)
    git_head = _git_head_short(root)
    last = rows[-1] if rows else {}
    scenario_id = str(last.get("scenario_id") or "").strip()
    facts = {
        "tsv_row_count": len(rows),
        "last_experiment": str(last.get("experiment") or "").strip(),
        "last_git_head": git_head,
        "last_scenario_id": scenario_id or ("default" if rows else ""),
        "updated_at": _utc_now_iso(),
    }

    journal = empty_journal()
    journal["facts"] = facts
    journal["entries"] = []
    if keep_analyse:
        journal["analyse"] = prev_analyse

    result: dict[str, Any] = {
        "path": str(path),
        "applied": False,
        "facts": facts,
        "keep_analyse": keep_analyse,
    }
    if apply:
        write_journal(path, journal)
        result["applied"] = True
    return result


def load_analyse_cursor(repo_root: Path | str) -> int | None:
    """供 MA-3 / analyse_delta 读取 analyse.tsv_row_count；无 journal 文件时返回 None。"""
    root = Path(repo_root).resolve()
    path = journal_path(root)
    if not path.is_file():
        return None
    journal = read_journal(path)
    raw = (journal.get("analyse") or {}).get("tsv_row_count")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def write_reflect_last_consumed(
    repo_root: Path | str,
    *,
    reflect_id: str,
    wall_short: str,
    suggest_one_liner: str,
    tier_hint: str,
    detail_rel: str,
    consume_summary: str,
    apply: bool = True,
) -> dict[str, Any]:
    """mark_reflect_consumed 成功后写入 journal.reflect.last_consumed。"""
    root = Path(repo_root).resolve()
    path = journal_path(root)
    journal = read_journal(path)
    consumed = {
        "reflect_id": reflect_id,
        "consumed_at": _utc_now_iso(),
        "wall_short": wall_short,
        "suggest_one_liner": suggest_one_liner,
        "tier_hint": tier_hint,
        "detail_rel": detail_rel,
        "consume_summary": consume_summary,
    }
    journal["reflect"] = {
        "last_consumed": consumed,
        "last_pending_snapshot": None,
    }
    result: dict[str, Any] = {
        "path": str(path),
        "applied": False,
        "last_consumed": consumed,
    }
    if apply:
        write_journal(path, journal)
        result["applied"] = True
    return result


def write_reflect_pending_snapshot(
    repo_root: Path | str,
    *,
    reflect_id: str,
    suggest_one_liner: str,
    tier_hint: str,
    apply: bool = True,
) -> dict[str, Any]:
    """reflect.py 新 pending 写入 journal.reflect.last_pending_snapshot（不覆盖 last_consumed）。"""
    root = Path(repo_root).resolve()
    path = journal_path(root)
    journal = read_journal(path)
    snapshot = {
        "reflect_id": reflect_id,
        "suggest_one_liner": suggest_one_liner[:200],
        "tier_hint": tier_hint,
        "snapshot_at": _utc_now_iso(),
    }
    reflect = journal.get("reflect")
    if isinstance(reflect, dict):
        reflect = dict(reflect)
    else:
        reflect = {"last_consumed": None}
    reflect["last_pending_snapshot"] = snapshot
    journal["reflect"] = reflect
    result: dict[str, Any] = {
        "path": str(path),
        "applied": False,
        "last_pending_snapshot": snapshot,
    }
    if apply:
        write_journal(path, journal)
        result["applied"] = True
    return result


def clear_reflect_journal(
    repo_root: Path | str,
    *,
    apply: bool = True,
) -> dict[str, Any]:
    """C5 clear_reflect：重置 journal.reflect 为 null。"""
    root = Path(repo_root).resolve()
    path = journal_path(root)
    journal = read_journal(path)
    journal["reflect"] = None
    result: dict[str, Any] = {"path": str(path), "applied": False}
    if apply:
        write_journal(path, journal)
        result["applied"] = True
    return result
