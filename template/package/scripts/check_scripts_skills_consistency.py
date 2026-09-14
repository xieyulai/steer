#!/usr/bin/env python3
"""维护仓 CI：scripts↔skills 一致性 4 步 — 对照 .scripts_skills_manifest.yaml。

R1 mirror：scripts/ 是 template/package/scripts/ 的 symlink（业务仓生效）
R2 caller：每个 cli 脚本的 ≥1 caller 文件存在（路径核对）
R3 governance-sync cp：每个 manifest 脚本名出现在 governance-sync.sh cp 块
R4 caller 实际引用：每个 caller 文件实际 grep 到 `scripts/<name>`

失败 → stderr 列 FAIL 行；exit 1。CI 兜底。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]  # template/package/scripts/X.py → parents[3] = 模板仓根
PKG = ROOT / "template" / "package"
SCRIPTS_PKG = PKG / "scripts"
MANIFEST = SCRIPTS_PKG / ".scripts_skills_manifest.yaml"
GOVSYNC = SCRIPTS_PKG / "governance-sync.sh"


def _load_manifest() -> list[dict]:
    import yaml  # 局部 import 允许缺包时报清晰错
    with MANIFEST.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("scripts") or []


def _r1_mirror() -> list[str]:
    """R1: 维护仓根目录的 scripts/ 必须是 symlink → template/package/scripts/。

    业务仓模式由 governance-sync.sh 端到端保证；本检查只验本地结构。
    """
    fails: list[str] = []
    repo_root_scripts = ROOT / "scripts"
    if not repo_root_scripts.is_symlink():
        fails.append(
            f"R1 mirror: {repo_root_scripts} 非 symlink（r23 铁律：scripts/ 必须 symlink 到 template/package/scripts/）"
        )
        return fails
    target = repo_root_scripts.resolve()
    if target != SCRIPTS_PKG.resolve():
        fails.append(
            f"R1 mirror: {repo_root_scripts} → {target}（期望 {SCRIPTS_PKG}）"
        )
    return fails


def _r2_caller_paths(entries: list[dict]) -> list[str]:
    fails: list[str] = []
    for entry in entries:
        if entry["type"] != "cli":
            continue
        name = entry["name"]
        for caller_rel in entry["callers"]:
            caller_path = ROOT / caller_rel
            if not caller_path.is_file():
                fails.append(f"R2 caller: {name} 的 caller {caller_rel} 不存在")
    return fails


def _r3_governance_sync_cp(entries: list[dict]) -> list[str]:
    r"""R3: manifest 里每个 name 都得在 governance-sync.sh cp 块（业务仓 sync 才会落盘）。

    用 \b 单词边界匹配 — 兼容 for-in-loop ``name \``、``name; do``、
    ``cp "$TEMPLATE_PKG/scripts/name"``、echo 包裹 ``name`` 四种写法。
    """
    if not GOVSYNC.is_file():
        return [f"R3 governance-sync: {GOVSYNC} 不存在"]
    text = GOVSYNC.read_text(encoding="utf-8")
    fails: list[str] = []
    for entry in entries:
        name = entry["name"]
        if not re.search(rf"\b{re.escape(name)}\b", text):
            fails.append(
                f"R3 governance-sync cp: {name} 不在 cp 块（业务仓 sync 时不会落盘）"
            )
    return fails


def _r4_caller_grep(entries: list[dict]) -> list[str]:
    """R4: caller 文件实际含 `scripts/<name>` 或 `python3 ... <name>` 的引用。

    防 manifest 写了 caller 但文件里没真引用的「声明漂移」。
    governance-sync.sh caller 特例：含 `python3` + name 也算。
    """
    fails: list[str] = []
    for entry in entries:
        if entry["type"] != "cli":
            continue
        name = entry["name"]
        for caller_rel in entry["callers"]:
            caller_path = ROOT / caller_rel
            if not caller_path.is_file():
                continue  # R2 已报
            text = caller_path.read_text(encoding="utf-8")
            if (
                f"scripts/{name}" in text
                or re.search(rf"python3\s+\S*{re.escape(name)}", text)
            ):
                break
        else:
            fails.append(
                f"R4 caller grep: {name} 的 caller 文件无 `scripts/{name}` 或 `python3 ... {name}` 引用"
            )
    return fails


def run_check(template_root: Path) -> tuple[bool, list[str]]:
    global ROOT, PKG, SCRIPTS_PKG, MANIFEST, GOVSYNC  # noqa: PLW0603
    ROOT = template_root.resolve()
    PKG = ROOT / "template" / "package"
    SCRIPTS_PKG = PKG / "scripts"
    MANIFEST = SCRIPTS_PKG / ".scripts_skills_manifest.yaml"
    GOVSYNC = SCRIPTS_PKG / "governance-sync.sh"

    if not MANIFEST.is_file():
        return False, [f"manifest 不存在: {MANIFEST}"]
    entries = _load_manifest()
    fails: list[str] = []
    fails += _r1_mirror()
    fails += _r2_caller_paths(entries)
    fails += _r3_governance_sync_cp(entries)
    fails += _r4_caller_grep(entries)
    return (len(fails) == 0, fails)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--template-root",
        type=Path,
        default=Path(__file__).resolve().parents[3],
        help="模板维护仓根（默认本脚本上三级 = 仓根）",
    )
    args = parser.parse_args()
    ok, fails = run_check(args.template_root)
    if ok:
        print("PASS: scripts↔skills 4 步一致")
        return 0
    for f in fails:
        print(f"FAIL: {f}", file=sys.stderr)
    print(
        f"FAIL: {len(fails)} 项不过；补 .scripts_skills_manifest.yaml + governance-sync cp + SKILL.md 命令",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
