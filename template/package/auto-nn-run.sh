#!/usr/bin/env bash
# =============================================================================
# auto-nn-run.sh — NN 实验外层循环（通用版：claude 优先，cursor 兜底）
#
# 用法:
#   ./auto-nn-run.sh <N>              # N 轮实验
#   ./auto-nn-run.sh reflect         # 仅反思（reflect.py；不跑实验）
#   ./auto-nn-run.sh <N> reflect     # N 轮实验，每轮后自动反思
#   ./auto-nn-run.sh <N> --claude ccx  # Claude 前端：claude|ccg|ccm|ccx|ccmm
#   ./auto-nn-run.sh <N> --agent cursor # 强制 Cursor（默认 auto：有 claude 则用 Claude）
#   ./auto-nn-run.sh -h | --help | help # 命令使用帮助（_print_usage；exit 0）
#
# 环境变量:
#   NN_AGENT_BACKEND         — auto（默认）| claude | cursor（与 --agent 二选一，CLI 优先）
#   NN_AGENT_CLAUDE_CMD      — Claude 前端：claude（默认）| ccg | ccm | ccmm | ccx（与 --claude 二选一，CLI 优先）
#   NN_AGENT_CURSOR_MODEL    — Cursor 模型（传给 agent --model；与 --model 二选一，CLI 优先）
#   NN_CC_SWITCH_HOME        — cc-switch 配置目录 HOME（$HOME 为软链的机器上指向真实家目录）
#   NN_AGENT_HEARTBEAT_SEC   — 心跳间隔秒数（默认 120）
#   NN_TIME_BUDGET — 冻结派生量：本脚本从 nn-config.yaml time_budget 解析后 export（供 wait-train max-wait / 横幅被动消费）；
#       会话内预 export 非默认值不再盖章放行——与 yaml 不一致即拒启并记 _runs/time_budget_violations.log（见 experiment.py _resolve_time_budget）
#       （已弃用 NN_AGENT_TRAIN_TIME_BUDGET_SEC 第三来源；0=关闭走 nn-config.yaml 显式写 time_budget: 0）
#   NN_AUTO_RUN_ACTIVE — 实验批次（REFLECT_ONLY=0）由本脚本设为 1，退出时 unset；可与 saved/.auto-run-active.pid 配对供 gate 校验
#   NN_RELAUNCH — 非空表示「立项 / 迁移轮」（允许动 contract/）；preflight G2 在此时不警告
#   NN_SMOKE — 本脚本启动时 export 0（全量训练）；迁移验收用 smoke-check.sh 单独 NN_SMOKE=1
#   迁移五阶段：migration-compare.sh(分析) → F1口径 → 改码 → CHECKLIST§2-4 → verify0+§5smoke（F1≠完成）
#   NN_AGENT_CLAUDE_DEBUG — 默认开启 --debug-file（*_agent-round-N_claude-debug.txt）；0/false/no/off 关闭
#   NN_AGENT_CLAUDE_STREAM_JSON — 默认开启：Claude --output-format stream-json --verbose → 原始 NDJSON
#       写入 *_agent-round-N_stream.jsonl；0 关闭（改用普通文本到 _runs/logs/run.log / 终端）
#   NN_AGENT_CLAUDE_STREAM_TO_STDERR — 仅当 stream-json 开启时有效；默认 0。设为 1/true/on 时把完整 NDJSON 再 tee 到 stderr（调试用，极吵）。
#   NN_AGENT_CLAUDE_STREAM_PROGRESS — 仅当 stream-json 开启且未开 STREAM_TO_STDERR 时有效；默认 1。
#       终端 stderr 只打印「单行结构化摘要」（类型 / tool 名 / 长度等），完整 NDJSON 仍在 *_agent-round-N_stream.jsonl 与 *_agent-round-N.log。
#       设为 0 关闭摘要（终端对 Agent  stdout 静默，仅 tail -f 文件跟进度）。
#   stderr 摘要实现：与本脚本同目录下 scripts/claude_stream_summarize.py（迁移项目时请保留该文件）。
#   NN_AGENT_CLAUDE_RESULT_GRACE_SEC — stream-json 轮：见 *_stream.jsonl 出现 type=result 后，若 Claude 进程仍存活则
#       等待该秒数再 SIGTERM→SIGKILL（默认 60）；0=关闭 watchdog。实现：scripts/claude_stream_result_watchdog.py
#
# 记录: 训练 tail -f _runs/logs/run.log；Claude stream-json → tail -f *_agent-round-N_stream.jsonl；
#       *_agent-round-N.log 含元数据+prompt 摘要；批次心跳 → *_batch.log（见 _runs/agent/README.md）
#   整终端: script -qfe _runs/agent/manual_typescript.log -- ./auto-nn-run.sh N
#
# 特性:
#   - 前台管道：Ctrl+C / SIGTERM 可直接中断 agent
#   - 自动反思：每轮结束后调用 reflect.py（Phase0 压缩 + Phase1～3）
#
# 日志: _runs/agent/
# =============================================================================
set -e

HEARTBEAT_SEC="${NN_AGENT_HEARTBEAT_SEC:-120}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

LOG_DIR="_runs/agent"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/$(date +%Y%m%d_%H%M%S)_batch.log"

log() {
    local level=$1; local message=$2
    local timestamp; timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "${timestamp} [${level}] ${message}" >> "$LOG_FILE"
    case $level in
        INFO)     echo -e "${DIM}${timestamp}${NC} ${BLUE}[INFO]${NC} ${message}" ;;
        SUCCESS)  echo -e "${DIM}${timestamp}${NC} ${GREEN}[SUCCESS]${NC} ${message}" ;;
        WARNING)  echo -e "${DIM}${timestamp}${NC} ${YELLOW}[WARNING]${NC} ${message}" ;;
        ERROR)    echo -e "${DIM}${timestamp}${NC} ${RED}[ERROR]${NC} ${message}" ;;
        PROGRESS) echo -e "${DIM}${timestamp}${NC} ${CYAN}[PROGRESS]${NC} ${message}" ;;
    esac
}

count_result_rows() {
    python3 -c "
import sys
p = '_runs/results.tsv'
try:
    with open(p) as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    print(max(0, len(lines) - 1))
except Exception:
    print(0)
" 2>/dev/null || echo "0"
}

contract_metric_key() {
    poetry run python -c "from contract import create_contract; print(create_contract({}).metric_key)" 2>/dev/null \
        || python3 -c "from contract import create_contract; print(create_contract({}).metric_key)" 2>/dev/null \
        || echo "?"
}

_nn_cfg_val() {
    python3 -c "
import yaml, sys
c = yaml.safe_load(open('nn-config.yaml'))
keys = sys.argv[1].split('.')
v = c
for k in keys: v = v[k]
print(v if not isinstance(v, list) else ','.join(map(str, v)))
" "$1" 2>/dev/null
}

_nn_cfg_profile() {
    if [[ -f nn-config.yaml ]]; then
        _nn_cfg_val "profile" 2>/dev/null
    else
        echo "(unset)"
    fi
}

_nn_cfg_exploration() {
    # 展示用：优先顶层 exploration_mode（与 load_nn_config_legacy_keys _vals[8] 一致）
    _nn_cfg_val 'exploration_mode' 2>/dev/null || _nn_cfg_val 'agent.exploration' 2>/dev/null || echo "optimize"
}

_nn_cfg_scenario_policy() {
    _nn_cfg_val 'agent.scenario_policy' 2>/dev/null || echo ""
}

_nn_cfg_scenario_default() {
    _nn_cfg_val 'agent.scenario_default' 2>/dev/null || echo ""
}

_nn_cfg_scenario_active() {
    _nn_cfg_val 'agent.scenario_active' 2>/dev/null || echo ""
}

_nn_cfg_train_poll_interval() {
    _nn_cfg_val 'training.train_poll_interval_sec' 2>/dev/null || echo "300"
}

# 批次内 nn-config.yaml 不可变（Agent 禁改）：循环前一次性读全部静态键 → 缓存到 CFG_* 全局变量，
# 避免每轮重复 spawn python3 读 yaml。GPU 三档快照（gpu_snapshot.py）随轮变化，不在此缓存。
_nn_cfg_load_static() {
    local _vals=()
    # v4 schema 解析：调 lib.nn_config.load_nn_config_legacy_keys()（v4-aware + preset expansion）
    # 见 scripts/lib/nn_config.py 注释：旧 heredoc 解析 v3 agent.* 字段，v4 顶层 block 全部解析为空
    # → 落 log "keep=? mode=? primary_delta=? exploration=conservative (fallback)"，与 yaml 实际不符。
    # 新 helper 统一读 v3 兼容（agent.* 回填）+ v4 顶层 block，15 行按原顺序输出。
    mapfile -t _vals < <(PYTHONPATH=scripts python3 -c "from lib.nn_config import load_nn_config_legacy_keys; print(load_nn_config_legacy_keys('.'))" 2>/dev/null || printf '%s\n' "" "" "" "" "" "" "" "" "" "" "" "" "" "" "")
    CFG_PROFILE="${_vals[0]:-}"
    CFG_TIME_BUDGET="${_vals[1]:-}"
    CFG_GPUS="${_vals[2]:-}"
    CFG_MAX_PARALLEL="${_vals[3]:-}"
    CFG_KEEP_IMPROVE="${_vals[4]:-}"
    CFG_KEEP_MODE="${_vals[5]:-}"
    CFG_KEEP_PRIMARY_DELTA="${_vals[6]:-}"
    CFG_KEEP_NEAR_BEST_ABS="${_vals[7]:-}"
    CFG_EXPLORATION="${_vals[8]:-}"
    CFG_PLATEAU_ROUNDS="${_vals[9]:-}"
    CFG_REFLECT_INTERVAL="${_vals[10]:-}"
    CFG_POLL_INTERVAL="${_vals[11]:-}"
    CFG_SCENARIO_POLICY="${_vals[12]:-}"
    CFG_SCENARIO_DEFAULT="${_vals[13]:-}"
    CFG_SCENARIO_ACTIVE="${_vals[14]:-}"
    # profile 在无配置文件时显示 (unset)，与旧 _nn_cfg_profile 行为一致
    [[ -f nn-config.yaml ]] || CFG_PROFILE="(unset)"
}

# 安全替换 prompt 占位符（避免 sed -i 在含 /& 等字符时破坏临时文件或误伤脚本）
_nn_prompt_substitute() {
    local _pf="$1"
    shift
    [[ -f "$_pf" ]] || return 1
    python3 - "$_pf" "$@" <<'PY'
import sys
path = sys.argv[1]
text = open(path, encoding="utf-8").read()
for spec in sys.argv[2:]:
    key, _, val = spec.partition("=")
    if not key:
        continue
    text = text.replace(key, val)
open(path, "w", encoding="utf-8").write(text)
PY
}

# --- Human roadmap / reflect index（PROTOCOL §7.5–7.6）---
_extract_human_roadmap_block() {
    [[ -f HUMAN_GUIDANCE.md ]] || return 0
    PYTHONPATH="${SCRIPT_DIR}/scripts${PYTHONPATH:+:$PYTHONPATH}" python3 - <<'PY' 2>/dev/null || true
from pathlib import Path
import sys
sys.path.insert(0, "scripts")
from lib.human_guidance_roadmap import (
    fair_constraints_section_body,
    roadmap_section_body,
    count_roadmap_phases,
)

text = Path("HUMAN_GUIDANCE.md").read_text(encoding="utf-8", errors="replace")
fair_body = fair_constraints_section_body(text)
body = roadmap_section_body(text)
has_phases = count_roadmap_phases(text) > 0
if not has_phases and not fair_body:
    raise SystemExit(0)
if fair_body:
    print("=== HUMAN 公平约束（必读；与路线图并列）===\n")
    print(fair_body)
    print("\n=== END HUMAN 公平约束 ===\n")
if has_phases:
    print("=== HUMAN ROADMAP（必读，优先级最高）===\n")
    print(body.strip())
    print("\n=== END HUMAN ROADMAP ===")
PY
}

_roadmap_status_block() {
    [[ -f scripts/summarize-runs.py ]] || return 0
    python3 scripts/summarize-runs.py --repo-root "${SCRIPT_DIR}" --roadmap-status 2>/dev/null || true
}

_extract_reflect_pending_block() {
    [[ -f references/REFLECT_INDEX.md ]] || return 0
    python3 - <<'PY' 2>/dev/null || true
import re
from pathlib import Path
text = Path("references/REFLECT_INDEX.md").read_text(encoding="utf-8", errors="replace")
m = re.search(r"##\s*待消费[^\n]*\n(.*?)(?=\n##\s|\Z)", text, re.DOTALL | re.I)
if not m:
    raise SystemExit(0)
section = m.group(1)
for line in section.splitlines():
    line = line.strip()
    if not line.startswith("|") or "---" in line:
        continue
    cells = [c.strip() for c in line.strip("|").split("|")]
    if len(cells) >= 4 and cells[0] not in ("（无）", "—", "-", "", "id"):
        print("=== REFLECT PENDING（必读；优先级低于 HUMAN_GUIDANCE）===\n")
        print(line)
        if len(cells) >= 4:
            print(f"\n下轮建议: {cells[3]}")
        print("\n=== END REFLECT PENDING ===")
        raise SystemExit(0)
raise SystemExit(0)
PY
}

_has_reflect_pending() {
    [[ -n "$(_extract_reflect_pending_block 2>/dev/null || true)" ]]
}

_reflect_ack_missing_marker() {
    echo "${SCRIPT_DIR}/saved/.reflect_ack_missing_last_run"
}

_consume_reflect_pending_if_ack() {
    local run="$1"
    [[ "$REFLECT_ONLY" == "1" ]] && return 0
    [[ "${REFLECT_PENDING_AT_ROUND_START:-0}" -eq 1 ]] || return 0
    local _ack _quality
    _ack="$(python3 - <<'PY' 2>/dev/null || true
import sys
from pathlib import Path
sys.path.insert(0, "scripts")
from lib.experience_ack import extract_reflect_ack_from_path
print(extract_reflect_ack_from_path(Path("EXPERIENCE.md")) or "")
PY
)"
    if [[ -z "$_ack" ]]; then
        log "WARNING" "reflect_ack_missing: Run $run 未写有效 reflect_ack，pending 未消费"
        echo "$run" > "$(_reflect_ack_missing_marker)"
        BATCH_REFLECT_ACK_MISSING=$((BATCH_REFLECT_ACK_MISSING + 1))
        return 0
    fi
    rm -f "$(_reflect_ack_missing_marker)" 2>/dev/null || true
    _quality="$(python3 - <<'PY' 2>/dev/null || echo low
import sys
from pathlib import Path
sys.path.insert(0, "scripts")
from lib.experience_ack import extract_reflect_ack_from_path, reflect_ack_quality_ok
ack = extract_reflect_ack_from_path(Path("EXPERIENCE.md")) or ""
print("ok" if reflect_ack_quality_ok(ack) else "low")
PY
)"
    if [[ "$_quality" == "low" ]]; then
        log "WARNING" "reflect_ack_low_quality: Run $run ack 过短或未含 adopt/defer/conflict/roadmap"
    fi
    if [[ -x scripts/mark-reflect-consumed.sh ]]; then
        if ! bash scripts/mark-reflect-consumed.sh "$_ack" >> "$AGENT_ROUND_LOG" 2>&1; then
            log "WARNING" "mark-reflect-consumed 失败（非致命）"
        fi
    fi
}

