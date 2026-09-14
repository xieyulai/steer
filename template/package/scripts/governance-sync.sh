#!/usr/bin/env bash
# governance-sync.sh — 从模板维护仓同步「治理三件套」到业务项目（不改 workspace/contract 业务逻辑）
#
# 同步：profiles.yaml、verify、rl_workspace_gate、smoke-check、wait-train、本脚本；
# nn-config.yaml：merge-only 补模板新键（merge-nn-config-keys.py），缺失时整文件 init；
# 写入：.auto-nn/{governance-rev,version}（template-root 改由 symlink/env 解析，不再写回）
#
# 用法：
#   bash <template_root>/scripts/governance-sync.sh \
#     --template-root <template_root> --project-root <project_root>
#
# <template_root> = auto-nn-experiment 仓库根；业务文件在 <template_root>/template/package/
set -euo pipefail

# 提前 source nn-state.sh：自发现（无 --template-root 时）需 nn_resolve_template_root
# shellcheck source=lib/nn-state.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib/nn-state.sh"

usage() {
  echo "用法: $0 --template-root <模板维护仓根> --project-root <业务项目根>"
  echo "      （未传时：project-root 默认 cwd；template-root 按 NN_TEMPLATE_ROOT > symlink > .auto-nn/template-root 解析）"
  exit 1
}

TEMPLATE_ROOT=""
PROJECT_ROOT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --template-root) TEMPLATE_ROOT="${2:-}"; shift 2 ;;
    --project-root) PROJECT_ROOT="${2:-}"; shift 2 ;;
    -h|--help) usage ;;
    *) echo "未知参数: $1" >&2; usage ;;
  esac
done

# 自发现默认（业务仓无参自助更新）
if [[ -z "$PROJECT_ROOT" ]]; then
  PROJECT_ROOT="$(pwd)"
fi
if [[ -z "$TEMPLATE_ROOT" ]]; then
  # 跨机器解析：$NN_TEMPLATE_ROOT > symlink 自动定位 > .auto-nn/template-root（见 nn_resolve_template_root）
  TEMPLATE_ROOT="$(nn_resolve_template_root "$PROJECT_ROOT")" || true
fi
if [[ -z "$TEMPLATE_ROOT" ]]; then
  echo "[governance-sync] FAIL: 未解析到 template-root。任选其一：" >&2
  echo "  1) 在模板维护仓执行 ./install.sh（建立 ~/.cursor/skills/auto-nn-* symlink）" >&2
  echo "  2) bash governance-sync.sh --template-root <模板仓根> --project-root ." >&2
  echo "  3) export NN_TEMPLATE_ROOT=<模板仓根>（临时覆盖，不进 git）" >&2
  exit 1
fi
TEMPLATE_ROOT="$(cd "$TEMPLATE_ROOT" && pwd)"
PROJECT_ROOT="$(cd "$PROJECT_ROOT" && pwd)"

if [[ -f "$TEMPLATE_ROOT/template/package/profiles.yaml" ]]; then
  TEMPLATE_PKG="$TEMPLATE_ROOT/template/package"
elif [[ -f "$TEMPLATE_ROOT/template/profiles.yaml" ]]; then
  TEMPLATE_PKG="$TEMPLATE_ROOT/template"
elif [[ -f "$TEMPLATE_ROOT/profiles.yaml" ]]; then
  TEMPLATE_PKG="$TEMPLATE_ROOT"
else
  echo "[governance-sync] FAIL: 找不到 template/package/profiles.yaml（或过渡期 template/profiles.yaml）" >&2
  exit 1
fi

if [[ ! -f "$TEMPLATE_ROOT/.template-maintainer" ]]; then
  echo "[governance-sync] 警告: --template-root 似非模板维护仓根（无 .template-maintainer）" >&2
fi

for need in .gitignore profiles.yaml experiment.py auto-nn-run.sh scripts/auto-nn-setup.py CLAUDE.md PROTOCOL.md reflect.py contract/__main__.py scripts/verify-migration-complete.sh scripts/verify_project_layout.py scripts/regen_results_tsv.py scripts/sync_exploration_ledger.py scripts/sync_ledger.py scripts/rl_workspace_gate.py scripts/d2_data_split_gate.py scripts/scenario_policy_gate.py scripts/info_perm_gate.py scripts/lib/info_perm.py scripts/lib/home_gpus.py scripts/readme-modify-gate.sh scripts/modify-post-change.sh scripts/readme_consistency_gate.py scripts/smoke-check.sh scripts/check-env.sh scripts/wait-train.sh scripts/claude_stream_summarize.py scripts/claude_stream_result_watchdog.py scripts/auto-run-batch-tail.sh scripts/refresh-human-guidance-baseline.sh scripts/analyze_hardcoded_params.py scripts/human_guidance_gate.py scripts/manual-run-scope-check.sh scripts/repair_keeper.py scripts/check_innovation_vocab.py scripts/check_exploration_stamp.py scripts/e_feedback.py scripts/lib/exploration_stamp.py scripts/lib/e_feedback_store.py scripts/lib/governance-rev.sh scripts/lib/nn-state.sh scripts/lib/scenario_inventory.py scripts/lib/experiment_mode.py scripts/lib/migrate_agent_keys.py scripts/migrate_to_exploration_mode.py scripts/lib/nn_config.py scripts/lib/presets.py scripts/lib/train_branch.py scripts/lib/train_branch_types.py scripts/lib/adapter_accept.py scripts/lib/framework_binding.py scripts/lib/smoke_metrics_gate.py scripts/lib/auto_mode.py scripts/lib/check_env_import_classify.py scripts/lib/migrate_finalize_run_kwargs.py scripts/lib/baseline_anchors_status.py scripts/view_runs.py scripts/check_brief.py scripts/check_goal.py scripts/check_metric_floor.py scripts/scan_no_fallback.py; do
  [[ -f "$TEMPLATE_PKG/$need" ]] || { echo "[governance-sync] FAIL: 模板包缺少 $need（TEMPLATE_PKG=$TEMPLATE_PKG）" >&2; exit 1; }
done

