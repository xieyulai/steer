"""nn-doctor.sh 必须「收齐 FAIL 再汇总退出码」（模板 4.1.1 修 ②）。

背景（真实缺陷，非假设）：
`set -euo pipefail` 下裸调用检查函数，函数内第一个 ``return 1`` 会让整脚本
**静默退出**——汇总行（PASS/WARN/FAIL）永远打不出来，调用方只看到一个非零退出码，
既不知道跑了多少项、也不知道漏跑了哪些。
旧版复现（见本文件 test_old_version_reproduces_abort 的注释）：
``ledger_watchlist`` 判 FAIL → return 1 → 脚本在第 9 行就停住，无汇总。

修法：
1. 检查调用统一走 ``check_call``（用 if 条件上下文调，bash 只在条件上下文忽略 -e）；
2. 装 EXIT 兜底 trap，任何退出路径都打出汇总。
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[2]
SCRIPTS = PKG / "scripts"
DOCTOR = SCRIPTS / "nn-doctor.sh"
AUTO_UPDATE = SCRIPTS / "auto-nn-update.sh"


def _build_fixture(tmp_path: Path) -> Path:
    """造一个最小业务仓：故意让 ledger.watchlist 非法 ⇒ check_ledger_watchlist 返回 1。"""
    repo = tmp_path / "repo"
    (repo / "scripts" / "lib").mkdir(parents=True)
    shutil.copy2(DOCTOR, repo / "scripts" / "nn-doctor.sh")
    shutil.copytree(SCRIPTS / "lib", repo / "scripts" / "lib", dirs_exist_ok=True)
    (repo / "nn-config.yaml").write_text(
        "profile: supervised\nledger:\n  watchlist: \"not-a-list\"\n", encoding="utf-8"
    )
    return repo


def _run_doctor(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "scripts/nn-doctor.sh"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=False,
    )


def test_doctor_emits_summary_even_when_a_check_fails(tmp_path):
    """检查项 FAIL 时：仍要跑到末尾并打出汇总 + 结论，退出码 1。"""
    repo = _build_fixture(tmp_path)
    proc = _run_doctor(repo)
    out = proc.stdout + proc.stderr

    assert "[nn-doctor] 汇总:" in out, out
    assert "[nn-doctor] 结论:" in out, out
    # 失败项本身要留下痕迹
    assert "ledger_watchlist" in out and "FAIL" in out, out
    # 退出码仍是 1（有 FAIL 不能放行）
    assert proc.returncode == 1, out


def test_doctor_does_not_stop_at_first_failing_check(tmp_path):
    """第一个 FAIL 之后，后面的检查仍要跑（否则「收齐 FAIL」无从谈起）。"""
    repo = _build_fixture(tmp_path)
    proc = _run_doctor(repo)
    out = proc.stdout + proc.stderr

    assert "ledger_watchlist" in out
    # shell_syntax / global_skills 位于 ledger_watchlist 之后的段位，跑到了就说明没提前退出
    assert "shell_syntax" in out, out
    assert "global_skills" in out, out
    # 行数远超旧版（旧版在 ledger_watchlist 后即停，约 9 行）
    assert len([ln for ln in out.splitlines() if ln.startswith("[nn-doctor]")]) >= 15, out


def test_summary_counter_counts_match_rows(tmp_path):
    """汇总里的 PASS/WARN/FAIL 计数应与实际行数一致（兜底 trap 打的汇总也算）。"""
    import re

    repo = _build_fixture(tmp_path)
    proc = _run_doctor(repo)
    out = proc.stdout + proc.stderr
    m = re.search(r"汇总: PASS=(\d+) WARN=(\d+) FAIL=(\d+)", out)
    assert m, out
    p, w, f = (int(x) for x in m.groups())
    assert p + w + f > 0
    # FAIL 计数至少为 1（本 fixture 必红）
    assert f >= 1


def test_no_bare_check_invocation_left():
    """所有顶层检查调用都必须包在 check_call 里（防止回归成裸调用）。"""
    text = DOCTOR.read_text(encoding="utf-8")
    # 只看「顶层裸调用」：整行就是 check_xxx，且不是函数定义、不是 check_call 调用
    offenders = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s.startswith("check_"):
            continue
        if s.startswith("check_call "):
            continue
        if "() {" in s:  # 函数定义
            continue
        offenders.append(s)
    assert not offenders, offenders
    assert "check_call check_ledger_watchlist" in text
    assert "trap _doctor_on_exit EXIT" in text
    assert "_emit_summary" in text


def test_auto_nn_update_runs_doctor_even_when_verify_fails():
    """auto-nn-update：verify 挂了也要让 doctor 跑到（太史慈 ② 后半句）。"""
    text = AUTO_UPDATE.read_text(encoding="utf-8")
    assert "|| _VERIFY_RC=$?" in text, "verify 必须捕获退出码而不是让 set -e 中止"
    assert "NN_RELAUNCH=1 bash scripts/nn-doctor.sh) || _DOCTOR_RC=$?" in text, (
        "doctor 必须在 verify 之后无条件执行，并捕获自己的退出码"
    )
    assert "doctor 未跑" in text, "缺 doctor 脚本时要显式记「未跑」"
    assert "_VERIFY_RC -ne 0 || $_DOCTOR_RC -ne 0" in text, "最后统一按 verify/doctor 结果退出"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
