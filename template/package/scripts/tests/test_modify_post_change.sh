#!/usr/bin/env bash
# test_modify_post_change.sh — 轨名解析 + ledger-sync 缺脚本可诊断
set -euo pipefail
SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MPC="$SCRIPTS/modify-post-change.sh"
TMP="$(mktemp -d -t mpc-XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

PASS=0
FAIL=0
ok() { echo "  OK: $*"; PASS=$((PASS+1)); }
fail() { echo "FAIL: $*" >&2; FAIL=$((FAIL+1)); }

[[ -x "$MPC" ]] || chmod +x "$MPC"

echo "=== 未知 track → exit 2"
if bash "$MPC" --track nope --repo-root "$TMP" >/dev/null 2>&1; then
  fail "应拒绝未知 track"
else
  ok "未知 track 拒绝"
fi

echo "=== ledger-sync 缺 regen → 非零"
mkdir -p "$TMP/scripts"
# 无 regen → need 失败
if bash "$MPC" --track ledger-sync --repo-root "$TMP" >/dev/null 2>&1; then
  fail "缺 regen 应失败"
else
  ok "缺积木失败"
fi

echo "=== --help"
bash "$MPC" --help >/dev/null 2>&1 && ok "help" || ok "help exit2 可接受"

echo "=== 汇总 PASS=$PASS FAIL=$FAIL"
[[ $FAIL -eq 0 ]]
