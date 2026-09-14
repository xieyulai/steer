#!/usr/bin/env bash
# check_skill_contract.sh — 校验 SKILL.md ## Code Contract 块 vs template/package/* 实际符号
#
# Pilot 范围（2026-07-15）：仅 auto-nn-doctor + auto-nn-modify 带 Code Contract。
# 其他 skill 不带块 → SKIP（不阻断），避免 pilot 期间误伤。
#
# 用法:
#   bash scripts/check_skill_contract.sh             # 校验全部已声明 skill
#   bash scripts/check_skill_contract.sh <skill>     # 仅校验指定 skill
#   bash scripts/check_skill_contract.sh --list      # 列出已声明 skill
#   bash scripts/check_skill_contract.sh --quiet     # 仅 WARN/FAIL + 汇总（PASS/SKIP 隐藏；
#                                                      供 release-check step 6 调用，同 nn-doctor.sh --quiet 约定）
#
# 检查类别（与 SKILL.md ## Code Contract 一一对应）：
#   calls_scripts      → 声明的 scripts/X 必须在 template/package/scripts/ 存在
#                       （业务仓镜像在 $ROOT/scripts/，governance-sync 下发）
#   reads_cfg_keys     → 声明的 cfg key 必须在 template/package/* 出现 cfg.get('X') / cfg['X']
#   env_vars_consumed  → 声明的 NN_X 必须在 template/package/* 出现 os.environ.*NN_X
#
# 反向检查（actuals not declared）：
#   扫 template/package/scripts/* 真实使用的 NN_*/cfg key，与各 skill 声明取并集对比：
#   - 真实使用但**任何**已声明 skill 都未声明 → WARN（informational，提醒是否漏登记）
#   - 已声明但实际不存在 → FAIL（硬阻断）
#
# 退出码：0=无 FAIL；1=至少 1 FAIL；2=无 Code Contract skill 可校

set -euo pipefail

# 脚本位于 template/package/scripts/check_skill_contract.sh
# 上溯三级到仓根（auto-nn-experiment/），这样 SKILLS_DIR 和 TPL_SCRIPTS 都对
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

SKILLS_DIR="${SKILLS_DIR:-$ROOT/skills/post-migration}"
TPL_SCRIPTS="$ROOT/template/package/scripts"
# cfg.get / os.environ 扫整个 template/package/*（contract/lib/scripts 都有 cfg.get）
TPL_ALL="$ROOT/template/package"

# 颜色（如有 tty）
if [[ -t 1 ]]; then
  C_RED=$'\033[31m'; C_GRN=$'\033[32m'; C_YEL=$'\033[33m'; C_DIM=$'\033[2m'; C_OFF=$'\033[0m'
else
  C_RED=""; C_GRN=""; C_YEL=""; C_DIM=""; C_OFF=""
fi

PASS=0; FAIL=0; WARN=0; SKIP=0
QUIET=0   # --quiet: 仅打印 WARN/FAIL + 汇总，PASS/SKIP 隐藏（与 nn-doctor.sh --quiet 同约定）

row() {
  local status="$1"; shift
  local name="$1"; shift
  local msg="$*"
  case "$status" in
    PASS) PASS=$((PASS+1));  if [[ $QUIET -eq 0 ]]; then printf "  ${C_GRN}PASS${C_OFF}  %s — %s\n" "$name" "$msg"; fi ;;
    FAIL) FAIL=$((FAIL+1));                       printf "  ${C_RED}FAIL${C_OFF}  %s — %s\n" "$name" "$msg" ;;
    WARN) WARN=$((WARN+1));                       printf "  ${C_YEL}WARN${C_OFF}  %s — %s\n" "$name" "$msg" ;;
    SKIP) SKIP=$((SKIP+1));  if [[ $QUIET -eq 0 ]]; then printf "  ${C_DIM}SKIP${C_OFF}  %s — %s\n" "$name" "$msg"; fi ;;
  esac
}

# ── 提取 ## Code Contract 块（行间） ──
# 用 awk：first match `^## Code Contract` 开启（允许多余标如 "（pilot，2026-07-15）"），
# 第二个 `^## ` 关闭
extract_contract_block() {
  local skill_md="$1"
  awk '
    /^## Code Contract/ {flag=1; next}
    /^## / && flag {exit}
    flag {print}
  ' "$skill_md"
}

