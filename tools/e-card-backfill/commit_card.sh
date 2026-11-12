#!/usr/bin/env bash
# commit_card.sh — 把某个业务仓的 E 卡台账（人工判定回填）单独提交一笔
#
# 用法:
#   bash commit_card.sh <仓名> [判定文件...]
#   判定文件省略时，按实际存在的 decisions/<仓名>.json 与 decisions/<仓名>.partN.json 推断。
#
# 模板 4.1.1 修 ③（太史慈判定：三处都是模板尺子的错）：
#   1. 只 stage 本次回填的目标文件（_runs/analysis/e_feedback.jsonl），
#      **禁止整工作区 git add**；提交前再核一遍暂存区只含这一个文件，
#      有多余文件就中止不提交（防止夹带业务卡/别人的 WIP）。
#   2. commit message 里的判定依据按**实际存在的判定文件**写，
#      一个仓可能拆成 <仓名>.part1.json / <仓名>.part2.json 多个分片，
#      不再硬编码 decisions/<仓名>.json（那个仓根本没这个文件 ⇒ 依据路径是假的）。
#
# 单一事实源：本文件随 steer 模板仓一起版本化；
# 运维副本 AUTO_RESEARCH/e-card-backfill/commit_card.sh 是指向本文件的符号链接。
set -uo pipefail

BASE="${NNF_BASE:-/data/xieyl/xie_workspace/AUTO_RESEARCH}"
PROJ="$BASE/auto-nn-factory-projects"
DEC="$BASE/e-card-backfill/decisions"
LEDGER="_runs/analysis/e_feedback.jsonl"

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

# ── 判定依据文件清单（按实际存在的文件写，不硬编码）────────────────────────
DEC_LIST=""
_add_dec() {
  local rel="$1"
  if [[ -z "$DEC_LIST" ]]; then
    DEC_LIST="$rel"
  else
    DEC_LIST="$DEC_LIST, $rel"
  fi
}

if [[ $# -gt 0 ]]; then
  # 调用方显式给了判定文件（apply_all.sh 有权威映射）
  for f in "$@"; do
    if [[ -f "$f" ]]; then
      _add_dec "$f"
    else
      echo "WARN: 指定的判定文件不存在，跳过: $f" >&2
    fi
  done
else
  for f in "$DEC/$REPO.json" "$DEC/$REPO".part*.json; do
    [[ -f "$f" ]] || continue
    _add_dec "AUTO_RESEARCH/e-card-backfill/decisions/$(basename "$f")"
  done
fi
if [[ -z "$DEC_LIST" ]]; then
  DEC_LIST="（未找到判定文件：AUTO_RESEARCH/e-card-backfill/decisions/${REPO}[.partN].json）"
fi

# ── 只 stage 本次回填目标文件 ─────────────────────────────────────────────
git add -- "$LEDGER" || { echo "git add 失败: $REPO" >&2; exit 1; }
if git diff --cached --quiet -- "$LEDGER"; then
  echo "无改动，无需提交: $REPO"
  exit 0
fi

# 双保险：暂存区里除台账外不允许有别的文件
EXTRA="$(git diff --cached --name-only | grep -v -x -F "$LEDGER" || true)"
if [[ -n "$EXTRA" ]]; then
  echo "暂存区含非本次回填文件，已中止（未提交）:" >&2
  printf '  %s\n' "$EXTRA" >&2
  echo "请先自行处理暂存区（git restore --staged <路径>），再重跑本脚本。" >&2
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
