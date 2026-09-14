#!/usr/bin/env python3
"""Official migration analysis CLI — profile, method comparison, layout guards.

Usage (from any cwd):
  export PYTHONPATH="<template_root>/skills/maintainer/auto-nn-init:<template_root>:$PYTHONPATH"
  python3 migration-compare.py --template-root <template_root> --project-root <project_root> [--json]

Exit 0: no hard failures (G-封装 / G-评估). G-布局 warnings may still appear.
Exit 1: hard guard failure or missing nn-config / contract files.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from comparator import (
    build_comparison_table,
    check_profile_facade_gate,
    check_rl_workspace_gate,
    check_root_py_layout,
    check_test_authority_gate,
    check_train_encapsulation,
    check_train_exp_dir_gate,
    compare_side,
    extract_methods,
)
from experiment_diff import compare_experiment_methods
from profile_data import load_profile_boundaries, require_profile, template_pkg


def run_compare(template_root: Path, project_root: Path) -> tuple[str, int, dict]:
    """Return (markdown, exit_code, summary_dict)."""
    project_root = project_root.resolve()
    template_root = template_root.resolve()

    profile = require_profile(project_root)
    boundaries = load_profile_boundaries(template_root)[profile]

    contract_path = project_root / "contract" / "__init__.py"
    workspace_path = project_root / "workspace" / "__init__.py"
    train_path = project_root / "train.py"

    if not contract_path.is_file():
        raise FileNotFoundError(f"缺少 {contract_path}")
    if not workspace_path.is_file():
        raise FileNotFoundError(f"缺少 {workspace_path}")
    if not train_path.is_file():
        raise FileNotFoundError(f"缺少 {train_path}")

    cm = extract_methods(contract_path)
    wm = extract_methods(workspace_path)
    cc = compare_side(cm, boundaries["contract_methods"])
    wc = compare_side(wm, boundaries["workspace_methods"])

    exp_inj: list[str] = []
    pe = project_root / "experiment.py"
    te = template_pkg(template_root) / "experiment.py"
    if pe.is_file() and te.is_file():
        diff = compare_experiment_methods(pe, te)
        exp_inj = diff["missing_methods"]

    train_violations = check_train_encapsulation(train_path)
    exp_dir_violations = check_train_exp_dir_gate(project_root)
    facade_violations = check_profile_facade_gate(project_root)
    rl_ws_violations = check_rl_workspace_gate(project_root)
    root_py = check_root_py_layout(project_root)
    test_auth = check_test_authority_gate(project_root)

    hard_fail = bool(
        train_violations or exp_dir_violations or facade_violations or rl_ws_violations or test_auth
    )
    exit_code = 1 if hard_fail else 0

    lines = [
        f"# migration-compare — profile=`{profile}`",
        f"- template_root: `{template_root}`",
        f"- project_root: `{project_root}`",
        "",
    ]
    if hard_fail:
        lines.append("**状态: FAIL**（G-封装 / G-路径 / G-门面 / G-评估 硬失败，修复后再进入 HARD-GATE）\n")
    elif root_py:
        lines.append("**状态: OK**（有 G-布局 警告，见下表）\n")
    else:
        lines.append("**状态: OK**\n")

    table = build_comparison_table(
        cc,
        wc,
        exp_inj,
        train_violations=train_violations or None,
        exp_dir_violations=exp_dir_violations or None,
        facade_violations=(facade_violations or []) + (rl_ws_violations or []) or None,
        root_py_unexpected=root_py or None,
        test_authority_violations=test_auth or None,
    )
    lines.append(table)

    retain = sum(1 for c in cc + wc if c["action"] == "保留")
    total = len(cc) + len(wc)
    summary = {
        "profile": profile,
        "exit_code": exit_code,
        "hard_fail": hard_fail,
        "contract_actions": {c["method"]: c["action"] for c in cc},
        "workspace_actions": {c["method"]: c["action"] for c in wc},
        "experiment_injections": exp_inj,
        "train_violations": len(train_violations),
        "test_authority_violations": len(test_auth),
        "root_py_unexpected": root_py,
        "retain_count": retain,
        "method_total": total,
        "fast_path_eligible": exit_code == 0 and retain == total and not exp_inj,
    }
    return "\n".join(lines), exit_code, summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Migration analysis (official CLI)")
    parser.add_argument("--template-root", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--json", action="store_true", help="Print summary JSON to stderr")
    args = parser.parse_args()

    try:
        md, code, summary = run_compare(args.template_root, args.project_root)
    except Exception as e:
        print(f"migration-compare FAIL: {e}", file=sys.stderr)
        return 1

    print(md)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2), file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
