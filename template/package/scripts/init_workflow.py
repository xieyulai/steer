"""Detect init workflow from target_root + source_root.

Three workflows drive the ABCDE init redesign (single-axis classification):
    BUILD    — no source_root, brand-new project from skeleton
    MIGRATE  — source_root ≠ target_root, port legacy code in
    UPDATE   — source_root == target_root, re-run init on same project

Decision tree (replaces old scenario classify() in init_scenarios.py):
    no source_root                       -> BUILD
    source_root == target_root           -> UPDATE
    source_root != target_root           -> MIGRATE

This file is the PR1 data-layer landing: behavior is identical to the
old init_scenarios.classify(), but exposes a single axis (workflow only).
PR2 will add detect() that combines workflow + object_type in one call.

Pattern split (MIGRATE only): old scenario 'migration' → port_to_contract;
old scenario 'adapter' → workspace_wrapper. PR1 keeps the old split
gates inside the scenarios/migrate.yaml `patterns:` key, not yet
queried by code.
"""
from __future__ import annotations

import argparse
import enum
from dataclasses import dataclass
from pathlib import Path


class Workflow(enum.Enum):
    """Init workflow classification (replaces Scenario)."""
    BUILD = "build"
    MIGRATE = "migrate"
    UPDATE = "update"


def classify(repo_root: Path | str, source_root: Path | str | None) -> Workflow:
    """Return init workflow (PR1: behavior-equivalent to old init_scenarios.classify).

    BUILD:    no source_root
    MIGRATE:  source_root present, no contract/ OR contract/ but not same dir
    UPDATE:   source_root == repo_root (legacy reinit case)

    Note: in PR1 we keep the contract/ check (old behavior) so existing
    callers see no change. PR2 will simplify this — only (None check +
    same-dir check) matters for single-axis.
    """
    repo_root = Path(repo_root)
    if source_root is None or source_root == "":
        return Workflow.BUILD
    src = Path(source_root)
    has_contract = (src / "contract").exists()
    if not has_contract:
        return Workflow.MIGRATE
    same = (src.resolve() == repo_root.resolve())
    return Workflow.UPDATE if same else Workflow.MIGRATE


def resolve_workflow(repo_root: Path | str, source_root: Path | str | None,
                     override: str | None = None) -> Workflow:
    """Resolve final workflow: override wins; else classify() auto-detect."""
    if override:
        try:
            return Workflow(override)
        except ValueError as e:
            valid = ", ".join(w.value for w in Workflow)
            raise ValueError(
                f"未知 --workflow={override!r};可选: {valid}"
            ) from e
    return classify(repo_root, source_root)


@dataclass(frozen=True)
class DetectionResult:
    """v1.33.0 — 单轴检测结果:workflow + object_type + optional pattern + framework_kind。

    framework_kind 仅在 object_type == "framework" 时有值;其他情况为 None。
    """
    workflow: Workflow
    object_type: str  # "data" | "code" | "framework"
    pattern: str | None = None  # only set when workflow=MIGRATE: "port_to_contract" | "workspace_wrapper"
    framework_kind: str | None = None  # "mammoth" | "lightning" | ... | None


# Path segments skipped when scanning for .py / @register_* (object_type).
_SKIP_SCAN_PARTS = frozenset({
    "_backend_",
    "site-packages",
    "_runs",
    ".venv",
    "__pycache__",
    ".git",
})


def _iter_scan_py(scan_root: Path):
    """Yield .py files under scan_root, skipping noise / venv / ledger trees."""
    for py in scan_root.rglob("*.py"):
        if _SKIP_SCAN_PARTS.intersection(py.parts):
            continue
        yield py


def detect(repo_root: Path | str, source_root: Path | str | None,
           force_workflow: str | None = None,
           framework_hint: dict | None = None) -> DetectionResult:
    """PR2: single-axis detection. Replaces _classify_object_type().

    Two axes:
      workflow (3): from source_root presence + same-dir check
      object_type (3): from .py presence + @register_* on the object-type scan root
      pattern (2, only when workflow=MIGRATE): from contract/ presence
      framework_kind (optional, v1.33.0): when object_type=framework, infer from module/file hints

    Object-type scan root (2026-07-20):
      MIGRATE + source_root set → scan source_root (not scaffolded target)
      else (BUILD / UPDATE) → scan repo_root

    framework_hint is optional — only used when source_root points to a
    site-packages path (then @register_* detection may miss).
    """
    repo_root = Path(repo_root)
    workflow = resolve_workflow(repo_root, source_root, override=force_workflow)

    # object_type: MIGRATE looks at source; BUILD/UPDATE look at repo
    if workflow == Workflow.MIGRATE and source_root:
        scan_root = Path(source_root)
    else:
        scan_root = repo_root

    module_name_hint: str | None = None
    register_hit = False
    has_py = False
    for py in _iter_scan_py(scan_root):
        has_py = True
        try:
            content = py.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "@register_" in content:
            register_hit = True
            module_name_hint = py.stem
            break

    if framework_hint and framework_hint.get("mutability") == "register":
        register_hit = True
        has_py = True  # hint implies a framework-shaped source

    if not has_py:
        object_type = "data"
    else:
        object_type = "framework" if register_hit else "code"

    # pattern: only when workflow=MIGRATE
    pattern = None
    if workflow == Workflow.MIGRATE and source_root is not None:
        src = Path(source_root)
        pattern = "workspace_wrapper" if (src / "contract").exists() else "port_to_contract"

    # v1.33.0 — 推断 framework_kind(只在 object_type=framework 时)
    framework_kind_value: str | None = None
    if object_type == "framework":
        try:
            from scripts.lib.train_branch_types import FrameworkKind
        except ImportError:  # PYTHONPATH=scripts（new-project / 单测）
            from lib.train_branch_types import FrameworkKind
        framework_name_hint = (framework_hint or {}).get("name")
        fk = FrameworkKind.from_module_hint(module_name_hint, framework_name_hint)
        framework_kind_value = fk.value

    return DetectionResult(
        workflow=workflow,
        object_type=object_type,
        pattern=pattern,
        framework_kind=framework_kind_value,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Detect or override init workflow")
    p.add_argument("--repo-root", required=True)
    p.add_argument("--source-root", default=None)
    p.add_argument("--workflow", default=None,
                   help="Explicit override (build|migrate|update); auto if omitted")
    args = p.parse_args()
    print(resolve_workflow(args.repo_root, args.source_root, args.workflow).value)