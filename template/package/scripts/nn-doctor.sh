#!/usr/bin/env bash
# nn-doctor.sh — 迁后结构体检（默认轻量；--deep 含 verify-migration-complete + smoke-check）
#
# 用法:
#   bash scripts/nn-doctor.sh
#   bash scripts/nn-doctor.sh --quiet
#   bash scripts/nn-doctor.sh --deep
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/governance-rev.sh
source "$SCRIPT_DIR/lib/governance-rev.sh"
# shellcheck source=lib/nn-state.sh
source "$SCRIPT_DIR/lib/nn-state.sh"

DEEP=0
QUIET=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --deep) DEEP=1; shift ;;
    --quiet) QUIET=1; shift ;;
    -h|--help)
      cat <<'EOF'
用法: nn-doctor.sh [--quiet] [--deep]

  默认（轻量）: layout、git/迁后文档、governance rev 对齐、contract/门面/G-封装/G-评估、
    TSV 表头、场景完整性（F1/nn-config/TSV/keepers）、台账、README/auto-run 配套、shell 语法、全局技能 rev、gate、遗留路径
  --quiet: 仅输出 WARN/FAIL 行（供 /auto-nn-analyse 静默前置）；全 PASS 时 stdout 空
  --deep: 轻量全部 + verify-migration-complete.sh + smoke-check.sh

退出码: 任一 FAIL → 1；仅 PASS/WARN → 0
EOF
      exit 0
      ;;
    *) echo "[nn-doctor] 未知参数: $1" >&2; exit 2 ;;
  esac
done

PASS=0
WARN=0
FAIL=0
IS_TEMPLATE_ROOT=0
PROFILE=""
TPKG=""

[[ -f .template-maintainer ]] && IS_TEMPLATE_ROOT=1

row() {
  local name="$1" status="$2" msg="$3"
  if [[ $QUIET -eq 0 ]] || [[ "$status" == "WARN" ]] || [[ "$status" == "FAIL" ]]; then
    printf '[nn-doctor] %s\t%s\t%s\n' "$name" "$status" "$msg"
  fi
  case "$status" in
    PASS) PASS=$((PASS + 1)) ;;
    WARN) WARN=$((WARN + 1)) ;;
    FAIL) FAIL=$((FAIL + 1)) ;;
  esac
}

run_check() {
  local name="$1"
  shift
  local out rc
  set +e
  out="$("$@" 2>&1)"
  rc=$?
  set -e
  if [[ $rc -eq 0 ]]; then
    row "$name" PASS "${out//$'\n'/; }"
  else
    row "$name" FAIL "${out//$'\n'/; }"
  fi
}

resolve_template_pkg() {
  local troot
  troot="$(nn_resolve_template_root)" || troot=""
  if [[ ! -d "$troot" ]]; then
    echo "INVALID:$troot"
    return 1
  fi
  if [[ -f "$troot/template/package/profiles.yaml" ]]; then
    echo "$troot/template/package"
  elif [[ -f "$troot/template/profiles.yaml" ]]; then
    echo "$troot/template"
  elif [[ -f "$troot/profiles.yaml" ]]; then
    echo "$troot"
  else
    echo "INVALID:$troot"
    return 1
  fi
}

collect_global_skill_names() {
  local troot="$1" d name
  for d in "$troot/skills/post-migration"/auto-nn-* "$troot/skills/maintainer"/auto-nn-*; do
    [[ -d "$d" && -f "$d/SKILL.md" ]] || continue
    name="$(basename "$d")"
    printf '%s\n' "$name"
  done
}

if [[ $QUIET -eq 0 ]]; then
  echo "[nn-doctor] 仓库: $ROOT"
  echo "[nn-doctor] 档位: $([[ $DEEP -eq 1 ]] && echo deep || echo light)"
fi

# ── 1. 布局 ──
if [[ -f scripts/verify_project_layout.py ]]; then
  run_check layout python3 scripts/verify_project_layout.py .
else
  row layout FAIL "缺少 scripts/verify_project_layout.py"
fi

# ── 1a. seed setup ──
if [[ -f train.py ]]; then
  if grep -q "setup_seed" train.py; then
    row seed_setup PASS "train.py uses ExperimentBase.setup_seed()"
  elif grep -q "torch.backends.cudnn.deterministic" train.py; then
    row seed_setup WARN "train.py has inline cudnn setup; 建议迁移到 ExperimentBase.setup_seed()"
  else
    row seed_setup WARN "train.py has no seed setup detected"
  fi
fi

# ── 1a2. SEED 必须从 config.json（Config-Only）──
if [[ -f train.py ]]; then
  # 检查是否依赖 NN_SEED 环境变量（不允许）
  if grep -q "os.environ.get.*NN_SEED" train.py || grep -q 'os.environ\["NN_SEED"\]' train.py; then
    row seed_config_only FAIL "train.py 依赖 NN_SEED 环境变量（禁止）
修复：将 SEED 写入 config.json，train.py 从 cfg['SEED'] 读取"
  elif [[ -f experiment.py ]] && python3 -c '
import re, pathlib, sys
text = pathlib.Path("experiment.py").read_text(encoding="utf-8")
m = re.search(r"def seed\(self\)[\s\S]*?(?=\n    def |\nclass )", text)
sys.exit(1 if m and "NN_SEED" in m.group(0) else 0)
'; then
    row seed_config_only FAIL "experiment.py seed 属性仍读 NN_SEED（禁止）