mkdir -p "$PROJECT_ROOT/scripts/lib"
cp "$TEMPLATE_PKG/scripts/lib/governance-rev.sh" "$PROJECT_ROOT/scripts/lib/governance-rev.sh"
cp "$TEMPLATE_PKG/scripts/lib/nn-state.sh" "$PROJECT_ROOT/scripts/lib/nn-state.sh"
cp "$TEMPLATE_PKG/scripts/lib/scenario_inventory.py" "$PROJECT_ROOT/scripts/lib/scenario_inventory.py"
# config restructure: nn_config canonical shim + migrate_agent_keys（agent.* → 顶层 additive）
cp "$TEMPLATE_PKG/scripts/lib/nn_config.py" "$PROJECT_ROOT/scripts/lib/nn_config.py"
cp "$TEMPLATE_PKG/scripts/lib/migrate_agent_keys.py" "$PROJECT_ROOT/scripts/lib/migrate_agent_keys.py"
# 2026-07-05 v4: ensure migrate_goal_schema.py present in scripts/lib (Step 2)
cp "$TEMPLATE_PKG/scripts/lib/migrate_goal_schema.py" "$PROJECT_ROOT/scripts/lib/migrate_goal_schema.py"
# v1.33.0: ensure migrate_metrics_shape.py present in scripts/lib (Step 2)
cp "$TEMPLATE_PKG/scripts/lib/migrate_metrics_shape.py" "$PROJECT_ROOT/scripts/lib/migrate_metrics_shape.py"
# 2026-07 config-minimal：presets 必须随 lib 下发（abcde_modifier_derive 已退役）
cp "$TEMPLATE_PKG/scripts/lib/presets.py" "$PROJECT_ROOT/scripts/lib/presets.py"
cp "$TEMPLATE_PKG/scripts/lib/train_branch.py" "$PROJECT_ROOT/scripts/lib/train_branch.py"
cp "$TEMPLATE_PKG/scripts/lib/train_branch_types.py" "$PROJECT_ROOT/scripts/lib/train_branch_types.py"
cp "$TEMPLATE_PKG/scripts/lib/adapter_accept.py" "$PROJECT_ROOT/scripts/lib/adapter_accept.py"
cp "$TEMPLATE_PKG/scripts/lib/framework_binding.py" "$PROJECT_ROOT/scripts/lib/framework_binding.py"
cp "$TEMPLATE_PKG/scripts/lib/smoke_metrics_gate.py" "$PROJECT_ROOT/scripts/lib/smoke_metrics_gate.py"
cp "$TEMPLATE_PKG/scripts/lib/auto_mode.py" "$PROJECT_ROOT/scripts/lib/auto_mode.py"
cp "$TEMPLATE_PKG/scripts/lib/scenario_contract_guard.py" "$PROJECT_ROOT/scripts/lib/scenario_contract_guard.py"
cp "$TEMPLATE_PKG/scripts/lib/scan_cfg_path_fallback.py" "$PROJECT_ROOT/scripts/lib/scan_cfg_path_fallback.py"
cp "$TEMPLATE_PKG/scripts/lib/scan_shared_context_contract.py" "$PROJECT_ROOT/scripts/lib/scan_shared_context_contract.py"
cp "$TEMPLATE_PKG/scripts/lib/scan_abcde_manual_hygiene.py" "$PROJECT_ROOT/scripts/lib/scan_abcde_manual_hygiene.py"
cp "$TEMPLATE_PKG/scripts/lib/check_env_import_classify.py" "$PROJECT_ROOT/scripts/lib/check_env_import_classify.py"
cp "$TEMPLATE_PKG/scripts/lib/migrate_finalize_run_kwargs.py" "$PROJECT_ROOT/scripts/lib/migrate_finalize_run_kwargs.py"
cp "$TEMPLATE_PKG/scripts/lib/contract_test_signature.py" "$PROJECT_ROOT/scripts/lib/contract_test_signature.py"
cp "$TEMPLATE_PKG/scripts/lib/governance_sync_manifest.yaml" "$PROJECT_ROOT/scripts/lib/governance_sync_manifest.yaml"
cp "$TEMPLATE_PKG/scripts/lib/governance_sync_manifest.py" "$PROJECT_ROOT/scripts/lib/governance_sync_manifest.py"
if [[ ! -f "$PROJECT_ROOT/.gitignore" ]]; then
  cp "$TEMPLATE_PKG/.gitignore" "$PROJECT_ROOT/.gitignore"
  echo "[governance-sync] init .gitignore (missing only)"
else
  # amend path: 追加 _runs/doctor_reports/* 规则（如缺失），不动已有行
  _gsync_gitignore_added=0
  if ! grep -qF '_runs/doctor_reports/*' "$PROJECT_ROOT/.gitignore"; then
    {
      echo ""
      echo "# _runs/doctor_reports/ (added by governance-sync — round-doctor 漂移报告)"
      echo "_runs/doctor_reports/*"
      echo "!_runs/doctor_reports/README.md"
    } >> "$PROJECT_ROOT/.gitignore"
    _gsync_gitignore_added=1
  fi
  if [[ "$_gsync_gitignore_added" -eq 1 ]]; then
    echo "[governance-sync] amend .gitignore (追加 doctor_reports 忽略行)"
  else
    echo "[governance-sync] skip .gitignore (exists — 已含 doctor_reports 规则)"
  fi
fi
cp "$TEMPLATE_PKG/profiles.yaml" "$PROJECT_ROOT/profiles.yaml"

# 迁移 agent.* → 顶层 block（additive；旧业务仓 yaml 补顶层块）。幂等；非致命。
# ⚠️ 必须在 merge-nn-config-keys 之前跑：先把项目 agent.* 值抬到顶层，否则 merge
# 会把 template 默认顶层值加进来覆盖项目特定值（如项目 agent.exploration=inductive
# 被 template 默认 conservative 吃掉 — R3 沙盒测试抓的 bug）。
if [[ -f "$PROJECT_ROOT/nn-config.yaml" ]] && [[ -f "$PROJECT_ROOT/scripts/lib/migrate_agent_keys.py" ]]; then
  python3 "$PROJECT_ROOT/scripts/lib/migrate_agent_keys.py" \
    --yaml "$PROJECT_ROOT/nn-config.yaml" --write --cleanup || {
    echo "[governance-sync] WARN: migrate_agent_keys 失败（继续）" >&2
  }
fi

# 老 mode 字段 → 顶层 exploration_mode 一次性迁移（agent.experiment_mode /
# agent.objective_mode / experiment.mode / exploration.{style,mode} → exploration_mode + 删老键）。
# 幂等；无法推断 → fail-loud（migrate 函数 ValueError；main exit 1；此处 WARN+继续）。
# ⚠️ 必须在 merge-nn-config-keys 之前：merge 会把 template 的 exploration_mode 默认值加进来，
# 本脚本看到已有 exploration_mode 即判 idempotent、老键不删（干净切失败）。
if [[ -f "$PROJECT_ROOT/nn-config.yaml" ]] && [[ -f "$TEMPLATE_PKG/scripts/migrate_to_exploration_mode.py" ]]; then
  cp "$TEMPLATE_PKG/scripts/migrate_to_exploration_mode.py" "$PROJECT_ROOT/scripts/migrate_to_exploration_mode.py"
  python3 "$PROJECT_ROOT/scripts/migrate_to_exploration_mode.py" \
    "$PROJECT_ROOT/nn-config.yaml" --write || {
      echo "[governance-sync] WARN: migrate_to_exploration_mode 失败（继续）" >&2
  }
fi

# Step 2 (v4): goal schema 迁移 (agent.goal_value/scenario_goals/goal_stop_mode → goal.target/per_scenario/policy)
# Idempotent; 非致命 (WARN + 继续).
if [[ -f "$PROJECT_ROOT/nn-config.yaml" ]] && [[ -f "$PROJECT_ROOT/scripts/lib/migrate_goal_schema.py" ]]; then
  python3 "$PROJECT_ROOT/scripts/lib/migrate_goal_schema.py" \
    --yaml "$PROJECT_ROOT/nn-config.yaml" --write || {
    echo "[governance-sync] WARN: migrate_goal_schema 失败（继续）" >&2
  }
fi

# v1.33.0: 业务仓拉新版后自动跑 metrics_shape 迁移(workspace_kind → metrics_shape)
# Idempotent; 非致命 (WARN + 继续).
if [[ -f "$PROJECT_ROOT/scripts/lib/migrate_metrics_shape.py" ]]; then
  python3 "$PROJECT_ROOT/scripts/lib/migrate_metrics_shape.py" "$PROJECT_ROOT" \
    || echo "[governance-sync] WARN: migrate_metrics_shape 失败(继续;业务仓可手动跑)" >&2
fi

if [[ -f "$PROJECT_ROOT/scripts/lib/migrate_finalize_run_kwargs.py" ]]; then
  if ! python3 "$PROJECT_ROOT/scripts/lib/migrate_finalize_run_kwargs.py" "$PROJECT_ROOT"; then
    echo "[governance-sync] FAIL: train.py 仍含 finalize_run(best_metrics=...)" >&2
    echo "  修复: python3 scripts/lib/migrate_finalize_run_kwargs.py \"$PROJECT_ROOT\" --apply" >&2
    exit 1
  fi
fi

# D 档 DATA_SAMPLER：在 prepare_data 后插入 ws.wrap_train_loader（experiment.py 已下发钩子）
if [[ -f "$TEMPLATE_PKG/scripts/lib/migrate_wrap_train_loader.py" ]]; then
  cp "$TEMPLATE_PKG/scripts/lib/migrate_wrap_train_loader.py" \
    "$PROJECT_ROOT/scripts/lib/migrate_wrap_train_loader.py"
  python3 "$PROJECT_ROOT/scripts/lib/migrate_wrap_train_loader.py" "$PROJECT_ROOT" --apply || {
    echo "[governance-sync] WARN: migrate_wrap_train_loader 失败（继续；可手动 --apply）" >&2
  }
