#!/usr/bin/env bash
# test_doctor_env_sanity_cascade.sh — env 失败时 contract_sanity 须 SKIP 非 FAIL
#
# 跑法: bash template/package/scripts/tests/test_doctor_env_sanity_cascade.sh
set -euo pipefail

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCTOR="$SCRIPTS/nn-doctor.sh"

PASS_COUNT=0
FAIL_COUNT=0
ok()   { echo "  OK: $*"; PASS_COUNT=$((PASS_COUNT+1)); }
fail() { echo "FAIL: $*" >&2; FAIL_COUNT=$((FAIL_COUNT+1)); }

# 抽取 env_runtime / contract_sanity 段（§11）
extract_env_block() {
  awk '
    /^# ── 11\. 运行环境/{f=1}
    f{print}
    f && /^# ── 12\./{exit}
  ' "$DOCTOR"
}

BODY="$(extract_env_block)"
if [[ -z "$BODY" ]]; then
  echo "FAIL: 未找到 doctor §11 运行环境块" >&2
  exit 1
fi

# 断言源码契约：env 失败分支用 SKIP
if echo "$BODY" | grep -q 'row contract_sanity SKIP'; then
  ok "源码：env 失败 → contract_sanity SKIP"
else
  fail "源码应含: row contract_sanity SKIP"
fi
if echo "$BODY" | grep -q 'row contract_sanity FAIL.*"跳过（env_runtime'; then
  fail "源码不应再对跳过 sanity 记 FAIL"
else
  ok "源码：跳过 sanity 不再 FAIL"
fi

# check-env 动态库文案契约
CE="$SCRIPTS/check-env.sh"
if grep -q 'CUDA/cuDNN 动态库不可用' "$CE"; then
  ok "check-env 含动态库 FAIL 文案"
else
  fail "check-env 缺动态库文案"
fi
if grep -q 'check_env_import_classify' "$CE"; then
  ok "check-env 调用分类器"
else
  fail "check-env 未接线分类器"
fi

echo "=== 汇总: PASS=$PASS_COUNT FAIL=$FAIL_COUNT"
if [[ $FAIL_COUNT -eq 0 ]]; then echo "ALL PASS"; exit 0; else echo "FAIL"; exit 1; fi
