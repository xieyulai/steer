#!/usr/bin/env python3
"""C4 experience — 归档 EXPERIENCE.md 旧叙事（保留精华/Tier 状态/近 K 条）。

不动 TSV/exp/keeper。归档到 _runs_legacy/experience/。
与 /auto-nn-compress 互补：compress 精简但不归档；clear C4 归档旧段。
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.experience_compress import (  # noqa: E402
    ESSENCE_HEADING,
    RECENT_HEADING_TEMPLATE,
    TIER_STATUS_HEADING,
    count_experiment_sections,
    is_experiment_section,
    is_protected_section,
    is_reflect_section,
    split_experience_sections,
)

ARCHIVE_DIR = "_runs_legacy/experience"
EXPERIENCE_MD = "EXPERIENCE.md"


def _warn(msg: str) -> None:
    print(f"[clear-experience] WARN: {msg}", file=sys.stderr)


def _info(msg: str) -> None:
    print(f"[clear-experience] {msg}")


def _archive_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def plan_clear_experience(repo_root: Path, keep_recent: int = 5) -> dict:
    repo_root = repo_root.resolve()
    exp_path = repo_root / EXPERIENCE_MD
    has_experience = exp_path.is_file()
    total_sections = 0
    archive_count = 0
    keep_count = 0

    if has_experience:
        md = exp_path.read_text(encoding="utf-8", errors="replace")
        total_sections = count_experiment_sections(md)
        archive_count = max(0, total_sections - keep_recent)
        keep_count = total_sections - archive_count

    return {
        "repo_root": str(repo_root),
        "has_experience": has_experience,
        "total_experiment_sections": total_sections,
        "archive_count": archive_count,
        "keep_count": keep_count,
        "keep_recent": keep_recent,
        "archive_dir": f"{ARCHIVE_DIR}/archive-{_archive_stamp()}",
    }


def _rebuild_experience(md: str, keep_recent: int) -> str:
    """保留：标题行 + 精华 + Tier 状态 + 场景 + 近 K 条实验。其余归档。"""
    result = split_experience_sections(md)
    if result is None:
        return md

    header, pre_container, experiments, reflects, recent_container, post_container = result

    # Collect kept experiments
    kept_experiments = experiments[-keep_recent:] if len(experiments) > keep_recent else experiments

    parts = [header]

    # Protected pre-container sections (精华, Tier 状态, 场景等)
    for title, body in pre_container:
        parts.append(f"## {title}\n{body}".strip())

    # Recent experiment container header if present
    if recent_container:
        recent_title, recent_body = recent_container
        # Replace N in template
        actual_recent = RECENT_HEADING_TEMPLATE.format(n=len(kept_experiments))
        parts.append(actual_recent)
    else:
        parts.append(RECENT_HEADING_TEMPLATE.format(n=len(kept_experiments)))

    # Kept experiments
    for title, body in kept_experiments:
        parts.append(f"## {title}\n{body}".strip())

    # Post-container protected sections
    for title, body in post_container:
        parts.append(f"## {title}\n{body}".strip())

    return "\n\n".join(parts) + "\n"


def apply_clear_experience(repo_root: Path, *, keep_recent: int = 5, dry_run: bool = True) -> dict:
    plan = plan_clear_experience(repo_root, keep_recent)
    repo_root = Path(plan["repo_root"])
    exp_path = repo_root / EXPERIENCE_MD

    _info(f"模式: tier=experience keep_recent={keep_recent} dry_run={dry_run}")

    if not plan["has_experience"]:
        _info("EXPERIENCE.md 不存在，无需归档")
        return plan

    md = exp_path.read_text(encoding="utf-8", errors="replace")
    total = plan["total_experiment_sections"]
    archive_n = plan["archive_count"]

    _info(f"EXPERIENCE.md 实验段: {total} 个，保留最近 {keep_recent} 个，归档 {archive_n} 个")

    if archive_n <= 0:
        _info("无旧段需归档（实验段 <= keep_recent）")
        return plan

    archive_rel = plan["archive_dir"]
    _info(f"归档目标: {archive_rel}/")

    if dry_run:
        _info("dry-run 结束；确认后请加 --apply")
        return plan

    # Archive original
    archive_dir = repo_root / archive_rel
    archive_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(exp_path), str(archive_dir / EXPERIENCE_MD))
    _info(f"已归档原文件: {archive_rel}/{EXPERIENCE_MD}")

    # Rebuild with only recent sections
    new_md = _rebuild_experience(md, keep_recent)
    exp_path.write_text(new_md, encoding="utf-8")
    new_count = count_experiment_sections(new_md)
    _info(f"已重建 EXPERIENCE.md: {total} → {new_count} 实验段")

    return plan


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--keep-recent", type=int, default=5, help="保留最近 K 条实验段（默认 5）")
    ap.add_argument("--apply", action="store_true", help="执行归档（默认 dry-run）")
    ap.add_argument("--json", action="store_true", help="输出 JSON 计划")
    args = ap.parse_args()

    plan = apply_clear_experience(
        args.repo_root.resolve(),
        keep_recent=args.keep_recent,
        dry_run=not args.apply,
    )

    if args.json:
        import json
        print(json.dumps(plan, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