_reflect_skip_log() {
    local reason="$1"
    local f="$LOG_DIR/$(date +%Y%m%d_%H%M%S)_reflect-skipped.log"
    printf '%s\n' "$reason" > "$f"
    log "INFO" "Reflect skipped: $reason (see $(basename "$f"))"
}

_should_run_reflect() {
    local run="$1"
    REFLECT_RUN_REASON=""
    local _interval=1 _plateau=3
    if [[ -f nn-config.yaml ]]; then
        _interval="$(_nn_cfg_val 'reflect.interval' 2>/dev/null || echo 1)"
        _plateau="$(_nn_cfg_val 'agent.plateau_rounds' 2>/dev/null || echo 3)"
    fi
    if [[ ! "$_interval" =~ ^[0-9]+$ ]] || [[ "$_interval" -eq 0 ]]; then
        _reflect_skip_log "reflect_interval=0（关闭自动 reflect）"
        return 1
    fi
    local _gate_out
    _gate_out="$(python3 "${SCRIPT_DIR}/scripts/summarize-runs.py" --reflect-gate --run "$run" --repo-root "${SCRIPT_DIR}" 2>/dev/null || echo "skip:gate_error")"
    if [[ "$_gate_out" == run:* ]]; then
        REFLECT_RUN_REASON="${_gate_out#run:}"
        return 0
    fi
    _reflect_skip_log "${_gate_out#skip:}"
    return 1
}

_nn_cfg_run_context_injection() {
    _nn_cfg_val 'context.injection' 2>/dev/null || echo "full"
}

_nn_cfg_human_gate_fail_fast() {
    local _v
    _v="$(_nn_cfg_val 'safety.human_guidance_gate_fail_fast' 2>/dev/null || echo false)"
    [[ "$_v" == "true" || "$_v" == "1" ]] && echo 1 || echo 0
}

_write_human_guidance_baseline() {
    [[ -f scripts/human_guidance_gate.py ]] || return 0
    python3 scripts/human_guidance_gate.py --repo-root "${SCRIPT_DIR}" write-baseline \
        >> "$LOG_FILE" 2>&1 || log "WARNING" "human-guidance baseline 写入失败（非致命）"
}

# 批次异常退出时也清理 NN_AUTO_RUN_ACTIVE / pid（正常结束再由 auto-run-batch-tail.sh 收口）
_cleanup_auto_run_active() {
    unset NN_AUTO_RUN_ACTIVE 2>/dev/null || true
    rm -f "${SCRIPT_DIR}/saved/.auto-run-active.pid" 2>/dev/null || true
}

_check_human_guidance_gate() {
    [[ -f scripts/human_guidance_gate.py ]] || return 0
    if python3 scripts/human_guidance_gate.py --repo-root "${SCRIPT_DIR}" check >> "$AGENT_ROUND_LOG" 2>&1; then
        return 0
    fi
    log "ERROR" "HUMAN_GUIDANCE 相对批次基线已变更 — 跳过本轮 Agent（仅人可改 HUMAN）"
    return 1
}

_maybe_auto_compress_experience() {
    local _run="$1"
    [[ -f scripts/lib/experience_auto_compress.py ]] || return 0
    local _out _rc
    _out="$(python3 - <<PY 2>&1 || true
import sys
from pathlib import Path
sys.path.insert(0, str(Path("${SCRIPT_DIR}").resolve() / "scripts"))
from lib.experience_auto_compress import run_auto_compress
rc, msg = run_auto_compress(Path("${SCRIPT_DIR}").resolve(), int("${_run}"))
print(msg)
raise SystemExit(rc)
PY
)"
    _rc=$?
    if [[ -n "$_out" ]]; then
        echo "$_out" >> "$AGENT_ROUND_LOG"
        if [[ "$_out" == warn:* ]]; then
            log "WARNING" "EXPERIENCE compress 建议: ${_out#warn: }"
        elif [[ "$_out" == applied:* ]]; then
            log "INFO" "EXPERIENCE auto-compress: ${_out#applied: }"
        elif [[ "$_out" == fail:* ]]; then
            log "WARNING" "EXPERIENCE auto-compress 失败: ${_out#fail: }"
        fi
    fi
    return 0
}

_inject_run_context_prompt() {
    local _pf="$1"
    [[ -f "$_pf" ]] || return 0
    local _mode _rc_args=()
    _mode="$(_nn_cfg_run_context_injection)"
    if [[ "${TOTAL_RUNS:-0}" -gt 0 ]]; then
        _rc_args=(
            --batch-run "${run:-1}"
            --batch-total "${TOTAL_RUNS}"
            --max-parallel "${_HW_MAX_PARALLEL:-1}"
            --free-gpus "${_HW_FREE_GPUS:-unknown}"
            --gpus-whitelist "${_HW_GPUS:-auto-detect}"
        )
        if [[ -n "${_HW_GPU_SNAP_FILE:-}" && -f "${_HW_GPU_SNAP_FILE}" ]]; then
            _rc_args+=(--gpu-snapshot-file "${_HW_GPU_SNAP_FILE}")
        fi
    fi
    if [[ "$_mode" == "off" ]]; then
        if [[ ${#_rc_args[@]} -gt 0 ]] && [[ -f "${SCRIPT_DIR}/scripts/build-run-context.py" ]]; then
            {
                echo ""
                echo "=== RUN CONTEXT（batch-only；run_context_injection=off）==="
                python3 "${SCRIPT_DIR}/scripts/build-run-context.py" \
                    --repo-root "${SCRIPT_DIR}" --format batch-md --run "${run:-1}" \
                    "${_rc_args[@]}" 2>/dev/null || true
                echo "=== END RUN CONTEXT ==="
                echo ""
            } >> "$_pf" || true
        fi
        return 0
    fi
    if [[ ! -f "${SCRIPT_DIR}/scripts/build-run-context.py" ]]; then
        {
            echo ""
            echo "=== RUN CONTEXT（auto-run 每轮注入）==="
            echo "(缺少 scripts/build-run-context.py)"
            echo "=== END RUN CONTEXT ==="
            echo ""
        } >> "$_pf"
        return 0
    fi
    python3 "${SCRIPT_DIR}/scripts/build-run-context.py" \
        --repo-root "${SCRIPT_DIR}" --write --run "${run:-1}" \
        "${_rc_args[@]}" >/dev/null 2>&1 || true
    {
        echo ""
        python3 "${SCRIPT_DIR}/scripts/build-run-context.py" \
            --repo-root "${SCRIPT_DIR}" --format md --run "${run:-1}" \
            "${_rc_args[@]}" 2>/dev/null \
            || echo "=== RUN CONTEXT ===
(run_context 生成失败)
=== END RUN CONTEXT ==="
        echo ""
    } >> "$_pf"
}

_inject_explore_prompt() {
    local _pf="$1"
    [[ -f "$_pf" ]] || return 0
    local _eo_line _mode _src
    _eo_line="$(
        python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path('${SCRIPT_DIR}') / 'scripts'))
from lib.explore_objective import effective_objective
r = effective_objective(Path('${SCRIPT_DIR}'))
print(f'effective_objective: {r.mode} (source={r.source})')
" 2>/dev/null || echo "effective_objective: optimize (source=default)"
    )"
    {
        echo ""
        echo "$_eo_line"
    } >> "$_pf"
    _mode="${_eo_line#effective_objective: }"
    _mode="${_mode%% *}"
    if [[ "$_mode" != "explore" ]]; then
        return 0
    fi
    {
        echo ""
        echo "0e. **EXPLORE MODE**（effective_objective=explore）"
        echo "    - 本轮目标：覆盖 / 证伪 / 多场景摸底（见 HUMAN NOTE），**非** primary 相对改善。"
        echo "    - keeper = 探索代码链锚点，**≠** metric_leader；不得仅据 keeper 断言 SOTA。"
        echo "    - DISCARD 若 attested 仍须在 EXPERIENCE 记录证伪结论；reflect_ack 须对照 HUMAN 探索网格。"
        echo "    - HUMAN NOTE 探索网格 / 场景顺序 / 禁止项 **高于** REFLECT pending 与 coverage brief。"
        echo ""
    } >> "$_pf"
}

_inject_guidance_reflect_prompt() {
    local _pf="$1"
    [[ -f "$_pf" ]] || return 0
    local _hg _rs _rp _missing_run=""
    _hg="$(_extract_human_roadmap_block 2>/dev/null || true)"
    _rs="$(_roadmap_status_block 2>/dev/null || true)"
    _rp="$(_extract_reflect_pending_block 2>/dev/null || true)"
    if [[ -f "$(_reflect_ack_missing_marker)" ]]; then
        _missing_run="$(cat "$(_reflect_ack_missing_marker)" 2>/dev/null || true)"
    fi
    if [[ -z "$_hg" && -z "$_rp" && -z "$_missing_run" ]]; then
        return 0
    fi
    {
        echo ""
        echo "--- Mandatory human / reflect context (injected by auto-nn-run.sh) ---"
        if [[ -n "$_missing_run" ]] && _has_reflect_pending 2>/dev/null; then
            echo "### Reflect 未确认消费（上轮 WARN）"
            echo "- 上轮 batch_run=${_missing_run} 结束时 EXPERIENCE 缺少有效 \`reflect_ack:\`，pending **未**归档。"
            echo "- 本轮须先读 REFLECT pending，并在本轮 EXPERIENCE 写 \`reflect_ack:\`。"
            echo ""
        fi
        if [[ -n "$_hg" ]]; then
            printf '%s\n' "$_hg"
            if [[ -n "$_rs" ]]; then
                echo ""
                echo "=== ROADMAP STATUS（summarize-runs --roadmap-status）==="
                printf '%s\n' "$_rs"
                echo "=== END ROADMAP STATUS ==="
                echo ""
                echo "只守 inferred_phase 对应阶段的 NOTE（含 Tier）；criteria_met 满足后下轮按下一阶段 NOTE 继续，勿改 HUMAN_GUIDANCE.md。"
            fi
        fi
        [[ -n "$_rp" ]] && printf '%s\n' "$_rp"
        echo "--- End injected context ---"
        echo ""
    } >> "$_pf"
}

_inject_tam_cochange_prompt() {
    local prompt_file="$1"
    local tam_line=""
    if [[ -f saved/tier_attestation.json ]]; then
        tam_line="$(python3 -c "import json;print(json.load(open('saved/tier_attestation.json')).get('tam_line',''))" 2>/dev/null || true)"
    fi
    {
        echo ""
        echo "## TAM 共改与 config 举证（轮初必读）"
        echo ""
        echo "权威：\`saved/tier_attestation.json\`（代码 diff + config.json 键 Δ）；**禁止**用 EXPERIENCE `## Tier 状态`（二维矩阵）覆盖 TAM 的 attested/not_attested。"
        if [[ -n "$tam_line" ]]; then
            echo "- 当前举证：${tam_line}"
        fi
        echo "- **B/C 单变量（OVAT）**：新文件放 \`workspace/nn/\`、\`workspace/models/\`、\`workspace/objectives/\`；**勿共改** \`workspace/data_process.py\`（否则 D 档证据干扰归因）。"
        echo "- **config-only**：只改 \`config.json\` 的 \`MODEL_ARCH\` / \`LOSS\` / \`MIXUP_*\` 等也会进 TAM；OVAT 时只动对应键。"
        echo "- EXPERIENCE「Tier 状态」（二维矩阵）须与 TAM 一致；写「已深/浅尝」时 TAM 该档不得 \`not_attested\`（reflect 会 WARN）。"
        echo ""
    } >> "$prompt_file"
}

_maybe_echo_e_feedback_pending() {
    local n=""
    n="$(PYTHONPATH="${SCRIPT_DIR}/scripts" python3 -c "
from pathlib import Path
from lib.e_feedback_store import pending_count
print(pending_count(Path('${SCRIPT_DIR}')))
" 2>/dev/null || true)"
    if [[ "${n:-0}" =~ ^[0-9]+$ ]] && [[ "$n" -gt 0 ]]; then
        log "INFO" "有改题建议已记下；本批不等人。稍后分析或手跑反思再处置（留下/搁置/驳回只改记录）。"
    fi
}

_inject_innovation_prompt() {
    local prompt_file="$1"
    local innov_boost=""
    innov_boost="$(python3 - <<'PY' 2>/dev/null || true
from pathlib import Path
import sys
sys.path.insert(0, "scripts")
from lib.experiment_mode import resolve_exploration
r = resolve_exploration(Path("."))
print("1" if r.innovate_prompt_boost else "0")
PY
)"
    local innov_line=""
    if [[ -f saved/innovation_audit.json ]]; then
        innov_line="$(python3 -c '
import json,sys
try:
    d = json.load(open("saved/innovation_audit.json"))
    print(d.get("summary_line", "") or "")
except Exception:
    pass
' 2>/dev/null || true)"
    fi

    # Fallback: 从 EXPERIENCE 二维矩阵提取简要状态（即使无 audit.json）
    if [[ -z "$innov_line" && -f EXPERIENCE.md ]]; then
        innov_line="$(python3 -c '
import re,sys
try:
    txt = open("EXPERIENCE.md").read()
    sec = re.search(r"^## Tier 状态（", txt, re.M)
    if sec:
        start = sec.start()
        rest = txt[start+1:]
        nxt = re.search(r"\n^## ", rest, re.M)
        end = start + 1 + (nxt.start() if nxt else len(rest))
        block = txt[start:end]
        rows = []
        for l in block.splitlines():
            s = l.strip()
            if "|" in s and not s.startswith("|-") and "Tier" not in s and s:
                parts = [p.strip() for p in s.strip("|").split("|") if p.strip()]
                if parts:
                    rows.append(" ".join(parts))
        if rows:
            print("EXPERIENCE矩阵: " + " | ".join(rows[:4]))
except Exception:
    pass
