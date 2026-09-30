#!/usr/bin/env bash
# new-project.sh — 从 auto-nn-experiment 创建新项目（安装 template/package/）
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
TEMPLATE_PACKAGE="$REPO_ROOT/template/package"
TEMPLATE_MAINTAINER="$REPO_ROOT/template/maintainer"
# shellcheck source=template/package/scripts/lib/nn-state.sh
source "$TEMPLATE_PACKAGE/scripts/lib/nn-state.sh"

usage() {
  echo "用法: $0 <目标目录> [Poetry项目名] [--profile supervised|rl|physical] [--skeleton rl|physical|none|auto] [--workflow build|migrate|update] [--source-root PATH] [--accept-profile-override] [--force]"
  echo "  范式骨架仅 supervised|rl|physical 三份;mammoth 见 docs/examples/adapter-mammoth/(MIGRATE 场景参考实例,非骨架)"
  echo "  --profile      写入 nn-config.yaml 的范式（默认采用 align_probe 建议；与建议冲突须 --accept-profile-override）"
  echo "  --accept-profile-override  允许 --profile 与探针建议不一致"
  echo "  --answers      答卷文件(headless confirm_only;校验过才出仓)"
  echo "  --adapter-strategy  keep_all|hybrid|rewrite(覆盖答卷 M0;仅 full_copy 用)"
  echo "  --workflow     显式覆盖 workflow(build|migrate|update);默认按 source_root 自动判定"
  echo "                 三 workflow 定义见 template/package/scenarios/<workflow>.yaml"
  echo "  --source-root  入口 A：旧项目路径；写入 .auto-nn/migration-source 并参与 governance-sync 校验"
  echo "  --skeleton  复制 skeletons/<范式>/ 四文件（覆盖演示 contract）"
  echo "              auto（默认）: profile 为 rl|physical 时自动套用同名校本；supervised 保持 FMNIST 演示"
  echo "              none: 始终使用 package 内 contract 演示（与 --profile 无关）"
  echo "  --force        目标已存在时覆盖（spec T-A4）— 但保留目标里现有的 _runs/ 跑数据"
  exit 1
}

