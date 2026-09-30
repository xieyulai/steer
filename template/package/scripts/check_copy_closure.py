# check_copy_closure.py
"""AST 闭包检查:扫描出仓产物内部 import,逐个验证目标文件存在。

用法:
  python3 check_copy_closure.py --repo-root <dest> [--source-root <src>]
rc 0 = 闭包完整;rc 1 = 缺文件(列出缺什么、建议)。
只查本仓内部模块(contract.*/workspace.*/lib.*/train/experiment);
第三方与标准库不查;相对 import 记 note 不判缺(v1 边界)。
"""
from __future__ import annotations

import argparse
import ast
import pathlib
import sys

_TOP_DIRS = {"contract": "contract", "workspace": "workspace", "lib": "scripts/lib"}
_ROOT_MODULES = ("train", "experiment")


def _candidates(repo: pathlib.Path, mod: str) -> list[pathlib.Path] | None:
    """mod 在仓库内可能指向的文件(任一存在即算满足);None = 外部依赖不查。"""
    parts = mod.split(".")
    head = parts[0]
    if head in _TOP_DIRS:
        base = repo / _TOP_DIRS[head]
        if len(parts) == 1:
            return [base / "__init__.py"]
        target = base.joinpath(*parts[1:])
        return [target.with_suffix(".py"), target / "__init__.py"]
    if head in _ROOT_MODULES:
        return [repo / (head + ".py")]
    return None


def _iter_imports(tree: ast.AST):
    """yield (候选模块名列表, 行号)。相对 import 候选为空(v1 不查)。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield [a.name], node.lineno
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                yield [], node.lineno
                continue
            mods = [node.module] if node.module else []
            mods += [f"{node.module}.{a.name}" for a in node.names]
            yield mods, node.lineno


def check_closure(repo: pathlib.Path, scan: list[pathlib.Path],
                  source_root: pathlib.Path | None = None) -> tuple[list[str], list[str]]:
    """返回 (problems, notes)。problem 一条 = 一处 import 缺目标文件。"""
    problems: list[str] = []
    notes: list[str] = []
    for f in scan:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except (OSError, SyntaxError) as e:
            notes.append(f"{f}: 语法解析失败,跳过({e})")
            continue
        for mods, lineno in _iter_imports(tree):
            rel = f.relative_to(repo)
            if not mods:
                notes.append(f"{rel}:{lineno} 相对 import 未展开(v1 不查)")
                continue
            internal = False
            satisfied = False
            for mod in mods:
                cand = _candidates(repo, mod)
                if cand is None:
                    continue
                internal = True
                if any(p.is_file() for p in cand):
                    satisfied = True
                    break
            if satisfied:
                continue
            head = mods[0].split(".")[0]
            if not internal:
                if (source_root is not None
                        and (source_root / f"{head}.py").is_file()
                        and not (repo / f"{head}.py").is_file()):
                    problems.append(
                        f"{rel}:{lineno} import {mods[0]} → 源根级模块 {head}.py 未复制;"
                        f"建议补进 migrate.yaml copy_targets 或手抄")
                continue
            problems.append(
                f"{rel}:{lineno} import {mods[0]} → 产物缺失;"
                f"建议补进 migrate.yaml copy_targets 或手抄")
    return problems, notes


def default_scan(repo: pathlib.Path) -> list[pathlib.Path]:
    """默认扫描面:contract/*.py + workspace/**/*.py + 根 train.py/experiment.py。"""
    files: list[pathlib.Path] = []
    files += sorted((repo / "contract").glob("*.py"))
    files += sorted(p for p in (repo / "workspace").rglob("*.py")
                    if "__pycache__" not in p.parts)
    for name in _ROOT_MODULES:
        p = repo / f"{name}.py"
        if p.is_file():
            files.append(p)
    return files


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="出仓产物 AST import 闭包检查")
    ap.add_argument("--repo-root", type=pathlib.Path, required=True)
    ap.add_argument("--source-root", type=pathlib.Path, default=None)
    ap.add_argument("files", nargs="*", type=pathlib.Path,
                    help="只查这些文件(缺省扫 contract/ workspace/ train.py experiment.py)")
    args = ap.parse_args(argv)
    repo = args.repo_root.resolve()
    scan = [p.resolve() for p in args.files] or default_scan(repo)
    problems, notes = check_closure(repo, scan, source_root=args.source_root)
    for n in notes:
        print(f"note: {n}", file=sys.stderr)
    for p in problems:
        print(f"缺: {p}")
    if problems:
        print(f"闭包检查失败: {len(problems)} 处 import 缺目标文件")
        return 1
    print(f"闭包检查通过: {len(scan)} 个文件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
