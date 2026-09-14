#!/usr/bin/env bash
# _check_template_version.sh — auto-nn-update 在 governance-sync 之前的 version gate
#
# 用法（在业务仓根）：
#   bash scripts/_check_template_version.sh \
#     --template-root <TEMPLATE_ROOT> \
#     --business-root <BUSINESS_ROOT> \
#     [--accept-major-bump] \
#     [--strict-version]
#
# 退出码：
#   0 = 通过（governance-sync 可继续）
#   1 = 阻断（需用户确认 major 或修正 downgrade）
#   2 = 内部错误（VERSION 文件读不出）
#
# 调 check_template_version.py --check 做实际判断；本脚本负责：
#   1. 读 .auto-nn/version（业务仓）
#   2. 读 $TEMPLATE_ROOT/VERSION（模板 semver）
#   3. 拼 template version = "<semver>+<HEAD short SHA>"
#   4. shell out 给 python，传入 args
set -euo pipefail

TEMPLATE_ROOT=""
BUSINESS_ROOT=""
ACCEPT_MAJOR=0
STRICT_VERSION=0

usage() {
  cat <<'EOF'
用法: _check_template_version.sh [选项]

  --template-root <T>     模板维护仓根（必填）
  --business-root <B>     业务仓根（默认 cwd）
  --accept-major-bump     接受 major bump（无此 flag 则 major 阻断）
  --strict-version        拒绝降级（默认仅 WARN）
  -h, --help              本帮助

退出码：0=通过 1=阻断 2=内部错误
EOF
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --template-root=*) TEMPLATE_ROOT="${1#*=}"; shift ;;
    --business-root=*) BUSINESS_ROOT="${1#*=}"; shift ;;
    --template-root) TEMPLATE_ROOT="${2:?require value}"; shift 2 ;;
    --business-root) BUSINESS_ROOT="${2:?require value}"; shift 2 ;;
    --accept-major-bump) ACCEPT_MAJOR=1; shift ;;
    --strict-version) STRICT_VERSION=1; shift ;;
    -h|--help) usage 0 ;;
    *) echo "[_check_template_version] FAIL: 未知参数 $1" >&2; usage 1 ;;
  esac
done

if [[ -z "$TEMPLATE_ROOT" ]]; then
  echo "[_check_template_version] FAIL: --template-root 必填" >&2
  exit 2
fi
BUSINESS_ROOT="${BUSINESS_ROOT:-$(pwd)}"

# 1) 读业务仓 stamp（可能空）
BIZ_VERSION=""
if [[ -f "$BUSINESS_ROOT/.auto-nn/version" ]]; then
  BIZ_VERSION="$(tr -d '\r\n' < "$BUSINESS_ROOT/.auto-nn/version")"
fi

# 2) 读模板 semver
if [[ ! -s "$TEMPLATE_ROOT/VERSION" ]]; then
  echo "[_check_template_version] FAIL: 模板仓 $TEMPLATE_ROOT/VERSION 缺失或空" >&2
  exit 2
fi
TPL_SEMVER="$(tr -d '\r\n' < "$TEMPLATE_ROOT/VERSION")"

# 3) 拼 template stamp
TPL_SHA="$(git -C "$TEMPLATE_ROOT" rev-parse --short HEAD 2>/dev/null || echo "unknown")"
TPL_VERSION="${TPL_SEMVER}+${TPL_SHA}"

# 4) 找 check_template_version.py
CHECK_PY=""
for cand in \
  "$BUSINESS_ROOT/scripts/check_template_version.py" \
  "$TEMPLATE_ROOT/template/package/scripts/check_template_version.py"; do
  if [[ -f "$cand" ]]; then
    CHECK_PY="$cand"
    break
  fi
done
if [[ -z "$CHECK_PY" ]]; then
  echo "[_check_template_version] FAIL: 找不到 check_template_version.py" >&2
  echo "  试: $BUSINESS_ROOT/scripts/ 或 $TEMPLATE_ROOT/template/package/scripts/" >&2
  exit 2
fi

# 5) shell-out 给 python
ARGS=(--check --business-version "$BIZ_VERSION" --template-version "$TPL_VERSION")
[[ "$ACCEPT_MAJOR" -eq 1 ]] && ARGS+=(--accept-major-bump)
[[ "$STRICT_VERSION" -eq 1 ]] && ARGS+=(--strict-version)

# 5a) Spec §4 #3: 模板仓非 git → stamp = "<semver>+unknown"，WARN + exit 0
#     短路：python 解析器要求 hex SHA（spec §1 决策 1），unknown 走不通；
#     bash 层直接 WARN + 放行，避免 python 把 unknown 误判为非法。
if [[ "$TPL_SHA" == "unknown" ]]; then
  echo "[_check_template_version] WARN: 模板仓非 git，stamp = ${TPL_VERSION}（无 SHA）" >&2
  exit 0
fi

PYTHONPATH="$(dirname "$CHECK_PY")" python3 "$CHECK_PY" "${ARGS[@]}"