fi

# Step 3 (ABCDE/v4): 老业务仓若缺边界文件则补写。**实际调用放到 ABCDE 脚本 + 模板 cp 块之后**
# （见下方），原因：abcde_migrate.py 找模板走 <repo>/skills/maintainer/auto-nn-init/templates/，
# 模板没 cp 过去就 read_text() FileNotFoundError → 漏写 manual。
# 此处仅留注释；删 prefix hook 是防「逻辑漂移」闸（绝不从此处调 abcde_migrate.py）。

# nn-config.yaml — R1 merge-keys：只补模板缺失键，不覆盖业务已有值；无文件则 init
_merge_nn_config_py="$TEMPLATE_PKG/scripts/merge-nn-config-keys.py"
if [[ ! -f "$_merge_nn_config_py" && -f "$TEMPLATE_ROOT/scripts/merge-nn-config-keys.py" ]]; then
  _merge_nn_config_py="$TEMPLATE_ROOT/scripts/merge-nn-config-keys.py"
fi
if [[ -f "$_merge_nn_config_py" ]]; then
  cp "$_merge_nn_config_py" "$PROJECT_ROOT/scripts/merge-nn-config-keys.py"
  chmod +x "$PROJECT_ROOT/scripts/merge-nn-config-keys.py" 2>/dev/null || true
fi
if [[ -f "$TEMPLATE_PKG/nn-config.yaml" ]]; then
  if [[ -f "$PROJECT_ROOT/nn-config.yaml" ]]; then
    if [[ -f "$_merge_nn_config_py" ]]; then
      echo "[governance-sync] nn-config: merge missing template keys (preserve project values)"
      python3 "$_merge_nn_config_py" \
        --project "$PROJECT_ROOT/nn-config.yaml" \
        --template "$TEMPLATE_PKG/nn-config.yaml"
    else
      echo "[governance-sync] WARN: merge-nn-config-keys.py missing — skip nn-config merge" >&2
    fi
  else
    cp "$TEMPLATE_PKG/nn-config.yaml" "$PROJECT_ROOT/nn-config.yaml"
    echo "[governance-sync] init nn-config.yaml (missing only)"
  fi
fi

cp "$TEMPLATE_PKG/experiment.py" "$PROJECT_ROOT/experiment.py"
cp "$TEMPLATE_PKG/CLAUDE.md" "$PROJECT_ROOT/CLAUDE.md"
cp "$TEMPLATE_PKG/PROTOCOL.md" "$PROJECT_ROOT/PROTOCOL.md"
# R3 always cp：python -m contract CLI 壳（无业务逻辑；缺则 doctor contract_sanity FAIL）
mkdir -p "$PROJECT_ROOT/contract"
cp "$TEMPLATE_PKG/contract/__main__.py" "$PROJECT_ROOT/contract/__main__.py"
cp "$TEMPLATE_PKG/auto-nn-run.sh" "$PROJECT_ROOT/auto-nn-run.sh"
# v2.5.6 fix: governance-sync 之前漏 cp scripts/auto-nn-setup.py，致业务仓 update
# 后 setup.py 仍是 init 时代的老版本（不支持 gpus block list 格式），跑
# /auto-nn-setup 报 "GPU 索引列表含非法 token: '-'"。补上后业务仓 update
# 才能拿到 v2.0.2 已修的 setup.py（_NNCFG_GPUS_BLOCK_RE 整块匹配三格式）。
cp "$TEMPLATE_PKG/scripts/auto-nn-setup.py" "$PROJECT_ROOT/scripts/auto-nn-setup.py"
# v2.5.7: governance-sync 之前漏 cp scripts/repair_keeper.py，致业务仓 update 后
# scripts/repair_keeper.py 不存在 → nn-doctor keeper_stale 检查跑不到（走 else 分支
# 报 "缺少 scripts/repair_keeper.py"）。补上后业务仓 update 才能拿到 v2.5.7 新增的
# keeper 路径相对化 + pointer 指 TSV 主指标最优修复工具。
cp "$TEMPLATE_PKG/scripts/repair_keeper.py" "$PROJECT_ROOT/scripts/repair_keeper.py"
# v2.8.3: check_innovation_vocab.py 同步（doctor innovation_vocab 检查扫 TSV 旧词）
cp "$TEMPLATE_PKG/scripts/check_innovation_vocab.py" "$PROJECT_ROOT/scripts/check_innovation_vocab.py"
# 探索格子必打 / 禁 E- / e_feedback schema（doctor exploration_space_stamp）
cp "$TEMPLATE_PKG/scripts/check_exploration_stamp.py" "$PROJECT_ROOT/scripts/check_exploration_stamp.py"
chmod +x "$PROJECT_ROOT/scripts/check_exploration_stamp.py" 2>/dev/null || true
cp "$TEMPLATE_PKG/scripts/e_feedback.py" "$PROJECT_ROOT/scripts/e_feedback.py"
chmod +x "$PROJECT_ROOT/scripts/e_feedback.py" 2>/dev/null || true

if [[ -f "$TEMPLATE_PKG/scripts/auto-nn-update.sh" ]]; then
  cp "$TEMPLATE_PKG/scripts/auto-nn-update.sh" "$PROJECT_ROOT/scripts/auto-nn-update.sh"
  chmod +x "$PROJECT_ROOT/scripts/auto-nn-update.sh" 2>/dev/null || true
fi
# 2026-06-20 rename: 旧名 nn-auto-run.sh 已废弃,同步时清掉孤儿文件
rm -f "$PROJECT_ROOT/nn-auto-run.sh"
cp "$TEMPLATE_PKG/reflect.py" "$PROJECT_ROOT/reflect.py"
chmod +x "$PROJECT_ROOT/reflect.py" 2>/dev/null || true
cp "$TEMPLATE_PKG/scripts/verify-migration-complete.sh" "$PROJECT_ROOT/scripts/verify-migration-complete.sh"
# 自复制须 temp+mv：业务仓 `bash scripts/governance-sync.sh` 时 in-place cp 会截断
# 正在执行的 inode，bash 继续读后续行（~L284 D 组）间歇性 parse error；重跑已过因磁盘已是完整文件。
_gsync_self="$PROJECT_ROOT/scripts/governance-sync.sh"
_gsync_self_tmp="$PROJECT_ROOT/scripts/.governance-sync.sh.$$.new"
cp "$TEMPLATE_PKG/scripts/governance-sync.sh" "$_gsync_self_tmp"
mv -f "$_gsync_self_tmp" "$_gsync_self"
cp "$TEMPLATE_PKG/scripts/rl_workspace_gate.py" "$PROJECT_ROOT/scripts/rl_workspace_gate.py"
cp "$TEMPLATE_PKG/scripts/d2_data_split_gate.py" "$PROJECT_ROOT/scripts/d2_data_split_gate.py"
cp "$TEMPLATE_PKG/scripts/scenario_policy_gate.py" "$PROJECT_ROOT/scripts/scenario_policy_gate.py"
# 信息权限（spec 20260905_1755）：README INFO_PERM 块门禁 + 扫描库（G-信息权限 / verify / doctor 共用）
cp "$TEMPLATE_PKG/scripts/info_perm_gate.py" "$PROJECT_ROOT/scripts/info_perm_gate.py"
cp "$TEMPLATE_PKG/scripts/lib/info_perm.py" "$PROJECT_ROOT/scripts/lib/info_perm.py"
cp "$TEMPLATE_PKG/scripts/lib/home_gpus.py" "$PROJECT_ROOT/scripts/lib/home_gpus.py"
if [[ -f "$TEMPLATE_PKG/scripts/set-scenario-policy.py" ]]; then
  cp "$TEMPLATE_PKG/scripts/set-scenario-policy.py" "$PROJECT_ROOT/scripts/set-scenario-policy.py"
  chmod +x "$PROJECT_ROOT/scripts/set-scenario-policy.py" 2>/dev/null || true
