"""scripts/info_perm_gate.py：README INFO_PERM 块 ↔ contract/runtime.py INFO_PERM 对账（spec §6）。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_PKG = Path(__file__).resolve().parents[2]
GATE = _PKG / "scripts" / "info_perm_gate.py"
RT = 'INFO_PERM = {"enforce": True, "official_path": "restricted", "official_path_impl": "_x"}\n'
BLOCK = (
    "# 项目\n\n<!-- INFO_PERM -->\nTRAIN_CONSUMES: A 全部\nOFFICIAL_PATH: %s   # 问②\n"
    "OTHER_RULES: 均无\nENFORCE: %s\n<!-- /INFO_PERM -->\n"
)


def _repo(tmp_path: Path, readme: str, rt: str = RT) -> Path:
    r = tmp_path / "r"
    (r / "contract").mkdir(parents=True)
    (r / "contract" / "runtime.py").write_text(rt, encoding="utf-8")
    (r / "README.md").write_text(readme, encoding="utf-8")
    return r


def _run(r: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(GATE), str(r)], capture_output=True, text=True)


def test_gate_script_exists():
    assert GATE.is_file()


def test_missing_block_is_2(tmp_path):
    assert _run(_repo(tmp_path, "# readme\n")).returncode == 2


def test_unfilled_block_is_2(tmp_path):
    readme = "<!-- INFO_PERM -->\nTRAIN_CONSUMES:\nOFFICIAL_PATH:   # 待填\nOTHER_RULES:\nENFORCE:\n<!-- /INFO_PERM -->\n"
    assert _run(_repo(tmp_path, readme)).returncode == 2


def test_consistent_is_0(tmp_path):
    p = _run(_repo(tmp_path, BLOCK % ("B 受限路径", "yes")))
    assert p.returncode == 0, p.stdout


def test_path_mismatch_is_1(tmp_path):
    assert _run(_repo(tmp_path, BLOCK % ("A 整网", "yes"))).returncode == 1


def test_enforce_mismatch_is_1(tmp_path):
    assert _run(_repo(tmp_path, BLOCK % ("B 受限路径", "no"))).returncode == 1


def test_block_without_contract_entry_is_1(tmp_path):
    assert _run(_repo(tmp_path, BLOCK % ("A 整网", "yes"), rt="X = 1\n")).returncode == 1


def test_invalid_contract_is_1(tmp_path):
    assert _run(_repo(tmp_path, BLOCK % ("B 受限", "yes"), rt="INFO_PERM = {'bogus': 1}\n")).returncode == 1


def test_template_readme_block_present_but_unfilled():
    """模板 README 自带空块 → 业务仓 init 前 gate 退 2（WARN），不 FAIL。"""
    assert _run(_PKG).returncode == 2
