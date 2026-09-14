#!/usr/bin/env bash
# verify_governance_sync_dest.sh — L3-A1 端到端验证
# 目的：业务仓跑 `dest/scripts/governance-sync.sh` 后，验 `dest/scripts/lib/` 真含
#   presets.py（v1.5.5 漏 lib 修复端到端；abcde_modifier_derive 已退役）
#
# 用法（在业务仓 cwd 或 template 仓根都可）：
#   bash template/package/scripts/verify_governance_sync_dest.sh --dest /path/to/dest \
#       [--template-root /path/to/template]
#   # 缺 --dest 时默认 cwd（要求 cwd = 业务仓根）
#   # 缺 --template-root 时默认与 dest 相同（要求 cwd 含 template/ 子目录）
#
# 退出码：0 = lib 在；1 = 缺 / 路径错 / 0 字节
#
# 配套单测：template/package/scripts/tests/test_verify_governance_sync_dest.py

set -euo pipefail

DEST=""
TEMPLATE_ROOT=""
# 也支持 --dest / --template-root 形式
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dest) DEST="$2"; shift 2 ;;
    --template-root) TEMPLATE_ROOT="$2"; shift 2 ;;
    -h|--help) head -20 "$0" | tail -16; exit 0 ;;
    *) DEST="$1"; shift ;;  # 兼容：第一个 positional 作 dest
  esac
done

# default dest = cwd
DEST="${DEST:-.}"
# default template-root = $DEST（要求 dest 含 template/ 子目录）
TEMPLATE_ROOT="${TEMPLATE_ROOT:-$DEST}"

if [[ ! -d "$DEST" ]]; then
  echo "FAIL: dest 目录不存在: $DEST" >&2
  exit 1
fi

DEST=$(cd "$DEST" && pwd)
TEMPLATE_ROOT=$(cd "$TEMPLATE_ROOT" && pwd)
GOVSYNC="$DEST/scripts/governance-sync.sh"

if [[ ! -f "$GOVSYNC" ]]; then
  echo "FAIL: dest 没 governance-sync.sh：$GOVSYNC" >&2
  exit 1
fi

# 1. governance-sync.sh 自身含 presets.py 白名单（abcde_modifier_derive 已退役）
if ! grep -qE "scripts/lib/presets\.py" "$GOVSYNC"; then
  echo "FAIL: dest governance-sync.sh 没含 presets.py 白名单" >&2
  exit 1
fi

# 2. 真跑一次 governance-sync（无破坏：只 cp / mkdir 不删）
bash "$GOVSYNC" --template-root "$TEMPLATE_ROOT" --project-root "$DEST" 2>&1 | tail -5 || {
  echo "FAIL: governance-sync 跑失败" >&2
  exit 1
}

# 3. 验 lib 真下发到 dest/scripts/lib/
missing=0
for lib in presets.py train_branch.py train_branch_types.py adapter_accept.py framework_binding.py auto_mode.py \
  check_env_import_classify.py scenario_contract_guard.py scan_cfg_path_fallback.py \
  scan_shared_context_contract.py \
  migrate_finalize_run_kwargs.py contract_test_signature.py governance_sync_manifest.py \
  governance_sync_manifest.yaml baseline_anchors_status.py home_gpus.py; do
  if [[ ! -f "$DEST/scripts/lib/$lib" ]]; then
    echo "FAIL: dest/scripts/lib/$lib 不存在" >&2
    missing=1
  elif [[ ! -s "$DEST/scripts/lib/$lib" ]]; then
    echo "FAIL: dest/scripts/lib/$lib 0 字节" >&2
    missing=1
  else
    size=$(wc -c < "$DEST/scripts/lib/$lib")
    echo "OK: dest/scripts/lib/$lib ($size bytes)"
  fi
done

# 4. 验 L3-* 2 脚本也下发（init_qa_log_walker 已退役；governance-sync 白名单 — fix commit fd98a76）
for s in check_multi_slot_finalize.py verify_governance_sync_dest.sh; do
  if [[ ! -f "$DEST/scripts/$s" ]]; then
    echo "FAIL: dest/scripts/$s 不存在（governance-sync 漏下 L3 脚本）" >&2
    missing=1
  fi
done

# 5. 验 auto_run_bundle 脚本 refresh-human-guidance-baseline.sh
if [[ ! -f "$DEST/scripts/refresh-human-guidance-baseline.sh" ]]; then
  echo "FAIL: dest/scripts/refresh-human-guidance-baseline.sh 不存在（governance-sync 漏下）" >&2
  missing=1
elif [[ ! -x "$DEST/scripts/refresh-human-guidance-baseline.sh" ]]; then
  echo "FAIL: dest/scripts/refresh-human-guidance-baseline.sh 不可执行（缺 chmod +x）" >&2
  missing=1
else
  size=$(wc -c < "$DEST/scripts/refresh-human-guidance-baseline.sh")
  echo "OK: dest/scripts/refresh-human-guidance-baseline.sh ($size bytes, executable)"
fi

# 6. 验 contract/__main__.py（R3 always cp — python -m contract）
if [[ ! -f "$DEST/contract/__main__.py" ]]; then
  echo "FAIL: dest/contract/__main__.py 不存在（governance-sync 漏下 CLI 壳）" >&2
  missing=1
elif [[ ! -s "$DEST/contract/__main__.py" ]]; then
  echo "FAIL: dest/contract/__main__.py 0 字节" >&2
  missing=1
else
  size=$(wc -c < "$DEST/contract/__main__.py")
  echo "OK: dest/contract/__main__.py ($size bytes)"
fi

if [[ $missing -eq 1 ]]; then
  exit 1
fi

echo "PASS: governance-sync 下发了 presets/train_branch*/adapter_accept/framework_binding/auto_mode/classify/scenario_guard/path_scan/migrate_finalize + refresh + 2 L3 脚本 + contract/__main__"

