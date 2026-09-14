#!/usr/bin/env bash
# verify-migration-complete.sh — 迁移/立项收尾硬性验收（未通过则 exit 1）
# 用法：在目标项目根执行  bash scripts/verify-migration-complete.sh
# 判据见 CHECKLIST.md §0（业务仓无 docs/，勿依赖模板仓 docs/）
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
# shellcheck source=scripts/lib/governance-rev.sh
source "$ROOT/scripts/lib/governance-rev.sh"
# shellcheck source=scripts/lib/nn-state.sh
source "$ROOT/scripts/lib/nn-state.sh"

IS_TEMPLATE_ROOT=0
if [[ -f .template-maintainer ]]; then
  IS_TEMPLATE_ROOT=1
fi

FAIL=0
warn() { echo "[verify] WARN: $*" >&2; }
die() { echo "[verify] FAIL: $*" >&2; FAIL=1; }
ok() { echo "[verify] OK: $*"; }

# ── 0a. 迁后须为 git 仓库；禁止与 source_root 同路径（入口 A 原地迁移）────
if [[ "$IS_TEMPLATE_ROOT" -eq 0 ]]; then
  if ! git rev-parse --is-inside-work-tree &>/dev/null; then
    die "迁后项目须为 git 仓库（推荐: <template_root>/scripts/new-project.sh <target> … 会 git init；禁止在无 .git 的旧目录原地改）"
  else
    ok "git 仓库（work tree）"
  fi
  if [[ ! -s .auto-nn/migration-summary.md ]]; then
    die "缺少或非空 .auto-nn/migration-summary.md — HARD-GATE 用户 F1-contract=① 后须写入（见 SKILL 阶段 F）"
  else
    ok ".auto-nn/migration-summary.md 已落盘"
  fi
  if [[ ! -f scripts/validate-init-qa-log.py ]]; then
    warn "缺少 scripts/validate-init-qa-log.py — init 问答 log 无法校验（先 governance-sync 或 new-project）"
  else
    set +e
    _iql_out="$(python3 scripts/validate-init-qa-log.py --repo-root . --require-closed 2>&1)"
    _iql_rc=$?
    set -e
    if [[ $_iql_rc -eq 0 ]]; then
      ok "init-qa-log 已闭合（问答忠实 log）"
      if [[ -f saved/baseline_start_intent.json ]]; then
        ok "saved/baseline_start_intent.json 已落盘（O3 尺子意图）"
      elif [[ -f .auto-nn/baseline-intent-skipped ]]; then
        ok "O3 尺子意图已显式跳过（.auto-nn/baseline-intent-skipped）"
      else
        die "init-qa-log 已闭合但缺 saved/baseline_start_intent.json — O3 非 skip 须落盘；若弱化跳过请写 .auto-nn/baseline-intent-skipped"
      fi
    else
      warn "init-qa-log: ${_iql_out//$'\n'/; }"
    fi
  fi
  if [[ -f .auto-nn/init-align.json ]]; then
    ok ".auto-nn/init-align.json 存在"
  else
    warn "缺 .auto-nn/init-align.json（近版 new-project 应写入；老仓可忽略）"
  fi
  if [[ ! -f scripts/verify_project_layout.py ]]; then
    die "缺少 scripts/verify_project_layout.py — 运行: bash <template_root>/scripts/governance-sync.sh --template-root <T> --project-root ."
  elif ! python3 scripts/verify_project_layout.py .; then
    FAIL=1
  fi
  if [[ ! -f references/manual/abcde-manual.md ]]; then
    die "缺少 references/manual/abcde-manual.md（立项应生成；可跑 init_o3_abcde.py / abcde_migrate.py）"
  else
    ok "references/manual/abcde-manual.md 存在"
  fi
fi