修复：bind_train_cfg(cfg) 后从 cfg[\"SEED\"] 读；见 ExperimentBase.seed"
  else
    row seed_config_only PASS "SEED 从 config.json 读取"
  fi
fi

# ── 1b. build_full_snapshot check ──
if [[ -f train.py ]]; then
  if grep -q "build_full_snapshot" train.py; then
    row config_snapshot PASS "train.py 调用了 build_full_snapshot()"
  else
    row config_snapshot FAIL "train.py 未调用 build_full_snapshot()，config.json 信息不完整
修复：在 device = _pick_device() 后加：
cfg.update(contract.build_full_snapshot(device=str(device)))
并删除 cfg[\"SEED\"] = contract.seed"
  fi
fi

# ── 1c. hardcoded params (AST 扫描，轻量档默认；命中才提示) ──
# analyze_hardcoded_params.py 退出码不区分命中（有发现也 rc=0），故解析 stdout：
# 含 "  • " 行 = 有 ParamAdvice 命中 → INFO（quiet 下隐藏，非 quiet 显示）；否则 PASS。
if [[ -f train.py ]] && [[ -f "$SCRIPT_DIR/analyze_hardcoded_params.py" ]]; then
  _hp_out="$(python3 "$SCRIPT_DIR/analyze_hardcoded_params.py" train.py 2>&1)" || true
  if printf '%s\n' "$_hp_out" | grep -q '^  • '; then
    _hp_n="$(printf '%s\n' "$_hp_out" | grep -c '^  • ' || true)"
    row hardcoded_params INFO "发现 ${_hp_n} 个未配置化常量（建议 _ev()/NN_ 参数化；详情手跑 scripts/analyze_hardcoded_params.py train.py）"
  else
    row hardcoded_params PASS "train.py 超参 + workspace build 已配置化，无硬编码常量"
  fi
fi

# ── G-repro-env: 检查整个项目是否禁止读实验参数的 NN_* 环境变量 ──
check_repro_env() {
  local repo_root="${1:-.}"
  local train_file="$repo_root/train.py"
  local check_name="G-repro-env"

  if [[ ! -f "$train_file" ]]; then
    echo -e "$check_name\tSKIP\tNo train.py found" >&2
    return 0
  fi

  # 系统参数白名单（允许读）- 与 PROTOCOL.md §2.3 系统参数对齐
  local allowed_nn_vars="NN_DEVICE|NN_PREFLIGHT|NN_SMOKE|NN_AUTO_FINALIZE_ROUND|NN_EXPERIMENT|NN_PARALLEL_TOTAL|NN_SLOT|NN_POST_TRAIN_HOOK|NN_TIME_BUDGET|NN_DATA_DIR|NN_GUARD|NN_RELAUNCH|NN_GRAD_CLIP|NN_NOTES|NN_EARLY_STOP_PATIENCE|NN_APPEND_RESULTS_TSV|NN_APPEND_RESULTS_JSONL|NN_PREFLIGHT_LEDGER|NN_ROOT_PY_ALLOWLIST"

  # 扫描 train.py, contract/, workspace/ 中的所有 os.environ.get("NN_XXX") 调用
  local nn_calls
  nn_calls="$(grep -rh 'os\.environ\.get("NN_[^"]*")' "$repo_root/train.py" "$repo_root/contract/"*.py "$repo_root/workspace/"*.py 2>/dev/null | sort -u || true)"

  if [[ -z "$nn_calls" ]]; then
    echo -e "$check_name\tPASS\t无 NN_* 环境变量读取" >&2
    return 0
  fi

  # 检查是否有不在白名单的实验参数
  local forbidden_calls=""
  while IFS= read -r line; do
    # 提取 NN_* 变量名
    local nn_var
    nn_var="$(echo "$line" | grep -oE 'NN_[A-Z_]+' || true)"
    if [[ -n "$nn_var" ]]; then
      # 检查是否在白名单中
      if [[ ! "$nn_var" =~ ^(${allowed_nn_vars})$ ]]; then
        forbidden_calls="$forbidden_calls$line"$'\n'
      fi
    fi
  done <<< "$nn_calls"

  if [[ -n "$forbidden_calls" ]]; then
    echo -e "$check_name\tFAIL\t发现读实验参数的 NN_* 环境变量:" >&2
    echo "$forbidden_calls" | while IFS= read -r line; do
      echo "  - $line\"" >&2
    done
    echo "  实验参数应通过 --config config.json 传入，禁止通过环境变量" >&2
    return 1
  fi

  echo -e "$check_name\tPASS\t仅使用允许的系统参数" >&2
  return 0
}

# ── G-repro-cli: 检查 train.py 是否禁止 CLI 参数（除 --config 外） ──
check_repro_cli() {
  local train_file="$1"
  local check_name="G-repro-cli"

  if [[ ! -f "$train_file" ]]; then
    echo -e "$check_name\tSKIP\tNo train.py found" >&2
    return 0
  fi

  # 检查是否有 add_argument("--lr") 等实验参数 CLI（排除 --config、--help 和系统参数）
  # 允许的系统参数: --experiment, --experiment-desc, --slot, --parallel-total, --device
  local forbidden_args
  forbidden_args="$(grep -E 'add_argument\("--[a-zA-Z]' "$train_file" 2>/dev/null \
    | grep -vE '"--(config|help|experiment-desc|experiment|slot|parallel-total|device|no-auto-finalize-round)' \
    || true)"

  if [[ -n "$forbidden_args" ]]; then
    echo -e "$check_name\tFAIL\t发现禁止的 CLI 参数:" >&2
    echo "$forbidden_args" | while IFS= read -r line; do
      echo "  - $line" >&2
    done
    echo "  仅允许 add_argument(\"--config\")，禁止其他实验参数 CLI" >&2
    return 1
  fi

  echo -e "$check_name\tPASS\t无禁止的 CLI 参数" >&2
  return 0
}

# ── G-cfg-no-defaults: 检查代码中是否使用 cfg.get 实验参数默认值 ──
check_cfg_no_defaults() {
  local repo_root="${1:-.}"
  local check_name="G-cfg-no-defaults"
  local scan_script="$SCRIPT_DIR/scan_cfg_defaults.py"

  if [[ ! -f "$scan_script" ]]; then
    echo -e "$check_name\tSKIP\tscan_cfg_defaults.py not found" >&2
    return 0
  fi

  if [[ ! -f "$repo_root/experiment.py" ]]; then
    echo -e "$check_name\tSKIP\tNo experiment.py found" >&2
    return 0
  fi

  # 运行 scan_cfg_defaults.py 并捕获输出
  local scan_out
  scan_out="$(cd "$repo_root" && python3 "$scan_script" "$repo_root" 2>&1)" || true

  if echo "$scan_out" | grep -q "FAIL"; then
    echo -e "$check_name\tFAIL\t发现实验参数 cfg.get 默认值:" >&2
    echo "$scan_out" | grep "FAIL" | while IFS= read -r line; do
      echo "  - $line" >&2
    done
    echo "  实验参数应通过 config.json 传入，禁止使用 cfg.get 默认值" >&2
    return 1
  fi

  echo -e "$check_name\tPASS\t无实验参数 cfg.get 默认值" >&2
  return 0
}

# ── G-no-fallback: 扫吞错的 except（no-fallback 三原则） ──
check_no_fallback() {
  set -e
  local repo_root="${1:-.}"
  local scan_script="$SCRIPT_DIR/scan_no_fallback.py"

  if [[ ! -f "$scan_script" ]]; then
    row "G-no-fallback" SKIP "scan_no_fallback.py not found"
    return 0
  fi
  if [[ ! -d "$repo_root/workspace" ]]; then
    row "G-no-fallback" SKIP "No workspace/ found"
    return 0
  fi

  local scan_out
  scan_out="$(cd "$repo_root" && python3 "$scan_script" "$repo_root" 2>&1)" || true

  if echo "$scan_out" | grep -qE '\[WARN\] '; then
    row "G-no-fallback" FAIL "发现吞错 except（无 # optional: 标记）；见 scan_no_fallback 输出"
    echo "$scan_out" | grep -E '\[WARN\] ' | head -5 | sed 's/^/  /' >&2
    return 1
  fi
  row "G-no-fallback" PASS "无吞错 except"
  return 0
}

# ── 1d. G-repro-env 和 G-repro-cli（config-only 复现机制）──
if [[ -f train.py ]]; then
  if check_repro_env .; then
    : # PASS
  else
    row G_repro_env FAIL "见 G-repro-env 检查"
  fi
  if check_repro_cli train.py; then
    : # PASS
  else
    row G_repro_cli FAIL "见 G-repro-cli 检查"
  fi
  if check_cfg_no_defaults .; then
    : # PASS
  else
    row G_cfg_no_defaults FAIL "见 G-cfg-no-defaults 检查"
  fi
  if check_no_fallback .; then
    : # PASS
  else
    row G_no_fallback FAIL "见 G-no-fallback 检查"
  fi
fi

# ── 1d. 项目文档目录（提醒人工判断，不改变 layout 判据）──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]]; then
  _found_doc_dirs=()
  for _dd in docs doc documentation; do
    if [[ -d "$_dd" ]]; then
      _found_doc_dirs+=("$_dd/")
    fi
  done
  if [[ ${#_found_doc_dirs[@]} -gt 0 ]]; then
    _doc_detail=""
    for _dd in "${_found_doc_dirs[@]}"; do
      _dd="${_dd%/}"
      _dc="$(find "$_dd" -type f 2>/dev/null | wc -l | tr -d ' ')"
      _doc_detail="${_doc_detail}${_dd}/(${_dc} files) "
    done
    row project_docs WARN \
      "发现项目文档: ${_doc_detail}— 可能是实验/领域记录，请自行判断是否保留；layout 仍按 verify 白名单"
  fi
fi

# ── 1c. git 仓库与迁后摘要（业务仓）──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]]; then
  if git rev-parse --is-inside-work-tree &>/dev/null; then
    row git_repo PASS "git work tree"
  else
    row git_repo FAIL "非 git 仓库 — 迁后须 git init（见 CHECKLIST §0）"
  fi
  if [[ -s .auto-nn/migration-summary.md ]]; then
    row migration_summary PASS ".auto-nn/migration-summary.md 已落盘"
  else
    row migration_summary FAIL "缺少或非空 .auto-nn/migration-summary.md"
  fi
  if [[ ! -f scripts/validate-init-qa-log.py ]]; then
    row init_qa_log WARN "缺少 validate-init-qa-log.py — 无法校验问答 log"
  else
    set +e
    _iql_out="$(python3 scripts/validate-init-qa-log.py --repo-root . --require-closed 2>&1)"
    _iql_rc=$?
    set -e
    if [[ $_iql_rc -eq 0 ]]; then
      row init_qa_log PASS "init-qa-log 已闭合"
    else
      row init_qa_log WARN "init-qa-log: ${_iql_out//$'\n'/; }"
    fi
  fi
  if [[ ! -f scripts/append-skill-activity.py ]]; then
    row skill_activity_log WARN "缺少 append-skill-activity.py"
  elif ! _sal="$(python3 scripts/append-skill-activity.py status --repo-root . 2>&1)"; then
    row skill_activity_log WARN "skill-activity status 失败: ${_sal}"
  elif echo "$_sal" | grep -q "enabled=false"; then
    row skill_activity_log WARN "safety.skill_activity_log=false（活动 log 已关）"
  else
    row skill_activity_log PASS "${_sal}"
  fi
fi

# ── 1e. PDH plain-anchor（Plain-Discovery Heuristic v2, 2026-07-06 spec §4.4）──
# 仅在触发轮（RUN CONTEXT 含 plain-anchor-init / plain-anchor-check）校验 EXPERIENCE.md
# Tier 矩阵 P 行 4 字段；非触发轮不校验；缺字段仅 WARN 不 FAIL。
check_PDH_plain_anchor() {
  local _rc_path="saved/run_context.md"
  local _is_trigger=0
  if [[ -f "$_rc_path" ]]; then
    if grep -qE "^### plain-anchor-init" "$_rc_path" 2>/dev/null \
       || grep -qE "^### plain-anchor-check" "$_rc_path" 2>/dev/null; then
      _is_trigger=1
    fi
  fi
  if [[ $_is_trigger -eq 0 ]]; then
    # ── round==1 例行 WARN:v0 2026-07-07 PDH BAS 第一轮主动触发 ──
    # 新业务仓 round=1 时,如未主动 emit plain-anchor-init 且仓尚无 plain_anchor,
    # 即漏了 BAS 主动 trigger;报 WARN 提醒人/agent 补 plain,不阻断 doctor。
    if [[ "${PDH_CURRENT_ROUND:-1}" == "1" ]]; then
      local _plain_existing=""
      if [[ -f "saved/plain_anchor.json" ]]; then
        _plain_existing="$(grep -o 'plain_anchor_value[^,}]*' "saved/plain_anchor.json" 2>/dev/null | head -1 | awk -F: '{print $2}' || true)"
      fi
      if [[ -z "$_plain_existing" ]]; then
        row "PDH_plain_anchor" WARN "round=1 且仓无 plain_anchor，run_context.md 缺 plain-anchor-init 段（BAS 主动 trigger 漏发）"
        return 0
      fi
    fi
    return 0  # 非 round=1 且非触发轮不校验
  fi
  if [[ ! -f EXPERIENCE.md ]]; then
    row "PDH_plain_anchor" WARN "触发轮缺 EXPERIENCE.md"
    return 0
  fi
  local _tier_block
  _tier_block="$(awk '/^## Tier 状态/{flag=1; next} flag && /^## /{exit} flag' EXPERIENCE.md 2>/dev/null || true)"
  if [[ -z "$_tier_block" ]]; then
    row "PDH_plain_anchor" WARN "触发轮缺 ## Tier 状态 段"
    return 0
  fi
  # 取 Tier 表 E 行 P 列（行内 `|` 数 = 6 → 第 5 个字段；awk 默认首字段为空故 $6）
  local _p_cell
  _p_cell="$(echo "$_tier_block" | awk -F'|' '/^\| E +\|/ {n=split($0, a, "|"); gsub(/^ +| +$/, "", a[n-1]); print a[n-1]}' 2>/dev/null || true)"
  if [[ -z "$_p_cell" || "$_p_cell" == "-" ]]; then
    row "PDH_plain_anchor" WARN "触发轮 Tier 矩阵 P 列为空/-（缺 4 字段：plain_anchor_value / plain_recipe / plain_budget / plain_why）"
    return 0
  fi
  local _missing=()
  local _field
  for _field in plain_anchor_value plain_recipe plain_budget plain_why; do
    if ! echo "$_p_cell" | grep -q "$_field"; then
      _missing+=("$_field")
    fi
  done
  if [[ ${#_missing[@]} -gt 0 ]]; then
    row "PDH_plain_anchor" WARN "触发轮 P 行缺字段: ${_missing[*]}（不阻断，可下轮补）"
  else
    row "PDH_plain_anchor" PASS "P 行 4 字段齐"
  fi
  return 0
}
check_PDH_plain_anchor

# ── 1f. ledger.watchlist (v1.2.0 inline gate; NN-LEDBOOK spec) ──
# 校验 nn-config.yaml 的 ledger.watchlist 段: 必为 list、字符串、非空、无重、长度 ≤ 10、
# 不与 contract.metric_keys / auxiliary_keys 重叠。
check_ledger_watchlist() {
  local repo_root="${1:-$(pwd)}"
  local nn_cfg="$repo_root/nn-config.yaml"
  local label="ledger_watchlist"

  if [[ ! -f "$nn_cfg" ]]; then
    row "$label" WARN "no nn-config.yaml; watchlist = () (no params tracked)"
    return 0
  fi

  local yaml_out
  yaml_out="$(python3 -c "
import sys, yaml
from pathlib import Path
sys.path.insert(0, '$SCRIPT_DIR')
from lib.nn_config import load_nn_config
cfg = load_nn_config(Path('$repo_root'))
wl = (cfg.get('ledger') or {}).get('watchlist')
print(repr(wl))
" 2>/dev/null)"
  local yaml_rc=$?
  if [[ $yaml_rc -ne 0 ]]; then
    row "$label" WARN "nn-config.yaml 解析失败; skip"
    return 0
  fi

  if [[ "$yaml_out" == "None" ]]; then
    row "$label" WARN "no ledger section; watchlist = () (no params tracked)"
    return 0
  fi

  # 校验 list + 非空字符串 + 无重复 + 长度 ≤ 10 + 不与 metric/aux 重叠
  local py_out py_rc
  set +e
  py_out="$(python3 - "$nn_cfg" <<'PYEOF'
import sys
from pathlib import Path
_repo = Path(sys.argv[1]).resolve().parent
sys.path.insert(0, str(_repo / 'scripts'))
from lib.nn_config import load_nn_config
cfg = load_nn_config(_repo)
wl = (cfg.get('ledger') or {}).get('watchlist')
errs = []
if not isinstance(wl, list):
    errs.append(f"watchlist 必为 list, got {type(wl).__name__}")
else:
    for x in wl:
        if not isinstance(x, str) or not x.strip():
            errs.append(f"watchlist 含非字符串或空: {x!r}")
    if len(wl) != len(set(wl)):
        errs.append(f"watchlist 有重复: {wl}")
    if len(wl) > 10:
        errs.append(f"watchlist len={len(wl)} > 10 (建议沉到 _all_cfg.json)")
    try:
        import os, sys
        if sys.argv[1] and sys.argv[1] not in ('', '.'):
            _p = os.path.dirname(os.path.abspath(sys.argv[1]))
            if _p and _p not in sys.path:
                sys.path.insert(0, _p)
        from contract import metric_keys, auxiliary_keys
        overlap = set(wl) & (set(metric_keys) | set(auxiliary_keys))
        if overlap:
            errs.append(f"watchlist 与 metric/aux 重叠: {overlap}")
    except ImportError:
        pass
for e in errs:
    print(e)
sys.exit(1 if errs else 0)
PYEOF
)"
  py_rc=$?
  set -e

  if [[ $py_rc -ne 0 ]]; then
    row "$label" FAIL "$py_out"
    return 1
  fi
  row "$label" PASS ""
  return 0
}
check_ledger_watchlist

# ── 1g. baseline_tag（② 层2 契约：每实验 config.json 有 baseline_tag 字段）──
check_baseline_tag() {
  local _cfg _found=0 _warn=0
  shopt -s nullglob
  for _cfg in _runs/exp/*/config.json; do
    _found=1
    if ! grep -q '"baseline_tag"' "$_cfg" 2>/dev/null; then
      row "baseline_tag" WARN "config.json 缺 baseline_tag 字段: ${_cfg#_runs/exp/}（finalize_run 应兜底 none）"
      _warn=1
    fi
  done
  shopt -u nullglob
  [[ $_found -eq 0 ]] && return 0
  # results.tsv：缺 baseline_tag 列 → WARN（全体；runner 另有 adapter_baseline_tag FAIL）
  if [[ -f _runs/results.tsv ]]; then
    if ! head -1 _runs/results.tsv 2>/dev/null | grep -qE '(^|\t)baseline_tag(\t|$)'; then
      row "baseline_tag" WARN "results.tsv 表头缺 baseline_tag 列（E5 系统列；regen 或补 ledger.watchlist）"
      _warn=1
    else
      local _col _bad
      _col="$(head -1 _runs/results.tsv | awk -F'\t' '{for(i=1;i<=NF;i++)if($i=="baseline_tag"){print i; exit}}')"
      _bad="$(awk -F'\t' -v c="$_col" 'NR>1 && $c!="" && $c!~/^(plain|reference|none)$/{print $c}' _runs/results.tsv 2>/dev/null | sort -u | paste -sd, -)"
      if [[ -n "$_bad" ]]; then
        row "baseline_tag" WARN "results.tsv baseline_tag 列越界值: $_bad（应为 plain/reference/none）"
        _warn=1
      fi
    fi
  fi
  [[ $_warn -eq 0 ]] && row "baseline_tag" PASS "config.json baseline_tag 字段齐"
  return 0
}
check_baseline_tag

# ── 1g-b. runner 出分（EVALUATE_RUNNER）baseline_tag 列/watchlist 硬 FAIL ──
# 行名 adapter_baseline_tag 为兼容遗留（≠ 立项 ADAPTER 场景）
check_adapter_baseline_tag() {
  local _result _status _msg
  _result="$(python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, '$SCRIPT_DIR')
from lib.adapter_accept import evaluate_runner_baseline_tag_doctor
status, msg = evaluate_runner_baseline_tag_doctor(Path('.').resolve())
if status is not None:
    print(f'{status}|{msg}')
" 2>/dev/null)" || return 0
  [[ -n "$_result" ]] || return 0

  _status="${_result%%|*}"
  _msg="${_result#*|}"
  row "adapter_baseline_tag" "$_status" "$_msg"
  return 0
}
check_adapter_baseline_tag

# ── 1g-c. runner 出分空串 CLI 透传硬 FAIL ──
# 行名 adapter_cli_empty 为兼容遗留
check_adapter_cli_empty() {
  local _result _status _msg
  _result="$(python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, '$SCRIPT_DIR')
from lib.adapter_accept import adapter_cli_empty_doctor
status, msg = adapter_cli_empty_doctor(Path('.').resolve())
if status is not None:
    print(f'{status}|{msg}')
" 2>/dev/null)" || return 0
  [[ -n "$_result" ]] || return 0

  _status="${_result%%|*}"
  _msg="${_result#*|}"
  row "adapter_cli_empty" "$_status" "$_msg"
  return 0
}
check_adapter_cli_empty

# ── 1g-c2. framework 接入总表（contract/framework_binding.yaml）──
check_framework_binding() {
  local _line _name _status _msg rest
  while IFS= read -r _line; do
    [[ -n "$_line" ]] || continue
    _name="${_line%%|*}"
    rest="${_line#*|}"
    _status="${rest%%|*}"
    _msg="${rest#*|}"
    row "$_name" "$_status" "$_msg"
  done < <(python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, '$SCRIPT_DIR')
from lib.framework_binding import framework_binding_doctor
for name, status, msg in framework_binding_doctor(Path('.').resolve()):
    print(f'{name}|{status}|{msg}')
" 2>/dev/null)
  return 0
}
check_framework_binding

# ── 1g-d. 辅指标近轮恒 0 软 WARN（不 FAIL；合法真零可忽略）──
check_aux_always_zero() {
  local _result _status _msg
  [[ -f _runs/results.tsv ]] || return 0
  _result="$(python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, '$SCRIPT_DIR')
from lib.metric_analysis import warn_aux_metrics_always_zero
ws = warn_aux_metrics_always_zero(Path('.').resolve())
if ws:
    print('WARN|' + '; '.join(w.replace('WARN: ', '', 1) for w in ws))
" 2>/dev/null)" || return 0
  [[ -n "$_result" ]] || return 0
  _status="${_result%%|*}"
  _msg="${_result#*|}"
  row "aux_always_zero" "$_status" "$_msg"
  return 0
}
check_aux_always_zero

check_baseline_reference() {
  # ③-i：EXPERIENCE「基线锚点（external reference）」段——段在则校验 reference_anchor_value 值域（float），
  # 段不在不报（novel/无公开参照是常态）。WARN 不 FAIL（与 check_baseline_tag / check_PDH_plain_anchor 同级）。
  [[ -f EXPERIENCE.md ]] || return 0
  local _block
  # 截取「## 基线锚点」段（含表头行，到下一个顶层 ## 或 EOF）
  _block="$(awk '/^## 基线锚点/{f=1} f{print} f&&/^## /&&!/^## 基线锚点/{exit}' EXPERIENCE.md 2>/dev/null || true)"
  if ! echo "$_block" | grep -q 'reference_anchor_value'; then
    return 0  # 段缺失或段内无该字段 → novel 常态，不报
  fi
  local _val
  _val="$(echo "$_block" | grep -oE 'reference_anchor_value[[:space:]]*[:：=][[:space:]]*[^[:space:]]+' | head -1 | sed -E 's/.*[:：=][[:space:]]*//')"
  if ! printf '%s' "$_val" | grep -qE '^-?[0-9]+(\.[0-9]+)?([eE][-+]?[0-9]+)?$'; then
    row "baseline_reference" WARN "EXPERIENCE「基线锚点」段 reference_anchor_value 非合法 float（值='$_val'）；应为数字，novel/无公开参照则整段省略"
    return 0
  fi
  row "baseline_reference" PASS "基线锚点 reference_anchor_value 合法 float"
  return 0
}
check_baseline_reference

# ── 2. TSV 表头 ──
if [[ $IS_TEMPLATE_ROOT -eq 1 ]]; then
  : # 模板根跳过
elif [[ ! -f _runs/results.tsv ]]; then
  row tsv_header WARN "缺少 _runs/results.tsv"
elif [[ ! -f scripts/regen_results_tsv.py ]]; then
  row tsv_header WARN "缺少 regen_results_tsv.py"
else
  set +e
  expected="$(python3 scripts/regen_results_tsv.py --repo-root . --header-only 2>/dev/null)"
  actual="$(head -1 _runs/results.tsv)"
  set -e
  if [[ -z "$expected" ]]; then
    row tsv_header WARN "regen --header-only 无输出（contract 未就绪？）"
  elif [[ "$expected" == "$actual" ]]; then
    row tsv_header PASS "表头与 contract 一致（${#actual} 列）"
  else
    row tsv_header FAIL "表头不一致 — 运行: python3 scripts/regen_results_tsv.py --repo-root ."
  fi
fi

# ── 2b. 立项延后表头标记 ──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]]; then
  if [[ -f _runs/.tsv-header-pending ]]; then
    row tsv_header_pending FAIL "仍存在 — regen_results_tsv.py 后 rm _runs/.tsv-header-pending"
  else
    row tsv_header_pending PASS "无 .tsv-header-pending"
  fi
fi

# ── 2c. 场景完整性（F1 / nn-config / TSV / keepers）──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]]; then
  if [[ -f scripts/scenario_completeness_gate.py ]]; then
    set +e
    _sc_out="$(python3 scripts/scenario_completeness_gate.py . 2>&1)"
    set -e
    if [[ -z "$_sc_out" ]]; then
      row scenario_completeness PASS "F1 清单、scenario_default、TSV scenario_id、keepers 对齐"
    else
      while IFS= read -r line; do
        [[ -z "$line" ]] && continue
        if [[ "$line" == WARN:* ]]; then
          row scenario_completeness WARN "${line#WARN: }"
        elif [[ "$line" == FAIL:* ]]; then
          row scenario_completeness FAIL "${line#FAIL: }"
        else
          row scenario_completeness WARN "$line"
        fi
      done <<< "$_sc_out"
    fi
  else
    row scenario_completeness WARN "缺少 scripts/scenario_completeness_gate.py — governance-sync"
  fi
fi

# ── 3. 治理 rev 与模板对齐（业务仓）──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]]; then
  if [[ -z "$(nn_resolve_template_root)" ]] || [[ -z "$(nn_state_read governance-rev)" ]]; then
    row governance_rev FAIL "未解析到 template-root 或缺少 governance-rev — 运行 governance-sync.sh（或 export NN_TEMPLATE_ROOT / 跑 install.sh）"
  else
    set +e
    TPKG="$(resolve_template_pkg)"
    tprc=$?
    set -e
    if [[ $tprc -ne 0 ]] || [[ "$TPKG" == INVALID:* ]]; then
      row governance_rev FAIL "template-root 解析到非模板维护仓: $(nn_resolve_template_root)"
    else
      EXPECTED="$(governance_rev_compute "$TPKG")"
      ACTUAL="$(nn_state_read governance-rev)"
      _gov_fail=""
      if [[ "$EXPECTED" != "$ACTUAL" ]]; then
        _gov_fail="rev 不匹配（$ACTUAL != $EXPECTED）"
      elif ! diff -q "$TPKG/profiles.yaml" profiles.yaml >/dev/null 2>&1; then
        _gov_fail="profiles.yaml 与模板不一致"
      elif ! diff -q "$TPKG/scripts/wait-train.sh" scripts/wait-train.sh >/dev/null 2>&1; then
        _gov_fail="wait-train.sh 与模板不一致"
      elif ! diff -q "$TPKG/scripts/nn-doctor.sh" scripts/nn-doctor.sh >/dev/null 2>&1; then
        _gov_fail="nn-doctor.sh 与模板不一致"
      elif ! diff -q "$TPKG/scripts/verify-migration-complete.sh" scripts/verify-migration-complete.sh >/dev/null 2>&1; then
        _gov_fail="verify-migration-complete.sh 与模板不一致"
      fi
      if [[ -n "$_gov_fail" ]]; then
        row governance_rev FAIL "${_gov_fail} — 运行 governance-sync.sh"
      else
        row governance_rev PASS "已与模板同步 (rev=$ACTUAL)"
      fi
    fi
  fi

  # ── 3b. stamp-required 文件齐套（≡ train_runtime；与 governance_rev 并列）──
  check_sync_need_files() {
    if [[ ! -f scripts/lib/governance_sync_manifest.py ]]; then
      row sync_need_files FAIL "缺少 scripts/lib/governance_sync_manifest.py — 运行 governance-sync.sh"
      return 0
    fi
    local _miss _rc
    set +e
    _miss="$(PYTHONPATH=scripts${PYTHONPATH:+:$PYTHONPATH} python3 -c "
from pathlib import Path
from lib.governance_sync_manifest import missing_stamp_required
m = missing_stamp_required(Path('.').resolve())
print(','.join(m))
" 2>/dev/null)"
    _rc=$?
    set -e
    if [[ $_rc -ne 0 ]]; then
      row sync_need_files FAIL "无法枚举 stamp-required — 检查 scripts/lib/governance_sync_manifest.py + PyYAML"
      return 0
    fi
    if [[ -n "${_miss}" ]]; then
      row sync_need_files FAIL "缺: ${_miss} — 运行 governance-sync.sh"
    else
      row sync_need_files PASS "stamp-required（train_runtime）文件齐"
    fi
  }
  check_sync_need_files
fi

# ── 3b. 模板版本 stamp（业务仓）──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]]; then
  if [[ -f .auto-nn/version ]]; then
    TV="$(nn_state_read version)"
    if [[ "$TV" =~ ^[0-9]+\.[0-9]+\.[0-9]+\+[0-9a-f]+$ ]] || [[ "$TV" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
      row template_version PASS "Template version: $TV"
    else
      row template_version WARN "Template version 格式异常: $TV"
    fi
  else
    row template_version WARN "缺少 .auto-nn/version — 业务仓未 init，请跑 /auto-nn-init 或 auto-nn-update"
  fi
  # 立项原始戳（write-once；与当前 version 正交）
  INIT_TV="$(nn_state_read init-template-version)"
  if [[ -n "$INIT_TV" ]]; then
    CUR_TV="$(nn_state_read version)"
    row init_template_version PASS "立项原始模板戳 init=${INIT_TV} current=${CUR_TV:-?}（只写一次，勿手改）"
  else
    row init_template_version WARN "无立项原始模板戳 .auto-nn/init-template-version（旧仓或未走 new-project/首 sync；勿用当前 version 盲目回填）"
  fi
fi

# ── 4. nn-config profile ──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]]; then
  if [[ ! -f nn-config.yaml ]]; then
    row nn_config FAIL "缺少 nn-config.yaml"
  else
    set +e
    PROFILE="$(python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, '$SCRIPT_DIR')
from lib.nn_config import load_nn_config
cfg = load_nn_config(Path('.'))
print(cfg.get('profile', ''))
" 2>/dev/null || true)"
    set -e
    if [[ -z "$PROFILE" ]]; then
      row nn_config FAIL "无法解析 profile"
    else
      row nn_config PASS "profile=$PROFILE"
    fi
  fi
fi

# ── 4a. goal_status（nn-config agent.goal_value；信息性，未配则 SKIP）──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]] && [[ -f scripts/check_goal.py ]]; then
  set +e
  _goal_out="$(python3 scripts/check_goal.py . 2>/dev/null)"
  _goal_rc=$?
  set -e
  case "$_goal_rc" in
    2)
      if [[ "$_goal_out" == GOAL_SKIPPED_EXPLORE* ]]; then
        row goal_status INFO "探索期跳过 goal 硬停（${_goal_out//[$'\t\r\n']/ }）"
      else
        row goal_status INFO "未设 goal_value（loop 跑满 N；/auto-nn-goal set）"
      fi
      ;;
    0)
      row goal_status PASS "达标: ${_goal_out//[$'\t\r\n']/ }"
      ;;
    1)
      row goal_status INFO "未达: ${_goal_out//[$'\t\r\n']/ }"
      ;;
    *)
      row goal_status WARN "check_goal.py 异常（rc=${_goal_rc}）"
      ;;
  esac
  unset _goal_out _goal_rc
fi

# ── 4a'. goal_spec_status（v3 goal_spec；与 v2 goal_status 并存）──
goal_spec_status="none"
if python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, '$SCRIPT_DIR')
from lib.nn_config import load_nn_config
p = Path('nn-config.yaml')
if not p.is_file():
    sys.exit(0)
cfg = load_nn_config(Path('.'))
goal = cfg.get('goal') or {}
agent = cfg.get('agent') or {}
if isinstance(agent.get('goal_spec'), dict) and agent.get('goal_spec'):
    print('v3_active')
    sys.exit(0)
gv = goal.get('target', goal.get('value'))
sg = goal.get('per_scenario') or goal.get('scenario_goals') or {}
if gv is not None or sg:
    print('v2_legacy')
else:
    print('none')
" 2>/dev/null | grep -q "v3_active"; then
    goal_spec_status="v3_active"
elif python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, '$SCRIPT_DIR')
from lib.nn_config import load_nn_config
p = Path('nn-config.yaml')
if not p.is_file():
    sys.exit(0)
cfg = load_nn_config(Path('.'))
goal = cfg.get('goal') or {}
gv = goal.get('target', goal.get('value'))
sg = goal.get('per_scenario') or goal.get('scenario_goals') or {}
sys.exit(0 if (gv is not None or sg) else 1)
" 2>/dev/null; then
    # v2 字段有 goal；进一步判定是否模板已支持 v3（v2_legacy vs v2_with_v3_available）
    if [[ -f scripts/lib/goal_spec.py ]] || [[ -f template/package/scripts/lib/goal_spec.py ]]; then
        goal_spec_status="v2_with_v3_available"
    else
        goal_spec_status="v2_legacy"
    fi
fi
printf 'goal_spec_status: %s\n' "$goal_spec_status"

# ── 4b. experiment_mode_status（exploration_mode via resolve_exploration）──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]] && [[ -f scripts/lib/experiment_mode.py ]]; then
  set +e
  _em_out="$(python3 -c "
import sys
sys.path.insert(0, 'scripts')
from pathlib import Path
from lib.experiment_mode import resolve_exploration
r = resolve_exploration(Path('.'))
print(
    f'mode={r.mode} resolved={r.resolved_mode} '
    f'skip_goal={str(r.skip_goal_stop).lower()} '
    f'innovate_boost={str(r.innovate_prompt_boost).lower()}'
)
" 2>/dev/null)"
  _em_rc=$?
  _goal_set="$(python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, 'scripts')
from lib.run_ledger_summary import _load_goal_section, has_any_configured_goal
p = Path('nn-config.yaml')
if not p.is_file():
    print('0')
else:
    print('1' if has_any_configured_goal(_load_goal_section(Path('.'))) else '0')
" 2>/dev/null || echo 0)"
  set -e
  if [[ $_em_rc -ne 0 ]] || [[ -z "$_em_out" ]]; then
    row experiment_mode_status WARN "resolve_exploration 异常（检查 exploration_mode）"
  elif [[ "$_em_out" == *"skip_goal=true"* ]] && [[ "$_goal_set" == "1" ]]; then
    row experiment_mode_status WARN "${_em_out}（explore 已设 goal，loop 不 goal 硬停；/auto-nn-goal clear）"
  else
    row experiment_mode_status PASS "$_em_out"
  fi
  unset _em_out _em_rc _goal_set
fi

# ── 4b2. auto_mode_lib（finalize_round / auto 升档依赖 scripts/lib/auto_mode.py）──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]]; then
  if [[ -f scripts/lib/auto_mode.py ]]; then
    row auto_mode_lib PASS "scripts/lib/auto_mode.py 存在"
  else
    row auto_mode_lib FAIL "缺少 scripts/lib/auto_mode.py — 请 governance-sync / auto-nn-update"
  fi
fi

# ── 4b1. legacy_mode_fields（v1.21.0 收口 6 档后，agent.exploration_style /
# agent.experiment_mode 为死字段；残留即 schema drift，FAIL）──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]] && [[ -f nn-config.yaml ]]; then
  set +e
  _lm_out="$(python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, '$SCRIPT_DIR')
from lib.nn_config import load_nn_config
cfg = load_nn_config(Path('.'))
agent = cfg.get('agent') or {}
legacy = []
if 'exploration_style' in agent:
    legacy.append(f'exploration_style={agent[\"exploration_style\"]!r}')
if 'experiment_mode' in agent:
    legacy.append(f'experiment_mode={agent[\"experiment_mode\"]!r}')
print('|'.join(legacy))
" 2>/dev/null)"
  set -e
  if [[ -n "$_lm_out" ]]; then
    row legacy_mode_fields FAIL "nn-config.yaml 残留死字段: ${_lm_out} — v1.21.0 起仅用顶层 exploration_mode（6 档：careful/optimize/innovate/aggressive/explore/auto）；删除或迁移"
  else
    row legacy_mode_fields PASS "无 agent.exploration_style / agent.experiment_mode 死字段"
  fi
  unset _lm_out
fi

# ── 4b2. exploration_mode_value（v1.21.0 单旋钮 6 档；顶层 exploration_mode
# 须在 _MODE_DEFAULTS.keys() 内）──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]] && [[ -f nn-config.yaml ]]; then
  set +e
  _emv_out="$(python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, '$SCRIPT_DIR')
from lib.nn_config import load_nn_config
from lib.presets import _MODE_DEFAULTS
cfg = load_nn_config(Path('.'))
# 2026-07-15: exploration_mode 是顶层字段，不是 agent.* 下
em = cfg.get('exploration_mode')
if em is None:
    print('NONE')
else:
    valid = sorted(_MODE_DEFAULTS.keys())
    em_s = str(em).strip()
    if em_s in valid:
        print('OK:' + em_s)
    else:
        print('BAD:' + em_s + '|valid=' + ','.join(valid))
" 2>/dev/null)"
  _emv_rc=$?
  set -e
  if [[ $_emv_rc -ne 0 ]]; then
    row exploration_mode_value WARN "解析 exploration_mode 失败"
  elif [[ "$_emv_out" == "NONE" ]]; then
    row exploration_mode_value PASS "未设 exploration_mode（用 default_for_mode optimize 兜底）"
  elif [[ "$_emv_out" == OK:* ]]; then
    row exploration_mode_value PASS "exploration_mode=${_emv_out#OK:}"
  else
    # BAD:inductive|valid=...
    _bad="${_emv_out#BAD:}"
    _val="${_bad%%|*}"
    _hint="${_bad#*|}"
    row exploration_mode_value FAIL "exploration_mode=${_val} 不在 6 档内（${_hint#valid=}）；v1.21.0 起仅 6 档"
  fi
  unset _emv_out _emv_rc _bad _val _hint
fi

# ── 4c. metric_floor_status（explore 底线护栏；信息性，未配则 SKIP）──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]] && [[ -f scripts/check_metric_floor.py ]]; then
  set +e
  _floor_out="$(python3 scripts/check_metric_floor.py . 2>/dev/null)"
  _floor_rc=$?
  set -e
  case "$_floor_rc" in
    2)
      row metric_floor_status SKIP "未配 explore 底线或未进入 explore"
      ;;
    0)
      row metric_floor_status PASS "${_floor_out//[$'\t\r\n']/ }"
      ;;
    1)
      row metric_floor_status INFO "${_floor_out//[$'\t\r\n']/ }"
      ;;
    *)
      row metric_floor_status WARN "check_metric_floor.py 异常（rc=${_floor_rc}）"
      ;;
  esac
  unset _floor_out _floor_rc
