#!/usr/bin/env bash
# test_manual_run_scope_check.sh — 6 场景 TDD for manual-run-scope-check.sh
#
# 场景 A: 临时 git 仓 + 空 diff → PASS + exit 0
# 场景 B: 临时 git 仓 + 仅 _runs/configs/exp.json 改 → PASS + exit 0
# 场景 C: 临时 git 仓 + 改 contract/__init__.py → FAIL(含 IMMUTABLE) + exit 2
# 场景 D: 非 git 目录 → SKIP + exit 0
# 场景 E: 临时 git 仓 + 仅改 workspace/ → WARN(含 workspace-edit) + exit 1
# 场景 F: NN_RELAUNCH=1 + 脏 contract/ → exit 0 且非 FAIL:
#
# 跑法: bash template/package/scripts/tests/test_manual_run_scope_check.sh

set -euo pipefail

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_SH="$SCRIPTS/manual-run-scope-check.sh"
TMP_BASE="$(mktemp -d -t manual-run-scope-XXXXXX)"
trap 'rm -rf "$TMP_BASE"' EXIT

PASS_COUNT=0
FAIL_COUNT=0

fail() {
  echo "FAIL: $*" >&2
  FAIL_COUNT=$((FAIL_COUNT + 1))
}

ok() {
  echo "  OK: $*"
  PASS_COUNT=$((PASS_COUNT + 1))
}

# ── 辅助: bootstrap 一个有 1 commit 的 git 仓 ──
make_repo() {
  local d="$1"
  mkdir -p "$d"
  (
    cd "$d"
    git init -q
    git -c user.email=test@test.com -c user.name=test commit --allow-empty -q -m init
  )
}

# ── 辅助: 跑被测脚本并捕获 stdout + rc ──
run_check() {
  local repo="$1"
  local out_var="$2"
  local rc_var="$3"
  shift 3
  set +e
  out="$(env "$@" "$TARGET_SH" --repo-root "$repo" 2>&1)"
  rc=$?
  set -e
  printf -v "$out_var" '%s' "$out"
  printf -v "$rc_var" '%d' "$rc"
}

# ── 前置检查: 脚本存在 ──
if [[ ! -f "$TARGET_SH" ]]; then
  echo "=== T-MRSC: setup"
  echo "FAIL: 目标脚本不存在: $TARGET_SH — 先写 manual-run-scope-check.sh"
  exit 1
fi

# ── Scenario A: 空 diff → PASS + exit 0 ──
echo "=== Scenario A: 空 git 仓,无改动"
REPO_A="$TMP_BASE/scenarioA"
make_repo "$REPO_A"
run_check "$REPO_A" out_a rc_a
if [[ $rc_a -eq 0 ]]; then
  ok "exit=0 (want 0)"
else
  fail "Scenario A exit=$rc_a want 0; out=$out_a"
fi
if [[ "$out_a" == "PASS: 无 Modify Track 范围改动" ]]; then
  ok "stdout=PASS:"
else
  fail "Scenario A stdout 错: got=$out_a"
fi

# ── Scenario B: 仅 config 改 → PASS + exit 0 ──
echo "=== Scenario B: 仅 _runs/configs/exp.json 改"
REPO_B="$TMP_BASE/scenarioB"
make_repo "$REPO_B"
mkdir -p "$REPO_B/_runs/configs"
echo '{"LR":0.001}' > "$REPO_B/_runs/configs/exp.json"
(
  cd "$REPO_B"
  git add _runs/configs/exp.json
  git -c user.email=test@test.com -c user.name=test commit -q -m "init config"
)
echo '{"LR":0.002}' > "$REPO_B/_runs/configs/exp.json"
run_check "$REPO_B" out_b rc_b
if [[ $rc_b -eq 0 ]]; then
  ok "exit=0 (want 0)"
else
  fail "Scenario B exit=$rc_b want 0; out=$out_b"
fi
if [[ "$out_b" == "PASS: 无 Modify Track 范围改动" ]]; then
  ok "stdout=PASS:"
else
  fail "Scenario B stdout 错: got=$out_b"
fi

