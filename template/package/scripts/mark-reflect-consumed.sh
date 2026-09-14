#!/usr/bin/env bash
# 将 references/REFLECT_INDEX.md 的 pending 行移至历史（实验轮结束后由 auto-run 调用）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
SUMMARY="${1:-已消费（auto-run）}"
if poetry run python scripts/mark_reflect_consumed.py "$SUMMARY" 2>/dev/null; then
  exit 0
fi
python3 scripts/mark_reflect_consumed.py "$SUMMARY"