fi

# ── 5. contract / 门面 / G-封装 / G-评估（业务仓）──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]]; then
  run_check contract_layout env PYTHONPATH=. python3 -c "
from experiment import check_contract_layout
v = check_contract_layout('.')
assert not v, v
"
  if [[ -f train.py ]]; then
    run_check train_encapsulation env PYTHONPATH=. python3 -c "
from experiment import check_train_encapsulation
v = check_train_encapsulation('.')
assert not v, v
"
  else
    row train_encapsulation SKIP "无 train.py"
  fi
  run_check train_exp_dir env PYTHONPATH=. python3 -c "
from experiment import check_train_exp_dir_layout
v = check_train_exp_dir_layout('.')
assert not v, [(x.rule, x.detail) for x in v]
"
  run_check profile_facade env PYTHONPATH=. python3 -c "
from experiment import check_profile_facade
v = check_profile_facade('.')
assert not v, [(x.rule, x.detail) for x in v]
"
  run_check test_authority env PYTHONPATH=. python3 -c "
from experiment import check_test_authority
v = check_test_authority('.')
assert not v, v
"
  # G-信息权限（IP0–IP5；无 env 开关，只认 contract/runtime.py INFO_PERM）
  if [[ -f scripts/lib/info_perm.py ]]; then
    run_check info_perm python3 scripts/lib/info_perm.py .
  else
    row info_perm SKIP "无 scripts/lib/info_perm.py（先 governance-sync）"
  fi
