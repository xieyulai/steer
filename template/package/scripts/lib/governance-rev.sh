#!/usr/bin/env bash
# governance-rev.sh — .auto-nn/governance-rev 参与文件列表（单一权威）与哈希计算
#
# 被 governance-sync.sh、nn-doctor.sh、verify-migration-complete.sh 共同 source。
# 增删治理文件时只改 GOVERNANCE_REV_FILE_PATHS 一处；template_tests/test_governance_rev.py 防漂移。
set -euo pipefail

# 路径相对 template/package 根目录；顺序稳定，勿随意重排。
GOVERNANCE_REV_FILE_PATHS=(
  profiles.yaml
  scripts/lib/governance-rev.sh
  scripts/verify-migration-complete.sh
  scripts/rl_workspace_gate.py
  scripts/d2_data_split_gate.py
  scripts/scenario_policy_gate.py
  scripts/readme-modify-gate.sh
  scripts/readme_consistency_gate.py
  scripts/smoke-check.sh
  scripts/wait-train.sh
  scripts/claude_stream_summarize.py
  scripts/claude_stream_result_watchdog.py
  scripts/verify_project_layout.py
  scripts/regen_results_tsv.py
  scripts/sync_exploration_ledger.py
  scripts/sync_ledger.py
  scripts/govern-runs.sh
  scripts/prune-runs.py
  scripts/clear-runs.sh
  scripts/clear_inspect.py
  scripts/nn-doctor.sh
  scripts/check_goal.py
  scripts/scan_no_fallback.py
)

# 计算 package 根目录的 16 字符 governance rev。
governance_rev_compute() {
  local pkg="${1:?pkg root required}"
  local -a inputs=()
  local rel missing=0
  for rel in "${GOVERNANCE_REV_FILE_PATHS[@]}"; do
    if [[ ! -f "$pkg/$rel" ]]; then
      echo "[governance-rev] FAIL: 缺少 $pkg/$rel" >&2
      missing=1
    fi
    inputs+=("$pkg/$rel")
  done
  if [[ $missing -ne 0 ]]; then
    return 1
  fi
  sha256sum "${inputs[@]}" | sha256sum | awk '{print $1}' | cut -c1-16
}
