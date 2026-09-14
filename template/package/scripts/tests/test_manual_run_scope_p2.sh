#!/usr/bin/env bash
# test_manual_run_scope_p2.sh — watchlist PASS / STRICT workspace-edit FAIL
set -euo pipefail
SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCOPE="$SCRIPTS/manual-run-scope-check.sh"
TMP="$(mktemp -d -t scope-p2-XXXXXX)"
trap 'rm -rf "$TMP"' EXIT

PASS=0
FAIL=0
ok() { echo "  OK: $*"; PASS=$((PASS+1)); }
fail() { echo "FAIL: $*" >&2; FAIL=$((FAIL+1)); }

setup_git() {
  local d="$1"
  mkdir -p "$d"
  git -C "$d" init -q
  git -C "$d" config user.email t@t
  git -C "$d" config user.name t
  echo "profile: supervised" > "$d/nn-config.yaml"
  printf 'ledger:\n  watchlist:\n    - LR\n' >> "$d/nn-config.yaml"
  echo "print(1)" > "$d/train.py"
  git -C "$d" add -A
  git -C "$d" commit -q -m init
}

echo "=== A: 仅改 watchlist → PASS not Modify"
REPO_A="$TMP/a"
setup_git "$REPO_A"
printf 'ledger:\n  watchlist:\n    - LR\n    - EPOCHS\n' >> "$REPO_A/nn-config.yaml"
# rewrite file cleanly
cat > "$REPO_A/nn-config.yaml" <<'EOF'
profile: supervised
ledger:
  watchlist:
    - LR
    - EPOCHS
EOF
out="$(bash "$SCOPE" --repo-root "$REPO_A" 2>&1 || true)"
rc=$?
if [[ $rc -eq 0 && "$out" == *watchlist* && "$out" == *"not Modify"* ]]; then
  ok "watchlist PASS"
else
  fail "A rc=$rc out=$out"
fi

echo "=== B: 改 train.py 默认 WARN"
REPO_B="$TMP/b"
setup_git "$REPO_B"
echo "print(2)" > "$REPO_B/train.py"
set +e
out="$(bash "$SCOPE" --repo-root "$REPO_B" 2>&1)"
rc=$?
set -e
if [[ $rc -eq 1 && "$out" == WARN:* && "$out" == *workspace-edit* ]]; then
  ok "train WARN"
else
  fail "B rc=$rc out=$out"
fi

echo "=== C: STRICT train → FAIL exit 2"
set +e
out="$(NN_MANUAL_RUN_STRICT=1 bash "$SCOPE" --repo-root "$REPO_B" 2>&1)"
rc=$?
set -e
if [[ $rc -eq 2 && "$out" == FAIL:* && "$out" == *STRICT* ]]; then
  ok "STRICT FAIL"
else
  fail "C rc=$rc out=$out"
fi

echo "=== 汇总 PASS=$PASS FAIL=$FAIL"
[[ $FAIL -eq 0 ]]
