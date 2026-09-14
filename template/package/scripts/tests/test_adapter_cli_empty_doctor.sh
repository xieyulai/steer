#!/usr/bin/env bash
# test_adapter_cli_empty_doctor.sh — Task 4: check_adapter_cli_empty()
#
# 场景 A: 非 adapter 形态 → 无输出（SKIP/静默）
# 场景 B: adapter + is-not-None 透传 → FAIL
# 场景 C: adapter + append_cfg_cli → PASS
# 场景 D: adapter 无 workspace/build_command → 无输出
#
# 跑法: bash template/package/scripts/tests/test_adapter_cli_empty_doctor.sh

set -euo pipefail

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCTOR="$SCRIPTS/nn-doctor.sh"
TMP_BASE="$(mktemp -d -t adapter-cli-empty-doctor-XXXXXX)"
trap 'rm -rf "$TMP_BASE"' EXIT

PASS_COUNT=0
FAIL_COUNT=0
ok()   { echo "  OK: $*"; PASS_COUNT=$((PASS_COUNT+1)); }
fail() { echo "FAIL: $*" >&2; FAIL_COUNT=$((FAIL_COUNT+1)); }

extract_fn() {
  local body
  body="$(awk '/^check_adapter_cli_empty\(\) \{/{f=1} f{print} f&&/^\}/{exit}' "$DOCTOR")"
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
  cat > "$repo/nn-config.yaml" <<EOF
profile: default
workspace:
  metrics_shape: ${metrics_shape}
ledger:
  watchlist:
    - LR
EOF
}

write_workspace_bad() {
  local repo="$1"
  mkdir -p "$repo/workspace"
  cat > "$repo/workspace/__init__.py" <<'PY'
CFG_TO_CLI = {"ALPHA": "alpha", "LR": "lr"}

def build_command(cfg, exp_dir):
    cmd = ["python", "main.py"]
    for cfg_key, cli_key in CFG_TO_CLI.items():
        if cfg_key in cfg and cfg[cfg_key] is not None:
            cmd.extend([f"--{cli_key}", str(cfg[cfg_key])])
    return cmd
PY
}

write_workspace_good() {
  local repo="$1"
  mkdir -p "$repo/workspace"
  cat > "$repo/workspace/__init__.py" <<'PY'
from lib.adapter_accept import append_cfg_cli

CFG_TO_CLI = {"ALPHA": "alpha", "LR": "lr"}

def build_command(cfg, exp_dir):
    cmd = ["python", "main.py"]
    append_cfg_cli(cmd, cfg, CFG_TO_CLI)
    return cmd
PY
}

run_check() {
  local fixture="$1"
  ROWS="$(mktemp -p "$TMP_BASE")"
  (
    cd "$fixture"
    SCRIPT_DIR="$SCRIPTS"
    eval "$FN_BODY"
    check_adapter_cli_empty
  ) > /dev/null 2>&1 || true
}

if ! FN_BODY="$(extract_fn)"; then
  echo "FAIL: check_adapter_cli_empty 未在 nn-doctor.sh 实现" >&2
  exit 1
fi

# ── Scenario A: 非 adapter → 无输出 ──
echo "=== Scenario A: 非 adapter 形态"
REPO_A="$TMP_BASE/a"
mkdir -p "$REPO_A"
write_nn_config "$REPO_A" "EVALUATE_LEARNER"
run_check "$REPO_A"
if [[ ! -s "$ROWS" ]]; then ok "非 adapter 无输出"; else fail "A 不应有输出: $(cat "$ROWS")"; fi

# ── Scenario B: adapter + 坏透传 → FAIL ──
echo "=== Scenario B: adapter 空串透传"
REPO_B="$TMP_BASE/b"
mkdir -p "$REPO_B"
write_nn_config "$REPO_B" "EVALUATE_RUNNER"
write_workspace_bad "$REPO_B"
run_check "$REPO_B"
if grep -q '^FAIL|' "$ROWS"; then ok "adapter 坏透传 → FAIL"; else fail "B 应 FAIL: $(cat "$ROWS")"; fi

# ── Scenario C: adapter + append_cfg_cli → PASS ──
echo "=== Scenario C: adapter 空串已省略"
REPO_C="$TMP_BASE/c"
mkdir -p "$REPO_C"
write_nn_config "$REPO_C" "adapter"
write_workspace_good "$REPO_C"
run_check "$REPO_C"
if grep -q '^PASS|' "$ROWS"; then ok "adapter 好实现 → PASS"; else fail "C 应 PASS: $(cat "$ROWS")"; fi
if grep -q '^FAIL|' "$ROWS"; then fail "C 不应 FAIL: $(cat "$ROWS")"; else ok "C 无 FAIL"; fi

# ── Scenario D: adapter 无 workspace → 无输出 ──
echo "=== Scenario D: adapter 无 workspace"
REPO_D="$TMP_BASE/d"
mkdir -p "$REPO_D"
write_nn_config "$REPO_D" "EVALUATE_RUNNER"
run_check "$REPO_D"
if [[ ! -s "$ROWS" ]]; then ok "无 workspace 无输出"; else fail "D 不应有输出: $(cat "$ROWS")"; fi

echo "=== 汇总: PASS=$PASS_COUNT FAIL=$FAIL_COUNT"
if [[ $FAIL_COUNT -eq 0 ]]; then echo "ALL PASS"; exit 0; else echo "FAIL"; exit 1; fi
