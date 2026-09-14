#!/usr/bin/env bash
# release-check.sh — 维护者 release 前自检（7 步短路拦截）
#
# 判定顺序（短路：先失败先退）：
#   1) git dirty（VERSION / CHANGELOG.md 未 commit）
#   2) VERSION 非空 + semver 合法
#   3) 上一 commit 与 HEAD 的 VERSION 比对（识别 bump type）
#   4) 若 major bump：CHANGELOG.md 含 "^## \[<NEW_VERSION>\](\s|$)" 段（Keep-a-Changelog 1.1.0 格式）
#   5) CHANGELOG 段日期 ≤ today
#   6) skill-code contract lint（SKILL.md ## Code Contract ↔ template/package/* 实符号对账；
#      FAIL > 0 阻断；CHECK_SKILL_CONTRACT_SKIP=1 可临时跳过）
#   7) package docs contract lint（PROTOCOL/CLAUDE banned+required；
#      FAIL > 0 阻断；CHECK_PACKAGE_DOCS_CONTRACT_SKIP=1 可临时跳过）
#
# 用法：
#   bash scripts/release-check.sh
#
# 退出码：
#   0 = OK，可发
#   1 = 阻断（具体见 stderr）
set -euo pipefail

# ROOT = 要校验的仓。默认从脚本自身位置推断（维护者直接 `bash scripts/release-check.sh`
# 时正确）；bump-version.sh 作为子进程跨仓调用时须通过 RELEASE_CHECK_ROOT 指明目标仓
# （否则脚本会 cd 回模板仓、读到模板仓的 VERSION 而非被 bump 的仓）。
ROOT="${RELEASE_CHECK_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
cd "$ROOT"

fail() { echo "[release-check] FAIL: $*" >&2; exit 1; }
warn() { echo "[release-check] WARN: $*" >&2; }

# 1) git dirty
if ! git status --porcelain VERSION CHANGELOG.md | grep -q .; then
  :
else
  fail "请先 commit VERSION + CHANGELOG.md 再跑 release-check（git 工作区脏）"
fi

# 2) VERSION 合法
[[ -s VERSION ]] || fail "VERSION 缺失或空"
NEW_VER="$(tr -d '\r\n' < VERSION)"
[[ "$NEW_VER" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "VERSION 非法 semver: $NEW_VER"

# 3) bump 识别（HEAD~1 → HEAD）
PREV_VER="$(git show HEAD~1:VERSION 2>/dev/null | tr -d '\r\n' || echo "")"
if [[ -z "$PREV_VER" ]]; then
  fail "未 bump VERSION（HEAD~1:VERSION 缺失；首次 release 不应走 release-check）"
fi

# CHANGELOG.md 存在性断言（Step 4/5 都读；先验避免 grep 漏 leak stderr 噪音）
[[ -s CHANGELOG.md ]] || fail "CHANGELOG.md 缺失或空"

# 调 python 做 classify
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUMP="$(
  PYTHONPATH="$SCRIPT_DIR" python3 - "$PREV_VER" "$NEW_VER" <<'PY'
import sys
from check_template_version import parse, classify
prev, new = parse(sys.argv[1]), parse(sys.argv[2])
print(classify(prev, new).value)
PY
)" || fail "classify 失败"

case "$BUMP" in
  patch|minor|major) ;;
  *) fail "未 bump VERSION（$PREV_VER → $NEW_VER 不是 bump）" ;;
esac

# 4) major bump → CHANGELOG 段必须存在
# Keep-a-Changelog 1.1.0 格式：## [0.1.0] - 2026-07-06（含方括号）
if [[ "$BUMP" == "major" ]]; then
  grep -qE "^## \[${NEW_VER}\](\s|$)" CHANGELOG.md \
    || fail "CHANGELOG 缺 ## [${NEW_VER}] 段（major bump 必须有 release notes）"
fi

# 5) CHANGELOG 段日期 ≤ today
# 抓最近一个 ## [<NEW_VER>] 行（含同行日期 " - YYYY-MM-DD"）
# mawk 不支持 match() + 复杂 regex；用 grep -E 提取 + awk 切片
TODAY="$(date +%Y-%m-%d)"
HEADER_LINE="$(grep -nE "^## \\[${NEW_VER}\\]" CHANGELOG.md | head -1 | cut -d: -f1)"
if [[ -z "$HEADER_LINE" ]]; then
  DATE_IN_CHANGELOG=""
else
  DATE_IN_CHANGELOG="$(
    sed -n "${HEADER_LINE}p" CHANGELOG.md | awk '{
      i = index($0, "20");  # ISO 日期以 20xx 开头
      if (i == 0) exit 1;
      print substr($0, i, 10);
    }'
  )"
  # 若同行无日期，回退到下一行
  if [[ -z "$DATE_IN_CHANGELOG" ]]; then
    NEXT=$((HEADER_LINE + 1))
    DATE_IN_CHANGELOG="$(
      sed -n "${NEXT}p" CHANGELOG.md | awk '{
        i = index($0, "20");
        if (i == 0) exit 1;
        print substr($0, i, 10);
      }'
    )"
  fi
fi
if [[ -z "$DATE_IN_CHANGELOG" ]]; then
  fail "CHANGELOG ## [${NEW_VER}] 段无日期（格式：## [${NEW_VER}] - YYYY-MM-DD）"
fi
if [[ "$DATE_IN_CHANGELOG" > "$TODAY" ]]; then
  fail "CHANGELOG ## [${NEW_VER}] 日期 $DATE_IN_CHANGELOG 是未来（today=$TODAY）"
fi

# 6) skill-code contract lint（CHECK_SKILL_CONTRACT_SKIP=1 可临时跳过，例如 1.16.0 前无 Code Contract 时）
#    调 check_skill_contract.sh --quiet：PASS 隐藏、FAIL/WARN 可见；FAIL>0 → 阻断
#    阻断：code 与 SKILL.md ## Code Contract 漂移，发版前须修
if [[ "${CHECK_SKILL_CONTRACT_SKIP:-0}" != "1" ]]; then
  echo "[release-check] Step 6: skill-code contract lint"
  if ! bash "$SCRIPT_DIR/check_skill_contract.sh" --quiet; then
    fail "skill-code contract drift（FAIL>0），见 check_skill_contract.sh 输出"
  fi
fi

# 6.5) skeleton_queue 健康 lint（A2 引入；NN_SKELETON_QUEUE_SKIP=1 临时跳过）
#    扫 saved/skeleton_queue.json，pending_fill 超 deadline → exit 1 阻断发版
#    阻断：骨架队列 overdue 没填，跨轮承诺破产；发版前须真填/标 abandoned
if [[ "${NN_SKELETON_QUEUE_SKIP:-0}" != "1" ]]; then
  echo "[release-check] Step 6.5: skeleton_queue health lint"
  if ! bash "$SCRIPT_DIR/check_skeleton_queue_health.sh"; then
    fail "skeleton_queue 有 overdue items，见 check_skeleton_queue_health.sh 输出"
  fi
fi

# 7) package docs contract lint
if [[ "${CHECK_PACKAGE_DOCS_CONTRACT_SKIP:-0}" != "1" ]]; then
  echo "[release-check] Step 7: package docs contract lint"
  if ! bash "$SCRIPT_DIR/check_package_docs_contract.sh" --quiet; then
    fail "package docs contract drift（FAIL>0），见 check_package_docs_contract.sh 输出"
  fi
fi

echo "[release-check] OK: release ${NEW_VER} (${BUMP})"
exit 0
