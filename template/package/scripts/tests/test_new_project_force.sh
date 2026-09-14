#!/usr/bin/env bash
# T-A4: new-project.sh --force 覆盖但保留 _runs 跑数据
#
# L4 fashionmnist-raw debug 暴露的低危 bug：
# new-project.sh 不可 idempotent 重入（目标已存在就报错），
# 用户的真实跑数据 _runs/ 容易被误删。
#
# 修复（spec T-A4）：
# 加 --force / --reuse-existing 选项，覆盖时用 rsync --exclude=_runs/ 保留
# 用户在目标里现有的 _runs/ 跑数据。

set -euo pipefail

SCRIPTS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE_PKG="$(cd "$SCRIPTS/.." && pwd)"
NEW_PROJECT_SH="$SCRIPTS/new-project.sh"
TMP_BASE="$(mktemp -d -t new-project-force-XXXXXX)"
trap 'rm -rf "$TMP_BASE"' EXIT

echo "=== T-A4: test_new_project_force_preserves_runs"

# === 1. 创建目标 + 假 _runs 跑数据 ===
DEST="$TMP_BASE/dest_proj"
mkdir -p "$DEST"
# 模拟业务仓有 _runs/（里面有 KEEP 跑数据）
mkdir -p "$DEST/_runs/results"
echo "fake_keep_metric 0.95" > "$DEST/_runs/results/results.tsv"
# 模拟业务仓有 .auto-nn 标记（migration done）
mkdir -p "$DEST/.auto-nn"
echo "2026-01-01" > "$DEST/.auto-nn/migration-completed-checklist-test.md"

# === 2. 第一次：目标存在不传 --force 应失败 ===
set +e
output_no_force=$(bash "$NEW_PROJECT_SH" "$DEST" "TestProj" 2>&1)
rc_no_force=$?
set -e
if [[ $rc_no_force -eq 0 ]]; then
    echo "FAIL: 不传 --force 应报错（目标已存在），实际 rc=0"
    echo "$output_no_force"
    exit 1
fi
if ! echo "$output_no_force" | grep -q "目标已存在"; then
    echo "FAIL: 错误信息应提示目标已存在:"
    echo "$output_no_force"
    exit 1
fi
echo "  OK: 不传 --force 正确报错（rc=$rc_no_force）"

# === 3. 第二次：传 --force 应成功 ===
set +e
output_force=$(bash "$NEW_PROJECT_SH" "$DEST" "TestProj" --force 2>&1)
rc_force=$?
set -e
if [[ $rc_force -ne 0 ]]; then
    echo "FAIL: 传 --force 应成功，实际 rc=$rc_force"
    echo "$output_force"
    exit 1
fi
echo "  OK: --force 覆盖成功（rc=$rc_force）"

# === 4. 验证 _runs/results/results.tsv 还在（用户的跑数据） ===
if [[ ! -f "$DEST/_runs/results/results.tsv" ]]; then
    echo "FAIL: --force 覆盖后 _runs/results/results.tsv 被删了（应保留）"
    exit 1
fi
content=$(cat "$DEST/_runs/results/results.tsv")
if [[ "$content" != "fake_keep_metric 0.95" ]]; then
    echo "FAIL: _runs 跑数据内容被改写（应保留）:"
    echo "  got: $content"
    exit 1
fi
echo "  OK: _runs/results/results.tsv 保留，跑数据未丢失"

# === 5. 验证模板文件被覆盖（应有新文件） ===
if [[ ! -f "$DEST/experiment.py" ]]; then
    echo "FAIL: --force 覆盖后 experiment.py 缺失（模板未覆盖）"
    exit 1
fi
if [[ ! -f "$DEST/train.py" ]]; then
    echo "FAIL: --force 覆盖后 train.py 缺失（模板未覆盖）"
    exit 1
fi
echo "  OK: experiment.py / train.py 模板文件已覆盖"

# === 6. 验证 .auto-nn/migration-completed-checklist-*.md 还在 ===
if ! ls "$DEST"/.auto-nn/migration-completed-checklist-*.md &>/dev/null; then
    echo "FAIL: .auto-nn/migration-completed-checklist-*.md 缺失"
    exit 1
fi
echo "  OK: .auto-nn/ 兜底标记保留"

# === 7. --force 不需要重复传（idempotent） ===
set +e
output_force2=$(bash "$NEW_PROJECT_SH" "$DEST" "TestProj" --force 2>&1)
rc_force2=$?
set -e
if [[ $rc_force2 -ne 0 ]]; then
    echo "FAIL: 第二次 --force 应 idempotent 成功，实际 rc=$rc_force2"
    echo "$output_force2"
    exit 1
fi
echo "  OK: --force 二次调用 idempotent（rc=$rc_force2）"

echo "=== T-A4: ALL PASS"
exit 0