' 2>/dev/null || true)"
    fi

    {
        echo ""
        echo "## 创新维度（routine / extend / novel）——轮初必读（与 TAM 正交）"
        echo ""
        if [[ "$innov_boost" == "1" ]]; then
            echo "实验模式=innovate/aggressive（innovate_prompt_boost）：本轮优先在 workspace/ 落地 extend/novel（新 @register_learner / objective / aug 等），不要只拧已注册 config 键；不要把「未注册实现」写成须等人解锁。仍禁止改 contract/ 等禁区。metric goal 仍硬停。"
            echo ""
        fi
        echo "见 PROTOCOL §7.5.1a。TAM 负责「该字母档是否被代码或 config 举证」（覆盖维）；"
        echo "创新维负责「该字母档的深度是否已穷尽」（routine=经典现成、extend=论文级/成熟组合、novel=研究性新结构或新目标形式）。"
        if [[ -n "$innov_line" ]]; then
            echo "- 当前 Innovation 摘要：${innov_line}"
        fi
        echo ""
        echo "**重要规则（请严格遵守）：**"
        echo "- **careful/optimize**：仅当 EXPERIENCE 二维 \`## Tier 状态\` 矩阵中**具体格子**标「已穷尽」时，才优先考虑同档下一深度或升档。"
        echo "- **innovate/aggressive**（boost 开）：若外源/创新维指向尚无代码的 extend/novel，**允许并鼓励本轮直接在 workspace 实现并训练**，不以「格子已穷尽」或「等人改能力」为前置。"
        echo "- 经典结构（torchvision、timm、kornia 现成 API，或项目已登记的常见 backbone/loss/aug）即使本项目之前没用过，也属于 routine，不是 novel。"
        echo "- 每轮训练结束写 EXPERIENCE 时，**必须**在该轮块内填写："
        echo "  - **innovation_depth**: routine | extend | novel"
        echo "  - **innovation_rationale**: 一句说明（例如：\`torchvision.resnet50\` / \`按 FNO 论文复现\` / \`自研 physics fusion block\`）"
        echo "- 不要只看 TAM 的 \`B:att×n\` 就宣称「B 已穷尽」或「可以升 C」。必须同时看 EXPERIENCE 的二维矩阵。"
        echo ""
        # === abcde-manual Tier 切片（append segment B — spec §5.2 Step 2）===
        tier_slice="$(python3 - <<'PY' 2>/dev/null || true
import sys
from pathlib import Path
sys.path.insert(0, "scripts")
from inject_innovation_segments import render_tier_slice
try:
    print(render_tier_slice(Path(".")))
except Exception:
    pass
PY
)"
        if [[ -n "$tier_slice" ]]; then
            echo "$tier_slice"
            echo ""
        fi
    } >> "$prompt_file"
}

_run_round_doctor() {
    local round="$1"
    local out_dir="_runs/doctor_reports"
    local out_log="${out_dir}/R${round}.log"
    mkdir -p "$out_dir"
    if [[ -f scripts/nn-doctor.sh ]]; then
        bash scripts/nn-doctor.sh > "$out_log" 2>&1 || true
    else
        : > "$out_log"
    fi
}

_inject_doctor_drift_prompt() {
    local prompt_file="$1"
    local run="$2"
    local prev_round=$((run - 1))
    [[ "$prev_round" -lt 1 ]] && return 0
    local log_path="_runs/doctor_reports/R${prev_round}.log"
    [[ -f "$log_path" ]] || return 0
    local fail_lines
    fail_lines=$(grep -E '^\[nn-doctor\].*FAIL' "$log_path" | head -10 || true)
    [[ -z "$fail_lines" ]] && return 0
    {
        printf '\n## Doctor R%d 漂移报告\n' "$prev_round"
        printf '\n上轮 doctor 检查结果（FAIL 行）：\n\n'
        while IFS= read -r line; do
            printf -- '- %s\n' "$line"
        done <<< "$fail_lines"
        printf '\n修复指引：\n'
        printf -- '- 改 train.py / workspace/（**可改**）\n'
        printf -- '- references/manual/abcde-manual.md：仅 fork 触发（REFLECT_INDEX 有 `[升级建议] register→fork` pending）时，可改命名 cell 从 register→fork（cell 级、单向）\n'
        printf -- '- 不改 contract/ / experiment.py / PROTOCOL.md / nn-config.yaml / auto-nn-run.sh（**不可改**）\n'
        printf -- '- no-fallback FAIL：except 加 `raise` 或加 `# optional:` 注释（合法 optional 路径）\n'
        printf -- '- 设 NN_GUARD_*=0 临时跳过 = 污染代码，须回滚\n'
        printf -- '- 详见 scripts/nn-doctor.sh 输出\n'
    } >> "$prompt_file"
}

# 轮初 pluggability 原则（设计自检 — 总是注入，不 FAIL-gate）
_inject_pluggable_principles_prompt() {
    local prompt_file="$1"
    cat >> "$prompt_file" <<'PRINCIPLES_EOF'

## Pluggability 原则（每轮自检）

新增 / 修改工作完成后，自问：

1. **新增不影响存量**：本轮加的新模型 / 新模块 / 新参数，是否让已有 baseline / 其他实验行为变化？
   - 反例：在 registry 加 `vit_b16`，但改了 `vit_l14` 的默认 lr → 老实验 lr 漂移
   - 正例：加 `vit_b16` 时，老模型配置完全不动

2. **重构保留旧值**：把 hardcode 改成 configurable 时，老值是否仍可恢复？
   - 反例：`lr=1e-3` → `lr=cfg["LR"]`，但 config.json 未写 LR → KeyError 或误用其它实验的 LR
   - 正例：新变体走 registry + 当轮 config.json 显式 `"LR": 0.001`；老 baseline 的 config 不动，行为不变（禁止 `cfg.get("LR", default)` 静默兜底，见 PROTOCOL §0.1 config-only）

不是 FAIL 门禁 — 是设计自检。若发现违反，回到 PROTOCOL §6 调整（不是写代码回滚 baseline）。
PRINCIPLES_EOF
}

# 解析并 export NN_TIME_BUDGET（冻结派生量：唯一真值 nn-config.yaml）；设置 NN_TB_SOURCE 供启动日志说明来源。
# 预置的 NN_TIME_BUDGET 不再盖章放行（旧 passthrough 分支已拆）：与 yaml 不一致 → 记违约日志并拒启。
_nn_cfg_resolve_time_budget() {
    local _from_yaml=""
    if [[ -f nn-config.yaml ]]; then
        _from_yaml="$(_nn_cfg_val 'time_budget' 2>/dev/null || true)"
    fi
    local _tb_val
    if [[ -n "${_from_yaml}" && "${_from_yaml}" =~ ^[0-9]+$ ]]; then
        _tb_val="${_from_yaml}"
        NN_TB_SOURCE="nn-config.yaml:time_budget"
    else
        _tb_val=3600
        NN_TB_SOURCE="脚本默认 3600（nn-config.yaml 无 time_budget）"
    fi
    if [[ -v NN_TIME_BUDGET && "${NN_TIME_BUDGET}" != "${_tb_val}" ]]; then
        mkdir -p _runs
        printf '%s\tpid=%s\tcwd=%s\tenv=%s\tyaml=%s\tlauncher=auto-nn-run.sh(拒启)\n' \
            "$(date '+%Y-%m-%d %H:%M:%S')" "$$" "$(pwd)" "${NN_TIME_BUDGET}" "${_tb_val}" \
            >> _runs/time_budget_violations.log
        echo "ERROR: 预置 NN_TIME_BUDGET=${NN_TIME_BUDGET} 与 nn-config.yaml time_budget=${_tb_val} 不一致：时限已冻结为 Config-Only，会话内预 export 改墙钟拒绝启动（已记 _runs/time_budget_violations.log）。改时限请改 nn-config.yaml。" >&2
        exit 1
    fi
    export NN_TIME_BUDGET="${_tb_val}"
}

_print_nn_config_summary() {
    [[ -f nn-config.yaml ]] || return
    # 复用 _nn_cfg_load_static 缓存（CFG_*），不再逐项 spawn python
    local _tb _gpus _mp _imp _kmode _kdelta _nba _exp _pl _ri _poll
    _tb="${CFG_TIME_BUDGET:-?}"
    _gpus="${CFG_GPUS:-?}"
    _mp="${CFG_MAX_PARALLEL:-?}"
    _imp="${CFG_KEEP_IMPROVE:-?}"
    _kmode="${CFG_KEEP_MODE:-?}"
    _kdelta="${CFG_KEEP_PRIMARY_DELTA:-?}"
    _nba="${CFG_KEEP_NEAR_BEST_ABS:-?}"
    _exp="${CFG_EXPLORATION:-conservative}"
    _pl="${CFG_PLATEAU_ROUNDS:-?}"
    _ri="${CFG_REFLECT_INTERVAL:-?}"
    _poll="${CFG_POLL_INTERVAL:-300}"
    log "INFO" "nn-config: profile=${NN_CFG_PROFILE} time_budget(yaml)=${_tb} NN_TIME_BUDGET=${NN_TIME_BUDGET} (${NN_TB_SOURCE}) gpus=[${_gpus}] max_parallel=${_mp} keep=${_imp} mode=${_kmode} primary_delta=${_kdelta} near_best_abs=${_nba} exploration=${_exp} plateau_rounds=${_pl} reflect_interval=${_ri} train_poll_interval_sec=${_poll}"
    echo -e "${CYAN}[nn-config]${NC} profile=${NN_CFG_PROFILE}  time_budget(yaml)=${_tb}  →  ${BOLD}NN_TIME_BUDGET=${NN_TIME_BUDGET}s${NC}  (${NN_TB_SOURCE})"
    echo -e "${CYAN}[nn-config]${NC} gpus=[${_gpus}]  max_parallel=${_mp}  keep=${_imp} mode=${_kmode} primary_delta=${_kdelta} near_best_abs=${_nba}"
    echo -e "${CYAN}[nn-config]${NC} exploration=${_exp}  plateau_rounds=${_pl}  reflect_interval=${_ri}"
    echo -e "${CYAN}[nn-config]${NC} train_poll_interval_sec=${_poll}  （后台训练请用 scripts/wait-train.sh，勿高频 grep）"
    if [[ "${_mp}" =~ ^[0-9]+$ && "${_mp}" -gt 1 ]]; then
        echo -e "${CYAN}[nn-config]${NC} 并行：最多 ${_mp} 槽可同时 train.py（是否启用由 Agent 按本轮目标自行判断）"
    fi
}

# Claude stream-json：后台 claude + fifo，供 result watchdog 拿到 pid（防 result 后 hang 不 exit）
_nn_claude_fifo=""
_nn_claude_pid=""
_nn_watchdog_pid=""

_nn_agent_claude_watchdog_stop() {
    if [[ -n "${_nn_watchdog_pid:-}" ]]; then
        kill "$_nn_watchdog_pid" 2>/dev/null || true
        wait "$_nn_watchdog_pid" 2>/dev/null || true
        _nn_watchdog_pid=""
    fi
}

_nn_agent_claude_stream_source_start() {
    _nn_claude_fifo=""
    _nn_claude_pid=""
    _nn_agent_claude_watchdog_stop
    _nn_claude_fifo="$(mktemp -u "${TMPDIR:-/tmp}/nn-claude.XXXXXX")"
    mkfifo "$_nn_claude_fifo"
    _nn_run_claude "${_claude_extra[@]}" "${_claude_stream_fmt[@]}" -p --dangerously-skip-permissions \
        < "$PROMPT_FILE" > "$_nn_claude_fifo" 2>&1 &
    _nn_claude_pid=$!
    local _grace="${NN_AGENT_CLAUDE_RESULT_GRACE_SEC:-60}"
    if [[ "$_grace" =~ ^[0-9]+$ && "$_grace" -gt 0 && -n "${_stream_jsonl:-}" ]]; then
        python3 -u "${SCRIPT_DIR}/scripts/claude_stream_result_watchdog.py" \
            --stream "$_stream_jsonl" \
            --pid "$_nn_claude_pid" \
            --grace-sec "$_grace" \
            --round "$run" >> "$LOG_FILE" 2>&1 &
        _nn_watchdog_pid=$!
        log "INFO" "Claude result watchdog grace=${_grace}s pid=${_nn_claude_pid}（关: NN_AGENT_CLAUDE_RESULT_GRACE_SEC=0）"
    fi
}

_nn_agent_claude_stream_source_finish() {
    if [[ -n "${_nn_claude_pid:-}" ]]; then
        wait "$_nn_claude_pid" 2>/dev/null || true
        _nn_claude_pid=""
    fi
    _nn_agent_claude_watchdog_stop
    if [[ -n "${_nn_claude_fifo:-}" ]]; then
        rm -f "$_nn_claude_fifo"
        _nn_claude_fifo=""
    fi
}

_detect_free_gpus() {
    if [[ -f "${SCRIPT_DIR}/scripts/gpu_snapshot.py" ]]; then
        python3 "${SCRIPT_DIR}/scripts/gpu_snapshot.py" --repo-root "${SCRIPT_DIR}" --format free-csv 2>/dev/null
        return
    fi
    python3 -c "
import subprocess, yaml
try:
    cfg = yaml.safe_load(open('nn-config.yaml'))
except Exception:
    print(''); exit(0)
whitelist = cfg.get('gpus', [])
if whitelist is None or (isinstance(whitelist, list) and len(whitelist) == 0):
    try:
        import torch
        whitelist = list(range(torch.cuda.device_count()))
    except Exception:
        print(''); exit(0)
whitelist = set(whitelist)
if not whitelist:
    print(''); exit(0)
try:
    lines = subprocess.check_output(
        ['nvidia-smi', '--query-gpu=index,memory.used,memory.total,utilization.gpu',
         '--format=csv,noheader,nounits']).decode().strip().split('\n')
except Exception:
    print(''); exit(0)
free = []
for line in lines:
    parts = line.strip().split(', ')
    if len(parts) < 4:
        continue
    idx = int(parts[0])
    if idx not in whitelist:
        continue
    mem_used = int(parts[1])
    mem_total = int(parts[2])
    util = int(parts[3])
    if mem_total > 0 and mem_used / mem_total <= 0.25 and util < 10:
        free.append(idx)
print(','.join(map(str, free)) if free else '')
" 2>/dev/null
}

_capture_gpu_snapshot() {
    _HW_GPU_SNAP_FILE=""
    _HW_GPU_TABLE=""
    if [[ ! -f nn-config.yaml ]] || [[ ! -f "${SCRIPT_DIR}/scripts/gpu_snapshot.py" ]]; then
        _HW_FREE_GPUS="$(_detect_free_gpus)"
        [[ -n "${_HW_FREE_GPUS}" ]] || _HW_FREE_GPUS="unknown"
        return 0
    fi
    _HW_GPU_SNAP_FILE="$(mktemp)" || return 0
    if ! python3 "${SCRIPT_DIR}/scripts/gpu_snapshot.py" --repo-root "${SCRIPT_DIR}" --format json > "$_HW_GPU_SNAP_FILE" 2>/dev/null; then
        rm -f "$_HW_GPU_SNAP_FILE"
        _HW_GPU_SNAP_FILE=""
        _HW_FREE_GPUS="unknown"
        return 0
    fi
    _HW_FREE_GPUS="$(python3 "${SCRIPT_DIR}/scripts/gpu_snapshot.py" --snapshot-file "$_HW_GPU_SNAP_FILE" --format free-csv 2>/dev/null || true)"
    [[ -n "${_HW_FREE_GPUS}" ]] || _HW_FREE_GPUS="unknown"
    _HW_GPU_TABLE="$(python3 "${SCRIPT_DIR}/scripts/gpu_snapshot.py" --snapshot-file "$_HW_GPU_SNAP_FILE" --format md-table 2>/dev/null || true)"
}