fi
# === 版本管理（2026-07-06 spec）===
if [[ -f "$TEMPLATE_PKG/scripts/check_template_version.py" ]]; then
  cp "$TEMPLATE_PKG/scripts/check_template_version.py" "$PROJECT_ROOT/scripts/check_template_version.py"
  chmod +x "$PROJECT_ROOT/scripts/check_template_version.py" 2>/dev/null || true
fi
if [[ -f "$TEMPLATE_PKG/scripts/_check_template_version.sh" ]]; then
  cp "$TEMPLATE_PKG/scripts/_check_template_version.sh" "$PROJECT_ROOT/scripts/_check_template_version.sh"
  chmod +x "$PROJECT_ROOT/scripts/_check_template_version.sh" 2>/dev/null || true
fi
if [[ -f "$TEMPLATE_PKG/scripts/release-check.sh" ]]; then
  cp "$TEMPLATE_PKG/scripts/release-check.sh" "$PROJECT_ROOT/scripts/release-check.sh"
  chmod +x "$PROJECT_ROOT/scripts/release-check.sh" 2>/dev/null || true
fi
if [[ -f "$TEMPLATE_PKG/scripts/template-version.sh" ]]; then
  cp "$TEMPLATE_PKG/scripts/template-version.sh" "$PROJECT_ROOT/scripts/template-version.sh"
  chmod +x "$PROJECT_ROOT/scripts/template-version.sh" 2>/dev/null || true
fi
cp "$TEMPLATE_PKG/scripts/readme-modify-gate.sh" "$PROJECT_ROOT/scripts/readme-modify-gate.sh"
cp "$TEMPLATE_PKG/scripts/modify-post-change.sh" "$PROJECT_ROOT/scripts/modify-post-change.sh"
chmod +x "$PROJECT_ROOT/scripts/modify-post-change.sh" 2>/dev/null || true
cp "$TEMPLATE_PKG/scripts/readme_consistency_gate.py" "$PROJECT_ROOT/scripts/readme_consistency_gate.py"
cp "$TEMPLATE_PKG/scripts/smoke-check.sh" "$PROJECT_ROOT/scripts/smoke-check.sh"
cp "$TEMPLATE_PKG/scripts/check-env.sh" "$PROJECT_ROOT/scripts/check-env.sh"
chmod +x "$PROJECT_ROOT/scripts/check-env.sh" 2>/dev/null || true
cp "$TEMPLATE_PKG/scripts/wait-train.sh" "$PROJECT_ROOT/scripts/wait-train.sh"
cp "$TEMPLATE_PKG/scripts/claude_stream_summarize.py" "$PROJECT_ROOT/scripts/claude_stream_summarize.py"
cp "$TEMPLATE_PKG/scripts/claude_stream_result_watchdog.py" "$PROJECT_ROOT/scripts/claude_stream_result_watchdog.py"
# nn_stream_watch 子包（claude_stream_summarize 的渲染引擎；同步随主包下发）
if [[ -d "$TEMPLATE_PKG/scripts/nn_stream_watch" ]]; then
  mkdir -p "$PROJECT_ROOT/scripts/nn_stream_watch"
  for f in __init__.py state.py detectors.py formatter.py; do
    [[ -f "$TEMPLATE_PKG/scripts/nn_stream_watch/$f" ]] && \
      cp "$TEMPLATE_PKG/scripts/nn_stream_watch/$f" "$PROJECT_ROOT/scripts/nn_stream_watch/$f"
  done
fi
cp "$TEMPLATE_PKG/scripts/auto-run-batch-tail.sh" "$PROJECT_ROOT/scripts/auto-run-batch-tail.sh"
cp "$TEMPLATE_PKG/scripts/refresh-human-guidance-baseline.sh" "$PROJECT_ROOT/scripts/refresh-human-guidance-baseline.sh"
chmod +x "$PROJECT_ROOT/scripts/refresh-human-guidance-baseline.sh" 2>/dev/null || true
cp "$TEMPLATE_PKG/scripts/human_guidance_gate.py" "$PROJECT_ROOT/scripts/human_guidance_gate.py"
chmod +x "$PROJECT_ROOT/scripts/human_guidance_gate.py" 2>/dev/null || true
cp "$TEMPLATE_PKG/scripts/verify_project_layout.py" "$PROJECT_ROOT/scripts/verify_project_layout.py"
cp "$TEMPLATE_PKG/scripts/regen_results_tsv.py" "$PROJECT_ROOT/scripts/regen_results_tsv.py"
cp "$TEMPLATE_PKG/scripts/sync_exploration_ledger.py" "$PROJECT_ROOT/scripts/sync_exploration_ledger.py"
cp "$TEMPLATE_PKG/scripts/sync_ledger.py" "$PROJECT_ROOT/scripts/sync_ledger.py"
cp "$TEMPLATE_PKG/scripts/govern-runs.sh" "$PROJECT_ROOT/scripts/govern-runs.sh"
cp "$TEMPLATE_PKG/scripts/prune-runs.py" "$PROJECT_ROOT/scripts/prune-runs.py"
cp "$TEMPLATE_PKG/scripts/clear-runs.sh" "$PROJECT_ROOT/scripts/clear-runs.sh"
cp "$TEMPLATE_PKG/scripts/clear_inspect.py" "$PROJECT_ROOT/scripts/clear_inspect.py"
chmod +x "$PROJECT_ROOT/scripts/clear-runs.sh" 2>/dev/null || true
cp "$TEMPLATE_PKG/scripts/nn-doctor.sh" "$PROJECT_ROOT/scripts/nn-doctor.sh"
chmod +x "$PROJECT_ROOT/scripts/nn-doctor.sh" 2>/dev/null || true
cp "$TEMPLATE_PKG/scripts/manual-run-scope-check.sh" "$PROJECT_ROOT/scripts/manual-run-scope-check.sh"
chmod +x "$PROJECT_ROOT/scripts/manual-run-scope-check.sh" 2>/dev/null || true
cp "$TEMPLATE_PKG/scripts/analyze_hardcoded_params.py" "$PROJECT_ROOT/scripts/analyze_hardcoded_params.py"
cp "$TEMPLATE_PKG/scripts/modify-config.py" "$PROJECT_ROOT/scripts/modify-config.py"
chmod +x "$PROJECT_ROOT/scripts/modify-config.py" 2>/dev/null || true
if [[ -f "$TEMPLATE_PKG/scripts/scan_cfg_defaults.py" ]]; then
  cp "$TEMPLATE_PKG/scripts/scan_cfg_defaults.py" "$PROJECT_ROOT/scripts/scan_cfg_defaults.py"
  chmod +x "$PROJECT_ROOT/scripts/scan_cfg_defaults.py" 2>/dev/null || true
fi
if [[ -f "$TEMPLATE_PKG/scripts/view_runs.py" ]]; then
  cp "$TEMPLATE_PKG/scripts/view_runs.py" "$PROJECT_ROOT/scripts/view_runs.py"
  chmod +x "$PROJECT_ROOT/scripts/view_runs.py" 2>/dev/null || true
fi
# auto-nn-check / console 看板 brief：漏 sync 会导致业务仓缺脚本、console 501
if [[ -f "$TEMPLATE_PKG/scripts/check_brief.py" ]]; then
  cp "$TEMPLATE_PKG/scripts/check_brief.py" "$PROJECT_ROOT/scripts/check_brief.py"
  chmod +x "$PROJECT_ROOT/scripts/check_brief.py" 2>/dev/null || true
fi
# auto-nn-baseline：立尺 CLI + 贴签库；漏 sync 业务仓无法 /auto-nn-plain / -reference
if [[ -f "$TEMPLATE_PKG/scripts/nn_baseline.py" ]]; then
  cp "$TEMPLATE_PKG/scripts/nn_baseline.py" "$PROJECT_ROOT/scripts/nn_baseline.py"
  chmod +x "$PROJECT_ROOT/scripts/nn_baseline.py" 2>/dev/null || true
