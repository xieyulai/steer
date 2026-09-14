"""auto-run 轮末 EXPERIENCE 压缩判定与执行。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.experience_compress import (  # noqa: E402
    ESSENCE_HEADING,
    c0_stats,
    split_experience_sections,
)
from lib.nn_config import load_nn_config  # noqa: E402

LAST_ROUND_BASENAME = ".experience-compress-last-round.json"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _load_nn_agent(repo_root: Path) -> dict[str, Any]:
    try:
        raw = load_nn_config(repo_root)
        agent = raw.get("agent") or {}
        return agent if isinstance(agent, dict) else {}
    except Exception:
        return {}


def compress_config(repo_root: Path) -> dict[str, Any]:
    try:
        raw = load_nn_config(repo_root)
    except Exception:
        raw = {}
    compress = raw.get("compress") if isinstance(raw.get("compress"), dict) else {}
    mode = str(
        os.environ.get("NN_EXPERIENCE_AUTO_COMPRESS", "")
        or compress.get("experience_auto_compress", "warn")
        or "warn"
    ).strip().lower()
    if mode not in ("off", "warn", "after_round"):
        mode = "warn"
    return {
        "mode": mode,
        "preset": str(compress.get("experience_compress_preset", "standard") or "standard"),
        "keep_n": int(compress.get("experience_compress_keep_n", 5)),
        "keep_reflects": int(compress.get("experience_compress_keep_reflects", 2)),
        "tier_cell_max": int(compress.get("experience_compress_tier_cell_max", 80)),
        "min_lines": int(compress.get("experience_compress_min_lines", 400)),
        "min_archivable": int(compress.get("experience_compress_min_archivable", 10)),
        "cooldown_rounds": int(compress.get("experience_compress_cooldown_rounds", 2)),
    }


def last_round_path(repo_root: Path) -> Path:
    return repo_root.resolve() / "saved" / LAST_ROUND_BASENAME


def load_last_round(repo_root: Path) -> dict[str, Any]:
    p = last_round_path(repo_root)
    if not p.is_file():
        return {}
    try:
        raw = json.loads(_read_text(p))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def historical_debt(
    cfg: dict[str, Any],
    *,
    lines: int,
    archivable_n: int,
    keep_n: int,
    has_essence: bool,
) -> tuple[bool, str]:
    """历史债务：行数或待归档量明显超标，轮末应自动压缩（可绕过冷却）。"""
    min_lines = int(cfg["min_lines"])
    min_arch = int(cfg["min_archivable"])
    if lines >= min_lines * 2:
        return True, f"lines={lines}>={min_lines * 2}"
    if archivable_n >= keep_n + min_arch:
        return True, f"archivable={archivable_n}>={keep_n + min_arch}"
    if has_essence and lines >= min_lines and archivable_n < min_arch:
        return True, f"lines={lines} essence=1 archivable={archivable_n}<{min_arch}"
    return False, ""


def write_last_round(repo_root: Path, *, run: int, lines: int) -> None:
    saved = repo_root.resolve() / "saved"
    saved.mkdir(parents=True, exist_ok=True)
    payload = {
        "round": run,
        "lines_after": lines,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    last_round_path(repo_root).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def should_compress(repo_root: Path, run: int) -> tuple[bool, str]:
    cfg = compress_config(repo_root)
    if cfg["mode"] == "off":
        return False, "mode=off"

    exp = repo_root / "EXPERIENCE.md"
    if not exp.is_file():
        return False, "no EXPERIENCE.md"

    md = _read_text(exp)
    stats = c0_stats(md)
    lines = int(stats.get("lines") or 0)
    keep_n = int(cfg["keep_n"])
    parts = split_experience_sections(md, keep_n=keep_n)
    archivable_n = len(parts.archivable) + len(parts.reflects_archivable)
    has_essence = ESSENCE_HEADING in md or "## 精华摘要" in md

    debt, debt_reason = historical_debt(
        cfg,
        lines=lines,
        archivable_n=archivable_n,
        keep_n=keep_n,
        has_essence=has_essence,
    )

    if not debt:
        if lines < int(cfg["min_lines"]) and archivable_n < int(cfg["min_archivable"]) + keep_n:
            return False, f"below threshold lines={lines} archivable={archivable_n}"

        if has_essence and archivable_n < int(cfg["min_archivable"]):
            return False, f"has essence but archivable={archivable_n}<{cfg['min_archivable']}"

    if cfg["mode"] == "after_round" and not debt:
        last = load_last_round(repo_root)
        last_round = int(last.get("round") or 0)
        if run - last_round < int(cfg["cooldown_rounds"]):
            return False, f"cooldown run={run} last={last_round}"

    suffix = f" debt={debt_reason}" if debt else ""
    return True, f"lines={lines} archivable={archivable_n} essence={has_essence}{suffix}"


def run_auto_compress(repo_root: Path, run: int) -> tuple[int, str]:
    """Return (exit_code, summary line)."""
    cfg = compress_config(repo_root)
    ok, reason = should_compress(repo_root, run)
    if not ok:
        return 0, f"skip: {reason}"

    scripts = repo_root / "scripts" / "compress-experience.py"
    if not scripts.is_file():
        return 0, "skip: no compress-experience.py"

    if cfg["mode"] == "warn":
        log_path = repo_root / "_runs" / "agent"
        log_path.mkdir(parents=True, exist_ok=True)
        msg = (
            f"EXPERIENCE compress suggested ({reason}); "
            f"run: python3 scripts/compress-experience.py --preset {cfg['preset']} --apply"
        )
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        (log_path / f"{stamp}_compress-suggested.log").write_text(msg + "\n", encoding="utf-8")
        return 0, f"warn: {reason}"

    cmd = [
        sys.executable,
        str(scripts),
        "--repo-root",
        str(repo_root.resolve()),
        "--preset",
        str(cfg["preset"]),
        "--keep-n",
        str(cfg["keep_n"]),
        "--keep-reflects",
        str(cfg["keep_reflects"]),
        "--tier-cell-max",
        str(cfg["tier_cell_max"]),
        "--apply",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    summary = (proc.stdout or "").strip().splitlines()
    tail = summary[-1] if summary else ""
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "compress failed")[:500]
        return proc.returncode, f"fail: {err}"

    exp = repo_root / "EXPERIENCE.md"
    lines_after = exp.read_text(encoding="utf-8").count("\n") + 1 if exp.is_file() else 0
    write_last_round(repo_root, run=run, lines=lines_after)
    return 0, f"applied: {reason}; {tail}"
