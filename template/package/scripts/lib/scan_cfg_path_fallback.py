"""Detect env/absolute-path fallbacks into ALL-CAPS cfg keys (config-only hygiene)."""
from __future__ import annotations

import ast
from pathlib import Path

_FIX_HINT = (
    "请改用 cfg[\"KEY\"] 强读（缺键 KeyError）；路径写入 config.json 或 train 模块常量，禁止 env 兜底"
)

_ABS_PATH_PREFIXES = ("/mnt/", "/home/", "/Users/")


def _caps_cfg_key(target: ast.expr) -> str | None:
    """Return ALL-CAPS cfg key from ``cfg[KEY]`` subscript, else None."""
    if not isinstance(target, ast.Subscript):
        return None
    if not isinstance(target.value, ast.Name) or target.value.id != "cfg":
        return None
    sl = target.slice
    if isinstance(sl, ast.Constant) and isinstance(sl.value, str) and sl.value.isupper():
        return sl.value
    if isinstance(sl, ast.Name) and sl.id.isupper():
        return sl.id
    return None


def _is_os_environ_access(node: ast.expr) -> bool:
    if isinstance(node, ast.Call):
        func = node.func
        return (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Attribute)
            and isinstance(func.value.value, ast.Name)
            and func.value.value.id == "os"
            and func.value.attr == "environ"
            and func.attr == "get"
        )
    if isinstance(node, ast.Subscript):
        val = node.value
        return (
            isinstance(val, ast.Attribute)
            and isinstance(val.value, ast.Name)
            and val.value.id == "os"
            and val.attr == "environ"
        )
    return False


def _is_abs_path_literal(node: ast.expr) -> bool:
    if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
        return False
    return node.value.startswith(_ABS_PATH_PREFIXES)


def _violation_message(path: Path, line: int, key: str, reason: str) -> str:
    return (
        f"{path}:{line}: cfg[{key!r}] {reason} — {_FIX_HINT}"
    )


def _check_assign(path: Path, key: str, value: ast.expr, line: int) -> str | None:
    if _is_os_environ_access(value):
        return _violation_message(path, line, key, "禁止 os.environ 兜底赋值")
    if _is_abs_path_literal(value):
        return _violation_message(path, line, key, "禁止绝对路径字面量兜底赋值")
    return None


def _scan_file(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [f"{path}: 无法解析 ({exc.msg})"]

    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                key = _caps_cfg_key(target)
                if key is None:
                    continue
                hit = _check_assign(path, key, node.value, node.lineno)
                if hit:
                    violations.append(hit)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            key = _caps_cfg_key(node.target)
            if key is None:
                continue
            hit = _check_assign(path, key, node.value, node.lineno)
            if hit:
                violations.append(hit)
    return violations


def _scan_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    train = repo_root / "train.py"
    if train.is_file():
        files.append(train)
    workspace = repo_root / "workspace"
    if workspace.is_dir():
        for path in sorted(workspace.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            files.append(path)
    return files


def find_cfg_path_fallback_violations(repo_root: Path) -> list[str]:
    """Return violation messages for train.py + workspace/**/*.py under repo_root."""
    violations: list[str] = []
    for path in _scan_files(repo_root):
        violations.extend(_scan_file(path))
    return violations
