"""轮末台账闭合检查：未 finalize 多槽、jsonl/TSV 漂移。

多槽未入账真源：find_unfinalized_multi_slot（正则 _s(\\d+)of(\\d+)_ + jsonl resolve）。
check_multi_slot_finalize / run_check 均经此入口。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_MULTI_SLOT = re.compile(r"_s(\d+)of(\d+)_")


@dataclass
class ClosureResult:
    ok: bool
    warns: list[str]
    fails: list[str]

    @property
    def exit_code(self) -> int:
        if self.fails:
            return 1
        if self.warns:
            return 2
        return 0


def _resolve_exp_dir(exp: str, repo_root: Path | None = None) -> str:
    p = Path(exp).expanduser()
    if not p.is_absolute() and repo_root is not None:
        p = repo_root / p
    try:
        return str(p.resolve())
    except OSError:
        return str(p)


def load_jsonl_exp_dirs(
    jsonl_path: Path,
    repo_root: Path | None = None,
) -> set[str]:
    out: set[str] = set()
    if not jsonl_path.is_file():
        return out
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        exp = row.get("exp_dir") or ""
        if not exp:
            continue
        out.add(_resolve_exp_dir(exp, repo_root))
    return out


def find_unfinalized_multi_slot(
    repo_root: Path,
    *,
    since_epoch: float | None = None,
) -> list[Path]:
    """已 train_done、N>=2、且不在 results.jsonl 的 multi-slot exp（按名字序）。

    ``since_epoch`` 若给定，仅保留落在时间窗内的目录（与 run_check 批窗一致）。
    """
    repo_root = Path(repo_root).resolve()
    exp_root = repo_root / "_runs" / "exp"
    jsonl_path = repo_root / "_runs" / "results.jsonl"
    if not exp_root.is_dir():
        return []
    finalized = load_jsonl_exp_dirs(jsonl_path, repo_root)
    gaps: list[Path] = []
    for exp_dir in sorted(exp_root.iterdir(), key=lambda p: p.name):
        if not exp_dir.is_dir():
            continue
        m = _MULTI_SLOT.search(exp_dir.name)
        if not m or int(m.group(2)) < 2:
            continue
        if not (exp_dir / "train_done.json").is_file():
            continue
        if since_epoch is not None and not _exp_in_window(exp_dir, since_epoch):
            continue
        if str(exp_dir.resolve()) not in finalized:
            gaps.append(exp_dir.resolve())
    return gaps


def _count_tsv_data_rows(tsv_path: Path) -> int:
    if not tsv_path.is_file():
        return 0
    lines = tsv_path.read_text(encoding="utf-8").splitlines()
    if len(lines) <= 1:
        return 0
    return len(lines) - 1


def _count_jsonl_rows(jsonl_path: Path) -> int:
    if not jsonl_path.is_file():
        return 0
    n = 0
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            n += 1
    return n


def _batch_start_epoch(repo_root: Path) -> float | None:
    marker = repo_root / "saved" / ".batch_start_epoch"
    if not marker.is_file():
        return None
    try:
        return float(marker.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def _exp_in_window(exp_dir: Path, since_epoch: float | None) -> bool:
    if since_epoch is None:
        return True
    for name in ("train_done.json", "results.json", "train_status.json"):
        p = exp_dir / name
        if p.is_file() and p.stat().st_mtime >= since_epoch:
            return True
    return exp_dir.stat().st_mtime >= since_epoch


def run_check(
    repo_root: Path,
    *,
    since_batch_start: bool = True,
    jsonl_tsv_warn_diff: int = 10,
    jsonl_tsv_fail_diff: int = 50,
) -> ClosureResult:
    repo_root = repo_root.resolve()
    runs = repo_root / "_runs"
    jsonl_path = runs / "results.jsonl"
    tsv_path = runs / "results.tsv"

    warns: list[str] = []
    fails: list[str] = []

    since_epoch = _batch_start_epoch(repo_root) if since_batch_start else None
    for gap in find_unfinalized_multi_slot(repo_root, since_epoch=since_epoch):
        fails.append(
            f"unfinalized_multi_slot: {gap.name} 已完成训练但未出现在 results.jsonl"
        )

    tsv_n = _count_tsv_data_rows(tsv_path)
    jsonl_n = _count_jsonl_rows(jsonl_path)
    diff = abs(tsv_n - jsonl_n)
    if diff >= jsonl_tsv_fail_diff:
        fails.append(
            f"ledger_drift: results.tsv 数据行 {tsv_n} vs results.jsonl {jsonl_n} (diff={diff})"
        )
    elif diff >= jsonl_tsv_warn_diff:
        warns.append(
            f"ledger_drift_warn: results.tsv 数据行 {tsv_n} vs results.jsonl {jsonl_n} (diff={diff})"
        )

    return ClosureResult(ok=not fails, warns=warns, fails=fails)


def format_lines(result: ClosureResult) -> list[str]:
    lines: list[str] = []
    for w in result.warns:
        lines.append(f"WARN: {w}")
    for f in result.fails:
        lines.append(f"FAIL: {f}")
    if result.ok and not result.warns:
        lines.append("PASS: round_ledger_closure OK")
    return lines
