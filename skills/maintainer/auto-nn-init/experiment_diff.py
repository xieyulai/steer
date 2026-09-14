"""Analyze experiment.py differences between project and template.

Identify which methods from the template's ExperimentBase are missing in the project's
experiment.py, so they can be injected.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import TypedDict


class ExperimentDiff(TypedDict):
    missing_methods: list[str]
    extra_methods: list[str]
    different_methods: list[str]


def extract_experiment_methods(file_path: str | Path) -> dict[str, str]:
    """Extract method names and their source code blocks from experiment.py."""
    code = Path(file_path).read_text(encoding="utf-8")
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return _extract_methods_regex(code)

    methods: dict[str, str] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "ExperimentBase":
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods[item.name] = _get_method_source(item, code)

    return methods


def _extract_methods_regex(code: str) -> dict[str, str]:
    """Fallback regex extraction."""
    methods: dict[str, str] = {}
    pattern = r"def\s+(\w+)\s*\([^)]*\)\s*(?:->\s*[^:]+)?\s*:(?:\s*\.\.\.)?"

    for m in re.finditer(pattern, code):
        methods[m.group(1)] = m.group(0)
    return methods


def _get_method_source(node: ast.FunctionDef | ast.AsyncFunctionDef, source: str) -> str:
    start_line = node.lineno - 1
    end_line = node.end_lineno
    lines = source.splitlines()
    return "\n".join(lines[start_line:end_line])


def compare_experiment_methods(
    project_experiment: str | Path,
    template_experiment: str | Path,
) -> ExperimentDiff:
    """Compare project experiment.py against template."""
    project_methods = extract_experiment_methods(project_experiment)
    template_methods = extract_experiment_methods(template_experiment)

    missing: list[str] = []
    extra: list[str] = []
    different: list[str] = []

    template_method_names = {
        "test", "build_model", "build_loss", "build_optimizer",
        "build_scheduler", "build_dataloader",
        "should_keep", "preflight_check", "finalize_run",
        "pick_keeper_exp_dir", "finalize_round",
        "save_checkpoint", "append_tsv_row", "append_jsonl_record",
        "report_results", "log_step", "progress_log_dict",
        "report_train_exp_snapshot", "report_train_artifacts",
        "snapshot_code", "snapshot_env",
        "write_slot_keep_suggestion", "write_evaluation_result", "_build_evaluation_result",
    }

    for name in sorted(template_method_names):
        if name not in project_methods and name in template_methods:
            missing.append(name)
        elif name in project_methods and name not in template_methods:
            extra.append(name)
        elif name in project_methods and name in template_methods:
            proj_impl = project_methods[name]
            templ_impl = template_methods[name]
            proj_is_abstract = "raise NotImplementedError" in proj_impl
            templ_is_abstract = "raise NotImplementedError" in templ_impl
            if not (proj_is_abstract and templ_is_abstract):
                if not templ_is_abstract:
                    different.append(name)

    return ExperimentDiff(
        missing_methods=missing,
        extra_methods=extra,
        different_methods=different,
    )


def generate_injection_patch(
    template_experiment: str | Path,
    missing_methods: list[str],
) -> str:
    """Generate code patch to inject missing methods from template into project."""
    template_methods = extract_experiment_methods(template_experiment)

    patches: list[str] = []
    for method_name in missing_methods:
        if method_name in template_methods:
            patches.append("\n    # --- injected from template ---\n")
            patches.append(template_methods[method_name])
            patches.append("    # --- end injection ---\n")

    return "\n".join(patches)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python experiment_diff.py <project_experiment.py> <template_experiment.py>")
        sys.exit(1)

    diff = compare_experiment_methods(sys.argv[1], sys.argv[2])
    print("Missing in project:", diff["missing_methods"])
    print("Extra in project:", diff["extra_methods"])
    print("Different implementations:", diff["different_methods"])
