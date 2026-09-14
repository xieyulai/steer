#!/usr/bin/env python3
"""Align ``_runs/results.jsonl`` with ``_runs/results.tsv`` (TSV is source of truth)."""
from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# Same directory import when run as scripts/sync_ledger.py
from regen_results_tsv import _load_contract, _read_tsv_rows  # noqa: TID252

SCENARIO_ID_COLUMN = "scenario_id"


def _git_head_short(repo_root: Path) -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=8,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "nogit"


def _clean_metrics_dict(metrics: dict[str, Any]) -> dict[str, object]:
    clean: dict[str, object] = {}
    for k, v in sorted(metrics.items()):
        if isinstance(v, float):
            if math.isnan(v) or math.isinf(v):
                continue
            clean[k] = round(v, 6)
        else:
            clean[k] = v
    return clean


def _escape_tsv_field(s: str) -> str:
    return s.replace("\t", " ").replace("\r", " ").replace("\n", " ")


def _normalize_exp_dir(repo_root: Path, raw: str) -> str:
    """v2.7.4: exp_dir 归一为相对 repo_root(换机不断链)。

    - 绝对路径在 repo 内 → 相对化; 不在 repo 内 → 保留绝对(跨 repo 数据)
    - 已相对 → 原样(幂等)
    - 之前(v2.7.3-)强制 resolve 成绝对 → sync 一跑就把 v2.7.4 相对数据改回绝对,
      故反转方向。
    """
    raw = raw.strip()
    if not raw:
        return ""
    jp = Path(raw).expanduser()
    try:
        if not jp.is_absolute():
            return str(jp)  # 已相对,幂等
        rel = jp.resolve().relative_to(repo_root.resolve())
        return str(rel)
    except (ValueError, OSError):
        return str(jp) if jp.is_absolute() else str((repo_root / jp))


def _parse_recorded_at(tsv_timestamp: str) -> str:
    cell = (tsv_timestamp or "").strip()
    if not cell:
        return datetime.now(timezone.utc).isoformat()
    try:
        iso = datetime.fromisoformat(cell.replace("Z", "+00:00"))
        if iso.tzinfo is None:
            iso = iso.replace(tzinfo=timezone.utc)
        else:
            iso = iso.astimezone(timezone.utc)
        # 与 naive datetime.isoformat()+00:00 Z 等价风格
        return iso.isoformat().replace("+00:00", "Z")
    except ValueError:
        return datetime.now(timezone.utc).isoformat()


