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
  echo "usage: commit_card.sh <repo> [decision-file...]" >&2
  exit 2
fi
shift || true

ROOT="$PROJ/$REPO"
if [[ ! -d "$ROOT" ]]; then
  echo "repo not found: $ROOT" >&2
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
      echo "WARN: decision file missing, skipped: $f" >&2
    fi
  done
else
  for f in "$DEC/$REPO.json" "$DEC/$REPO".part*.json; do
    [[ -f "$f" ]] || continue
    _add_dec "$(_dec_msg_path "$f")"
  done
fi
if [[ -z "$DEC_LIST" ]]; then
  echo "no decision file found: ${DEC_MSG_PREFIX}/${REPO}[.partN].json" >&2
  if [[ $EXPLICIT -eq 1 ]]; then
    echo "all explicit paths are missing; aborted (nothing committed)." >&2
  else
    echo "auto-infer found nothing; aborted (nothing committed). Add decision files or pass paths." >&2
  fi
  exit 2
fi

# ── Stage only this backfill's target file ─────────────────────────────
git add -- "$LEDGER" || { echo "git add failed: $REPO" >&2; exit 1; }
if git diff --cached --quiet -- "$LEDGER"; then
  echo "no changes to commit: $REPO"
  exit 0
fi

# Belt and braces: no file other than the ledger may be in the index
EXTRA="$(git diff --cached --name-only | grep -v -x -F "$LEDGER" || true)"
if [[ -n "$EXTRA" ]]; then
  echo "index holds files outside this backfill; aborted (nothing committed):" >&2
  printf '  %s\n' "$EXTRA" >&2
  echo "unstaged the ledger this script added; other staged files were left alone." >&2
  git restore --staged -- "$LEDGER" 2>/dev/null || git reset HEAD -- "$LEDGER" 2>/dev/null || true
  exit 1
fi

MSG="chore(e-card): manual backfill of E-card face fields (e_type + headline)

Manual adjudication backfill, not an automatic software write-back. Per-card
basis:
${DEC_LIST}
and AUTO_RESEARCH/e-card-backfill/decisions/RULES.md.
Since template 4.1.0 a new shout must carry e_type and a one-line headline;
this pass only adds e_type / headline / e_type_note / continues on existing
cards. Every other field is left byte-for-byte unchanged."

git commit -m "$MSG" -- "$LEDGER" || { echo "git commit failed: $REPO" >&2; exit 1; }
echo "committed: $REPO ($LEDGER)"