[[ "${1:-}" ]] || usage
DEST_RAW=""
NAME=""
PROFILE=""
SKELETON="auto"
WORKFLOW_OVERRIDE=""
SOURCE_ROOT=""
ANSWERS_FILE=""
ADAPTER_STRATEGY=""
FORCE=0
ACCEPT_PROFILE_OVERRIDE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile)
      [[ $# -ge 2 ]] || usage
      PROFILE="$2"
      shift 2
      ;;
    --workflow)
      [[ $# -ge 2 ]] || usage
      WORKFLOW_OVERRIDE="$2"
      shift 2
      ;;
    --source-root)
      [[ $# -ge 2 ]] || usage
      SOURCE_ROOT="$2"
      shift 2
      ;;
    --answers)
      [[ $# -ge 2 ]] || usage
      ANSWERS_FILE="$2"
      shift 2
      ;;
    --adapter-strategy)
      [[ $# -ge 2 ]] || usage
      ADAPTER_STRATEGY="$2"
      shift 2
      ;;
    --skeleton)
      if [[ $# -ge 2 && "$2" != --* ]]; then
        SKELETON="$2"
        shift 2
      else
        SKELETON="auto"
        shift
      fi
      ;;
    --accept-profile-override)
      ACCEPT_PROFILE_OVERRIDE=1
      shift
      ;;
    --force|--reuse-existing)
      FORCE=1
      shift
      ;;
    *)
      if [[ -z "$DEST_RAW" ]]; then
        DEST_RAW="$1"
      elif [[ -z "$NAME" ]]; then
        NAME="$1"
      fi
      shift
      ;;
  esac
done

[[ -n "$DEST_RAW" ]] || usage
NAME="${NAME:-$(basename "$DEST_RAW")}"

[[ "$NAME" =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] || { echo "错误: 项目名不合法: $NAME"; exit 1; }

if [[ -n "$PROFILE" ]]; then
  case "$PROFILE" in
    supervised|rl|physical) ;;
    *) echo "错误: 未知 profile: $PROFILE（可选: supervised, rl, physical）"; exit 1 ;;
  esac
fi

case "$SKELETON" in
  auto|none|supervised|rl|physical) ;;
  *) echo "错误: 未知 --skeleton: $SKELETON（可选: auto, none, rl, physical）"; exit 1 ;;
esac

if [[ -n "$ANSWERS_FILE" && ! -f "$ANSWERS_FILE" ]]; then
  echo "错误: --answers 文件不存在: $ANSWERS_FILE" >&2; exit 1
fi
if [[ -n "$ADAPTER_STRATEGY" ]] && [[ "$ADAPTER_STRATEGY" != keep_all \
    && "$ADAPTER_STRATEGY" != hybrid && "$ADAPTER_STRATEGY" != rewrite ]]; then
  echo "错误: --adapter-strategy 须为 keep_all|hybrid|rewrite" >&2; exit 1
fi

if [[ "$DEST_RAW" == */* ]] || [[ "$DEST_RAW" == */ ]]; then
  PARENT="$(cd "$(dirname "$DEST_RAW")" && pwd)"
  DEST="$PARENT/$(basename "$DEST_RAW")"
else
  DEST="$(pwd)/$DEST_RAW"
fi

[[ ! -e "$DEST" ]] || { echo "错误: 目标已存在: $DEST（用 --force 覆盖，保留 _runs/ 跑数据）"; [[ "$FORCE" == "1" ]] || exit 1; }

[[ -d "$TEMPLATE_PACKAGE" ]] || { echo "错误: 缺少 $TEMPLATE_PACKAGE" >&2; exit 1; }

echo "=== 模板维护仓: $REPO_ROOT"
echo "=== 安装包: $TEMPLATE_PACKAGE"
echo "=== 新项目: $DEST"
echo "=== name: $NAME  profile: ${PROFILE:-supervised (default)}  skeleton: $SKELETON"
if [[ "$FORCE" == "1" && -e "$DEST" ]]; then
  echo "=== --force: 覆盖现有目标，保留 _runs/ 与 .auto-nn/（spec T-A4）"
fi

mkdir -p "$DEST"

if command -v rsync &>/dev/null; then
  rsync -a \
    --exclude='_runs/' \
    --exclude='.auto-nn/' \
    --exclude='scenarios/' \
    "$TEMPLATE_PACKAGE/" "$DEST/"
else
  ( cd "$TEMPLATE_PACKAGE" && tar -cf - --exclude='./_runs' --exclude='./.auto-nn' --exclude='./scenarios' . ) | ( cd "$DEST" && tar -xf - )
fi
echo "=== 已从 template/package/ 安装业务项目骨架"

# CHECKLIST.md 不再保留在业务仓根目录；立即移到 .auto-nn/migration-completed-checklist-<ts>.md
# is_migration_in_progress() 已支持 .auto-nn/migration-completed-checklist-*.md glob 兼容（764816d）
if [[ -f "$DEST/CHECKLIST.md" ]]; then
  mkdir -p "$DEST/.auto-nn"
  _ckpt_ts="$(date -u +%Y%m%d_%H%M%SZ)"
  mv "$DEST/CHECKLIST.md" "$DEST/.auto-nn/migration-completed-checklist-${_ckpt_ts}.md"
  echo "=== 已移动 CHECKLIST.md → .auto-nn/migration-completed-checklist-${_ckpt_ts}.md（业务仓根不再保留）"
fi

mkdir -p "$DEST/_runs/logs" "$DEST/_runs/agent"
if [[ -f "$TEMPLATE_PACKAGE/_runs/logs/README.md" ]]; then
  cp "$TEMPLATE_PACKAGE/_runs/logs/README.md" "$DEST/_runs/logs/README.md"
fi
if [[ -f "$TEMPLATE_PACKAGE/_runs/agent/README.md" ]]; then
  cp "$TEMPLATE_PACKAGE/_runs/agent/README.md" "$DEST/_runs/agent/README.md"
fi

GPU_LIST="$(PYTHONPATH="$TEMPLATE_PACKAGE/scripts${PYTHONPATH:+:$PYTHONPATH}" python3 -c "
from lib.home_gpus import init_project_gpus_yaml
print(init_project_gpus_yaml())
" 2>/dev/null || echo '[]')"

_PROFILE="${PROFILE:-}"

# 写模板版本戳:README 占位符替换 + §3 header 版本行 + nn_state(D1:骨架跳过时仍执行)
_write_template_version() {
  local TPL_SEMVER TPL_SHA TPL_STAMP
  sed -i "s/{PROJECT_NAME}/$NAME/g" "$DEST/README.md"
  sed -i "s/{PROFILE}/$_PROFILE/g" "$DEST/README.md"
  sed -i "s/{CREATED_AT}/$(date -Iseconds)/g" "$DEST/README.md"
  # 2026-07-06 spec:拼 full stamp(semver+SHA)替换 README 占位符
  TPL_SEMVER="$(tr -d '\r\n' < "$REPO_ROOT/VERSION")"
  TPL_SHA="$(cd "$REPO_ROOT" && git rev-parse --short HEAD 2>/dev/null || echo unknown)"
  TPL_STAMP="${TPL_SEMVER}+${TPL_SHA}"
  sed -i "s/{TEMPLATE_VERSION}/$TPL_STAMP/g" "$DEST/README.md"
  # §3 header 加版本行(一次性 awk:找首个 ## 标题后插入;已存在则不动)
  if ! grep -q "^> Template version:" "$DEST/README.md"; then
    awk -v stamp="$TPL_STAMP" '
      /^## / && !done {
        print; print ""; print "> Template version: " stamp " (init " strftime("%Y-%m-%d") ")";
        done=1; next
      }
      { print }
    ' "$DEST/README.md" > "$DEST/README.md.tmp" && mv "$DEST/README.md.tmp" "$DEST/README.md"
  fi
  # 当前戳 + 立项原始戳(后者 write-once;sync 只改 version)
  nn_state_write version "$TPL_STAMP" "$DEST"
  nn_state_write_once init-template-version "$TPL_STAMP" "$DEST"
  echo "=== 已写模板版本戳: $TPL_STAMP"
}

_apply_contract_skeleton() {
  local sk="$1"
  local skel_dir="$TEMPLATE_MAINTAINER/skeletons/$sk"
  if [[ ! -d "$skel_dir" ]]; then
    echo "=== 警告: 无 skeletons/$sk，保留模板 contract 演示" >&2
    return 1
  fi
  # 复制 contract 文件（统一从 contract/ 子目录复制；WP0.1 结构统一后 elif 已废）
  for f in metrics.py runtime.py prepare_data.py test.py; do
    if [[ ! -f "$skel_dir/contract/$f" ]]; then
      echo "错误: 骨架 $skel_dir/contract/$f 缺失（WP0.1 统一 contract/ 结构要求）" >&2
      return 1
    fi
    cp "$skel_dir/contract/$f" "$DEST/contract/$f"
  done
  # 复制 workspace 文件
  if [[ -f "$skel_dir/workspace/__init__.py" ]]; then
    cp "$skel_dir/workspace/__init__.py" "$DEST/workspace/__init__.py"
  fi
  # 复制 README 文件(版本戳统一走 _write_template_version)
  if [[ -f "$skel_dir/README.md" ]]; then
    cp "$skel_dir/README.md" "$DEST/README.md"
  fi
  _write_template_version
  echo "=== 已应用完整骨架: $sk（contract + workspace + README）"
  return 0
}