fi
if [[ -f "$TEMPLATE_PKG/scripts/lib/baseline_stamp.py" ]]; then
  mkdir -p "$PROJECT_ROOT/scripts/lib"
  cp "$TEMPLATE_PKG/scripts/lib/baseline_stamp.py" "$PROJECT_ROOT/scripts/lib/baseline_stamp.py"
fi
if [[ -f "$TEMPLATE_PKG/scripts/nn_audit.py" ]]; then
  cp "$TEMPLATE_PKG/scripts/nn_audit.py" "$PROJECT_ROOT/scripts/nn_audit.py"
  chmod +x "$PROJECT_ROOT/scripts/nn_audit.py" 2>/dev/null || true
fi
if [[ -f "$TEMPLATE_PKG/scripts/lib/audit_core.py" ]]; then
  mkdir -p "$PROJECT_ROOT/scripts/lib"
  cp "$TEMPLATE_PKG/scripts/lib/audit_core.py" "$PROJECT_ROOT/scripts/lib/audit_core.py"
fi
if [[ -f "$TEMPLATE_PKG/scripts/lib/audit_attest.py" ]]; then
  mkdir -p "$PROJECT_ROOT/scripts/lib"
  cp "$TEMPLATE_PKG/scripts/lib/audit_attest.py" "$PROJECT_ROOT/scripts/lib/audit_attest.py"
fi
if [[ -f "$TEMPLATE_PKG/scripts/check_goal.py" ]]; then
  cp "$TEMPLATE_PKG/scripts/check_goal.py" "$PROJECT_ROOT/scripts/check_goal.py"
  chmod +x "$PROJECT_ROOT/scripts/check_goal.py" 2>/dev/null || true
fi
if [[ -f "$TEMPLATE_PKG/scripts/manage_goal.py" ]]; then
  cp "$TEMPLATE_PKG/scripts/manage_goal.py" "$PROJECT_ROOT/scripts/manage_goal.py"
  chmod +x "$PROJECT_ROOT/scripts/manage_goal.py" 2>/dev/null || true
fi
if [[ -f "$TEMPLATE_PKG/scripts/check_metric_floor.py" ]]; then
  cp "$TEMPLATE_PKG/scripts/check_metric_floor.py" "$PROJECT_ROOT/scripts/check_metric_floor.py"
  chmod +x "$PROJECT_ROOT/scripts/check_metric_floor.py" 2>/dev/null || true
fi
if [[ -f "$TEMPLATE_PKG/scripts/lib/init_qa_log.py" ]]; then
  mkdir -p "$PROJECT_ROOT/scripts/lib"
  cp "$TEMPLATE_PKG/scripts/lib/init_qa_log.py" "$PROJECT_ROOT/scripts/lib/init_qa_log.py"
fi
if [[ -f "$TEMPLATE_PKG/scripts/append-init-qa-log.py" ]]; then
  cp "$TEMPLATE_PKG/scripts/append-init-qa-log.py" "$PROJECT_ROOT/scripts/append-init-qa-log.py"
  chmod +x "$PROJECT_ROOT/scripts/append-init-qa-log.py" 2>/dev/null || true
fi
if [[ -f "$TEMPLATE_PKG/scripts/validate-init-qa-log.py" ]]; then
  cp "$TEMPLATE_PKG/scripts/validate-init-qa-log.py" "$PROJECT_ROOT/scripts/validate-init-qa-log.py"
  chmod +x "$PROJECT_ROOT/scripts/validate-init-qa-log.py" 2>/dev/null || true
fi
# 立项答案清单 + 信息权限三问落表（spec 20260905_1845）；题库随 Init 组 docs/init/ 整目录下发
for _init_tool in scripts/lib/init_answers.py scripts/init_answers.py scripts/init_info_perm.py; do
  if [[ -f "$TEMPLATE_PKG/$_init_tool" ]]; then
    mkdir -p "$PROJECT_ROOT/$(dirname "$_init_tool")"
    cp "$TEMPLATE_PKG/$_init_tool" "$PROJECT_ROOT/$_init_tool"
    chmod +x "$PROJECT_ROOT/$_init_tool" 2>/dev/null || true
  fi
done
if [[ -f "$TEMPLATE_PKG/scripts/lib/skill_activity.py" ]]; then
  mkdir -p "$PROJECT_ROOT/scripts/lib"
  cp "$TEMPLATE_PKG/scripts/lib/skill_activity.py" "$PROJECT_ROOT/scripts/lib/skill_activity.py"
fi
if [[ -f "$TEMPLATE_PKG/scripts/append-skill-activity.py" ]]; then
  cp "$TEMPLATE_PKG/scripts/append-skill-activity.py" "$PROJECT_ROOT/scripts/append-skill-activity.py"
  chmod +x "$PROJECT_ROOT/scripts/append-skill-activity.py" 2>/dev/null || true
fi
if [[ -f "$TEMPLATE_PKG/scripts/lib/experiment_mode.py" ]]; then
  mkdir -p "$PROJECT_ROOT/scripts/lib"
  cp "$TEMPLATE_PKG/scripts/lib/experiment_mode.py" "$PROJECT_ROOT/scripts/lib/experiment_mode.py"
fi
if [[ -f "$TEMPLATE_PKG/scripts/scan_no_fallback.py" ]]; then
  cp "$TEMPLATE_PKG/scripts/scan_no_fallback.py" "$PROJECT_ROOT/scripts/scan_no_fallback.py"
  chmod +x "$PROJECT_ROOT/scripts/scan_no_fallback.py" 2>/dev/null || true
fi
# L3-*: 多槽门禁 / dest 验证 — v1.5.5+ 沙箱端到端验证发现缺这些（init_qa_log_walker 已退役）
if [[ -f "$TEMPLATE_PKG/scripts/check_multi_slot_finalize.py" ]]; then
  cp "$TEMPLATE_PKG/scripts/check_multi_slot_finalize.py" "$PROJECT_ROOT/scripts/check_multi_slot_finalize.py"
  chmod +x "$PROJECT_ROOT/scripts/check_multi_slot_finalize.py" 2>/dev/null || true
fi
if [[ -f "$TEMPLATE_PKG/scripts/verify_governance_sync_dest.sh" ]]; then
  cp "$TEMPLATE_PKG/scripts/verify_governance_sync_dest.sh" "$PROJECT_ROOT/scripts/verify_governance_sync_dest.sh"
  chmod +x "$PROJECT_ROOT/scripts/verify_governance_sync_dest.sh" 2>/dev/null || true
fi
if [[ -f "$TEMPLATE_PKG/scripts/clear_experience.py" ]]; then
  cp "$TEMPLATE_PKG/scripts/clear_experience.py" "$PROJECT_ROOT/scripts/clear_experience.py"
fi
if [[ -f "$TEMPLATE_PKG/scripts/clear_factory.py" ]]; then
  cp "$TEMPLATE_PKG/scripts/clear_factory.py" "$PROJECT_ROOT/scripts/clear_factory.py"
fi
if [[ -f "$TEMPLATE_PKG/scripts/compress-experience.py" ]]; then
  cp "$TEMPLATE_PKG/scripts/compress-experience.py" "$PROJECT_ROOT/scripts/compress-experience.py"
  mkdir -p "$PROJECT_ROOT/scripts/lib"
  cp "$TEMPLATE_PKG/scripts/lib/experience_compress.py" "$PROJECT_ROOT/scripts/lib/experience_compress.py"
  [[ -f "$TEMPLATE_PKG/scripts/lib/__init__.py" ]] && \
    cp "$TEMPLATE_PKG/scripts/lib/__init__.py" "$PROJECT_ROOT/scripts/lib/__init__.py"
fi
if [[ -f "$TEMPLATE_PKG/scripts/summarize-runs.py" ]]; then
  mkdir -p "$PROJECT_ROOT/scripts/lib"
  cp "$TEMPLATE_PKG/scripts/summarize-runs.py" "$PROJECT_ROOT/scripts/summarize-runs.py"
  cp "$TEMPLATE_PKG/scripts/lib/run_ledger_summary.py" "$PROJECT_ROOT/scripts/lib/run_ledger_summary.py"
  [[ -f "$TEMPLATE_PKG/scripts/lib/__init__.py" ]] && \
    cp "$TEMPLATE_PKG/scripts/lib/__init__.py" "$PROJECT_ROOT/scripts/lib/__init__.py"
  chmod +x "$PROJECT_ROOT/scripts/summarize-runs.py" 2>/dev/null || true
