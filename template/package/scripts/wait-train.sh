#!/usr/bin/env bash
# wait-train.sh — 按固定间隔等待 train.py 完成（供 Agent 在后台起训后单次调用）
#
# 用法:
#   ./scripts/wait-train.sh --log _runs/logs/run.log --pid "$!"
#   ./scripts/wait-train.sh --log _runs/logs/run_slot0.log --pid 123 --parallel-total 4 \
#       --exp-dir _runs/exp/dir0 --exp-dir _runs/exp/dir1 ...
#
# 配置优先级: --interval > NN_TRAIN_POLL_INTERVAL_SEC > nn-config.yaml agent.train_poll_interval_sec > 300
# 墙钟上限: --max-wait > NN_TIME_BUDGET > 3600
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

LOG_FILE="_runs/logs/run.log"
PID=""
INTERVAL=""
MAX_WAIT=""
PARALLEL_TOTAL=1
declare -a EXP_DIRS=()

usage() {
    cat <<'EOF'
Usage: scripts/wait-train.sh [options]

  --log PATH              训练日志路径（用于摘要里 last step 指标）
  --pid PID               后台 train.py 的 PID（单槽推荐）
  --interval SEC          两次 poll 间隔（秒）
  --max-wait SEC          最长等待墙钟（秒）
  --parallel-total N      并行槽位数（>1 时等待 N 个 exp 的 train_done.json）
  --exp-dir PATH          指定 exp 目录（可重复）；省略则单槽用最新 _runs/exp/*（跳过 preflight_check）

Exit: 0 训练完成  1 失败/超时  2 参数错误
EOF
}

_read_yaml_interval() {
    # Phase 2 (config-minimal v1.4.4): 走 load_nn_config() 自动注入 preset 默认 +
    # 顶层 training.train_poll_interval_sec；缺则 300。
    _lib="$(cd "$(dirname "$0")" && pwd)/lib"
    python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, r'${_lib}')
from nn_config import load_nn_config
try:
    cfg = load_nn_config(Path('.'))
    val = (cfg.get('training') or {}).get('train_poll_interval_sec')
    print(int(val) if val is not None else 300)
except Exception:
    print(300)
" 2>/dev/null || echo 300
}

_latest_single_exp() {
    local d base
    while IFS= read -r d; do
        [[ -n "$d" && -d "$d" ]] || continue
        base="$(basename "$d")"
        [[ "$base" == *preflight_check ]] && continue
        echo "$d"
        return 0
    done < <(ls -td _runs/exp/* 2>/dev/null || true)
}

_find_parallel_exps() {
    local n="$1"
    local d base
    local count=0
    while IFS= read -r d && (( count < n )); do
        [[ -n "$d" && -d "$d" ]] || continue
        base="$(basename "$d")"
        [[ "$base" == *preflight_check ]] && continue
        echo "$d"
        count=$(( count + 1 ))
    done < <(ls -td _runs/exp/*_s*of"${n}"_* 2>/dev/null || true)
}

_all_done() {
    (( $# < 1 )) && return 1
    local d
    for d in "$@"; do
        [[ -n "$d" && -f "${d}/train_done.json" ]] || return 1
    done
    return 0
}

_any_failed() {
    local d
    for d in "$@"; do
        if [[ -n "$d" && -f "${d}/train_exception.txt" ]]; then
            echo "$d"
            return 0
        fi
    done
    return 1
}

_status_bits() {
    local exp="$1"
    local epoch="?"
    local top1="?"
    if [[ -f "${exp}/train_status.json" ]]; then
        epoch="$(python3 -c "import json; print(json.load(open('${exp}/train_status.json')).get('epoch','?'))" 2>/dev/null || echo "?")"
    fi
    if [[ -f "$LOG_FILE" ]]; then
        top1="$(grep -E '^step=' "$LOG_FILE" 2>/dev/null | tail -1 | sed -n 's/.*top1_accuracy=\([0-9.]*\).*/\1/p' || true)"
        [[ -z "$top1" ]] && top1="?"
    fi
    echo "epoch=${epoch} last_top1=${top1}"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --log) LOG_FILE="$2"; shift 2 ;;
        --pid) PID="$2"; shift 2 ;;
        --interval) INTERVAL="$2"; shift 2 ;;
        --max-wait) MAX_WAIT="$2"; shift 2 ;;
        --parallel-total) PARALLEL_TOTAL="$2"; shift 2 ;;
        --exp-dir) EXP_DIRS+=("$2"); shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "[wait-train] 未知参数: $1" >&2; usage >&2; exit 2 ;;
    esac
done

if [[ -z "$INTERVAL" ]]; then
    INTERVAL="${NN_TRAIN_POLL_INTERVAL_SEC:-$(_read_yaml_interval)}"
fi
if [[ -z "$MAX_WAIT" ]]; then
    if [[ "${NN_TIME_BUDGET:-}" == "0" ]]; then
        MAX_WAIT=0
    else
        MAX_WAIT="${NN_TIME_BUDGET:-3600}"
    fi
fi
if ! [[ "$INTERVAL" =~ ^[0-9]+$ ]] || ! [[ "$MAX_WAIT" =~ ^[0-9]+$ ]] || ! [[ "$PARALLEL_TOTAL" =~ ^[0-9]+$ ]]; then
    echo "[wait-train] interval/max-wait/parallel-total 须为非负整数" >&2
    exit 2
