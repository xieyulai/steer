#!/usr/bin/env bash
# 人改 HUMAN_GUIDANCE 并 commit 后，刷新批次基线（慎用：确保正文正确）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
APPLY=0
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    -h|--help)
      echo "用法: bash scripts/refresh-human-guidance-baseline.sh [--apply]"
      exit 0
      ;;
  esac
done
if [[ "$APPLY" -ne 1 ]]; then
  echo "[refresh-human-guidance-baseline] dry-run: 将重写 saved/.human-guidance-baseline.json"
  echo "  确认: bash scripts/refresh-human-guidance-baseline.sh --apply"
  exit 0
fi
if [[ -f saved/.auto-run-active.pid ]] && nn_pid="$(cat saved/.auto-run-active.pid 2>/dev/null)" && [[ -n "${nn_pid}" ]] && kill -0 "$nn_pid" 2>/dev/null; then
  echo "[refresh-human-guidance-baseline] REFUSE: auto-run batch 活跃" >&2
  exit 1
fi
python3 scripts/human_guidance_gate.py --repo-root . refresh