# full_copy:按 migrate.yaml copy_targets 把源代码整套复制进新仓(fork-and-own)
_full_copy_source() {
  local src="$1" mig_json="$2"
  local contract_glob workspace_dir f
  contract_glob="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["copy_targets"]["contract_glob"])' "$mig_json")"
  workspace_dir="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["copy_targets"]["workspace_dir"])' "$mig_json")"
  # contract/*.py(含 __init__;__pycache__ 天然不匹配)
  rm -rf "$DEST/contract"
  mkdir -p "$DEST/contract"
  (
    cd "$src" || exit 1
    for f in $contract_glob; do
      [[ -f "$f" ]] || continue
      cp "$f" "$DEST/$f"
      echo "=== full_copy: $f"
    done
  )
  [[ -f "$DEST/contract/__init__.py" ]] || { : > "$DEST/contract/__init__.py"; echo "=== 提示: 源无 contract/__init__.py,已建空文件"; }
  # workspace/ 整目录(排除 __pycache__)
  rm -rf "$DEST/workspace"
  mkdir -p "$DEST/workspace"
  if [[ -d "$src/$workspace_dir" ]]; then
    rsync -a --exclude='__pycache__/' "$src/$workspace_dir" "$DEST/$workspace_dir"
    echo "=== full_copy: $workspace_dir(整目录)"
  else
    echo "=== 提示: 源无 $workspace_dir,保留空目录"
  fi
  [[ -f "$DEST/workspace/__init__.py" ]] || { : > "$DEST/workspace/__init__.py"; echo "=== 提示: 源无 workspace/__init__.py,已建空文件"; }
  # 根级文件(存在则复制;源无则保留模板版)
  for f in $(python3 -c 'import json,sys; print(" ".join(json.load(open(sys.argv[1]))["copy_targets"]["root_files"]))' "$mig_json"); do
    if [[ -f "$src/$f" ]]; then
      cp "$src/$f" "$DEST/$f"
      echo "=== full_copy: $f"
    else
      echo "=== 提示: 源无 $f,保留模板版"
    fi
  done
  echo "=== full_copy 完成(禁拷: data/ _runs/ saved/ references/ .git .venv)"
}

# port_to_contract:老资产拷进只读参考区(白名单扩展名;禁拷目录排除)
_copy_legacy_reference() {
  local src="$1" legacy_dir="$2"
  [[ -n "$src" ]] || return 0
  mkdir -p "$DEST/$legacy_dir"
  rsync -a \
    --include='*/' --include='*.py' --include='*.yaml' --include='*.yml' --include='*.md' \
    --exclude='__pycache__/' --exclude='data/' --exclude='_runs/' --exclude='saved/' \
    --exclude='references/' --exclude='.git/' --exclude='.venv/' \
    "$src/" "$DEST/$legacy_dir/"
  echo "=== port_to_contract: 已存参考副本到 $legacy_dir(只读参考,agent 按 port_targets 手抄拆解)"
}

# Reinit 场景：保留源 manual.md + _runs/ + saved/（不动 E 档；让源经验沉淀生效）
_update_reinit_config() {
  local src="$1" dest="$2"
  if [[ -f "$src/references/manual/abcde-manual.md" ]]; then
    mkdir -p "$dest/references/manual"
    cp "$src/references/manual/abcde-manual.md" "$dest/references/manual/abcde-manual.md"
    echo "=== REINIT：已保留源 manual.md（不动 E 档）"
  else
    echo "=== REINIT：源无 manual.md，跳过（首次 init 由 init_o3_abcde 生成）" >&2
  fi
  for d in _runs saved; do
    if [[ -e "$src/$d" ]]; then
      cp -a "$src/$d" "$dest/" 2>/dev/null || true
      echo "=== REINIT：已保留源 $d/"
    fi
  done
}

# 入口 ABCDE 路由（new_project_scenarios.resolve_init_workflow；--workflow 可显式覆盖自动分类）
WORKFLOW="build"
_WORKFLOW_ARGS=(--repo "$DEST")
if [[ -n "$SOURCE_ROOT" ]]; then
  _WORKFLOW_ARGS+=(--source "$SOURCE_ROOT")
fi
if [[ -n "$WORKFLOW_OVERRIDE" ]]; then
  _WORKFLOW_ARGS+=(--workflow "$WORKFLOW_OVERRIDE")
fi
WORKFLOW="$(python3 "$TEMPLATE_PACKAGE/scripts/new_project_scenarios.py" "${_WORKFLOW_ARGS[@]}")"

# align_probe：深度/范式建议；纯数据源禁止 migrate；profile 默认用建议
set +e
_PROBE_JSON="$(
  PYTHONPATH="$TEMPLATE_PACKAGE/scripts${PYTHONPATH:+:$PYTHONPATH}" \
  python3 "$TEMPLATE_PACKAGE/scripts/init_align.py" probe \
    --repo-root "$DEST" \
    ${SOURCE_ROOT:+--source-root "$SOURCE_ROOT"} \
    --force-workflow "$WORKFLOW"
)"
_PROBE_RC=$?
set -e
if [[ "$_PROBE_RC" -eq 2 ]]; then
  echo "=== FAIL: 源几乎无训练代码，禁止 migrate；请改 BUILD（无 --source-root）并把数据目录挂载/symlink" >&2
  echo "$_PROBE_JSON" >&2
  exit 1
