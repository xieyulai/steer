#!/usr/bin/env bash
# clear-runs.sh — 运行态清理统一入口（C0–C6 + custom）
#
# 用法:
#   bash scripts/clear-runs.sh --tier inspect
#   bash scripts/clear-runs.sh --tier junk [--apply]
#   bash scripts/clear-runs.sh --tier runs [--apply]
#   bash scripts/clear-runs.sh --tier runs+journal [--apply] [--keep-analyse]
#   bash scripts/clear-runs.sh --tier custom --drop-experiment NAME ...
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# 优先 poetry env（业务依赖如 pyarrow）；无 poetry 再退裸 python3
_nn_python() {
  if command -v poetry >/dev/null 2>&1 && { [[ -f poetry.lock ]] || [[ -f pyproject.toml ]]; }; then
    poetry run python "$@"
  else
    python3 "$@"
  fi
}

TIER=""
DRY_RUN=1
APPLY=0
CONFIRM_FACTORY=""
KEEP_RECENT=5
KEEP_ANALYSE=0
PRUNE_ARGS=()

usage() {
  cat <<'EOF'
用法: clear-runs.sh --tier <name> [选项…]

档位（C0–C6）:
  inspect          只读报告（C0）
  junk             删 preflight/smoke 脏数据（C1）
  runs             清全部 exp + TSV 表头 + jsonl（C2）
  runs+journal     C2 + reset saved/experiment_journal.json（C3）
  experience       归档 EXPERIENCE 叙事（C4）
  reflect          C4 + 清 reflect 产物（C5）
  factory          绿场（C6；apply 须 --confirm factory）
  custom           透传 prune-runs.py 参数（原 modify O1/O3）

选项:
  --dry-run        默认
  --apply          执行删除
  --confirm factory  tier=factory 且 --apply 时必需
  --keep-recent N  tier=experience 时保留最近 K 条（默认 5）
  --keep-analyse   tier=runs+journal 时保留 journal.analyse 游标

示例:
  bash scripts/govern-runs.sh clear --tier junk
  bash scripts/govern-runs.sh clear --tier junk --apply
  bash scripts/govern-runs.sh clear --tier custom --drop-experiment preflight_check --apply
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tier)
      TIER="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      APPLY=0
      shift
      ;;
    --apply)
      DRY_RUN=0
      APPLY=1
      shift
      ;;
    --confirm)
      CONFIRM_FACTORY="${2:-}"
      shift 2
      ;;
    --keep-recent)
      KEEP_RECENT="${2:-5}"
      shift 2
      ;;
    --keep-analyse)
      KEEP_ANALYSE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      PRUNE_ARGS+=("$1")
      shift
      ;;
  esac
done

[[ -n "$TIER" ]] || {
  echo "[clear-runs] 错误: 须 --tier" >&2
  usage >&2
  exit 1
}

if [[ "$TIER" == "runs+progress" ]]; then
  echo "[clear-runs] DEPRECATED: tier runs+progress 已更名为 runs+journal（下一版将移除别名）" >&2
  TIER="runs+journal"
fi

case "$TIER" in
  inspect)
    _nn_python scripts/clear_inspect.py --repo-root "$ROOT"
    exit $?
    ;;
  junk)
    JUNK_ARGS=(
      --drop-experiment preflight_check
      --drop-experiment smoke_check
      --exp-suffix _preflight_check
      --exp-suffix _smoke_check
    )
    [[ "$APPLY" -eq 1 ]] && JUNK_ARGS+=(--apply)
    _nn_python scripts/prune-runs.py "${JUNK_ARGS[@]}"
    exit $?
    ;;
  custom)
    if [[ ${#PRUNE_ARGS[@]} -eq 0 ]]; then
      echo "[clear-runs] 错误: --tier custom 须带 prune 参数（如 --drop-experiment）" >&2
      exit 1
    fi
    [[ "$APPLY" -eq 1 ]] && PRUNE_ARGS+=(--apply)
    _nn_python scripts/prune-runs.py "${PRUNE_ARGS[@]}"
    exit $?
    ;;
  runs|runs+journal)
    ;;
  reflect)
    REFLECT_ARGS=(--repo-root "$ROOT")
    [[ "$APPLY" -eq 1 ]] && REFLECT_ARGS+=(--apply)
    _nn_python scripts/clear_reflect.py "${REFLECT_ARGS[@]}"
    exit $?
    ;;
  experience)
    EXP_ARGS=(--repo-root "$ROOT" "--keep-recent" "$KEEP_RECENT")
    [[ "$APPLY" -eq 1 ]] && EXP_ARGS+=(--apply)
    _nn_python scripts/clear_experience.py "${EXP_ARGS[@]}"
    exit $?
    ;;
  factory)
    if [[ "$APPLY" -eq 1 && "$CONFIRM_FACTORY" != "factory" ]]; then
      echo "[clear-runs] 错误: factory apply 须 --confirm factory" >&2
      exit 1
    fi
    FACTORY_ARGS=(--repo-root "$ROOT")
    [[ "$APPLY" -eq 1 ]] && FACTORY_ARGS+=(--apply)
    _nn_python scripts/clear_factory.py "${FACTORY_ARGS[@]}"
    exit $?
    ;;
  *)
    echo "[clear-runs] 错误: 未知 tier: $TIER" >&2
    exit 1
    ;;