_release_gpu_snapshot() {
    if [[ -n "${_HW_GPU_SNAP_FILE:-}" ]]; then
        rm -f "$_HW_GPU_SNAP_FILE"
        _HW_GPU_SNAP_FILE=""
    fi
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
TRAIN_LOG="_runs/logs/run.log"
mkdir -p _runs/logs

_print_usage() {
    echo "Usage: $0 <number_of_runs> [reflect] [options]"
    echo "       $0 reflect [options]"
    echo "       $0 -h | --help | help       show this help and exit"
    echo ""
    echo "Agent options:"
    echo "  --agent auto|claude|cursor   default auto (claude if in PATH, else cursor)"
    echo "  --claude claude|ccg|ccm|ccx|ccmm  Claude/cc-switch frontend (Claude branch only)"
    echo "  --model <name>               Cursor model (Cursor branch only; agent --model)"
    echo ""
    echo "Examples:"
    echo "  $0 20 --claude ccm              # MiniMax via cc-switch"
    echo "  $0 20 --claude=ccmm             # MiniMaxM via cc-switch"
    echo "  $0 20 --claude=ccx              # 小米 via cc-switch"
    echo "  $0 20 --agent cursor            # 强制 Cursor Agent"
    echo "  $0 20 --agent cursor --model sonnet-4-thinking"
    echo "  env NN_AGENT_CLAUDE_CMD=ccg $0 10"
    echo ""
    echo "Env vars & full reference: see the docstring at the top of this script."
}

# ---------------------------------------------------------------------------
# 参数解析（须先于 Agent CLI 检测，以支持 --agent / --claude / --model）
# ---------------------------------------------------------------------------
TOTAL_RUNS=0
REFLECT_ONLY=0
NN_AGENT_BACKEND="${NN_AGENT_BACKEND:-auto}"
NN_AGENT_CLAUDE_CMD="${NN_AGENT_CLAUDE_CMD:-claude}"
NN_AGENT_CURSOR_MODEL="${NN_AGENT_CURSOR_MODEL:-}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        reflect)
            REFLECT_ONLY=1
            shift
            ;;
        --agent)
            if [[ $# -lt 2 ]]; then
                echo "Error: --agent requires auto|claude|cursor" >&2
                exit 1
            fi
            NN_AGENT_BACKEND="$2"
            shift 2
            ;;
        --agent=*)
            NN_AGENT_BACKEND="${1#*=}"
            shift
            ;;
        --claude)
            if [[ $# -lt 2 ]]; then
                echo "Error: --claude requires claude|ccg|ccm|ccx|ccmm" >&2
                exit 1
            fi
            NN_AGENT_CLAUDE_CMD="$2"
            shift 2
            ;;
        --claude=*)
            NN_AGENT_CLAUDE_CMD="${1#*=}"
            shift
            ;;
        --model)
            if [[ $# -lt 2 ]]; then
                echo "Error: --model requires a Cursor model name" >&2
                exit 1
            fi
            NN_AGENT_CURSOR_MODEL="$2"
            shift 2
            ;;
        --model=*)
            NN_AGENT_CURSOR_MODEL="${1#*=}"
            shift
            ;;
        [0-9]*)
            TOTAL_RUNS=$(( $1 + 0 ))
            shift
            ;;
        -h|--help|help)
            _print_usage
            exit 0
            ;;
        *)
            echo "Error: unknown argument: $1" >&2
            exit 1
            ;;
    esac
done

_nn_validate_agent_cli_args() {
    case "${NN_AGENT_BACKEND}" in
        auto|claude|cursor) ;;
        *)
            echo "Error: --agent must be auto|claude|cursor (got: ${NN_AGENT_BACKEND})" >&2
            exit 1
            ;;
    esac
    case "${NN_AGENT_CLAUDE_CMD}" in
        claude|ccg|ccm|ccx|ccmm) ;;
        *)
            echo "Error: --claude must be claude|ccg|ccm|ccx|ccmm (got: ${NN_AGENT_CLAUDE_CMD})" >&2
            exit 1
            ;;
    esac
    if [[ "${NN_AGENT_CLAUDE_CMD}" != "claude" ]] && ! command -v cc-switch >/dev/null 2>&1; then
        echo "Error: ${NN_AGENT_CLAUDE_CMD} requires cc-switch in PATH" >&2
        exit 1
    fi
    if [[ -n "${NN_AGENT_CURSOR_MODEL}" && "${NN_AGENT_BACKEND}" == "claude" ]]; then
        echo "Error: --model is only valid with --agent cursor (or auto when Cursor is selected)" >&2
        exit 1
    fi
}
_nn_validate_agent_cli_args
export NN_AGENT_CLAUDE_CMD
export NN_AGENT_CURSOR_MODEL

if [[ "$REFLECT_ONLY" == "0" && "$TOTAL_RUNS" == "0" ]]; then
    _print_usage
    exit 1
fi

if [[ "$REFLECT_ONLY" == "1" ]]; then
    TOTAL_RUNS=1
fi

# 契约墙钟：export 给子进程（含 claude 内 poetry run python train.py）。见 experiment.py _resolve_time_budget / ExperimentBase.time_budget。
# 冻结派生量：唯一真值 nn-config.yaml time_budget（无则 3600）；预 export 与 yaml 不一致 → 拒启 + 记违约日志
_nn_cfg_resolve_time_budget

# GPU 选择：先透传已有 CUDA_VISIBLE_DEVICES / NN_GPU_DEVICE，再按 ~/.gpus 收紧
if [[ ! -v CUDA_VISIBLE_DEVICES && -v NN_GPU_DEVICE ]]; then
    export CUDA_VISIBLE_DEVICES="$NN_GPU_DEVICE"
fi
if [[ -v CUDA_VISIBLE_DEVICES ]]; then
    export CUDA_VISIBLE_DEVICES
fi
if [[ -f "${SCRIPT_DIR}/scripts/lib/home_gpus.py" ]]; then
    _nn_home_gpus_err="$(mktemp)"
    set +e
    _nn_home_gpus_line="$(PYTHONPATH="${SCRIPT_DIR}/scripts${PYTHONPATH:+:$PYTHONPATH}" python3 \
        "${SCRIPT_DIR}/scripts/lib/home_gpus.py" --shell-export 2>"$_nn_home_gpus_err")"
    _nn_home_gpus_rc=$?
    set -e
    if [[ $_nn_home_gpus_rc -ne 0 ]]; then
        echo "Error: 家目录显卡名单（~/.gpus）: $(cat "${_nn_home_gpus_err}" 2>/dev/null || true)" >&2
        rm -f "${_nn_home_gpus_err}"
        exit 1
    fi
    rm -f "${_nn_home_gpus_err}"
    _nn_home_gpus_line="${_nn_home_gpus_line//$'\n'/}"
    if [[ -n "${_nn_home_gpus_line}" ]]; then
        eval "${_nn_home_gpus_line}"
        export CUDA_VISIBLE_DEVICES
        log "INFO" "家目录显卡名单已收紧：${CUDA_VISIBLE_DEVICES}"
    fi
fi

# 立项/迁移轮：允许 Agent 改 contract/，preflight G2 不警告
if [[ -v NN_RELAUNCH && -n "$NN_RELAUNCH" ]]; then
    export NN_RELAUNCH
fi

# 迁后全量训练：显式关 smoke（train.py 默认已 0；避免 shell 遗留 NN_SMOKE=1）
export NN_SMOKE=0

_nn_cc_switch() {
    if [[ -n "${NN_CC_SWITCH_HOME:-}" ]]; then
        HOME="${NN_CC_SWITCH_HOME}" command cc-switch "$@"
    else
        command cc-switch "$@"
    fi
}

_nn_claude_provider() {
    case "$1" in
        ccg) echo zhipu-glm ;;
        ccm) echo minimax ;;
        ccmm) echo minimaxM ;;
        ccx) echo xiaomi ;;
    esac
}

_nn_run_claude() {
    local _claude_bin
    _claude_bin="$(command -v claude 2>/dev/null || true)"
    if [[ -z "$_claude_bin" ]]; then
        echo "Error: claude CLI not found in PATH" >&2
        return 1
    fi
    case "${NN_AGENT_CLAUDE_CMD}" in
        claude)
            stdbuf -oL -eL "$_claude_bin" "$@"
            ;;
        ccg|ccm|ccx|ccmm)
            # stdbuf 只能 exec 外部可执行文件，不能调用 shell 函数/内建 command
            local _provider _ccsw _home_real
            _ccsw="$(command -v cc-switch 2>/dev/null || true)"
            if [[ -z "$_ccsw" ]]; then
                echo "Error: cc-switch not found (required for ${NN_AGENT_CLAUDE_CMD})" >&2
                return 1
            fi
            _provider="$(_nn_claude_provider "${NN_AGENT_CLAUDE_CMD}")"
            _home_real="$(readlink -f "${NN_CC_SWITCH_HOME:-$HOME}")"
            stdbuf -oL -eL env HOME="$_home_real" "$_ccsw" start claude "$_provider" -- "$_claude_bin" "$@"
            ;;
        *)
            echo "Error: invalid NN_AGENT_CLAUDE_CMD=${NN_AGENT_CLAUDE_CMD}" >&2
            return 1
            ;;
    esac
}

# ---------------------------------------------------------------------------
# Agent CLI：--agent 指定；默认 auto = claude 优先，cursor 兜底
# ---------------------------------------------------------------------------
AGENT_TYPE=""
AGENT_NAME=""
case "${NN_AGENT_BACKEND}" in
    auto)
        if command -v claude >/dev/null 2>&1; then
            AGENT_TYPE="claude"
            AGENT_NAME="Claude"
        elif command -v agent >/dev/null 2>&1; then
            AGENT_TYPE="cursor"
            AGENT_NAME="Cursor"
        else
            echo "Error: neither 'agent' (Cursor) nor 'claude' CLI found."
            echo "Install Cursor: curl https://cursor.com/install -fsS | bash"
            echo "Install Claude: https://docs.anthropic.com/en/docs/claude-code"
            exit 1
        fi
        ;;
    claude)
        if ! command -v claude >/dev/null 2>&1; then
            echo "Error: --agent claude requires 'claude' CLI in PATH" >&2
            exit 1
        fi
        AGENT_TYPE="claude"
        AGENT_NAME="Claude"
        ;;
    cursor)
        if ! command -v agent >/dev/null 2>&1; then
            echo "Error: --agent cursor requires 'agent' (Cursor CLI) in PATH" >&2
            exit 1
        fi
        AGENT_TYPE="cursor"
        AGENT_NAME="Cursor"
        ;;
esac
if [[ "$AGENT_TYPE" == "claude" && "${NN_AGENT_CLAUDE_CMD}" != "claude" ]]; then
    AGENT_NAME="Claude (${NN_AGENT_CLAUDE_CMD})"
elif [[ "$AGENT_TYPE" == "cursor" && "${NN_AGENT_CLAUDE_CMD}" != "claude" ]]; then
    log "WARNING" "--claude ${NN_AGENT_CLAUDE_CMD} ignored (using Cursor agent)"
    NN_AGENT_CLAUDE_CMD=claude
    export NN_AGENT_CLAUDE_CMD
fi
if [[ "$AGENT_TYPE" == "cursor" && -n "${NN_AGENT_CURSOR_MODEL}" ]]; then
    AGENT_NAME="Cursor (${NN_AGENT_CURSOR_MODEL})"
fi
echo "[auto-nn-run.sh] Using agent: ${AGENT_NAME} (${AGENT_TYPE})"
if [[ "$AGENT_TYPE" == "claude" ]]; then
    _nn_claude_bin="$(command -v claude 2>/dev/null || true)"
    if [[ -n "$_nn_claude_bin" ]]; then
        export NN_CLAUDE_BIN="$_nn_claude_bin"
    else
        unset NN_CLAUDE_BIN
    fi
fi

_nn_tb_wall_sec=$(( NN_TIME_BUDGET * 8 / 10 ))
_nn_tb_h=$(( NN_TIME_BUDGET / 3600 ))
_nn_tb_m=$(( (NN_TIME_BUDGET % 3600) / 60 ))
_nn_wh=$(( _nn_tb_wall_sec / 3600 ))
_nn_wm=$(( (_nn_tb_wall_sec % 3600) / 60 ))

if [[ "${NN_TIME_BUDGET}" == "0" ]]; then
    echo ""
    echo -e "${YELLOW}${BOLD}╔══════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}${BOLD}║  【训练墙钟】已关闭  NN_TIME_BUDGET=0                                ║${NC}"
    echo -e "${YELLOW}${BOLD}║  0=不限单次 train 墙钟；若未在 yaml 写 0，默认会是 3600s（1 小时）     ║${NC}"
    echo -e "${YELLOW}${BOLD}╚══════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    log "WARNING" "训练墙钟 NN_TIME_BUDGET=0（已关闭）"
else
    echo ""
    echo -e "${YELLOW}${BOLD}╔══════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}${BOLD}║  【训练墙钟】默认已开启（契约 TimeGuard → train.py）                  ║${NC}"
    echo -e "${YELLOW}${BOLD}║  NN_TIME_BUDGET=${NN_TIME_BUDGET}s  ≈ ${_nn_tb_h}h${_nn_tb_m}m  总预算 wall clock              ║${NC}"
    echo -e "${YELLOW}${BOLD}║  约在 ${_nn_tb_wall_sec}s（≈${_nn_wh}h${_nn_wm}m）处到达 80% 阈值，于 epoch 边界停止训练      ║${NC}"
    echo -e "${YELLOW}${BOLD}║  来源: ${NN_TB_SOURCE}                                              ║${NC}"
    echo -e "${YELLOW}${BOLD}║  改时长: 停 batch 后改 nn-config time_budget（会话内 export 一律拒启） ║${NC}"
    echo -e "${YELLOW}${BOLD}╚══════════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    log "WARNING" "训练墙钟已启用 NN_TIME_BUDGET=${NN_TIME_BUDGET}s（约 80% 时 epoch 边界停训）"
fi

echo ""
echo "========================================"
echo "  auto-nn-agent workflow (${AGENT_NAME}) — ${TOTAL_RUNS} run(s)"
if [[ "$REFLECT_ONLY" == "1" ]]; then
    echo "  *** REFLECTION ONLY (reflect.py) ***"
fi
echo "========================================"
echo ""

# === external-keys banner (D2) ===
# 启动时一次性检查 4 个外部 key（SERPER/OPENAI/GITHUB_TOKEN/ANTHROPIC）,
# 缺则 stderr WARN,不阻断 batch。NN_SKIP_KEYCHECK=1 静默跳过。
if [[ "${NN_SKIP_KEYCHECK:-0}" != "1" ]] && [[ -f "${SCRIPT_DIR}/scripts/check-external-keys.py" ]]; then
    python3 "${SCRIPT_DIR}/scripts/check-external-keys.py" --repo-root "${SCRIPT_DIR}" 2>&1 || true
fi
# === end D2 banner ===

log "INFO" "Starting ${TOTAL_RUNS} run(s); agent=${AGENT_NAME}; master log: ${LOG_FILE}"
ROWS_START=$(count_result_rows)
log "INFO" "_runs/results.tsv data rows at start: ${ROWS_START}"

mkdir -p saved
date +%s > saved/.batch_start_epoch