fi

# ── 5b1. scenario_not_in_contract（场景号不得回潮进 contract）──
check_scenario_not_in_contract() {
  [[ $IS_TEMPLATE_ROOT -eq 0 ]] || return 0
  if [[ ! -d contract ]]; then
    row scenario_not_in_contract PASS "无 contract/ 目录"
    return 0
  fi
  if [[ ! -f scripts/lib/scenario_contract_guard.py ]]; then
    row scenario_not_in_contract WARN "缺少 scripts/lib/scenario_contract_guard.py — governance-sync"
    return 0
  fi
  local _scn_out _scn_rc
  set +e
  _scn_out="$(python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, '$SCRIPT_DIR')
from lib.scenario_contract_guard import find_scenario_id_in_contract
v = find_scenario_id_in_contract(Path('.').resolve())
if v:
    print('; '.join(v), file=sys.stderr)
    sys.exit(1)
" 2>&1)"
  _scn_rc=$?
  set -e
  if [[ $_scn_rc -eq 0 ]]; then
    row scenario_not_in_contract PASS "contract 无 SCENARIO_ID 回潮"
  else
    row scenario_not_in_contract FAIL "${_scn_out//$'\n'/; }"
  fi
}
check_scenario_not_in_contract

# ── 5b0. cfg_path_fallback（禁 env/绝对路径写入全大写 cfg 键）──
check_cfg_path_fallback() {
  [[ $IS_TEMPLATE_ROOT -eq 0 ]] || return 0
  if [[ ! -f train.py ]] && [[ ! -d workspace ]]; then
    row cfg_path_fallback SKIP "无 train.py / workspace/"
    return 0
  fi
  if [[ ! -f scripts/lib/scan_cfg_path_fallback.py ]]; then
    row cfg_path_fallback WARN "缺少 scripts/lib/scan_cfg_path_fallback.py — governance-sync"
    return 0
  fi
  local _cpf_out _cpf_rc
  set +e
  _cpf_out="$(python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, '$SCRIPT_DIR')
from lib.scan_cfg_path_fallback import find_cfg_path_fallback_violations
v = find_cfg_path_fallback_violations(Path('.').resolve())
if v:
    print('; '.join(v), file=sys.stderr)
    sys.exit(1)
" 2>&1)"
  _cpf_rc=$?
  set -e
  if [[ $_cpf_rc -eq 0 ]]; then
    row cfg_path_fallback PASS "train/workspace 无 env/绝对路径 cfg 兜底"
  else
    row cfg_path_fallback FAIL "${_cpf_out//$'\n'/; }"
  fi
}
check_cfg_path_fallback