esac

warn() { echo "[clear-runs] WARN: $*" >&2; }
info() { echo "[clear-runs] $*"; }

EXP_ROOT="_runs/exp"
TSV="_runs/results.tsv"
JSONL="_runs/results.jsonl"
RD="_runs/round_decision.json"
JOURNAL="saved/experiment_journal.json"
KEEPER="saved/keeper.json"

count_exp() {
  if [[ ! -d "$EXP_ROOT" ]]; then
    echo 0
    return
  fi
  find "$EXP_ROOT" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l
}

count_tsv_data() {
  [[ -f "$TSV" ]] || { echo 0; return; }
  local n
  n=$(wc -l < "$TSV" | tr -d ' ')
  if [[ "$n" -le 1 ]]; then
    echo 0
  else
    echo $((n - 1))
  fi
}

count_jsonl() {
  [[ -f "$JSONL" ]] || { echo 0; return; }
  wc -l < "$JSONL" | tr -d ' '
}

if [[ -f "$KEEPER" ]]; then
  warn "存在 $KEEPER — clear runs 后指针可能失效，apply 后请删或 write-keeper"
fi

info "模式: tier=$TIER dry_run=$DRY_RUN"
info "将清空: ${EXP_ROOT}/* ($(count_exp) 个目录)"
info "TSV 数据行: $(count_tsv_data) → 仅保留表头"
info "jsonl 行: $(count_jsonl) → 0"
[[ -f "$RD" ]] && info "将删除: $RD"
if [[ "$TIER" == "runs+journal" ]]; then
  if [[ -f "$JOURNAL" ]]; then
    info "将 reset: $JOURNAL（entries=[]，facts 对齐 TSV）"
  else
    info "将创建空: $JOURNAL"
  fi
  if [[ "$KEEP_ANALYSE" -eq 1 ]]; then
    info "保留 journal.analyse 游标"
  fi
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  info "dry-run 结束；确认后请加 --apply"
  exit 0
fi

[[ -f scripts/regen_results_tsv.py ]] || { echo "[clear-runs] 缺少 regen_results_tsv.py" >&2; exit 1; }

if [[ -f "$TSV" && -s "$TSV" ]]; then
  cp -f "$TSV" "${TSV}.bak"
  info "已备份: ${TSV}.bak"
fi
if [[ -f "$JSONL" && -s "$JSONL" ]]; then
  cp -f "$JSONL" "${JSONL}.bak"
  info "已备份: ${JSONL}.bak"
fi

HEADER="$(_nn_python scripts/regen_results_tsv.py --repo-root . --header-only)"
printf '%s\n' "$HEADER" > "$TSV"
info "已写入 TSV 表头"

: > "$JSONL"
info "已清空 $JSONL"

if [[ -d "$EXP_ROOT" ]]; then
  rm -rf "${EXP_ROOT:?}"/*
  info "已清空 $EXP_ROOT"
fi

rm -f "$RD"
info "已删除 round_decision（若曾存在）"

if [[ "$TIER" == "runs+journal" ]]; then
  [[ -f scripts/lib/experiment_journal.py ]] || {
    echo "[clear-runs] 缺少 scripts/lib/experiment_journal.py" >&2
    exit 1
  }
  _keep_flag=""
  [[ "$KEEP_ANALYSE" -eq 1 ]] && _keep_flag="keep_analyse=True"
  python3 -c "
import sys
sys.path.insert(0, 'scripts')
from lib.experiment_journal import reset_journal_for_runs_clear
reset_journal_for_runs_clear('.', apply=True, ${_keep_flag:-keep_analyse=False})
"
  info "已 reset $JOURNAL"
fi

info "apply 完成；建议: bash scripts/smoke-check.sh"