fi
if [[ "$_PROBE_RC" -ne 0 ]]; then
  echo "=== FAIL: align_probe 失败 (rc=$_PROBE_RC)" >&2
  echo "$_PROBE_JSON" >&2
  exit 1
fi
_PROBE_PROFILE="$(python3 -c "import json,sys; print(json.load(sys.stdin)['profile_suggested'])" <<<"$_PROBE_JSON")"
_PROBE_OT="$(python3 -c "import json,sys; print(json.load(sys.stdin)['object_type_suggested'])" <<<"$_PROBE_JSON")"
_PROBE_FW="$(python3 -c "import json,sys; print(json.load(sys.stdin).get('framework_name_suggested') or '')" <<<"$_PROBE_JSON")"
_PROBE_PATTERN="$(python3 -c "import json,sys; print(json.load(sys.stdin).get('pattern') or '')" <<<"$_PROBE_JSON")"
echo "=== align_probe: profile=$_PROBE_PROFILE object_type=$_PROBE_OT framework=${_PROBE_FW:-none}"

_PROFILE_OVERRIDE=0
if [[ -z "$_PROFILE" ]]; then
  _PROFILE="$_PROBE_PROFILE"
elif [[ "$_PROFILE" != "$_PROBE_PROFILE" ]]; then
  if [[ "$ACCEPT_PROFILE_OVERRIDE" != "1" ]]; then
    echo "=== FAIL: --profile=$_PROFILE 与探针建议 $_PROBE_PROFILE 冲突；确认后加 --accept-profile-override" >&2
    exit 1
  fi
  _PROFILE_OVERRIDE=1
  echo "=== 警告: 已接受 profile 覆盖 $_PROBE_PROFILE → $_PROFILE"
fi

# migrate pattern 分流(单一真源 migrate.yaml;D6)
_MIG_JSON=""
_MIG_PATTERN=""
if [[ "$WORKFLOW" == "migrate" && -n "$SOURCE_ROOT" ]]; then
  _MIG_JSON="$(python3 "$REPO_ROOT/template/package/scripts/new_project_patterns.py" --source-root "$SOURCE_ROOT" --emit)"
  _MIG_PATTERN="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["pattern"])' <<<"$_MIG_JSON")"
  echo "=== migrate pattern=$_MIG_PATTERN"
fi

# D5:答卷校验(headless 也有门禁) + D3:策略从 resolved 提取
_RESOLVED_JSON=""
if [[ -n "$ANSWERS_FILE" ]]; then
  echo "=== 答卷校验(headless confirm_only 路径)"
  if ! python3 "$REPO_ROOT/template/package/scripts/init_answers.py" validate \
      --answers "$ANSWERS_FILE" --workflow "$WORKFLOW" --repo-root "$DEST" --write-resolved \
      ${SOURCE_ROOT:+--source-root "$SOURCE_ROOT"} \
      ${_MIG_PATTERN:+--pattern "$_MIG_PATTERN"}; then
    echo "!!! 答卷校验未过,中止(D5:headless 也有门禁)" >&2
    exit 1
  fi
  _RESOLVED_JSON="$DEST/.auto-nn/init-answers.resolved.json"
fi
if [[ -z "$ADAPTER_STRATEGY" && "$_MIG_PATTERN" == "full_copy" && -n "$_RESOLVED_JSON" ]]; then
  ADAPTER_STRATEGY="$(python3 -c '
import json, sys
d = json.load(open(sys.argv[1]))
lock = d.get("resolved", {}).get("M0-adapter-strategy", {}).get("lock", "M0=hybrid")
print(lock.split("=")[-1])' "$_RESOLVED_JSON")"
fi
if [[ "$_MIG_PATTERN" == "full_copy" && -z "$ADAPTER_STRATEGY" ]]; then
  ADAPTER_STRATEGY="hybrid"
  echo "=== 提示: 未提供适配策略,默认 hybrid"
fi