# governance-rev 漂移：long batch 前须 auto-nn-update
if [[ "$REFLECT_ONLY" != "1" ]] && [[ -f scripts/lib/nn-state.sh ]] && [[ -f scripts/lib/governance-rev.sh ]]; then
    # shellcheck source=scripts/lib/nn-state.sh
    source scripts/lib/nn-state.sh
    _gov_troot="$(nn_resolve_template_root "${SCRIPT_DIR}" 2>/dev/null || true)"
    if [[ -n "$_gov_troot" ]] && [[ -f "$_gov_troot/template/package/profiles.yaml" ]]; then
        # shellcheck source=scripts/lib/governance-rev.sh
        source scripts/lib/governance-rev.sh
        _gov_exp="$(governance_rev_compute "$_gov_troot/template/package")"
        _gov_act="$(tr -d '\r\n' < .auto-nn/governance-rev 2>/dev/null || true)"
        if [[ "$_gov_act" != "$_gov_exp" ]]; then
            log "WARNING" "governance_drift: rev got=${_gov_act:-<missing>} want=${_gov_exp} — 请先 bash scripts/auto-nn-update.sh --pull-template"
            if [[ "${NN_AUTO_RUN_REQUIRE_GOV_SYNC:-0}" == "1" ]]; then
                log "ERROR" "NN_AUTO_RUN_REQUIRE_GOV_SYNC=1 — 终止 batch"
                exit 1
            fi
        fi
    fi
    unset _gov_troot _gov_exp _gov_act
fi

# HUMAN 批次基线（reflect-only 不写；实验 batch 启动时锁定 sha256 + batch pid）
if [[ "$REFLECT_ONLY" != "1" ]]; then
    _write_human_guidance_baseline
    export NN_AUTO_RUN_ACTIVE=1
    mkdir -p saved
    printf '%s\n' "$$" > saved/.auto-run-active.pid
    trap '_cleanup_auto_run_active' EXIT
fi

# ---------------------------------------------------------------------------
# 文件完整性检查
# ---------------------------------------------------------------------------
for need in CLAUDE.md PROTOCOL.md profiles.yaml nn-config.yaml experiment.py contract/__init__.py workspace/__init__.py train.py \
           reflect.py scripts/wait-train.sh scripts/claude_stream_summarize.py scripts/claude_stream_result_watchdog.py scripts/auto-run-batch-tail.sh; do
    if [ ! -f "$need" ]; then
        log "ERROR" "Missing required file: $need"
        exit 1
    fi
done

# nn-config 静态键一次性读入 CFG_*（批次内不变；循环里复用，勿每轮 spawn python）
_nn_cfg_load_static
NN_CFG_PROFILE="${CFG_PROFILE}"
log "INFO" "profile=${NN_CFG_PROFILE}  NN_RELAUNCH=${NN_RELAUNCH:-(unset)}"
echo -e "${CYAN}profile${NC} ${NN_CFG_PROFILE}    ${CYAN}NN_RELAUNCH${NC} ${NN_RELAUNCH:-(unset)}"
_print_nn_config_summary

# 批次内不变量：循环前算一次（contract metric / torch / poetry python 不随轮变；省去每轮 poetry run）
_CACHED_METRIC_KEY=""
_CACHED_ENV_SNAPSHOT=""
if [[ "$REFLECT_ONLY" != "1" ]]; then
    _CACHED_METRIC_KEY="$(contract_metric_key)"
    if [[ -f scripts/check-env.sh ]]; then
        bash scripts/check-env.sh || exit 1
        _CACHED_ENV_SNAPSHOT="$(bash scripts/check-env.sh --snapshot 2>/dev/null || true)"
    else
        _CACHED_ENV_SNAPSHOT="$(
            echo "python3_system: $(command -v python3)"
            if command -v poetry >/dev/null 2>&1; then
                echo "poetry_python: $(poetry run which python 2>/dev/null || echo n/a)"
                poetry run python - <<'PY'
import torch
print(f"torch: {torch.__version__}")
print(f"cuda_available: {torch.cuda.is_available()}")
print(f"torch_cuda: {torch.version.cuda}")
if torch.cuda.is_available():
    print(f"gpu_name: {torch.cuda.get_device_name(0)}")
PY
            else
                echo "WARNING: poetry 未找到，跳过 torch 快照"
            fi
        )"
    fi
fi

# ---------------------------------------------------------------------------
# 主循环
# ---------------------------------------------------------------------------
BATCH_REFLECT_ACK_MISSING=0
BATCH_JOURNAL_UNCOMMITTED_WARNS=0
# AE-2 batch 早退根治：禁用 set -e 在 round 体内的传播。
# 原 bug：`auto-nn-run.sh N` (N>1) 跑 1 轮后退出；推测根因是 claude 退出时
# 关闭 stdio + pipefail 触发 set -e 退出。当前 round 失败不应导致 batch 整体早退
# —— batch 应该继续下一轮并累计 SUCCESS / WARNING。
_round_failed=0
set +e  # batch 循环体内禁用 set -e（每轮错误累计 _round_failed，循环结束后再决定 exit code）
for ((run=1; run<=TOTAL_RUNS; run++)); do
    echo ""
    echo "========================================"
    log "PROGRESS" "Run $run of $TOTAL_RUNS"
    echo "========================================"

    RUN_START=$(date +%s)
    AGENT_ROUND_LOG="$LOG_DIR/$(date +%Y%m%d_%H%M%S)_agent-round-${run}.log"
    log "INFO" "Agent round log: $AGENT_ROUND_LOG"

    # 仅反思：直接 reflect.py（Path B 已废弃；与 reflect.py 同路径）
    if [[ "$REFLECT_ONLY" == "1" ]]; then
        REFLECT_LOG="$LOG_DIR/$(date +%Y%m%d_%H%M%S)_reflect-only.log"
        {
            echo "=== Reflect-only @ $(date '+%Y-%m-%d %H:%M:%S') ==="
            echo "agent_type: ${AGENT_TYPE}"
            echo "mode: reflect.py (no experiment agent)"
        } > "$REFLECT_LOG"
        _ref_start=$(date +%s)
        echo "[reflect-only] calling reflect.py agent=${AGENT_TYPE}..." >&2
        if poetry run python reflect.py --agent "$AGENT_TYPE" >> "$REFLECT_LOG" 2>&1; then
            log "SUCCESS" "Reflect-only finished in $(($(date +%s) - _ref_start))s (see $(basename "$REFLECT_LOG"))"
            tee -a "$AGENT_ROUND_LOG" < "$REFLECT_LOG" >/dev/null
        else
            log "WARNING" "reflect.py reflect-only failed (see $(basename "$REFLECT_LOG"))"
            tee -a "$AGENT_ROUND_LOG" < "$REFLECT_LOG" >/dev/null
        fi
        unset _ref_start
        continue
    fi

    # Hardware context（静态值取自 CFG_* 缓存；GPU 三档快照每轮实时探测）
    _HW_GPUS="${CFG_GPUS}"
    _HW_FREE_GPUS=""
    _HW_GPU_SNAP_FILE=""
    _HW_GPU_TABLE=""
    _HW_MAX_PARALLEL="${CFG_MAX_PARALLEL:-1}"
    _EXPLORATION="${CFG_EXPLORATION:-conservative}"
    _POLL_INTERVAL="${CFG_POLL_INTERVAL:-300}"
    _SCENARIO_POLICY="${CFG_SCENARIO_POLICY}"
    _SCENARIO_DEFAULT="${CFG_SCENARIO_DEFAULT}"
    _SCENARIO_ACTIVE="${CFG_SCENARIO_ACTIVE}"
    if [[ -f nn-config.yaml ]]; then
        _capture_gpu_snapshot
    fi
    [[ -n "${_SCENARIO_POLICY}" ]] || _SCENARIO_POLICY="see README"
    [[ -n "${_SCENARIO_DEFAULT}" ]] || _SCENARIO_DEFAULT="see README"
    [[ -n "${_SCENARIO_ACTIVE}" ]] || _SCENARIO_ACTIVE="see README"
    if [[ -n "${NN_TRAIN_POLL_INTERVAL_SEC:-}" ]]; then
        _POLL_INTERVAL="${NN_TRAIN_POLL_INTERVAL_SEC}"
    fi

    # 环境快照 + prompt
    {
        echo "=== Run $run of $TOTAL_RUNS @ $(date '+%Y-%m-%d %H:%M:%S') ==="
        echo "_runs/results.tsv rows before: $(count_result_rows)"
        echo "agent_type: ${AGENT_TYPE}"
        echo ""
        echo "--- Environment snapshot ---"
        echo "cwd: $(pwd)"
        echo "git_head: $(git rev-parse --short HEAD 2>/dev/null || echo none)"
        echo "NN_TIME_BUDGET=${NN_TIME_BUDGET} (${NN_TB_SOURCE})"
        if [[ -f nn-config.yaml ]]; then
            echo "nn-config.yaml profile=${NN_CFG_PROFILE} time_budget=${CFG_TIME_BUDGET:-?} gpus=${CFG_GPUS:-?} max_parallel=${CFG_MAX_PARALLEL:-?} keep.improve_mode=${CFG_KEEP_IMPROVE:-?} keep.near_best_abs=${CFG_KEEP_NEAR_BEST_ABS:-?} exploration=${CFG_EXPLORATION:-conservative} plateau_rounds=${CFG_PLATEAU_ROUNDS:-?} train_poll_interval_sec=${_POLL_INTERVAL}"
        fi
        # python3/poetry/torch 快照批次内不变：用循环前缓存（省每轮 poetry run）
        printf '%s\n' "$_CACHED_ENV_SNAPSHOT"
        echo "run_context: saved/run_context.md"
        echo ""
        echo "--- Agent output ---"
    } > "$AGENT_ROUND_LOG"

    PROMPT_FILE=$(mktemp) || { log "ERROR" "mktemp 失败，无法创建 prompt 临时文件"; exit 1; }

    # 标准实验 prompt（ExperimentBase）
    cat > "$PROMPT_FILE" << 'PROMPT_EOF'
You are in an auto-nn-experiment repository. The core architecture is:
- experiment.py: ExperimentBase base class with ALL framework methods (TimeGuard, preflight, finalize, checkpoints, ledgers). DO NOT modify.
- contract/__init__.py: Contract(ExperimentBase) — metric_key / metric_direction / keep_threshold / aux_metrics / prepare_data / test / should_keep (IMMUTABLE during regular iterations; only modify when NN_RELAUNCH=1 is set by the human for a re-launch / migration round).
- workspace/__init__.py: Workspace(ExperimentBase) — build_learner / build_objective / train_step / predict / evaluate (mutable each iteration); may organise submodules under workspace/.
- train.py: orchestration via `contract` and `ws` (workspace) objects + a `shared_context` dict. MUST only call `ws.<method>` / `contract.<method>`; MUST NOT `from workspace.<submodule> import ...` (preflight G1 will fail).

Profile and task definition: read `nn-config.yaml` (profile field) and `profiles.yaml` for method ownership; read `contract/__init__.py` for the actual metric / data definition. Do not assume a specific dataset.

**Preflight 守门（每次 train 自动跑，先于 loss 验证）：**
- G1 — train.py 不得 `from workspace.<子模块> import`：违规则 RuntimeError（失败）。
- G2 — contract/ 或 experiment.py 相对 HEAD~1 有改动：仅在 NN_RELAUNCH 未设置时打印警告。
- G3 — nn-config.yaml 的 profile 与 profiles.yaml 方法清单不一致：警告（不阻断）。
- G4 — 仓库根目录出现非白名单 .py（白名单：train.py / experiment.py / reflect.py）：警告。
  探路 / 临时脚本只放 `workspace/scripts/`（见该目录 README）。

**Tier 梯子**（权威：`EXPERIENCE.md` §Tier A–E + **Tier 状态**表 + PROTOCOL §7.5.1）：
- A=标量日程；B=表示容量；C=**优化目标**（改 workspace loss/reward/正则）；D=**数据分布**（课程/采样逻辑，非仅一个 ratio）；E=**改题/评估**（非算力、非更长训练）
- **B vs E**：任务不变换 backbone/算子 = **B**；改 contract 主指标/official test/KEEP = **E**（须人设 `NN_RELAUNCH`）。文献 **禁止**默认 E；见 EXPERIENCE「B vs E」「E 闸门」
- **tier_this_round** 与路径一致（model→B，loss→C，contract→E）；**常规轮不得为 E**，不得改 `contract/`；撞墙 ≠ E
- plateau 后 C 穷尽可升 **B**（未试），不必等到 E
- **假升档**：experiment 名含 TierC 但只改 `NN_*` 或 `train.py` 常量 → EXPERIENCE `## Tier 状态`（二维矩阵）记「假升档」，不得声称已试 C/D-深
- 每轮 EXPERIENCE 必填：`tier_this_round` / `tier_change`（代码路径）/ `tier_verdict` + `innovation_depth` + `innovation_rationale`；并更新 `## Tier 状态` **二维矩阵**对应格子

**探索策略**（`exploration_mode`=<EXPLORATION>；起手格子见 `resolve_exploration().tier_start`，由 mode preset 派生；撞墙见 `agent.plateau_rounds` + 具体格子升档）：
- careful→A；optimize/explore/auto 起步→B；innovate→C；aggressive→D（以当前模板 presets 为准）
- 连续 plateau 且当前**具体格子**（如 B-routine）在 EXPERIENCE `## Tier 状态`（二维矩阵）标「已穷尽」→ 考虑同档下一深度或升到下一「未试」格。**仅当**「当前格子已穷尽 ∧ 已 plateau」时，禁止再对该格子做**同变量多幅度 grid 扫描**；**独立单变量候选的并行探索、以及未穷尽格子的 HPO sweep 不受此限**（见 step 4）
- **起步尺子**：开局检索台账当前场景是否已有 `baseline_tag=plain`。有 → 禁止再写 plain，扫参/衍生必须 `none`。无 → 可做至多 1 轮 plain（写 tag=plain + EXPERIENCE P 行）。前 10 轮**禁止**自动设 `baseline_tag=reference`；满 10 轮仍无则跟 `### reference-anchor-init` 立公开对照（中点代用可自动贴；文献尺须本机原仓校准过线）。`--from-template` 未显式 `--set baseline_tag=…` 时标签为 none。

**撞墙分析**（连续 3+ 轮无改善时，先读 EXPERIENCE `## Tier 状态`（二维矩阵）再行动）：
- 回顾 `_runs/results.tsv`；勿写「未尝试 Tier X」若对应格子已标已试/浅尝/已穷尽
- 可用 WebSearch；文献方案映射到 B/C/D 并写明 workspace 路径，**不是** Tier E（除非改 contract）
- **范式锁死（要求1）**：scenario_id 一旦选定范式（supervised/RL/physical），骨架/loader/dispatcher 即锁死，agent **不得**自行切换。若 R8 范式撞墙信号命中（`_runs/round_decision.json` 的 `paradigm_fit: MISMATCH`，或 reflect_gate 返回 `run:R8:paradigm_mismatch`）→ 本轮 EXPERIENCE 标 `paradigm_fit: MISMATCH`，reflect 中**可建议** E 档任务级变更并标 `e_subtype: contract`（换 test/metric/契约）或 `e_subtype: paradigm`（换范式，如 sup→RL）；**执行切换须 human 开新 init（新 scenario_id）**，agent 仅产出信号 + 建议，不自决切。

**批内迭代默认（人话；HUMAN NOTE 更高；无程序 stage 标签）：**
- 已有 keeper 且 RUN CONTEXT 中 plateau_streak 接近阈值：优先 seed 稳健性 / A 档单键微扰。**careful/optimize**：**默认**不启新 backbone 满 budget。**innovate/aggressive**：不受该默认约束——可/应注册新 backbone 或新结构（可用短探针；HUMAN NOTE 要求满 budget 则满 budget）。
- RUN CONTEXT「recent ledger window」中 last_row_vs_leader 明显为负：**默认**不 full-budget 重试同一机制组合；可短探针或换单键。
- 新 loss / KD / 复杂 schedule：**默认**短探针，除非 HUMAN NOTE 明确要求满 budget。

