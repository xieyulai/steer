#!/usr/bin/env bash
# check_package_docs_contract.sh — PROTOCOL/CLAUDE 文档漂移 lint（第一批）
#
# 用法:
#   bash scripts/check_package_docs_contract.sh
#   bash scripts/check_package_docs_contract.sh --quiet
#   bash scripts/check_package_docs_contract.sh --base HEAD~3
#   bash scripts/check_package_docs_contract.sh --no-git
#
# 退出码: 0=无 FAIL（可有 WARN）；1=至少 1 FAIL
# CHECK_PACKAGE_DOCS_CONTRACT_SKIP=1 可临时跳过（仅供排障；release-check 同步认此变量）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$ROOT"

if [[ "${CHECK_PACKAGE_DOCS_CONTRACT_SKIP:-0}" == "1" ]]; then
  echo "[package-docs-contract] SKIP (CHECK_PACKAGE_DOCS_CONTRACT_SKIP=1)"
  exit 0
fi

exec python3 "$SCRIPT_DIR/lib/package_docs_contract.py" "$@"