# ── 0. 治理三件套与模板根一致（仅业务仓）────────────────────────────
if [[ "$IS_TEMPLATE_ROOT" -eq 0 ]]; then
  TROOT="$(nn_resolve_template_root)" || TROOT=""
  GOV_REV="$(nn_state_read governance-rev)"
  if [[ -z "$TROOT" ]] || [[ -z "$GOV_REV" ]]; then
    die "无法解析 template-root 或缺少 .auto-nn/governance-rev — 须 export NN_TEMPLATE_ROOT / 跑 install.sh，或 bash <template_root>/scripts/governance-sync.sh --template-root <T> --project-root ."
  else
    if [[ ! -d "$TROOT" ]]; then
      die ".auto-nn/template-root 无效: $TROOT"
    elif [[ -f "$TROOT/template/package/profiles.yaml" ]]; then
      TPKG="$TROOT/template/package"
    elif [[ -f "$TROOT/template/profiles.yaml" ]]; then
      TPKG="$TROOT/template"
    elif [[ -f "$TROOT/profiles.yaml" ]]; then
      TPKG="$TROOT"
    else
      die "模板维护仓缺少 template/package/profiles.yaml: $TROOT"
    fi
    if [[ ! -f "$TPKG/scripts/verify-migration-complete.sh" ]]; then
      die "模板包缺少 verify 脚本: $TPKG"
    else
      EXPECTED="$(governance_rev_compute "$TPKG")"
      ACTUAL="$GOV_REV"
      if [[ "$EXPECTED" != "$ACTUAL" ]]; then
        die "profiles.yaml 或 verify 落后于模板（rev $ACTUAL != $EXPECTED）— 运行 governance-sync.sh"
      elif ! diff -q "$TPKG/profiles.yaml" profiles.yaml >/dev/null 2>&1; then
        die "profiles.yaml 与模板不一致 — 运行 governance-sync.sh"
      elif ! diff -q "$TPKG/scripts/verify-migration-complete.sh" scripts/verify-migration-complete.sh >/dev/null 2>&1; then
        die "verify-migration-complete.sh 与模板不一致 — 运行 governance-sync.sh"
      elif ! diff -q "$TPKG/scripts/rl_workspace_gate.py" scripts/rl_workspace_gate.py >/dev/null 2>&1; then
        die "rl_workspace_gate.py 与模板不一致 — 运行 governance-sync.sh"
      elif ! diff -q "$TPKG/scripts/d2_data_split_gate.py" scripts/d2_data_split_gate.py >/dev/null 2>&1; then
        die "d2_data_split_gate.py 与模板不一致 — 运行 governance-sync.sh"
      elif ! diff -q "$TPKG/scripts/scenario_policy_gate.py" scripts/scenario_policy_gate.py >/dev/null 2>&1; then
        die "scenario_policy_gate.py 与模板不一致 — 运行 governance-sync.sh"
      elif ! diff -q "$TPKG/scripts/smoke-check.sh" scripts/smoke-check.sh >/dev/null 2>&1; then
        die "smoke-check.sh 与模板不一致 — 运行 governance-sync.sh"
      elif ! diff -q "$TPKG/scripts/wait-train.sh" scripts/wait-train.sh >/dev/null 2>&1; then
        die "wait-train.sh 与模板不一致 — 运行 governance-sync.sh"
      elif ! diff -q "$TPKG/scripts/claude_stream_summarize.py" scripts/claude_stream_summarize.py >/dev/null 2>&1; then
        die "claude_stream_summarize.py 与模板不一致 — 运行 governance-sync.sh"
      elif ! diff -q "$TPKG/scripts/claude_stream_result_watchdog.py" scripts/claude_stream_result_watchdog.py >/dev/null 2>&1; then
        die "claude_stream_result_watchdog.py 与模板不一致 — 运行 governance-sync.sh"
      elif ! diff -q "$TPKG/scripts/verify_project_layout.py" scripts/verify_project_layout.py >/dev/null 2>&1; then
        die "verify_project_layout.py 与模板不一致 — 运行 governance-sync.sh"
      elif ! diff -q "$TPKG/reflect.py" reflect.py >/dev/null 2>&1; then
        die "reflect.py 与模板不一致 — 运行 governance-sync.sh"
      else
        ok "治理文件已与模板同步 (rev=$ACTUAL)"
      fi
    fi
  fi
fi