# ── 5b0b. shared_context_contract（禁袋内 contract 实例）──
check_shared_context_contract() {
  [[ $IS_TEMPLATE_ROOT -eq 0 ]] || return 0
  if [[ ! -f train.py ]] && [[ ! -d workspace ]] && [[ ! -d contract ]]; then
    row shared_context_contract SKIP "无 train.py / workspace/ / contract/"
    return 0
  fi
  if [[ ! -f scripts/lib/scan_shared_context_contract.py ]]; then
    row shared_context_contract WARN "缺少 scripts/lib/scan_shared_context_contract.py — governance-sync"
    return 0
  fi
  local _scc_out _scc_rc
  set +e
  _scc_out="$(python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, '$SCRIPT_DIR')
from lib.scan_shared_context_contract import find_shared_context_contract_violations
v = find_shared_context_contract_violations(Path('.').resolve())
if v:
    print('; '.join(v), file=sys.stderr)
    sys.exit(1)
" 2>&1)"
  _scc_rc=$?
  set -e
  if [[ $_scc_rc -eq 0 ]]; then
    row shared_context_contract PASS "train/workspace/contract 无袋内 contract"
  else
    row shared_context_contract FAIL "${_scc_out//$'\n'/; }"
  fi
}
check_shared_context_contract

# ── 5b0c. time_budget_violations（取值点守卫违约记录；存在即 WARN）──
check_time_budget_violations() {
  [[ $IS_TEMPLATE_ROOT -eq 0 ]] || return 0
  local _tbvl="_runs/time_budget_violations.log"
  if [[ ! -f "$_tbvl" ]]; then
    row time_budget_violations PASS "无守卫违约记录（_runs/time_budget_violations.log 不存在）"
    return 0
  fi
  local _n
  _n="$(grep -c . "$_tbvl" 2>/dev/null || echo 0)"
  if [[ "$_n" -gt 0 ]]; then
    row time_budget_violations WARN "时间预算守卫违约 ${_n} 条（见 $_tbvl；收工审计 scripts/check_time_budget_audit.py）"
  else
    row time_budget_violations WARN "$_tbvl 存在但为空（可人工核看后删除）"
  fi
}
check_time_budget_violations

# ── 5b. contract 演示指标冲突 ──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]] && [[ -n "$PROFILE" ]]; then
  set +e
  _demo_out="$(python3 -c "
from pathlib import Path
import ast, sys
sys.path.insert(0, '$SCRIPT_DIR')
from lib.nn_config import load_nn_config
root = Path('.')
profile = load_nn_config(root).get('profile', '')
keys = set()
mp = root / 'contract' / 'metrics.py'
if mp.is_file():
    mtree = ast.parse(mp.read_text(encoding='utf-8'))
    for node in mtree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in ('METRIC_KEYS', 'AUXILIARY_KEYS'):
                    if isinstance(node.value, ast.Dict):
                        for k in node.value.keys:
                            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                                keys.add(k.value)
src = (root/'contract'/'__init__.py').read_text(encoding='utf-8')
tree = ast.parse(src)
for node in tree.body:
    if isinstance(node, ast.ClassDef):
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == 'metric_keys':
                for sub in ast.walk(item):
                    if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Dict):
                        for k in sub.value.keys:
                            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                                keys.add(k.value)
if profile in ('rl', 'physical') and 'val_accuracy' in keys:
    print('contract 含 val_accuracy 演示指标', file=sys.stderr)
    sys.exit(1)
" 2>&1)"
  _demo_rc=$?
  set -e
  if [[ $_demo_rc -eq 0 ]]; then
    row contract_demo_metrics PASS "与 profile 无演示冲突"
  else
    row contract_demo_metrics FAIL "${_demo_out//$'\n'/; }"
  fi
fi

# ── 5z. EXPERIENCE ↔ TSV 叙事一致性 ──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]] && [[ -f EXPERIENCE.md ]] && [[ -f _runs/results.tsv ]]; then
  _ela_out=""
  _ela_rc=0
  _ela_out="$(python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, 'scripts')
from lib.experience_ledger_audit import audit_experience_vs_tsv
for msg in audit_experience_vs_tsv(Path('.')):
    print('WARN:', msg)
" 2>&1)" || _ela_rc=$?
  if [[ $_ela_rc -ne 0 ]]; then
    row experience_ledger_audit WARN "experience_ledger_audit.py 异常（rc=${_ela_rc}）"
  elif [[ -z "$_ela_out" ]]; then
    row experience_ledger_audit PASS "EXPERIENCE 已试/穷尽声称与 TSV 无冲突"
  else
    _ela_n=0
    while IFS= read -r _ela_line; do
      [[ -z "$_ela_line" ]] && continue
      _ela_msg="${_ela_line#WARN: }"
      row experience_ledger_audit WARN "$_ela_msg"
      _ela_n=$((_ela_n + 1))
      [[ $_ela_n -ge 5 ]] && break
    done <<< "$_ela_out"
  fi
fi

# ── 6. 台账文件 ──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]]; then
  if [[ -f _runs/results.tsv ]]; then
    n="$(wc -l < _runs/results.tsv | tr -d ' ')"
    if [[ "$n" -le 1 ]]; then
      row results_tsv WARN "results.tsv 仅表头或无数据行"
    else
      row results_tsv PASS "$((n - 1)) 行数据"
    fi
  else
    row results_tsv FAIL "缺少 _runs/results.tsv"
  fi
  if [[ -f _runs/results.jsonl ]]; then
    jn="$(wc -l < _runs/results.jsonl | tr -d ' ')"
    row results_jsonl PASS "${jn} 行"
    if [[ -f _runs/results.tsv ]]; then
      tn="$(wc -l < _runs/results.tsv | tr -d ' ')"
      tdata=$((tn - 1))
      if [[ "$tdata" -gt 0 && "$jn" -gt 0 && "$tdata" != "$jn" ]]; then
        row ledger_row_sync WARN "TSV 数据行 ${tdata} != jsonl ${jn} — 考虑 python3 scripts/sync_ledger.py --apply"
      elif [[ "$tdata" -gt 0 ]]; then
        row ledger_row_sync PASS "TSV/jsonl 行数一致 (${tdata})"
      fi
    fi
  else
    row results_jsonl WARN "缺少 _runs/results.jsonl"
  fi
fi

# ── 6a. progress / journal 遗留 ──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]]; then
  if [[ -f progress.txt ]]; then
    row legacy_progress_file WARN "progress.txt 已废弃 — migrate-drop-progress.sh 或删除"
  else
    row legacy_progress_file PASS "无 progress.txt"
  fi
  _journal_tsv_data=0
  if [[ -f _runs/results.tsv ]]; then
    _journal_tn="$(wc -l < _runs/results.tsv | tr -d ' ')"
    if [[ "$_journal_tn" -gt 1 ]]; then
      _journal_tsv_data=$((_journal_tn - 1))
    fi
  fi
  if [[ "$_journal_tsv_data" -gt 0 && ! -f saved/experiment_journal.json ]]; then
    row journal_missing_with_tsv WARN "TSV ${_journal_tsv_data} 行数据但无 saved/experiment_journal.json"
  elif [[ "$_journal_tsv_data" -gt 0 ]]; then
    row journal_missing_with_tsv PASS "journal 与 TSV 数据行共存"
  else
    row journal_missing_with_tsv PASS "无 TSV 数据行或 journal 已存在"
  fi
fi