_SKEL_APPLY=""
case "$WORKFLOW" in
  build)
    # Build（原 greenfield）：套 skeleton，无源 contract 复制；保留 auto/none/profile 默认行为
    if [[ "$SKELETON" == "none" ]]; then
      :
    elif [[ "$SKELETON" == "auto" ]]; then
      _SKEL_APPLY="$_PROFILE"
    else
      _SKEL_APPLY="$SKELETON"
    fi
    echo "=== BUILD：使用 skeleton 骨架: ${_SKEL_APPLY:-$SKELETON}"
    ;;
      migrate)
        # Migrate:按 migrate.yaml patterns 二级分流(fork-and-own)
        #   - full_copy(源有 contract/):整套复制源代码,不套演示骨架
        #   - port_to_contract(源无 contract/):套模板 skeleton + 老资产进只读参考区
        if [[ "$_MIG_PATTERN" == "full_copy" ]]; then
          if [[ -n "$SKELETON" && "$SKELETON" != "auto" && "$SKELETON" != "none" ]]; then
            echo "=== 警告: full_copy 不套演示骨架,--skeleton $SKELETON 已忽略(源代码优先;演示骨架请走 build)"
          fi
          _MIG_JSON_FILE="$(mktemp)"
          printf '%s' "$_MIG_JSON" > "$_MIG_JSON_FILE"
          _full_copy_source "$SOURCE_ROOT" "$_MIG_JSON_FILE"
          rm -f "$_MIG_JSON_FILE"
          _write_template_version
          echo "=== 闭包检查(AST import)"
          if ! python3 "$REPO_ROOT/template/package/scripts/check_copy_closure.py" \
              --repo-root "$DEST" ${SOURCE_ROOT:+--source-root "$SOURCE_ROOT"}; then
            echo "!!! migrate full_copy 闭包检查未过(缺 import 目标文件),中止" >&2
            exit 1
          fi
        else
          # port_to_contract:套模板骨架(该路径本就要模板结构)
          if [[ "$SKELETON" == "none" ]]; then
            :
          elif [[ "$SKELETON" == "auto" ]]; then
            _SKEL_APPLY="$_PROFILE"
          else
            _SKEL_APPLY="$SKELETON"
          fi
          if [[ -n "$_MIG_JSON" ]]; then
            _LEGACY_DIR="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("legacy_dir","references/legacy"))' <<<"$_MIG_JSON")"
          else
            _LEGACY_DIR="references/legacy"
          fi
          _copy_legacy_reference "$SOURCE_ROOT" "$_LEGACY_DIR"
        fi
        ;;
  update)
    # Update（原 reinit）：源是本仓历史；保留 manual.md + _runs/saved
    _update_reinit_config "$SOURCE_ROOT" "$DEST"
    ;;
  *)
    echo "=== 警告: 未知 workflow=$WORKFLOW，按 build 兜底" >&2
    if [[ "$SKELETON" == "none" ]]; then
      :
    elif [[ "$SKELETON" == "auto" ]]; then
      _SKEL_APPLY="$_PROFILE"
    else
      _SKEL_APPLY="$SKELETON"
    fi
    ;;
esac
if [[ -n "$_SKEL_APPLY" ]]; then
  _apply_contract_skeleton "$_SKEL_APPLY" || true
fi

# 任何场景都生成 manual.md（update 已由 _update_reinit_config 从源拷过，存在则跳过）
# WORKFLOW 是 new_project_scenarios.py 输出的 lowercase（build/migrate/update）
# 模板源在维护仓根 skills/maintainer/auto-nn-init/templates/（不在 TPKG 内）
_TPL_TEMPLATES_DIR="$REPO_ROOT/skills/maintainer/auto-nn-init/templates"
if [[ ! -f "$DEST/references/manual/abcde-manual.md" ]]; then
  if [[ -d "$_TPL_TEMPLATES_DIR" ]] && [[ -f "$_TPL_TEMPLATES_DIR/${WORKFLOW}.md" ]]; then
    # 先写 init-align，供 init_o3 消费（对齐确认真源）
    _ENTRY="B"
    [[ -n "$SOURCE_ROOT" ]] && _ENTRY="A"
    _OT_OVERRIDE=false
    _DET_OT="$(python3 -c "import json,sys; print(json.load(sys.stdin).get('detect_object_type') or '')" <<<"$_PROBE_JSON")"
    [[ "$_PROBE_OT" != "$_DET_OT" ]] && _OT_OVERRIDE=true
    _OVERRIDES="$(printf '{"profile": %s, "object_type": %s}' \
      "$([[ $_PROFILE_OVERRIDE == 1 ]] && echo true || echo false)" \
      "$_OT_OVERRIDE")"
    PYTHONPATH="$TEMPLATE_PACKAGE/scripts${PYTHONPATH:+:$PYTHONPATH}" \
    python3 "$TEMPLATE_PACKAGE/scripts/init_align.py" write \
      --repo-root "$DEST" \
      --entry "$_ENTRY" \
      ${SOURCE_ROOT:+--source-root "$SOURCE_ROOT"} \
      --workflow "$WORKFLOW" \
      --object-type "$_PROBE_OT" \
      --profile "$_PROFILE" \
      ${_PROBE_PATTERN:+--pattern "$_PROBE_PATTERN"} \
      ${_PROBE_FW:+--framework-name "$_PROBE_FW"} \
      --probe-snapshot "$_PROBE_JSON" \
      --overrides "$_OVERRIDES"
    echo "=== 已写入 .auto-nn/init-align.json"

    if [[ "$WORKFLOW" == "migrate" && -n "$SOURCE_ROOT" ]]; then
      python3 - "$DEST/.auto-nn/init-align.json" "$_MIG_PATTERN" "$ADAPTER_STRATEGY" <<'PY'
import json, sys
p, pattern, strategy = sys.argv[1], sys.argv[2], sys.argv[3]
d = json.load(open(p, encoding="utf-8"))
if pattern:
    d["pattern"] = pattern
if strategy:
    d["adapter_strategy"] = strategy
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY
      echo "=== init-align.json 注入 pattern=$_MIG_PATTERN adapter_strategy=${ADAPTER_STRATEGY:-（无）}"
    fi

    _INIT_O3_ARGS=(
      --repo-root "$DEST"
      --templates-dir "$_TPL_TEMPLATES_DIR"
      --force-workflow "$WORKFLOW"
      --force-object-type "$_PROBE_OT"
    )
    [[ -n "$SOURCE_ROOT" ]] && _INIT_O3_ARGS+=(--source-root "$SOURCE_ROOT")
    [[ -n "$_PROBE_FW" ]] && _INIT_O3_ARGS+=(--framework-name "$_PROBE_FW" --framework-mutability register)
    if PYTHONPATH="$TEMPLATE_PACKAGE/scripts${PYTHONPATH:+:$PYTHONPATH}" \
       python3 "$TEMPLATE_PACKAGE/scripts/init_o3_abcde.py" "${_INIT_O3_ARGS[@]}" >/dev/null; then
      echo "=== 已生成 manual.md（workflow=$WORKFLOW object_type=$_PROBE_OT）"
      if [[ "$_MIG_PATTERN" == "full_copy" && -n "$ANSWERS_FILE" ]]; then
        python3 - "$DEST" "$ADAPTER_STRATEGY" >> "$DEST/references/manual/abcde-manual.md" <<'PY'
