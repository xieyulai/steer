"""Detect SCENARIO_ID / scenario_id property regressions under contract/."""
from __future__ import annotations

import ast
from pathlib import Path


def _is_property_decorated(func: ast.FunctionDef) -> bool:
    for dec in func.decorator_list:
        if isinstance(dec, ast.Name) and dec.id == "property":
            return True
        if isinstance(dec, ast.Attribute) and dec.attr == "property":
            return True
    return False


def _returns_scenario_id_constant(func: ast.FunctionDef) -> bool:
    for node in ast.walk(func):
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        val = node.value
        if isinstance(val, ast.Name) and val.id == "SCENARIO_ID":
            return True
        if isinstance(val, ast.Attribute) and val.attr == "SCENARIO_ID":
            return True
    return False


def _scan_file(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [f"{path}: 无法解析 ({exc.msg})"]

    violations: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "SCENARIO_ID":
                    violations.append(
                        f"{path}: 模块级 SCENARIO_ID 赋值（场景号属 cfg + F1，不在 contract）"
                    )
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == "SCENARIO_ID":
                violations.append(
                    f"{path}: 模块级 SCENARIO_ID 赋值（场景号属 cfg + F1，不在 contract）"
                )

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "scenario_id":
            continue
        if not _is_property_decorated(node):
            continue
        if _returns_scenario_id_constant(node):
            violations.append(
                f"{path}: Contract.scenario_id property 返回 SCENARIO_ID 常量（应迁出到 cfg）"
            )

    return violations


def find_scenario_id_in_contract(repo_root: Path) -> list[str]:
    """Return list of violation messages for paths under contract/."""
    contract_dir = repo_root / "contract"
    if not contract_dir.is_dir():
        return []

    violations: list[str] = []
    for path in sorted(contract_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        violations.extend(_scan_file(path))
    return violations