Follow CLAUDE.md and PROTOCOL.md exactly.

Complete ONE experiment iteration (PROTOCOL §6):
0. **Read `HUMAN_GUIDANCE.md`** — 若有「公平约束」注入块：比较口径全程遵守（与阶段无关）。若有 ROADMAP 注入块：对照 **inferred_phase** 只守该阶段 NOTE；空路线图则阶段全自主（仍守公平约束若有）。
0b. If REFLECT PENDING block above is present (or `references/REFLECT_INDEX.md` has a pending row): **Read `references/REFLECT_INDEX.md`** and design this round per **下轮建议** (lower priority than HUMAN_GUIDANCE roadmap). In EXPERIENCE.md this round, include a line **`reflect_ack:`** stating adopt / defer / conflict with roadmap. If the pending row carries a `[升级建议] … register→fork` line (fork 触发): Read the named cell in `references/manual/abcde-manual.md`, then edit **only that cell** from `register` to `fork` (cell-level, one-way, single dimension — no downgrade, no other cells). This is the **only** permitted edit to `references/manual/abcde-manual.md`. **Gate:** 有 pending 时 `reflect_ack:` 为轮末 consumed 程序门禁；缺失则 pending 留待下轮（不会自动归档）。
0c. Read README: `<!-- D2_DATA_SPLIT -->` … `<!-- /D2_DATA_SPLIT -->` (incl. SCENARIO_CANDIDATES if present), optional `<!-- SCENARIO_POLICY -->` / `<!-- AGENT_BOUNDARY -->`, and "Hard Constraints" if present. If F1 or README lists a scenario inventory table, do not KEEP-compare across rows with different S_data or different frozen S_run defaults. If EXPERIENCE.md has section "场景与 KEEP 约定", follow the `下一轮计划` column for this round (scenario id, env naming, experiment prefix). Scenario policy/default/active 见下方 **Agent scenario manifest** 注入块（结构化；单一真源）。

[step 0c 末尾] plain 标签检索（auto）:
  1. 读 `_runs/results.tsv`：当前场景是否已有 baseline_tag=plain
  2. 有 → 本轮禁止 baseline_tag=plain；普通实验用 none
  3. 无 → 若 RUN CONTEXT 含 ### plain-anchor-init：可做 1 轮 plain（baseline_tag=plain），写 plain_anchor_value 到 EXPERIENCE Tier P 行
  4. 前 10 轮禁止自动 baseline_tag=reference；满 10 轮仍无则本轮必做公开对照（跟 reference-anchor-init）
0d. **RUN CONTEXT** block is injected above ( **batch** batch_run/N + remaining + max_parallel/free_gpus for slot allocation; summarize-runs brief, keeper-status, MA-1 brief-oneline, journal tail, env, round_decision). Design this round using **batch_run**, **metric_leader / code_baseline / plateau** from that block; do **not** treat jsonl last row or keeper alone as SOTA. Still Read `_runs/results.tsv` / EXPERIENCE for deep context; on conflict with stale manual reads, trust the injected snapshot. If present, use `recent ledger window` `delta_vs_leader` / `summary` for near-term facts (not a stage label).
1. Read `_runs/results.tsv`, `saved/experiment_journal.json` (if present), EXPERIENCE.md, contract/__init__.py, workspace/__init__.py, and `_runs/round_decision.json` if present (repo-level; per-slot runs have `_runs/exp/<run_dir>/keep_suggestion.json` before aggregation). The injected RUN CONTEXT already summarizes ledger state — use it before deep reads.
2. Edit boundary（两态）: (a) **可改** — `config.json` 实验参数（LR/EPOCHS/SEED/`scenario_id` 等）via `scripts/modify-config.py` or writing config；以及 `train.py` / `workspace/` 实现（须遵守 PROTOCOL §0.1 改码三原则：config-only / no-fallback / pluggable）。Keep implementation under workspace/; place exploratory scripts in `workspace/scripts/`. (b) **禁改** — `experiment.py`、手改 `_runs/results.tsv`/`results.jsonl`、改 `HUMAN_GUIDANCE.md` / `references/REFLECT_INDEX.md` / `PROTOCOL.md` / `nn-config.yaml`（ledger 段除外）、常规轮改 `contract/`（无 `NN_RELAUNCH`）。若需要改禁区：停止该项，用人话说明需人类改题面/口径；**勿**调用改能力斜杠技能。常规迭代 **不要** 无 `NN_RELAUNCH` 直接改 `contract/`。**Exception (fork 触发):** when a `[升级建议] register→fork` row is pending in `references/REFLECT_INDEX.md`, you may edit **only the named cell** of `references/manual/abcde-manual.md` from `register` to `fork` (cell-level, one-way).
3. git commit (one experiment per iteration). EXPERIENCE.md MUST be part of this commit.
3a-slot-plan（开槽前必写，3 行；与下方 3a OVAT 枚举并列）：
1. anchor: 本轮起点 config（keeper / metric_leader 的 exp_dir 或 config 键摘要）
2. slot_variables: 每槽恰好一个变更键（OVAT）
3. risk_check: 对照 RUN CONTEXT plateau 与 recent ledger window；新 loss/KD 默认短探针，除非 HUMAN NOTE 要求满 budget
4. **Training + slots** — **OVAT ≠ 串行**：OVAT = *每槽改一个变量*（可归因），多个**独立**单变量候选应并行探索，不是「一次只跑一次」。并行默认规则 + slot↔GPU 映射见文末 Hardware / 并行能力段。
   - **3a. 枚举本轮独立 OVAT 候选**（翻转默认的支点，每轮必做）：列出本轮可独立探索的单变量候选，每条一句独立性说明（互不为对方设计前提、无共享混淆变量）。正例：不同变量 / 不同 scenario / 不同 seed；反例：同变量多幅度 grid 在「已穷尽档∧plateau」（见上文 Tier 规则）。
   - **3b. 默认并行**：`枚举出 ≥2 独立候选 ∧ max_parallel ≥ 2` → 并行 `min(max_parallel, 候选数)` 槽；**串行（单槽）须说明理由**（候选有依赖 / C-D 深单变量 / 结构大改 / E 预研 / max_parallel=1）。**slot 与 GPU 解耦**：是否并行只看 `max_parallel` 与候选数，**与物理 GPU 数无关**——单卡机器多 slot 共享同卡，天然支持。
   - 目录名 `s0of1` = 单槽，`s0of4`…`s3of4` = 多 slot 并行。**具体格子**是否穷尽以 EXPERIENCE `## Tier 状态` 二维矩阵为准（并行批次任一槽 KEEP 会重置 plateau 计数，勿只看 plateau）。
   - **单槽**（单组超参、C/D-深单变量、结构大改、需专注对比时）: `mkdir -p _runs/logs && CUDA_VISIBLE_DEVICES=X setsid poetry run python train.py > _runs/logs/run.log 2>&1 < /dev/null &`（`setsid` 让 train.py 脱离 agent bash session —— Ctrl+C / SIGTERM 不会通过 SIGHUP 牵连到训练;详见 step 4 注释）。默认训末自动 `finalize_round`（写 `_runs/round_decision.json`、追加 TSV/jsonl）；**勿**再跑 `finalize-round`（同 exp_dir 二次 finalize 会跳过已入账行（幂等），仍应避免无谓重复）。更多试跑日志用 `_runs/logs/<short>.log`，**勿**在仓库根写 `run.log` / `run2.log`。
   - **多 slot 并行**（`≥2 独立候选 ∧ max_parallel≥2` 时**默认**；候选可为不同架构（Tier B）/不同 loss·正则（Tier C）/不同场景（scenario）/种子稳健性多跑，也含未穷尽档的 A·B HPO sweep。**每槽仍须是干净的单变量实验**；仅「已穷尽档∧plateau」禁同变量 grid，独立单变量并行不受限）: 同时起 `min(max_parallel, 候选数)` 个 `train.py`，各进程**相同** `NN_PARALLEL_TOTAL=N`、**不同** `NN_SLOT`（0..N-1），超参用各自 config/`NN_*` 区分。**slot→GPU 映射**：`free_gpus ≥ N` → 各槽不同 `CUDA_VISIBLE_DEVICES`（分散）；`free_gpus < N` → 多槽共享同卡（多个槽设同一 `CUDA_VISIBLE_DEVICES`，受显存约束，勿超额）。示例（4 槽分散 4 卡）: `(CUDA_VISIBLE_DEVICES=0 NN_SLOT=0 NN_PARALLEL_TOTAL=4 setsid poetry run python train.py > _runs/logs/run_slot0.log 2>&1 < /dev/null &) ; …` … 全部 slot 训完（且无 fail）后由 `wait-train.sh` 训末**自动** `finalize-round`（见 step 5）；agent 常规轮无需再手动跑。同 exp_dir 二次 finalize 幂等跳过、避免无谓重复；仅当 wait-train 报 auto-finalize WARN 才手动 `poetry run python -m contract finalize-round <dirs> --repo-root .` 补账。汇总后 jsonl/TSV 须含**全部**候选 `exp_dir`（不论 keeper 与否、分数好坏均各一行）；**1 行 = 1 次实验（槽位）**，不是 1 轮编排。
4b. **Build metadata 检查**（训后必查）— `train.py` 每个 `ws.build_*` 调用会在 stderr 打印 `[build_learner]` / `[build_objective]` / `[build_optimizer]` / `[build_scheduler]` / `[build_transforms]` 行，显示 workspace 实际解析的参数（如被 scenario_id 覆盖的模型名、调整后的 LR 等）。这些值已写入 `exp_dir/config.json`。训后执行 `grep '\[build_' _runs/logs/run.log` 或读 config.json 验证：实际值与意图一致则继续；若出现意外覆盖（如模型架构非预期），在 EXPERIENCE 记录并检查 workspace `build_*` 方法。
5. **训练等待（后台起训后）** — **必须且仅能**调用一次 `./scripts/wait-train.sh`（间隔 **<POLL_INTERVAL>** 秒，来自 `nn-config.yaml` → `agent.train_poll_interval_sec`；可用 `NN_TRAIN_POLL_INTERVAL_SEC` 覆盖）：
   - 单槽示例: `(mkdir -p _runs/logs && CUDA_VISIBLE_DEVICES=2 setsid poetry run python train.py > _runs/logs/run.log 2>&1 < /dev/null &) && echo PID=$!` 然后 `./scripts/wait-train.sh --log _runs/logs/run.log --pid $!`（`setsid` 让 train.py 走新 session,免受 Ctrl+C / SIGHUP 影响 — 见 step 4 注释）
   - 多槽示例: 全部子进程启动并记下各 PID 后: `./scripts/wait-train.sh --log _runs/logs/run_slot0.log --parallel-total 4`（必要时对各槽 `--exp-dir`）；多槽训末 wait-train 自动 finalize（失败会 WARN，届时手动补 `finalize-round <dirs> --repo-root .`）。
   - **禁止**在 `wait-train.sh` 返回前自行连环 `sleep` + `grep '^step='` / 反复 `tail`（仅当 wait-train 已报 failed/timeout 需排查例外）。
   - 退出码 0 → **先查 build metadata（step 4b）** → 继续读 `_runs/round_decision.json`、KEEP、EXPERIENCE；退出码 1 → 读日志与 `train_exception.txt` 再修复，勿空等。

[step 5 末尾] 撞墙 / 跨场景 / 怀疑 bug (WPL trigger):
  满足任一条件即触发:plateau_streak ≥ agent.plateau_rounds  ||  scenario_id 切  ||  fancy < plain_anchor

  Agent 须重新推 plain:
    1. 若 scenario 切换:CSP 派生,先在新场景跑 plain 重新建立 anchor(同 BAS 流程)
    2. 若 plateau ≥ N:对比 plain_anchor_value vs best
       - plain < best  → fancy 空间有效但耗尽 → 升档(不在本 protocol 范围,见 PROTOCOL §7.5.1)
       - plain ≈ best  → 撞 plain 墙 → 收手或换 baseline
       - plain > best  → fancy 有 bug,回退 plain 当 baseline → SBN 派生,必 DISCARD 本轮
    3. 写 plain_why 重审(若是 WPL 触发而非 BAS 触发,plain_why 必填解释「为什么撞墙后 plain 也变了」)

  共享 PDH 6 原则(P1-P6):
    P1 弱于 random      :plain 略胜随机,不与 fancy 争辉
    P2 朴素经济         :plain 几分钟跑完,不是几小时
    P3 领域 worst sane  :CL=ER/Naive/DER++; 时序=last-value/AR(1); 分类=per-class prior/LR;
                         回归=mean predictor; RL=random/heuristic; 物理=naive dynamics
                         ↑ 不限定领域,模板不假设
    P4 一眼看可解释     :< 100 超参,不是 1 万参数网络
    P5 plain_why 必写   :一句话,review 友好
    P6 预算感知          :plain_budget 必填(time_budget / memory budget / params 上限);
                          CSI 紧预算=int4 后量化,松预算=FP16 简单量化,实例不同但思路同

6. **Pre-flight** runs automatically inside `train.py` (G1–G4 + loss→backward→finalize dry-run). If preflight fails, fix train.py / workspace/; do not disable guards casually.
7. Use `_runs/round_decision.json` → `keep_suggestion` + PROTOCOL §6 for keep/discard:
   - KEEP: keep the commit; `finalize_round` auto-writes `saved/keeper.json` when `keep_suggestion=true` (stderr: `saved_keeper:`). If missing (old template), run `poetry run python -m contract write-keeper --exp-dir <keeper_run_dir>` (`keeper_exp_dir=...` from finalize stderr). Manual `write-keeper` still for baseline adopt when `keep_suggestion=false`. Do NOT use `_runs/keep/` or `saved/keep/*.pt`.
   - DISCARD: record `git_commit` before rollback → `git checkout HEAD~1 -- train.py workspace/` → new commit; no need to manually delete `_runs/exp/<run_dir>`.
   - **fork 触发（实现撞墙）:** if this round picked a novel cell and lightweight means (register/adapter/monkey-patch/slim) could NOT express it, write a sidecar `_runs/exp/<run_dir>/source_block.json` with `{"blocked": true, "cell": "<ABCDE-depth, e.g. C-novel>", "evidence": "<点名试过的轻量手段 + 为何改不动，≥20 字>"}` BEFORE rollback. finalize_round 会把它并入 `_runs/round_decision.json`；轮末 reflect 核验真假撞墙并在 REFLECT_INDEX 写升级建议。未撞墙则**不**写。**Still run step 10:** commit ledger files appended by finalize (checkout does not revert TSV/jsonl).
