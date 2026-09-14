#!/usr/bin/env python3
"""C6 factory — 绿场重置。

清空 _runs/、saved/（keeper/journal）、references/auto/、归档 EXPERIENCE.md，
重置 REFLECT_INDEX，保留 contract/、workspace/、train.py、nn-config.yaml、PROTOCOL.md 等。

apply 须额外 --confirm factory（由 clear-runs.sh 校验）。
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

ARCHIVE_DIR = "_runs_legacy/factory"

# 这些不动（白名单）
# 注: CHECKLIST.md 自 1.1.1 起不再保留在业务仓根目录（new-project.sh 自动移到
#     .auto-nn/migration-completed-checklist-<ts>.md）；从白名单移除。
KEEP_PATTERNS = {
    "contract",
    "workspace",
    "train.py",
    "experiment.py",
    "reflect.py",
    "CLAUDE.md",
    "PROTOCOL.md",
    "nn-config.yaml",
    "profiles.yaml",
    "poetry.lock",
    "pyproject.toml",
    "README.md",
    "HUMAN_GUIDANCE.md",
    ".gitignore",
    ".auto-nn",
    "scripts",
    "data",
    "docs",
    "_runs_legacy",
    "references/manual",
    "workspace/scripts",
}

# 清空的目标（saved/ 含 saved/external_evidence/* 归档副本）
SAVED_EXTERNAL_EVIDENCE_GLOB = "saved/external_evidence/*"

CLEAR_DIRS = (
    "_runs",
    "saved",
    "references/auto",
)

CLEAR_FILES = (
    "EXPERIENCE.md",
    "references/REFLECT_INDEX.md",
    "progress.txt",
    "_runs_legacy",  # 不清，只归档进这里
)


def _warn(msg: str) -> None:
    print(f"[clear-factory] WARN: {msg}", file=sys.stderr)


def _info(msg: str) -> None:
    print(f"[clear-factory] {msg}")


def _archive_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _reset_experience(path: Path) -> None:
    """Write minimal EXPERIENCE.md with just the title."""
    # Try to extract title from existing content
    title = "EXPERIENCE"
    if path.is_file():
        first_line = path.read_text(encoding="utf-8", errors="replace").split("\n")[0]
        if first_line.startswith("# "):
            title = first_line[2:].strip()
    path.write_text(f"# {title}\n\n## 精华摘要（滚动，compress 维护）\n\n## Tier 状态\n\n| 档 | 状态 | 备注 |\n|----|------|------|\n| A | 未试 | factory reset |\n\n## 近期实验（保留最近 0 轮全文）\n\n<!-- experience-log-start -->\n\n<!-- experience-log-end -->\n", encoding="utf-8")
    _info(f"已重置: {path.name}")


def _reset_reflect_index(path: Path) -> None:
    template = """# REFLECT_INDEX — 反思索引

## 待消费

| id | 轮次 | 触发 | 下轮建议 | 状态 |
|----|------|------|----------|------|
| （无） | | | | |

## 已消费

| id | 轮次 | 触发 | 下轮建议 | 消费时间 |
|----|------|------|----------|----------|
| （无） | | | | |

## 归档

| id | 轮次 | 触发 | 下轮建议 | 归档时间 |
|----|------|------|----------|----------|
| （无） | | | | |
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(template, encoding="utf-8")
    _info(f"已重置: {path.relative_to(path.parent.parent)}")


