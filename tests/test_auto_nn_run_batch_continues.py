"""AE-2 auto-nn-run.sh batch 早退根治回归测试。

原 bug：`auto-nn-run.sh N` (N>1) 跑 1 轮后 exit 0，剩 N-1 轮不跑。
根因（推测）：claude 退出时关闭 stdio + pipefail 触发 set -e 退出。
修法（AE-2）：在 batch 循环体内 `set +e`，每轮失败累计 `_round_failed`，
循环结束后再决定是否退出。
"""
import subprocess
from pathlib import Path


def _run_batch_mock(tmp_path: Path, *, round1_exit_code: int) -> subprocess.CompletedProcess:
    """运行一个模拟 batch 循环的 bash 脚本（AE-2 修复前后对比）。

    第 1 轮命令以指定 exit code 退出（0 = 成功，非 0 = 失败）。
    """
    batch_sh = tmp_path / "mock_batch.sh"
    batch_sh.write_text(
        f"""#!/usr/bin/env bash
# AE-2 修复后结构（auto-nn-run.sh 当前实现）
TOTAL_RUNS=3
_round_failed=0
set +e  # AE-2 关键：循环体内禁用 set -e
for ((run=1; run<=TOTAL_RUNS; run++)); do
    if [ "$run" -eq 1 ]; then
        # 模拟 round 1 命令（claude 调用）
        ( exit {round1_exit_code} )
        _round1_rc=$?
    else
        _round1_rc=0
    fi
    if [ "$_round1_rc" -ne 0 ]; then
        _round_failed=$((_round_failed + 1))
    fi
    echo "round $run rc=$_round1_rc"
done
set -e  # 循环外恢复
echo "ALL_DONE _round_failed=$_round_failed"
"""
    )
    batch_sh.chmod(0o755)

    return subprocess.run(
        ["bash", str(batch_sh)],
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_batch_with_set_e_exits_early(tmp_path: Path):
    """对照：bug 行为（set -e 在循环内）。round 1 失败 → 整体退出，round 2/3 不跑。"""
    buggy_sh = tmp_path / "buggy_batch.sh"
    buggy_sh.write_text(
        """#!/usr/bin/env bash
# 修复前行为（buggy）
set -e
TOTAL_RUNS=3
for ((run=1; run<=TOTAL_RUNS; run++)); do
    if [ "$run" -eq 1 ]; then
        false  # round 1 直接失败（不是子 shell，set -e 会触发退出）
    fi
    echo "round $run ran"
done
echo "ALL_DONE"
"""
    )
    buggy_sh.chmod(0o755)

    result = subprocess.run(
        ["bash", str(buggy_sh)],
        capture_output=True,
        text=True,
        timeout=10,
    )

    # 验证 buggy 行为：set -e + 失败 → 整体退出，round 2/3 不跑
    assert "round 1 ran" not in result.stdout, (
        f"buggy 模式下 round 1 应该不让 echo 执行（false 触发 set -e 退出）。stdout={result.stdout!r}"
    )
    assert "round 2 ran" not in result.stdout, (
        f"buggy 模式不会跑 round 2。stdout={result.stdout!r}"
    )
    assert "ALL_DONE" not in result.stdout, (
        f"buggy 模式不会到 ALL_DONE。stdout={result.stdout!r}"
    )
    assert result.returncode != 0, "buggy 模式应该非 0 退出"


def test_batch_with_set_plus_e_continues(tmp_path: Path):
    """AE-2 修复：set +e 在循环内 → round 1 失败但 round 2/3 继续。"""
    result = _run_batch_mock(tmp_path, round1_exit_code=1)

    assert "round 1 rc=1" in result.stdout, (
        f"round 1 应该 rc=1。stdout={result.stdout!r}"
    )
    assert "round 2 rc=0" in result.stdout, (
        f"round 2 应该继续跑（rc=0）。stdout={result.stdout!r}"
    )
    assert "round 3 rc=0" in result.stdout, (
        f"round 3 应该继续跑。stdout={result.stdout!r}"
    )
    assert "ALL_DONE _round_failed=1" in result.stdout, (
        f"应该跑完所有轮 + 记录 _round_failed=1。stdout={result.stdout!r}"
    )
    assert result.returncode == 0, (
        f"修复后 batch 应该返回 0（已完成所有轮）。rc={result.returncode}, stderr={result.stderr!r}"
    )


def test_batch_all_rounds_ok(tmp_path: Path):
    """所有轮成功时，_round_failed 应是 0，batch 跑完所有轮。"""
    result = _run_batch_mock(tmp_path, round1_exit_code=0)

    assert "round 1 rc=0" in result.stdout
    assert "round 2 rc=0" in result.stdout
    assert "round 3 rc=0" in result.stdout
    assert "_round_failed=0" in result.stdout
    assert result.returncode == 0


def test_real_auto_nn_run_batch_syntax():
    """auto-nn-run.sh bash 语法 + AE-2 修复结构验证。"""
    script = (
        Path(__file__).parent.parent
        / "template" / "package" / "auto-nn-run.sh"
    )
    assert script.exists(), f"auto-nn-run.sh not found: {script}"

    # bash 语法检查
    syntax = subprocess.run(
        ["bash", "-n", str(script)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert syntax.returncode == 0, (
        f"auto-nn-run.sh bash 语法错：{syntax.stderr!r}"
    )

    content = script.read_text(encoding="utf-8")

    # AE-2 修复特征存在
    assert "AE-2 batch 早退根治" in content, "AE-2 注释缺失"
    assert "_round_failed=0" in content, "_round_failed 初始化缺失"
    assert "set +e  # batch 循环体内禁用 set -e" in content, (
        "batch 循环前 set +e 缺失"
    )
    assert "set -e  # batch 循环外恢复 set -e" in content, (
        "batch 循环后 set -e 恢复缺失"
    )

    # for 循环在 set +e 之后、set -e 之前
    set_plus_e_pos = content.index("set +e  # batch 循环体内禁用 set -e")
    for_pos = content.index("for ((run=1; run<=TOTAL_RUNS; run++))", set_plus_e_pos)
    set_minus_e_pos = content.index("set -e  # batch 循环外恢复 set -e", for_pos)
    assert set_plus_e_pos < for_pos < set_minus_e_pos, (
        "set +e ... for ... set -e 顺序错"
    )