# ── 6b. 台账 git（训后 commit 闭环）──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]] && git rev-parse --git-dir >/dev/null 2>&1; then
  _ledger_git_warn=""
  for _lf in _runs/results.tsv _runs/results.jsonl; do
    [[ -f "$_lf" ]] || continue
    if ! git ls-files --error-unmatch "$_lf" >/dev/null 2>&1; then
      _ledger_git_warn="${_ledger_git_warn}; ${_lf} 未 track"
      continue
    fi
    if ! git diff --quiet -- "$_lf" 2>/dev/null || ! git diff --cached --quiet -- "$_lf" 2>/dev/null; then
      _ledger_git_warn="${_ledger_git_warn}; ${_lf} 有未 commit 变更"
    fi
  done
  if [[ -n "$_ledger_git_warn" ]]; then
    row ledger_git WARN "台账未入库${_ledger_git_warn} — PROTOCOL §6 步骤 10"
  else
    if [[ -f _runs/results.tsv || -f _runs/results.jsonl ]]; then
      row ledger_git PASS "台账文件已 commit 或无未提交变更"
    fi
  fi
fi

# ── 7. README 项目化 ──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]]; then
  if [[ ! -f README.md ]]; then
    row readme FAIL "缺少 README.md"
  elif head -1 README.md | grep -q '^# auto-nn-experiment$'; then
    row readme FAIL "首行仍为模板标题 — 须重写为目标项目说明"
  else
    row readme PASS "非模板默认标题"
  fi

  if git rev-parse HEAD~1 >/dev/null 2>&1; then
    _rd_contract=0
    _rd_readme=0
    git diff --name-only HEAD~1 HEAD 2>/dev/null | grep -q '^contract/' && _rd_contract=1
    git diff --name-only HEAD~1 HEAD 2>/dev/null | grep -qx 'README.md' && _rd_readme=1
    if [[ $_rd_contract -eq 1 && $_rd_readme -eq 0 ]]; then
      row readme_modify_sync WARN "最近提交改了 contract 但未改 README.md"
    else
      row readme_modify_sync PASS "最近提交 contract/README 同步或无关"
    fi
  else
    row readme_modify_sync PASS "无 HEAD~1，跳过提交同步检查"
  fi

  if [[ -f scripts/readme_consistency_gate.py ]]; then
    set +e
    _rc_out="$(python3 scripts/readme_consistency_gate.py . 2>&1)"
    _rc=$?
    set -e
    if [[ $_rc -eq 0 && -z "$_rc_out" ]]; then
      row readme_consistency PASS "R1–R5 无 FAIL/WARN"
    elif [[ $_rc -eq 0 ]]; then
      row readme_consistency WARN "${_rc_out//$'\n'/; }"
    else
      row readme_consistency FAIL "${_rc_out//$'\n'/; }"
    fi
  fi
fi

# ── 7c. EXPERIENCE 结构（精华置顶 / Tier 状态） ──
if [[ $IS_TEMPLATE_ROOT -eq 0 && -f EXPERIENCE.md ]]; then
  if grep -q 'nn-tier-block' EXPERIENCE.md || grep -qE '^## Tier A–E' EXPERIENCE.md; then
    row experience_structure WARN "含 legacy nn-tier-block 或 Tier A–E 梯子 — 建议 migrate + compress"
  fi
  if ! grep -q '## Tier 状态' EXPERIENCE.md; then
    row experience_structure FAIL "缺少 ## Tier 状态 — compress C2 前置"
  else
    row experience_structure PASS "含 ## Tier 状态"
  fi
  _essence_line=""
  _exp_date_line=""
  _essence_line="$(grep -n '## 精华摘要' EXPERIENCE.md | head -1 | cut -d: -f1 || true)"
  _exp_date_line="$(grep -nE '^## [0-9]{4}-[0-9]{2}-[0-9]{2}' EXPERIENCE.md | head -1 | cut -d: -f1 || true)"
  if [[ -n "$_exp_date_line" && -n "$_essence_line" && "$_exp_date_line" -lt "$_essence_line" ]]; then
    row experience_prepend WARN "实验段出现在 ## 精华摘要 之前（prepend 违规）"
  elif [[ -n "$_essence_line" ]]; then
    row experience_prepend PASS "精华摘要位于实验段之前或未 prepend"
  fi
fi

# ── 7c2. abcde-manual 存在性（形式闸门 #2）──
check_abcde_manual() {
  [[ $IS_TEMPLATE_ROOT -eq 0 ]] || return 0
  if [[ -f references/manual/abcde-manual.md ]]; then
    row abcde_manual PASS "references/manual/abcde-manual.md 存在"
  else
    row abcde_manual FAIL "缺少 references/manual/abcde-manual.md（立项应生成；可跑 init_o3_abcde.py / abcde_migrate.py）"
  fi
}
check_abcde_manual

# ── 7c2b. abcde-manual 卫生（旧名 / 头身冲突；仅 WARN）──
check_abcde_manual_hygiene() {
  [[ $IS_TEMPLATE_ROOT -eq 0 ]] || return 0
  [[ -f references/manual/abcde-manual.md ]] || return 0
  if [[ ! -f scripts/lib/scan_abcde_manual_hygiene.py ]]; then
    row abcde_manual_hygiene WARN "缺少 scripts/lib/scan_abcde_manual_hygiene.py — governance-sync"
    return 0
  fi
  local _out _status _msg
  set +e
  _out="$(python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, '$SCRIPT_DIR')
from lib.scan_abcde_manual_hygiene import doctor_abcde_manual_hygiene
r = doctor_abcde_manual_hygiene(Path('.').resolve())
if r is None:
    sys.exit(2)
print(r[0] + '|' + r[1])
" 2>/dev/null)"
  _rc=$?
  set -e
  if [[ $_rc -eq 2 ]] || [[ -z "$_out" ]]; then
    return 0
  fi
  _status="${_out%%|*}"
  _msg="${_out#*|}"
  row abcde_manual_hygiene "$_status" "$_msg"
}
check_abcde_manual_hygiene

check_baseline_start_intent() {
  [[ $IS_TEMPLATE_ROOT -eq 0 ]] || return 0
  # 仅在 init-qa-log 已闭合时硬闸（立项中途不拦）
  if [[ ! -f .auto-nn/init-qa-log.md ]]; then
    return 0
  fi
  if ! grep -qE '(^| )closed|F1.*close|init-qa-log closed' .auto-nn/init-qa-log.md 2>/dev/null \
     && [[ ! -f scripts/validate-init-qa-log.py ]]; then
    return 0
  fi
  if [[ -f scripts/validate-init-qa-log.py ]]; then
    if ! python3 scripts/validate-init-qa-log.py --repo-root . --require-closed >/dev/null 2>&1; then
      return 0
    fi
  fi
  if [[ -f saved/baseline_start_intent.json ]]; then
    row baseline_start_intent PASS "saved/baseline_start_intent.json 存在"
  elif [[ -f .auto-nn/baseline-intent-skipped ]]; then
    row baseline_start_intent PASS "已显式跳过（baseline-intent-skipped）"
  else
    row baseline_start_intent FAIL "init-qa-log 已闭合但缺尺子意图文件（写 saved/baseline_start_intent.json 或 .auto-nn/baseline-intent-skipped）"
  fi
}
check_baseline_start_intent

# ── 7c2c. init-align 轻闸（缺 WARN / 坏 FAIL / profile 不一致 WARN）──
check_init_align() {
  [[ $IS_TEMPLATE_ROOT -eq 0 ]] || return 0
  if [[ ! -f scripts/init_align.py ]]; then
    row init_align WARN "缺少 scripts/init_align.py — governance-sync"
    return 0
  fi
  local _out _status _msg
  set +e
  _out="$(python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, '$SCRIPT_DIR')
from init_align import doctor_check_init_align
st, msg = doctor_check_init_align(Path('.').resolve())
print(st + '|' + msg)
" 2>/dev/null)"
  _rc=$?
  set -e
  if [[ $_rc -ne 0 ]] || [[ -z "$_out" ]]; then
    row init_align WARN "init_align 检查执行失败"
    return 0
  fi
  _status="${_out%%|*}"
  _msg="${_out#*|}"
  row init_align "$_status" "$_msg"
}
check_init_align

# ── 7d. REFLECT_INDEX 账本健康 ──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]]; then
  if [[ ! -f scripts/summarize-runs.py ]]; then
    row reflect_index WARN "缺少 scripts/summarize-runs.py"
  elif [[ ! -f references/REFLECT_INDEX.md ]]; then
    row reflect_index FAIL "缺少 references/REFLECT_INDEX.md"
  else
    _ri_fail=0
    set +e
    while IFS= read -r _ri_line; do
      [[ -z "$_ri_line" ]] && continue
      case "$_ri_line" in
        PASS:*)
          row reflect_index PASS "${_ri_line#PASS:}"
          ;;
        FAIL:*)
          row reflect_index FAIL "${_ri_line#FAIL:}"
          _ri_fail=1
          ;;
        WARN:*)
          row reflect_index WARN "${_ri_line#WARN:}"
          ;;
        *)
          row reflect_index WARN "${_ri_line}"
          ;;
      esac
    done < <(python3 scripts/summarize-runs.py --reflect-index-health --repo-root . 2>&1)
    set -e
    if [[ $_ri_fail -eq 1 ]] && [[ -x scripts/repair-reflect-index.sh ]]; then
      row reflect_index_repair WARN "可试: bash scripts/repair-reflect-index.sh --apply"
    fi
  fi
fi

