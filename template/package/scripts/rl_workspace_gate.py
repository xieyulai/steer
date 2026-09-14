#!/usr/bin/env python3
"""RL profile 迁后硬门禁：D2 build_learner 须走 contract.prepare_data；E3 evaluate 默认须 contract.test。

退出码 0 = 通过；1 = 违规（打印 rule/detail/fix）。

若 F1 明确选用 E4②（evaluate 独立轻量），须在 README.md 含一行：``E4_EVALUATE_INDEPENDENT: yes``。
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import yaml


def _load_profile(repo_root: Path) -> str:
    p = repo_root / "nn-config.yaml"
    if not p.is_file():
        return ""
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return str(data.get("profile", "")).strip()


def _e3_independent(repo_root: Path) -> bool:
    readme = repo_root / "README.md"
    if not readme.is_file():
        return False
    return bool(re.search(r"E4_EVALUATE_INDEPENDENT\s*:\s*yes", readme.read_text(encoding="utf-8"), re.I))


def _method_body(src: str, class_name: str, method_name: str) -> str:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return ""
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return ast.get_source_segment(src, item) or ""
    return ""


def check(repo_root: str | Path) -> list[dict[str, str]]:
    root = Path(repo_root).resolve()
    if _load_profile(root) != "rl":
        return []

    ws = root / "workspace" / "__init__.py"
    if not ws.is_file():
        return [{"rule": "D2", "detail": "缺少 workspace/__init__.py", "fix": "创建 Workspace 门面"}]

    src = ws.read_text(encoding="utf-8")
    violations: list[dict[str, str]] = []

    bl = _method_body(src, "Workspace", "build_learner")
    if bl and "prepare_data" not in bl:
        violations.append({
            "rule": "D2",
            "detail": "build_learner 未调用 contract.prepare_data（勿仅读 DATA_DIR/NN_DATA_DIR）",
            "fix": "dataset_path = Contract().prepare_data(cfg) 后传入 make_eval_env",
        })

    if not _e3_independent(root):
        ev = _method_body(src, "Workspace", "evaluate")
        if ev and "contract.test" not in ev.replace(" ", "") and "Contract().test" not in ev:
            violations.append({
                "rule": "E3",
                "detail": "evaluate 未委托 contract.test（训内与台账口径不一致）",
                "fix": "return Contract().test(learner, self, shared_context=shared_context)；或 README 声明 E4_EVALUATE_INDEPENDENT: yes",
            })

    return violations


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    v = check(root)
    if not v:
        return 0
    for item in v:
        print(f"[{item['rule']}] {item['detail']} → {item['fix']}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