fi
if [[ -f "$TEMPLATE_PKG/scripts/build-run-context.py" ]]; then
  mkdir -p "$PROJECT_ROOT/scripts/lib"
  cp "$TEMPLATE_PKG/scripts/build-run-context.py" "$PROJECT_ROOT/scripts/build-run-context.py"
  # baseline_anchors_status：build-run-context / metric_analysis / view_runs 依赖（漏 sync 会 ImportError）
  for libf in baseline_anchors_status.py baseline_stamp.py metric_analysis.py experiment_journal.py code_delta.py ledger_anchor.py experience_ack.py experience_sections.py gpu_snapshot.py home_gpus.py; do
    [[ -f "$TEMPLATE_PKG/scripts/lib/$libf" ]] && \
      cp "$TEMPLATE_PKG/scripts/lib/$libf" "$PROJECT_ROOT/scripts/lib/$libf"
  done
  if [[ -f "$TEMPLATE_PKG/scripts/gpu_snapshot.py" ]]; then
    cp "$TEMPLATE_PKG/scripts/gpu_snapshot.py" "$PROJECT_ROOT/scripts/gpu_snapshot.py"
    chmod +x "$PROJECT_ROOT/scripts/gpu_snapshot.py" 2>/dev/null || true
  fi
  for scr in analyse_metrics.py analyse_delta.py analyse_code_delta.py journal_append.py migrate-drop-progress.sh; do
    [[ -f "$TEMPLATE_PKG/scripts/$scr" ]] && cp "$TEMPLATE_PKG/scripts/$scr" "$PROJECT_ROOT/scripts/$scr"
  done
  chmod +x "$PROJECT_ROOT/scripts/migrate-drop-progress.sh" 2>/dev/null || true
fi
if [[ -f "$TEMPLATE_PKG/scripts/lib/train_dynamics.py" ]]; then
  mkdir -p "$PROJECT_ROOT/scripts/lib"
  cp "$TEMPLATE_PKG/scripts/lib/train_dynamics.py" "$PROJECT_ROOT/scripts/lib/train_dynamics.py"
  [[ -f "$TEMPLATE_PKG/scripts/lib/__init__.py" ]] && \
    cp "$TEMPLATE_PKG/scripts/lib/__init__.py" "$PROJECT_ROOT/scripts/lib/__init__.py"
fi
if [[ -f "$TEMPLATE_PKG/scripts/lib/scenario_bindings.py" ]]; then
  mkdir -p "$PROJECT_ROOT/scripts/lib"
  cp "$TEMPLATE_PKG/scripts/lib/scenario_bindings.py" "$PROJECT_ROOT/scripts/lib/scenario_bindings.py"
fi
if [[ -f "$TEMPLATE_PKG/scripts/lib/goal_spec.py" ]]; then
  mkdir -p "$PROJECT_ROOT/scripts/lib"
  cp "$TEMPLATE_PKG/scripts/lib/goal_spec.py" "$PROJECT_ROOT/scripts/lib/goal_spec.py"
fi
if [[ -f "$TEMPLATE_PKG/scripts/train_dynamics_gate.py" ]]; then
  cp "$TEMPLATE_PKG/scripts/train_dynamics_gate.py" "$PROJECT_ROOT/scripts/train_dynamics_gate.py"
  chmod +x "$PROJECT_ROOT/scripts/train_dynamics_gate.py" 2>/dev/null || true
fi
chmod +x "$PROJECT_ROOT/scripts/verify-migration-complete.sh" 2>/dev/null || true
chmod +x "$PROJECT_ROOT/scripts/governance-sync.sh" 2>/dev/null || true
chmod +x "$PROJECT_ROOT/scripts/rl_workspace_gate.py" 2>/dev/null || true
chmod +x "$PROJECT_ROOT/scripts/d2_data_split_gate.py" 2>/dev/null || true
chmod +x "$PROJECT_ROOT/scripts/scenario_policy_gate.py" 2>/dev/null || true
chmod +x "$PROJECT_ROOT/scripts/info_perm_gate.py" 2>/dev/null || true
chmod +x "$PROJECT_ROOT/scripts/lib/info_perm.py" 2>/dev/null || true
chmod +x "$PROJECT_ROOT/scripts/readme-modify-gate.sh" 2>/dev/null || true
chmod +x "$PROJECT_ROOT/scripts/readme_consistency_gate.py" 2>/dev/null || true
chmod +x "$PROJECT_ROOT/scripts/smoke-check.sh" 2>/dev/null || true
chmod +x "$PROJECT_ROOT/scripts/check-env.sh" 2>/dev/null || true
chmod +x "$PROJECT_ROOT/scripts/wait-train.sh" 2>/dev/null || true
chmod +x "$PROJECT_ROOT/scripts/claude_stream_summarize.py" 2>/dev/null || true
chmod +x "$PROJECT_ROOT/scripts/claude_stream_result_watchdog.py" 2>/dev/null || true
# nn_stream_watch 子包不需可执行位（python 包）
chmod +x "$PROJECT_ROOT/scripts/auto-run-batch-tail.sh" 2>/dev/null || true
chmod +x "$PROJECT_ROOT/scripts/sync_ledger.py" 2>/dev/null || true

# stamp-required（≡ train_runtime）：写戳前自检；缺文件则不写 version/governance-rev
_stamp_miss="$(
  PYTHONPATH="$TEMPLATE_PKG/scripts${PYTHONPATH:+:$PYTHONPATH}" python3 -c "
from pathlib import Path
from lib.governance_sync_manifest import missing_stamp_required
m = missing_stamp_required(Path(r'''$PROJECT_ROOT'''), manifest_root=Path(r'''$TEMPLATE_PKG'''))
print('\n'.join(m))
" 2>&1
)" || {
  echo "[governance-sync] FAIL: stamp-required 自检无法运行:" >&2
  echo "$_stamp_miss" >&2
  exit 1
}
if [[ -n "${_stamp_miss// }" ]]; then
  echo "[governance-sync] FAIL: stamp-required 文件未齐（不写 version/governance-rev）:" >&2
  printf '%s\n' "$_stamp_miss" | sed 's/^/  - /' >&2
  echo "[governance-sync] 修复: 确认 template/package 含 train_runtime 文件且本脚本 cp 成功，再重跑" >&2
  exit 1
fi

# shellcheck source=lib/governance-rev.sh
source "$TEMPLATE_PKG/scripts/lib/governance-rev.sh"

REV="$(governance_rev_compute "$TEMPLATE_PKG")"
nn_state_write governance-rev "$REV" "$PROJECT_ROOT"
# TPL_SEMVER：版本号文件可能在模板仓根（--template-root=仓库根）或其 template/package/ 子树下
# 用 fallback 链：对维护仓根传 VERSION 直接读；传子树时回退 ../VERSION
if [[ -f "$TEMPLATE_ROOT/VERSION" ]]; then
  TPL_SEMVER="$(tr -d '\r\n' < "$TEMPLATE_ROOT/VERSION")"
elif [[ -f "$TEMPLATE_ROOT/../VERSION" ]]; then
  TPL_SEMVER="$(tr -d '\r\n' < "$TEMPLATE_ROOT/../VERSION")"
else
  TPL_SEMVER="unknown"
fi
TPL_SHA="$(git -C "$TEMPLATE_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
_TPL_STAMP="${TPL_SEMVER}+${TPL_SHA}"
# 立项原始戳：仅「此前既无 version 也无 init」时锁定一次；已有 version、缺 init 的旧仓不回填（防把升版后戳当原始）
_had_ver=0
_had_init=0
[[ -s "$(nn_state_path version "$PROJECT_ROOT")" ]] && _had_ver=1
[[ -s "$(nn_state_path init-template-version "$PROJECT_ROOT")" ]] && _had_init=1
nn_state_write version "$_TPL_STAMP" "$PROJECT_ROOT"
if [[ $_had_init -eq 0 && $_had_ver -eq 0 ]]; then
  nn_state_write_once init-template-version "$_TPL_STAMP" "$PROJECT_ROOT"