# ── 1. 立项延后表头标记 ─────────────────────────────────────────────
if [[ -f _runs/.tsv-header-pending ]]; then
  die "_runs/.tsv-header-pending 仍存在 — contract 迁移后须: python3 scripts/regen_results_tsv.py --repo-root . && rm -f _runs/.tsv-header-pending"
  cat _runs/.tsv-header-pending >&2 || true
else
  ok "无 .tsv-header-pending"
fi

# ── 2. nn-config profile ────────────────────────────────────────────
if [[ ! -f nn-config.yaml ]]; then
  die "缺少 nn-config.yaml"
else
  PROFILE="$(python3 -c "import yaml; print(yaml.safe_load(open('nn-config.yaml'))['profile'])" 2>/dev/null || echo "")"
  if [[ -z "$PROFILE" ]]; then
    die "nn-config.yaml 无法解析 profile"
  else
    ok "profile=$PROFILE"
  fi
fi

# ── 3. contract 四文件布局 + 门面 import ─────────────────────────────
if PYTHONPATH=. python3 -c "
from experiment import check_contract_layout
v = check_contract_layout('.')
assert not v, v
" 2>/dev/null; then
  ok "contract 四文件布局与门面 import"
else
  die "contract 布局未通过 — 运行: PYTHONPATH=. python3 -c \"from experiment import check_contract_layout; print(check_contract_layout('.'))\""
fi

# ── 3b. train.py 实验目录（G-路径）──────────────────────────────────
if PYTHONPATH=. python3 -c "
from experiment import check_train_exp_dir_layout
v = check_train_exp_dir_layout('.')
assert not v, [(x.rule, x.detail) for x in v]
" 2>/dev/null; then
  ok "train.py 使用 _runs/exp（allocate_exp_dir 或等价路径）"
else
  die "train.py 实验目录须在 _runs/exp/ — PYTHONPATH=. python3 -c \"from experiment import check_train_exp_dir_layout; print(check_train_exp_dir_layout('.'))\""
fi

# ── 3c. 门面契约（workspace_forbidden 等）──────────────────────────
if PYTHONPATH=. python3 -c "
from experiment import check_profile_facade
v = check_profile_facade('.')
assert not v, [(x.rule, x.detail) for x in v]
" 2>/dev/null; then
  ok "profiles.yaml 门面契约（含 workspace 禁止 prepare_data）"
else
  die "门面契约未通过 — PYTHONPATH=. python3 -c \"from experiment import check_profile_facade; print(check_profile_facade('.'))\""
fi

# ── 3d. RL workspace D2/E3（profile=rl 时硬失败）──────────────────────
if [[ "$PROFILE" == "rl" ]]; then
  if [[ ! -f scripts/rl_workspace_gate.py ]]; then
    die "profile=rl 但缺少 scripts/rl_workspace_gate.py — 先 governance-sync.sh"
  elif python3 scripts/rl_workspace_gate.py . 2>/dev/null; then
    ok "RL workspace D2/E3（prepare_data + evaluate→contract.test）"
  else
    die "RL workspace 未满足 D2/E3 — 运行: python3 scripts/rl_workspace_gate.py ."
  fi
fi

