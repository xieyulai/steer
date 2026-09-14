#!/usr/bin/env python3
"""write_baseline_start_intent.py — 校验并写入 saved/baseline_start_intent.json。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED_KEYS = ("schema_version", "start_runs", "scenario_id")


def validate_intent(data: dict) -> None:
    if not isinstance(data, dict):
        raise ValueError("intent must be object")
    for k in REQUIRED_KEYS:
        if k not in data:
            raise ValueError(f"missing key: {k}")
    if int(data.get("schema_version") or 0) < 1:
        raise ValueError("schema_version must be >= 1")
    sr = data.get("start_runs")
    if not isinstance(sr, str) or not sr.strip():
        raise ValueError("start_runs must be non-empty string")


def write_intent(repo_root: Path, data: dict, *, force: bool = False) -> Path:
    validate_intent(data)
    out = Path(repo_root) / "saved" / "baseline_start_intent.json"
    if out.is_file() and not force:
        raise FileExistsError(f"{out} exists; use --force to overwrite")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo-root", required=True)
    p.add_argument("--json", required=True, help="intent JSON string or @path")
    p.add_argument("--force", action="store_true")
    a = p.parse_args()
    raw = a.json
    if raw.startswith("@"):
        data = json.loads(Path(raw[1:]).read_text(encoding="utf-8"))
    else:
        data = json.loads(raw)
    path = write_intent(Path(a.repo_root), data, force=a.force)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
