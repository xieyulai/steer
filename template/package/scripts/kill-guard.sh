#!/usr/bin/env bash
# kill-guard.sh — PreToolUse hook: 拦截 kill/pkill/killall，校验 PID 归属
set -euo pipefail

# 从 stdin 读 hook JSON
INPUT=$(cat)
COMMAND=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null || true)

# 无命令 → 放行
[[ -n "$COMMAND" ]] || exit 0

# 不含 kill 关键词 → 放行
if ! echo "$COMMAND" | grep -qiE '\b(kill|pkill|killall)\b'; then
    exit 0
fi

# 白名单：kill -l / kill 无参数
if echo "$COMMAND" | grep -qiE '^\s*kill\s+(-l|--list)\s*$'; then
    exit 0
fi
if echo "$COMMAND" | grep -qiE '^\s*kill\s*$'; then
    exit 0
fi

# 禁止 pkill / killall
if echo "$COMMAND" | grep -qiE '\bpkill\b'; then
    echo "BLOCKED: 禁止模糊匹配 pkill，请用 kill <具体PID>" >&2
    exit 2
fi
if echo "$COMMAND" | grep -qiE '\bkillall\b'; then
    echo "BLOCKED: 禁止模糊匹配 killall，请用 kill <具体PID>" >&2
    exit 2
fi

# 解析 kill 后面的 PID（处理 kill -9 PID 格式）
TARGET_PIDS=()
for arg in $COMMAND; do
    if [[ "$arg" =~ ^[0-9]+$ ]] && [[ "$arg" -gt 0 ]]; then
        TARGET_PIDS+=("$arg")
    fi
done

[[ ${#TARGET_PIDS[@]} -gt 0 ]] || exit 0

# 检查是否有 saved/.train_pid
PID_FILE="saved/.train_pid"
[[ -f "$PID_FILE" ]] || exit 0

# 读取本仓主 PID
MAIN_PID=$(python3 -c "import json; print(json.load(open('$PID_FILE')).get('pid',0))" 2>/dev/null || echo 0)
[[ "$MAIN_PID" -gt 0 ]] || exit 0

# 收集本仓所有相关 PID（主进程 + 子进程）
OWN_PIDS=("$MAIN_PID")
while IFS= read -r child; do
    [[ -n "$child" ]] && OWN_PIDS+=("$child")
done < <(pgrep -P "$MAIN_PID" 2>/dev/null || true)

for TPID in "${TARGET_PIDS[@]}"; do
    IS_OWN=false
    for OPID in "${OWN_PIDS[@]}"; do
        if [[ "$TPID" -eq "$OPID" ]]; then
            IS_OWN=true
            break
        fi
    done
    if $IS_OWN; then
        echo "BLOCKED: 即将终止本仓训练进程 PID=$TPID，如需执行请确认后重试" >&2
        exit 2
    else
        echo "BLOCKED: PID $TPID 不属于本仓，禁止终止" >&2
        exit 2
    fi
done

exit 0