fi
if (( PARALLEL_TOTAL < 1 )); then
    echo "[wait-train] parallel-total 须 >= 1" >&2
    exit 2
fi

mkdir -p "$(dirname "$LOG_FILE")"

if (( PARALLEL_TOTAL == 1 )) && [[ ${#EXP_DIRS[@]} -eq 0 ]]; then
    _e="$(_latest_single_exp)"
    [[ -n "$_e" ]] && EXP_DIRS=("$_e")
fi
if (( PARALLEL_TOTAL > 1 )) && [[ ${#EXP_DIRS[@]} -eq 0 ]]; then
    mapfile -t EXP_DIRS < <(_find_parallel_exps "$PARALLEL_TOTAL")
fi

start_ts=$(date +%s)
poll=0
first_sleep=$(( INTERVAL < 45 ? INTERVAL : 45 ))

while true; do
    now=$(date +%s)
    elapsed=$(( now - start_ts ))
    if (( MAX_WAIT > 0 && elapsed >= MAX_WAIT )); then
        echo "[wait-train] poll=${poll} elapsed=${elapsed}s status=timeout max_wait=${MAX_WAIT} log=${LOG_FILE}"
        exit 1
    fi

    if (( poll == 0 )); then
        sleep "$first_sleep"
    else
        sleep "$INTERVAL"
    fi
    poll=$(( poll + 1 ))

    if [[ ${#EXP_DIRS[@]} -eq 0 ]]; then
        _e="$(_latest_single_exp)"
        [[ -n "$_e" ]] && EXP_DIRS=("$_e")
    fi

    if fail_exp="$(_any_failed "${EXP_DIRS[@]}")"; then
        echo "[wait-train] poll=${poll} elapsed=${elapsed}s status=failed reason=train_exception exp=${fail_exp} log=${LOG_FILE}"
        exit 1
    fi

    if _all_done "${EXP_DIRS[@]}"; then
        if (( PARALLEL_TOTAL <= 1 )); then
            echo "[wait-train] poll=${poll} elapsed=${elapsed}s status=done exp=${EXP_DIRS[0]} log=${LOG_FILE} $(_status_bits "${EXP_DIRS[0]}")"
        else
            echo "[wait-train] poll=${poll} elapsed=${elapsed}s status=done parallel_total=${PARALLEL_TOTAL} slots=${#EXP_DIRS[@]} log=${LOG_FILE}"
            # 多槽训末自动 finalize-round（forward-only）。
            # 能走到这里 ⟸ _any_failed(180) 未命中且 _all_done(185) 成立：全部 slot 有
            # train_done.json、无 train_exception.txt。wait-train 此刻持有全部 slot dir，
            # 正满足 finalize_round「全部候选」前提。
            # 守卫 >= PARALLEL_TOTAL：_find_parallel_exps 仅启动时取一次、主循环不回填，
            #   故要求持有数 ≥ 声明槽位数，防止只发现部分 slot 就过早 finalize。
            # 失败只 WARN、不改 exit 0（训练本身已成功）；下游 multi_slot_finalize_missing
            #   硬门(auto-nn-run.sh:1625)兜 gap→ERROR。finalize_round 幂等（已入账行跳过）。
            if (( ${#EXP_DIRS[@]} >= PARALLEL_TOTAL )); then
                if _fz_out="$(poetry run python -m contract finalize-round "${EXP_DIRS[@]}" --repo-root . 2>&1)"; then
                    echo "[wait-train] auto-finalize OK (slots=${#EXP_DIRS[@]})"
                else
                    _fz_rc=$?
                    echo "[wait-train] WARN: auto-finalize 失败(rc=${_fz_rc})，需手动 finalize-round 补账；训练本身成功，exit 0 不变。" >&2
                    echo "${_fz_out}" | tail -n 20 >&2
                    unset _fz_out _fz_rc
                fi
            fi
        fi
        exit 0
    fi

    if (( PARALLEL_TOTAL <= 1 )) && [[ -n "$PID" ]] && ! kill -0 "$PID" 2>/dev/null; then
        exp0="${EXP_DIRS[0]:-unknown}"
        echo "[wait-train] poll=${poll} elapsed=${elapsed}s status=failed reason=pid_exit pid=${PID} exp=${exp0} log=${LOG_FILE}"
        exit 1
    fi

    if (( PARALLEL_TOTAL <= 1 )) && [[ ${#EXP_DIRS[@]} -gt 0 ]]; then
        echo "[wait-train] poll=${poll} elapsed=${elapsed}s status=running log=${LOG_FILE} exp=${EXP_DIRS[0]} $(_status_bits "${EXP_DIRS[0]}")"
    else
        done_n=0
        for d in "${EXP_DIRS[@]}"; do
            [[ -f "${d}/train_done.json" ]] && done_n=$(( done_n + 1 ))
        done
        echo "[wait-train] poll=${poll} elapsed=${elapsed}s status=running parallel_total=${PARALLEL_TOTAL} done_slots=${done_n}/${#EXP_DIRS[@]} log=${LOG_FILE}"
    fi
done
