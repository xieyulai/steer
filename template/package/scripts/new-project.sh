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
  # 复制 README 文件
  if [[ -f "$skel_dir/README.md" ]]; then
    cp "$skel_dir/README.md" "$DEST/README.md"
    # 替换占位符
    sed -i "s/{PROJECT_NAME}/$NAME/g" "$DEST/README.md"
    sed -i "s/{PROFILE}/$_PROFILE/g" "$DEST/README.md"
    sed -i "s/{CREATED_AT}/$(date -Iseconds)/g" "$DEST/README.md"
    # 2026-07-06 spec：拼 full stamp（semver+SHA）替换 README 占位符
    TPL_SEMVER="$(tr -d '\r\n' < "$REPO_ROOT/VERSION")"
    TPL_SHA="$(cd "$REPO_ROOT" && git rev-parse --short HEAD 2>/dev/null || echo unknown)"
    TPL_STAMP="${TPL_SEMVER}+${TPL_SHA}"
    sed -i "s/{TEMPLATE_VERSION}/$TPL_STAMP/g" "$DEST/README.md"
    # §3 header 加版本行（一次性 awk：找首个 ## 标题后插入；已存在则不动）
    if ! grep -q "^> Template version:" "$DEST/README.md"; then
      awk -v stamp="$TPL_STAMP" '
        /^## / && !done {
          print; print ""; print "> Template version: " stamp " (init " strftime("%Y-%m-%d") ")";
          done=1; next
        }
        { print }
      ' "$DEST/README.md" > "$DEST/README.md.tmp" && mv "$DEST/README.md.tmp" "$DEST/README.md"
    fi
    # 当前戳 + 立项原始戳（后者 write-once；sync 只改 version）
    nn_state_write version "$TPL_STAMP" "$DEST"
    nn_state_write_once init-template-version "$TPL_STAMP" "$DEST"
  fi
  echo "=== 已应用完整骨架: $sk（contract + workspace + README）"
  return 0
}

# 入口 A：从源项目复制 contract 文件（如果有）
_copy_source_contract() {
  local src="$1"
  if [[ ! -d "$src/contract" ]]; then
    echo "=== 源项目无 contract/ 目录，跳过复制" >&2
    return 1
  fi
  # 复制 contract 实现文件（保留 __init__.py 和 __main__.py 从模板）
  for f in metrics.py runtime.py prepare_data.py test.py; do
    if [[ -f "$src/contract/$f" ]]; then
      cp "$src/contract/$f" "$DEST/contract/$f"
      echo "=== 从源项目复制 contract/$f"
    fi
  done
  # 复制 workspace 文件（如果有）
  if [[ -f "$src/workspace/__init__.py" ]]; then
    cp "$src/workspace/__init__.py" "$DEST/workspace/__init__.py"
    echo "=== 从源项目复制 workspace/__init__.py"
  fi
  # 复制 train.py（如果有）
  if [[ -f "$src/train.py" ]]; then
    cp "$src/train.py" "$DEST/train.py"
    echo "=== 从源项目复制 train.py"
  fi
  return 0
}

# 4 场景路由 — Migration 场景只复制 train.py / prepare_data.py（不带 contract/）
_copy_migration_essentials() {
  local src="$1"
  for f in train.py prepare_data.py; do
    if [[ -f "$src/$f" ]] && [[ ! -f "$DEST/$f" ]]; then
      cp "$src/$f" "$DEST/$f"
      echo "=== 从源项目复制 $f（Migration 场景）"
    fi
  done
}

# Adapter 场景：写 .auto-nn/init-adapter-pending.txt 给 HARD-GATE O3 阶段 Agent 弹 AskUserQuestion 补答
_adapter_ask_strategy() {
  local src="$1" dest="$2"
  mkdir -p "$dest/.auto-nn"
  cat <<'EOF' > "$dest/.auto-nn/init-adapter-pending.txt"
=== 适配策略选择（HARD-GATE O3 阶段 AskUserQuestion 必填） ===

源项目已有 contract/：
- A) keep_all      完整保留源 contract（运行时只调源 API；本仓 contract/ 占位）
- B) hybrid (推荐) 保留 metrics.py + runtime.py；重写 prepare_data.py + test.py
- C) rewrite       源 contract 仅作参考；本仓按 profile 重写全套

选后在 HARD-GATE O3 阶段 AskUserQuestion 弹窗补答（不再回填 yaml 字段）。
EOF
  echo "=== ADAPTER：已写入 .auto-nn/init-adapter-pending.txt（待 HARD-GATE O3 阶段弹 AskUserQuestion 补答）"
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
    # Migrate（原 migration + adapter 合并）：按 source 有无 contract/ 二级分流
    #   - 有 contract/ → workspace_wrapper（旧 adapter）：复制 contract + 弹策略选项
    #   - 无 contract/ → port_to_contract（旧 migration）：套 skeleton + 复制 train.py / prepare_data.py
    if [[ "$SKELETON" == "none" ]]; then
      :
    elif [[ "$SKELETON" == "auto" ]]; then
      _SKEL_APPLY="$_PROFILE"
    else
      _SKEL_APPLY="$SKELETON"
    fi
    if [[ -n "$SOURCE_ROOT" && -d "$SOURCE_ROOT/contract" ]]; then
      # workspace_wrapper 路径
      _copy_source_contract "$SOURCE_ROOT" || true
      _adapter_ask_strategy "$SOURCE_ROOT" "$DEST"
      echo "=== MIGRATE(workspace_wrapper): 源有 contract/，复制 contract + workspace_wrapper 策略待选: ${_SKEL_APPLY:-$SKELETON}"
    else
      # port_to_contract 路径
      _copy_migration_essentials "$SOURCE_ROOT" || true
      echo "=== MIGRATE(port_to_contract): 源无 contract/，复制 train.py / prepare_data.py + skeleton: ${_SKEL_APPLY:-$SKELETON}"
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
HEADER="$(python3 "$TEMPLATE_PACKAGE/scripts/regen_results_tsv.py" --repo-root "$DEST" --header-only 2>"$TSV_HDR_ERR")"
if [[ -z "$HEADER" ]]; then
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
  printf '%s\n' "$HEADER" > "$DEST/_runs/results.tsv"
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
# 替换占位符
ENTRY_TYPE="A"
[[ -z "$SOURCE_ROOT" ]] && ENTRY_TYPE="B"
sed -i "s/{ENTRY_TYPE}/$ENTRY_TYPE/g" "$DEST/.auto-nn/init-qa-log.md"
sed -i "s|{TARGET_ROOT}|$DEST|g" "$DEST/.auto-nn/init-qa-log.md"
sed -i "s/{STARTED_AT}/$(date -Iseconds)/g" "$DEST/.auto-nn/init-qa-log.md"
echo "=== 已初始化 .auto-nn/init-qa-log.md（entry=$ENTRY_TYPE）"

# 清理 new-project 过程的临时文件（业务仓不应保留；verify 当"整包拷贝残留"判 FAIL）
rm -f "$DEST/.new-project-tsv-header.err"

cd "$DEST"
rm -rf .git 2>/dev/null || true
git init
git add -A
git commit -m "init: $NAME (from auto-nn-experiment template)"

echo ""
echo "=== 完成: cd $DEST && poetry run python train.py ==="
