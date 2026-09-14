#!/usr/bin/env python3
"""只读增量边界：自上次 analyse 以来的 TSV 行与 git 摘要（无数值）。"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lib.experiment_journal import empty_journal, journal_path, read_journal  # noqa: E402
from lib.run_ledger_summary import tsv_rows  # noqa: E402

_GIT_SCOPE_PATHS = ("train.py", "workspace/")


def _data_rows(repo_root: Path) -> list[dict[str, str]]:
    return [r for r in tsv_rows(repo_root) if r.get("experiment") != "preflight_check"]


def _git_is_repo(repo_root: Path) -> bool:
    return (repo_root / ".git").exists()


def _git_log_oneline(repo_root: Path, since: str, until: str, max_n: int = 20) -> list[str]:
    if not since or not _git_is_repo(repo_root):
        return []
    rev_range = f"{since}..{until}" if until else since
    try:
        proc = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "log",
                f"-{max_n}",
                "--oneline",
                "--no-decorate",
                rev_range,
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


def _git_head(repo_root: Path) -> str:
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


def build_delta_report(
    repo_root: Path,
) -> tuple[list[str], list[str], list[str], int | None, int]:
    """返回 (experiments, git_lines, warnings, analyse_cursor, all_row_count)。"""
    root = repo_root.resolve()
    warnings: list[str] = []
    path = journal_path(root)
    if not path.is_file():
        journal = empty_journal()
        warnings.append("WARN: 无 journal analyse 游标，列出全部 TSV 数据行")
    else:
        journal = read_journal(path)
    analyse = journal.get("analyse") or {}
    cursor_raw = analyse.get("tsv_row_count")
    cursor: int | None
    try:
        cursor = int(cursor_raw) if cursor_raw is not None else None
    except (TypeError, ValueError):
        cursor = None

    all_rows = _data_rows(root)
    if cursor is None:
        warnings.append("WARN: 无 journal analyse 游标，列出全部 TSV 数据行")
        new_rows = all_rows
    elif cursor < 0:
        new_rows = all_rows
    elif cursor >= len(all_rows):
        new_rows = []
    else:
        new_rows = all_rows[cursor:]

    experiments = [str(r.get("experiment") or "").strip() for r in new_rows if r.get("experiment")]

    git_since = str(analyse.get("git_head") or "").strip()
    git_until = _git_head(root)
    git_lines = _git_log_oneline(root, git_since, git_until) if git_since else []
    if not git_since and _git_is_repo(root):
        warnings.append("WARN: 无 analyse.git_head，跳过 git 增量摘要")

    return experiments, git_lines, warnings, cursor, len(all_rows)


def main() -> int:
    ap = argparse.ArgumentParser(description="Analyse delta boundary (TSV rows + git log)")
    ap.add_argument("--repo-root", type=Path, default=Path.cwd())
    ap.add_argument(
        "--quiet",
        action="store_true",
        help="无新 TSV 行且无 git 增量时不输出 stdout；跳过游标缺失类 WARN",
    )
    args = ap.parse_args()
    root = args.repo_root.resolve()

    experiments, git_lines, warnings, cursor, all_row_count = build_delta_report(root)
    if not args.quiet:
        for w in warnings:
            print(w, file=sys.stderr)
    elif warnings:
        for w in warnings:
            if "无新行" not in w and "游标" not in w and "git_head" not in w:
                print(w, file=sys.stderr)

    if args.quiet and not experiments and not git_lines:
        return 0

    # 游标 0 等价于「尚未有过 analyse 边界」，quiet 时不列全表
    if args.quiet and cursor == 0 and experiments and len(experiments) == all_row_count:
        return 0

    if not args.quiet or experiments or git_lines:
        if experiments:
            print("### TSV 增量（experiment）")
            for exp in experiments:
                print(exp)
        if git_lines:
            print("### Git（train.py workspace/）")
            print(" ".join(git_lines))
        elif not args.quiet:
            print("### TSV 增量（experiment）")
            print("(无新行)" if not experiments else "")
            print("### Git（train.py workspace/）")
            print("(无 commit 或无可比对游标)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