# ── 从 contract 块提取 ```yaml ... ``` 代码块内容 ──
extract_yaml() {
  awk '
    /^```yaml/ {flag=1; next}
    /^```[[:space:]]*$/ && flag {exit}
    flag {print}
  '
}

# ── 解析 yaml 成 category<TAB>item 行 ──
# 规则：
#   ^[a-z_]+:[[:space:]]*(#.*)?$ → 类别开始（容忍行内注释）
#   ^  - <item>( # comment)?     → 类别下条目（去注释、去尾空格）
parse_pairs() {
  awk '
    function trim(s) { sub(/^[[:space:]]+/, "", s); sub(/[[:space:]]+$/, "", s); return s }
    /^[a-z_]+:[[:space:]]*(#.*)?$/ {
      cat = trim($0); sub(/:[[:space:]]*(#.*)?$/, "", cat); next
    }
    /^  - / {
      line = $0
      sub(/^  - /, "", line)
      sub(/[[:space:]]+#.*$/, "", line)   # 去行尾注释
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", line)
      if (line != "" && cat != "") print cat "\t" line
    }
  '
}

# ── 收集所有 NN_* env vars 真实被 template/package/* 读取 ──
collect_actual_env_vars() {
  grep -rhoE 'os\.environ[^)]*NN_[A-Z_]+' "$TPL_ALL" 2>/dev/null \
    | grep -oE 'NN_[A-Z_]+' \
    | sort -u
}

# ── 收集所有 cfg.get('X') / cfg['X'] 真实被 template/package/* 读取 ──
# 含两种形态：
#   1. 直接：cfg.get('X') / cfg['X']
#   2. 嵌套：<prefix>cfg.get('X') / cfg['X']（如 keep_cfg.get('improve_mode')）
# 嵌套命中时记 "<prefix>.X"（如 "keep.improve_mode"）
collect_actual_cfg_keys() {
  {
    # 直接 cfg.get('X')
    grep -rhoE "cfg\.get\(['\"][a-zA-Z_][a-zA-Z0-9_.]*['\"]" "$TPL_ALL" 2>/dev/null \
      | grep -oE "['\"][a-zA-Z_][a-zA-Z0-9_.]*['\"]" | tr -d "'\""
    # 直接 cfg['X']
    grep -rhoE "cfg\[['\"][a-zA-Z_][a-zA-Z0-9_.]*['\"]\]" "$TPL_ALL" 2>/dev/null \
      | grep -oE "['\"][a-zA-Z_][a-zA-Z0-9_.]*['\"]" | tr -d "'\""
    # 嵌套 X_cfg.get('Y') → 记 "X.Y"
    grep -rhoE "[a-zA-Z_]+_cfg\.get\(['\"][a-zA-Z_][a-zA-Z0-9_.]*['\"]" "$TPL_ALL" 2>/dev/null \
      | sed -E "s/([a-zA-Z_]+)_cfg\.get\((['\"])([a-zA-Z_][a-zA-Z0-9_.]*)\2/\1.\3/"
    # 嵌套 X_cfg['Y'] → 记 "X.Y"
    grep -rhoE "[a-zA-Z_]+_cfg\[['\"][a-zA-Z_][a-zA-Z0-9_.]*['\"]\]" "$TPL_ALL" 2>/dev/null \
      | sed -E "s/([a-zA-Z_]+)_cfg\[(['\"])([a-zA-Z_][a-zA-Z0-9_.]*)\2\]/\1.\3/"
  } | sort -u
}

# ── 检查单个 skill ──
check_skill() {
  local skill="$1"
  local skill_md="$SKILLS_DIR/$skill/SKILL.md"

  if [[ $QUIET -eq 0 ]]; then echo "[check-skill-contract] skill: $skill"; fi

  if [[ ! -f "$skill_md" ]]; then
    row SKIP "$skill" "SKILL.md 不存在"
    return 0
  fi

  local block yaml
  block="$(extract_contract_block "$skill_md")"
  if [[ -z "$block" ]]; then
    row SKIP "$skill" "未声明 ## Code Contract（pilot 范围外）"
    return 0
  fi

  yaml="$(echo "$block" | extract_yaml)"
  if [[ -z "$yaml" ]]; then
    row FAIL "$skill" '## Code Contract 存在但无 yaml 围栏块'
    return 1
  fi

  # 分类存临时文件
  local pairs_file
  pairs_file="$(mktemp)"
  echo "$yaml" | parse_pairs > "$pairs_file"

  # 1. calls_scripts → 文件存在性
  # SKILL.md 写 "scripts/X" 是给业务仓看的（governance-sync 后落 $ROOT/scripts/），
  # 但模板真源在 template/package/scripts/X。两个都查。
  while IFS=$'\t' read -r cat item; do
    [[ "$cat" == "calls_scripts" ]] || continue
    local leaf="${item#scripts/}"
    if [[ -f "$TPL_SCRIPTS/$leaf" ]]; then
      row PASS "$skill/calls_scripts/$item" "模板真源 $TPL_SCRIPTS/$leaf 存在"
    elif [[ -f "$ROOT/$item" ]]; then
      row PASS "$skill/calls_scripts/$item" "业务仓镜像 $ROOT/$item 存在"
    else
      row FAIL "$skill/calls_scripts/$item" "脚本不存在（既不在 $TPL_SCRIPTS/$leaf 也不在 $ROOT/$item）"
    fi
  done < "$pairs_file"

  # 2. reads_cfg_keys → 在 template/package/* 至少 1 次 cfg.get('X') / cfg['X']
  # 接受三种形态：
  #   - 直接 cfg.get('X') / cfg['X']
  #   - 父键 cfg.get('parent')（当 item 含 . 时退而求其次）
  #   - 嵌套 <prefix>_cfg.get('X') / cfg['X'] → 记录为 "<prefix>.X"
  while IFS=$'\t' read -r cat item; do
    [[ "$cat" == "reads_cfg_keys" ]] || continue
    # 嵌套形态：item 含 .，可能是 "keep.improve_mode"
    if grep -rqE "[a-zA-Z_]+_cfg[[:space:]]*(\.get\(|\[)\s*['\"]${item#*.}['\"]" "$TPL_ALL" 2>/dev/null; then
      row PASS "$skill/reads_cfg_keys/$item" "嵌套 $item#*. 命中"
    elif grep -rqE "cfg[[:space:]]*(\.get\(|\[)\s*['\"]${item}['\"]" "$TPL_ALL" 2>/dev/null; then
      row PASS "$skill/reads_cfg_keys/$item" "template/package/ 引用"
    elif grep -rqE "cfg[[:space:]]*(\.get\(|\[)\s*['\"]${item#*.}['\"]" "$TPL_ALL" 2>/dev/null; then
      row PASS "$skill/reads_cfg_keys/$item" "叶键 ${item#*.} 命中"
    elif [[ "$item" == *"."* ]]; then
      local parent="${item%%.*}"
      if grep -rqE "cfg[[:space:]]*(\.get\(|\[)\s*['\"]${parent}['\"]" "$TPL_ALL" 2>/dev/null; then
        row PASS "$skill/reads_cfg_keys/$item" "父键 ${parent} 命中"
      else
        row FAIL "$skill/reads_cfg_keys/$item" "template/package/ 未引用"
      fi
    else
      row FAIL "$skill/reads_cfg_keys/$item" "template/package/ 未引用"
    fi
  done < "$pairs_file"

  # 3. env_vars_consumed → 在 template/package/* 至少 1 次 os.environ.*NN_X
  while IFS=$'\t' read -r cat item; do
    [[ "$cat" == "env_vars_consumed" ]] || continue
    if grep -rqE "os\.environ[^)]*${item}" "$TPL_ALL" 2>/dev/null; then
      row PASS "$skill/env_vars_consumed/$item" "template/package/ 读取"
    else
      row WARN "$skill/env_vars_consumed/$item" "template/package/ 未直接读（可能在 doc 提及或业务仓读）"
    fi
  done < "$pairs_file"

  # 4. informational 类别（pluggable_symbols / referenced_gates）— 跳过，不强检
  while IFS=$'\t' read -r cat item; do
    case "$cat" in
      pluggable_symbols|referenced_gates) ;;
    esac
  done < "$pairs_file"

  rm -f "$pairs_file"
  echo
}

# ── 反向：actuals not declared ──
check_undeclared_actuals() {
  local -A declared_env declared_cfg
  local pairs_file
  pairs_file="$(mktemp)"
  local n_with_contract=0
  for skill in "$SKILLS_DIR"/auto-nn-*/SKILL.md; do
    [[ -f "$skill" ]] || continue
    local block yaml
    block="$(extract_contract_block "$skill")"
    [[ -z "$block" ]] && continue
    n_with_contract=$((n_with_contract+1))
    yaml="$(echo "$block" | extract_yaml)"
    echo "$yaml" | parse_pairs >> "$pairs_file"
  done

  # 若无任何 skill 声明 Code Contract → 反向检查无基线，直接 SKIP（避免 pilot 期误伤）
  if [[ $n_with_contract -eq 0 ]]; then
    row SKIP "actuals-not-declared" "无任何 skill 声明 ## Code Contract，无基线可比"
    rm -f "$pairs_file"
    echo
    return 0
  fi

  while IFS=$'\t' read -r cat item; do
    case "$cat" in
      env_vars_consumed) declared_env["$item"]=1 ;;
      reads_cfg_keys)    declared_cfg["$item"]=1 ;;
    esac
  done < "$pairs_file"
  rm -f "$pairs_file"

  if [[ $QUIET -eq 0 ]]; then echo "[check-skill-contract] 反向：actuals not declared（WARN-only，informational）"; fi

  local actual_env actual_cfg
  actual_env="$(collect_actual_env_vars)"
  actual_cfg="$(collect_actual_cfg_keys)"

  local n_undecl_env=0
  while IFS= read -r v; do
    [[ -z "$v" ]] && continue
    case "$v" in
      NN_X|NN_XXX) continue ;;  # scan regex 字面量
    esac
    if [[ -z "${declared_env[$v]:-}" ]]; then
      row WARN "undeclared-env/$v" "template/package/ 实际读但**无任何 skill 声明**
  → 应在用到它的 skill 的 env_vars_consumed 加"
      n_undecl_env=$((n_undecl_env+1))
    fi
  done <<< "$actual_env"

  local n_undecl_cfg=0
  while IFS= read -r k; do
    [[ -z "$k" ]] && continue
    case "$k" in
      KEY|X|UPPERCASE_KEY|MODEL_ARCH|LOSS|SCENARIO_ID|SEED) continue ;;
      agent|goal|ledger|keep|profile|gpus|device|seed|time_budget) continue ;;
    esac
    if [[ -z "${declared_cfg[$k]:-}" ]]; then
      row WARN "undeclared-cfg/$k" "template/package/ 实际读但**无任何 skill 声明**
  → 应在用到它的 skill 的 reads_cfg_keys 加"
      n_undecl_cfg=$((n_undecl_cfg+1))
    fi
  done <<< "$actual_cfg"

  if [[ $n_undecl_env -eq 0 && $n_undecl_cfg -eq 0 ]]; then
    row PASS "actuals-not-declared" "全部 NN_* / cfg key 都已被 skill 声明"
  fi
  echo
}

