#!/usr/bin/env bash
# manual-run-scope-check.sh — preflight git diff 闸 (nn-doctor §8 兜底)
#
# 扫 git diff(working tree + staged + HEAD~1 HEAD 合并去重),按路径模式
# 映射到 Modify Track 代号或 IMMUTABLE 桶,emit 单行 stdout:
#   PASS: 无改动 / 仅 ledger.watchlist 台账同步 → exit 0
#   FAIL: IMMUTABLE（须 NN_RELAUNCH=1）或 NN_MANUAL_RUN_STRICT=1 下的 workspace-edit → exit 2
#   WARN: 检测到改能力范围改动 → exit 1
#   SKIP: 非 git 仓或 git diff 不可用 → exit 0
#
# 路径模式:
#   experiment.py, contract/**, CLAUDE.md, PROTOCOL.md, auto-nn-run.sh → IMMUTABLE
#   workspace/**, train.py → workspace-edit（默认 WARN；STRICT 时 FAIL）
#   _runs/results.tsv → WARN ledger/hand-edit（勿手改 TSV）
#   scripts/modify-config.py → PASS 忽略（单次 config 合法）
#   nn-config.yaml: 仅 watchlist → PASS；keep 段 → Modify-L3；其它 → WARN nn-config
#   *metric* → Modify-L2
#   scenarios.yaml, F1*, scenario_bindings* → Modify-Scenario
# 白名单:_runs/configs/**
#
# 用法: bash manual-run-scope-check.sh [--repo-root <path>]

set -euo pipefail

REPO_ROOT="."
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root) REPO_ROOT="${2:-}"; shift 2 ;;
    *) echo "WARN: 未知参数: $1" >&2; exit 1 ;;
  esac
done

if ! git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
  echo "SKIP: 非 git 仓或 git diff 不可用"
  exit 0
fi

diff_paths="$(
  {
    git -C "$REPO_ROOT" diff --name-only 2>/dev/null || true
    git -C "$REPO_ROOT" diff --cached --name-only 2>/dev/null || true
    git -C "$REPO_ROOT" log --name-only --pretty=format: -1 HEAD~1..HEAD 2>/dev/null || true
  } | awk 'NF' | sort -u
)"

filtered="$(printf '%s\n' "$diff_paths" | grep -v '^_runs/configs/' || true)"
# 单次 config 改参不算改能力
filtered="$(printf '%s\n' "$filtered" | grep -v '^scripts/modify-config\.py$' || true)"

if [[ -z "$filtered" ]]; then
  echo "PASS: 无 Modify Track 范围改动"
  exit 0
fi

# nn-config.yaml：仅 watchlist → 台账同步 PASS；keep → L3；其它 → nn-config WARN
_nn_config_code() {
  local diff
  diff="$(git -C "$REPO_ROOT" diff HEAD -- nn-config.yaml 2>/dev/null || true)"
  diff+="$(git -C "$REPO_ROOT" diff --cached -- nn-config.yaml 2>/dev/null || true)"
  if [[ -z "$diff" ]]; then
    # 仅出现在上一 commit 文件列表、无内容 diff 时保守 WARN
    echo "nn-config"
    return
  fi
  if printf '%s\n' "$diff" | grep -qiE '^[+-].*keep:'; then
    echo "Modify-L3"
    return
  fi
  # 若 diff 行（非 ---/+++）均与 watchlist/ledger 相关，或仅空白 → watchlist sync
  local suspicious
  suspicious="$(printf '%s\n' "$diff" | grep -E '^[+-]' | grep -vE '^[+-]{3}' | grep -viE 'watchlist|ledger:|^[+-]\s*- |^[+-]\s*$|^[+-]\s*#|^[+-]\s*\[|^[+-]\s*\]' || true)"
  if [[ -z "$suspicious" ]]; then
    echo "watchlist-sync"
    return
  fi
  echo "nn-config"
}

codes=""
files=""
immutable_files=""
workspace_edit_files=""
watchlist_only=1
while IFS= read -r p; do
  [[ -z "$p" ]] && continue
  code=""
  case "$p" in
    experiment.py|contract|contract/*|CLAUDE.md|PROTOCOL.md|auto-nn-run.sh)
      if [[ -z "$immutable_files" ]]; then
        immutable_files="$p"
      elif ! [[ ",$immutable_files," == *",$p,"* ]]; then
        immutable_files="${immutable_files},${p}"
      fi
      watchlist_only=0
      ;;
    workspace/*|train.py)
      code="workspace-edit"
      workspace_edit_files="${workspace_edit_files:+$workspace_edit_files,}$p"
      watchlist_only=0
      ;;
    _runs/results.tsv)
      code="hand-edit-tsv"
      watchlist_only=0
      ;;
    nn-config.yaml)
      code="$(_nn_config_code)"
      if [[ "$code" != "watchlist-sync" ]]; then
        watchlist_only=0
      fi
      if [[ "$code" == "watchlist-sync" ]]; then
        code=""  # 不计入 codes；稍后统一 PASS
      fi
      ;;
    *metric*)
      code="Modify-L2"
      watchlist_only=0
      ;;
    scenarios.yaml|F1*|scenario_bindings*)
      code="Modify-Scenario"
      watchlist_only=0
      ;;
    *)
      watchlist_only=0
      ;;
  esac
  if [[ -n "$code" ]]; then
    if [[ -z "$codes" ]]; then
      codes="$code"
    elif ! [[ ",$codes," == *",$code,"* ]]; then
      codes="${codes},${code}"
    fi
  fi
  files="${files:+$files,}$p"
done <<< "$filtered"

if [[ -n "$immutable_files" && -z "${NN_RELAUNCH:-}" ]]; then
  echo "FAIL: IMMUTABLE 路径改动（须 NN_RELAUNCH=1）: ${immutable_files}"
  exit 2
fi

# 仅 watchlist 台账同步
if [[ "$watchlist_only" -eq 1 ]] && [[ -z "$codes" ]] && [[ -n "$files" ]]; then
  echo "PASS: ledger.watchlist sync (not Modify Track)"
  exit 0
fi

if [[ -z "$codes" ]]; then
  echo "PASS: 无 Modify Track 范围改动"
  exit 0
fi

# STRICT：workspace-edit → FAIL
if [[ -n "${NN_MANUAL_RUN_STRICT:-}" && -n "$workspace_edit_files" ]]; then
  echo "FAIL: STRICT workspace-edit（workspace/train；设 NN_MANUAL_RUN_STRICT=1）: ${workspace_edit_files}"
  exit 2
fi

# nn-config 其它变更：文案不再叫 Modify-L1
codes="${codes//nn-config/nn-config(ledger-sync or modify as needed)}"
codes="${codes//hand-edit-tsv/hand-edit-tsv(use regen)}"

echo "WARN: 检测到 ${codes} 范围改动: ${files}"
exit 1
