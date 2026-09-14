#!/usr/bin/env bash
# smoke-check.sh — CHECKLIST §5 机械验收（按 nn-config profile 分轨）
#
# 用法（在项目根）:
#   bash scripts/smoke-check.sh
#   bash scripts/smoke-check.sh --log _runs/logs/migration_smoke.log   # 仅校验已有日志
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LOG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --log) LOG="${2:-}"; shift 2 ;;
    -h|--help)
      echo "用法: $0 [--log <已有 train 日志>]"
      exit 0
      ;;
    *) echo "未知参数: $1" >&2; exit 1 ;;
  esac
done

die() { echo "[smoke-check] FAIL: $*" >&2; exit 1; }
ok() { echo "[smoke-check] OK: $*"; }

[[ -f nn-config.yaml ]] || die "缺少 nn-config.yaml"
PROFILE="$(python3 -c "import yaml; print(yaml.safe_load(open('nn-config.yaml'))['profile'])")"
[[ -n "$PROFILE" ]] || die "nn-config.yaml 无 profile"

[[ -f _runs/results.tsv ]] || die "缺少 _runs/results.tsv"

[[ -f scripts/check-env.sh ]] && bash scripts/check-env.sh || die "环境未就绪（常见：换机后须 poetry install；见 scripts/check-env.sh）"

if [[ -z "$LOG" ]]; then
  mkdir -p _runs/logs
  LOG="_runs/logs/migration_smoke.log"
  export NN_RELAUNCH=1 NN_SMOKE=1 NN_SKIP_WRITE_KEEPER=1 NN_EXPERIMENT=smoke_check
  export NN_SMOKE_BUDGET="${NN_SMOKE_BUDGET:-120}"
  echo "[smoke-check] profile=$PROFILE smoke 墙钟 ${NN_SMOKE_BUDGET}s（真数据短跑；可经 NN_SMOKE_BUDGET 覆盖；TimeGuard 到点 finalize。NN_TIME_BUDGET 已冻结为 yaml 一致性校验，smoke 不再借用）"
  set +e
  poetry run python train.py 2>&1 | tee "$LOG"
  TRAIN_RC="${PIPESTATUS[0]}"
  set -e
  [[ "$TRAIN_RC" -eq 0 ]] || die "train.py 退出码 $TRAIN_RC（见 $LOG）"
else
  [[ -f "$LOG" ]] || die "日志不存在: $LOG"
  ok "使用已有日志 $LOG"
fi

# 静态守门标记（preflight）仅信息性；硬验收 = train.py exit 0 + round_decision.json
# loss OK 仅 supervised 在 preflight 会做 backward 试跑（rl/physical 不传 learner，见 PROTOCOL §3.0.1）
if [[ "$PROFILE" == "supervised" ]]; then
  if grep -q '静态守门 OK' "$LOG"; then
    grep -qE 'loss OK' "$LOG" || die "supervised：preflight 后无 loss OK"
  fi
fi

if [[ -f _runs/round_decision.json && -s _runs/round_decision.json ]]; then
  :
elif [[ -f _runs/evaluation_result.json && -s _runs/evaluation_result.json ]]; then
  echo "[smoke-check] WARN: 使用旧名 _runs/evaluation_result.json；请重新 train 以生成 round_decision.json" >&2
else
  die "_runs/round_decision.json 不存在或为空（兼容旧名 evaluation_result.json）"
fi

# 实质指标：primary_metric 有限；拒绝 results.json 带 _error 且主分为 0 的失败兜底
python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, 'scripts')
from lib.smoke_metrics_gate import evaluate_smoke_metrics
ok, msg = evaluate_smoke_metrics(Path('.').resolve())
print('[smoke-check]', msg)
sys.exit(0 if ok else 1)
" || die "实质指标闸未过（见上；主分须 finite；禁止 _error+主分0 兜底）"

# framework 接入总表：eval.bound 时台账主分须等于声明的框架原样键（无总表则跳过）
python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, 'scripts')
from lib.framework_binding import check_eval_binding_smoke
check_eval_binding_smoke(Path('.').resolve())
" || die "framework_binding eval 对账失败（台账主分 ≠ 声明的框架原样键；见 contract/framework_binding.yaml）"

ok "profile=$PROFILE 通用墙钟 smoke 通过（log=$LOG；round_decision + 实质指标闸）"
