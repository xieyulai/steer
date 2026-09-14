"""v1.33.0 — 业务仓一次性迁移脚本:workspace_kind → metrics_shape。

用法:
  python3 scripts/lib/migrate_metrics_shape.py <repo_root> [--dry-run] [--no-backup]
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_REWRITES = [
    (re.compile(r'workspace_kind="supervised"'), 'metrics_shape="evaluate_learner"'),
    (re.compile(r"workspace_kind='supervised'"), "metrics_shape='evaluate_learner'"),
    (re.compile(r'workspace_kind="adapter"'), 'metrics_shape="evaluate_runner"'),
    (re.compile(r"workspace_kind='adapter'"), "metrics_shape='evaluate_runner'"),
    (re.compile(r'workspace_kind="mammoth_cl"'),
     'metrics_shape="evaluate_learner"  # v1.33.0 — framework_kind=MAMMOTH 已在 workspace 装饰器声明'),
    (re.compile(r'^(\s*)kind:\s*supervised$', re.MULTILINE),
     r'\1metrics_shape: evaluate_learner'),
    (re.compile(r'^(\s*)kind:\s*adapter$', re.MULTILINE),
     r'\1metrics_shape: evaluate_runner'),
    (re.compile(r'^(\s*)kind:\s*mammoth_cl$', re.MULTILINE),
     r'\1metrics_shape: evaluate_learner  # v1.33.0 — framework_kind: mammoth 已在 workspace 装饰器声明'),
]


def rewrite_text(content: str) -> str:
    for pattern, replacement in _REWRITES:
        content = pattern.sub(replacement, content)
    return content


def needs_migration(content: str) -> bool:
    if "workspace_kind=" in content:
        return True
    if re.search(r"^\s*kind:\s*(supervised|adapter|mammoth_cl)\s*$",
                 content, re.MULTILINE):
        return True
    return False


def migrate_file(path: Path, *, dry_run: bool = False, backup: bool = True) -> bool:
    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return False
    if not needs_migration(content):
        return False
    new_content = rewrite_text(content)
    if new_content == content:
        return False
    if dry_run:
        print(f"[DRY-RUN] {path}: would modify")
        return True
    if backup:
        backup_path = path.with_suffix(path.suffix + ".bak")
        if not backup_path.exists():
            backup_path.write_text(content, encoding="utf-8")
    path.write_text(new_content, encoding="utf-8")
    print(f"[MODIFIED] {path}")
    return True


def migrate_repo(repo_root: Path, *, dry_run: bool = False,
                 backup: bool = True) -> int:
    repo_root = Path(repo_root).resolve()
    if not repo_root.is_dir():
        print(f"ERROR: {repo_root} 不是目录", file=sys.stderr)
        return 0
    modified_count = 0
    targets: list[Path] = []
    for py in repo_root.rglob("*.py"):
        parts = py.parts
        if any(p in parts for p in (".venv", "site-packages", "_backend_", "__pycache__")):
            continue
        targets.append(py)
    cfg_yaml = repo_root / "nn-config.yaml"
    if cfg_yaml.exists():
        targets.append(cfg_yaml)
    for path in targets:
        if migrate_file(path, dry_run=dry_run, backup=backup):
            modified_count += 1
    print(f"\n{'[DRY-RUN] ' if dry_run else ''}Migrated {modified_count} file(s).")
    return modified_count


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Migrate workspace_kind → metrics_shape (v1.33.0)"
    )
    p.add_argument("repo_root", type=Path,
                   help="业务仓根目录(扫 .py + nn-config.yaml)")
    p.add_argument("--dry-run", action="store_true",
                   help="只打印改动,不实际改写")
    p.add_argument("--no-backup", action="store_true",
                   help="不写 .bak 备份")
    args = p.parse_args(argv)
    count = migrate_repo(args.repo_root, dry_run=args.dry_run,
                         backup=not args.no_backup)
    return 0 if count >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())