8. After `finalize_round`, **do not** manually append `_runs/results.tsv` / jsonl (already done).
9. MUST append EXPERIENCE.md every round at <!-- experience-log-start --> (after 近期实验区). Section title must include a wall-clock timestamp in the form YYYY-MM-DD HH:MM (see template at top of EXPERIENCE.md). Do NOT prepend before ## 精华摘要. Read ## 精华摘要 + ## 信息索引 + ## Tier 状态 + ## 近期实验 (last 5 rounds, points only); follow index paths on demand; do not read `references/experience/archive_*` or paste arxiv urls into EXPERIENCE. **P0-1 pre-append strip (mandatory):** 在 append 之前，**正则剔除** arxiv URL（pattern `https?://arxiv\.org/(abs|pdf)/[\d.]+(?:v\d+)?(?:\.pdf)?`），统一替换为 `[arxiv:<id>]`（如 `https://arxiv.org/abs/2407.12345` → `[arxiv:2407.12345]`）；若整段无 paper id 信息，删除整段链接（保留文字描述）。Each round ≤40 lines. Tier semantics: PROTOCOL §7.5.1; update ## Tier 状态 every round (cells ≤80 chars).
10. **Post-round git (ledger closure, REQUIRED):** After finalize + EXPERIENCE, MUST `git add` and `git commit` at least: `_runs/results.tsv`, `_runs/results.jsonl`, `_runs/round_decision.json` (if updated), `EXPERIENCE.md`, and `git add -f saved/keepers.json saved/experiment_journal.json` if changed. Do NOT commit only `workspace/` / `train.py` while leaving ledger uncommitted. `finalize_round` writes disk only — git commit is separate (PROTOCOL §6 step 10).
11. If blocked, document in EXPERIENCE.md (optional short note via `journal_append --event round --note "…"` on next round).

Do not ask whether to continue.
PROMPT_EOF
    # Append hardware context to prompt (needs bash variable interpolation)
    # 占位符替换（勿用 sed -i，避免特殊字符破坏临时文件）
    if ! _nn_prompt_substitute "$PROMPT_FILE" \
        "<EXPLORATION>=${_EXPLORATION}" \
        "<POLL_INTERVAL>=${_POLL_INTERVAL}"; then
        log "ERROR" "prompt 占位符替换失败"
        rm -f "$PROMPT_FILE"
        exit 1
    fi
    _SCENARIO_MANIFEST_BLOCK=""
    if command -v python3 >/dev/null 2>&1; then
        _SCENARIO_MANIFEST_BLOCK="$(python3 - <<'PY' 2>/dev/null || true
from pathlib import Path
import sys
sys.path.insert(0, str(Path.cwd().resolve()))
from experiment import build_agent_scenario_manifest, format_agent_scenario_prompt_block
block = format_agent_scenario_prompt_block(build_agent_scenario_manifest(Path.cwd().resolve()))
if block.strip():
    print(block)
PY
)"
    fi
    if [[ -n "${_SCENARIO_MANIFEST_BLOCK}" ]]; then
        printf '\n%s\n' "$_SCENARIO_MANIFEST_BLOCK" >> "$PROMPT_FILE"
    fi

    # G-HUMAN 轮初双检（baseline drift → skip Agent 或 fail-fast）
    if ! _check_human_guidance_gate; then
        if [[ "$(_nn_cfg_human_gate_fail_fast)" -eq 1 ]]; then
            rm -f "$PROMPT_FILE"
            log "ERROR" "human_guidance_gate_fail_fast=true — 终止 batch"
            exit 1
        fi
        rm -f "$PROMPT_FILE"
        log "WARNING" "Run $run Agent 已跳过（HUMAN drift）"
        continue
    fi

    REFLECT_PENDING_AT_ROUND_START=0
    if _has_reflect_pending 2>/dev/null; then
        REFLECT_PENDING_AT_ROUND_START=1
    fi
    rm -f "${SCRIPT_DIR}/saved/.reflect_pending_at_round_start" 2>/dev/null || true
    if [[ "$REFLECT_PENDING_AT_ROUND_START" -eq 1 ]]; then
        echo "1" > "${SCRIPT_DIR}/saved/.reflect_pending_at_round_start"
    fi

    _inject_run_context_prompt "$PROMPT_FILE"
    _inject_guidance_reflect_prompt "$PROMPT_FILE"
    _inject_explore_prompt "$PROMPT_FILE"
    _inject_pluggable_principles_prompt "$PROMPT_FILE"
    _inject_tam_cochange_prompt "$PROMPT_FILE"
    _inject_innovation_prompt "$PROMPT_FILE"
    _inject_doctor_drift_prompt "$PROMPT_FILE" "$run"
    printf '\nDo NOT edit HUMAN_GUIDANCE.md; roadmap is injected read-only from committed/baseline snapshot.\n' >> "$PROMPT_FILE"
    printf '\n禁止运行 scripts/refresh-human-guidance-baseline.sh；G-HUMAN fail 时不得 bypass，须停 batch 由人恢复 HUMAN_GUIDANCE.md。\n' >> "$PROMPT_FILE"
    if _has_reflect_pending 2>/dev/null; then
        : # pending 已注入
    else
        printf '\n**Reflect:** 无待消费反思（REFLECT_INDEX pending 为空）；勿通读 references/auto/。\n' >> "$PROMPT_FILE"
    fi
    if [[ -f nn-config.yaml ]]; then
        cat >> "$PROMPT_FILE" <<HW_EOF

**Hardware context (from nn-config.yaml):**
- Available GPUs (whitelist): ${_HW_GPUS:-auto-detect}
- Usable GPUs right now (exclusive+shareable): ${_HW_FREE_GPUS:-unknown}
- max_parallel (upper bound per round): ${_HW_MAX_PARALLEL}

**GPU 档位（exclusive=近空独占；shareable=可同卡插队；busy=勿加任务）:**
${_HW_GPU_TABLE:-（未探测到 nvidia-smi 快照）}

