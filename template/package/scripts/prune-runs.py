#!/usr/bin/env python3
"""按用户条件局部清理台账与 _runs/exp（默认 --dry-run，--apply 才执行）。"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# 与 regen_results_tsv 共用读表逻辑
_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
from scripts.regen_results_tsv import _read_tsv_rows  # noqa: E402


def _norm_exp_dir(repo_root: Path, p: str) -> Path | None:
    raw = (p or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = (repo_root / raw).resolve()
    else:
        path = path.resolve()
    return path


def _exp_dir_name_before_date(name: str, before: str) -> bool:
    m = re.match(r"^(\d{8})_", name)
    if not m:
        return False
    return m.group(1) < before


def _collect_exp_dirs_from_disk(
    repo_root: Path,
    *,
    exp_globs: tuple[str, ...],
    exp_suffixes: tuple[str, ...],
    before_dates: tuple[str, ...],
    explicit: set[Path],
) -> set[Path]:
    exp_root = repo_root / "_runs" / "exp"
    found: set[Path] = set(explicit)
    if not exp_root.is_dir():
        return found
    for child in exp_root.iterdir():
        if not child.is_dir():
            continue
        name = child.name
        for g in exp_globs:
            if fnmatch.fnmatch(name, g):
                found.add(child.resolve())
                break
        for suf in exp_suffixes:
            if name.endswith(suf):
                found.add(child.resolve())
                break
        for bd in before_dates:
            if _exp_dir_name_before_date(name, bd):
                found.add(child.resolve())
                break
    return found


def _row_matches_drop(
    row: dict[str, str],
    *,
    drop_experiments: frozenset[str],
    exp_dirs_to_drop: set[Path],
    repo_root: Path,
) -> bool:
    ex = (row.get("experiment") or "").strip()
    if ex and ex in drop_experiments:
        return True
    ed = _norm_exp_dir(repo_root, row.get("exp_dir", ""))
    if ed is not None and ed in exp_dirs_to_drop:
        return True
    return False


def _dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def _warn_keeper(repo_root: Path, exp_dirs: set[Path]) -> None:
    keeper = repo_root / "saved" / "keeper.json"
    if not keeper.is_file():
        return
    try:
        data = json.loads(keeper.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print("[prune-runs] WARN: saved/keeper.json 无法解析", file=sys.stderr)
        return
    kdir = (data.get("keeper_exp_dir") or "").strip()
    if not kdir:
        return
    kp = (Path(repo_root) / kdir if not Path(kdir).is_absolute() else Path(kdir)).resolve()
    if kp in exp_dirs or (kp.exists() is False and any(str(kp) == str(d) for d in exp_dirs)):
        print(
            f"[prune-runs] WARN: saved/keeper.json 指向将删目录 {kp} — "
            "apply 后请删 keeper.json 或 write-keeper",
            file=sys.stderr,
        )
    elif not kp.exists():
        print(f"[prune-runs] WARN: saved/keeper.json 指向不存在路径 {kp}", file=sys.stderr)


def _warn_round_decision(repo_root: Path, exp_dirs: set[Path]) -> None:
    rd = repo_root / "_runs" / "round_decision.json"
    if not rd.is_file():
        return
    try:
        data = json.loads(rd.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    fin = data.get("finalize_round") or {}
    keeper = (fin.get("keeper_exp_dir") or "").strip()
    if keeper:
        kp = (Path(repo_root) / keeper if not Path(keeper).is_absolute() else Path(keeper)).resolve()
        if kp in exp_dirs:
            print(
                "[prune-runs] WARN: round_decision.json 的 keeper 将被删 — "
                "apply 后建议 rm _runs/round_decision.json",
                file=sys.stderr,
            )


def _filter_jsonl(
    repo_root: Path,
    jsonl_rel: str,
    *,
    drop_experiments: frozenset[str],
    exp_dirs_to_drop: set[Path],
) -> tuple[int, int]:
    path = repo_root / jsonl_rel
    if not path.is_file():
        return 0, 0
    kept_lines: list[str] = []
    dropped = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            kept_lines.append(line)
            continue
        ex = (obj.get("experiment") or "").strip()
        ed = _norm_exp_dir(repo_root, obj.get("exp_dir", "") or "")
        drop = (ex in drop_experiments) or (ed is not None and ed in exp_dirs_to_drop)
        if drop:
            dropped += 1
        else:
            kept_lines.append(line)
    return len(kept_lines), dropped


def plan_prune(
    repo_root: Path,
    *,
    drop_experiments: frozenset[str],
    exp_globs: tuple[str, ...],
    exp_suffixes: tuple[str, ...],
    before_dates: tuple[str, ...],
    exp_dir_file: Path | None,
    ledger_only: bool,
    tsv_rel: str,
    jsonl_rel: str,
) -> tuple[list[dict[str, str]], list[dict[str, str]], set[Path]]:
    explicit: set[Path] = set()
    if exp_dir_file and exp_dir_file.is_file():
        for line in exp_dir_file.read_text(encoding="utf-8").splitlines():
            p = _norm_exp_dir(repo_root, line)
            if p is not None:
                explicit.add(p)

    exp_dirs_disk = _collect_exp_dirs_from_disk(
        repo_root,
        exp_globs=exp_globs,
        exp_suffixes=exp_suffixes,
        before_dates=before_dates,
        explicit=explicit,
    )

    _, rows = _read_tsv_rows(repo_root / tsv_rel)
    drop_rows: list[dict[str, str]] = []
    keep_rows: list[dict[str, str]] = []
    exp_from_rows: set[Path] = set()

    for row in rows:
        if _row_matches_drop(
            row,
            drop_experiments=drop_experiments,
            exp_dirs_to_drop=exp_dirs_disk,
            repo_root=repo_root,
        ):
            drop_rows.append(row)
            ed = _norm_exp_dir(repo_root, row.get("exp_dir", ""))
            if ed is not None:
                exp_from_rows.add(ed)
        else:
            keep_rows.append(row)

    exp_to_delete = set() if ledger_only else (exp_dirs_disk | exp_from_rows)
    return keep_rows, drop_rows, exp_to_delete


def _print_plan(
    repo_root: Path,
    *,
    keep_rows: list[dict[str, str]],
    drop_rows: list[dict[str, str]],
    exp_to_delete: set[Path],
    ledger_only: bool,
    jsonl_rel: str,
    drop_experiments: frozenset[str],
) -> None:
    print(f"[prune-runs] 模式: {'ledger-only' if ledger_only else 'ledger+exp'}", file=sys.stderr)
    print(f"[prune-runs] TSV 将删 {len(drop_rows)} 行，保留 {len(keep_rows)} 行", file=sys.stderr)
    if drop_experiments:
        print(f"[prune-runs] --drop-experiment: {', '.join(sorted(drop_experiments))}", file=sys.stderr)
    total_bytes = 0
    for i, row in enumerate(drop_rows[:30]):
        print(
            f"  TSV drop: experiment={row.get('experiment','')!r} "
            f"exp_dir={row.get('exp_dir','')}",
            file=sys.stderr,
        )
    if len(drop_rows) > 30:
        print(f"  ... 另有 {len(drop_rows) - 30} 行", file=sys.stderr)
    if ledger_only and exp_to_delete:
        print("[prune-runs] WARN: --ledger-only 不删 exp，但磁盘上仍有匹配目录", file=sys.stderr)
    if not ledger_only:
        print(f"[prune-runs] 将删 exp 目录 {len(exp_to_delete)} 个", file=sys.stderr)
        for i, p in enumerate(sorted(exp_to_delete)[:30]):
            sz = _dir_size(p)
            total_bytes += sz
            print(f"  exp rm: {p} ({sz} bytes)", file=sys.stderr)
        if len(exp_to_delete) > 30:
            print(f"  ... 另有 {len(exp_to_delete) - 30} 个目录", file=sys.stderr)
        print(f"[prune-runs] exp 合计约 {total_bytes} bytes", file=sys.stderr)
    kept, dropped = _filter_jsonl(
        repo_root, jsonl_rel,
        drop_experiments=drop_experiments,
        exp_dirs_to_drop=exp_to_delete,
    )
    print(f"[prune-runs] jsonl 将删 {dropped} 行，保留 {kept} 行", file=sys.stderr)
    if not ledger_only:
        _warn_keeper(repo_root, exp_to_delete)
        _warn_round_decision(repo_root, exp_to_delete)


def _write_filtered_tsv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    lines = ["\t".join(header)]
    for row in rows:
        lines.append("\t".join(row.get(col, "") for col in header))
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def apply_prune(
    repo_root: Path,
    *,
    keep_rows: list[dict[str, str]],
    drop_rows: list[dict[str, str]],
    exp_to_delete: set[Path],
    ledger_only: bool,
    tsv_rel: str,
    jsonl_rel: str,
    drop_experiments: frozenset[str],
    no_backup: bool,
) -> None:
    tsv_path = repo_root / tsv_rel
    jsonl_path = repo_root / jsonl_rel
    header, _ = _read_tsv_rows(tsv_path)
    if not header and keep_rows:
        header = list(keep_rows[0].keys())

    if not no_backup:
        if tsv_path.is_file() and tsv_path.stat().st_size > 0:
            bak = tsv_path.with_suffix(tsv_path.suffix + ".bak")
            shutil.copy2(tsv_path, bak)
            print(f"[prune-runs] 已备份 TSV: {bak}", file=sys.stderr)
        if jsonl_path.is_file() and jsonl_path.stat().st_size > 0:
            bak_j = jsonl_path.with_suffix(jsonl_path.suffix + ".bak")
            shutil.copy2(jsonl_path, bak_j)
            print(f"[prune-runs] 已备份 jsonl: {bak_j}", file=sys.stderr)

    # 主流程：写台账 → 删目录 → 写 jsonl。regen 只做表头/回填，失败不得阻断清理。
    _write_filtered_tsv(tsv_path, header, keep_rows)

    if not ledger_only:
        for p in sorted(exp_to_delete):
            if p.is_dir():
                shutil.rmtree(p)
                print(f"[prune-runs] 已删 exp: {p}", file=sys.stderr)
            elif p.is_file():
                p.unlink()

    if jsonl_path.is_file():
        kept_lines: list[str] = []
        for line in jsonl_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                kept_lines.append(line)
                continue
            ex = (obj.get("experiment") or "").strip()
            ed = _norm_exp_dir(repo_root, obj.get("exp_dir", "") or "")
            if _row_matches_drop(
                {"experiment": ex, "exp_dir": str(ed) if ed else ""},
                drop_experiments=drop_experiments,
                exp_dirs_to_drop=exp_to_delete if not ledger_only else set(),
                repo_root=repo_root,
            ):
                continue
            kept_lines.append(line)
        jsonl_path.write_text(
            "\n".join(kept_lines) + ("\n" if kept_lines else ""),
            encoding="utf-8",
        )
        print(f"[prune-runs] jsonl 保留 {len(kept_lines)} 行", file=sys.stderr)

    _best_effort_regen_tsv(repo_root, tsv_rel)
    print("[prune-runs] apply 完成", file=sys.stderr)


def _best_effort_regen_tsv(repo_root: Path, tsv_rel: str) -> None:
    """表头对齐 / 指标回填；失败只 WARN，不抬高清理 exit。"""
    regen = repo_root / "scripts" / "regen_results_tsv.py"
    if not regen.is_file():
        print("[prune-runs] WARN: 缺少 regen_results_tsv.py，跳过表头同步", file=sys.stderr)
        return
    try:
        subprocess.run(
            [sys.executable, str(regen), "--repo-root", str(repo_root), "--tsv", tsv_rel, "--no-backup"],
            check=True,
            cwd=repo_root,
        )
    except subprocess.CalledProcessError as exc:
        print(
            f"[prune-runs] WARN: regen_results_tsv 失败（exit={exc.returncode}）；"
            "台账行与 exp 目录已按计划清理，请用 poetry run python scripts/regen_results_tsv.py 补同步",
            file=sys.stderr,
        )
    except OSError as exc:
        print(f"[prune-runs] WARN: 无法启动 regen_results_tsv: {exc}", file=sys.stderr)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--tsv", default="_runs/results.tsv")
    ap.add_argument("--jsonl", default="_runs/results.jsonl")
    ap.add_argument("--drop-experiment", action="append", default=[], metavar="NAME")
    ap.add_argument("--exp-glob", action="append", default=[], metavar="GLOB")
    ap.add_argument("--exp-suffix", action="append", default=[], metavar="SUFFIX")
    ap.add_argument("--before-date", action="append", default=[], metavar="YYYYMMDD")
    ap.add_argument("--exp-dir-file", type=Path, default=None)
    ap.add_argument("--ledger-only", action="store_true")
    ap.add_argument("--apply", action="store_true", help="执行删除（默认仅 dry-run）")
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args()

    repo_root = args.repo_root.resolve()
    drop_ex = frozenset(x.strip() for x in args.drop_experiment if x.strip())
    before = tuple(x.strip() for x in args.before_date if re.fullmatch(r"\d{8}", x.strip()))

    if not (
        drop_ex or args.exp_glob or args.exp_suffix or before
        or args.exp_dir_file
    ):
        print("[prune-runs] 错误: 须至少指定一种条件", file=sys.stderr)
        return 1

    keep_rows, drop_rows, exp_del = plan_prune(
        repo_root,
        drop_experiments=drop_ex,
        exp_globs=tuple(args.exp_glob),
        exp_suffixes=tuple(args.exp_suffix),
        before_dates=before,
        exp_dir_file=args.exp_dir_file,
        ledger_only=args.ledger_only,
        tsv_rel=args.tsv,
        jsonl_rel=args.jsonl,
    )

    if not drop_rows and not exp_del:
        print("[prune-runs] 无匹配项，未改动", file=sys.stderr)
        return 0

    _print_plan(
        repo_root,
        keep_rows=keep_rows,
        drop_rows=drop_rows,
        exp_to_delete=exp_del,
        ledger_only=args.ledger_only,
        jsonl_rel=args.jsonl,
        drop_experiments=drop_ex,
    )

    if not args.apply:
        print("[prune-runs] dry-run 结束；确认后请加 --apply", file=sys.stderr)
        return 0

    apply_prune(
        repo_root,
        keep_rows=keep_rows,
        drop_rows=drop_rows,
        exp_to_delete=exp_del,
        ledger_only=args.ledger_only,
        tsv_rel=args.tsv,
        jsonl_rel=args.jsonl,
        drop_experiments=drop_ex,
        no_backup=args.no_backup,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
