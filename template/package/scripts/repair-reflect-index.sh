#!/usr/bin/env bash
# 修复 REFLECT_INDEX.md 历史表结构（不删 pending）。
# 若 pending 误放在 blockquote 内导致 parse_pending_cells 失败，--apply 会重建
# ## 待消费 表结构并将有效 pending 移出 blockquote（不删历史数据行）。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
APPLY=0
for arg in "$@"; do
  [[ "$arg" == "--apply" ]] && APPLY=1
done
export NN_REPAIR_APPLY="$APPLY"
if poetry run python scripts/repair_reflect_index.py 2>/dev/null; then
  exit 0
fi
python3 scripts/repair_reflect_index.py
