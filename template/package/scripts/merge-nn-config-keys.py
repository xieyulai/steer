#!/usr/bin/env python3
"""Merge missing keys from template nn-config into project nn-config (never overwrite)."""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PyYAML required") from exc


def deep_merge_missing(base: dict, overlay: dict) -> dict:
    """Add keys from overlay missing in base; recurse into nested dicts."""
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if key not in result:
            result[key] = copy.deepcopy(value)
        elif isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge_missing(result[key], value)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    project_path = args.project.resolve()
    template_path = args.template.resolve()
    if not project_path.is_file():
        print(f"ERROR: missing project config: {project_path}", file=sys.stderr)
        return 1
    if not template_path.is_file():
        print(f"ERROR: missing template config: {template_path}", file=sys.stderr)
        return 1

    project = yaml.safe_load(project_path.read_text(encoding="utf-8")) or {}
    template = yaml.safe_load(template_path.read_text(encoding="utf-8")) or {}
    merged = deep_merge_missing(project, template)

    if merged == project:
        print(f"  nn-config: no missing keys ({project_path.name})")
        return 0

    if args.dry_run:
        added = sorted(set(_flatten_keys(template)) - set(_flatten_keys(project)))
        print(f"  nn-config: would add keys: {', '.join(added) or '(none)'}")
        return 0

    project_path.write_text(
        yaml.safe_dump(merged, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    print(f"  nn-config: merged missing template keys into {project_path}")
    return 0


def _flatten_keys(node: dict, prefix: str = "") -> list[str]:
    out: list[str] = []
    for key, value in node.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        out.append(path)
        if isinstance(value, dict):
            out.extend(_flatten_keys(value, path))
    return out


if __name__ == "__main__":
    raise SystemExit(main())
