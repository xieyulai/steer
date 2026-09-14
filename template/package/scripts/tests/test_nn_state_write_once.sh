#!/usr/bin/env bash
# test_nn_state_write_once.sh — write-once + sync 首戳门禁语义
set -euo pipefail

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../lib/nn-state.sh
source "$SCRIPTS/lib/nn-state.sh"

TMP="$(mktemp -d -t nn-state-write-once-XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

PASS=0
FAIL=0
ok() { echo "  OK: $*"; PASS=$((PASS + 1)); }
fail() { echo "FAIL: $*" >&2; FAIL=$((FAIL + 1)); }

# --- write_once 二次不覆盖 ---
nn_state_write_once init-template-version "1.0.0+aaa" "$TMP"
nn_state_write_once init-template-version "9.9.9+bbb" "$TMP"
got="$(nn_state_read init-template-version "$TMP")"
if [[ "$got" == "1.0.0+aaa" ]]; then
  ok "write_once 二次不覆盖"
else
  fail "write_once 被覆盖: got=$got"
fi

# --- 空文件可写 ---
: > "$TMP/.auto-nn/empty-key"
nn_state_write_once empty-key "filled" "$TMP"
got="$(nn_state_read empty-key "$TMP")"
if [[ "$got" == "filled" ]]; then
  ok "空文件可 write_once"
else
  fail "空文件未写入: got=$got"
fi

# --- sync 门禁语义：有 version 无 init → 不回填 ---
REPO_A="$TMP/repo-upgraded"
mkdir -p "$REPO_A/.auto-nn"
printf '%s\n' "1.48.9+old" > "$REPO_A/.auto-nn/version"
_had_ver=0; _had_init=0
[[ -s "$(nn_state_path version "$REPO_A")" ]] && _had_ver=1
[[ -s "$(nn_state_path init-template-version "$REPO_A")" ]] && _had_init=1
_STAMP="1.48.12+new"
nn_state_write version "$_STAMP" "$REPO_A"
if [[ $_had_init -eq 0 && $_had_ver -eq 0 ]]; then
  nn_state_write_once init-template-version "$_STAMP" "$REPO_A"
fi
if [[ ! -s "$REPO_A/.auto-nn/init-template-version" ]] \
  && [[ "$(nn_state_read version "$REPO_A")" == "$_STAMP" ]]; then
  ok "已有 version 缺 init → 不回填 init"
else
  fail "旧仓被误回填 init=$(nn_state_read init-template-version "$REPO_A")"
fi

# --- 皆无 → 写出 init ---
REPO_B="$TMP/repo-fresh"
mkdir -p "$REPO_B"
_had_ver=0; _had_init=0
[[ -s "$(nn_state_path version "$REPO_B")" ]] && _had_ver=1
[[ -s "$(nn_state_path init-template-version "$REPO_B")" ]] && _had_init=1
_STAMP2="1.48.12+fresh"
nn_state_write version "$_STAMP2" "$REPO_B"
if [[ $_had_init -eq 0 && $_had_ver -eq 0 ]]; then
  nn_state_write_once init-template-version "$_STAMP2" "$REPO_B"
fi
if [[ "$(nn_state_read init-template-version "$REPO_B")" == "$_STAMP2" ]]; then
  ok "皆无 → 首 sync 锁定 init"
else
  fail "首 sync 未写 init"
fi

# --- 再 sync 改 version、init 不变 ---
_had_ver=0; _had_init=0
[[ -s "$(nn_state_path version "$REPO_B")" ]] && _had_ver=1
[[ -s "$(nn_state_path init-template-version "$REPO_B")" ]] && _had_init=1
_STAMP3="1.99.0+later"
nn_state_write version "$_STAMP3" "$REPO_B"
if [[ $_had_init -eq 0 && $_had_ver -eq 0 ]]; then
  nn_state_write_once init-template-version "$_STAMP3" "$REPO_B"
fi
if [[ "$(nn_state_read version "$REPO_B")" == "$_STAMP3" ]] \
  && [[ "$(nn_state_read init-template-version "$REPO_B")" == "$_STAMP2" ]]; then
  ok "再 sync：version 变、init 不变"
else
  fail "再 sync 破坏 init 或未改 version"
fi

echo "---"
echo "PASS=$PASS FAIL=$FAIL"
[[ "$FAIL" -eq 0 ]]