def plan_factory(repo_root: Path) -> dict:
    repo_root = repo_root.resolve()
    items = []

    for d in CLEAR_DIRS:
        dp = repo_root / d
        if dp.is_dir():
            count = sum(1 for _ in dp.rglob("*") if _.is_file())
            item: dict = {"action": "clear_dir", "path": d, "count": count}
            if d == "saved":
                ext_dir = dp / "external_evidence"
                if ext_dir.is_dir():
                    ext_files = sorted(
                        str(p.relative_to(repo_root))
                        for p in ext_dir.glob("*")
                        if p.is_file()
                    )
                    item["external_evidence_glob"] = SAVED_EXTERNAL_EVIDENCE_GLOB
                    item["external_evidence_files"] = ext_files
            items.append(item)

    exp_path = repo_root / "EXPERIENCE.md"
    if exp_path.is_file():
        size = exp_path.stat().st_size
        items.append({"action": "archive_and_reset", "path": "EXPERIENCE.md", "size": size})

    idx_path = repo_root / "references" / "REFLECT_INDEX.md"
    if idx_path.is_file():
        items.append({"action": "archive_and_reset", "path": "references/REFLECT_INDEX.md", "size": idx_path.stat().st_size})

    progress = repo_root / "progress.txt"
    if progress.is_file():
        items.append({"action": "delete", "path": "progress.txt"})

    return {
        "repo_root": str(repo_root),
        "archive_dir": f"{ARCHIVE_DIR}/archive-{_archive_stamp()}",
        "items": items,
    }


def apply_factory(repo_root: Path, *, dry_run: bool = True) -> dict:
    plan = plan_factory(repo_root)
    repo_root = Path(plan["repo_root"])

    _info(f"模式: tier=factory dry_run={dry_run}")

    if not plan["items"]:
        _info("仓库已为绿场状态，无需清理")
        return plan

    archive_rel = plan["archive_dir"]
    _info(f"归档目标: {archive_rel}/")

    for item in plan["items"]:
        action = item["action"]
        path = item["path"]
        if action == "clear_dir":
            _info(f"  将清空: {path}/ ({item['count']} 个文件)")
        elif action == "archive_and_reset":
            _info(f"  将归档并重置: {path}")
        elif action == "delete":
            _info(f"  将删除: {path}")

    _info("将保留: contract/、workspace/、train.py、experiment.py、nn-config.yaml、scripts/ 等")
    _warn("factory 是最高破坏性操作，不可逆（归档在 _runs_legacy/ 可手动恢复）")

    if dry_run:
        _info("dry-run 结束；确认后请加 --apply --confirm factory")
        return plan

    archive_dir = repo_root / archive_rel
    archive_dir.mkdir(parents=True, exist_ok=True)
    _info(f"归档目录: {archive_rel}/")

    for item in plan["items"]:
        action = item["action"]
        src = repo_root / item["path"]

        if action == "clear_dir":
            if not src.is_dir():
                continue
            # Archive the whole directory
            dst = archive_dir / item["path"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(str(src), str(dst), dirs_exist_ok=True)
            # Clear contents but keep the dir
            for child in list(src.iterdir()):
                if child.is_dir():
                    shutil.rmtree(str(child))
                else:
                    child.unlink()
            _info(f"已归档并清空: {item['path']}/")

        elif action == "archive_and_reset":
            if not src.is_file():
                continue
            dst = archive_dir / item["path"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))

            if src.name == "EXPERIENCE.md":
                _reset_experience(src)
            elif src.name == "REFLECT_INDEX.md":
                _reset_reflect_index(src)

        elif action == "delete":
            if src.is_file():
                src.unlink()
                _info(f"已删除: {item['path']}")

    try:
        from lib.skill_activity import reset_log

        reset_log(repo_root)
        _info("已清空: .auto-nn/skill-activity.jsonl（保留 init-qa-log / migration-summary）")
    except Exception as exc:
        _warn(f"skill-activity reset 跳过: {exc}")

    _info(f"factory reset 完成；归档于 {archive_rel}/")
    _info("建议: bash scripts/smoke-check.sh && bash scripts/nn-doctor.sh")
    return plan


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--apply", action="store_true", help="执行（默认 dry-run；还需 --confirm factory）")
    ap.add_argument("--json", action="store_true", help="输出 JSON 计划")
    args = ap.parse_args()

    plan = apply_factory(args.repo_root.resolve(), dry_run=not args.apply)

    if args.json:
        import json
        print(json.dumps(plan, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
