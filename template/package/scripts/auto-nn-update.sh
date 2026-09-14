#!/usr/bin/env bash
# auto-nn-update.sh — 业务仓一键拉模板治理更新
#
# 前提：模板维护仓已 git pull（或本机 template-root 指向的目录已是最新）
# 用法（在业务仓根目录）：
#   bash scripts/auto-nn-update.sh
#   bash scripts/auto-nn-update.sh --pull-template   # 同步前先 pull 模板仓（同机便利项）
set -euo pipefail

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_PROJECT_ROOT="$(pwd)"

usage() {
  cat <<'EOF'
用法: auto-nn-update.sh [选项]

  在业务仓根目录执行（cwd = 项目根，含 scripts/governance-sync.sh 或 _runs/）。

  --pull-template   同步前在解析到的模板维护仓 git pull --ff-only
  --skip-verify     跳过 verify / nn-doctor（仅 governance-sync + 硬门禁；调试用）
  --accept-major-bump  接受模板 major bump（无 flag 则 major 阻断；治理仍 sync 后更新 .auto-nn/version）
  --strict-version  拒绝降级（默认仅 WARN）
  -h, --help        本帮助

前提：模板维护仓已更新（维护者 git pull 或远端已 push 且本机已 pull）。
EOF
  exit "${1:-0}"
}

PULL_TEMPLATE=0
SKIP_VERIFY=0
ACCEPT_MAJOR=0
STRICT_VERSION=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pull-template) PULL_TEMPLATE=1; shift ;;
    --skip-verify) SKIP_VERIFY=1; shift ;;
    --accept-major-bump) ACCEPT_MAJOR=1; shift ;;
    --strict-version) STRICT_VERSION=1; shift ;;
    -h|--help) usage 0 ;;
    *) echo "[auto-nn-update] FAIL: 未知参数: $1" >&2; usage 1 ;;
  esac
done

_assert_business_repo() {
  local root="$1"
  if [[ -f "$root/.template-maintainer" ]]; then
    echo "[auto-nn-update] FAIL: 请在业务仓根目录执行，不要从模板维护仓发起。" >&2
    echo "  cd <业务仓> && bash scripts/auto-nn-update.sh" >&2
    echo "  前提：模板维护仓已 git pull。" >&2
    return 1
  fi
  if [[ ! -f "$root/scripts/auto-nn-update.sh" ]]; then
    echo "[auto-nn-update] FAIL: 请在业务仓根目录执行（cwd 须含 scripts/auto-nn-update.sh）" >&2
    return 1
  fi
  return 0
}

_resolve_template_root() {
  local root="$1"
  if [[ ! -f "$root/scripts/lib/nn-state.sh" ]]; then
    echo "[auto-nn-update] FAIL: 缺少 scripts/lib/nn-state.sh" >&2
    return 1
  fi
  # shellcheck source=/dev/null
  source "$root/scripts/lib/nn-state.sh"
  nn_resolve_template_root "$root"
}

_hard_gates() {
  local proj="$1"
  local troot="$2"
  local fail=0
  echo "[auto-nn-update] 硬门禁: py_compile reflect.py"
  if ! (cd "$proj" && python3 -m py_compile reflect.py); then
    echo "[auto-nn-update] FAIL: reflect.py 语法错误" >&2
    fail=1
  fi
  if [[ ! -f "$proj/scripts/gpu_snapshot.py" ]]; then
    echo "[auto-nn-update] FAIL: 缺少 scripts/gpu_snapshot.py" >&2
    fail=1
  fi
  if [[ ! -f "$proj/scripts/lib/gpu_snapshot.py" ]]; then
    echo "[auto-nn-update] FAIL: 缺少 scripts/lib/gpu_snapshot.py" >&2
    fail=1
  fi
  if [[ ! -f "$proj/scripts/lib/home_gpus.py" ]]; then
    echo "[auto-nn-update] FAIL: 缺少 scripts/lib/home_gpus.py" >&2
    fail=1
  fi
  local expected actual
  # shellcheck source=/dev/null
  source "$troot/template/package/scripts/lib/governance-rev.sh"
  expected="$(governance_rev_compute "$troot/template/package")"
  actual="$(tr -d '\r\n' < "$proj/.auto-nn/governance-rev" 2>/dev/null || true)"
  if [[ "$actual" != "$expected" ]]; then
    echo "[auto-nn-update] FAIL: 治理版本未对齐 want=$expected got=${actual:-<missing>}" >&2
    echo "  提示: 模板维护仓是否已 git pull？可试 --pull-template" >&2
    fail=1
  else
    echo "[auto-nn-update] 治理版本 OK: $actual"
  fi
  if [[ -f "$proj/scripts/check_reflect_runtime.py" ]]; then
    echo "[auto-nn-update] 硬门禁: reflect_runtime"
    if ! (cd "$proj" && python3 scripts/check_reflect_runtime.py --repo-root "$proj"); then
      echo "[auto-nn-update] FAIL: reflect 运行时未就绪 — 请确认模板仓已 pull 并重跑 update" >&2
      echo "  若仍失败：维护仓 template_tests 或 governance-sync manifest 可能滞后" >&2
      fail=1
    fi
  else
    echo "[auto-nn-update] FAIL: 缺少 scripts/check_reflect_runtime.py（governance-sync 未完整）" >&2
    fail=1
  fi
  return "$fail"
}

