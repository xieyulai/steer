#!/usr/bin/env bash
# test_baseline_tag_doctor.sh — TDD for nn-doctor.sh check_baseline_tag()
#
# 场景 A: 无 _runs/exp → 无输出（return 0）
# 场景 B: config.json 含 baseline_tag → PASS 行
# 场景 C: config.json 缺 baseline_tag → WARN 行
#
# 跑法: bash template/package/scripts/tests/test_baseline_tag_doctor.sh

set -euo pipefail

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCTOR="$SCRIPTS/nn-doctor.sh"
TMP_BASE="$(mktemp -d -t baseline-tag-doctor-XXXXXX)"
trap 'rm -rf "$TMP_BASE"' EXIT

PASS_COUNT=0
FAIL_COUNT=0
ok()   { echo "  OK: $*"; PASS_COUNT=$((PASS_COUNT+1)); }
fail() { echo "FAIL: $*" >&2; FAIL_COUNT=$((FAIL_COUNT+1)); }

# 提取 check_baseline_tag() 函数体（定义行到首个单独的 `}`）
extract_fn() {
  local body
  body="$(awk '/^check_baseline_tag\(\) \{/{f=1} f{print} f&&/^\}/{exit}' "$DOCTOR")"
  if [[ -z "$body" ]]; then
    return 1
  fi
  printf '%s\n' "$body"
}

# row stub：nn-doctor 调 row "label" WARN "msg" → $1=label $2=WARN $3=msg
ROWS=""
row() { echo "$2|$3" >> "$ROWS"; }

run_check() {
  local fixture="$1"
  ROWS="$(mktemp -p "$TMP_BASE")"
  (
    cd "$fixture"
    eval "$FN_BODY"
    check_baseline_tag
  ) > /dev/null 2>&1 || true
}

# ── 前置: check_baseline_tag 必须已实现（RED 守卫）──
if ! FN_BODY="$(extract_fn)"; then
  echo "FAIL: check_baseline_tag 未在 nn-doctor.sh 实现" >&2
  exit 1
fi

# ── Scenario A: 无 _runs/exp → 无输出 ──
echo "=== Scenario A: 无 _runs/exp"
REPO_A="$TMP_BASE/a"; mkdir -p "$REPO_A"
run_check "$REPO_A"
if [[ ! -s "$ROWS" ]]; then ok "无 _runs/exp 无输出"; else fail "A 不应有输出: $(cat "$ROWS")"; fi

# ── Scenario B: config.json 含 baseline_tag → PASS ──
echo "=== Scenario B: config.json 含 baseline_tag"
REPO_B="$TMP_BASE/b"; mkdir -p "$REPO_B/_runs/exp/exp001"
echo '{"LR":0.001,"baseline_tag":"none","_repro":{}}' > "$REPO_B/_runs/exp/exp001/config.json"
run_check "$REPO_B"
if grep -q '^PASS|' "$ROWS"; then ok "含 baseline_tag → PASS"; else fail "B 应 PASS: $(cat "$ROWS")"; fi
if grep -q '^WARN|' "$ROWS"; then fail "B 不应 WARN"; else ok "B 无 WARN"; fi

# ── Scenario C: config.json 缺 baseline_tag → WARN ──
echo "=== Scenario C: config.json 缺 baseline_tag"
REPO_C="$TMP_BASE/c"; mkdir -p "$REPO_C/_runs/exp/exp002"
echo '{"LR":0.001,"_repro":{}}' > "$REPO_C/_runs/exp/exp002/config.json"
run_check "$REPO_C"
if grep -q '^WARN|' "$ROWS"; then ok "缺 baseline_tag → WARN"; else fail "C 应 WARN: $(cat "$ROWS")"; fi

echo "=== 汇总: PASS=$PASS_COUNT FAIL=$FAIL_COUNT"
if [[ $FAIL_COUNT -eq 0 ]]; then echo "ALL PASS"; exit 0; else echo "FAIL"; exit 1; fi
