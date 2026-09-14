#!/usr/bin/env bash
# check_skeleton_queue_health.sh — A2 release-check 第 6 步 lint
#
# 扫 saved/skeleton_queue.json，存在 status=pending_fill 且
# current_round - deadline_round > grace → exit 1
#
# 用法: bash scripts/check_skeleton_queue_health.sh
#       (NN_SAVED_DIR / NN_CURRENT_ROUND / NN_SKELETON_QUEUE_GRACE_ROUNDS 可调)
set -euo pipefail

SAVED_DIR="${NN_SAVED_DIR:-saved}"
CURRENT_ROUND="${NN_CURRENT_ROUND:-0}"
GRACE="${NN_SKELETON_QUEUE_GRACE_ROUNDS:-0}"

QUEUE_FILE="$SAVED_DIR/skeleton_queue.json"

if [[ ! -f "$QUEUE_FILE" ]]; then
  echo "[skeleton-queue] SKIP: $QUEUE_FILE 缺失 (A2 未启用)" >&2
  exit 0
fi

OVERDUE=$(CURRENT_ROUND="$CURRENT_ROUND" GRACE="$GRACE" python3 - "$QUEUE_FILE" <<'PY'
import json
import os
import sys

queue_file = sys.argv[1]
with open(queue_file) as f:
    q = json.load(f)

current = int(os.environ.get("CURRENT_ROUND", "0"))
grace = int(os.environ.get("GRACE", "1"))

pending = [x for x in q.get("items", []) if x.get("status") == "pending_fill"]
overdue = [
    f"{x.get('class_name')} (R{x.get('round')}, deadline R{x.get('deadline_round')}, paper_ref={x.get('paper_ref')})"
    for x in pending
    if current - x.get("deadline_round", 0) > grace
]
for line in overdue:
    print(line)
PY
)

if [[ -n "$OVERDUE" ]]; then
  echo "[skeleton-queue] FAIL: 骨架队列有 overdue items (>${GRACE} 轮未填):" >&2
  echo "$OVERDUE" >&2
  echo "[skeleton-queue] HINT: 设 NN_SKELETON_QUEUE_GRACE_ROUNDS=<更大> 临时绕过,或真填骨架 / 标 abandoned" >&2
  exit 1
fi

echo "[skeleton-queue] PASS: 无 overdue 骨架 (pending 队列 OK, grace=$GRACE)" >&2
exit 0