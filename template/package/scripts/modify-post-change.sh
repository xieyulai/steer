#!/usr/bin/env bash
# modify-post-change.sh — 按轨跑 Modify 改后验收链（权威步骤见 docs/nn-modify/post-change.md）
#
# 用法:
#   bash scripts/modify-post-change.sh --track L|T|Scenario-complete|Scenario-expand|ledger-sync
#        [--repo-root DIR] [--skip-smoke] [--apply-backfill] [--with-doctor]
#
# 不发明新门禁；只编排已有脚本。Scenario-complete 默认只 dry-run backfill。

set -euo pipefail

TRACK=""
REPO_ROOT="."
SKIP_SMOKE=0
APPLY_BACKFILL=0
WITH_DOCTOR=0

usage() {
  sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --track) TRACK="${2:-}"; shift 2 ;;
    --repo-root) REPO_ROOT="${2:-}"; shift 2 ;;
    --skip-smoke) SKIP_SMOKE=1; shift ;;
    --apply-backfill) APPLY_BACKFILL=1; shift ;;
    --with-doctor) WITH_DOCTOR=1; shift ;;
    -h|--help) usage ;;
    *) echo "[modify-post-change] 未知参数: $1" >&2; usage ;;
  esac
done

[[ -n "$TRACK" ]] || { echo "[modify-post-change] 须 --track" >&2; usage; }

cd "$REPO_ROOT"
ROOT="$(pwd)"
SCRIPTS="$ROOT/scripts"

need() {
  local f="$1"
  if [[ ! -f "$f" ]]; then
    echo "[modify-post-change] 缺少 $f — 请 /auto-nn-update 或 governance-sync" >&2
    exit 1
  fi
}

run_step() {
  echo "[modify-post-change] >>> $*"
  "$@"
}

smoke_or_skip() {
  if [[ "$SKIP_SMOKE" -eq 1 ]]; then
    echo "[modify-post-change] SKIP smoke (--skip-smoke)"
    return 0
  fi
  need "$SCRIPTS/smoke-check.sh"
  run_step bash "$SCRIPTS/smoke-check.sh"
}

doctor_step() {
  need "$SCRIPTS/nn-doctor.sh"
  run_step bash "$SCRIPTS/nn-doctor.sh"
}

case "$TRACK" in
  ledger-sync)
    need "$SCRIPTS/regen_results_tsv.py"
    run_step python3 "$SCRIPTS/regen_results_tsv.py" --repo-root "$ROOT"
    rm -f "$ROOT/_runs/.tsv-header-pending"
    doctor_step
    ;;
  L)
    export NN_RELAUNCH=1
    need "$SCRIPTS/readme-modify-gate.sh"
    need "$SCRIPTS/readme_consistency_gate.py"
    need "$SCRIPTS/regen_results_tsv.py"
    need "$SCRIPTS/d2_data_split_gate.py"
    need "$SCRIPTS/scenario_policy_gate.py"
    run_step bash "$SCRIPTS/readme-modify-gate.sh" "$ROOT"
    run_step python3 "$SCRIPTS/readme_consistency_gate.py" "$ROOT" --strict
    run_step python3 "$SCRIPTS/regen_results_tsv.py" --repo-root "$ROOT"
    rm -f "$ROOT/_runs/.tsv-header-pending"
    run_step python3 "$SCRIPTS/d2_data_split_gate.py" "$ROOT"
    run_step python3 "$SCRIPTS/scenario_policy_gate.py" "$ROOT"
    doctor_step
    smoke_or_skip
    ;;
  T)
    if [[ "$WITH_DOCTOR" -eq 1 ]]; then
      doctor_step
    fi
    if command -v poetry >/dev/null 2>&1; then
      run_step poetry run python -m contract sanity || {
        echo "[modify-post-change] WARN: contract sanity 失败（无 poetry 环境时可忽略后自查）" >&2
        exit 1
      }
    else
      echo "[modify-post-change] WARN: 无 poetry，跳过 contract sanity" >&2
    fi
    smoke_or_skip
    ;;
  Scenario-complete)
    need "$SCRIPTS/readme-modify-gate.sh"
    need "$SCRIPTS/readme_consistency_gate.py"
    need "$SCRIPTS/backfill-scenario-tsv.sh"
    run_step bash "$SCRIPTS/readme-modify-gate.sh" "$ROOT"
    run_step python3 "$SCRIPTS/readme_consistency_gate.py" "$ROOT" --strict
    run_step bash "$SCRIPTS/backfill-scenario-tsv.sh" --dry-run "$ROOT"
    if [[ "$APPLY_BACKFILL" -ne 1 ]]; then
      echo "[modify-post-change] STOP: backfill 仅 dry-run。人审通过后重跑并加 --apply-backfill" >&2
      exit 0
    fi
    run_step bash "$SCRIPTS/backfill-scenario-tsv.sh" --apply "$ROOT"
    export NN_RELAUNCH="${NN_RELAUNCH:-1}"
    need "$SCRIPTS/regen_results_tsv.py"
    need "$SCRIPTS/d2_data_split_gate.py"
    need "$SCRIPTS/scenario_policy_gate.py"
    run_step python3 "$SCRIPTS/regen_results_tsv.py" --repo-root "$ROOT"
    rm -f "$ROOT/_runs/.tsv-header-pending"
    run_step python3 "$SCRIPTS/d2_data_split_gate.py" "$ROOT"
    run_step python3 "$SCRIPTS/scenario_policy_gate.py" "$ROOT"
    doctor_step
    if command -v poetry >/dev/null 2>&1; then
      run_step poetry run python -m contract sanity || true
    fi
    smoke_or_skip
    ;;
  Scenario-expand)
    need "$SCRIPTS/readme-modify-gate.sh"
    need "$SCRIPTS/readme_consistency_gate.py"
    need "$SCRIPTS/scenario_policy_gate.py"
    run_step bash "$SCRIPTS/readme-modify-gate.sh" "$ROOT"
    run_step python3 "$SCRIPTS/readme_consistency_gate.py" "$ROOT" --strict
    run_step python3 "$SCRIPTS/scenario_policy_gate.py" "$ROOT"
    doctor_step
    if [[ -n "${NN_RELAUNCH:-}" ]]; then
      need "$SCRIPTS/regen_results_tsv.py"
      need "$SCRIPTS/d2_data_split_gate.py"
      run_step python3 "$SCRIPTS/regen_results_tsv.py" --repo-root "$ROOT"
      rm -f "$ROOT/_runs/.tsv-header-pending"
      run_step python3 "$SCRIPTS/d2_data_split_gate.py" "$ROOT"
      smoke_or_skip
    else
      echo "[modify-post-change] 未设 NN_RELAUNCH：跳过 regen/d2/smoke（未触达 contract 时正常）"
    fi
    ;;
  *)
    echo "[modify-post-change] 未知 --track=$TRACK（允许: L|T|Scenario-complete|Scenario-expand|ledger-sync）" >&2
    exit 2
    ;;
esac

echo "[modify-post-change] OK track=$TRACK"
exit 0
