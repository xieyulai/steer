#!/usr/bin/env bash
# 仅由仓库根 auto-nn-run.sh 在 main for 循环结束后 source。
# 独立成小文件，避免 Agent 误改主脚本末尾（常见：log → g、孤立 || 等）。
# 依赖父 shell：log()、TOTAL_RUNS、LOG_FILE、BLUE、NC
: "${TOTAL_RUNS:?auto-run-batch-tail: TOTAL_RUNS unset}"
: "${LOG_FILE:?auto-run-batch-tail: LOG_FILE unset}"

echo ""
log "SUCCESS" "Completed ${TOTAL_RUNS} runs"
if [[ -n "${BATCH_REFLECT_ACK_MISSING:-}" || -n "${BATCH_JOURNAL_UNCOMMITTED_WARNS:-}" ]]; then
  log "INFO" "batch_summary: runs=${TOTAL_RUNS} reflect_ack_missing=${BATCH_REFLECT_ACK_MISSING:-0} journal_uncommitted_warns=${BATCH_JOURNAL_UNCOMMITTED_WARNS:-0}"
fi
echo -e "批次日志: ${BLUE}${LOG_FILE}${NC}"
echo ""

unset NN_AUTO_RUN_ACTIVE 2>/dev/null || true
rm -f saved/.auto-run-active.pid 2>/dev/null || true
