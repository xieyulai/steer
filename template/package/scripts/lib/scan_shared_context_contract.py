"""禁止 shared_context 承载 / 读取 contract 实例（方案 B）。"""
from __future__ import annotations

import ast
from pathlib import Path

_FIX = (
    "shared_context 不得放/读 contract；"
    "题面对象经函数参数或 cfg/prepare_data/ws 显式属性传递（CLAUDE shared_context；ADR-11）"
)


def _is_shared_context_name(node: ast.expr) -> bool:
    return isinstance(node, ast.Name) and node.id == "shared_context"


def _is_contract_str(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value == "contract"


def _scan_file(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        return [f"{path}: 无法解析 ({exc})"]

    hits: list[str] = []
    for node in ast.walk(tree):
        # shared_context.get("contract", ...)
        if isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "get"
                and _is_shared_context_name(func.value)
                and node.args
                and _is_contract_str(node.args[0])
            ):
                hits.append(f"{path}:{node.lineno}: shared_context.get('contract') — {_FIX}")
        # shared_context["contract"] 读或写目标
        if isinstance(node, ast.Subscript) and _is_shared_context_name(node.value):
            sl = node.slice
            if _is_contract_str(sl):
                hits.append(f"{path}:{node.lineno}: shared_context['contract'] — {_FIX}")
    return hits


def _scan_files(repo_root: Path) -> list[Path]:
    root = Path(repo_root)
    files: list[Path] = []
    train = root / "train.py"
    if train.is_file():
        files.append(train)
    for sub in ("workspace", "contract"):
        d = root / sub
        if not d.is_dir():
            continue
        for path in sorted(d.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            files.append(path)
    return files


def find_shared_context_contract_violations(repo_root: Path) -> list[str]:
    """返回违规说明列表；空 = 通过。"""
    out: list[str] = []
    for path in _scan_files(Path(repo_root).resolve()):
        out.extend(_scan_file(path))
    return out
