#!/usr/bin/env bash
# migrate-drop-progress.sh — 废弃 progress.txt，初始化 experiment_journal.json
#
# 用法:
#   bash scripts/migrate-drop-progress.sh [--dry-run|--apply]
#   bash scripts/migrate-drop-progress.sh --repo-root /path/to/project --apply
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DRY_RUN=1

usage() {
  cat <<'EOF'
用法: migrate-drop-progress.sh [--dry-run|--apply] [--repo-root PATH]

  --dry-run   默认：打印将执行的操作
  --apply     归档 progress.txt → progress.txt.bak；缺失时写入空 journal
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root)
      ROOT="$(cd "${2:-}" && pwd)"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --apply)
      DRY_RUN=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[migrate-drop-progress] 未知参数: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

cd "$ROOT"

PROGRESS="progress.txt"
JOURNAL="saved/experiment_journal.json"

if [[ -f "$PROGRESS" ]]; then
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[migrate-drop-progress] dry-run: mv $PROGRESS → ${PROGRESS}.bak"
  else
    mv -f "$PROGRESS" "${PROGRESS}.bak"
    echo "[migrate-drop-progress] 已归档: ${PROGRESS}.bak"
  fi
else
  echo "[migrate-drop-progress] 无 $PROGRESS，跳过归档"
fi

if [[ ! -f "$JOURNAL" ]]; then
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[migrate-drop-progress] dry-run: 将写入空 $JOURNAL"
  else
    [[ -f scripts/lib/experiment_journal.py ]] || {
      echo "[migrate-drop-progress] 错误: 缺少 scripts/lib/experiment_journal.py" >&2
      exit 1
    }
    python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, 'scripts')
from lib.experiment_journal import empty_journal, journal_path, write_journal
p = journal_path(Path('.'))
write_journal(p, empty_journal())
print('[migrate-drop-progress] 已写入', p)
"
  fi
else
  echo "[migrate-drop-progress] $JOURNAL 已存在，跳过初始化"
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[migrate-drop-progress] dry-run 结束；确认后请加 --apply"
fi
