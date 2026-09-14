#!/usr/bin/env python3
"""Strict layout check: business project root must match template/package (+ data/).

Exit 0 on success, 1 on failure. Prints [verify] lines to stdout/stderr.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _nn_state_path(repo: Path, key: str) -> Path:
    return repo / ".auto-nn" / key


def _resolve_maintainer_root(repo: Path) -> Path | None:
    """与 ``nn_resolve_template_root`` 同序：env > skills symlink > ``.auto-nn/template-root``。

    跨机时文件里可能是别机绝对路径；不得只读该文件，否则 layout 永久 FAIL。
    """
    import os
    import subprocess

    lib = Path(__file__).resolve().parent / "lib" / "nn-state.sh"
    if not lib.is_file():
        # 最小回退：仅文件（无 bash 解析器时）
        marker = _nn_state_path(repo, "template-root")
        if marker.is_file():
            cand = Path(marker.read_text(encoding="utf-8").strip())
            if cand.is_dir():
                return cand
        env = os.environ.get("NN_TEMPLATE_ROOT", "").strip()
        return Path(env) if env and Path(env).is_dir() else None
    try:
        out = subprocess.run(
            ["bash", "-c", f'source "{lib}" && nn_resolve_template_root "{repo}"'],
            capture_output=True,
            text=True,
            check=False,
            env=os.environ.copy(),
        )
    except OSError:
        return None
    if out.returncode != 0:
        return None
    resolved = (out.stdout or "").strip()
    return Path(resolved) if resolved else None


def _template_package_root(repo: Path) -> Path | None:
    troot = _resolve_maintainer_root(repo)
    if troot is None:
        return None
    for candidate in (
        troot / "template" / "package",
        troot / "template",
        troot,
    ):
        if (candidate / "profiles.yaml").is_file() and (candidate / "train.py").is_file():
            return candidate
    return None


# Legacy / whole-copy migration artifacts — always FAIL
FORBIDDEN_ROOT_NAMES: frozenset[str] = frozenset(
    {
        "results.tsv",
        "results.jsonl",
        "progress_latest15.txt",
        "parallel-agents.sh",
        "launch_m.sh",
        "init.sh",
        "run-nn-agent.sh",
        "new-project.sh",
        "NEW_PROJECT_CHECKLIST.md",
        "test_evaluation_all.json",
        ".new-project-tsv-header.err",
        "NN_PROFILE",
        "skeletons",
        "LOGS",
        "RUNS",
        "logs",
        "automation-logs-nn",
    }
)

FORBIDDEN_ROOT_PREFIXES: tuple[str, ...] = ("ledger_backup_",)

# Python / 测试运行时产物 — layout 一律不判断（靠 .gitignore）
IGNORED_RUNTIME_DIRS: frozenset[str] = frozenset(
    {"__pycache__", ".pytest_cache", ".venv", "venv"}
)


def _skip_runtime_artifact(name: str) -> bool:
    return name in IGNORED_RUNTIME_DIRS or name.endswith((".pyc", ".pyo"))


FORBIDDEN_SCRIPT_NAMES: frozenset[str] = frozenset(
    {
        "init.sh",
        "generate-profile-locks.sh",
        "new-project.sh",
    }
)

# 业务仓可选脚本（sync / Modify-Scenario-complete 产生，不在 template/package 镜像内）
OPTIONAL_SCRIPT_NAMES: frozenset[str] = frozenset(
    {
        "scenario_backfill_map.tsv",
    }
)

# Allowed beyond template/package top-level (business / governance)
EXTRA_ALLOWED_ROOT: frozenset[str] = frozenset(
    {
        "data",
        "_runs_legacy",
        "poetry.lock",
        "poetry.toml",
        ".auto-nn",
        ".gitignore",
        # reflect / auto-run 运行时产物（PROTOCOL L1、KEEP 权重、进度表）
        "references",
        "saved",
        "docs",
        # ABCDE 模板（由 governance-sync §ABCDE 段 cp 下来）
        "skills",
        # 用户本地配置（settings.local.json 等，允许保留）
        ".claude",
        # IDE 和编辑器配置
        ".vscode",
        ".idea",
        ".fleet",
        # 本地配置文件
        "config.json",
        "template",
        # adapter 场景：外部框架源码入仓（mammoth 等 immutable 3rd-party）
        "_vendor",
        # 业务仓自留的分析/出图目录（multiseed 锚点 / RUNLOG / 冻盘台账），不属模板布局
        "_paper",
        # 其他常见忽略项
        ".worktrees",
    }
)

GREENFIELD_SOURCE_MARKERS: frozenset[str] = frozenset(
    {
        "",
        "-",
        "none",
        "# greenfield",
        "# entry-b",
        "# entry-b greenfield",
    }
)

REQUIRED_ROOT_FILES: tuple[str, ...] = (
    "README.md",
    "PROTOCOL.md",
    "CLAUDE.md",
    "EXPERIENCE.md",
    "pyproject.toml",
    "profiles.yaml",
    "nn-config.yaml",
    "train.py",
    "experiment.py",
    "auto-nn-run.sh",
    "reflect.py",
)

REQUIRED_DIRS: tuple[str, ...] = ("contract", "workspace", "scripts", "_runs")

REQUIRED_UNDER_RUNS: tuple[str, ...] = ("logs", "agent")

REQUIRED_SCRIPTS: tuple[str, ...] = (
    "auto-run-batch-tail.sh",
    "check_exploration_stamp.py",
    "claude_stream_summarize.py",
    "claude_stream_result_watchdog.py",
    "d2_data_split_gate.py",
    "e_feedback.py",
    "govern-runs.sh",
    "governance-sync.sh",
    "nn-doctor.sh",
    "prune-runs.py",
    "regen_results_tsv.py",
    "sync_exploration_ledger.py",
    "clear-runs.sh",
    "clear_inspect.py",
    "rl_workspace_gate.py",
    "scenario_policy_gate.py",
    "smoke-check.sh",
    "sync_ledger.py",
    "verify-migration-complete.sh",
    "verify_project_layout.py",
    "wait-train.sh",
)


def _ok(msg: str) -> None:
    print(f"[verify] OK: {msg}")


def _fail(msg: str, errors: list[str]) -> None:
    errors.append(msg)
    print(f"[verify] FAIL: {msg}", file=sys.stderr)


def _warn(msg: str) -> None:
    print(f"[verify] WARN: {msg}", file=sys.stderr)


def _allowed_root_names(tpkg: Path) -> set[str]:
    allowed = {p.name for p in tpkg.iterdir() if p.name != "__pycache__"}
    allowed |= EXTRA_ALLOWED_ROOT
    return allowed


def _allowed_script_names(tpkg: Path) -> set[str]:
    scripts = tpkg / "scripts"
    if not scripts.is_dir():
        return set(REQUIRED_SCRIPTS)
    return {p.name for p in scripts.iterdir() if p.name != "__pycache__"}


def _read_migration_source(repo: Path) -> str:
    p = _nn_state_path(repo, "migration-source")
    if not p.is_file():
        return ""
    raw = p.read_text(encoding="utf-8").strip()
    for line in raw.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return raw.splitlines()[0].strip() if raw else ""


def check_layout(repo: Path, *, is_template_root: bool = False) -> list[str]:
    errors: list[str] = []
    repo = repo.resolve()

    if is_template_root or (repo / ".template-maintainer").is_file():
        _ok("模板根：跳过严格目录布局检查")
        return errors

    tpkg = _template_package_root(repo)
    if tpkg is None:
        _fail(
            "无法解析 template-root（NN_TEMPLATE_ROOT / skills symlink / .auto-nn/template-root）"
            "或无法定位 template/package — 先 install.sh / export NN_TEMPLATE_ROOT / governance-sync",
            errors,
        )
        return errors

    allowed_root = _allowed_root_names(tpkg)
    allowed_scripts = _allowed_script_names(tpkg)

    # ── .auto-nn/migration-source（入口 A 必填；入口 B 为 # greenfield）──
    src_file = _nn_state_path(repo, "migration-source")
    if not src_file.is_file():
        _fail(
            "缺少 .auto-nn/migration-source — 入口 A 写 source_root 绝对路径；"
            "入口 B 由 new-project.sh 写入「# greenfield」",
            errors,
        )
    else:
        raw_all = src_file.read_text(encoding="utf-8").strip()
        src_line = _read_migration_source(repo)
        norm = raw_all.lower().strip() if raw_all.startswith("#") else src_line.lower().strip()
        if norm in GREENFIELD_SOURCE_MARKERS or src_line.lower() in {"", "-", "none"}:
            _ok("迁移落点: 入口 B（greenfield，无 source_root）")
        elif src_line and Path(src_line).is_dir():
            src_abs = Path(src_line).resolve()
            if src_abs == repo:
                _fail(f"违反禁止原地迁移: project_root 与 source 相同 ({src_abs})", errors)
            else:
                _ok(f"迁移落点: source={src_abs} ≠ target={repo}")
        else:
            _fail(f".auto-nn/migration-source 无效（非 greenfield 且目录不存在）: {src_line or raw_all!r}", errors)

    # ── manifest 必备 ──
    for rel in REQUIRED_ROOT_FILES:
        if not (repo / rel).is_file():
            _fail(f"缺少必备文件: {rel}（须 new-project.sh 或 governance-sync）", errors)
    for d in REQUIRED_DIRS:
        if not (repo / d).is_dir():
            _fail(f"缺少必备目录: {d}/", errors)
    for sub in REQUIRED_UNDER_RUNS:
        if not (repo / "_runs" / sub).is_dir():
            _fail(f"缺少 _runs/{sub}/", errors)
    if not (repo / "_runs" / "results.tsv").is_file():
        _fail("缺少 _runs/results.tsv", errors)

    refs = repo / "references"
    if refs.is_dir():
        for p in refs.iterdir():
            if p.is_file() and p.name.endswith("_auto_reflected.md"):
                _fail(
                    f"references/ 根目录禁止平铺 auto 长文: {p.name} — 移至 references/auto/",
                    errors,
                )
        auto_d = refs / "auto"
        manual_d = refs / "manual"
        if auto_d.is_dir() or manual_d.is_dir():
            _ok("references/ 含 manual/ 或 auto/ 子目录")
    else:
        _ok("references/ 未创建（可选）")

    scripts_dir = repo / "scripts"
    for s in REQUIRED_SCRIPTS:
        if not (scripts_dir / s).is_file():
            _fail(f"缺少 scripts/{s}", errors)

    # ── 禁止项（整包拷贝指纹）──
    for name in sorted(FORBIDDEN_ROOT_NAMES):
        if (repo / name).exists():
            _fail(
                f"禁止保留旧仓根目录项: {name} — 非模板标准（整包拷贝残留）；"
                "删除或移至 _runs_legacy/",
                errors,
            )
    for entry in repo.iterdir():
        for prefix in FORBIDDEN_ROOT_PREFIXES:
            if entry.name.startswith(prefix):
                _fail(
                    f"禁止保留旧仓根目录项: {entry.name} — 删除或移至 _runs_legacy/",
                    errors,
                )
                break

    # ── 根目录白名单（相对 template/package + data 等）──
    extras: list[str] = []
    for entry in sorted(repo.iterdir(), key=lambda p: p.name):
        name = entry.name
        if name == ".git":
            continue
        if _skip_runtime_artifact(name):
            continue
        if name in allowed_root:
            continue
        if name in FORBIDDEN_ROOT_NAMES or any(
            name.startswith(p) for p in FORBIDDEN_ROOT_PREFIXES
        ):
            continue
        extras.append(name)

    if extras:
        for name in extras:
            _fail(
                f"多余根目录项: {name} — 不在 template/package 白名单；"
                "删除、合并进 data/contract/workspace，或移至 _runs_legacy/",
                errors,
            )

    # ── scripts/ 仅允许模板包内脚本 ──
    if scripts_dir.is_dir():
        for s in sorted(scripts_dir.iterdir(), key=lambda p: p.name):
            if _skip_runtime_artifact(s.name) or s.name == "lib":
                continue
            if s.name in FORBIDDEN_SCRIPT_NAMES:
                _fail(f"禁止 scripts/{s.name} — 迁完须删除（CHECKLIST §2）", errors)
            elif s.name not in allowed_scripts and s.name not in OPTIONAL_SCRIPT_NAMES:
                _fail(
                    f"多余 scripts/{s.name} — 不在 template/package/scripts；"
                    "移入 workspace/ 或删除",
                    errors,
                )

    # ── 根目录遗留训练日志 ──
    for pattern in ("run.log", "run2.log", "pipeline.log"):
        if (repo / pattern).is_file():
            _fail(f"根目录遗留 {pattern} — 日志须在 _runs/logs/", errors)

    # ── 迁前 KEEP 路径（方案 B：exp_dir + saved/keeper.json）──
    legacy_runs_keep = repo / "_runs" / "keep"
    if legacy_runs_keep.exists():
        _warn(
            "存在迁前遗留 _runs/keep/ — 请删除；权重在 _runs/exp/<keeper>/best_model.pt，"
            "指针用: poetry run python -m contract write-keeper --exp-dir <keeper>",
        )
    legacy_saved_keep = repo / "saved" / "keep"
    if legacy_saved_keep.is_dir():
        try:
            has_pt = any(legacy_saved_keep.glob("*.pt"))
        except OSError:
            has_pt = False
        if has_pt:
            _warn(
                "saved/keep/*.pt 为迁前权重复制品 — 已废弃；KEEP 后请用 "
                "poetry run python -m contract write-keeper --exp-dir <keeper>",
            )

    if not errors:
        _ok("根目录与 scripts/ 布局符合 template/package 白名单")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify business project layout vs template/package")
    ap.add_argument("repo_root", nargs="?", default=".", type=Path)
    ap.add_argument(
        "--template-root",
        action="store_true",
        help="Skip checks (template maintainer repo)",
    )
    args = ap.parse_args()
    repo = args.repo_root.resolve()
    errs = check_layout(repo, is_template_root=args.template_root)
    if errs:
        print(
            "[verify] 布局未通过 — 推荐: new-project.sh 新建 target，再移植 contract/workspace/train.py；"
            "勿 cp -r 旧仓",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