# ── 4. contract 与 profile 一致（非演示）────────────────────────────
if python3 -c "
from pathlib import Path
import ast, sys, yaml
root = Path('.')
profile = yaml.safe_load((root/'nn-config.yaml').read_text())['profile']
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
    print('contract 仍为 supervised 演示 metric_keys（含 val_accuracy）', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null; then
  ok "contract 与 profile 无演示指标冲突"
else
  die "nn-config profile=$PROFILE 但 contract 仍为 FashionMNIST 演示（含 val_accuracy）"
fi

# ── 5. TSV 表头与 contract ──────────────────────────────────────────
if [[ $IS_TEMPLATE_ROOT -eq 1 ]]; then
  ok "模板根：跳过 TSV 表头检查"
elif [[ ! -f scripts/regen_results_tsv.py ]]; then
  warn "无 scripts/regen_results_tsv.py，跳过 TSV 表头校验"
elif [[ ! -f _runs/results.tsv ]]; then
  die "缺少 _runs/results.tsv（或仍为 .tsv-header-pending 未 regen）"
else
  EXPECTED="$(python3 scripts/regen_results_tsv.py --repo-root . --header-only 2>/dev/null || true)"
  ACTUAL="$(head -1 _runs/results.tsv)"
  if [[ -z "$EXPECTED" ]]; then
    die "无法从 contract 生成期望表头"
  elif [[ "$EXPECTED" != "$ACTUAL" ]]; then
    die "TSV 表头与 contract 不一致"
    echo "  期望: $EXPECTED" >&2
    echo "  实际: $ACTUAL" >&2
  else
    ok "TSV 表头与 contract 一致"
  fi
fi

# ── 6. README 已项目化（模板根跳过）──────────────────────────────────
if [[ $IS_TEMPLATE_ROOT -eq 1 ]]; then
  ok "模板根：跳过 README 项目化检查"
elif [[ -f README.md ]]; then
  if head -1 README.md | grep -q '^# auto-nn-experiment$'; then
    die "README.md 首行仍为模板标题 — 须重写为目标项目说明（含 test/evaluate/metrics）"
  else
    ok "README 非模板默认标题"
  fi
else
  die "缺少 README.md"
fi

# ── 6c. D2 数据划分块（README D2_DATA_SPLIT）────────────────────────
if [[ $IS_TEMPLATE_ROOT -eq 1 ]]; then
  ok "模板根：跳过 D2_DATA_SPLIT 检查"
elif [[ ! -f scripts/d2_data_split_gate.py ]]; then
  die "缺少 scripts/d2_data_split_gate.py — 先 governance-sync.sh"
elif python3 scripts/d2_data_split_gate.py . 2>/dev/null; then
  ok "D2 数据划分块（README D2_DATA_SPLIT）"
else
  die "D2 数据划分未通过 — 运行: python3 scripts/d2_data_split_gate.py ."
fi

# ── 6d. 场景策略块（README SCENARIO_POLICY，条件触发）────────────────
if [[ $IS_TEMPLATE_ROOT -eq 1 ]]; then
  ok "模板根：跳过 SCENARIO_POLICY 检查"
elif [[ ! -f scripts/scenario_policy_gate.py ]]; then
  die "缺少 scripts/scenario_policy_gate.py — 先 governance-sync.sh"
elif python3 scripts/scenario_policy_gate.py . 2>/dev/null; then
  ok "场景策略块（SCENARIO_POLICY / AGENT_BOUNDARY）"
else
  die "场景策略未通过 — 运行: python3 scripts/scenario_policy_gate.py ."
fi

# ── 6e. train_dynamics 门禁（train.py hook + 末轮 dynamics）──────────
if [[ $IS_TEMPLATE_ROOT -eq 1 ]]; then
  ok "模板根：跳过 train_dynamics_gate"
elif [[ ! -f scripts/train_dynamics_gate.py ]]; then
  warn "缺少 scripts/train_dynamics_gate.py — 先 governance-sync.sh"
elif python3 scripts/train_dynamics_gate.py . 2>/dev/null; then
  ok "train_dynamics 门禁（hook + dynamics 产物）"
else
  warn "train_dynamics_gate 未完全通过 — 运行: python3 scripts/train_dynamics_gate.py ."
fi

# ── 6f. 信息权限（README INFO_PERM ↔ contract/runtime.py INFO_PERM；静态扫描 IP0–IP5）──
if [[ $IS_TEMPLATE_ROOT -eq 1 ]]; then
  ok "模板根：跳过 INFO_PERM 检查"
elif [[ ! -f scripts/info_perm_gate.py ]] || [[ ! -f scripts/lib/info_perm.py ]]; then
  warn "缺少 scripts/info_perm_gate.py / scripts/lib/info_perm.py — 先 governance-sync.sh"
else
  set +e; python3 scripts/info_perm_gate.py . >/dev/null 2>&1; _ip_rc=$?; set -e
  case $_ip_rc in
    0) ok "信息权限块（README INFO_PERM ↔ INFO_PERM）";;
    2) warn "README 缺 INFO_PERM 块或未填（立项三问未落盘）";;
    *) die "信息权限块与 contract/runtime.py INFO_PERM 不一致 — 运行: python3 scripts/info_perm_gate.py .";;
  esac
  if python3 scripts/lib/info_perm.py . >/dev/null 2>&1; then
    ok "G-信息权限静态扫描（IP0–IP5）"
  else
    die "G-信息权限静态扫描未通过 — 运行: python3 scripts/lib/info_perm.py ."
  fi
