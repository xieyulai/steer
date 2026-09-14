#!/usr/bin/env bash
# readme-modify-gate.sh — modify **Modify-L/Scenario-*** 后防「contract 变了 README 完全未碰」
#
# 用法:
#   bash scripts/readme-modify-gate.sh [repo_root]
# 环境:
#   NN_MODIFY_TRACK     含 L 或 S 时强制检查（即使 git 无 contract diff）
#   README_SYNC_SKIP=1  跳过（须 README_SYNC_SKIP_REASON）
#   README_GATE_SINCE   可选，传给 git diff（如 HEAD~1）
set -euo pipefail

REPO="${1:-.}"
cd "$REPO"

if [[ "${README_SYNC_SKIP:-}" == "1" ]]; then
  if [[ -z "${README_SYNC_SKIP_REASON:-}" ]]; then
    echo "[readme-modify-gate] SKIP 须设 README_SYNC_SKIP_REASON" >&2
    exit 1
  fi
  exit 0
fi

if [[ -f scripts/readme_consistency_gate.py ]]; then
  if python3 scripts/readme_consistency_gate.py . --strict 2>/dev/null; then
    exit 0
  fi
fi

need_check=0
if [[ "${NN_MODIFY_TRACK:-}" =~ (^|,)(L|S)(,|$) ]]; then
  need_check=1
fi

if ! git -C "$REPO" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "[readme-modify-gate] WARN: 非 git 仓，跳过检查" >&2
  exit 0
fi

SINCE="${README_GATE_SINCE:-}"
staged="$(git -C "$REPO" diff --cached --name-only 2>/dev/null || true)"
unstaged="$(git -C "$REPO" diff --name-only 2>/dev/null || true)"
files="$(printf '%s\n%s' "$staged" "$unstaged" | sort -u | grep -v '^$' || true)"

contract_touched=0
nn_agent_keep_touched=0
while IFS= read -r f; do
  [[ -z "$f" ]] && continue
  [[ "$f" == contract/* ]] && contract_touched=1
  if [[ "$f" == nn-config.yaml ]]; then
    diff_out="$(git -C "$REPO" diff ${SINCE:+$SINCE} -- nn-config.yaml 2>/dev/null || true)"
    if printf '%s\n' "$diff_out" | grep -qE '^[+-](agent|keep):'; then
      nn_agent_keep_touched=1
    fi
  fi
done <<< "$files"

if [[ $contract_touched -eq 1 || $nn_agent_keep_touched -eq 1 ]]; then
  need_check=1
fi

if [[ $need_check -eq 0 ]]; then
  exit 0
fi

if printf '%s\n' "$files" | grep -qx 'README.md'; then
  exit 0
fi

echo "[readme-modify-gate] contract 或 nn-config(agent/keep) 已变更，但 README.md 无同次 diff。" >&2
echo "→ 按 docs/archive/readme-sync-after-modify.md 更新；或 README_SYNC_SKIP=1 + README_SYNC_SKIP_REASON。" >&2
exit 1
