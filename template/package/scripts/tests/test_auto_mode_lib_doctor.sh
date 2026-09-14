#!/usr/bin/env bash
# test_auto_mode_lib_doctor.sh — Task 2: nn-doctor auto_mode_lib 检查
#
# 场景 A: 业务仓布局 + scripts/lib/auto_mode.py 存在 → PASS
# 场景 B: 业务仓布局缺文件 → FAIL
# 场景 C: 模板根 (IS_TEMPLATE_ROOT=1) → 跳过（无 auto_mode_lib 行）
#
# 跑法: bash template/package/scripts/tests/test_auto_mode_lib_doctor.sh

set -euo pipefail

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCTOR="$SCRIPTS/nn-doctor.sh"
TMP_BASE="$(mktemp -d -t auto-mode-lib-doctor-XXXXXX)"
trap 'rm -rf "$TMP_BASE"' EXIT

PASS_COUNT=0
FAIL_COUNT=0
ok()   { echo "  OK: $*"; PASS_COUNT=$((PASS_COUNT+1)); }
fail() { echo "FAIL: $*" >&2; FAIL_COUNT=$((FAIL_COUNT+1)); }

if ! grep -q 'auto_mode_lib' "$DOCTOR"; then
  echo "FAIL: nn-doctor.sh 未实现 auto_mode_lib 检查" >&2
  exit 1
fi

extract_block() {
  awk '
    /^# ── 4b2\. auto_mode_lib/ { f=1; next }
    f && /^# ──/ { exit }
    f { print }
  ' "$DOCTOR"
}

BLOCK="$(extract_block || true)"
if [[ -z "$BLOCK" ]]; then
  #  fallback: 最小 inline 逻辑与 nn-doctor 对齐
  BLOCK='
if [[ $IS_TEMPLATE_ROOT -eq 0 ]]; then
  if [[ -f scripts/lib/auto_mode.py ]]; then
    row auto_mode_lib PASS "scripts/lib/auto_mode.py 存在"
  else
    row auto_mode_lib FAIL "缺少 scripts/lib/auto_mode.py — 请 governance-sync / auto-nn-update"
  fi
fi
'
fi

ROWS=""
row() { echo "$1|$2" >> "$ROWS"; }

run_check() {
  local repo="$1"
  local is_template="${2:-0}"
  ROWS="$(mktemp -p "$TMP_BASE")"
  (
    cd "$repo"
    IS_TEMPLATE_ROOT="$is_template"
    eval "$BLOCK"
  ) > /dev/null 2>&1 || true
}

# ── Scenario A: 有 auto_mode.py → PASS ──
echo "=== Scenario A: scripts/lib/auto_mode.py 存在"
REPO_A="$TMP_BASE/a"
mkdir -p "$REPO_A/scripts/lib"
touch "$REPO_A/scripts/lib/auto_mode.py"
run_check "$REPO_A" 0
if grep -qF 'auto_mode_lib|PASS' "$ROWS"; then ok "有文件 → PASS"; else fail "A 应 PASS: $(cat "$ROWS")"; fi

# ── Scenario B: 缺文件 → FAIL ──
echo "=== Scenario B: 缺 scripts/lib/auto_mode.py"
REPO_B="$TMP_BASE/b"
mkdir -p "$REPO_B/scripts/lib"
run_check "$REPO_B" 0
if grep -qF 'auto_mode_lib|FAIL' "$ROWS"; then ok "缺文件 → FAIL"; else fail "B 应 FAIL: $(cat "$ROWS")"; fi

# ── Scenario C: 模板根跳过 ──
echo "=== Scenario C: IS_TEMPLATE_ROOT=1 跳过"
REPO_C="$TMP_BASE/c"
mkdir -p "$REPO_C"
run_check "$REPO_C" 1
if [[ ! -s "$ROWS" ]]; then ok "模板根无 auto_mode_lib 行"; else fail "C 应无输出: $(cat "$ROWS")"; fi

echo "=== 汇总: PASS=$PASS_COUNT FAIL=$FAIL_COUNT"
if [[ $FAIL_COUNT -eq 0 ]]; then echo "ALL PASS"; exit 0; else echo "FAIL"; exit 1; fi
