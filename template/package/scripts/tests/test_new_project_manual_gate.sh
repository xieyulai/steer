#!/usr/bin/env bash
# test_new_project_manual_gate.sh — 形式闸门 #1：接线与硬失败语义
#
# 1) 静态：SOURCE_ROOT 路径必须出现 --source-root
# 2) 静态：禁止「不影响立项」
# 3) 行为：缺手册目录时模拟收尾断言 → 写标记 + 非零（抽同逻辑）
#
# 跑法: bash template/package/scripts/tests/test_new_project_manual_gate.sh

set -euo pipefail

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NP="$SCRIPTS/new-project.sh"
TMP_BASE="$(mktemp -d -t new-project-manual-gate-XXXXXX)"
trap 'rm -rf "$TMP_BASE"' EXIT

PASS_COUNT=0
FAIL_COUNT=0
ok()   { echo "  OK: $*"; PASS_COUNT=$((PASS_COUNT+1)); }
fail() { echo "FAIL: $*" >&2; FAIL_COUNT=$((FAIL_COUNT+1)); }

echo "=== Static: --source-root wiring"
if grep -q 'SOURCE_ROOT.*--source-root\|--source-root "\$SOURCE_ROOT"\|_INIT_O3_ARGS+=(--source-root' "$NP"; then
  ok "new-project 含 --source-root 接线"
else
  fail "new-project 缺少 --source-root 接线"
fi

echo "=== Static: 手册块禁止「不影响立项」"
_MANUAL_BLOCK="$(awk '/_TPL_TEMPLATES_DIR=/,/形式闸门 #1/' "$NP")"
if printf '%s\n' "$_MANUAL_BLOCK" | grep -n '不影响立项'; then
  fail "手册生成块仍含「不影响立项」"
else
  ok "手册块无「不影响立项」"
fi

echo "=== Static: 缺手册 exit 1"
if grep -q '缺少 references/manual/abcde-manual.md' "$NP" && grep -q 'exit 1' "$NP"; then
  ok "含缺手册失败退出"
else
  fail "缺少缺手册 exit 1 逻辑"
fi

echo "=== Behavior: assert missing manual writes marker"
DEST="$TMP_BASE/dest"
mkdir -p "$DEST/references/manual" "$DEST/.auto-nn"
# 镜像 new-project 块末断言
set +e
(
  set -euo pipefail
  if [[ ! -f "$DEST/references/manual/abcde-manual.md" ]]; then
    mkdir -p "$DEST/.auto-nn"
    [[ -f "$DEST/.auto-nn/manual-generate-failed" ]] || \
      echo "abcde-manual.md missing after init block" > "$DEST/.auto-nn/manual-generate-failed"
    exit 1
  fi
)
_rc=$?
set -e
if [[ $_rc -ne 0 ]] && [[ -f "$DEST/.auto-nn/manual-generate-failed" ]]; then
  ok "缺手册 → 非零 + 失败标记"
else
  fail "行为断言失败 rc=$_rc marker=$(ls -la "$DEST/.auto-nn" 2>/dev/null || true)"
fi

echo "=== 汇总: PASS=$PASS_COUNT FAIL=$FAIL_COUNT"
if [[ $FAIL_COUNT -eq 0 ]]; then echo "ALL PASS"; exit 0; else echo "FAIL"; exit 1; fi
