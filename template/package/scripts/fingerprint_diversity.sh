#!/usr/bin/env bash
# fingerprint_diversity.sh — 扫最近 N 轮 reflect log 算 fingerprint 重复率
# 用法：bash scripts/fingerprint_diversity.sh [N]    # 默认 10
#
# 输出三段：
#   1. 最近 N 轮 fingerprint 单行（按时间倒序）
#   2. primary_key 重复率 Top 5（MODEL_ARCH/LOSS/OPTIMIZER/SCHEDULER/MIXUP_ALPHA → 模式）
#   3. Tier 分布
#
# 不写盘、不发请求、纯只读 grep。
set -euo pipefail

N="${1:-10}"

# 定位业务仓根（含 _runs/agent/ 的目录）
# 优先级：环境变量 AUTO_NN_REPO_ROOT > 父目录含 _runs/agent > cwd
if [[ -n "${AUTO_NN_REPO_ROOT:-}" ]] && [[ -d "${AUTO_NN_REPO_ROOT}/_runs/agent" ]]; then
  REPO_ROOT="$AUTO_NN_REPO_ROOT"
elif [[ -d "./_runs/agent" ]]; then
  REPO_ROOT="$(pwd)"
elif [[ -d "../_runs/agent" ]]; then
  REPO_ROOT="$(cd .. && pwd)"
else
  echo "[fingerprint_diversity] 错误: 找不到 _runs/agent 目录" >&2
  echo "  设置 AUTO_NN_REPO_ROOT 或在业务仓根目录跑" >&2
  exit 1
fi

echo "=== 最近 $N 轮 fingerprint（$REPO_ROOT） ==="
ls -t "$REPO_ROOT/_runs/agent/"*_reflect-*.log 2>/dev/null | head -"$N" | while read -r f; do
  bn=$(basename "$f" .log | sed 's/^.*_reflect-//')
  fp=$(grep -oP 'Fingerprint: \[[^]]+\]' "$f" 2>/dev/null | head -1)
  if [[ -z "$fp" ]]; then
    fp="(no fingerprint in log)"
  fi
  printf "  R%-3s  %s\n" "$bn" "$fp"
done

echo
echo "=== primary_key 重复率（Top 5） ==="
ls -t "$REPO_ROOT/_runs/agent/"*_reflect-*.log 2>/dev/null | head -"$N" | while read -r f; do
  grep -oP '(MODEL_ARCH|LOSS|OPTIMIZER|SCHEDULER|MIXUP_ALPHA|EPOCHS|LR|BATCH_SIZE|WD|LS|WARMUP)\s+\S+→\S+' "$f" 2>/dev/null | head -1
done | sort | uniq -c | sort -rn | head -5

echo
echo "=== Tier 分布（仅 Fingerprint 行；避免抓 TAM / not_tried / 台账最优） ==="
ls -t "$REPO_ROOT/_runs/agent/"*_reflect-*.log 2>/dev/null | head -"$N" | while read -r f; do
  grep -oP 'Fingerprint: Tier [A-E]' "$f" 2>/dev/null | head -1 | grep -oP 'Tier [A-E]'
done | sort | uniq -c | sort -rn

echo
echo "=== wall_crash 与 plateau 触发 ==="
ls -t "$REPO_ROOT/_runs/agent/"*_reflect-*.log 2>/dev/null | head -"$N" | while read -r f; do
  bn=$(basename "$f" .log | sed 's/^.*_reflect-//')
  wc=$(grep -oP 'Phase 1: wall_crash=\K\S+' "$f" 2>/dev/null | head -1)
  pl=$(grep -oP 'plateau_active=\K\S+' "$f" 2>/dev/null | head -1)
  printf "  R%-3s  wall_crash=%s  plateau_active=%s\n" "$bn" "${wc:-?}" "${pl:-?}"
done