fi
# 探索格子发版戳：首次写入 ISO 日期；已存在不覆盖（历史空格 WARN 分界）
nn_state_write_once exploration-stamp-since "$(date -u +%Y-%m-%d)" "$PROJECT_ROOT"

# README — 只 merge 模板区（NAV/QUICKSTART/SKILLS/APPENDIX），保留 §3/§4 业务内容
_merge_readme_py="$TEMPLATE_PKG/scripts/merge-readme-template-blocks.py"
if [[ -f "$_merge_readme_py" ]]; then
  cp "$_merge_readme_py" "$PROJECT_ROOT/scripts/merge-readme-template-blocks.py"
  chmod +x "$PROJECT_ROOT/scripts/merge-readme-template-blocks.py" 2>/dev/null || true
  if [[ -f "$PROJECT_ROOT/README.md" ]]; then
    python3 "$PROJECT_ROOT/scripts/merge-readme-template-blocks.py" \
      --project "$PROJECT_ROOT" --template "$TEMPLATE_PKG" || true
  fi
fi

echo "[governance-sync] OK: 已同步 profiles.yaml + verify + regen_results_tsv + sync_ledger + gates + smoke-check + wait-train + claude_stream_summarize + claude_stream_result_watchdog + view_runs + check_brief + reflect.py + human_guidance_gate"
echo "[governance-sync]     rev=$REV  template_root=$TEMPLATE_ROOT  template_pkg=$TEMPLATE_PKG"

# === governance-sync coverage: 2026-06-19 spec 增补(A+B+C) ===
# A 组:scripts/lib/ 运行时依赖(reflect.py / build-run-context / runtime-activity / human_guidance_gate / auto-nn-run)
cp "$TEMPLATE_PKG/scripts/lib/reflect_index.py" "$PROJECT_ROOT/scripts/lib/reflect_index.py"
cp "$TEMPLATE_PKG/scripts/lib/experiment_journal.py" "$PROJECT_ROOT/scripts/lib/experiment_journal.py"
cp "$TEMPLATE_PKG/scripts/lib/explore_objective.py" "$PROJECT_ROOT/scripts/lib/explore_objective.py"
cp "$TEMPLATE_PKG/scripts/lib/experiment_mode.py" "$PROJECT_ROOT/scripts/lib/experiment_mode.py"
cp "$TEMPLATE_PKG/scripts/lib/reflect_evidence.py" "$PROJECT_ROOT/scripts/lib/reflect_evidence.py"
cp "$TEMPLATE_PKG/scripts/lib/tier_attestation.py" "$PROJECT_ROOT/scripts/lib/tier_attestation.py"
cp "$TEMPLATE_PKG/scripts/lib/runtime_activity.py" "$PROJECT_ROOT/scripts/lib/runtime_activity.py"
cp "$TEMPLATE_PKG/scripts/lib/human_guidance_gate.py" "$PROJECT_ROOT/scripts/lib/human_guidance_gate.py"
cp "$TEMPLATE_PKG/scripts/lib/reflect_brief.py" "$PROJECT_ROOT/scripts/lib/reflect_brief.py"
cp "$TEMPLATE_PKG/scripts/lib/human_guidance_roadmap.py" "$PROJECT_ROOT/scripts/lib/human_guidance_roadmap.py"
cp "$TEMPLATE_PKG/scripts/lib/experience_auto_compress.py" "$PROJECT_ROOT/scripts/lib/experience_auto_compress.py"
if [[ -f "$TEMPLATE_PKG/scripts/lib/experience_ledger_audit.py" ]]; then
  cp "$TEMPLATE_PKG/scripts/lib/experience_ledger_audit.py" "$PROJECT_ROOT/scripts/lib/experience_ledger_audit.py"
fi
cp "$TEMPLATE_PKG/scripts/lib/innovation_audit.py" "$PROJECT_ROOT/scripts/lib/innovation_audit.py"
if [[ -f "$TEMPLATE_PKG/scripts/lib/innovation_fingerprint.py" ]]; then
  cp "$TEMPLATE_PKG/scripts/lib/innovation_fingerprint.py" "$PROJECT_ROOT/scripts/lib/innovation_fingerprint.py"
fi
cp "$TEMPLATE_PKG/scripts/lib/exploration_stamp.py" "$PROJECT_ROOT/scripts/lib/exploration_stamp.py"
cp "$TEMPLATE_PKG/scripts/lib/e_feedback_store.py" "$PROJECT_ROOT/scripts/lib/e_feedback_store.py"
if [[ -f "$TEMPLATE_PKG/scripts/lib/innovation_catalog.yaml" ]]; then
  cp "$TEMPLATE_PKG/scripts/lib/innovation_catalog.yaml" "$PROJECT_ROOT/scripts/lib/innovation_catalog.yaml"
fi
# reflect insight 增强（P1-P4，2026-07-02：fingerprint_diversity / tam_reconcile / leader_attribution）
cp "$TEMPLATE_PKG/scripts/lib/fingerprint_diversity.py" "$PROJECT_ROOT/scripts/lib/fingerprint_diversity.py"
cp "$TEMPLATE_PKG/scripts/lib/tam_reconcile.py" "$PROJECT_ROOT/scripts/lib/tam_reconcile.py"
cp "$TEMPLATE_PKG/scripts/lib/leader_attribution.py" "$PROJECT_ROOT/scripts/lib/leader_attribution.py"
mkdir -p "$PROJECT_ROOT/scripts/lib/external"
if [[ -f "$TEMPLATE_PKG/scripts/lib/external/external_search.py" ]]; then
  cp "$TEMPLATE_PKG/scripts/lib/external/external_search.py" "$PROJECT_ROOT/scripts/lib/external/external_search.py"
fi
cp "$TEMPLATE_PKG/scripts/fingerprint_diversity.sh" "$PROJECT_ROOT/scripts/fingerprint_diversity.sh"
chmod +x "$PROJECT_ROOT/scripts/fingerprint_diversity.sh" 2>/dev/null || true
cp "$TEMPLATE_PKG/scripts/lib/agent_cli.py" "$PROJECT_ROOT/scripts/lib/agent_cli.py"
# External evidence 子包（reflect Phase 1.85 / external_tool.py）
if [[ -d "$TEMPLATE_PKG/scripts/lib/external" ]]; then
  mkdir -p "$PROJECT_ROOT/scripts/lib/external"
  for f in "$TEMPLATE_PKG/scripts/lib/external/"*; do
    [[ -f "$f" ]] && cp "$f" "$PROJECT_ROOT/scripts/lib/external/$(basename "$f")"
  done
fi
if [[ -f "$TEMPLATE_PKG/scripts/lib/literature_search.py" ]]; then
  cp "$TEMPLATE_PKG/scripts/lib/literature_search.py" "$PROJECT_ROOT/scripts/lib/literature_search.py"
fi
if [[ -f "$TEMPLATE_PKG/scripts/external_tool.py" ]]; then
  cp "$TEMPLATE_PKG/scripts/external_tool.py" "$PROJECT_ROOT/scripts/external_tool.py"
  chmod +x "$PROJECT_ROOT/scripts/external_tool.py" 2>/dev/null || true
fi
# auto-nn-update 治本：manifest + reflect/ledger 运行时检查
for _gsync_chk in \
  scripts/lib/governance_sync_manifest.yaml \
  scripts/lib/governance_sync_manifest.py \
  scripts/lib/reflect_runtime_check.py \
  scripts/lib/round_ledger_closure.py \
  scripts/check_reflect_runtime.py \
  scripts/check_round_ledger_closure.py \
  scripts/check_governance_sync_coverage.py \
  scripts/check_scripts_skills_consistency.py; do
  if [[ -f "$TEMPLATE_PKG/$_gsync_chk" ]]; then
    mkdir -p "$PROJECT_ROOT/$(dirname "$_gsync_chk")"
    cp "$TEMPLATE_PKG/$_gsync_chk" "$PROJECT_ROOT/$_gsync_chk"
  fi