def _load_results_json(repo_root: Path, exp_raw: str) -> dict[str, Any] | None:
    raw = exp_raw.strip()
    if not raw:
        return None
    jp = Path(raw)
    if not jp.is_absolute():
        jp = (repo_root / jp).resolve()
    else:
        jp = jp.resolve()
    rf = jp / "results.json"
    if not rf.is_file():
        return None
    try:
        data = json.loads(rf.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _elapsed_from_row_and_results(
    row: dict[str, str],
    payload: dict[str, Any],
) -> float:
    pj = payload.get("elapsed_sec")
    if isinstance(pj, (int, float)):
        return float(pj)
    rs = row.get("elapsed_sec", "").strip()
    if rs:
        try:
            return float(rs)
        except ValueError:
            pass
    return 0.0


def _metrics_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    m = payload.get("metrics")
    return m if isinstance(m, dict) else {}


def _build_jsonl_record(
    *,
    repo_root: Path,
    metric_key: str,
    row: dict[str, str],
    payload: dict[str, Any],
) -> dict[str, Any]:
    ex = _escape_tsv_field((row.get("experiment") or "").strip())
    if not ex and row.get("exp_dir"):
        ex = _escape_tsv_field(Path(row["exp_dir"]).name)

    sid = str(row.get(SCENARIO_ID_COLUMN, "") or "").strip()
    exp_abs = _normalize_exp_dir(repo_root, str(row.get("exp_dir", "") or ""))

    elapsed = _elapsed_from_row_and_results(row, payload)
    metrics_raw = _metrics_from_payload(payload)
    if not metrics_raw and payload:
        metrics_raw = {k: v for k, v in payload.items() if k not in ("elapsed_sec", "metrics")}

    git_c = (row.get("git_commit") or "").strip() or _git_head_short(repo_root)

    recorded = _parse_recorded_at(row.get("timestamp", ""))

    record: dict[str, Any] = {
        "recorded_at": recorded,
        "schema_version": 2 if sid else 1,
        "kind": "train_end",
        "metric_key": metric_key,
        "experiment": ex or "unnamed",
        "git_commit": git_c,
        "exp_dir": exp_abs,
        "elapsed_sec": round(float(elapsed), 2),
        "metrics": _clean_metrics_dict(metrics_raw),
    }
    if sid:
        record[SCENARIO_ID_COLUMN] = sid
    desc = (row.get("description") or "").strip()
    if desc:
        record["description"] = _escape_tsv_field(desc)
    notes = (row.get("notes") or "").strip()
    if notes:
        record["notes"] = notes

    return record


def _normalized_exp_from_jsonl(repo_root: Path, raw: str) -> str:
    """v2.7.4: jsonl exp_dir 归一逻辑与 TSV 侧 _normalize_exp_dir 一致(相对 repo_root),
    保证 TSV↔jsonl 配对(need[resolved])格式对齐。"""
    return _normalize_exp_dir(repo_root, raw)


def _count_old_orphans(repo_root: Path, existing_lines: list[str], new_exp_dirs: Counter[str]) -> int:
    """旧 jsonl 中无法与「将由 TSV 重建」的记录逐条配对消耗的行数。"""
    need = Counter(new_exp_dirs)
    orphaned = 0
    for line in existing_lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            orphaned += 1
            continue
        if not isinstance(obj, dict):
            orphaned += 1
            continue
        resolved = _normalized_exp_from_jsonl(repo_root, str(obj.get("exp_dir", "") or ""))
        if not resolved:
            orphaned += 1
            continue
        if need[resolved] > 0:
            need[resolved] -= 1
        else:
            orphaned += 1
    return orphaned


def _candidate_exp_dirs_from_round_decision(repo_root: Path) -> list[str]:
    p = repo_root / "_runs" / "round_decision.json"
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    fin = data.get("finalize_round")
    if not isinstance(fin, dict):
        return []
    raw_dirs = fin.get("candidate_exp_dirs")
    if not isinstance(raw_dirs, list):
        return []
    out: list[str] = []
    for d in raw_dirs:
        norm = _normalize_exp_dir(repo_root, str(d))
        if norm:
            out.append(norm)
    return out


def sync_ledger(
    repo_root: Path,
    *,
    tsv_rel: str = "_runs/results.tsv",
    jsonl_rel: str = "_runs/results.jsonl",
    dry_run: bool = True,
    backup_jsonl: bool = True,
) -> dict[str, int]:
    repo_root = repo_root.resolve()
    tsv_path = repo_root / tsv_rel
    jsonl_path = repo_root / jsonl_rel

    _, rows = _read_tsv_rows(tsv_path)
    jsonl_before = 0
    raw_old_lines: list[str] = []
    if jsonl_path.is_file():
        raw_old_lines = [ln for ln in jsonl_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        jsonl_before = len(raw_old_lines)

    metric_key = str(_load_contract(repo_root).metric_key)

    built: list[dict[str, Any]] = []
    missing_skips = 0
    warn_paths: list[str] = []

    exp_counter: Counter[str] = Counter()
    for row in rows:
        exp_raw = (row.get("exp_dir") or "").strip()
        payload = _load_results_json(repo_root, exp_raw)
        if payload is None:
            missing_skips += 1
            if exp_raw:
                warn_paths.append(exp_raw)
            continue
        rec = _build_jsonl_record(repo_root=repo_root, metric_key=metric_key, row=row, payload=payload)
        built.append(rec)
        ed = rec.get("exp_dir", "")
        if isinstance(ed, str) and ed:
            exp_counter[ed] += 1

    for exp_abs in _candidate_exp_dirs_from_round_decision(repo_root):
        if exp_counter.get(exp_abs, 0) > 0:
            continue
        payload = _load_results_json(repo_root, exp_abs)
        if payload is None:
            continue
        row = {
            "experiment": Path(exp_abs).name,
            "exp_dir": exp_abs,
            "description": "sync_ledger round_decision candidate",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "git_commit": _git_head_short(repo_root),
        }
        rec = _build_jsonl_record(
            repo_root=repo_root, metric_key=metric_key, row=row, payload=payload,
        )
        built.append(rec)
        exp_counter[exp_abs] += 1

    orphans_dropped = _count_old_orphans(repo_root, raw_old_lines, exp_counter)
    jsonl_after = len(built)

    print(
        json.dumps(
            {
                "tsv_rows": len(rows),
                "jsonl_before": jsonl_before,
                "jsonl_after": jsonl_after,
                "orphans_dropped": orphans_dropped,
                "missing_built": missing_skips,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    if dry_run:
        for p in warn_paths[:50]:
            print(f"[WARN] dry-run：TSV 行 exp_dir 无 results.json，将跳过写入 jsonl: {p}", file=sys.stderr)
        if len(warn_paths) > 50:
            print(f"[WARN] ... 另有 {len(warn_paths) - 50} 条同上", file=sys.stderr)
        return {
            "tsv_rows": len(rows),
            "jsonl_before": jsonl_before,
            "jsonl_after": jsonl_after,
            "orphans_dropped": orphans_dropped,
            "missing_built": missing_skips,
        }

    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    if backup_jsonl and jsonl_path.is_file() and jsonl_path.stat().st_size > 0:
        bak = jsonl_path.with_suffix(jsonl_path.suffix + ".bak")
        shutil.copy2(jsonl_path, bak)
        print(f"已备份 jsonl -> {bak}", file=sys.stderr, flush=True)

    with jsonl_path.open("w", encoding="utf-8") as f:
        for rec in built:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    for p in warn_paths[:50]:
        print(f"[WARN] TSV 行 exp_dir 无 results.json，已跳过: {p}", file=sys.stderr)
    if len(warn_paths) > 50:
        print(f"[WARN] ... 另有 {len(warn_paths) - 50} 条同上", file=sys.stderr)

    return {
        "tsv_rows": len(rows),
        "jsonl_before": jsonl_before,
        "jsonl_after": jsonl_after,
        "orphans_dropped": orphans_dropped,
        "missing_built": missing_skips,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", type=Path, default=Path("."), help="项目根目录")
    ap.add_argument("--tsv", default="_runs/results.tsv", help="相对 repo-root 的 TSV 路径")
    ap.add_argument("--jsonl", default="_runs/results.jsonl", help="相对 repo-root 的 JSONL 路径")
    mx = ap.add_mutually_exclusive_group(required=False)
    mx.add_argument(
        "--dry-run",
        action="store_true",
        help="显式预览（省略时亦为默认预览，仅在不与 --apply 同时出现时有效）",
    )
    mx.add_argument("--apply", action="store_true", help="实际写入 JSONL")
    ap.add_argument("--no-backup", action="store_true", help="--apply 时不备份既有 jsonl")
    args = ap.parse_args()

    repo = args.repo_root.resolve()
    dry = not bool(args.apply)

    sync_ledger(
        repo,
        tsv_rel=args.tsv,
        jsonl_rel=args.jsonl,
        dry_run=dry,
        backup_jsonl=not args.no_backup,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