fi

# ── 6b. auto-nn-run 配套（manifest 必备；与 auto-nn-run.sh 启动检查一致）──
if [[ $IS_TEMPLATE_ROOT -eq 0 ]]; then
  if [[ ! -f auto-nn-run.sh ]]; then
    die "缺少 auto-nn-run.sh — new-project.sh 或 governance-sync 后从模板复制"
  fi
  # 2026-06-20 rename: 旧 nn-auto-run.sh 已废弃;governance-sync 应已 rm,残留即未走 sync
  if [[ -f nn-auto-run.sh ]]; then
    die "存在废弃副本 nn-auto-run.sh — 运行 bash <template_root>/scripts/governance-sync.sh 自动清理"
  fi
fi
if [[ $IS_TEMPLATE_ROOT -eq 0 ]] && [[ -f auto-nn-run.sh ]]; then
  _CLAUDE_SUMMARIZE=scripts/claude_stream_summarize.py
  _CLAUDE_WATCHDOG=scripts/claude_stream_result_watchdog.py
  _agent_need=(reflect.py scripts/wait-train.sh scripts/auto-run-batch-tail.sh "$_CLAUDE_SUMMARIZE" "$_CLAUDE_WATCHDOG")
  for need in "${_agent_need[@]}"; do
    if [[ ! -f "$need" ]]; then
      die "存在 auto-nn-run.sh 但缺少 $need — 从模板复制或 bash <template_root>/scripts/governance-sync.sh"
    fi
  done
  chmod +x scripts/wait-train.sh scripts/auto-run-batch-tail.sh "$_CLAUDE_SUMMARIZE" "$_CLAUDE_WATCHDOG" 2>/dev/null || true
  if [[ -x scripts/wait-train.sh ]] && [[ -x scripts/auto-run-batch-tail.sh ]] && [[ -x "$_CLAUDE_SUMMARIZE" ]] && [[ -x "$_CLAUDE_WATCHDOG" ]]; then
    ok "auto-nn-run 配套（reflect、wait-train、claude_stream_summarize、claude_stream_result_watchdog）"
  else
    die "scripts/wait-train.sh 或 $_CLAUDE_SUMMARIZE 或 $_CLAUDE_WATCHDOG 不可执行（已尝试 chmod +x）"
  fi
  if ! err=$(bash -n auto-nn-run.sh 2>&1); then
    die "auto-nn-run.sh 语法错误（常见：末尾 Completed … run(s) 未加双引号）: ${err}"
  fi
  ok "auto-nn-run.sh 语法检查通过"
fi

# ── 7. 模板残留（迁移完成后不应并存；模板根跳过）────────────────────
# v1.28+：业务仓不再下发 skills/maintainer/auto-nn-init/templates/。
# governance-sync §ABCDE 段已移除 cp 循环（场景模板从维护仓读）；
# 业务仓残留 skills/ 视为过时，die 并建议删除。
if [[ $IS_TEMPLATE_ROOT -eq 1 ]]; then
  ok "模板根：跳过 skills/new-project.sh/docs 残留检查"
elif [[ -d .claude/skills ]]; then
  die "业务仓不得含 .claude/skills/ — 使用全局 auto-nn-* 技能；见 CHECKLIST §2"
elif [[ -d skills ]]; then
  die "业务仓不得含 skills/（v1.28+ governance-sync 不再下发；模板真源在维护仓根 skills/maintainer/auto-nn-init/templates/）— 请 rm -rf skills/"
elif [[ -f scripts/new-project.sh ]]; then
  die "业务仓不得含 scripts/new-project.sh — 见 CHECKLIST §2 清理模板文件"
else
  ok "无 skills/、无 new-project.sh 残留（项目 docs/ 允许）"
fi

# ── 7b. .gitignore（模板 package 真源）──────────────────────────────
if [[ ! -f .gitignore ]]; then
  die "缺少根目录 .gitignore — 从 template/package 复制或运行 governance-sync"