done
chmod +x "$PROJECT_ROOT/scripts/check_reflect_runtime.py" 2>/dev/null || true
chmod +x "$PROJECT_ROOT/scripts/check_round_ledger_closure.py" 2>/dev/null || true
chmod +x "$PROJECT_ROOT/scripts/check_governance_sync_coverage.py" 2>/dev/null || true
chmod +x "$PROJECT_ROOT/scripts/check_scripts_skills_consistency.py" 2>/dev/null || true
if [[ -f "$TEMPLATE_PKG/scripts/literature_search.py" ]]; then
  cp "$TEMPLATE_PKG/scripts/literature_search.py" "$PROJECT_ROOT/scripts/literature_search.py"
  chmod +x "$PROJECT_ROOT/scripts/literature_search.py" 2>/dev/null || true
fi
# B 组:scripts/ 顶层运行时入口(/auto-nn-analyse / -clear / nn-doctor --deep)
cp "$TEMPLATE_PKG/scripts/runtime-activity.py" "$PROJECT_ROOT/scripts/runtime-activity.py"
cp "$TEMPLATE_PKG/scripts/clear_reflect.py" "$PROJECT_ROOT/scripts/clear_reflect.py"
cp "$TEMPLATE_PKG/scripts/scenario_completeness_gate.py" "$PROJECT_ROOT/scripts/scenario_completeness_gate.py"
# C 组:.sh 转发器(named by auto-run exec)
cp "$TEMPLATE_PKG/scripts/mark-reflect-consumed.sh" "$PROJECT_ROOT/scripts/mark-reflect-consumed.sh"
cp "$TEMPLATE_PKG/scripts/mark_reflect_consumed.py" "$PROJECT_ROOT/scripts/mark_reflect_consumed.py"
chmod +x "$PROJECT_ROOT/scripts/mark-reflect-consumed.sh" 2>/dev/null || true

# ABCDE + Watchlist 组: manual 脚本 + workflow 真源（O3 picker 写 abcde-manual + 老业务仓兜底）
# 4 个核心脚本：init_o3_abcde / abcde_migrate / init_workflow / init_watchlist
# （v1.22+ 起 init_workflow 取代 init_scenarios；业务仓不再下发 init_scenarios.py）
# 注：$TEMPLATE_PKG = template/package；脚本路径须显式拼 scripts/ 前缀
# （check_ABCDE_boundaries 已整体退役；题面保护由 contract/ IMMUTABLE 锁承载）
for _abcde_script in \
  init_o3_abcde.py \
  abcde_migrate.py \
  init_workflow.py \
  init_watchlist.py \
  init_align.py \
  write_baseline_start_intent.py; do
  if [[ -f "$TEMPLATE_PKG/scripts/$_abcde_script" ]]; then
    mkdir -p "$PROJECT_ROOT/scripts"
    cp "$TEMPLATE_PKG/scripts/$_abcde_script" "$PROJECT_ROOT/scripts/$_abcde_script"
  fi
done
# align_probe 库
if [[ -f "$TEMPLATE_PKG/scripts/lib/align_probe.py" ]]; then
  mkdir -p "$PROJECT_ROOT/scripts/lib"
  cp "$TEMPLATE_PKG/scripts/lib/align_probe.py" "$PROJECT_ROOT/scripts/lib/align_probe.py"
fi
chmod +x "$PROJECT_ROOT/scripts/init_watchlist.py" 2>/dev/null || true
chmod +x "$PROJECT_ROOT/scripts/init_align.py" 2>/dev/null || true
chmod +x "$PROJECT_ROOT/scripts/write_baseline_start_intent.py" 2>/dev/null || true
# 场景模板已退役 cp（v1.28+）：
# 源在维护仓 skills/maintainer/auto-nn-init/templates/{build,migrate,update}.md + overlay/；
# 业务仓不再下发 skills/maintainer/...（governance-sync 不再 cp）。
# 调用方（abcde_migrate.py / init_o3_abcde.py）从 .auto-nn/template-root 或
# 环境变量 NN_ABCDE_TEMPLATES_DIR 解析到维护仓路径。
#
# 旧版 $(cd "$TEMPLATE_PKG/../../.." && pwd) 上溯多层在过渡 layout (template/ vs
# template/package/) 下错位 — 改用 TEMPLATE_ROOT = 维护仓根（line 49/53 已解析）。
# 老业务仓残留 skills/ 不自动 rm（doctor + verify-migration-complete FAIL 提示删）。

# Step 3 (ABCDE/v4, 2026-07-06): 老业务仓若缺 guidance 文件则补写
# references/manual/abcde-manual.md（idempotent；已存在则 skip）
# 必须放在 ABCDE cp 块之后：模板已落盘，abcde_migrate.py 才能 read_text 写 manual
# WARN + continue：失败不阻塞（治理同步本身仍可继续；O3 picker 阶段也会写）
if [[ -f "$PROJECT_ROOT/scripts/abcde_migrate.py" ]]; then
  python3 "$PROJECT_ROOT/scripts/abcde_migrate.py" \
    --repo-root "$PROJECT_ROOT" 2>&1 | head -20 || {
    echo "[governance-sync] WARN: abcde_migrate 失败（继续）" >&2
  }
fi

# D 组: NL 技能路由（业务仓 Agent 入口；随 auto-nn-update 下发）
if [[ -d "$TEMPLATE_PKG/.cursor/rules" ]]; then
  mkdir -p "$PROJECT_ROOT/.cursor/rules"
  for f in "$TEMPLATE_PKG/.cursor/rules"/*.mdc; do
    [[ -f "$f" ]] || continue
    cp "$f" "$PROJECT_ROOT/.cursor/rules/$(basename "$f")"
  done
  echo "[governance-sync] D组: .cursor/rules/"
fi
if [[ -d "$TEMPLATE_PKG/docs/nn-routing" ]]; then
  mkdir -p "$PROJECT_ROOT/docs/nn-routing"
  cp -a "$TEMPLATE_PKG/docs/nn-routing/." "$PROJECT_ROOT/docs/nn-routing/"
  echo "[governance-sync] D组: docs/nn-routing/"
fi

# Init 组: init 交互 policy（业务仓 init/migration 只读）
if [[ -d "$TEMPLATE_PKG/docs/init" ]]; then
  mkdir -p "$PROJECT_ROOT/docs/init"
  cp -a "$TEMPLATE_PKG/docs/init/." "$PROJECT_ROOT/docs/init/"
  echo "[governance-sync] Init组: docs/init/"
fi
if [[ -f "$TEMPLATE_PKG/scripts/lib/init_interaction_policy.py" ]]; then
  mkdir -p "$PROJECT_ROOT/scripts/lib"
  cp "$TEMPLATE_PKG/scripts/lib/init_interaction_policy.py" \
     "$PROJECT_ROOT/scripts/lib/init_interaction_policy.py"
fi

# 已有成绩表：对齐 overlay 列顺序（exploration_space / untrained 等）。
# 2.12→2.13 增 untrained 列后，旧表头列顺序与 contract 不一致 → verify/doctor tsv_header FAIL。
# 无 TSV 的绿场跳过。脚本目录在 sys.path[0]，可 import sync_ledger。
if [[ -f "$PROJECT_ROOT/_runs/results.tsv" && -f "$PROJECT_ROOT/scripts/regen_results_tsv.py" ]]; then
  echo "[governance-sync] regen TSV 表头（已有成绩表）"
  python3 "$PROJECT_ROOT/scripts/regen_results_tsv.py" --repo-root "$PROJECT_ROOT" --sync-jsonl \
    || { echo "[governance-sync] FAIL: regen_results_tsv 失败" >&2; exit 1; }
fi