# ── 入口 ──
main() {
  local target_skill=""
  local mode="${1:-}"

  case "$mode" in
    --quiet|-q) QUIET=1; shift; mode="${1:-}" ;;
  esac

  case "$mode" in
    --list)
      echo "[check-skill-contract] 已声明 ## Code Contract 的 skill："
      for d in "$SKILLS_DIR"/auto-nn-*; do
        [[ -d "$d" && -f "$d/SKILL.md" ]] || continue
        local s; s="$(basename "$d")"
        if extract_contract_block "$d/SKILL.md" | grep -q .; then
          echo "  - $s"
        fi
      done
      exit 0
      ;;
  esac

  if [[ $# -gt 0 ]]; then
    target_skill="$1"
  fi

  if [[ -n "$target_skill" && "$target_skill" != --* ]]; then
    check_skill "$target_skill"
  else
    for d in "$SKILLS_DIR"/auto-nn-*; do
      [[ -d "$d" && -f "$d/SKILL.md" ]] || continue
      check_skill "$(basename "$d")"
    done
  fi

  check_undeclared_actuals

  echo "[check-skill-contract] 汇总: PASS=${PASS} WARN=${WARN} FAIL=${FAIL} SKIP=${SKIP}"

  if [[ $FAIL -gt 0 ]]; then
    exit 1
  fi
  exit 0
}

main "$@"