# ── Scenario C: contract 改 → FAIL + IMMUTABLE + exit 2 ──
echo "=== Scenario C: 改 contract/__init__.py"
REPO_C="$TMP_BASE/scenarioC"
make_repo "$REPO_C"
mkdir -p "$REPO_C/contract"
echo "# empty" > "$REPO_C/contract/__init__.py"
(
  cd "$REPO_C"
  git add contract/__init__.py
  git -c user.email=test@test.com -c user.name=test commit -q -m "init contract"
)
echo "# changed" > "$REPO_C/contract/__init__.py"
run_check "$REPO_C" out_c rc_c
if [[ $rc_c -eq 2 ]]; then
  ok "exit=2 (want 2)"
else
  fail "Scenario C exit=$rc_c want 2; out=$out_c"
fi
if [[ "$out_c" == FAIL:* ]]; then
  ok "stdout starts with FAIL:"
else
  fail "Scenario C stdout 不是 FAIL: got=$out_c"
fi
if [[ "$out_c" == *"IMMUTABLE"* ]]; then
  ok "stdout 含 IMMUTABLE"
else
  fail "Scenario C stdout 缺 IMMUTABLE: got=$out_c"
fi
if [[ "$out_c" == *"workspace-edit"* ]]; then
  fail "Scenario C stdout 不应含 workspace-edit: got=$out_c"
else
  ok "stdout 不含 workspace-edit"
fi

# ── Scenario D: 非 git → SKIP + exit 0 ──
echo "=== Scenario D: 非 git 目录"
REPO_D="$TMP_BASE/scenarioD"
mkdir -p "$REPO_D"   # 故意不 git init
run_check "$REPO_D" out_d rc_d
if [[ $rc_d -eq 0 ]]; then
  ok "exit=0 (want 0)"
else
  fail "Scenario D exit=$rc_d want 0; out=$out_d"
fi
if [[ "$out_d" == "SKIP: 非 git 仓或 git diff 不可用" ]]; then
  ok "stdout=SKIP:"
else
  fail "Scenario D stdout 错: got=$out_d"
fi

# ── Scenario E: 仅 workspace 改 → WARN + workspace-edit + exit 1 ──
echo "=== Scenario E: 仅改 workspace/__init__.py"
REPO_E="$TMP_BASE/scenarioE"
make_repo "$REPO_E"
mkdir -p "$REPO_E/workspace"
echo "# empty" > "$REPO_E/workspace/__init__.py"
(
  cd "$REPO_E"
  git add workspace/__init__.py
  git -c user.email=test@test.com -c user.name=test commit -q -m "init workspace"
)
echo "# changed" > "$REPO_E/workspace/__init__.py"
run_check "$REPO_E" out_e rc_e
if [[ $rc_e -eq 1 ]]; then
  ok "exit=1 (want 1)"
else
  fail "Scenario E exit=$rc_e want 1; out=$out_e"
fi
if [[ "$out_e" == WARN:* ]]; then
  ok "stdout starts with WARN:"
else
  fail "Scenario E stdout 不是 WARN: got=$out_e"
fi
if [[ "$out_e" == *"workspace-edit"* ]]; then
  ok "stdout 含 workspace-edit"
else
  fail "Scenario E stdout 缺 workspace-edit: got=$out_e"
fi

# ── Scenario F: NN_RELAUNCH=1 + 脏 contract → exit 0 且非 FAIL ──
echo "=== Scenario F: NN_RELAUNCH=1 + 改 contract/__init__.py"
REPO_F="$TMP_BASE/scenarioF"
make_repo "$REPO_F"
mkdir -p "$REPO_F/contract"
echo "# empty" > "$REPO_F/contract/__init__.py"
(
  cd "$REPO_F"
  git add contract/__init__.py
  git -c user.email=test@test.com -c user.name=test commit -q -m "init contract"
)
echo "# changed" > "$REPO_F/contract/__init__.py"
run_check "$REPO_F" out_f rc_f NN_RELAUNCH=1
if [[ $rc_f -eq 0 ]]; then
  ok "exit=0 (want 0)"
else
  fail "Scenario F exit=$rc_f want 0; out=$out_f"
fi
if [[ "$out_f" == FAIL:* ]]; then
  fail "Scenario F stdout 不应是 FAIL: got=$out_f"
else
  ok "stdout 非 FAIL:"
fi

# ── 汇总 ──
echo "=== T-MRSC 汇总: PASS=${PASS_COUNT} FAIL=${FAIL_COUNT}"
if [[ $FAIL_COUNT -gt 0 ]]; then
  echo "FAIL"
  exit 1
fi
echo "ALL PASS"
exit 0