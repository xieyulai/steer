#!/usr/bin/env python3
"""维护仓 CI：governance-sync.sh 须覆盖 manifest 全部路径。"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.governance_sync_manifest import all_manifest_paths  # noqa: E402


def _sync_script_text(template_pkg: Path) -> str:
    path = template_pkg / "scripts" / "governance-sync.sh"
    return path.read_text(encoding="utf-8")


def _path_covered(sync_text: str, rel_path: str) -> bool:
    if rel_path.startswith("scripts/lib/external/"):
        return "scripts/lib/external" in sync_text
    if rel_path.endswith(".py") or rel_path.endswith(".yaml") or rel_path.endswith(".sh"):
        base = Path(rel_path).name
        if f'"{rel_path}"' in sync_text or f"'{rel_path}'" in sync_text:
            return True
        if f"/{rel_path}" in sync_text:
            return True
        if f'/{base}"' in sync_text or f"/{base}'" in sync_text:
            return True
        if re.search(rf'\$TEMPLATE_PKG/{re.escape(rel_path)}', sync_text):
            return True
        if base in sync_text and "TEMPLATE_PKG" in sync_text:
            return True
    return rel_path in sync_text


def run_check(template_pkg: Path) -> tuple[bool, list[str]]:
    template_pkg = template_pkg.resolve()
    sync_text = _sync_script_text(template_pkg)
    missing: list[str] = []
    for rel in all_manifest_paths(template_pkg):
        if not _path_covered(sync_text, rel):
            missing.append(rel)
    return (len(missing) == 0, missing)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--template-pkg",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="template/package 根（默认脚本上级）",
    )
    args = parser.parse_args()
    ok, missing = run_check(args.template_pkg)
    if ok:
        print("PASS: governance-sync covers manifest")
        return 0
    for m in missing:
        print(f"FAIL: governance-sync.sh 未覆盖 manifest 路径: {m}", file=sys.stderr)
    print(
        "FAIL: 请更新 governance-sync.sh 与 governance_sync_manifest.yaml",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
