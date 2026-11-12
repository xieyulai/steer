#!/usr/bin/env python3
"""隔离副本预演改题：只在副本里改合同并训练，结果写回正仓改题卡和成绩表。

用法:
  python3 scripts/rehearse_e.py --repo-root . --proposed "..." --why "..." --ask "..." --patch <path>
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lib.e_feedback_store import (  # noqa: E402
    _norm_proposed,
    attach_rehearsal,
    load_records,
)
from lib.rehearsal_row import REHEARSAL_CELL, REHEARSAL_SCORE_COL  # noqa: E402
from lib.run_ledger_summary import best_tsv_row, metric_key  # noqa: E402

_WATCH = ("contract", "HUMAN_GUIDANCE.md", "saved/keepers.json")
_METRIC_JSON = Path("_runs") / "analysis" / "rehearsal_metric.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _say(msg: str) -> None:
    print(f"rehearse_e: {msg}", file=sys.stderr)


def _git_diff_state(repo: Path) -> str:
    """clean / dirty / git_fail。只把仓库里实际存在的路径交给 git diff。"""
    paths = [p for p in _WATCH if (repo / p).exists()]
    if paths:
        cmd = ["git", "-C", str(repo), "diff", "--", *paths]
    else:
        cmd = ["git", "-C", str(repo), "rev-parse", "--is-inside-work-tree"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except OSError:
        return "git_fail"
    if proc.returncode != 0:
        return "git_fail"
    if not paths:
        return "clean"
    if proc.stdout:
        return "dirty"
    return "clean"


def _claim_has_rehearsal(repo: Path, proposed: str) -> bool:
    key = _norm_proposed(proposed)
    for rec in load_records(repo):
        if rec.get("kind") != "shout":
            continue
        if _norm_proposed(str(rec.get("proposed") or "")) != key:
            continue
        if isinstance(rec.get("rehearsal"), dict):
            return True
    return False


def _ignore_copy(_directory: str, names: list[str]) -> set[str]:
    drop: set[str] = set()
    if ".git" in names:
        drop.add(".git")
    if "_runs" in names:
        drop.add("_runs")
    return drop


def _git(cwd: Path, *args: str) -> None:
    proc = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(detail or f"git {' '.join(args)} 失败")


def _make_copy(repo: Path) -> Path:
    dest = Path(tempfile.mkdtemp(prefix="e_rehearse_"))
    try:
        shutil.copytree(repo, dest, dirs_exist_ok=True, ignore=_ignore_copy)
        _git(dest, "init")
        _git(dest, "config", "user.email", "rehearse@local")
        _git(dest, "config", "user.name", "rehearse")
        _git(dest, "config", "commit.gpgsign", "false")
        _git(dest, "config", "core.autocrlf", "false")
        _git(dest, "add", "-A")
        _git(dest, "commit", "-m", "rehearsal snapshot")
    except Exception:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    return dest


def _split_diff_git_paths(rest: str) -> list[str]:
    paths: list[str] = []
    i = 0
    n = len(rest)
    while i < n:
        while i < n and rest[i] == " ":
            i += 1
        if i >= n:
            break
        if rest[i] == '"':
            i += 1
            buf: list[str] = []
            while i < n:
                if rest[i] == "\\" and i + 1 < n:
                    buf.append(rest[i + 1])
                    i += 2
                    continue
                if rest[i] == '"':
                    i += 1
                    break
                buf.append(rest[i])
                i += 1
            paths.append("".join(buf))
            continue
        j = rest.find(" ", i)
        if j < 0:
            paths.append(rest[i:])
            break
        paths.append(rest[i:j])
        i = j + 1
    return paths


def _normalize_patch_path(path: str) -> str:
    text = path.strip().strip('"').replace("\\", "/")
    if text.startswith("./"):
        text = text[2:]
    if text.startswith("a/") or text.startswith("b/"):
        text = text[2:]
    return text


def _parse_patch_files(patch: Path) -> list[str]:
    try:
        text = patch.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    from_git: list[str] = []
    from_plus: list[str] = []
    for line in text.splitlines():
        if line.startswith("diff --git "):
            parts = _split_diff_git_paths(line[len("diff --git ") :])
            if parts:
                from_git.append(_normalize_patch_path(parts[-1]))
        elif line.startswith("+++ "):
            token = line[4:].strip().split("\t", 1)[0].strip()
            if token and token != "/dev/null":
                from_plus.append(_normalize_patch_path(token))
    raw = from_git or from_plus
    out: list[str] = []
    for item in raw:
        if item and item != "/dev/null" and item not in out:
            out.append(item)
    return out


def _under_contract(path: str) -> bool:
    norm = _normalize_patch_path(path)
    if not norm or norm == "/dev/null":
        return True
    parts = PurePosixPath(norm).parts
    if any(part == ".." for part in parts):
        return False
    return len(parts) >= 2 and parts[0] == "contract"


def _changed_paths(copy: Path) -> list[str]:
    found: list[str] = []
    commands = (
        ["diff", "--name-only"],
        ["diff", "--cached", "--name-only"],
        ["ls-files", "--others", "--exclude-standard"],
    )
    for args in commands:
        proc = subprocess.run(
            ["git", "-C", str(copy), *args],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            continue
        for line in proc.stdout.splitlines():
            name = line.strip()
            if name and name not in found:
                found.append(name)
    return found


def _apply_patch(copy: Path, patch: Path) -> tuple[list[str], str | None]:
    files = _parse_patch_files(patch)
    outside = [item for item in files if not _under_contract(item)]
    if outside:
        return files, "补丁超出 contract/: " + ", ".join(outside)
    if not patch.is_file():
        return files, f"补丁不存在: {patch}"
    proc = subprocess.run(
        ["git", "-C", str(copy), "apply", str(patch)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "git apply 失败").strip()
        return files, err
    changed = _changed_paths(copy)
    merged = list(dict.fromkeys([*files, *changed]))
    outside = [item for item in merged if not _under_contract(item)]
    if outside:
        return merged, "补丁超出 contract/: " + ", ".join(outside)
    return merged, None


def _train(copy: Path, train_cmd: str | None) -> tuple[int, str]:
    cmd = train_cmd.strip() if train_cmd and train_cmd.strip() else "python3 train.py"
    env = os.environ.copy()
    env["NN_RELAUNCH"] = "1"
    proc = subprocess.run(
        cmd,
        shell=True,
        cwd=str(copy),
        env=env,
        capture_output=True,
        text=True,
    )
    tail = (proc.stderr or proc.stdout or "").strip()
    if len(tail) > 500:
        tail = tail[-500:]
    return proc.returncode, tail


def _read_metric(copy: Path) -> tuple[str, float] | None:
    path = copy / _METRIC_JSON
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    key = data.get("metric_key")
    metric = data.get("metric")
    if not isinstance(key, str) or not key.strip():
        return None
    if isinstance(metric, bool) or not isinstance(metric, (int, float)):
        return None
    value = float(metric)
    if math.isnan(value) or math.isinf(value):
        return None
    return key.strip(), value


def _formal_leader(repo: Path) -> tuple[str, str, float | None]:
    """没有正式行时场景用 default，最高分实验名为空，读数与差值为 null。"""
    try:
        mk = metric_key(repo)
    except Exception:
        return "default", "", None
    try:
        row = best_tsv_row(repo, mk)
    except Exception:
        return "default", "", None
    if not row:
        return "default", "", None
    scenario = str(row.get("scenario_id") or "").strip() or "default"
    experiment = str(row.get("experiment") or "")
    raw = str(row.get(mk, "") or "").strip()
    try:
        leader = float(raw)
    except (TypeError, ValueError):
        return scenario, experiment, None
    if math.isnan(leader) or math.isinf(leader):
        return scenario, experiment, None
    return scenario, experiment, leader


def _fmt_score(metric: float) -> str:
    value = float(metric)
    if value.is_integer() and abs(value) < 10**15:
        return str(int(value))
    return format(value, "g")


def _append_tsv(
    path: Path,
    *,
    experiment: str,
    scenario_id: str,
    metric_key_name: str,
    score: float,
) -> None:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines:
        raise ValueError("results.tsv 没有表头")
    header = lines[0].split("\t")
    if REHEARSAL_SCORE_COL not in header:
        if "exploration_space" in header:
            at = header.index("exploration_space") + 1
        else:
            at = len(header)
        header.insert(at, REHEARSAL_SCORE_COL)
        rebuilt = ["\t".join(header)]
        for line in lines[1:]:
            cells = line.split("\t")
            if len(cells) < at:
                cells.extend([""] * (at - len(cells)))
            cells.insert(at, "")
            if len(cells) < len(header):
                cells.extend([""] * (len(header) - len(cells)))
            rebuilt.append("\t".join(cells[: len(header)]))
        lines = rebuilt
    header = lines[0].split("\t")
    row = [""] * len(header)
    index = {name: i for i, name in enumerate(header)}

    def put(name: str, value: str) -> None:
        if name in index:
            row[index[name]] = value

    put("experiment", experiment)
    put("scenario_id", scenario_id)
    put("exploration_space", REHEARSAL_CELL)
    put(REHEARSAL_SCORE_COL, _fmt_score(score))
    protected = {
        "experiment",
        "scenario_id",
        "exploration_space",
        REHEARSAL_SCORE_COL,
    }
    if metric_key_name in index and metric_key_name not in protected:
        row[index[metric_key_name]] = ""
    lines.append("\t".join(row))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _restore_tsv(path: Path, before: bytes | None) -> None:
    if before is None:
        if path.exists():
            path.unlink()
        return
    path.write_bytes(before)


def _delete_tree(tree: Path | None) -> bool:
    if tree is None:
        return True
    try:
        if tree.exists():
            shutil.rmtree(tree)
    except OSError:
        return not tree.exists()
    return not tree.exists()


def _body(
    *,
    status: str,
    metric: float | None,
    metric_key_name: str | None,
    leader_experiment: str,
    leader_metric: float | None,
    delta: float | None,
    patch_files: list[str],
    tree_deleted: bool,
    live_contract_clean: bool,
    tsv_experiment: str | None,
    error: str,
) -> dict:
    return {
        "status": status,
        "metric": metric,
        "metric_key": metric_key_name,
        "leader_experiment": leader_experiment,
        "leader_metric": leader_metric,
        "delta_vs_leader": delta,
        "patch_files": list(patch_files),
        "tree_deleted": tree_deleted,
        "live_contract_clean": live_contract_clean,
        "tsv_experiment": tsv_experiment,
        "error": error,
        "ts": _now_iso(),
    }


def _book(
    repo: Path,
    proposed: str,
    why: str,
    ask: str,
    rehearsal: dict,
    *,
    e_type: str = "",
    headline: str = "",
    e_type_note: str = "",
    continues: str = "",
) -> None:
    attach_rehearsal(
        repo,
        proposed,
        rehearsal,
        overwrite=True,
        why=why,
        ask=ask,
        e_type=e_type,
        headline=headline,
        e_type_note=e_type_note,
        continues=continues,
    )


def rehearse(
    repo: Path,
    *,
    proposed: str,
    why: str,
    ask: str,
    patch: Path,
    train_cmd: str | None,
    e_type: str,
    headline: str,
    e_type_note: str = "",
    continues: str = "",
) -> int:
    if os.environ.get("NN_RELAUNCH", "").strip():
        _say("父进程已设置 NN_RELAUNCH")
        return 3
    if _git_diff_state(repo) != "clean":
        _say("正仓合同、keeper 或路线图已有改动，或 git 不可用")
        return 3
    if _claim_has_rehearsal(repo, proposed):
        _say("该主张已有预演")
        return 2

    placed = attach_rehearsal(
        repo,
        proposed,
        {"status": "running", "metric": None},
        why=why,
        ask=ask,
        e_type=e_type,
        headline=headline,
        e_type_note=e_type_note,
        continues=continues,
    )
    if "skipped" in placed:
        _say(f"未占位: {placed.get('skipped')}")
        return 2

    card_id = str(placed.get("id") or "")
    tree: Path | None = None
    patch_files: list[str] = []
    appended = False
    tsv_path = repo / "_runs" / "results.tsv"
    tsv_before: bytes | None = None
    outcome = "fail"
    error = ""
    exit_code = 0
    metric_value: float | None = None
    metric_name: str | None = None
    leader_experiment = ""
    leader_metric: float | None = None
    delta: float | None = None
    scenario_id = "default"
    exp_name = f"e_rehearsal_{card_id}"

    try:
        tree = _make_copy(repo)
        patch_files, apply_err = _apply_patch(tree, patch)
        if apply_err:
            outcome = "fail"
            error = apply_err
        else:
            rc, tail = _train(tree, train_cmd)
            parsed = _read_metric(tree) if rc == 0 else None
            if rc != 0 or parsed is None:
                outcome = "fail"
                if rc != 0:
                    error = f"训练退出码 {rc}"
                    if tail:
                        error = f"{error}: {tail}"
                else:
                    error = "缺少或无法读取 _runs/analysis/rehearsal_metric.json"
            else:
                metric_name, metric_value = parsed
                scenario_id, leader_experiment, leader_metric = _formal_leader(repo)
                if leader_metric is None:
                    delta = None
                else:
                    delta = metric_value - leader_metric
                tsv_before = tsv_path.read_bytes() if tsv_path.is_file() else None
                _append_tsv(
                    tsv_path,
                    experiment=exp_name,
                    scenario_id=scenario_id,
                    metric_key_name=metric_name,
                    score=metric_value,
                )
                appended = True
                if _git_diff_state(repo) != "clean":
                    outcome = "dirty"
                    error = "正仓合同、keeper 或路线图在预演后有改动"
                    exit_code = 3
                else:
                    outcome = "ok"
    except Exception as exc:
        outcome = "fail"
        error = f"{type(exc).__name__}: {exc}"
        exit_code = 0

    if outcome == "dirty":
        if appended:
            _restore_tsv(tsv_path, tsv_before)
            appended = False
        deleted = _delete_tree(tree)
        try:
            _book(
                repo,
                proposed,
                why,
                ask,
                _body(
                    status="fail",
                    metric=None,
                    metric_key_name=metric_name,
                    leader_experiment=leader_experiment,
                    leader_metric=leader_metric,
                    delta=None,
                    patch_files=patch_files,
                    tree_deleted=deleted,
                    live_contract_clean=False,
                    tsv_experiment=None,
                    error=error or "正仓在预演后变脏",
                ),
            )
        except Exception as exc:
            _say(f"记账失败: {exc}")
        _say(error or "正仓在预演后变脏")
        return 3

    if outcome != "ok":
        if appended:
            _restore_tsv(tsv_path, tsv_before)
        deleted = _delete_tree(tree)
        try:
            _book(
                repo,
                proposed,
                why,
                ask,
                _body(
                    status="fail",
                    metric=None,
                    metric_key_name=None,
                    leader_experiment="",
                    leader_metric=None,
                    delta=None,
                    patch_files=patch_files,
                    tree_deleted=deleted,
                    live_contract_clean=True,
                    tsv_experiment=None,
                    error=error or "预演失败",
                ),
            )
        except Exception as exc:
            _say(f"记账失败: {exc}")
        _say(error or "预演失败")
        return 0

    deleted = _delete_tree(tree)
    if not deleted:
        if appended:
            _restore_tsv(tsv_path, tsv_before)
        try:
            _book(
                repo,
                proposed,
                why,
                ask,
                _body(
                    status="fail",
                    metric=None,
                    metric_key_name=metric_name,
                    leader_experiment=leader_experiment,
                    leader_metric=leader_metric,
                    delta=delta,
                    patch_files=patch_files,
                    tree_deleted=False,
                    live_contract_clean=True,
                    tsv_experiment=None,
                    error="副本删除失败",
                ),
            )
        except Exception as exc:
            _say(f"记账失败: {exc}")
        _say("副本删除失败")
        return 0

    try:
        _book(
            repo,
            proposed,
            why,
            ask,
            _body(
                status="ok",
                metric=metric_value,
                metric_key_name=metric_name,
                leader_experiment=leader_experiment,
                leader_metric=leader_metric,
                delta=delta,
                patch_files=patch_files,
                tree_deleted=True,
                live_contract_clean=True,
                tsv_experiment=exp_name,
                error="",
            ),
        )
    except Exception as exc:
        if appended:
            _restore_tsv(tsv_path, tsv_before)
        try:
            _book(
                repo,
                proposed,
                why,
                ask,
                _body(
                    status="fail",
                    metric=None,
                    metric_key_name=metric_name,
                    leader_experiment=leader_experiment,
                    leader_metric=leader_metric,
                    delta=delta,
                    patch_files=patch_files,
                    tree_deleted=True,
                    live_contract_clean=True,
                    tsv_experiment=None,
                    error=f"{type(exc).__name__}: {exc}",
                ),
            )
        except Exception as exc2:
            _say(f"记账失败: {exc2}")
        _say(f"{type(exc).__name__}: {exc}")
        return 0
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="隔离副本预演改题")
    parser.add_argument("--repo-root", default=".", help="正仓根目录")
    parser.add_argument("--proposed", required=True, help="改题主张")
    parser.add_argument("--why", required=True, help="为什么 A–D 不够")
    parser.add_argument("--ask", required=True, help="想请人做什么")
    parser.add_argument("--patch", required=True, type=Path, help="只改 contract/ 的补丁")
    parser.add_argument(
        "--e-type",
        required=True,
        choices=[
            "method_escape",
            "score_rule",
            "task_scope",
            "trainable",
            "information_visibility",
            "other",
        ],
        help="改题类型。信息权限用 information_visibility",
    )
    parser.add_argument("--headline", required=True, help="一行标题，不超过 80 字")
    parser.add_argument("--e-type-note", default="", help="类型为 other 时必填的一行说明")
    parser.add_argument("--continues", default="", help="复提时填写原卡 id，类型沿用原卡")
    parser.add_argument(
        "--train-cmd",
        default=None,
        help="在副本里执行的训练命令；缺省为 python3 train.py",
    )
    args = parser.parse_args(argv)
    repo = Path(args.repo_root).resolve()
    patch = args.patch if args.patch.is_absolute() else Path.cwd() / args.patch
    return rehearse(
        repo,
        proposed=args.proposed,
        why=args.why,
        ask=args.ask,
        patch=patch,
        train_cmd=args.train_cmd,
        e_type=args.e_type,
        headline=args.headline,
        e_type_note=args.e_type_note,
        continues=args.continues,
    )


if __name__ == "__main__":
    raise SystemExit(main())