# ── 8. auto-run 配套与 shell 语法 ──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]]; then
  if [[ ! -f auto-nn-run.sh ]]; then
    row auto_run_bundle FAIL "缺少 auto-nn-run.sh"
  else
    _agent_need=(
      reflect.py
      scripts/wait-train.sh
      scripts/auto-run-batch-tail.sh
      scripts/claude_stream_summarize.py
      scripts/claude_stream_result_watchdog.py
      scripts/mark_reflect_consumed.py
      scripts/lib/reflect_index.py
      scripts/build-run-context.py
      scripts/human_guidance_gate.py
      scripts/lib/human_guidance_gate.py
      scripts/lib/human_guidance_roadmap.py
      scripts/runtime-activity.py
      scripts/lib/runtime_activity.py
      scripts/refresh-human-guidance-baseline.sh
      scripts/journal_append.py
      scripts/lib/agent_cli.py
      scripts/lib/innovation_fingerprint.py
      scripts/lib/innovation_catalog.yaml
      scripts/lib/external/router.py
      scripts/lib/external/reflect_hook.py
      scripts/external_tool.py
      scripts/check_reflect_runtime.py
    )
    _agent_missing=()
    for need in "${_agent_need[@]}"; do
      [[ -f "$need" ]] || _agent_missing+=("$need")
    done
    if [[ ${#_agent_missing[@]} -gt 0 ]]; then
      row auto_run_bundle FAIL "缺少: ${_agent_missing[*]}"
    else
      chmod +x scripts/wait-train.sh scripts/auto-run-batch-tail.sh scripts/claude_stream_summarize.py scripts/claude_stream_result_watchdog.py 2>/dev/null || true
      if [[ -x scripts/wait-train.sh ]] && [[ -x scripts/auto-run-batch-tail.sh ]] && [[ -x scripts/claude_stream_summarize.py ]] && [[ -x scripts/claude_stream_result_watchdog.py ]]; then
        row auto_run_bundle PASS "g-human/auto-run/journal 脚本齐全"
      else
        row auto_run_bundle FAIL "wait-train、claude_stream_summarize 或 claude_stream_result_watchdog 不可执行"
      fi
    fi
    if [[ -f scripts/check_reflect_runtime.py ]]; then
      set +e
      _rr_fail=0
      while IFS= read -r _rr_line; do
        [[ -z "$_rr_line" ]] && continue
        case "$_rr_line" in
          PASS:*)
            row reflect_runtime PASS "${_rr_line#PASS:}"
            ;;
          FAIL:*)
            row reflect_runtime FAIL "${_rr_line#FAIL:}"
            _rr_fail=1
            ;;
          *)
            row reflect_runtime WARN "$_rr_line"
            ;;
        esac
      done < <(python3 scripts/check_reflect_runtime.py --repo-root . 2>&1)
      set -e
    else
      row reflect_runtime FAIL "缺少 scripts/check_reflect_runtime.py — 请 auto-nn-update"
    fi
    set +e
    _ar_err="$(bash -n auto-nn-run.sh 2>&1)"
    _ar_rc=$?
    set -e
    if [[ $_ar_rc -eq 0 ]]; then
      row auto_run_syntax PASS "auto-nn-run.sh bash -n OK"
    else
      row auto_run_syntax FAIL "${_ar_err//$'\n'/; }"
    fi
    if [[ -f scripts/build-run-context.py ]]; then
      set +e
      _rc_out="$(python3 scripts/build-run-context.py --repo-root . --write 2>&1)"
      _rc_rc=$?
      set -e
      if [[ $_rc_rc -eq 0 && -f saved/run_context.md && -s saved/run_context.md ]]; then
        row run_context PASS "build-run-context --write OK"
      else
        # 2026-07-15: WARN → FAIL。run_context.md/json 是 auto-run batch 启动必需
        # （含 batch_scheduling / gpu_snapshot / keeper_recipe_keys），写失败 = batch 挂。
        row run_context FAIL "${_rc_out:-build-run-context 失败或 run_context.md 为空}"
      fi
    else
      row run_context FAIL "缺少 scripts/build-run-context.py — auto-nn-update"
    fi
    if [[ -f scripts/lib/explore_objective.py ]]; then
      row explore_objective PASS "explore_objective.py 已安装"
      if [[ -f CHECKLIST.md ]]; then
        set +e
        _eo_mode="$(python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, 'scripts')
from lib.explore_objective import objective_mode_from_config, is_migration_in_progress
root = Path('.')
if is_migration_in_progress(root) and objective_mode_from_config(root) == 'explore':
    print('WARN')
else:
    print('OK')
" 2>/dev/null || echo OK)"
        set -e
        if [[ "$_eo_mode" == "WARN" ]]; then
          row explore_objective WARN "迁移中（CHECKLIST.md 存在）应使用 objective_mode=optimize"
        fi
      fi
    else
      row explore_objective WARN "缺少 scripts/lib/explore_objective.py"
    fi
    if [[ -f scripts/human_guidance_gate.py ]]; then
      set +e
      _hg_out="$(python3 scripts/human_guidance_gate.py --repo-root . doctor 2>&1)"
      _hg_rc=$?
      set -e
      if [[ $_hg_rc -eq 0 ]]; then
        if [[ "$_hg_out" == PASS:* ]]; then
          row human_guidance_gate PASS "${_hg_out#PASS: }"
        elif [[ "$_hg_out" == SKIP:* ]]; then
          row human_guidance_gate SKIP "${_hg_out#SKIP: }"
        else
          row human_guidance_gate WARN "${_hg_out#WARN: }"
        fi
      else
        row human_guidance_gate WARN "${_hg_out:-human_guidance_gate doctor 失败}"
      fi
    else
      row human_guidance_gate WARN "缺少 scripts/human_guidance_gate.py"
    fi
    if [[ -f scripts/runtime-activity.py ]]; then
      set +e
      _ra_out="$(python3 scripts/runtime-activity.py --repo-root . --format doctor 2>&1)"
      _ra_rc=$?
      set -e
      if [[ $_ra_rc -eq 0 ]]; then
        if [[ "$_ra_out" == PASS:* ]]; then
          row runtime_activity PASS "${_ra_out#PASS: }"
        elif [[ "$_ra_out" == WARN:* ]]; then
          row runtime_activity WARN "${_ra_out#WARN: }"
        else
          row runtime_activity WARN "${_ra_out:-runtime-activity doctor 输出异常}"
        fi
      else
        row runtime_activity WARN "${_ra_out:-runtime-activity doctor 失败}"
      fi
    else
      row runtime_activity WARN "缺少 scripts/runtime-activity.py"
    fi
    if [[ -f scripts/manual-run-scope-check.sh ]]; then
      set +e
      _msc_out="$(bash scripts/manual-run-scope-check.sh --repo-root . 2>&1)"
      _msc_rc=$?
      set -e
      if [[ "$_msc_out" == FAIL:* ]] || [[ $_msc_rc -eq 2 ]]; then
        if [[ "$_msc_out" == FAIL:*STRICT* ]] || [[ "$_msc_out" == FAIL:*workspace-edit* ]]; then
          row immutable_path_guard PASS "无 IMMUTABLE 路径改动（或已 NN_RELAUNCH）"
          row manual_run_scope_check FAIL "${_msc_out#FAIL: }"
        elif [[ "$_msc_out" == FAIL:* ]]; then
          row immutable_path_guard FAIL "${_msc_out#FAIL: }"
        else
          row immutable_path_guard FAIL "${_msc_out:-manual-run-scope-check 运行失败}"
        fi
      elif [[ "$_msc_out" == WARN:* ]]; then
        row immutable_path_guard PASS "无 IMMUTABLE 路径改动"
        row manual_run_scope_check WARN "${_msc_out#WARN: }"
      elif [[ "$_msc_out" == PASS:* ]]; then
        row immutable_path_guard PASS "无 IMMUTABLE 路径改动"
        row manual_run_scope_check PASS "${_msc_out#PASS: }"
      elif [[ "$_msc_out" == SKIP:* ]]; then
        row immutable_path_guard SKIP "${_msc_out#SKIP: }"
        row manual_run_scope_check SKIP "${_msc_out#SKIP: }"
      elif [[ $_msc_rc -eq 1 ]]; then
        row immutable_path_guard PASS "无 IMMUTABLE 路径改动"
        row manual_run_scope_check WARN "${_msc_out:-manual-run-scope-check 运行失败}"
      else
        row immutable_path_guard PASS "无 IMMUTABLE 路径改动"
        row manual_run_scope_check WARN "${_msc_out:-manual-run-scope-check 运行失败}"
      fi
    else
      row manual_run_scope_check WARN "缺少 scripts/manual-run-scope-check.sh — 请 auto-nn-update"
    fi
  fi

  # v2.5.7: keeper 指针检查（路径硬编码死链 + pointer 不指 TSV 最优）
  if [[ -f scripts/repair_keeper.py ]]; then
    set +e
    _rk_out="$(python3 scripts/repair_keeper.py --check --repo-root . 2>&1)"
    _rk_rc=$?
    set -e
    if [[ "$_rk_out" == FAIL:* ]]; then
      row keeper_stale FAIL "${_rk_out#FAIL: }"
    elif [[ "$_rk_out" == WARN:* ]]; then
      row keeper_stale WARN "${_rk_out#WARN: }"
    elif [[ "$_rk_out" == PASS:* ]]; then
      row keeper_stale PASS "${_rk_out#PASS: }"
    else
      row keeper_stale WARN "${_rk_out:-repair-keeper --check 运行失败}"
    fi
  else
    row keeper_stale WARN "缺少 scripts/repair_keeper.py — 请 auto-nn-update"
  fi

  # v2.8.3: TSV exploration_space 列 RDDN 旧词检查 (extend→derived 等)
  if [[ -f scripts/check_innovation_vocab.py ]]; then
    set +e
    _iv_out="$(python3 scripts/check_innovation_vocab.py --check --repo-root . 2>&1)"
    set -e
    if [[ "$_iv_out" == FAIL:* ]]; then
      row innovation_vocab FAIL "${_iv_out#FAIL: }"
    elif [[ "$_iv_out" == PASS:* ]]; then
      row innovation_vocab PASS "${_iv_out#PASS: }"
    else
      row innovation_vocab WARN "${_iv_out:-check-innovation-vocab 运行失败}"
    fi
  else
    row innovation_vocab WARN "缺少 scripts/check_innovation_vocab.py — 请 auto-nn-update"
  fi

  # 探索格子必打 / 禁 E- / 历史空格 WARN；含 e_feedback.jsonl schema
  if [[ -f scripts/check_exploration_stamp.py ]]; then
    set +e
    _es_out="$(python3 scripts/check_exploration_stamp.py --check --repo-root . 2>&1)"
    set -e
    if [[ "$_es_out" == FAIL:* ]]; then
      row exploration_space_stamp FAIL "${_es_out#FAIL: }"
    elif [[ "$_es_out" == WARN:* ]]; then
      row exploration_space_stamp WARN "${_es_out#WARN: }"
    elif [[ "$_es_out" == PASS:* ]]; then
      row exploration_space_stamp PASS "${_es_out#PASS: }"
    else
      row exploration_space_stamp WARN "${_es_out:-check_exploration_stamp 运行失败}"
    fi
    # 未登记配置键：独立行（勿并入 exploration_space_stamp，避免互相染色）
    set +e
    _urk_out="$(python3 scripts/check_exploration_stamp.py --check-unregistered --repo-root . 2>&1)"
    set -e
    if [[ "$_urk_out" == WARN:* ]]; then
      row unregistered_config_keys WARN "${_urk_out#WARN: }"
    elif [[ "$_urk_out" == PASS:* ]]; then
      row unregistered_config_keys PASS "${_urk_out#PASS: }"
    else
      row unregistered_config_keys PASS "${_urk_out:-无未登记键或跳过}"
    fi
  else
    row exploration_space_stamp WARN "缺少 scripts/check_exploration_stamp.py — 请 auto-nn-update"
    row unregistered_config_keys PASS "缺少 check_exploration_stamp.py — 跳过未登记键检查"
  fi

  _shell_targets=(scripts/wait-train.sh scripts/govern-runs.sh scripts/clear-runs.sh scripts/mark-reflect-consumed.sh scripts/repair-reflect-index.sh)
  _shell_bad=()
  for _sh in "${_shell_targets[@]}"; do
    [[ -f "$_sh" ]] || continue
    if ! bash -n "$_sh" 2>/dev/null; then
      _shell_bad+=("$_sh")
    fi
  done
  if [[ ${#_shell_bad[@]} -eq 0 ]]; then
    row shell_syntax PASS "关键 shell 脚本 bash -n OK"
  else
    row shell_syntax FAIL "语法错误: ${_shell_bad[*]}"
  fi
fi

# ── 9. 模板残留 ──
# v1.28+：业务仓不应含 skills/（governance-sync 不再下发 ABCDE 模板；
# 模板真源在维护仓根 skills/maintainer/auto-nn-init/templates/，业务仓按 .auto-nn/template-root 解析）。
# 残留 skills/ 视为过时，FAIL 建议删除。
if [[ $IS_TEMPLATE_ROOT -eq 0 ]]; then
  _tr_fail=""
  # .claude/skills/ 业务仓绝对禁止
  if [[ -d .claude/skills ]]; then
    _tr_fail+=".claude/skills "
  fi
  # skills/ 整体禁止（不再有白名单；真源在维护仓根）
  if [[ -d skills ]]; then
    _tr_fail+="skills/ "
  fi
  if [[ -n "$_tr_fail" ]]; then
    row template_residuals FAIL "建议删除 ${_tr_fail% }（v1.28+ governance-sync 不再下发；模板真源在维护仓根 skills/maintainer/auto-nn-init/templates/）"
  elif [[ -f scripts/new-project.sh ]]; then
    row template_residuals FAIL "不得含 scripts/new-project.sh"
  else
    row template_residuals PASS "无 skills/、无 new-project.sh 残留"
  fi
fi

# ── 10. git 大日志 ──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]] && git rev-parse --is-inside-work-tree &>/dev/null; then
  BAD_LOGS="$(git ls-files 2>/dev/null | grep -E 'pipeline\.log$|multi_structure_logs/.*\.log$' || true)"
  if [[ -n "$BAD_LOGS" ]]; then
    row git_bad_logs FAIL "大日志仍被 track: $(echo "$BAD_LOGS" | tr '\n' ' ')"
  else
    row git_bad_logs PASS "未 track offline 大日志"
  fi
fi

# ── 10b. contract.test.run / adapter_runner 签名（条件 FAIL/WARN）──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]]; then
  check_contract_test_signature() {
    if [[ ! -f scripts/lib/contract_test_signature.py ]]; then
      row contract_test_signature WARN "缺少 scripts/lib/contract_test_signature.py — governance-sync"
      return 0
    fi
    local _line _status _msg
    set +e
    _line="$(PYTHONPATH=scripts${PYTHONPATH:+:$PYTHONPATH} python3 -c "
from pathlib import Path
from lib.contract_test_signature import analyze_contract_test_signature
r = analyze_contract_test_signature(Path('.').resolve())
print(r.doctor_status + '\t' + r.message)
" 2>/dev/null)"
    _rc=$?
    set -e
    if [[ $_rc -ne 0 ]] || [[ -z "$_line" ]]; then
      row contract_test_signature WARN "签名分析失败"
      return 0
    fi
    _status="${_line%%$'\t'*}"
    _msg="${_line#*$'\t'}"
    case "$_status" in
      PASS|FAIL|WARN|SKIP) row contract_test_signature "$_status" "$_msg" ;;
      *) row contract_test_signature WARN "未知状态: $_line" ;;
    esac
  }
  check_contract_test_signature
fi

# ── 11. 运行环境（Poetry / torch / CUDA；换机后常见 FAIL）──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]]; then
  _env_ok=1
  if [[ -f scripts/check-env.sh ]]; then
    set +e
    _ce_out="$(bash scripts/check-env.sh --quiet 2>&1)"
    _ce_rc=$?
    set -e
    if [[ $_ce_rc -eq 0 ]]; then
      row env_runtime PASS "Poetry/torch 就绪"
    else
      row env_runtime FAIL "${_ce_out//$'\n'/; }"
      _env_ok=0
    fi
  fi
  if [[ $_env_ok -eq 1 ]]; then
    set +e
    if [[ -f pyproject.toml ]] && command -v poetry >/dev/null 2>&1; then
      _san_out="$(env PYTHONPATH=. poetry run python -m contract sanity 2>&1)"
      _san_rc=$?
    else
      _san_out="$(env PYTHONPATH=. python3 -m contract sanity 2>&1)"
      _san_rc=$?
    fi
    set -e
    if [[ $_san_rc -eq 0 ]]; then
      row contract_sanity PASS "Linear+MSE backward OK"
    else
      row contract_sanity FAIL "${_san_out//$'\n'/; }"
    fi
  else
    # env 未通过时不重复计 FAIL（同一根因）；SKIP 不入 FAIL 计数
    row contract_sanity SKIP "跳过（env_runtime 未通过）"
  fi
fi

# ── 12. 迁前遗留 ──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]]; then
  if [[ -d _runs/keep ]]; then
    row legacy_runs_keep WARN "存在 _runs/keep/ — 用 /auto-nn-clear（tier junk/custom）清理"
  fi
  if [[ -d saved/keep ]] && compgen -G "saved/keep/*.pt" >/dev/null 2>&1; then
    row legacy_saved_keep WARN "saved/keep/*.pt 遗留 — 已废弃"
  fi
fi

# ── 13. history_experiment_substr 遗留 override ──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]] && [[ -f contract/__init__.py ]]; then
  if grep -q 'history_experiment_substr' contract/__init__.py 2>/dev/null; then
    row history_experiment_substr WARN "contract 仍 override history_experiment_substr — Modify-Scenario-complete 应删除"
  else
    row history_experiment_substr PASS "未 override history_experiment_substr"
  fi
fi

# ── 13b. （keeper 迁移并入 scenario_completeness）──

# ── 14. Gate（业务仓）──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]]; then
  if [[ -f scripts/scenario_policy_gate.py ]] && [[ -f README.md ]] \
    && grep -q 'SCENARIO_POLICY' README.md 2>/dev/null; then
    run_check scenario_policy_gate python3 scripts/scenario_policy_gate.py .
  fi
  if [[ -f scripts/d2_data_split_gate.py ]]; then
    run_check d2_data_split_gate python3 scripts/d2_data_split_gate.py .
  fi
  if [[ -f scripts/info_perm_gate.py ]] && [[ -f README.md ]]; then
    set +e; python3 scripts/info_perm_gate.py . >/dev/null 2>&1; _ipg_rc=$?; set -e
    case $_ipg_rc in
      0) row info_perm_gate PASS "README INFO_PERM 块 ↔ 合同一致";;
      2) row info_perm_gate WARN "README 缺 INFO_PERM 块或未填（立项三问未落盘）";;
      *) row info_perm_gate FAIL "README INFO_PERM 块与 contract/runtime.py INFO_PERM 不一致";;
    esac
  fi
  if [[ "$PROFILE" == "rl" ]] && [[ -f scripts/rl_workspace_gate.py ]]; then
    run_check rl_workspace_gate python3 scripts/rl_workspace_gate.py .
  fi
  if [[ -f scripts/train_dynamics_gate.py ]]; then
    set +e
    _td_out="$(python3 scripts/train_dynamics_gate.py . 2>&1)"
    _td_rc=$?
    set -e
    if [[ $_td_rc -eq 0 ]]; then
      row train_dynamics_gate PASS "${_td_out//$'\n'/; }"
    else
      row train_dynamics_gate WARN "${_td_out//$'\n'/; }"
    fi
  fi
  if [[ "$PROFILE" == "supervised" ]] && [[ -f train.py ]]; then
    if grep -qE 'record_train_epoch|record_metrics' train.py 2>/dev/null; then
      row train_dynamics_hook PASS "train.py 已接 record_* hook"
    else
      row train_dynamics_hook WARN "supervised train.py 无 record_train_epoch/record_metrics"
    fi
    _last_exp=""
    if [[ -f _runs/results.tsv ]]; then
      _last_exp="$(python3 -c "
