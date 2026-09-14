#!/usr/bin/env bash
# test_scenario_not_in_contract_doctor.sh — Task 3: check_scenario_not_in_contract()
#
# 场景 A: 模板根 → 跳过（无 scenario_not_in_contract 行）
# 场景 B: 无 contract/ → PASS
# 场景 C: 干净 contract → PASS
# 场景 D: contract 含 SCENARIO_ID → FAIL
#
# 跑法: bash template/package/scripts/tests/test_scenario_not_in_contract_doctor.sh

set -euo pipefail

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCTOR="$SCRIPTS/nn-doctor.sh"
TMP_BASE="$(mktemp -d -t scenario-not-in-contract-doctor-XXXXXX)"
trap 'rm -rf "$TMP_BASE"' EXIT

PASS_COUNT=0
FAIL_COUNT=0
ok()   { echo "  OK: $*"; PASS_COUNT=$((PASS_COUNT+1)); }
fail() { echo "FAIL: $*" >&2; FAIL_COUNT=$((FAIL_COUNT+1)); }

extract_fn() {
  awk '/^check_scenario_not_in_contract\(\) \{/{f=1} f{print} f&&/^\}/{exit}' "$DOCTOR"
}

ROWS=""
row() { echo "$1|$2" >> "$ROWS"; }

run_check() {
  local fixture="$1"
  local is_template="${2:-0}"
  ROWS="$(mktemp -p "$TMP_BASE")"
  (
    cd "$fixture"
    IS_TEMPLATE_ROOT="$is_template"
    SCRIPT_DIR="$SCRIPTS"
    eval "$FN_BODY"
    check_scenario_not_in_contract
  ) > /dev/null 2>&1 || true
}

if ! FN_BODY="$(extract_fn)"; then
  echo "FAIL: check_scenario_not_in_contract 未在 nn-doctor.sh 实现" >&2
  exit 1
fi

# ── Scenario A: 模板根跳过 ──
echo "=== Scenario A: IS_TEMPLATE_ROOT=1 跳过"
REPO_A="$TMP_BASE/a"
mkdir -p "$REPO_A/scripts/lib"
cp "$SCRIPTS/lib/scenario_contract_guard.py" "$REPO_A/scripts/lib/"
run_check "$REPO_A" 1
if [[ ! -s "$ROWS" ]]; then ok "模板根无输出"; else fail "A 不应有输出: $(cat "$ROWS")"; fi

# ── Scenario B: 无 contract/ → PASS ──
echo "=== Scenario B: 无 contract/"
REPO_B="$TMP_BASE/b"
mkdir -p "$REPO_B/scripts/lib"
cp "$SCRIPTS/lib/scenario_contract_guard.py" "$REPO_B/scripts/lib/"
run_check "$REPO_B" 0
if grep -qF 'scenario_not_in_contract|PASS' "$ROWS"; then ok "无 contract → PASS"; else fail "B 应 PASS: $(cat "$ROWS")"; fi

# ── Scenario C: 干净 contract → PASS ──
echo "=== Scenario C: 干净 contract"
REPO_C="$TMP_BASE/c"
mkdir -p "$REPO_C/contract" "$REPO_C/scripts/lib"
cp "$SCRIPTS/lib/scenario_contract_guard.py" "$REPO_C/scripts/lib/"
printf 'METRIC_KEYS = {}\n' > "$REPO_C/contract/metrics.py"
run_check "$REPO_C" 0
if grep -qF 'scenario_not_in_contract|PASS' "$ROWS"; then ok "干净 contract → PASS"; else fail "C 应 PASS: $(cat "$ROWS")"; fi

# ── Scenario D: SCENARIO_ID 回潮 → FAIL ──
echo "=== Scenario D: contract 含 SCENARIO_ID"
REPO_D="$TMP_BASE/d"
mkdir -p "$REPO_D/contract" "$REPO_D/scripts/lib"
cp "$SCRIPTS/lib/scenario_contract_guard.py" "$REPO_D/scripts/lib/"
printf 'SCENARIO_ID = "x"\n' > "$REPO_D/contract/metrics.py"
run_check "$REPO_D" 0
if grep -qF 'scenario_not_in_contract|FAIL' "$ROWS"; then ok "SCENARIO_ID → FAIL"; else fail "D 应 FAIL: $(cat "$ROWS")"; fi

echo "=== 汇总: PASS=$PASS_COUNT FAIL=$FAIL_COUNT"
if [[ $FAIL_COUNT -eq 0 ]]; then echo "ALL PASS"; exit 0; else echo "FAIL"; exit 1; fi
