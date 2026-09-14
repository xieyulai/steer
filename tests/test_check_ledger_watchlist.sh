#!/usr/bin/env bash
# tests/test_check_ledger_watchlist.sh — 跑 5 个 inline bash 场景
#
# 5 场景全部走 check_ledger_watchlist() inline 函数（仿 check_PDH_plain_anchor 模式）。
#
# 测试策略：从 nn-doctor.sh 用 sed 抽出 check_ledger_watchlist 函数定义 + stub
# row()，写到临时脚本，再 source 后调函数。理由：
#   - 直接 source nn-doctor.sh 会触发顶层所有 gate 输出大量无关噪音
#   - 顶层 gate 出 FAIL 时 set -e 可能让 source 提前退出
#   - 抽出函数后跑测试快且纯净
#
# 退出码 (仅函数返回):
#   0 = PASS 或 WARN
#   1 = FAIL — watchlist 不合规
#   2 = 解析失败 / 异常
#
# Bash 断言: 我们关注 stdout 里 "ledger_watchlist<TAB>STATUS" 的 status 字段。

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NN_DOCTOR="$REPO_ROOT/template/package/scripts/nn-doctor.sh"
TMPDIR="$(mktemp -d)"
trap "rm -rf $TMPDIR" EXIT

if [[ ! -f "$NN_DOCTOR" ]]; then
  echo "SKIP: nn-doctor.sh 不存在：$NN_DOCTOR"
  exit 0
fi

# Extract function + stubs to a standalone test runner.
TESTRUNNER="$(mktemp "$TMPDIR/runner-XXXXXX.sh")"
{
  echo '#!/usr/bin/env bash'
  echo 'set -uo pipefail'
  echo 'row() { printf "%s\t%s\t%s\n" "$1" "$2" "$3"; }'
  echo 'QUIET=0'
  sed -n '/^check_ledger_watchlist() {$/,/^}$/p' "$NN_DOCTOR"
} > "$TESTRUNNER"
# shellcheck disable=SC1090
source "$TESTRUNNER"

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

# ── 场景 1: 无 nn-config.yaml → WARN (no params tracked) ──
mkdir -p "$TMPDIR/no_cfg"
out=$(check_ledger_watchlist "$TMPDIR/no_cfg" 2>&1)
echo "场景1(no_cfg): $out"
echo "$out" | grep -q $'ledger_watchlist\tWARN' \
  || fail "场景1: no_cfg 应 WARN（行: $out）"

# ── 场景 2: 有 ledger.watchlist 但有 dup → FAIL ──
mkdir -p "$TMPDIR/dup"
cat > "$TMPDIR/dup/nn-config.yaml" <<'YAML'
ledger:
  watchlist:
    - LR
    - LR
YAML
set +e
out=$(check_ledger_watchlist "$TMPDIR/dup" 2>&1)
rc=$?
set -e
echo "场景2(dup): rc=$rc $out"
echo "$out" | grep -q $'ledger_watchlist\tFAIL' \
  || fail "场景2: dup 应 FAIL（行: $out）"

# ── 场景 3: watchlist 与 metric_keys 重叠 → FAIL ──
mkdir -p "$TMPDIR/overlap/contract"
cat > "$TMPDIR/overlap/contract/__init__.py" <<'PY'
metric_keys = ("LR",)
auxiliary_keys = ()
PY
cat > "$TMPDIR/overlap/nn-config.yaml" <<'YAML'
ledger:
  watchlist:
    - LR
YAML
set +e
out=$(check_ledger_watchlist "$TMPDIR/overlap" 2>&1)
rc=$?
set -e
echo "场景3(overlap): rc=$rc $out"
echo "$out" | grep -q $'ledger_watchlist\tFAIL' \
  || fail "场景3: overlap 应 FAIL（行: $out）"

# ── 场景 4: 干净 watchlist → PASS ──
mkdir -p "$TMPDIR/clean"
cat > "$TMPDIR/clean/nn-config.yaml" <<'YAML'
ledger:
  watchlist:
    - LR
    - BATCH_SIZE
YAML
out=$(check_ledger_watchlist "$TMPDIR/clean" 2>&1)
echo "场景4(clean): $out"
echo "$out" | grep -q $'ledger_watchlist\tPASS' \
  || fail "场景4: clean 应 PASS（行: $out）"

# ── 场景 5: 无 ledger 段 → WARN ──
mkdir -p "$TMPDIR/no_ledger"
cat > "$TMPDIR/no_ledger/nn-config.yaml" <<'YAML'
profile: supervised
YAML
out=$(check_ledger_watchlist "$TMPDIR/no_ledger" 2>&1)
echo "场景5(no_ledger): $out"
echo "$out" | grep -q $'ledger_watchlist\tWARN' \
  || fail "场景5: no_ledger 应 WARN（行: $out）"

echo "OK — 5 场景通过"
