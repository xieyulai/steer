#!/usr/bin/env bash
# 官方迁移分析 CLI 包装（逻辑在 skills/maintainer/auto-nn-init/migration-compare.py）
# 用法:
#   bash scripts/migration-compare.sh --template-root <模板根> --project-root <目标项目根> [--json]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILL_ROOT="$ROOT/skills/maintainer/auto-nn-init"
export PYTHONPATH="$SKILL_ROOT:$ROOT/template/package:$ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec python3 "$SKILL_ROOT/migration-compare.py" "$@"
