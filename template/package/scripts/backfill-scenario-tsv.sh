#!/usr/bin/env bash
# 场景台账回填：转发 backfill_scenario_tsv.py（业务仓 scripts/ 与 template/package 同路径）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$ROOT/scripts/backfill_scenario_tsv.py"
if [[ ! -f "$PY" ]]; then
  PY="$ROOT/template/package/scripts/backfill_scenario_tsv.py"
fi
exec python3 "$PY" --repo-root "$ROOT" "$@"
