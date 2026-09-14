"""Git 代码增量工具（analyse_code_delta / reflect 证据共用）。"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from lib.experiment_journal import journal_path, read_journal

GIT_SCOPE_PATHS = ("train.py", "workspace/")
_ROOT_PY_DEFAULT_ALLOWLIST = frozenset({"train.py", "experiment.py", "reflect.py"})
_DEFAULT_MAX_CHANGE_FILES = 3


def git_is_repo(repo_root: Path) -> bool:
    return (repo_root / ".git").exists()


def run_git(repo_root: Path, *args: str, timeout: float = 30.0) -> str:
    if not git_is_repo(repo_root):
        return ""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if proc.returncode != 0:
            return ""
        return proc.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def git_head_short(repo_root: Path) -> str:
    return run_git(repo_root, "rev-parse", "--short", "HEAD")


def git_diff_name_only(
    repo_root: Path,
    since: str,
    until: str,
    *,
    paths: tuple[str, ...] | None = None,
) -> list[str]:
    if not since or not until or not git_is_repo(repo_root):
        return []
    args: list[str] = ["diff", "--name-only", since, until]
    if paths is not None:
        args.extend(["--", *paths])
    raw = run_git(repo_root, *args)
    if not raw:
        return []
    return [ln.strip() for ln in raw.splitlines() if ln.strip()]


def root_py_allowlist() -> frozenset[str]:
    names = set(_ROOT_PY_DEFAULT_ALLOWLIST)
    extra = os.environ.get("NN_ROOT_PY_ALLOWLIST", "").strip()
    if extra:
        names.update(x.strip() for x in extra.split(",") if x.strip())
    return frozenset(names)


def relaunch_declared() -> bool:
    return bool(os.environ.get("NN_RELAUNCH", "").strip())


def is_allowed_code_path(path: str) -> bool:
    return path == "train.py" or path.startswith("workspace/")


def infer_tier_from_paths(paths: list[str]) -> list[str]:
    tiers: list[str] = []
    joined = " ".join(paths).lower()
    if re.search(r"workspace/.*(loss|reward|objective)", joined):
        tiers.append("C")
    if re.search(r"workspace/.*(model|pinn|backbone|arch|net)", joined) or "train.py" in paths:
        if re.search(r"workspace/", joined):
            tiers.append("B")
    if re.search(r"workspace/.*(data|colloc|sampler|curriculum)", joined):
        tiers.append("D")
    if paths == ["train.py"] or (len(paths) == 1 and paths[0] == "train.py"):
        tiers.append("A")
    return sorted(set(tiers))


def analyse_max_change_files(repo_root: Path) -> int:
    cfg_path = repo_root / "nn-config.yaml"
    if not cfg_path.is_file():
        return _DEFAULT_MAX_CHANGE_FILES
    try:
        import yaml

        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        val = (raw.get("agent") or {}).get("analyse_max_change_files")
        if val is not None:
            return max(1, int(val))
    except Exception:
        pass
    return _DEFAULT_MAX_CHANGE_FILES


def _analyse_git_head(repo_root: Path) -> str:
    path = journal_path(repo_root)
    if not path.is_file():
        return ""
    journal = read_journal(path)
    return str((journal.get("analyse") or {}).get("git_head") or "").strip()


@dataclass
class CodeDeltaReport:
    skipped: bool = False
    skip_reason: str = ""
    git_range: str = ""
    scoped_files: list[str] = field(default_factory=list)
    all_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info_lines: list[str] = field(default_factory=list)


def build_code_delta_report(repo_root: Path) -> CodeDeltaReport:
    root = repo_root.resolve()
    report = CodeDeltaReport()

    if not git_is_repo(root):
        report.skipped = True
        report.skip_reason = "无 git 仓库"
        return report

    since = _analyse_git_head(root)
    if not since:
        report.skipped = True
        report.skip_reason = "无 analyse.git_head 基线"
        return report

    until = git_head_short(root)
    if not until:
        report.skipped = True
        report.skip_reason = "无法解析 HEAD"
        return report

    report.git_range = f"{since}..{until}"
    report.all_files = git_diff_name_only(root, since, until)
    report.scoped_files = git_diff_name_only(root, since, until, paths=GIT_SCOPE_PATHS)

    contract_or_experiment = [
        f for f in report.all_files if f.startswith("contract/") or f == "experiment.py"
    ]
    if contract_or_experiment and not relaunch_declared():
        report.warnings.append(
            "WARN: CD-1 contract/ 或 experiment.py 有改动且未设置 NN_RELAUNCH=1"
            f" ({', '.join(contract_or_experiment)})"
        )

    if "HUMAN_GUIDANCE.md" in report.all_files:
        report.warnings.append("WARN: CD-2 HUMAN_GUIDANCE.md 有改动")

    allow = root_py_allowlist()
    bad_root_py = [
        f for f in report.all_files if "/" not in f and f.endswith(".py") and f not in allow
    ]
    if bad_root_py:
        report.warnings.append(
            f"WARN: CD-3 根目录 .py 不在白名单 ({', '.join(sorted(bad_root_py))})"
        )

    outside = [f for f in report.all_files if not is_allowed_code_path(f)]
    if outside:
        report.warnings.append(
            f"WARN: CD-4 train.py+workspace 外路径 ({', '.join(sorted(outside))})"
        )

    max_files = analyse_max_change_files(root)
    if len(report.scoped_files) > max_files:
        report.warnings.append(
            f"WARN: CD-5 变更文件数 {len(report.scoped_files)} > analyse_max_change_files={max_files}"
        )

    tiers = infer_tier_from_paths(report.scoped_files)
    if tiers:
        report.info_lines.append(f"INFO: CD-6 tier hints: {', '.join(tiers)}")

    return report
