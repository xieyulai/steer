#!/usr/bin/env bash
# test_baseline_reference_doctor.sh — ③-i Task C: check_baseline_reference 三场景
#
# 镜像 test_baseline_tag_doctor.sh：awk 抽取函数体 + row() stub（nn-doctor 用
# relative 路径 EXPERIENCE.md + row name STATUS msg + 恒 return 0；非 REPO 变量/exit 码）。
#
# 场景 A: EXPERIENCE 有「基线锚点」段且 reference_anchor_value 合法 float → 无 WARN
# 场景 B: 有段但 reference_anchor_value 非 float（"abc"）→ WARN
# 场景 C: 无段（novel） → 无输出（段缺失是常态）
#
# 跑法: bash template/package/scripts/tests/test_baseline_reference_doctor.sh

set -euo pipefail

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCTOR="$SCRIPTS/nn-doctor.sh"
TMP_BASE="$(mktemp -d -t baseline-ref-doctor-XXXXXX)"
trap 'rm -rf "$TMP_BASE"' EXIT

PASS_COUNT=0
FAIL_COUNT=0
ok()   { echo "  OK: $*"; PASS_COUNT=$((PASS_COUNT+1)); }
fail() { echo "FAIL: $*" >&2; FAIL_COUNT=$((FAIL_COUNT+1)); }

# 提取 check_baseline_reference() 函数体（定义行到首个单独的 `}`）
extract_fn() {
  local body
  body="$(awk '/^check_baseline_reference\(\) \{/{f=1} f{print} f&&/^\}/{exit}' "$DOCTOR")"
  if [[ -z "$body" ]]; then
    return 1
  fi
  printf '%s\n' "$body"
}

# row stub：nn-doctor 调 row "label" WARN "msg" → $2=STATUS $3=msg
ROWS=""
row() { echo "$2|$3" >> "$ROWS"; }

run_check() {
  local fixture="$1"
  ROWS="$(mktemp -p "$TMP_BASE")"
  (
    cd "$fixture"
    eval "$FN_BODY"
    check_baseline_reference
  ) > /dev/null 2>&1 || true
}

# ── 前置: check_baseline_reference 必须已实现（RED 守卫）──
if ! FN_BODY="$(extract_fn)"; then
  echo "FAIL: check_baseline_reference 未在 nn-doctor.sh 实现" >&2
  exit 1
fi

# ── Scenario A: 段在 + reference_anchor_value=0.9850 → 无 WARN ──
echo "=== Scenario A: 段在 + reference_anchor_value=0.9850"
REPO_A="$TMP_BASE/a"; mkdir -p "$REPO_A"
printf '## 基线锚点（external reference，init 探测，固定）\n\n- reference_anchor_value: 0.9850\n- reference_source: README\n- reference_ref: README.md\n' > "$REPO_A/EXPERIENCE.md"
run_check "$REPO_A"
if ! grep -q '^WARN|' "$ROWS"; then ok "合法 float 无 WARN"; else fail "A 不应 WARN: $(cat "$ROWS")"; fi

# ── Scenario B: 段在 + reference_anchor_value=abc → WARN ──
echo "=== Scenario B: 段在 + reference_anchor_value=abc (非 float)"
REPO_B="$TMP_BASE/b"; mkdir -p "$REPO_B"
printf '## 基线锚点（external reference）\n\n- reference_anchor_value: abc\n' > "$REPO_B/EXPERIENCE.md"
run_check "$REPO_B"
if grep -q '^WARN|' "$ROWS"; then ok "非 float → WARN"; else fail "B 应 WARN: $(cat "$ROWS")"; fi

# ── Scenario C: 无段（novel） → 无输出 ──
echo "=== Scenario C: 无「基线锚点」段（novel）"
REPO_C="$TMP_BASE/c"; mkdir -p "$REPO_C"
printf '## Tier 状态\n| Tier | routine |\n|---|---|\n| A | x |\n' > "$REPO_C/EXPERIENCE.md"
run_check "$REPO_C"
if [[ ! -s "$ROWS" ]]; then ok "novel 段缺失无输出"; else fail "C 不应有输出: $(cat "$ROWS")"; fi

echo "=== 汇总: PASS=$PASS_COUNT FAIL=$FAIL_COUNT"
if [[ $FAIL_COUNT -eq 0 ]]; then echo "ALL PASS"; exit 0; else echo "FAIL"; exit 1; fi