fi
if ! grep -qE '^__pycache__/' .gitignore || ! grep -qE '^exp/' .gitignore; then
  die ".gitignore 不完整（须含 __pycache__/ 与 exp/；勿用 _runs/ 整目录忽略，以免误挡 results.tsv）"
fi
ok ".gitignore 存在且含核心规则（__pycache__/、exp/）"

# ── 8. 大日志不得被 git 跟踪 ───────────────────────────────────────
if git rev-parse --is-inside-work-tree &>/dev/null; then
  BAD_LOGS="$(git ls-files 2>/dev/null | grep -E 'pipeline\.log$|multi_structure_logs/.*\.log$' || true)"
  if [[ -n "$BAD_LOGS" ]]; then
    die "下列运行日志仍被 git 跟踪（应 git rm --cached 并写入 .gitignore）:"
    echo "$BAD_LOGS" >&2
  else
    ok "git 未跟踪 offline_knn 大日志"
  fi
fi

# ── 9. G-评估 ───────────────────────────────────────────────────────
if PYTHONPATH=. python3 -c "
from experiment import check_test_authority
v = check_test_authority('.')
assert not v, v
" 2>/dev/null; then
  ok "G-评估 check_test_authority"
else
  die "G-评估未通过 — 运行: python3 -c \"from experiment import check_test_authority; print(check_test_authority('.'))\""
fi

# ── 10. RL：make_eval_env 须使用 mode 参数（防 v6 回归）────────────
if [[ "${PROFILE:-}" == "rl" ]] && [[ -f workspace/infer.py ]]; then
  if PYTHONPATH=. python3 -c "
from pathlib import Path
import ast
p = Path('workspace/infer.py')
tree = ast.parse(p.read_text(encoding='utf-8'))
for node in tree.body:
    if isinstance(node, ast.FunctionDef) and node.name == 'make_eval_env':
        src = ast.get_source_segment(p.read_text(encoding='utf-8'), node) or ''
        if 'create_multi_structure_env' in src and 'mode=PERF_MODEL_MODE' in src.replace(' ', ''):
            if 'eval_mode' not in src and 'mode if mode' not in src:
                raise SystemExit('make_eval_env 未将 mode 传入 create_multi_structure_env')
" 2>/dev/null; then
    ok "RL infer make_eval_env mode 传递"
  else
    die "workspace/infer.py make_eval_env 仍将 mode 写死为 PERF_MODEL_MODE — 对齐 v5: eval_mode = (mode or PERF_MODEL_MODE)"
  fi
fi

echo ""
if [[ $FAIL -ne 0 ]]; then
  echo "[verify] 迁移收尾验收未通过（对照 CHECKLIST.md §0–§4 与上方 FAIL 项）" >&2
  echo "[verify] 提示: 改代码前可先 bash <template_root>/scripts/migration-compare.sh 做阶段 0 分析" >&2
  exit 1
fi
echo "[verify] 全部通过 — 可声明迁移完成（仍建议 CHECKLIST §5 smoke）"

# verify 通过 → best-effort 归档 CHECKLIST.md 到 .auto-nn/（path-independent）
# 覆盖 new-project.sh 未触发的路径：cp 仓 / 入口 A 迁入既有仓 / 沙箱副本（如 r26）。
# 模板根跳过：template/package/CHECKLIST.md 是种子真源，不能移。
if [[ $IS_TEMPLATE_ROOT -eq 0 && -f "$ROOT/CHECKLIST.md" && -d "$ROOT/.auto-nn" ]]; then
  _ckpt_ts="$(date -u +%Y%m%d_%H%M%SZ)"
  if mv "$ROOT/CHECKLIST.md" "$ROOT/.auto-nn/migration-completed-checklist-${_ckpt_ts}.md" 2>/dev/null; then
    echo "[verify] ✅ CHECKLIST.md → .auto-nn/migration-completed-checklist-${_ckpt_ts}.md（业务仓根不再保留）"
  else
    echo "[verify] ⚠ 自动归档失败（手动 mv CHECKLIST.md .auto-nn/）" >&2
  fi
fi
exit 0