_assert_business_repo "$_PROJECT_ROOT" || exit 1

TEMPLATE_ROOT=""
if ! TEMPLATE_ROOT="$(_resolve_template_root "$_PROJECT_ROOT")"; then
  echo "[auto-nn-update] FAIL: 无法解析 template-root（检查 symlink / .auto-nn/template-root）" >&2
  exit 1
fi
TEMPLATE_ROOT="$(cd "$TEMPLATE_ROOT" && pwd)"

if [[ "$PULL_TEMPLATE" -eq 1 ]]; then
  echo "[auto-nn-update] git pull --ff-only @ $TEMPLATE_ROOT"
  git -C "$TEMPLATE_ROOT" pull --ff-only
fi

echo "========== auto-nn-update: $_PROJECT_ROOT =========="
echo "[auto-nn-update] template_root=$TEMPLATE_ROOT"

# === Version gate（在 governance-sync 之前）===
echo "[auto-nn-update] version gate"
GATE_ARGS=(--template-root "$TEMPLATE_ROOT" --business-root "$_PROJECT_ROOT")
[[ "$ACCEPT_MAJOR" -eq 1 ]] && GATE_ARGS+=(--accept-major-bump)
[[ "$STRICT_VERSION" -eq 1 ]] && GATE_ARGS+=(--strict-version)
# 业务仓可能尚未 sync，gate 脚本尚不存在 → 现造
if [[ ! -f "$_PROJECT_ROOT/scripts/_check_template_version.sh" ]]; then
  cp "$TEMPLATE_ROOT/template/package/scripts/_check_template_version.sh" \
     "$_PROJECT_ROOT/scripts/_check_template_version.sh"
  chmod +x "$_PROJECT_ROOT/scripts/_check_template_version.sh" 2>/dev/null || true
fi
if [[ ! -f "$_PROJECT_ROOT/scripts/check_template_version.py" ]]; then
  cp "$TEMPLATE_ROOT/template/package/scripts/check_template_version.py" \
     "$_PROJECT_ROOT/scripts/check_template_version.py"
  chmod +x "$_PROJECT_ROOT/scripts/check_template_version.py" 2>/dev/null || true
fi
bash "$_PROJECT_ROOT/scripts/_check_template_version.sh" "${GATE_ARGS[@]}" \
  || { echo "[auto-nn-update] FAIL: version gate 阻断（major bump 需 --accept-major-bump；降级需 --strict-version）" >&2; exit 1; }

bash "$TEMPLATE_ROOT/template/package/scripts/governance-sync.sh" \
  --template-root "$TEMPLATE_ROOT" \
  --project-root "$_PROJECT_ROOT"

# v2 → v4 goal 升级提示（不自动应用）
if [[ -f "$_PROJECT_ROOT/nn-config.yaml" ]] && [[ -f "$_PROJECT_ROOT/scripts/lib/goal_spec.py" ]]; then
    if (cd "$_PROJECT_ROOT" && python3 -c "
import sys
sys.path.insert(0, '$_PROJECT_ROOT/scripts/lib')
from nn_config import load_nn_config
from pathlib import Path
cfg = load_nn_config(Path('.'))
goal = cfg.get('goal') or {}
if isinstance(goal.get('policy'), dict) and goal.get('policy'):
    sys.exit(1)  # 已是 v4
gt = goal.get('target')
ps = goal.get('per_scenario') or {}
sys.exit(0 if (gt is not None or ps) else 1)
" 2>/dev/null); then
        cat <<'EOF'

ℹ 检测到 v2 goal 配置。可升级到 v3 goal_spec 享受多 metric 复合门槛：
  python scripts/manage_goal.py upgrade         # dry-run
  python scripts/manage_goal.py upgrade --apply  # 写回

EOF
    fi
fi

_hard_gates "$_PROJECT_ROOT" "$TEMPLATE_ROOT" || exit 1

if [[ "$SKIP_VERIFY" -eq 0 ]]; then
  echo "[auto-nn-update] verify-migration-complete.sh"
  (cd "$_PROJECT_ROOT" && bash scripts/verify-migration-complete.sh)
  echo "[auto-nn-update] nn-doctor.sh（FAIL 则 update 非 0 退出）"
  # governance-sync 刚覆盖治理文件（CLAUDE/PROTOCOL/auto-nn-run.sh）= 显式治理升级，
  # 自带 NN_RELAUNCH=1 ack；与 experiment.py:1589「governance-sync 后首训」同义。
  # 不削弱护栏：偷改（非 update 路径）仍被 manual-run-scope-check A+B+C 拦。
  (cd "$_PROJECT_ROOT" && NN_RELAUNCH=1 bash scripts/nn-doctor.sh)
else
  echo "[auto-nn-update] --skip-verify：已跳过 verify 与 nn-doctor"
fi

echo ""
echo "[auto-nn-update] 完成（governance-sync + 硬门禁${SKIP_VERIFY:+；verify/doctor 已跳过}）。请审 diff 后自行 commit 业务仓。"
