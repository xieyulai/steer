"""init_info_perm.py write/show：三问 → INFO_PERM 字面量 + README 块，写后 info_perm_gate 对账（spec 20260905_1845 §2.3）。"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
PKG = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from lib.info_perm import load_info_perm  # noqa: E402

WRITE = SCRIPTS / "init_info_perm.py"
ANSWERS = SCRIPTS / "init_answers.py"
GATE = SCRIPTS / "info_perm_gate.py"


def _run(script: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "biz"
    (root / "contract").mkdir(parents=True)
    shutil.copy(PKG / "contract" / "runtime.py", root / "contract" / "runtime.py")
    shutil.copy(PKG / "README.md", root / "README.md")
    return root


def test_csi_write_then_gate_ok_and_idempotent(repo: Path):
    args = [
        "write", "--repo-root", str(repo),
        "--consumes", "B", "--eval-only-assets", "data/data_real.npy",
        "--eval-only-readers", "contract/test.py", "--eval-only-readers", "contract/prepare_data.py",
        "--official-path", "B", "--official-path-impl", "_reconstruct",
        "--official-path-rule", "先压成 ≤64 bit 码，再只凭码还原",
        "--other-rules", "均无",
    ]
    r = _run(WRITE, *args)
    assert r.returncode == 0, r.stdout + r.stderr
    perm = load_info_perm(repo)
    assert perm is not None
    assert perm.enforce is True and perm.official_path == "restricted" and perm.official_path_impl == "_reconstruct"
    assert perm.eval_only_assets == ("data/data_real.npy",)
    assert perm.eval_only_readers == ("contract/test.py", "contract/prepare_data.py")
    assert perm.train_batch_keys is None and perm.strict_no_train_files is False
    assert _run(GATE, str(repo)).returncode == 0
    md = (repo / "README.md").read_text(encoding="utf-8")
    assert md.count("<!-- INFO_PERM -->") == 1
    assert "TRAIN_CONSUMES: B 只有训练份；只评：data/data_real.npy（读者：contract/test.py, contract/prepare_data.py）" in md
    assert "OFFICIAL_PATH: B 受限路径（_reconstruct）：先压成 ≤64 bit 码，再只凭码还原" in md
    assert "OTHER_RULES: 均无" in md and "ENFORCE: yes" in md
    # 幂等：再写一次内容不变
    before = (repo / "contract" / "runtime.py").read_text(encoding="utf-8"), md
    assert _run(WRITE, *args).returncode == 0
    after = (repo / "contract" / "runtime.py").read_text(encoding="utf-8"), (repo / "README.md").read_text(encoding="utf-8")
    assert before == after
    # 只替换字面量，文件头等其余内容未被碰
    assert after[0].startswith('"""契约运行时常量') and after[0].count("INFO_PERM = {") == 1


def test_pinn_strict_and_batch_keys(repo: Path):
    r = _run(WRITE, "write", "--repo-root", str(repo), "--consumes", "C",
             "--eval-only-assets", "contract.test.run_ssfm", "--official-path", "A",
             "--other-rules", "训练只见初始脉冲与方程；参考场只在打分时现算",
             "--train-batch-keys", "z", "--train-batch-keys", "t")
    assert r.returncode == 0, r.stdout + r.stderr
    perm = load_info_perm(repo)
    assert perm.strict_no_train_files is True and perm.official_path == "full_model" and perm.official_path_impl is None
    assert perm.eval_only_assets == ("contract.test.run_ssfm",) and perm.train_batch_keys == ("z", "t")
    md = (repo / "README.md").read_text(encoding="utf-8")
    assert "TRAIN_CONSUMES: C 无数据文件（样本由代码生成）；只评：contract.test.run_ssfm（读者：contract/test.py）" in md
    assert "OTHER_RULES: 训练只见初始脉冲与方程；参考场只在打分时现算（机器管：训练 batch 键 z,t）" in md
    assert _run(GATE, str(repo)).returncode == 0
    r2 = _run(WRITE, "show", "--repo-root", str(repo))
    assert r2.returncode == 0 and "strict_no_train_files    True" in r2.stdout and "<!-- INFO_PERM -->" in r2.stdout


