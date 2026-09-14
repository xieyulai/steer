# scripts/new_project_scenarios.py
"""Pure routing helper used by scripts/new-project.sh.

Decides which of the 3 init workflows (build / migrate / update) applies for
a given (repo, source) pair. Wraps :classify` from `init_workflow` so it can
be called both from bash and from pytest without pulling in the full O3
writer.

Routing rules (highest priority first):
  1. ``force_update=True``                -> ``"update"``
  2. ``workflow_override`` non-empty      -> ``<override>`` (validated against Workflow enum)
  3. ``source`` is empty / unset          -> ``"build"``
  4. otherwise                            -> classify(repo, source) → ``"build" | "migrate" | "update"``

PR2.3: 删了 resolve_init_scenario(4-branch 解析),只留 resolve_init_workflow(3-branch 入口)。
"""
from __future__ import annotations

import argparse

from init_workflow import Workflow, classify


def resolve_init_workflow(repo: str, source: str | None, force_update: bool,
                          workflow_override: str | None = None) -> str:
    """Return one of ``"build" | "migrate" | "update"``.

    Parameters
    ----------
    repo
        Target project root path.
    source
        Source project root path (or ``None``/empty for build).
    force_update
        Explicit ``--force-update`` flag from new-project.sh; if set, UPDATE
        wins regardless of the (repo, source) equality check.
    workflow_override
        Optional explicit ``--workflow <build|migrate|update>`` override;
        validated against :class:`Workflow` before returning.
    """
    if force_update:
        return Workflow.UPDATE.value
    if workflow_override:
        try:
            return Workflow(workflow_override).value
        except ValueError as e:
            valid = ", ".join(w.value for w in Workflow)
            raise ValueError(
                f"未知 --workflow={workflow_override!r};可选: {valid}"
            ) from e
    return classify(repo, source).value


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Resolve init workflow for new-project.sh")
    p.add_argument("--repo", required=True, help="Target project root")
    p.add_argument("--source", default=None, help="Source project root (optional)")
    p.add_argument("--force-update", action="store_true",
                   help="Force UPDATE workflow (source == repo)")
    p.add_argument("--workflow", default=None,
                   help="Explicit override (build|migrate|update); auto if omitted")
    args = p.parse_args()
    print(resolve_init_workflow(
        args.repo, args.source, args.force_update, args.workflow
    ))