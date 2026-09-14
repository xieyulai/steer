#!/usr/bin/env python3
"""Merge template-owned README regions into a business repo (preserve §3/§4).

Template regions (from template/package/README.md):
  NN_TEMPLATE:NAV | QUICKSTART | SKILLS | APPENDIX

Never overwritten:
  - First H1 title line
  - ## §3 … through <!-- /PROJECT_NOTES -->
  - Structured gates: D2_DATA_SPLIT, SCENARIO_POLICY, METRICS_SNAPSHOT, AGENT_BOUNDARY
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_TEMPLATE_REGIONS = ("NAV", "QUICKSTART", "SKILLS", "APPENDIX")
_LEGACY_INNER = ("SKILLS_GUIDE", "SKILLS_SCENARIOS")
_PROTECTED_BLOCKS = (
    "D2_DATA_SPLIT",
    "SCENARIO_POLICY",
    "METRICS_SNAPSHOT",
    "AGENT_BOUNDARY",
    "PROJECT_NOTES",
)


def _region_pattern(name: str) -> re.Pattern[str]:
    return re.compile(
        rf"(<!-- NN_TEMPLATE:{re.escape(name)} -->)(.*?)(<!-- /NN_TEMPLATE:{re.escape(name)} -->)",
        re.DOTALL,
    )


def _inner_pattern(name: str) -> re.Pattern[str]:
    return re.compile(
        rf"(<!-- {re.escape(name)} -->)(.*?)(<!-- /{re.escape(name)} -->)",
        re.DOTALL,
    )


def _extract_region(text: str, name: str) -> str | None:
    m = _region_pattern(name).search(text)
    return m.group(2) if m else None


def _replace_region(text: str, name: str, inner: str) -> tuple[str, bool]:
    pat = _region_pattern(name)
    if not pat.search(text):
        return text, False
    repl = rf"\1{inner}\3"
    return pat.sub(repl, text, count=1), True


def _replace_inner(text: str, name: str, inner: str) -> tuple[str, bool]:
    pat = _inner_pattern(name)
    if not pat.search(text):
        return text, False
    repl = rf"\1{inner}\3"
    return pat.sub(repl, text, count=1), True


def _first_h1(text: str) -> str | None:
    for line in text.splitlines():
        if line.startswith("# "):
            return line
    return None


def _has_new_structure(text: str) -> bool:
    return "<!-- NN_TEMPLATE:SKILLS -->" in text


def merge_readme(template_text: str, project_text: str) -> tuple[str, list[str]]:
    """Return merged README and human-readable log lines."""
    logs: list[str] = []
    out = project_text
    title = _first_h1(project_text) or _first_h1(template_text)

    if _has_new_structure(project_text):
        for region in _TEMPLATE_REGIONS:
            tpl_inner = _extract_region(template_text, region)
            if tpl_inner is None:
                logs.append(f"WARN: template missing NN_TEMPLATE:{region}")
                continue
            new_out, ok = _replace_region(out, region, tpl_inner)
            if ok:
                out = new_out
                logs.append(f"OK: merged NN_TEMPLATE:{region}")
            else:
                logs.append(f"WARN: project missing NN_TEMPLATE:{region} (skipped)")
    else:
        logs.append("WARN: project README lacks NN_TEMPLATE markers — legacy inner merge only")
        for inner in _LEGACY_INNER:
            m = _inner_pattern(inner).search(template_text)
            if not m:
                continue
            tpl_inner = m.group(2)
            new_out, ok = _replace_inner(out, inner, tpl_inner)
            if ok:
                out = new_out
                logs.append(f"OK: merged legacy {inner}")
            else:
                logs.append(f"WARN: project missing {inner}")

    if title:
        proj_title = _first_h1(out)
        if proj_title and proj_title != title:
            out = out.replace(proj_title, title, 1)
            logs.append("OK: preserved project title")

    for block in _PROTECTED_BLOCKS:
        pm = _inner_pattern(block).search(project_text)
        if not pm:
            continue
        inner = pm.group(2)
        new_out, ok = _replace_inner(out, block, inner)
        if ok:
            out = new_out

    return out, logs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True, help="Business repo root")
    parser.add_argument("--template", type=Path, required=True, help="template/package root")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    project_root = args.project.resolve()
    template_root = args.template.resolve()
    readme = project_root / "README.md"
    tpl_readme = template_root / "README.md"

    if not tpl_readme.is_file():
        print(f"ERROR: missing template README: {tpl_readme}", file=sys.stderr)
        return 1
    if not readme.is_file():
        print("README: skip (no README.md)")
        return 0

    before = readme.read_text(encoding="utf-8")
    merged, logs = merge_readme(tpl_readme.read_text(encoding="utf-8"), before)

    for line in logs:
        print(f"  readme-merge: {line}")

    if merged == before:
        print("  readme-merge: no changes")
        return 0

    if args.dry_run:
        print("  readme-merge: dry-run (would update README.md)")
        return 0

    readme.write_text(merged, encoding="utf-8")
    print("  readme-merge: updated README.md (template regions only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