def test_from_resolved_chain(repo: Path, tmp_path: Path):
    ans = tmp_path / "pinn.yaml"
    ans.write_text(
        "version: 1\nanswers:\n  训练许用材料: {choice: C, eval_only_assets: [contract.test.run_ssfm]}\n"
        "  官方打分通道: A\n  其他信息规矩: none\n  实验模式: B\n", encoding="utf-8")
    r = _run(ANSWERS, "validate", "--answers", str(ans), "--workflow", "build", "--repo-root", str(repo), "--write-resolved")
    assert r.returncode == 0, r.stdout + r.stderr
    resolved = repo / ".auto-nn" / "init-answers.resolved.json"
    assert json.loads(resolved.read_text(encoding="utf-8"))["info_perm_flags"]
    r2 = _run(WRITE, "write", "--repo-root", str(repo), "--from-resolved", str(resolved))
    assert r2.returncode == 0, r2.stdout + r2.stderr
    perm = load_info_perm(repo)
    assert perm.strict_no_train_files is True and perm.eval_only_assets == ("contract.test.run_ssfm",)
    assert perm.enforce is True
    assert _run(GATE, str(repo)).returncode == 0


def test_enforce_no_rejects_consumes_c(repo: Path):
    r = _run(WRITE, "write", "--repo-root", str(repo), "--consumes", "C",
             "--eval-only-assets", "data/x.mat", "--enforce", "no")
    assert r.returncode == 2 and "C-DL1" in r.stderr


def test_enforce_no_with_consumes_a(repo: Path):
    r = _run(WRITE, "write", "--repo-root", str(repo), "--consumes", "A", "--enforce", "no")
    assert r.returncode == 0, r.stdout + r.stderr
    perm = load_info_perm(repo)
    assert perm is not None and perm.enforce is False and perm.strict_no_train_files is False
    md = (repo / "README.md").read_text(encoding="utf-8")
    assert "ENFORCE: no" in md


def test_validation_errors_and_guards(repo: Path):
    assert _run(WRITE, "write", "--repo-root", str(repo), "--consumes", "B").returncode == 2          # 缺资产
    assert _run(WRITE, "write", "--repo-root", str(repo), "--official-path", "B").returncode == 2     # 缺 impl
    assert _run(WRITE, "write", "--repo-root", str(repo), "--official-path", "B",
                "--official-path-impl", "bad-name").returncode == 2
    r = _run(WRITE, "write", "--repo-root", str(PKG), "--consumes", "A")
    assert r.returncode == 2 and "template/package" in r.stderr
    # dry-run 不写
    before = (repo / "contract" / "runtime.py").read_text(encoding="utf-8")
    r2 = _run(WRITE, "write", "--repo-root", str(repo), "--consumes", "A", "--dry-run")
    assert r2.returncode == 0 and "dry-run" in r2.stdout
    assert (repo / "contract" / "runtime.py").read_text(encoding="utf-8") == before


def test_runtime_without_info_perm_literal_gets_appended(repo: Path):
    """存量业务仓（迁入早于 INFO_PERM）：write 追加字面量到 runtime.py 末尾并仍对账通过。"""
    rt = repo / "contract" / "runtime.py"
    text = rt.read_text(encoding="utf-8")
    start = text.index("INFO_PERM = {")
    end = text.index("\n}\n", start) + 3
    rt.write_text(text[:start] + text[end:], encoding="utf-8")
    assert load_info_perm(repo) is None
    r = _run(WRITE, "write", "--repo-root", str(repo), "--consumes", "A")
    assert r.returncode == 0 and "已追加" in r.stdout, r.stdout + r.stderr
    perm = load_info_perm(repo)
    assert perm is not None and perm.official_path == "full_model"
    assert rt.read_text(encoding="utf-8").count("INFO_PERM = {") == 1
    assert _run(GATE, str(repo)).returncode == 0


def test_readme_without_block_gets_section(repo: Path):
    md = repo / "README.md"
    text = md.read_text(encoding="utf-8")
    s = text.index("### 3.2b")
    e = text.index("### 3.3", s)
    md.write_text(text[:s] + text[e:], encoding="utf-8")
    assert _run(WRITE, "write", "--repo-root", str(repo), "--consumes", "A").returncode == 0
    new = md.read_text(encoding="utf-8")
    assert new.count("<!-- INFO_PERM -->") == 1 and "### 3.2b 信息权限" in new
    assert _run(GATE, str(repo)).returncode == 0
