#!/usr/bin/env python3
"""train_dynamics 门禁：train.py hook + 最新 exp 的 dynamics 产物。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml


def _load_profile(repo_root: Path) -> str:
    p = repo_root / "nn-config.yaml"
    if not p.is_file():
        return ""
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return str(data.get("profile", "")).strip()


def _is_template_root(repo_root: Path) -> bool:
    return (repo_root / ".template-maintainer").is_file()


def _train_py_has_hooks(repo_root: Path) -> bool:
    p = repo_root / "train.py"
    if not p.is_file():
        return False
    text = p.read_text(encoding="utf-8", errors="replace")
    return "record_train_epoch" in text or "record_metrics" in text


def _latest_exp_dir(repo_root: Path) -> Path | None:
    tsv = repo_root / "_runs" / "results.tsv"
    if not tsv.is_file():
        return None
    lines = tsv.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) < 2:
        return None
    header = lines[0].split("\t")
    try:
        idx = header.index("exp_dir")
    except ValueError:
        return None
    for line in reversed(lines[1:]):
        cols = line.split("\t")
        if len(cols) <= idx:
            continue
        exp = cols[idx].strip()
        if not exp or cols[0].strip() == "preflight_check":
            continue
        p = Path(exp)
        if p.is_dir():
            return p
    return None


def check_train_dynamics_gate(repo_root: Path) -> tuple[bool, list[str], list[str]]:
    """Return (ok, errors, warnings)."""
    root = repo_root.resolve()
    errors: list[str] = []
    warns: list[str] = []

    if _is_template_root(root):
        return True, errors, warns

    profile = _load_profile(root)
    if profile == "supervised" and not _train_py_has_hooks(root):
        errors.append("supervised train.py 缺少 record_train_epoch/record_metrics hook")

    exp_dir = _latest_exp_dir(root)
    if exp_dir is None:
        warns.append("无可用 exp_dir（跳过 dynamics 产物检查）")
        return len(errors) == 0, errors, warns

    dyn_path = exp_dir / "train_dynamics.json"
    if not dyn_path.is_file() or dyn_path.stat().st_size < 2:
        warns.append(f"末轮 exp 无 train_dynamics.json: {exp_dir.name}")
    else:
        try:
            dyn = json.loads(dyn_path.read_text(encoding="utf-8"))
            n_points = int(dyn.get("n_points") or 0)
            if profile == "supervised" and n_points <= 0:
                errors.append(f"supervised 末轮 dynamics n_points=0 ({exp_dir.name})")
            elif profile == "rl" and n_points <= 0:
                warns.append(f"rl 末轮 dynamics n_points=0（v1 adapter 未命中 monitor.csv）")
        except (json.JSONDecodeError, OSError) as exc:
            errors.append(f"train_dynamics.json 无法解析: {exc}")

    series_path = exp_dir / "metrics_series.tsv"
    if profile == "supervised":
        if not series_path.is_file() or series_path.stat().st_size < 2:
            errors.append(f"supervised 末轮无 metrics_series.tsv: {exp_dir.name}")
        else:
            row_count = max(0, len(series_path.read_text(encoding="utf-8").splitlines()) - 1)
            if row_count < 1:
                errors.append(f"supervised metrics_series.tsv 无数据行 ({exp_dir.name})")

    return len(errors) == 0, errors, warns


def main() -> int:
    repo = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    ok, errors, warns = check_train_dynamics_gate(repo)
    for w in warns:
        print(f"WARN: {w}", file=sys.stderr)
    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        return 1
    print("train_dynamics_gate: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
