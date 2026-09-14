#!/usr/bin/env python3
"""把探索空间格子写入台账 ``exploration_space`` 列（事后观察列，非 KEEP 输入）。

格式：``{TIER}-{depth}``，例 ``B-routine`` / ``C-different`` / ``B-novel``。
深度词 RDDN：routine / derived / different / novel。
``novel`` 优先取 ``saved/innovation_audit.json`` 的 ``attested_depth``
（different ⊕ 文献背书 ∧ P3+）；否则用创新判定 ``effective_depth`` / ``depth``。

用法::

  python3 scripts/sync_exploration_ledger.py              # 当前判定 → 对应 exp 行
  python3 scripts/sync_exploration_ledger.py --backfill-all  # 扫 fingerprint_history.jsonl
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path
from typing import Any

_DEPTH_OK = frozenset({"routine", "derived", "different", "novel"})
_DEPTH_ALIASES = {
    "extend": "derived",
    "formal-novel": "different",
    "r": "routine",
    "e": "derived",
    "d": "derived",
    "f": "different",
    "n": "novel",
}
_COL = "exploration_space"
_DIFFERENT_CELL_RE = re.compile(r"^([ABCD])-different$")


def should_apply_cell_update(old: str, val: str, *, backfill_all: bool) -> bool:
    """默认 sync 只允许已有 ``X-different`` → ``X-novel``；不填空格。

    ``--backfill-all`` 仍可写任意非空目标（迁后补账）。
    """
    old_s = (old or "").strip()
    val_s = (val or "").strip()
    if not val_s or old_s == val_s:
        return False
    if backfill_all:
        return True
    m = _DIFFERENT_CELL_RE.match(old_s)
    if not m:
        return False
    return val_s == f"{m.group(1)}-novel"


def normalize_depth(raw: str | None) -> str:
    d = str(raw or "").strip().lower()
    if not d or d == "ambiguous":
        return ""
    d = _DEPTH_ALIASES.get(d, d)
    return d if d in _DEPTH_OK else ""


def cell_from_fingerprint(
    fp: dict[str, Any],
    *,
    attested_depth: str | None = None,
) -> str:
    tier = str(fp.get("primary_tier") or "").strip().upper()[:1]
    if tier not in "ABCD":
        return ""
    structural = normalize_depth(str(fp.get("depth") or fp.get("effective_depth") or ""))
    effective = normalize_depth(str(fp.get("effective_depth") or fp.get("depth") or ""))
    base = effective or structural
    # novel 仅可盖在本轮 structural different 上；避免审计残留 novel 污染其它轮
    att = normalize_depth(attested_depth)
    if att == "novel" and structural == "different":
        depth = "novel"
    elif att and att == base:
        depth = att
    else:
        depth = base
    if not depth:
        return ""
    return f"{tier}-{depth}"


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


def _attested_depth(repo_root: Path) -> str | None:
    audit = _load_json(repo_root / "saved" / "innovation_audit.json") or {}
    d = normalize_depth(str(audit.get("attested_depth") or ""))
    return d or None


def _exp_names_from_fp(fp: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for key in ("candidate_exp_dirs",):
        for item in fp.get(key) or []:
            s = str(item or "").strip()
            if s:
                names.add(Path(s).name)
                names.add(s)
    return names


def _row_matches(row: dict[str, str], names: set[str]) -> bool:
    if not names:
        return False
    exp = (row.get("experiment") or "").strip()
    ed = (row.get("exp_dir") or "").strip()
    ed_name = Path(ed).name if ed else ""
    if exp and (exp in names or any(exp == Path(n).name for n in names)):
        return True
    if ed_name and ed_name in names:
        return True
    if ed and any(ed in n or n in ed for n in names if "/" in n or n.startswith("/")):
        return True
    return False


def _ensure_col(header: list[str], rows: list[dict[str, str]]) -> list[str]:
    if _COL in header:
        return header
    # 插在 baseline_tag 后，否则 parameters 区末、elapsed_sec 前
    out = list(header)
    if "baseline_tag" in out:
        i = out.index("baseline_tag") + 1
        out.insert(i, _COL)
    elif "elapsed_sec" in out:
        out.insert(out.index("elapsed_sec"), _COL)
    else:
        out.append(_COL)
    for r in rows:
        r.setdefault(_COL, "")
    return out


def _patch_tsv(
    path: Path,
    updates: dict[str, str],
    *,
    backfill_all: bool = False,
) -> int:
    """updates: exp_dir basename → exploration_space value. Returns number of cells changed."""
    if not path.is_file() or not updates:
        return 0
    with path.open(encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        if not reader.fieldnames:
            return 0
        orig_header = list(reader.fieldnames)
        rows = [dict(r) for r in reader]
    header = _ensure_col(list(orig_header), rows)
    header_added = _COL not in orig_header
    changed = 0
    names = set(updates.keys())
    for row in rows:
        if not _row_matches(row, names):
            continue
        ed_name = Path((row.get("exp_dir") or "").strip()).name
        exp = (row.get("experiment") or "").strip()
        val = updates.get(ed_name) or updates.get(exp) or ""
        if not val:
            for k, v in updates.items():
                if _row_matches(row, {k}):
                    val = v
                    break
        if not val:
            continue
        old = (row.get(_COL) or "").strip()
        if not should_apply_cell_update(old, val, backfill_all=backfill_all):
            continue
        row[_COL] = val
        changed += 1
    if changed == 0 and not header_added:
        return 0
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=header, delimiter="\t", lineterminator="\n", extrasaction="ignore"
        )
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in header})
    tmp.replace(path)
    return changed


def _patch_jsonl(
    path: Path,
    updates: dict[str, str],
    *,
    backfill_all: bool = False,
) -> int:
    if not path.is_file() or not updates:
        return 0
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    out: list[str] = []
    changed = 0
    names = set(updates.keys())
    for line in lines:
        if not line.strip():
            out.append(line)
            continue
        try:
            obj = json.loads(line)
        except Exception:
            out.append(line)
            continue
        if not isinstance(obj, dict):
            out.append(line)
            continue
        row = {
            "experiment": str(obj.get("experiment") or ""),
            "exp_dir": str(obj.get("exp_dir") or ""),
        }
        if not _row_matches(row, names):
            out.append(line)
            continue
        ed_name = Path(row["exp_dir"]).name
        val = updates.get(ed_name) or updates.get(row["experiment"]) or ""
        if not val:
            for k, v in updates.items():
                if _row_matches(row, {k}):
                    val = v
                    break
        old = str(obj.get(_COL) or "").strip()
        if not should_apply_cell_update(old, val, backfill_all=backfill_all):
            out.append(json.dumps(obj, ensure_ascii=False))
            continue
        obj[_COL] = val
        changed += 1
        out.append(json.dumps(obj, ensure_ascii=False))
    if changed:
        path.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")
    return changed


def _collect_updates_from_fp(
    fp: dict[str, Any],
    *,
    attested_depth: str | None,
) -> dict[str, str]:
    cell = cell_from_fingerprint(fp, attested_depth=attested_depth)
    if not cell:
        return {}
    updates: dict[str, str] = {}
    for item in fp.get("candidate_exp_dirs") or []:
        s = str(item or "").strip()
        if not s:
            continue
        updates[Path(s).name] = cell
        updates[s] = cell
    return updates


def sync_repo(repo_root: Path, *, backfill_all: bool = False) -> dict[str, int]:
    root = repo_root.resolve()
    tsv = root / "_runs" / "results.tsv"
    jsonl = root / "_runs" / "results.jsonl"
    updates: dict[str, str] = {}

    if backfill_all:
        hist = root / "saved" / "fingerprint_history.jsonl"
        if hist.is_file():
            for line in hist.read_text(encoding="utf-8", errors="replace").splitlines():
                if not line.strip():
                    continue
                try:
                    fp = json.loads(line)
                except Exception:
                    continue
                if isinstance(fp, dict):
                    # history 通常无 attested_depth；用条目自身 depth
                    updates.update(_collect_updates_from_fp(fp, attested_depth=None))
    else:
        fp = _load_json(root / "saved" / "innovation_fingerprint.json") or {}
        attested = _attested_depth(root)
        # 当前条：attested_depth 可区分 different vs novel
        updates.update(_collect_updates_from_fp(fp, attested_depth=attested))
        # 若当前 fingerprint 空，尝试 history 末条 + attested
        if not updates:
            hist = root / "saved" / "fingerprint_history.jsonl"
            if hist.is_file():
                last: dict[str, Any] | None = None
                for line in hist.read_text(encoding="utf-8", errors="replace").splitlines():
                    if not line.strip():
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(obj, dict):
                        last = obj
                if last:
                    updates.update(_collect_updates_from_fp(last, attested_depth=attested))

    n_tsv = (
        _patch_tsv(tsv, updates, backfill_all=backfill_all) if tsv.is_file() else 0
    )
    n_jsonl = (
        _patch_jsonl(jsonl, updates, backfill_all=backfill_all) if jsonl.is_file() else 0
    )
    return {"tsv": n_tsv, "jsonl": n_jsonl, "targets": len({k for k in updates if "/" not in k and not k.startswith("/")})}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Sync exploration_space cell into results.tsv / results.jsonl"
    )
    p.add_argument("--repo-root", type=Path, default=Path("."))
    p.add_argument(
        "--backfill-all",
        action="store_true",
        help="Scan saved/fingerprint_history.jsonl for all candidate dirs",
    )
    args = p.parse_args(argv)
    try:
        stats = sync_repo(args.repo_root, backfill_all=bool(args.backfill_all))
    except Exception as exc:
        print(f"[sync_exploration_ledger] WARN: {exc}", file=sys.stderr)
        return 0
    print(
        f"[sync_exploration_ledger] ok targets≈{stats['targets']} "
        f"tsv_changed={stats['tsv']} jsonl_changed={stats['jsonl']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
