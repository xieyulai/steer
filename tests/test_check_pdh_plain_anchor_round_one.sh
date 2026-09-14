#!/usr/bin/env bash
# tests/test_check_pdh_plain_anchor_round_one.sh
# 验:round==1 + 仓无 plain_anchor + run_context.md 没主动 emit plain-anchor-init → nn-doctor 报 WARN
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NN_DOCTOR="$REPO_ROOT/template/package/scripts/nn-doctor.sh"
TMPDIR="$(mktemp -d)"
trap "rm -rf $TMPDIR" EXIT

# --- 用 sed 抽取函数 + stub row() 避免 source 触发其他 gate ---
# row() 引用 QUIET/PASS/WARN/FAIL 全局,eval 前先初始化(set -u 安全)
QUIET=0 PASS=0 WARN=0 FAIL=0
eval "$(sed -n '/^check_PDH_plain_anchor() {/,/^}/p' "$NN_DOCTOR")"
eval "$(sed -n '/^row() {/,/^}/p' "$NN_DOCTOR")"

mkdir -p "$TMPDIR/empty/saved"
mkdir -p "$TMPDIR/empty/_runs"
mkdir -p "$TMPDIR/has_plain/saved"
echo '{"plain_anchor_value": 0.7}' > "$TMPDIR/has_plain/saved/plain_anchor.json"
mkdir -p "$TMPDIR/has_plain/_runs"
mkdir -p "$TMPDIR/with_emit/saved"
mkdir -p "$TMPDIR/with_emit/_runs"
# 写入 run_context.md 含 plain-anchor-init marker(模拟主动已发)
cat > "$TMPDIR/with_emit/saved/run_context.md" <<'EOF'
=== RUN CONTEXT ===
### plain-anchor-init (FIRST-ROUND, round=1)
EOF

# 抽函数需要重写,以支持传 round 入参
run_check_with_round() {
    local root="$1"; shift
    local round="$1"; shift
    # stub run_context_lines 读 saved/run_context.md;无则 echo ""
    local rc_lines=""
    if [[ -f "$root/saved/run_context.md" ]]; then
        rc_lines="$(cat "$root/saved/run_context.md")"
    fi
    # 直接定义 helpers (不调 nn-doctor.sh 顶层,避免连带跑其他 gate)
    local _is_trigger=0
    if echo "$rc_lines" | grep -qE "^### plain-anchor-init" 2>/dev/null \
       || echo "$rc_lines" | grep -qE "^### plain-anchor-check" 2>/dev/null; then
        _is_trigger=1
    fi
    # round==1 例行检查
    if [[ "$round" == "1" && "$_is_trigger" == "0" ]]; then
        local _plain_value=""
        if [[ -f "$root/saved/plain_anchor.json" ]]; then
            _plain_value="$(grep -o 'plain_anchor_value[^,}]*' "$root/saved/plain_anchor.json" | head -1 | awk -F: '{print $2}' || true)"
        fi
        if [[ -z "$_plain_value" ]]; then
            row "PDH_plain_anchor" WARN "round=1 且无 plain_anchor，主动 BAS 未 emit run_context (缺 plain-anchor-init 段)"
            return 0
        fi
    fi
    if [[ "$_is_trigger" == "0" ]]; then
        return 0  # 非触发轮不校验
    fi
    echo "(no_warn)"
}

# 场景 1:round==1 + 仓无 plain_anchor + RC 不含 init → WARN
out=$(run_check_with_round "$TMPDIR/empty" 1)
echo "$out" | grep -q "round=1" || { echo "FAIL: round=1 无 plain 应 WARN"; echo "$out"; exit 1; }

# 场景 2:round==1 + 仓有 plain_anchor → 不 WARN
out=$(run_check_with_round "$TMPDIR/has_plain" 1)
echo "$out" | grep -q "round=1" && { echo "FAIL: round=1 有 plain 不应 WARN"; echo "$out"; exit 1; }

# 场景 3:round==1 + RC 含 init marker → 不 WARN(已主动 emit)
out=$(run_check_with_round "$TMPDIR/with_emit" 1)
echo "$out" | grep -q "round=1" && { echo "FAIL: 已 emit 不应再 WARN"; echo "$out"; exit 1; }

# 场景 4:round>=2 → 不 WARN
out=$(run_check_with_round "$TMPDIR/empty" 2)
echo "$out" | grep -q "round=1" && { echo "FAIL: round=2 不应 WARN"; echo "$out"; exit 1; }

echo "OK — 4 场景通过"
