"""Execute the migration plan: inject methods, update paths, modify files."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

# Allow `python executor.py` from any cwd
_SKILL_DIR = Path(__file__).resolve().parent
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))

from comparator import compare_side, extract_methods  # noqa: E402
from experiment_diff import compare_experiment_methods, generate_injection_patch  # noqa: E402
from profile_data import load_profile_boundaries  # noqa: E402


MigrationPlan = dict[str, Any]


def backup_project(project_root: str | Path) -> None:
    """Create timestamped backup of project."""
    root = Path(project_root)
    backup_dir = root / "__backup_migration__"
    backup_dir.mkdir(exist_ok=True)

    for subdir in ["contract", "workspace"]:
        src = root / subdir
        if src.exists():
            dst = backup_dir / subdir
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)

    exp = root / "experiment.py"
    if exp.exists():
        shutil.copy2(exp, backup_dir / "experiment.py")


def apply_experiment_injection(
    project_experiment: str | Path,
    template_experiment: str | Path,
    missing_methods: list[str],
) -> None:
    """Inject missing methods from template into project's experiment.py."""
    if not missing_methods:
        return

    patch = generate_injection_patch(template_experiment, missing_methods)
    project_path = Path(project_experiment)

    content = project_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    insert_idx = len(lines)

    in_class = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("class ExperimentBase"):
            in_class = True
        elif in_class and stripped.startswith("class ") and not stripped.startswith("class ExperimentBase"):
            insert_idx = i
            break
        elif in_class and stripped.startswith("class ExperimentBase"):
            insert_idx = i + 1

    patch_lines = patch.splitlines()
    lines = lines[:insert_idx] + patch_lines + lines[insert_idx:]

    project_path.write_text("\n".join(lines), encoding="utf-8")


def execute_plan(
    project_root: str | Path,
    template_root: str | Path,
    plan: MigrationPlan,
) -> dict[str, str]:
    """Execute the migration plan."""
    root = Path(project_root)
    tmpl = Path(template_root)
    results: dict[str, str] = {}

    backup_project(root)
    results["backup"] = "Created __backup_migration__/"

    project_exp = root / "experiment.py"
    if project_exp.exists() and plan.get("experiment_missing_methods"):
        apply_experiment_injection(
            project_exp,
            tmpl / "experiment.py",
            plan["experiment_missing_methods"],
        )
        results["experiment_injection"] = f"Injected: {plan['experiment_missing_methods']}"

    if plan.get("contract_changes"):
        results["contract"] = f"Changes needed: {plan['contract_changes']}"

    if plan.get("workspace_changes"):
        results["workspace"] = f"Changes needed: {plan['workspace_changes']}"

    return results


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python executor.py <project_root> <template_root> [plan_json]")
        sys.exit(1)

    project_root = sys.argv[1]
    template_root = sys.argv[2]
    plan = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}

    results = execute_plan(project_root, template_root, plan)
    for action, result in results.items():
        print(f"{action}: {result}")