HW_EOF
    fi

    {
        echo ""
        echo "--- Prompt excerpt (first 18 lines) ---"
        sed -n '1,18p' "$PROMPT_FILE"
    } >> "$AGENT_ROUND_LOG"

    METRIC_KEY="${_CACHED_METRIC_KEY:-$(contract_metric_key)}"
    echo ""
    _sj_hint="${LOG_DIR}/$(basename "$AGENT_ROUND_LOG" .log)_stream.jsonl"
    echo -e "${CYAN}Agent 轮次${NC}  $AGENT_ROUND_LOG（无 stream-json 时亦含 Agent stdout）"
    echo -e "${CYAN}批次日志${NC}  $LOG_FILE（心跳 / SUCCESS）"
    echo -e "${CYAN}METRIC_KEY${NC} $METRIC_KEY  ${CYAN}git${NC} $(git rev-parse --short HEAD 2>/dev/null || echo none)"
    echo -e "${YELLOW}看训练${NC}  ${BLUE}tail -f $(printf '%q' "$SCRIPT_DIR/$TRAIN_LOG")${NC}"
    if [[ "$AGENT_TYPE" == "claude" ]]; then
        echo -e "${YELLOW}看 Agent 摘要${NC} stderr [claude-stream]（关: NN_AGENT_CLAUDE_STREAM_PROGRESS=0）· NDJSON ${BLUE}tail -f $(printf '%q' "$_sj_hint")${NC}"
    fi
    unset _sj_hint
    echo ""

    # 心跳
    (
        while true; do
            sleep "$HEARTBEAT_SEC"
            elapsed=$(($(date +%s) - RUN_START))
            hb="[heartbeat] Run $run/$TOTAL_RUNS · ${elapsed}s · ${AGENT_NAME} 仍在执行 · 训练: _runs/logs/run.log"
            echo -e "\n${YELLOW}${hb}${NC}" >&2
            echo "$hb" >> "$LOG_FILE"
        done
    ) &
    HEARTBEAT_PID=$!

    # 进程清理
    cleanup_agent_job() {
        kill "$HEARTBEAT_PID" 2>/dev/null || true
        _nn_agent_claude_watchdog_stop
        if [[ -n "${_nn_claude_pid:-}" ]]; then
            kill "$_nn_claude_pid" 2>/dev/null || true
            wait "$_nn_claude_pid" 2>/dev/null || true
            _nn_claude_pid=""
        fi
        if [[ -n "${_nn_claude_fifo:-}" ]]; then
            rm -f "$_nn_claude_fifo"
            _nn_claude_fifo=""
        fi
    }
    # Ctrl+C / SIGTERM 处理：仅清理**编排层**（心跳 + agent fifo 源 + prompt 临时文件），
    # **不**递归杀子进程 —— agent 内部用 `setsid` 启动的 train.py 走新 session，
    # agent bash 死时不会通过 SIGHUP 牵连到 train.py,后台训练可继续跑。
    on_interrupt_stop_all() {
        cleanup_agent_job
        rm -f "${PROMPT_FILE:-}"
        _release_gpu_snapshot
        log "WARNING" "已中断：编排已停止（Ctrl+C / SIGTERM）— 后台训练若仍在跑可用 tail -f _runs/logs/run*.log 观察，不会被强制 kill"
        trap - INT TERM
        exit 130
    }
    trap 'on_interrupt_stop_all' INT
    trap 'on_interrupt_stop_all' TERM

    # 调用 agent（前台管道；Ctrl+C / SIGTERM 可直接传到 agent）
    set -o pipefail
    _ok=0
    _claude_extra=()
    if [[ "$AGENT_TYPE" == "claude" ]]; then
        _dbg="$(echo "${NN_AGENT_CLAUDE_DEBUG:-1}" | tr '[:upper:]' '[:lower:]')"
        if [[ "$_dbg" != "0" && "$_dbg" != "false" && "$_dbg" != "no" && "$_dbg" != "off" ]]; then
            _ccf="${LOG_DIR}/$(basename "$AGENT_ROUND_LOG" .log)_claude-debug.txt"
            _claude_extra=(--debug-file "$_ccf")
            log "INFO" "Claude --debug-file（默认开，关: NN_AGENT_CLAUDE_DEBUG=0）: $_ccf"
        fi
        unset _dbg
    fi
    _stream_jsonl=""
    _claude_stream_fmt=()
    if [[ "$AGENT_TYPE" == "claude" ]]; then
        _sjs="$(echo "${NN_AGENT_CLAUDE_STREAM_JSON:-1}" | tr '[:upper:]' '[:lower:]')"
        if [[ "$_sjs" != "0" && "$_sjs" != "false" && "$_sjs" != "no" && "$_sjs" != "off" ]]; then
            _stream_jsonl="${LOG_DIR}/$(basename "$AGENT_ROUND_LOG" .log)_stream.jsonl"
            # stream-json + --print 必须 --verbose，否则 stdout 几乎只有一行报错
            _claude_stream_fmt=(--output-format stream-json --verbose)
            log "INFO" "Claude 原始流 NDJSON（关: NN_AGENT_CLAUDE_STREAM_JSON=0）: $_stream_jsonl"
        fi
        unset _sjs
    fi
    if [[ -n "$_stream_jsonl" ]]; then
        { echo ""; echo "--- Agent stdout (raw NDJSON) → $_stream_jsonl ---"; } >> "$AGENT_ROUND_LOG"
    fi
    if [[ "$AGENT_TYPE" == "cursor" ]]; then
        _cursor_extra=()
        if [[ -n "${NN_AGENT_CURSOR_MODEL}" ]]; then
            _cursor_extra=(--model "${NN_AGENT_CURSOR_MODEL}")
        fi
        stdbuf -oL -eL agent -p --trust --yolo --approve-mcps \
            "${_cursor_extra[@]}" \
            --workspace "$SCRIPT_DIR" < "$PROMPT_FILE" 2>&1 \
            | stdbuf -oL -eL tee -a "$AGENT_ROUND_LOG" \
            | stdbuf -oL -eL tee -p /dev/stderr \
            && _ok=1 || _ok=0
        unset _cursor_extra
    elif [[ -n "$_stream_jsonl" ]]; then
        _sj_err="$(echo "${NN_AGENT_CLAUDE_STREAM_TO_STDERR:-0}" | tr '[:upper:]' '[:lower:]')"
        _nn_agent_claude_stream_source_start
        if [[ "$_sj_err" == "1" || "$_sj_err" == "true" || "$_sj_err" == "yes" || "$_sj_err" == "on" ]]; then
            stdbuf -oL -eL tee -a "$_stream_jsonl" < "$_nn_claude_fifo" \
                | stdbuf -oL -eL tee -a "$AGENT_ROUND_LOG" \
                | stdbuf -oL -eL tee -p /dev/stderr \
                && _ok=1 || _ok=0
        else
            _sj_prog="$(echo "${NN_AGENT_CLAUDE_STREAM_PROGRESS:-1}" | tr '[:upper:]' '[:lower:]')"
            if [[ "$_sj_prog" != "0" && "$_sj_prog" != "false" && "$_sj_prog" != "no" && "$_sj_prog" != "off" ]]; then
                echo -e "${CYAN}[claude]${NC} stream-json → $(printf '%q' "$_stream_jsonl") · ${CYAN}终端${NC}: stderr 单行摘要 · ${CYAN}原文${NC}: tail -f … · ${CYAN}关摘要${NC}: NN_AGENT_CLAUDE_STREAM_PROGRESS=0 · ${CYAN}镜像完整 NDJSON${NC}: NN_AGENT_CLAUDE_STREAM_TO_STDERR=1" >&2
                stdbuf -oL -eL tee -a "$_stream_jsonl" < "$_nn_claude_fifo" \
                    | stdbuf -oL -eL tee -a "$AGENT_ROUND_LOG" \
                    | python3 -u "${SCRIPT_DIR}/scripts/claude_stream_summarize.py" \
                    && _ok=1 || _ok=0
            else
                echo -e "${CYAN}[claude]${NC} stream-json → $(printf '%q' "$_stream_jsonl")（终端静默；开摘要: NN_AGENT_CLAUDE_STREAM_PROGRESS=1；原文: tail -f …；镜像 NDJSON: NN_AGENT_CLAUDE_STREAM_TO_STDERR=1）" >&2
                stdbuf -oL -eL tee -a "$_stream_jsonl" < "$_nn_claude_fifo" \
                    | stdbuf -oL -eL tee -a "$AGENT_ROUND_LOG" \
                    > /dev/null \
                    && _ok=1 || _ok=0
            fi
            unset _sj_prog
        fi
        _nn_agent_claude_stream_source_finish
        unset _sj_err
    else
        _nn_run_claude "${_claude_extra[@]}" -p --dangerously-skip-permissions \
            < "$PROMPT_FILE" 2>&1 \
            | stdbuf -oL -eL tee -a "$AGENT_ROUND_LOG" \
            | stdbuf -oL -eL tee -p /dev/stderr \
            && _ok=1 || _ok=0
    fi
    unset _ccf _claude_extra _stream_jsonl _claude_stream_fmt
    set +o pipefail
    trap - INT TERM
    cleanup_agent_job

    # L3-D1: multi-slot finalize 兜底门 — 跑完一轮先验多槽是否都入账。
    # 单槽不检（单槽 train.py 训末自动 finalize_round）；多槽 _s\d+ofN_ (N>=2) 现由
    # wait-train.sh 训末自动 finalize-round（全部 slot done 且无 fail 时）。本门为兜底：
    # 自动 finalize 失败/未触发（如 EXP_DIRS < PARALLEL_TOTAL 跳过）→ gap → 本轮降级 ERROR。
    # 逻辑不变：jsonl/TSV 须含全部候选 exp_dir（坏分也保留）；同 exp_dir 二次 finalize 跳过（幂等）。
    _MULTI_SLOT_GAP=0
    if [[ "${_ok:-0}" -eq 1 ]] && [[ -f scripts/check_multi_slot_finalize.py ]]; then
        _msf_out="$(python3 scripts/check_multi_slot_finalize.py --repo-root "${SCRIPT_DIR}" 2>&1)" && _msf_rc=0 || _msf_rc=$?
        if [[ "${_msf_rc:-0}" -ne 0 ]]; then
            _MULTI_SLOT_GAP=1
            _msf_names="$(echo "${_msf_out}" | grep '^UNFINALIZED:' | sed 's/^UNFINALIZED:[[:space:]]*//' | tr '\n' ' ')"
            log "ERROR" "multi_slot_finalize_missing: ${_msf_names}（需手动 poetry run python -m contract finalize-round <dirs>...）"
        fi
        unset _msf_out _msf_rc _msf_names
    fi

    if [[ "${_ok:-0}" -eq 1 && "${_MULTI_SLOT_GAP}" -eq 0 ]]; then
        log "SUCCESS" "Run $run finished in $(($(date +%s) - RUN_START))s"
    elif [[ "${_ok:-0}" -eq 1 ]]; then
        log "ERROR" "Run $run agent OK 但 multi-slot finalize gap（见上）"
    else
        log "WARNING" "Run $run 子进程失败（详见 $AGENT_ROUND_LOG）"
    fi
    _ROUND_AGENT_OK="${_ok:-0}"
    [[ "${_MULTI_SLOT_GAP}" -eq 1 ]] && _ROUND_AGENT_OK=0
    # AE-2 失败计数接线：本轮 agent 失败或 multi-slot gap → _round_failed+1（循环后汇总 WARNING）
    [[ "${_ROUND_AGENT_OK:-0}" -ne 1 ]] && _round_failed=$((_round_failed + 1))
    unset _MULTI_SLOT_GAP
    unset _ok
    rm -f "$PROMPT_FILE"
    _release_gpu_snapshot

    _ROWS_AFTER=$(count_result_rows)

    if [[ "${_ROUND_AGENT_OK:-0}" -eq 1 && "${_ROWS_AFTER:-0}" -le "${ROWS_START:-0}" ]]; then
        if [[ "${NN_AUTO_RUN_SKIP_LEDGER_CLOSURE:-0}" != "1" ]] && [[ -f scripts/check_round_ledger_closure.py ]]; then
            if python3 scripts/check_round_ledger_closure.py --repo-root "${SCRIPT_DIR}" 2>&1 | grep -q '^FAIL:'; then
                log "WARNING" "finalize_missing: 本轮有已完成训练但未入账（见 check_round_ledger_closure）"
            fi
        fi
    fi

    # G-HUMAN — 须在 git WARN（含 journal_pre_append）之前；D1：revert 时 log ERROR 但继续批次
    if [[ "$REFLECT_ONLY" != "1" ]] && [[ -f scripts/human_guidance_gate.py ]]; then
        NN_AUTO_RUN_ROUND="$run" python3 scripts/human_guidance_gate.py \
            --repo-root "${SCRIPT_DIR}" post-round-enforce >> "$AGENT_ROUND_LOG" 2>&1 \
            || true
        if grep -qE 'G-HUMAN-(COMMIT_REVERT|WS_REVERT):' "$AGENT_ROUND_LOG" 2>/dev/null; then
            log "ERROR" "G-HUMAN-COMMIT: 本轮 HUMAN_GUIDANCE 已从 batch baseline 恢复（见 agent log）"
        fi
    fi

    # 轮末漂移检测：捕获本轮 doctor FAIL（不阻断 batch）
    _run_round_doctor "$run"

    if [[ -f scripts/sync_ledger.py ]]; then
        python3 scripts/sync_ledger.py --apply >> "$LOG_FILE" 2>&1 || true
    fi

    # git 警告（EXPERIENCE + 台账训后 commit；journal 仅统计 append 前脏状态，PROTOCOL §6 步骤 10）
    if git rev-parse --git-dir >/dev/null 2>&1; then
        if git rev-parse --verify HEAD~1 >/dev/null 2>&1; then
            if ! git diff --name-only HEAD~1 HEAD 2>/dev/null | grep -qE '^EXPERIENCE\.md$'; then
                log "WARNING" "EXPERIENCE.md 未出现在本轮提交相对 HEAD~1 的变更中"
            fi
            _ledger_in_commit=0
            if git diff --name-only HEAD~1 HEAD 2>/dev/null | grep -qE '^_runs/results\.(tsv|jsonl)$'; then
                _ledger_in_commit=1
            fi
            if [[ "${_ROWS_AFTER:-0}" -gt "${ROWS_START:-0}" && "$_ledger_in_commit" -eq 0 ]]; then
                log "WARNING" "本轮 finalize 后台账未出现在最近 commit（TSV 行 ${ROWS_START}→${_ROWS_AFTER}）"
            fi
        fi
        _ledger_dirty=0
        for _lf in _runs/results.tsv _runs/results.jsonl; do
            [[ -f "$_lf" ]] || continue
            if ! git ls-files --error-unmatch "$_lf" >/dev/null 2>&1; then
                log "WARNING" "台账未 commit（${_lf} 未纳入 git track）"
                _ledger_dirty=1
                continue
            fi
            if ! git diff --quiet -- "$_lf" 2>/dev/null || ! git diff --cached --quiet -- "$_lf" 2>/dev/null; then
                _ledger_dirty=1
            fi
        done
        if [[ "$_ledger_dirty" -eq 1 ]]; then
            log "WARNING" "台账未 commit（_runs/results.tsv 或 results.jsonl 工作区/暂存区有未提交变更）"
        fi
        if [[ -f saved/experiment_journal.json ]]; then
            _journal_dirty=0
            if ! git ls-files --error-unmatch saved/experiment_journal.json >/dev/null 2>&1; then
                _journal_dirty=1
            elif ! git diff --quiet -- saved/experiment_journal.json 2>/dev/null \
                || ! git diff --cached --quiet -- saved/experiment_journal.json 2>/dev/null; then
                _journal_dirty=1
            fi
            if [[ "$_journal_dirty" -eq 1 ]]; then
                log "WARNING" "journal 未 commit（saved/experiment_journal.json 工作区/暂存区有未提交变更）"
                BATCH_JOURNAL_UNCOMMITTED_WARNS=$((BATCH_JOURNAL_UNCOMMITTED_WARNS + 1))
            fi
        elif [[ "${_ROWS_AFTER:-0}" -gt 0 ]]; then
            log "WARNING" "journal_missing（有 TSV 数据行但无 saved/experiment_journal.json）"
        fi
        if [[ -f progress.txt ]]; then
            log "WARNING" "legacy_progress_file（progress.txt 已废弃，请 migrate-drop-progress 或删除）"
        fi
    fi

    {
        echo ""
        echo "--- Run $run end, _runs/results.tsv rows: ${_ROWS_AFTER} ---"
    } >> "$AGENT_ROUND_LOG"

    # EXPERIENCE 轮末压缩（warn / after_round；台账 WARN 之后、mark-reflect-consumed 之前）
    if [[ "$REFLECT_ONLY" != "1" ]]; then
        _maybe_auto_compress_experience "$run"
    fi

    # 消费 reflect pending（实验轮结束后；反思轮不消费；须有效 reflect_ack）
    if [[ "$REFLECT_ONLY" != "1" ]]; then
        _consume_reflect_pending_if_ack "$run"
    fi

    # journal round append（须在 git WARN 与 reflect_ack 消费之后，避免假阳性 journal 未 commit）
    _JOURNAL_APPEND_RAN=0
    if [[ "${_ROUND_AGENT_OK:-0}" -eq 1 && "${_ROWS_AFTER:-0}" -gt "${ROWS_START:-0}" ]]; then
        if [[ -f scripts/journal_append.py ]]; then
            if python3 scripts/journal_append.py --event round --apply >> "$AGENT_ROUND_LOG" 2>&1; then
                _JOURNAL_APPEND_RAN=1
            else
                log "WARNING" "journal_append round 失败（非致命）"
            fi
        fi
    fi
    if [[ "$_JOURNAL_APPEND_RAN" -eq 1 ]]; then
        log "INFO" "journal_appended_by_shell: Run $run（下轮 PROTOCOL 步骤 10 须 commit saved/experiment_journal.json）"
    fi
    unset _JOURNAL_APPEND_RAN

    # P1-3: 轮末 auto-commit journal 类文件（独立 commit；不依赖 agent step 10）
    # saved/experiment_journal.json + saved/keepers.json + references/auto/*_auto_reflected.md
    # 行为：add 所有 → 若 staged 不空则 commit；
    # 副作用：BATCH_JOURNAL_UNCOMMITTED_WARNS 下轮不再假阳性递增
    if [[ -f saved/experiment_journal.json ]] || [[ -f saved/keepers.json ]] || [[ -d references/auto ]]; then
        [[ -f saved/experiment_journal.json ]] && git add -- saved/experiment_journal.json 2>/dev/null
        [[ -f saved/keepers.json ]] && git add -f -- saved/keepers.json 2>/dev/null
        [[ -f .auto-nn/skill-activity.jsonl ]] && git add -- .auto-nn/skill-activity.jsonl 2>/dev/null
        [[ -d references/auto ]] && git add -A -- "references/auto/" 2>/dev/null
        if ! git diff --cached --quiet 2>/dev/null; then
            git commit -m "ledger: auto journal artifacts (Run $run)" >/dev/null 2>&1 \
                && log "INFO" "auto-journal-committed (Run $run)" \
                || log "WARNING" "auto-journal-commit 失败（Run $run）"
        fi
    fi

    # ------------------------------------------------------------------------
    # Tier-ladder 反思轮（门禁 R1–R6；reflect_interval 为上限频率；R1=nn-config reflect_force）
    # ------------------------------------------------------------------------
    if [[ "$REFLECT_ONLY" != "1" ]]; then
        _skip_reflect=0
        if [[ "${NN_AUTO_RUN_SKIP_LEDGER_CLOSURE:-0}" != "1" ]] && [[ -f scripts/check_round_ledger_closure.py ]]; then
            _closure_log="$(mktemp "${TMPDIR:-/tmp}/nn-closure.XXXXXX")"
            _closure_rc=0
            python3 scripts/check_round_ledger_closure.py --repo-root "${SCRIPT_DIR}" >> "$_closure_log" 2>&1 \
                || _closure_rc=$?
            while IFS= read -r _cl_line; do
                [[ -z "$_cl_line" ]] && continue
                case "$_cl_line" in
                    FAIL:*)
                        log "WARNING" "${_cl_line#FAIL: }"
                        _skip_reflect=1
                        ;;
                    WARN:*)
                        log "WARNING" "${_cl_line#WARN: }"
                        ;;
                    PASS:*)
                        ;;
                    *)
                        log "INFO" "$_cl_line"
                        ;;
                esac
            done < "$_closure_log"
            if [[ "$_skip_reflect" -eq 1 ]]; then
                log "WARNING" "reflect_skipped: ledger 未闭合（unfinalized_runs / ledger_drift）"
            fi
            rm -f "$_closure_log"
            unset _closure_rc _cl_line
        fi
        if [[ "$_skip_reflect" -eq 0 ]] && _should_run_reflect "$run"; then
            REFLECT_LOG="$LOG_DIR/$(date +%Y%m%d_%H%M%S)_reflect-${run}.log"
            {
                echo "=== Reflect after Run $run @ $(date '+%Y-%m-%d %H:%M:%S') ==="
                echo "agent_type: ${AGENT_TYPE}"
                echo "gate: ${REFLECT_RUN_REASON:-?}"
            } > "$REFLECT_LOG"

            _ref_start=$(date +%s)
            echo "[reflect] calling reflect.py (${REFLECT_RUN_REASON}) agent=${AGENT_TYPE}..." >&2
            if poetry run python reflect.py \
                --agent "$AGENT_TYPE" \
                --run "$run" \
                --reflect-gate "${REFLECT_RUN_REASON:-manual:reflect_invoked}" \
                >> "$REFLECT_LOG" 2>&1; then
                log "SUCCESS" "Reflect after run $run (${REFLECT_RUN_REASON}) in $(($(date +%s) - _ref_start))s"
            else
                log "WARNING" "reflect.py run $run failed (non-fatal)"
            fi
            unset _ref_start
        fi
        unset _skip_reflect
    fi

    echo "" >> "$LOG_FILE"
    log "INFO" "Run $run/$TOTAL_RUNS 收尾完成（实验 + 可选 reflect）"
    _maybe_echo_e_feedback_pending

    # ── goal 达标即停（N 轮为底底网）──
    # check_goal.py（T1）：exit 0=GOAL_MET / 1=GOAL_PENDING / 2=NO_GOAL 或 GOAL_SKIPPED_EXPLORE。
    # 仅在轮末（finalize 已写 TSV 行、journal/post-round-enforce 完成）判定；
    # 仅 exit 0（GOAL_MET）时 break 提前结束 loop；exit 2 含 explore 跳过（GOAL_SKIPPED_EXPLORE）→ 继续。
    if [[ -f scripts/check_goal.py ]]; then
        _gc_out="$(mktemp "${TMPDIR:-/tmp}/nn-goal.XXXXXX")"
        if python3 scripts/check_goal.py . > "$_gc_out" 2>&1; then
            _gc_msg="$(cat "$_gc_out" 2>/dev/null)"
            # 仅 GOAL_MET（exit 0）才 break；GOAL_SKIPPED_EXPLORE 为 exit 2，不会进此分支
            if [[ "$_gc_msg" == *GOAL_MET* ]]; then
                log "SUCCESS" "goal 达标：${_gc_msg}（round ${run}/${TOTAL_RUNS}）；停止 loop"
                rm -f "$_gc_out"
                break
            fi
        fi
        # exit 1（pending） / exit 2（未配 goal 或 explore 跳过）→ 继续 loop（N 轮底底网）
        rm -f "$_gc_out"
    fi

    if [[ -f scripts/check_metric_floor.py ]]; then
        _fb_out="$(python3 scripts/check_metric_floor.py . 2>&1)" || true
        if [[ "$_fb_out" == *"FLOOR_BREACH"* ]]; then
            log "WARN" "metric 底线破线：${_fb_out}"
        fi
    fi

    [ "$run" -lt "$TOTAL_RUNS" ] && sleep 2
done
set -e  # batch 循环外恢复 set -e（恢复原行为，让 batch 后 tail 阶段错误继续暴露）

# AE-2 修复：如果 batch 里有 round 失败，log 但不立刻退出（tail 阶段仍能跑）
# 让 tail 阶段汇总所有 round 状态后决定最终 exit code
if [[ "${_round_failed:-0}" -gt 0 ]]; then
    log "WARNING" "Batch 中 ${_round_failed}/${TOTAL_RUNS} 轮子进程失败（详见各 round log）"
fi
unset _round_failed

# 批次收尾在 scripts/auto-run-batch-tail.sh（勿把 log/echo 写回主脚本末尾）
# shellcheck source=scripts/auto-run-batch-tail.sh
source "${SCRIPT_DIR}/scripts/auto-run-batch-tail.sh"