import json, pathlib, sys
dest, strategy = pathlib.Path(sys.argv[1]), sys.argv[2]
meanings = {"keep_all": "整套照抄(源口径即新仓口径)",
            "hybrid": "保留 metrics/runtime,重写 prepare_data/test",
            "rewrite": "源仅作参考,按 profile 重写全套"}
print()
print("## 适配与差异工作清单(M0 + 源vs答卷差异;机器生成)")
print()
print(f"- 适配策略(M0): **{strategy}** —— {meanings.get(strategy, '未知策略')}")
print()
diff_p = dest / ".auto-nn" / "migration-diff.json"
rows = json.load(open(diff_p, encoding="utf-8"))["rows"] if diff_p.is_file() else []
if not rows:
    print("- 无 migration-diff.json(未传 --source-root 或无差异表):按 F1 签字口径自查产物")
else:
    todo = [r for r in rows if not r["landing"].startswith("（人工核对）")]
    manual = [r for r in rows if r["landing"].startswith("（人工核对）")]
    if todo:
        print("### 须核改(落点明确)")
        print()
        for r in todo:
            src_v = json.dumps(r["source_value"], ensure_ascii=False)
            print(f"- `{r['slug']}` → 核改 `{r['landing']}`(源值: {src_v};答卷: {r['answer_lock']})")
        print()
    if manual:
        print("### 需人工核对(探针提不出源值)")
        print()
        for r in manual:
            print(f"- `{r['slug']}` → 落点 {r['landing'][6:]}(源值: 机读不可得;答卷: {r['answer_lock']})")
        print()
PY
        echo "=== manual.md 已附适配与差异工作清单"
      fi
      rm -f "$DEST/.auto-nn/manual-generate-failed"
    else
      echo "=== FAIL: manual 写入失败（立项中止；事后可手动跑 init_o3_abcde.py）" >&2
      mkdir -p "$DEST/.auto-nn"
      echo "init_o3_abcde failed workflow=$WORKFLOW" > "$DEST/.auto-nn/manual-generate-failed"
    fi
  else
    echo "=== FAIL: 缺模板 ${_TPL_TEMPLATES_DIR}/${WORKFLOW}.md（或模板目录不存在）— 立项中止" >&2
    mkdir -p "$DEST/.auto-nn"
    echo "missing templates dir or ${WORKFLOW}.md" > "$DEST/.auto-nn/manual-generate-failed"
  fi
else
  echo "=== manual.md 已存在（update 从源保留）；跳过"
  rm -f "$DEST/.auto-nn/manual-generate-failed"
fi

# framework 对象迁移：提示补 contract/framework_binding.yaml（接入总表，Discovery 结论落盘）。
# headless 立项没有 Discovery 会话代写此表，不提示则 nn-doctor fw_binding_decl 必挂——提示级不代答。
if [[ "$WORKFLOW" == "migrate" && "$_PROBE_OT" == "framework" && -f "$DEST/references/manual/abcde-manual.md" ]]; then
  cat >> "$DEST/references/manual/abcde-manual.md" <<'FWBINDING_EOF'

## 待办：补 contract/framework_binding.yaml（framework 接入总表）
- 探测判定本源仓为 framework 对象；`nn-doctor` 的 `fw_binding_decl` 项会校验 `contract/framework_binding.yaml` 存在且合法。
- headless 立项没有 Discovery 会话代写：请按源仓代码事实人工落盘该表后再过闸（交互立项由 init 会话 Discovery 负责）。
- 必填结构与取值以校验器为准：`scripts/lib/framework_binding.py` 的 `validate_framework_binding`；
  五节 `data/train/eval/train_log/checkpoint` 各 `status: bound|unavailable`（unavailable 须给 `reason`）。
FWBINDING_EOF
  echo "=== framework 对象：已往 manual.md 追加 framework_binding.yaml 待办提示"
fi

# 形式闸门 #1：说明书必须落盘，否则立项失败
if [[ ! -f "$DEST/references/manual/abcde-manual.md" ]]; then
  mkdir -p "$DEST/.auto-nn"
  [[ -f "$DEST/.auto-nn/manual-generate-failed" ]] || \
    echo "abcde-manual.md missing after init block" > "$DEST/.auto-nn/manual-generate-failed"
  echo "=== FAIL: 缺少 references/manual/abcde-manual.md — 立项中止" >&2
  exit 1
fi

cp "$TEMPLATE_PACKAGE/nn-config.yaml" "$DEST/nn-config.yaml"
sed -i "s/^profile:.*/profile: ${_PROFILE}          # supervised | rl | physical/" "$DEST/nn-config.yaml"
sed -i "s/^gpus:.*/gpus: ${GPU_LIST}/" "$DEST/nn-config.yaml"
echo "=== 范式 ${_PROFILE}：对照 profiles.yaml → profiles.${_PROFILE}"
echo "=== nn-config.yaml 已生成（自 template 复制，gpus=${GPU_LIST}）"

