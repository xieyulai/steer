from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore


def resolve_policy_path(
    *,
    project_root: Path,
    template_pkg: Path | None = None,
) -> Path | None:
    for base in (project_root, template_pkg or Path()):
        cand = base / "docs" / "init" / "init-interaction-policy.yaml"
        if cand.is_file():
            return cand
    return None


def load_policy(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML required for init-interaction-policy")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"invalid policy: {path}")
    return data


def is_must_individual(policy: dict[str, Any], slug: str) -> bool:
    return slug in set(policy.get("must_individual") or [])


def parallel_bundle_for_slugs(
    policy: dict[str, Any],
    *,
    entry: str,
    next_slugs: list[str],
    confirmed_slugs: set[str],
) -> dict[str, Any] | None:
    if len(next_slugs) < 2:
        return None
    max_p = int((policy.get("defaults") or {}).get("max_parallel") or 2)
    pair = next_slugs[:max_p]
    for bundle in policy.get("bundles") or []:
        if entry not in (bundle.get("entry") or []):
            continue
        if not bundle.get("parallel_eligible"):
            continue
        req = set(bundle.get("requires_confirmed") or [])
        if not req.issubset(confirmed_slugs):
            continue
        b_slugs = [s["slug"] for s in bundle.get("slugs") or []]
        if pair == b_slugs[: len(pair)]:
            return bundle
    return None
