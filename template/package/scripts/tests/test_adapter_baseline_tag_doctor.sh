#!/usr/bin/env bash
# test_adapter_baseline_tag_doctor.sh — check_adapter_baseline_tag()（行名遗留）
#
# 场景 A: 非 runner 出分 → 无输出（SKIP/静默）
# 场景 B: EVALUATE_RUNNER + watchlist/TSV 均缺 baseline_tag → FAIL
# 场景 C: EVALUATE_RUNNER + watchlist 与 TSV 表头均有 baseline_tag → PASS
# 场景 D: EVALUATE_RUNNER + 无 results.tsv、watchlist 齐 → PASS（TSV 不存在不 FAIL）
#
# 跑法: bash template/package/scripts/tests/test_adapter_baseline_tag_doctor.sh

set -euo pipefail

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCTOR="$SCRIPTS/nn-doctor.sh"
TMP_BASE="$(mktemp -d -t adapter-baseline-tag-doctor-XXXXXX)"
trap 'rm -rf "$TMP_BASE"' EXIT

PASS_COUNT=0
FAIL_COUNT=0
ok()   { echo "  OK: $*"; PASS_COUNT=$((PASS_COUNT+1)); }
fail() { echo "FAIL: $*" >&2; FAIL_COUNT=$((FAIL_COUNT+1)); }

extract_fn() {
  local body
  body="$(awk '/^check_adapter_baseline_tag\(\) \{/{f=1} f{print} f&&/^\}/{exit}' "$DOCTOR")"
  if [[ -z "$body" ]]; then
    return 1
  fi
  printf '%s\n' "$body"
}

ROWS=""
row() { echo "$2|$3" >> "$ROWS"; }

write_nn_config() {
  local repo="$1"
  local metrics_shape="${2:-}"
  local watchlist_yaml="${3:-}"
  cat > "$repo/nn-config.yaml" <<EOF
profile: default
workspace:
  metrics_shape: ${metrics_shape}
ledger:
  watchlist:
${watchlist_yaml}
EOF
}

run_check() {
  local fixture="$1"
  ROWS="$(mktemp -p "$TMP_BASE")"
  (
    cd "$fixture"
    SCRIPT_DIR="$SCRIPTS"
    eval "$FN_BODY"
    check_adapter_baseline_tag
  ) > /dev/null 2>&1 || true
}

if ! FN_BODY="$(extract_fn)"; then
  echo "FAIL: check_adapter_baseline_tag 未在 nn-doctor.sh 实现" >&2
  exit 1
fi

# ── Scenario A: 非 runner 出分 → 无输出 ──
echo "=== Scenario A: 非 runner 出分"
REPO_A="$TMP_BASE/a"
mkdir -p "$REPO_A"
write_nn_config "$REPO_A" "EVALUATE_LEARNER" "    - LR"
run_check "$REPO_A"
if [[ ! -s "$ROWS" ]]; then ok "非 runner 出分无输出"; else fail "A 不应有输出: $(cat "$ROWS")"; fi

# ── Scenario B: runner 出分 + watchlist/TSV 均缺 baseline_tag → FAIL ──
echo "=== Scenario B: runner 出分缺 baseline_tag"
REPO_B="$TMP_BASE/b"
mkdir -p "$REPO_B/_runs"
write_nn_config "$REPO_B" "EVALUATE_RUNNER" "    - LR"
printf 'run_id\tLR\n1\t0.001\n' > "$REPO_B/_runs/results.tsv"
run_check "$REPO_B"
if grep -q '^FAIL|' "$ROWS"; then ok "runner 缺列/watchlist → FAIL"; else fail "B 应 FAIL: $(cat "$ROWS")"; fi

# ── Scenario C: runner 出分 + 齐 → PASS ──
echo "=== Scenario C: runner 出分 baseline_tag 齐"
REPO_C="$TMP_BASE/c"
mkdir -p "$REPO_C/_runs"
write_nn_config "$REPO_C" "adapter" $'    - LR\n    - baseline_tag'
printf 'run_id\tLR\tbaseline_tag\n1\t0.001\tnone\n' > "$REPO_C/_runs/results.tsv"
run_check "$REPO_C"
if grep -q '^PASS|' "$ROWS"; then ok "runner 齐 → PASS"; else fail "C 应 PASS: $(cat "$ROWS")"; fi
if grep -q '^FAIL|' "$ROWS"; then fail "C 不应 FAIL: $(cat "$ROWS")"; else ok "C 无 FAIL"; fi

# ── Scenario D: runner 出分 + 无 TSV、watchlist 齐 → PASS ──
echo "=== Scenario D: runner 出分无 results.tsv"
REPO_D="$TMP_BASE/d"
mkdir -p "$REPO_D"
write_nn_config "$REPO_D" "EVALUATE_RUNNER" "    - baseline_tag"
run_check "$REPO_D"
if grep -q '^PASS|' "$ROWS"; then ok "无 TSV + watchlist 齐 → PASS"; else fail "D 应 PASS: $(cat "$ROWS")"; fi

echo "=== 汇总: PASS=$PASS_COUNT FAIL=$FAIL_COUNT"
if [[ $FAIL_COUNT -eq 0 ]]; then echo "ALL PASS"; exit 0; else echo "FAIL"; exit 1; fi
