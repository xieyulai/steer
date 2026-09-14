#!/usr/bin/env bash
# test_skeleton_queue_health.sh — 3 场景 bash 测试
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/../check_skeleton_queue_health.sh"

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*" >&2; exit 0; }

# 场景 A: 队列空 → exit 0
TMP_A=$(mktemp -d)
mkdir -p "$TMP_A/saved"
echo '{"v":1,"items":[]}' > "$TMP_A/saved/skeleton_queue.json"
if ! NN_SAVED_DIR="$TMP_A/saved" bash "$SCRIPT" >/dev/null 2>&1; then
  fail "场景 A 应 PASS (空队列)"
fi
rm -rf "$TMP_A"
echo "PASS: 场景 A (空队列 → exit 0)"

# 场景 B: 有 overdue → exit 1
TMP_B=$(mktemp -d)
mkdir -p "$TMP_B/saved"
cat > "$TMP_B/saved/skeleton_queue.json" <<'EOF'
{"v":1,"items":[{"id":"R5-Poly","status":"pending_fill","round":5,"deadline_round":6,"registry":"learner","registry_name":"Poly","class_name":"Poly","paper_ref":"arxiv:x"}]}
EOF
if NN_SAVED_DIR="$TMP_B/saved" NN_CURRENT_ROUND=7 bash "$SCRIPT" >/dev/null 2>&1; then
  fail "场景 B 应 FAIL (overdue)"
fi
rm -rf "$TMP_B"
echo "PASS: 场景 B (overdue → exit 1)"

# 场景 C: GRACE_ROUNDS=1 + 差 1 轮 → exit 0 (grace)
TMP_C=$(mktemp -d)
mkdir -p "$TMP_C/saved"
cat > "$TMP_C/saved/skeleton_queue.json" <<'EOF'
{"v":1,"items":[{"id":"R5-Poly","status":"pending_fill","round":5,"deadline_round":7,"registry":"learner","registry_name":"Poly","class_name":"Poly","paper_ref":"arxiv:x"}]}
EOF
if ! NN_SAVED_DIR="$TMP_C/saved" NN_CURRENT_ROUND=7 NN_SKELETON_QUEUE_GRACE_ROUNDS=1 bash "$SCRIPT" >/dev/null 2>&1; then
  fail "场景 C 应 PASS (grace)"
fi
rm -rf "$TMP_C"
echo "PASS: 场景 C (grace → exit 0)"

echo "ALL PASS: 3/3 scenarios"