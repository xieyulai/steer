"""改题待办（e_feedback）jsonl 存储：追加 / 去重 / 决议 / 计数 / 摘要。

路径：``_runs/analysis/e_feedback.jsonl``。写入经 tempfile + os.replace。
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REL_PATH = Path("_runs") / "analysis" / "e_feedback.jsonl"
KIND_OK = frozenset({"shout", "executed"})
RESOLVE_OK = frozenset({"adopted", "deferred", "rejected"})
_ID_RE = re.compile(r"^E(\d{8})_(\d{3})$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _today_yyyymmdd() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y%m%d")


def feedback_path(repo_root: Path | str) -> Path:
    return Path(repo_root).resolve() / REL_PATH


def _blank(s: str | None) -> bool:
    return not (s or "").strip()


def _norm_proposed(s: str | None) -> str:
    return (s or "").strip().lower()


def load_records(repo_root: Path | str) -> list[dict[str, Any]]:
    p = feedback_path(repo_root)
    if not p.is_file():
        return []
    out: list[dict[str, Any]] = []
    for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        text = line.strip()
        if not text:
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"e_feedback.jsonl L{n}: 坏 JSON ({e})") from e
        if not isinstance(obj, dict):
            raise ValueError(f"e_feedback.jsonl L{n}: 须为 object")
        out.append(obj)
    return out


def _atomic_write(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records)
    fd, tmp_name = tempfile.mkstemp(
        prefix=".e_feedback_",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _next_id(records: list[dict[str, Any]], day: str) -> str:
    max_n = 0
    for r in records:
        m = _ID_RE.match(str(r.get("id") or ""))
        if not m:
            continue
        if m.group(1) != day:
            continue
        max_n = max(max_n, int(m.group(2)))
    return f"E{day}_{max_n + 1:03d}"


def append_event(
    repo_root: Path | str,
    *,
    kind: str,
    proposed: str,
    why_abcd_insufficient: str,
    ask: str,
    quote: str,
    experiment: str,
    source: str,
    round_hint: int | None,
) -> dict[str, Any]:
    if kind not in KIND_OK:
        raise ValueError(f"kind 须为 {sorted(KIND_OK)}，得 {kind!r}")
    if kind == "shout" and (
        _blank(proposed) or _blank(why_abcd_insufficient) or _blank(ask)
    ):
        return {"skipped": "incomplete"}

    records = load_records(repo_root)
    now = _now_iso()
    prop_key = _norm_proposed(proposed)
    # pending：同主张不新开。驳回/留下：同主张不再提。搁置不当禁令，允许再开一条 pending。
    blocked_skip: dict[str, Any] | None = None
    for i, existing in enumerate(records):
        if existing.get("kind") != kind:
            continue
        if _norm_proposed(existing.get("proposed")) != prop_key:
            continue
        status = (existing.get("resolution") or {}).get("status")
        if status == "pending":
            existing["last_seen_ts"] = now
            records[i] = existing
            _atomic_write(feedback_path(repo_root), records)
            return existing
        if status in ("rejected", "adopted") and blocked_skip is None:
            existing["last_seen_ts"] = now
            records[i] = existing
            blocked_skip = {"skipped": status, "id": existing.get("id")}
    if blocked_skip is not None:
        _atomic_write(feedback_path(repo_root), records)
        return blocked_skip

    day = _today_yyyymmdd()
    rec: dict[str, Any] = {
        "id": _next_id(records, day),
        "kind": kind,
        "ts": now,
        "experiment": experiment,
        "round_hint": round_hint,
        "proposed": proposed,
        "why_abcd_insufficient": why_abcd_insufficient,
        "ask": ask,
        "quote": quote,
        "source": source,
        "resolution": {
            "status": "pending",
            "by": None,
            "ts": None,
            "note": None,
        },
    }
    records.append(rec)
    _atomic_write(feedback_path(repo_root), records)
    return rec


def resolve(
    repo_root: Path | str,
    id: str,
    status: str,
    *,
    note: str = "",
    by: str = "human",
) -> dict[str, Any]:
    if status not in RESOLVE_OK:
        raise ValueError(f"status 须为 {sorted(RESOLVE_OK)}，得 {status!r}")
    records = load_records(repo_root)
    for i, rec in enumerate(records):
        if rec.get("id") != id:
            continue
        resolution = dict(rec.get("resolution") or {})
        resolution["status"] = status
        resolution["by"] = by
        resolution["ts"] = _now_iso()
        resolution["note"] = note
        rec = dict(rec)
        rec["resolution"] = resolution
        records[i] = rec
        _atomic_write(feedback_path(repo_root), records)
        return rec
    raise KeyError(f"e_feedback id 不存在: {id}")


def pending_count(repo_root: Path | str) -> int:
    n = 0
    for rec in load_records(repo_root):
        status = (rec.get("resolution") or {}).get("status")
        if status == "pending":
            n += 1
    return n


def summarize(repo_root: Path | str) -> str:
    records = load_records(repo_root)
    if not records:
        return "e_feedback: (无)"
    pending = 0
    deferred = 0
    for rec in records:
        status = (rec.get("resolution") or {}).get("status")
        if status == "pending":
            pending += 1
        elif status == "deferred":
            deferred += 1
    return f"e_feedback: pending={pending} deferred={deferred}"


def shout_proposed_for_status(repo_root: Path | str, status: str) -> list[str]:
    """指定决议态下 shout 的 proposed 原文（去空白；供反思 prompt 注入）。"""
    out: list[str] = []
    for rec in load_records(repo_root):
        if rec.get("kind") != "shout":
            continue
        if (rec.get("resolution") or {}).get("status") != status:
            continue
        text = str(rec.get("proposed") or "").strip()
        if text:
            out.append(text)
    return out


def format_shout_resolution_hint(repo_root: Path | str) -> str:
    """Phase 1 注入：三选一都不改题；驳回/留下禁再提；搁置可再提。"""
    rej = shout_proposed_for_status(repo_root, "rejected")
    adp = shout_proposed_for_status(repo_root, "adopted")
    dfr = shout_proposed_for_status(repo_root, "deferred")
    lines = [
        "改题人决议（留下/搁置/驳回之后 Agent 仍不得改 contract / 题面）：",
    ]
    if rej:
        lines.append("- 已驳回、禁止再提类似主张：" + "；".join(rej))
    if adp:
        lines.append(
            "- 已留下、只可当建议复述、禁止再三选一、禁止改代码：" + "；".join(adp)
        )
    if dfr:
        lines.append("- 已搁置、不当禁令、若仍主张可再提：" + "；".join(dfr))
    if not (rej or adp or dfr):
        lines.append(
            "- 尚无人决议。三选一无论哪项都不得改题面；驳回后勿再提类似；"
            "留下只给建议；搁置当没发生、下次该提还提。"
        )
    return "\n".join(lines)


def shout_fields_from_reflect_payload(payload: dict) -> tuple[str, str, str]:
    """返回 (proposed, why, ask)；缺键当空串。禁止用正则扫 'Tier E'。"""
    if not isinstance(payload, dict):
        return "", "", ""
    return (
        str(payload.get("e_proposed") or ""),
        str(payload.get("e_why_abcd") or ""),
        str(payload.get("e_ask") or ""),
    )


def contract_file_map(contract_root: Path | str) -> dict[str, str]:
    """``contract/`` 树 → 相对路径→正文（忽略 pyc / __pycache__）。"""
    root = Path(contract_root)
    out: dict[str, str] = {}
    if not root.is_dir():
        return out
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        parts = p.relative_to(root).parts
        if any(part == "__pycache__" or part.endswith(".pyc") for part in parts):
            continue
        if p.suffix == ".pyc":
            continue
        rel = p.relative_to(root).as_posix()
        try:
            out[rel] = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return out


def contract_changed(
    prev_exp_dir: Path | str,
    cur_exp_dir: Path | str,
    *,
    live_contract: Path | str | None = None,
) -> bool:
    """本轮 vs 上一有效轮 ``code_snapshot/contract``（或缺则 live ``contract/``）是否有路径/内容变化。

    不喂给 A–D 打格；仅供改题落地（executed）判定。
    """
    prev_map = contract_file_map(Path(prev_exp_dir) / "code_snapshot" / "contract")
    cur_snap = Path(cur_exp_dir) / "code_snapshot" / "contract"
    if cur_snap.is_dir():
        cur_map = contract_file_map(cur_snap)
    elif live_contract is not None:
        cur_map = contract_file_map(live_contract)
    else:
        cur_map = {}
    if not prev_map or not cur_map:
        return False
    return prev_map != cur_map


def try_append_shout_from_reflect(
    repo_root: Path | str,
    payload: dict,
    *,
    experiment: str,
    round_hint: int | None,
    quote: str = "",
) -> dict[str, Any]:
    proposed, why, ask = shout_fields_from_reflect_payload(payload)
    return append_event(
        repo_root,
        kind="shout",
        proposed=proposed,
        why_abcd_insufficient=why,
        ask=ask,
        quote=(quote or "")[:200],
        experiment=experiment,
        source="reflect",
        round_hint=round_hint,
    )


def try_append_executed_on_relaunch(
    repo_root: Path | str,
    *,
    relaunch_env: str | None,
    prev_exp_dir: Path | str | None,
    cur_exp_dir: Path | str | None,
    experiment: str,
    round_hint: int | None = None,
) -> dict[str, Any] | None:
    """``NN_RELAUNCH`` 非空且 contract 有 diff → 记 executed；不改 TSV 格子。"""
    if not (relaunch_env or "").strip():
        return None
    if prev_exp_dir is None or cur_exp_dir is None:
        return None
    root = Path(repo_root).resolve()
    if not contract_changed(
        prev_exp_dir,
        cur_exp_dir,
        live_contract=root / "contract",
    ):
        return None
    return append_event(
        root,
        kind="executed",
        proposed="contract diff",
        why_abcd_insufficient="relaunch",
        ask="already",
        quote="",
        experiment=experiment,
        source="reflect",
        round_hint=round_hint,
    )
