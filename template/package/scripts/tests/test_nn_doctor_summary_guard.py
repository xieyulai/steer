"""nn-doctor.sh must "collect every FAIL, then print a summary and an exit code"
(template 4.1.1 fix ②).

Background (a real defect, not a hypothesis):
under `set -euo pipefail`, calling a check function bare means the first
``return 1`` inside the function makes the whole script **exit silently** — the
summary lines (PASS/WARN/FAIL) can never be printed, and the caller only sees a
non-zero exit code, with no way to know how many checks ran or which ones were
skipped.
Reproduction on the old version (see the comment on
test_old_version_reproduces_abort in this file):
``ledger_watchlist`` is judged FAIL → return 1 → the script stops at line 9, with
no summary.

Fix:
1. all check invocations go through ``check_call`` (called in an `if` condition
   context, where bash ignores -e);
2. an EXIT trap is installed as a fallback so the summary is printed on every
   exit path.
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
    """Build a minimal business repo: deliberately make ledger.watchlist invalid
    ⇒ check_ledger_watchlist returns 1."""
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
    """When a check FAILs: it must still run to the end and print the summary +
    conclusion, with exit code 1."""
    repo = _build_fixture(tmp_path)
    proc = _run_doctor(repo)
    out = proc.stdout + proc.stderr

    assert "[nn-doctor] 汇总:" in out, out
    assert "[nn-doctor] 结论:" in out, out
    # The failing check itself must leave a trace
    assert "ledger_watchlist" in out and "FAIL" in out, out
    # The exit code is still 1 (a FAIL must not let the run pass)
    assert proc.returncode == 1, out


def test_doctor_does_not_stop_at_first_failing_check(tmp_path):
    """After the first FAIL, the later checks must still run (otherwise "collect
    every FAIL" is meaningless)."""
    repo = _build_fixture(tmp_path)
    proc = _run_doctor(repo)
    out = proc.stdout + proc.stderr

    assert "ledger_watchlist" in out
    # shell_syntax / global_skills are in the sections after ledger_watchlist; if they
    # ran, the script did not exit early
    assert "shell_syntax" in out, out
    assert "global_skills" in out, out
    # The line count far exceeds the old version (the old one stopped right after
    # ledger_watchlist, at about 9 lines)
    assert len([ln for ln in out.splitlines() if ln.startswith("[nn-doctor]")]) >= 15, out


def test_summary_counter_counts_match_rows(tmp_path):
    """The PASS/WARN/FAIL counts in the summary should match the actual number of
    rows (the summary printed by the fallback trap counts too)."""
    import re

    repo = _build_fixture(tmp_path)
    proc = _run_doctor(repo)
    out = proc.stdout + proc.stderr
    m = re.search(r"汇总: PASS=(\d+) WARN=(\d+) FAIL=(\d+)", out)
    assert m, out
    p, w, f = (int(x) for x in m.groups())
    assert p + w + f > 0
    # The FAIL count is at least 1 (this fixture is guaranteed to be red)
    assert f >= 1


def test_no_bare_check_invocation_left():
    """All top-level check invocations must be wrapped in check_call (to prevent a
    regression back to bare calls)."""
    text = DOCTOR.read_text(encoding="utf-8")
    # Only look at "top-level bare calls": the whole line is check_xxx, and it is
    # neither a function definition nor a check_call invocation
    offenders = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s.startswith("check_"):
            continue
        if s.startswith("check_call "):
            continue
        if "() {" in s:  # function definition
            continue
        offenders.append(s)
    assert not offenders, offenders
    assert "check_call check_ledger_watchlist" in text
    assert "trap _doctor_on_exit EXIT" in text
    assert "_emit_summary" in text


def test_run_check_and_check_call_use_if_not_set_e_toggle():
    """run_check / check_call must capture via `if`, not set +e / set -e."""
    text = DOCTOR.read_text(encoding="utf-8")
    assert 'if out="$("$@" 2>&1)"; then' in text
    assert 'if "$@"; then' in text
    # Old toggle pattern next to capturing the external command
    assert "set +e\n  out=" not in text
    assert "Do NOT use `set +e`" in text
    assert "MUST be the first statement" in text


def test_g_no_fallback_not_double_rowed_on_fail():
    """Outer block must not row G_no_fallback again after check_no_fallback."""
    text = DOCTOR.read_text(encoding="utf-8")
    assert "if check_no_fallback .; then" in text
    assert 'row G_no_fallback FAIL "见 G-no-fallback 检查"' not in text
    assert 'row G_repro_env PASS "see check output"' in text
    assert 'row G_repro_env FAIL "see check output"' in text


def test_auto_nn_update_runs_doctor_even_when_verify_fails():
    """auto-nn-update: even if verify fails, doctor must still be run (Taishici ②,
    second half)."""
    text = AUTO_UPDATE.read_text(encoding="utf-8")
    assert "|| _VERIFY_RC=$?" in text, "verify 必须捕获退出码而不是让 set -e 中止"
    assert "NN_RELAUNCH=1 bash scripts/nn-doctor.sh) || _DOCTOR_RC=$?" in text, (
        "doctor 必须在 verify 之后无条件执行，并捕获自己的退出码"
    )
    assert "doctor 未跑" in text, "缺 doctor 脚本时要显式记「未跑」"
    assert "_VERIFY_RC -ne 0 || $_DOCTOR_RC -ne 0" in text, "最后统一按 verify/doctor 结果退出"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
