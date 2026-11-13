#!/usr/bin/env bash
# commit_card.sh — commit the E-card ledger backfill (manual adjudication) of one
# business repo as a single commit.
#
# Usage:
#   bash commit_card.sh <repo> [decision-file...]
#   When the decision files are omitted, they are inferred from the decision files
#   that actually exist: decisions/<repo>.json and decisions/<repo>.partN.json.
#
# Template 4.1.1 fix ③ (Taishici adjudication: all three are bugs in the template's
# own measuring tools):
#   1. Stage ONLY the target file of this backfill (_runs/analysis/e_feedback.jsonl),
#      **never `git add` the whole working tree**; before committing, re-check the
#      index to make sure it holds only this one file, and abort without committing
#      if anything else is staged (prevents smuggling in business cards / other
#      people's WIP). On abort, unstage only the ledger this script added.
#   2. The decision basis in the commit message is written from the **decision files
#      that actually exist**; one repo may be split into several shards such as
#      <repo>.part1.json / <repo>.part2.json, and the hardcoded
#      decisions/<repo>.json is no longer used (that repo has no such file at all
#      ⇒ the basis path would be fake). Auto-infer with zero hits exits non-zero
#      (do not commit with a placeholder basis). Explicit paths use the same
#      AUTO_RESEARCH/e-card-backfill/decisions/<basename> form in the message.
#
# Single source of truth: this file is versioned together with the steer template
# repo; the operational copy AUTO_RESEARCH/e-card-backfill/commit_card.sh is a
# symlink pointing to this file.
set -uo pipefail

BASE="${NNF_BASE:-/data/xieyl/xie_workspace/AUTO_RESEARCH}"
PROJ="$BASE/auto-nn-factory-projects"
DEC="$BASE/e-card-backfill/decisions"
LEDGER="_runs/analysis/e_feedback.jsonl"
DEC_MSG_PREFIX="AUTO_RESEARCH/e-card-backfill/decisions"

REPO="${1:-}"
if [[ -z "$REPO" ]]; then
  echo "用法: commit_card.sh <仓名> [判定文件...]" >&2
  exit 2
fi
shift || true

ROOT="$PROJ/$REPO"
if [[ ! -d "$ROOT" ]]; then
  echo "仓不存在: $ROOT" >&2
  exit 2
fi
cd "$ROOT" || exit 2

# ── List of decision-basis files (written from the files that actually exist) ──
DEC_LIST=""
_add_dec() {
  local rel="$1"
  if [[ -z "$DEC_LIST" ]]; then
    DEC_LIST="$rel"
  else
    DEC_LIST="$DEC_LIST, $rel"
  fi
}

_dec_msg_path() {
  local f="$1"
  echo "${DEC_MSG_PREFIX}/$(basename "$f")"
}

EXPLICIT=0
if [[ $# -gt 0 ]]; then
  EXPLICIT=1
  for f in "$@"; do
    if [[ -f "$f" ]]; then
      _add_dec "$(_dec_msg_path "$f")"
    else
      echo "WARN: 指定的判定文件不存在，跳过: $f" >&2
    fi
  done
else
  for f in "$DEC/$REPO.json" "$DEC/$REPO".part*.json; do
    [[ -f "$f" ]] || continue
    _add_dec "$(_dec_msg_path "$f")"
  done
fi
if [[ -z "$DEC_LIST" ]]; then
  echo "未找到判定文件: ${DEC_MSG_PREFIX}/${REPO}[.partN].json" >&2
  if [[ $EXPLICIT -eq 1 ]]; then
    echo "显式传入的路径均不存在，已中止（未提交）。" >&2
  else
    echo "自动推断为空，已中止（未提交）。请补判定文件或显式传入路径。" >&2
  fi
  exit 2
fi

# ── Stage only this backfill's target file ─────────────────────────────
git add -- "$LEDGER" || { echo "git add 失败: $REPO" >&2; exit 1; }
if git diff --cached --quiet -- "$LEDGER"; then
  echo "无改动，无需提交: $REPO"
  exit 0
fi

# Belt and braces: no file other than the ledger may be in the index
EXTRA="$(git diff --cached --name-only | grep -v -x -F "$LEDGER" || true)"
if [[ -n "$EXTRA" ]]; then
  echo "暂存区含非本次回填文件，已中止（未提交）:" >&2
  printf '  %s\n' "$EXTRA" >&2
  echo "已撤销本脚本对台账的 stage；其它已暂存文件未动。" >&2
  git restore --staged -- "$LEDGER" 2>/dev/null || git reset HEAD -- "$LEDGER" 2>/dev/null || true
  exit 1
fi

MSG="chore(e-card): 人工判定回填 E 卡新卡面（e_type + headline）

人工判定回填，非软件自动回填。逐卡依据见
${DEC_LIST}
与 AUTO_RESEARCH/e-card-backfill/decisions/RULES.md。
模板 4.1.0 起新 shout 须带 e_type + 一行 headline；本次按用户拍板
对存量旧卡补卡面，只新增 e_type/headline/e_type_note/continues 四键，
其余字段逐字节未动。"

git commit -m "$MSG" -- "$LEDGER" || { echo "git commit 失败: $REPO" >&2; exit 1; }
echo "已提交: $REPO ($LEDGER)"
