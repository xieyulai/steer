#!/usr/bin/env python3
"""C5 reflect — 归档 reflect 产物并重置 REFLECT_INDEX pending（不动 TSV/exp/EXPERIENCE/keeper）。"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

# 允许 import scripts/lib
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.reflect_index import default_index_template, parse_pending_cells  # noqa: E402
from lib.experiment_journal import clear_reflect_journal  # noqa: E402
from clear_experience import apply_clear_experience  # noqa: E402

LEGACY_SUBDIR = "reflect"
ARCHIVE_PREFIX = "archive"

# reflect 落盘产物（相对 repo 根）
SAVED_REFLECT_FILES = (
    "saved/reflect_latest.json",
    "saved/reflect_evidence.json",
    "saved/reflect_evidence.md",
    "saved/reflect_evidence_gaps.json",
    "saved/tier_attestation.json",
    "saved/tier_attestation.md",
    "saved/evidence_bundle.json",
    "saved/external_plan.json",
    "saved/innovation_audit.json",
)
# 改题待办：随 reflect 档点名归档；不删 TSV exploration_space 格子
E_FEEDBACK_JSONL = "_runs/analysis/e_feedback.jsonl"
# saved/external_evidence/ 目录：clear reflect 不删（spec §11.9 可选保留 archive）
# saved/external_evidence/pdfs/ 同上 — PDF 资料库与 {reflect_id}.json 一并保留
# saved/audit/ 属审查卡片，本档不删（factory 清整个 saved/）。

REFLECT_INDEX = "references/REFLECT_INDEX.md"
AUTO_REFLECT_GLOB = "*_auto_reflected.md"


def _warn(msg: str) -> None:
    print(f"[clear-reflect] WARN: {msg}", file=sys.stderr)


def _info(msg: str) -> None:
    print(f"[clear-reflect] {msg}")


def _collect_auto_reflect_md(repo_root: Path) -> list[Path]:
    auto_dir = repo_root / "references" / "auto"
    if not auto_dir.is_dir():
        return []
    return sorted(p for p in auto_dir.glob(AUTO_REFLECT_GLOB) if p.is_file())


def _collect_saved_reflect(repo_root: Path) -> list[Path]:
    found: list[Path] = []
    for rel in SAVED_REFLECT_FILES:
        p = repo_root / rel
        if p.is_file():
            found.append(p)
    return found


def _collect_e_feedback(repo_root: Path) -> list[Path]:
    p = repo_root / E_FEEDBACK_JSONL
    return [p] if p.is_file() else []


_PENDING_PLACEHOLDERS = frozenset({"（无）", "—", "-", "", "id"})


def _pending_rows_in_index(text: str) -> list[str]:
    """解析 ## 待消费 区有效 pending 行（忽略 blockquote 内的 ## 待消费）。"""
    m = re.search(r"^##\s*待消费[^\n]*\n(.*?)(?=\n##\s|\Z)", text, re.DOTALL | re.I | re.MULTILINE)
    if not m:
        return []
    rows: list[str] = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 6 and cells[0] not in _PENDING_PLACEHOLDERS:
            rows.append(line)
    return rows


def _index_has_pending(repo_root: Path) -> bool:
    index_path = repo_root / REFLECT_INDEX
    if not index_path.is_file():
        return False
    text = index_path.read_text(encoding="utf-8", errors="replace")
    return bool(_pending_rows_in_index(text))


def plan_clear_reflect(repo_root: Path) -> dict:
    repo_root = repo_root.resolve()
    auto_md = _collect_auto_reflect_md(repo_root)
    saved_files = _collect_saved_reflect(repo_root)
    e_feedback = _collect_e_feedback(repo_root)
    index_path = repo_root / REFLECT_INDEX
    reset_index = _index_has_pending(repo_root) or (
        not index_path.is_file() and bool(auto_md or saved_files or e_feedback)
    )

    archive_rel = f"_runs_legacy/{LEGACY_SUBDIR}/{ARCHIVE_PREFIX}-{{ts}}/"
    items: list[dict] = []

    for p in auto_md:
        items.append({"action": "archive", "path": str(p.relative_to(repo_root)), "kind": "auto_md"})
    for p in saved_files:
        items.append({"action": "archive", "path": str(p.relative_to(repo_root)), "kind": "saved"})
    for p in e_feedback:
        items.append({"action": "archive", "path": str(p.relative_to(repo_root)), "kind": "e_feedback"})
    if reset_index:
        items.append(
            {
                "action": "reset_index",
                "path": REFLECT_INDEX,
                "kind": "reflect_index",
                "archive_old": index_path.is_file(),
            }
        )

    return {
        "repo_root": str(repo_root),
        "archive_dir_template": archive_rel,
        "items": items,
        "auto_md_count": len(auto_md),
        "saved_count": len(saved_files),
        "e_feedback_count": len(e_feedback),
        "reset_index": reset_index,
        "c4_skipped": True,
    }


def _archive_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def apply_clear_reflect(repo_root: Path, *, dry_run: bool = True) -> dict:
    plan = plan_clear_reflect(repo_root)
    repo_root = Path(plan["repo_root"])
    ts = _archive_stamp()
    archive_dir = repo_root / "_runs_legacy" / LEGACY_SUBDIR / f"{ARCHIVE_PREFIX}-{ts}"

    _info(f"模式: tier=reflect dry_run={dry_run}")

    # C4: archive EXPERIENCE narrative first
    apply_clear_experience(repo_root, keep_recent=5, dry_run=dry_run)

    if not plan["items"]:
        _info("未发现 reflect 产物；无需清理")
        return plan

    _info(f"归档目标: {archive_dir.relative_to(repo_root)}/")
    for item in plan["items"]:
        rel = item["path"]
        action = item["action"]
        if action == "archive":
            _info(f"  将归档: {rel}")
        elif action == "reset_index":
            if item.get("archive_old"):
                _info(f"  将归档并重置: {rel} → 空 pending 模板")
            else:
                _info(f"  将写入: {rel}（默认模板）")

    _info("将保留: _runs/results.tsv（含 exploration_space 格子）、_runs/exp/*、saved/keeper.json、EXPERIENCE.md 正文")

    if dry_run:
        _info("dry-run 结束；确认后请加 --apply")
        return plan

    archive_dir.mkdir(parents=True, exist_ok=True)

    for item in plan["items"]:
        rel = item["path"]
        src = repo_root / rel
        if item["action"] == "archive":
            if not src.is_file():
                continue
            dst = archive_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            _info(f"已归档: {rel}")
        elif item["action"] == "reset_index":
            if item.get("archive_old") and src.is_file():
                dst = archive_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src), str(dst))
                _info(f"已归档 INDEX 副本: {rel}")
            src.parent.mkdir(parents=True, exist_ok=True)
            src.write_text(default_index_template(), encoding="utf-8")
            _info(f"已重置: {rel}")

    if plan["reset_index"]:
        clear_reflect_journal(repo_root, apply=True)

    _info(f"apply 完成；归档于 {archive_dir.relative_to(repo_root)}/")
    _info("建议: bash scripts/smoke-check.sh；可选 bash scripts/nn-doctor.sh")
    return plan


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--apply", action="store_true", help="执行归档与重置（默认 dry-run）")
    ap.add_argument("--json", action="store_true", help="输出 JSON 计划")
    args = ap.parse_args()

    plan = apply_clear_reflect(args.repo_root.resolve(), dry_run=not args.apply)

    if args.json:
        import json

        print(json.dumps(plan, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
