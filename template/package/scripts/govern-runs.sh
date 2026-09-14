#!/usr/bin/env bash
# govern-runs.sh — 运行态治理统一入口（clear）
#
# 用法:
#   bash scripts/govern-runs.sh clear --tier junk
#   bash scripts/govern-runs.sh clear --tier runs --apply
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CMD="${1:-}"
shift || true

case "$CMD" in
  clear)
    exec bash scripts/clear-runs.sh "$@"
    ;;
  prune|reset)
    echo "[govern-runs] 已废止: 子命令 \"$CMD\"。请改用 clear --tier …" >&2
    echo "  例: bash scripts/govern-runs.sh clear --tier junk" >&2
    echo "  例: bash scripts/govern-runs.sh clear --tier runs --apply" >&2
    echo "  详见 PROTOCOL §1 与技能 /auto-nn-clear" >&2
    exit 1
    ;;
  -h|--help|"")
    cat <<'EOF'
用法: govern-runs.sh clear [clear-runs.sh 参数…]

  clear   → scripts/clear-runs.sh（C0–C6 + custom；默认 dry-run）

已废止（硬切）:
  prune / reset → 请用 clear --tier junk | runs | custom …

示例:
  bash scripts/govern-runs.sh clear --tier inspect
  bash scripts/govern-runs.sh clear --tier junk --apply
  bash scripts/govern-runs.sh clear --tier custom --drop-experiment preflight_check --apply
EOF
    exit 0
    ;;
  *)
    echo "[govern-runs] 未知子命令: $CMD（须 clear）" >&2
    exit 1
    ;;
esac
