"""Resolve external paper search task domain from nn-config or README."""
from __future__ import annotations

from pathlib import Path


def resolve_task_domain(repo_root: Path) -> str:
    cfg_path = repo_root / "nn-config.yaml"
    if cfg_path.is_file():
        try:
            import yaml

            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            dom = str((cfg.get("external") or {}).get("task_domain") or "").strip()
            if dom:
                return dom[:200]
        except Exception:
            pass
    readme = repo_root / "README.md"
    if readme.is_file():
        for line in readme.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.lstrip("#").strip()
            if s:
                return s[:200]
    return ""