TSV_HDR_ERR="$DEST/.new-project-tsv-header.err"
TSV_HDR_FALLBACK=0
HEADER="$(python3 "$TEMPLATE_PACKAGE/scripts/regen_results_tsv.py" --repo-root "$DEST" --header-only 2>"$TSV_HDR_ERR")"
if [[ -z "$HEADER" ]]; then
  TSV_HDR_FALLBACK=1
  echo "=== 警告: 无法从 contract 生成 TSV 表头（见 $TSV_HDR_ERR）；使用占位表头 val_accuracy。" >&2
  echo "=== 须在首次训练前执行: python3 scripts/regen_results_tsv.py --repo-root ." >&2
  HEADER="$(printf '%s' "experiment	val_accuracy	elapsed_sec	git_commit	exp_dir	description	timestamp")"
fi
cp "$TEMPLATE_PACKAGE/scripts/regen_results_tsv.py" "$DEST/scripts/regen_results_tsv.py"
chmod +x "$DEST/scripts/regen_results_tsv.py" 2>/dev/null || true
cp "$TEMPLATE_PACKAGE/scripts/verify-migration-complete.sh" "$DEST/scripts/verify-migration-complete.sh"
chmod +x "$DEST/scripts/verify-migration-complete.sh" 2>/dev/null || true
bash "$REPO_ROOT/template/package/scripts/governance-sync.sh" \
  --template-root "$REPO_ROOT" --project-root "$DEST"

TSV_DEFER=0
if [[ "$_PROFILE" != "supervised" ]] && echo "$HEADER" | grep -qE '(^|	)val_accuracy(	|$)'; then
  TSV_DEFER=1
  echo "=== 警告: nn-config profile=${_PROFILE} 但 contract 仍为 supervised 演示；跳过写入 _runs/results.tsv" >&2
  echo "=== 迁移 contract 后执行: python3 scripts/regen_results_tsv.py --repo-root ." >&2
  echo "=== 收尾验收: bash scripts/verify-migration-complete.sh + CHECKLIST §5" >&2
  mkdir -p "$DEST/_runs"
  printf 'profile=%s\ncontract_demo=supervised\naction=run_regen_results_tsv_after_contract_migration\n' "$_PROFILE" \
    > "$DEST/_runs/.tsv-header-pending"
else
  # Step 0.4：update/reinit 从源带来的存量成绩表（>1 行）不许被裸表头覆盖（保行）；
  # contract 未就绪时挂 pending 标记，regen 对齐后按 verify/doctor 提示收尾
  if [[ -f "$DEST/_runs/results.tsv" ]] && [[ "$(grep -c '' "$DEST/_runs/results.tsv")" -gt 1 ]]; then
    echo "=== 警告: 已有存量 _runs/results.tsv，跳过表头写入（保留原行）" >&2
    if [[ "$TSV_HDR_FALLBACK" == 1 ]]; then
      mkdir -p "$DEST/_runs"
      printf 'profile=%s\nsource=kept_existing_results_tsv\naction=run_regen_results_tsv_after_contract_migration\n' "$_PROFILE" \
        > "$DEST/_runs/.tsv-header-pending"
    fi
  else
    printf '%s\n' "$HEADER" > "$DEST/_runs/results.tsv"
  fi
fi

if [[ "$_PROFILE" == "rl" ]]; then
  GI="$DEST/.gitignore"
  if [[ -f "$GI" ]] && ! grep -q 'multi_structure_logs/\*\.log' "$GI" 2>/dev/null; then
    printf '\n# RL offline_knn 运行日志（new-project --profile rl）\nworkspace/offline_knn/multi_structure_logs/*.log\n' >> "$GI"
  fi
fi

# workspace 起步布局建议（消费 profiles.yaml recommended_files；仅参考，不参与 gate）
python3 - "$TEMPLATE_PACKAGE/profiles.yaml" "$_PROFILE" "$DEST/workspace/RECOMMENDED_LAYOUT.md" <<'PYEOF' || echo "=== 警告: 生成 workspace/RECOMMENDED_LAYOUT.md 失败（不影响立项）" >&2
import sys, yaml
from pathlib import Path

yaml_path, profile, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
data = yaml.safe_load(Path(yaml_path).read_text(encoding="utf-8")) or {}
prof = (data.get("profiles") or {}).get(profile) or {}
rec = prof.get("recommended_files") or {}
ws_methods = prof.get("workspace") or []
req = prof.get("required_capabilities") or {}

lines = [
    f"# workspace 起步布局建议（profile={profile}）",
    "",
    "> **仅命名建议，不参与任何 gate。** 文件名完全自由：`model.py` 改叫 `models/`、",
    "> 把 `loss.py` 并进 `train_loop.py` 都不影响验收。守门只校验 `Workspace` 类上的",
    "> **方法**（见下）是否存在，不看文件叫什么。可删除本文件。",
    "",
    "## 必须由 `Workspace` 暴露的方法（G-范式 / G-门面 校验）",
    "",
]
lines += [f"- `{m}`" for m in ws_methods] or ["- （见 profiles.yaml）"]
lines += ["", "## 推荐子模块命名（可改可不用）", ""]
if rec:
    lines += [f"- `{path}` — {role}" for role, path in rec.items()]
else:
    lines += ["- （该 profile 未给建议）"]
if req:
    lines += ["", "## 与文件无关的硬性能力约束", ""]
    for name, desc in req.items():
        lines.append(f"- `{name}`：{desc}（守门按函数名扫 `workspace/**.py`，放哪个文件都行）")
lines += [
    "",
    "## 不变量（迁移铁律）",
    "",
    "- `train.py` 只调 `ws.*` / `contract.*`，**禁止** `from workspace.<子模块> import`（G-封装）。",
    "- 数据划分 / 官方 test / metrics 归 `contract/`，不进 workspace。",
    "",
]
Path(out_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"=== 已生成 workspace/RECOMMENDED_LAYOUT.md（profile={profile}；仅建议，可删）")
PYEOF

