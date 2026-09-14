#!/usr/bin/env bash
# template-version.sh — 业务仓独立查模板版本
#
# 用法（在业务仓根）：
#   bash scripts/template-version.sh         # 打印当前 .auto-nn/version（+ 有则 init）
#   bash scripts/template-version.sh --json  # JSON（含 governance-rev / init-template-version）
#   bash scripts/template-version.sh --init  # 只打立项原始戳（缺则 exit 1）
#
# 退出码：0 = 有当前版本（或 --init 时有原始戳）；1 = 未初始化 / 缺原始戳
set -euo pipefail

ROOT=""
JSON=0
INIT_ONLY=0

usage() {
  cat <<'EOF'
用法: template-version.sh [业务仓路径] [--json] [--init]

  打印业务仓 .auto-nn/version（当前模板戳 = semver+SHA）。
  若存在 .auto-nn/init-template-version，文本模式另打一行 init-template-version: …
  若 .auto-nn/version 缺失，exit 1 并提示「未初始化」。

  --json   输出 JSON（version / governance-rev / init-template-version）
  --init   只打印立项原始戳；缺失则 exit 1
EOF
  exit "${1:-0}"
}

# 先解 flags，再把第一个非-flag 视为 ROOT（业务仓路径），避免与 --json 等冲突
while [[ $# -gt 0 ]]; do
  case "$1" in
    --json) JSON=1; shift ;;
    --init) INIT_ONLY=1; shift ;;
    -h|--help) usage 0 ;;
    --) shift; break ;;
    -*) echo "[template-version] FAIL: 未知参数 $1" >&2; usage 1 ;;
    *) ROOT="$1"; shift ;;
  esac
done
ROOT="${ROOT:-$(pwd)}"

VER=""
REV=""
INIT_VER=""
[[ -f "$ROOT/.auto-nn/version" ]] && VER="$(tr -d '\r\n' < "$ROOT/.auto-nn/version")"
[[ -f "$ROOT/.auto-nn/governance-rev" ]] && REV="$(tr -d '\r\n' < "$ROOT/.auto-nn/governance-rev")"
[[ -f "$ROOT/.auto-nn/init-template-version" ]] && INIT_VER="$(tr -d '\r\n' < "$ROOT/.auto-nn/init-template-version")"

if [[ $INIT_ONLY -eq 1 ]]; then
  if [[ -z "$INIT_VER" ]]; then
    echo "[template-version] 无立项原始模板戳（.auto-nn/init-template-version 缺失）" >&2
    exit 1
  fi
  printf '%s\n' "$INIT_VER"
  exit 0
fi

if [[ -z "$VER" ]]; then
  echo "[template-version] 未初始化（.auto-nn/version 缺失）— 请跑 /auto-nn-init 或 auto-nn-update" >&2
  exit 1
fi

if [[ $JSON -eq 1 ]]; then
  # 最小 JSON（无 jq 依赖）
  printf '{"version": "%s", "governance-rev": "%s", "init-template-version": "%s"}\n' \
    "$VER" "$REV" "$INIT_VER"
else
  printf '%s\n' "$VER"
  if [[ -n "$REV" ]]; then
    printf 'governance-rev: %s\n' "$REV"
  fi
  if [[ -n "$INIT_VER" ]]; then
    printf 'init-template-version: %s\n' "$INIT_VER"
  fi
fi
