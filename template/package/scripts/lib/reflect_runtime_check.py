"""Reflect 运行时文件与 import 检查（不调用 LLM、不依赖 CUDA）。"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

_EXTERNAL_MIN = ("router.py", "reflect_hook.py", "arxiv.py")

_IMPORT_MODULES = (
    "lib.agent_cli",
    "lib.innovation_fingerprint",
    "lib.external.reflect_hook",
)


def _required_file_paths(repo_root: Path) -> list[str]:
    from lib.governance_sync_manifest import (  # noqa: WPS433
        expand_patterns,
        iter_group_patterns,
        load_manifest,
    )

    scripts_lib = repo_root / "scripts" / "lib"
    manifest = load_manifest(scripts_lib)
    return expand_patterns(repo_root, iter_group_patterns(manifest, "reflect_runtime"))


def run_check(repo_root: Path) -> tuple[bool, list[str]]:
    repo_root = repo_root.resolve()
    failures: list[str] = []

    for rel in _required_file_paths(repo_root):
        p = repo_root / rel
        if "*" in rel:
            failures.append(f"missing glob: {rel}")
        elif not p.is_file():
            failures.append(f"missing file: {rel}")

    ext_dir = repo_root / "scripts" / "lib" / "external"
    for name in _EXTERNAL_MIN:
        if not (ext_dir / name).is_file():
            failures.append(f"missing file: scripts/lib/external/{name}")

    scripts = repo_root / "scripts"
    inserted = False
    if scripts.is_dir():
        sp = str(scripts)
        if sp not in sys.path:
            sys.path.insert(0, sp)
            inserted = True
    try:
        for mod in _IMPORT_MODULES:
            try:
                importlib.import_module(mod)
            except ImportError as exc:
                failures.append(f"import {mod}: {exc}")
    finally:
        if inserted and str(scripts) in sys.path:
            sys.path.remove(str(scripts))

    return (len(failures) == 0, failures)


def format_lines(ok: bool, failures: list[str]) -> list[str]:
    if ok:
        return ["PASS: reflect_runtime OK"]
    lines = [f"FAIL: {f}" for f in failures]
    lines.append(
        "FAIL: reflect 运行时未就绪 — 请在业务仓执行 bash scripts/auto-nn-update.sh --pull-template"
    )
    return lines