PY="$DEST/pyproject.toml"
if [[ -f "$PY" ]]; then
  sed -i "s/^name = \"auto-nn-experiment\"/name = \"$NAME\"/" "$PY"
fi

# 入口 A：写真 source_root；入口 B（greenfield）：写 # greenfield
if [[ -n "$SOURCE_ROOT" ]]; then
  nn_state_write migration-source "$SOURCE_ROOT" "$DEST"
else
  nn_state_write migration-source '# greenfield' "$DEST"
fi
# 入口 A/B 都写 template-root（governance-sync 无参自发现依赖它）
nn_state_write template-root "$REPO_ROOT" "$DEST"

# 迁后摘要（build/migrate/update 都落盘；nn-doctor migration_summary 门禁）
mkdir -p "$DEST/.auto-nn"
{
  echo "# 迁移摘要（migration-summary）"
  echo ""
  echo "- **workflow**: $WORKFLOW"
  echo "- **entry**: $(if [[ -n "$SOURCE_ROOT" ]]; then echo A-migrate; else echo B-build; fi)"
  echo "- **source_root**: ${SOURCE_ROOT:-（无——greenfield 从 skeleton 新建）}"
  echo "- **answers**: ${ANSWERS_FILE:-（无——交互问答）}"
  echo "- **generated**: $(date -Iseconds)"
  echo ""
  echo "> F1 口径结论：headless 路径以 .auto-nn/init-answers.resolved.json 的 lock 为准；"
  echo "> 现场签字流程与问答 transcript 见 .auto-nn/init-qa-log.md。"
} > "$DEST/.auto-nn/migration-summary.md"
echo "=== 已写 .auto-nn/migration-summary.md（workflow=$WORKFLOW）"

# 初始化 init-qa-log（init 过程的忠实记录）
mkdir -p "$DEST/.auto-nn"
cat > "$DEST/.auto-nn/init-qa-log.md" << 'QAEOF'
# Init 问答忠实记录（HARD-GATE）

> **状态**: 待开始（HARD-GATE 进行中由 Agent append）
> **路径**: `.auto-nn/init-qa-log.md`
> **性质**: 迁后**留档**；运行时（auto-run / doctor / gate）**不读**
> **分工**: 本文件 = **逐步问答 transcript**；`.auto-nn/migration-summary.md` = **F1 口径结论合同**
> **维护**: Agent 每步用户确认后调用 `scripts/append-init-qa-log.py`；F1 签字后 `close`

## 元数据

- **entry**: {ENTRY_TYPE}
- **target_root**: {TARGET_ROOT}
- **started**: {STARTED_AT}

## 日志

（待填充）
QAEOF
# 替换占位符（注意：entry+workflow 行要先替换——全局 {ENTRY_TYPE} 替换会把
# 占位符吃掉，放在后面就永远匹配不上了）
ENTRY_TYPE="A"
[[ -z "$SOURCE_ROOT" ]] && ENTRY_TYPE="B"
sed -i "s/^- \*\*entry\*\*: {ENTRY_TYPE}$/- **entry**: $ENTRY_TYPE\n- **workflow**: $WORKFLOW/" "$DEST/.auto-nn/init-qa-log.md"
sed -i "s/{ENTRY_TYPE}/$ENTRY_TYPE/g" "$DEST/.auto-nn/init-qa-log.md"
sed -i "s|{TARGET_ROOT}|$DEST|g" "$DEST/.auto-nn/init-qa-log.md"
sed -i "s/{STARTED_AT}/$(date -Iseconds)/g" "$DEST/.auto-nn/init-qa-log.md"
echo "=== 已初始化 .auto-nn/init-qa-log.md（entry=$ENTRY_TYPE workflow=$WORKFLOW）"

# 落位层：resolved lock → 产物形态（headless 无人接线的步骤由 scaffold 完成；F1/F2/F6）
# 注：results.tsv 表头不在此渲染——唯一事实源是 contract（regen_results_tsv.py 派生）
if [[ -n "$_RESOLVED_JSON" ]]; then
  python3 "$TEMPLATE_PACKAGE/scripts/render_init_blocks.py" \
    --repo-root "$DEST" --resolved "$_RESOLVED_JSON" \
    || echo "=== 警告: README/场景清单/nn-config/intent 渲染失败（不影响立项；可手动重跑 render_init_blocks.py）" >&2
  # F6: headless 直接执行 INFO_PERM 落表（交互路径仍走 lib/init_answers.py 的 hint）
  python3 "$TEMPLATE_PACKAGE/scripts/init_info_perm.py" write \
      --repo-root "$DEST" --from-resolved "$_RESOLVED_JSON" \
    || echo "=== 警告: INFO_PERM 落表未过（answer 的 I1/I2 值形不合注册表时发生；README 会留 WARN）" >&2
fi

# 清理 new-project 过程的临时文件（业务仓不应保留；verify 当"整包拷贝残留"判 FAIL）
rm -f "$DEST/.new-project-tsv-header.err"
# 脚手架入口脚本不进交付品（verify/doctor 按 CHECKLIST §2 判 FAIL；F3）
rm -f "$DEST/scripts/new-project.sh"

cd "$DEST"
rm -rf .git 2>/dev/null || true
git init
git add -A
git commit -m "init: $NAME (from auto-nn-experiment template)"

echo ""
echo "=== 完成: cd $DEST && poetry run python train.py ==="
