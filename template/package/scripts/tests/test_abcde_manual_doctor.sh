#!/usr/bin/env bash
# test_abcde_manual_doctor.sh — TDD for nn-doctor.sh check_abcde_manual()
#
# Scenario A: 无 references/manual/abcde-manual.md → FAIL
# Scenario B: 有该文件 → PASS
#
# 跑法: bash template/package/scripts/tests/test_abcde_manual_doctor.sh

set -euo pipefail

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCTOR="$SCRIPTS/nn-doctor.sh"
TMP_BASE="$(mktemp -d -t abcde-manual-doctor-XXXXXX)"
trap 'rm -rf "$TMP_BASE"' EXIT

PASS_COUNT=0
FAIL_COUNT=0
ok()   { echo "  OK: $*"; PASS_COUNT=$((PASS_COUNT+1)); }
fail() { echo "FAIL: $*" >&2; FAIL_COUNT=$((FAIL_COUNT+1)); }

extract_fn() {
  local body
  body="$(awk '/^check_abcde_manual\(\) \{/{f=1} f{print} f&&/^\}/{exit}' "$DOCTOR")"
  if [[ -z "$body" ]]; then
    return 1
  fi
  printf '%s\n' "$body"
}

ROWS=""
row() { echo "$2|$3" >> "$ROWS"; }

run_check() {
  local fixture="$1"
  ROWS="$(mktemp -p "$TMP_BASE")"
  (
    cd "$fixture"
    IS_TEMPLATE_ROOT=0
    eval "$FN_BODY"
    check_abcde_manual
  ) > /dev/null 2>&1 || true
}

if ! FN_BODY="$(extract_fn)"; then
  echo "FAIL: check_abcde_manual 未在 nn-doctor.sh 实现" >&2
  exit 1
fi

echo "=== Scenario A: 无 abcde-manual.md → FAIL"
REPO_A="$TMP_BASE/a"; mkdir -p "$REPO_A/references/manual"
run_check "$REPO_A"
if grep -q '^FAIL|' "$ROWS"; then ok "缺手册 → FAIL"; else fail "A 应 FAIL: $(cat "$ROWS")"; fi
if grep -q '^PASS|' "$ROWS"; then fail "A 不应 PASS"; else ok "A 无 PASS"; fi

echo "=== Scenario B: 有 abcde-manual.md → PASS"
REPO_B="$TMP_BASE/b"; mkdir -p "$REPO_B/references/manual"
echo "# manual" > "$REPO_B/references/manual/abcde-manual.md"
run_check "$REPO_B"
if grep -q '^PASS|' "$ROWS"; then ok "有手册 → PASS"; else fail "B 应 PASS: $(cat "$ROWS")"; fi
if grep -q '^FAIL|' "$ROWS"; then fail "B 不应 FAIL"; else ok "B 无 FAIL"; fi

echo "=== 汇总: PASS=$PASS_COUNT FAIL=$FAIL_COUNT"
if [[ $FAIL_COUNT -eq 0 ]]; then echo "ALL PASS"; exit 0; else echo "FAIL"; exit 1; fi