import csv
from pathlib import Path
p = Path('_runs/results.tsv')
with p.open() as f:
    rows = list(csv.DictReader(f, delimiter='\\t'))
for r in reversed(rows):
    if r.get('experiment') != 'preflight_check' and r.get('exp_dir'):
        print(r['exp_dir'])
        break
" 2>/dev/null || true)"
    fi
    if [[ -n "$_last_exp" && -f "$_last_exp/results.json" && ! -f "$_last_exp/train_dynamics.json" ]]; then
      row train_dynamics_artifact WARN "末轮 exp 有 results.json 无 train_dynamics.json（旧 run）"
    elif [[ -n "$_last_exp" && -f "$_last_exp/train_dynamics.json" ]]; then
      row train_dynamics_artifact PASS "末轮 exp 含 train_dynamics.json"
    fi
  fi
fi

# ── 15. RL make_eval_env mode（业务仓 profile=rl；按方法定位，文件名自由）──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]] && [[ "$PROFILE" == "rl" ]] && [[ -d workspace ]]; then
  set +e
  _rl_out="$(env PYTHONPATH=. python3 -c "
from pathlib import Path
import ast
from experiment import _ta_find_make_eval_env_file
p = _ta_find_make_eval_env_file(Path('workspace'))
if p is None:
    raise SystemExit('__SKIP__')
src_all = p.read_text(encoding='utf-8')
tree = ast.parse(src_all)
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == 'make_eval_env':
        src = ast.get_source_segment(src_all, node) or ''
        if 'create_multi_structure_env' in src and 'mode=PERF_MODEL_MODE' in src.replace(' ', ''):
            if 'eval_mode' not in src and 'mode if mode' not in src:
                raise SystemExit(f'{p}: make_eval_env 未将 mode 传入 create_multi_structure_env')
print(str(p))
" 2>&1)"
  _rl_rc=$?
  set -e
  if [[ $_rl_rc -ne 0 ]] && [[ "$_rl_out" == *"__SKIP__"* ]]; then
    row rl_make_eval_env SKIP "workspace 内未定义 make_eval_env（eval 逻辑可能内联于 contract.test）"
  elif [[ $_rl_rc -eq 0 ]]; then
    row rl_make_eval_env PASS "make_eval_env mode 传递 OK（${_rl_out//$'\n'/; }）"
  else
    row rl_make_eval_env FAIL "${_rl_out//$'\n'/; }"
  fi
fi

# ── 16. 全局技能链接（与模板 glob 对齐）──
missing_skills=()
_skill_troot="$(nn_resolve_template_root)" || _skill_troot=""
if [[ -n "$_skill_troot" && -d "$_skill_troot" ]]; then
  mapfile -t _skill_names < <(collect_global_skill_names "$_skill_troot")
else
  _skill_names=(
    auto-nn-doctor auto-nn-analyse auto-nn-compress auto-nn-modify auto-nn-clear
    auto-nn-human-guidance auto-nn-manual-run auto-nn-reflect auto-nn-auto-run
    auto-nn-init
  )
fi
for sk in "${_skill_names[@]}"; do
  [[ -n "$sk" ]] || continue
  if [[ ! -L "${HOME}/.cursor/skills/${sk}" && ! -d "${HOME}/.cursor/skills/${sk}" ]]; then
    missing_skills+=("$sk")
  fi
done
if [[ ${#missing_skills[@]} -eq 0 ]]; then
  row global_skills PASS "${#_skill_names[@]} 个 auto-nn-* 已安装"
else
  row global_skills WARN "未安装 (${#missing_skills[@]}/${#_skill_names[@]}): ${missing_skills[*]} — install.sh"
fi

# ── 深度档 ──
if [[ $DEEP -eq 1 ]]; then
  if [[ -f scripts/verify-migration-complete.sh ]]; then
    run_check verify_migration_complete bash scripts/verify-migration-complete.sh
  else
    row verify_migration_complete FAIL "缺少 verify-migration-complete.sh"
  fi
  if [[ -f scripts/smoke-check.sh ]]; then
    run_check smoke_check bash scripts/smoke-check.sh
  else
    row smoke_check FAIL "缺少 smoke-check.sh"
  fi
fi

if [[ $QUIET -eq 0 ]]; then
  echo "[nn-doctor] 汇总: PASS=${PASS} WARN=${WARN} FAIL=${FAIL}"
fi
if [[ $FAIL -gt 0 ]]; then
  if [[ $QUIET -eq 0 ]]; then
    echo "[nn-doctor] 结论: UNHEALTHY（存在 FAIL）" >&2
  fi
  exit 1
fi
if [[ $QUIET -eq 0 ]]; then
  echo "[nn-doctor] 结论: OK（无 FAIL；若有 WARN 见上表）"
fi
exit 0
