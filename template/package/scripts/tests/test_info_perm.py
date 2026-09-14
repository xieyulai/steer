"""scripts/lib/info_perm.py 单测（不依赖 torch；spec 20260905_1755）。

fixture 只模仿两类锁的形状：PINN 形（只评文件 / 严格档）与 CSI 形（受限交卷路径 / 开关字面量）。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_PKG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PKG / "scripts"))
from lib.info_perm import (  # noqa: E402
    InfoPermError,
    check_info_perm,
    check_train_batch_keys,
    collect_guard_bypasses,
    inventory_eval_only_literals,
    load_info_perm,
)


def _repo(
    tmp_path: Path,
    runtime: str,
    test_py: str = "",
    ws: dict[str, str] | None = None,
    train_py: str = "",
) -> Path:
    r = tmp_path / "r"
    (r / "contract").mkdir(parents=True)
    (r / "workspace").mkdir()
    (r / "contract" / "__init__.py").write_text("", encoding="utf-8")
    (r / "contract" / "runtime.py").write_text(runtime, encoding="utf-8")
    (r / "contract" / "test.py").write_text(test_py, encoding="utf-8")
    (r / "workspace" / "__init__.py").write_text("", encoding="utf-8")
    for name, src in (ws or {}).items():
        (r / "workspace" / name).write_text(src, encoding="utf-8")
    (r / "train.py").write_text(train_py, encoding="utf-8")
    return r


PINN_RT = '''
INFO_PERM = {
    "enforce": True,
    "official_path": "full_model",
    "official_path_impl": None,
    "eval_only_assets": ("data/**/*.mat",),
    "eval_only_readers": ("contract/test.py",),
    "train_batch_keys": None,
    "strict_no_train_files": %s,
}
'''

CSI_RT = '''
INFO_PERM = {
    "enforce": True,
    "official_path": "restricted",
    "official_path_impl": "_reconstruct",
    "official_path_switch": "_switch",
    "eval_only_assets": ("data/**/data_real.npy",),
    "eval_only_readers": ("contract/test.py",),
    "train_batch_keys": ("x", "y"),
    "strict_no_train_files": False,
}
'''


# ── 登记表读取（IP0）──────────────────────────────────────────────

def test_not_declared_is_noop(tmp_path):
    r = _repo(tmp_path, "DEFAULT_DATA_DIR = 'data'\n", ws={"m.py": "import numpy as np\nnp.load('data/x.npy')\n"})
    assert load_info_perm(r) is None
    assert check_info_perm(r) == []


def test_non_literal_raises_ip0(tmp_path):
    r = _repo(tmp_path, "import os\nINFO_PERM = {'enforce': os.environ.get('X') == '1'}\n")
    with pytest.raises(InfoPermError, match="字面量"):
        load_info_perm(r)


def test_unknown_key_raises(tmp_path):
    r = _repo(tmp_path, "INFO_PERM = {'enforce': True, 'bogus': 1}\n")
    with pytest.raises(InfoPermError, match="未知键"):
        load_info_perm(r)


def test_restricted_requires_impl(tmp_path):
    r = _repo(tmp_path, "INFO_PERM = {'official_path': 'restricted'}\n")
    with pytest.raises(InfoPermError, match="official_path_impl"):
        load_info_perm(r)


def test_defaults_filled(tmp_path):
    perm = load_info_perm(_repo(tmp_path, "INFO_PERM = {}\n"))
    assert perm is not None
    assert perm.enforce is True and perm.official_path == "full_model"
    assert perm.official_path_switch == "_official_path_enabled"
    assert perm.eval_only_readers == ("contract/test.py",)


# ── PINN 形：只评文件（IP1）/ 读者豁免 / enforce=False / 严格档（IP3）──

def test_pinn_workspace_opens_eval_only_asset_ip1(tmp_path):
    ws = {"train_loop.py": 'from scipy.io import loadmat\nfield = loadmat("data/ssfm/field_ref.mat")\n'}
    r = _repo(tmp_path, PINN_RT % "False", ws=ws)
    assert check_info_perm(r) == []
    vs = inventory_eval_only_literals(r)
    assert [v.rule for v in vs] == ["IP1"]
    assert vs[0].path == "workspace/train_loop.py" and vs[0].line == 2


@pytest.mark.parametrize(
    "literal",
    ["data/a.mat", "data/ssfm/deep/x.mat", "/abs/path/data/a.mat", "field_ref.mat", "a.mat"],
)
def test_globstar_matches_zero_or_more_dirs(tmp_path, literal):
    r = _repo(tmp_path, PINN_RT % "False", ws={"m.py": f'P = "{literal}"\n'})
    assert check_info_perm(r) == []
    assert [v.rule for v in inventory_eval_only_literals(r)] == ["IP1"], literal


def test_non_matching_literals_pass(tmp_path):
    ws = {"m.py": 'A = "data/a.npz"\nB = "ckpt/best.pt"\nC = "mat"\nD = "other/dir/a.mat.bak"\n'}
    r = _repo(tmp_path, PINN_RT % "False", ws=ws)
    assert check_info_perm(r) == []


def test_train_py_is_scanned_too(tmp_path):
    r = _repo(tmp_path, PINN_RT % "False", train_py='P = "data/ssfm/field_ref.mat"\n')
    assert check_info_perm(r) == []
    assert [(v.rule, v.path) for v in inventory_eval_only_literals(r)] == [("IP1", "train.py")]


def test_reader_exempt_and_docstring_ignored(tmp_path):
    test_py = 'from scipy.io import loadmat\ndef run(learner, ws, *, shared_context):\n    return loadmat("data/ssfm/field_ref.mat")\n'
    ws = {"m.py": '"""这里提到 data/ssfm/field_ref.mat 只是文档。"""\nX = 1\n'}
    r = _repo(tmp_path, PINN_RT % "False", test_py=test_py, ws=ws)
    assert check_info_perm(r) == []


def test_enforce_false_is_noop(tmp_path):
    rt = PINN_RT.replace('"enforce": True', '"enforce": False') % "True"
    ws = {"m.py": 'from scipy.io import loadmat\nloadmat("data/ssfm/field_ref.mat")\n'}
    r = _repo(tmp_path, rt, ws=ws)
    assert check_info_perm(r) == []


def test_strict_flags_any_data_read_ip3(tmp_path):
    ws = {
        "m.py": (
            "import numpy as np\nimport h5py\n"
            "a = np.load('data/other.npz')\n"
            "f = h5py.File('data/x.h5')\n"
            "g = open('data/x.bin', 'rb')\n"
            "w = open('log.txt', 'w')\n"
            "t = torch.load('ckpt.pt')\n"
        )
    }
    r = _repo(tmp_path, PINN_RT % "True", ws=ws)
    assert check_info_perm(r) == []
    vs = inventory_eval_only_literals(r)
    assert [v.rule for v in vs] == ["IP3", "IP3", "IP3"]
    assert [v.line for v in vs] == [3, 4, 5]


# ── 点名读取函数（IP2）────────────────────────────────────────────

def test_callable_asset_ip2(tmp_path):
    rt = PINN_RT.replace('("data/**/*.mat",)', '("contract.test.get_test_loader",)') % "False"
    ws = {
        "a.py": "from contract.test import get_test_loader\n",
        "b.py": "from contract import test\nloader = test.get_test_loader()\n",
        "c.py": "import contract.test\nloader = contract.test.get_test_loader()\n",
        "d.py": "def get_test_loader():\n    return 1\n",
    }
    r = _repo(tmp_path, rt, ws=ws)
    assert check_info_perm(r) == []
    vs = inventory_eval_only_literals(r)
    assert sorted(v.path for v in vs) == ["workspace/a.py", "workspace/b.py", "workspace/c.py"]
    assert all(v.rule == "IP2" for v in vs)


# ── CSI 形：受限交卷路径（IP4）/ 开关字面量（IP5）─────────────────

CSI_TEST_OK = '''
def _switch():
    return True


def _reconstruct(learner, data):
    codes = learner.encode(data)
    if codes is None:
        return None
    return learner.decode(codes)


def run(learner, ws, *, shared_context):
    for data in []:
        pred = _reconstruct(learner, data) if _switch() else ws.predict(learner, data)
    return {}
'''


def test_csi_restricted_ok(tmp_path):
    r = _repo(tmp_path, CSI_RT, test_py=CSI_TEST_OK)
    assert check_info_perm(r) == []


def test_csi_run_without_impl_ip4(tmp_path):
    bad = CSI_TEST_OK.replace("_reconstruct(learner, data) if _switch() else ", "")
    r = _repo(tmp_path, CSI_RT, test_py=bad)
    vs = check_info_perm(r)
    assert [v.rule for v in vs] == ["IP4"]
    assert "run() 未调用" in vs[0].detail


def test_csi_trivial_impl_ip4(tmp_path):
    bad = CSI_TEST_OK.replace(
        "    codes = learner.encode(data)\n    if codes is None:\n        return None\n    return learner.decode(codes)\n",
        "    return None\n",
    )
    r = _repo(tmp_path, CSI_RT, test_py=bad)
    assert [v.rule for v in check_info_perm(r)] == ["IP4"]


def test_csi_switch_reads_env_ip5(tmp_path):
    bad = CSI_TEST_OK.replace(
        "def _switch():\n    return True",
        "import os\ndef _switch():\n    return os.environ.get('NN_PREFLIGHT') == '1'",
    )
    r = _repo(tmp_path, CSI_RT, test_py=bad)
    assert [v.rule for v in check_info_perm(r)] == ["IP5"]


def test_switch_absent_is_not_checked(tmp_path):
    ok = CSI_TEST_OK.replace("def _switch():\n    return True\n", "").replace(" if _switch() else ws.predict(learner, data)", "")
    r = _repo(tmp_path, CSI_RT, test_py=ok)
    assert check_info_perm(r) == []


# ── 旁路留痕 / 首 batch 键 ────────────────────────────────────────

def test_collect_guard_bypasses():
    env = {"NN_PREFLIGHT": "0", "NN_GUARD_TEST_AUTHORITY": "off", "NN_GUARD_X": "1", "NN_DEVICE": "cpu", "NN_GUARD": "false"}
    assert collect_guard_bypasses(env) == ["NN_GUARD=false", "NN_GUARD_TEST_AUTHORITY=off", "NN_PREFLIGHT=0"]
    assert collect_guard_bypasses({"NN_PREFLIGHT": "1"}) == []


def test_check_train_batch_keys():
    assert check_train_batch_keys({"x": 1, "y": 2}, ("x", "y")) == []
    bad = check_train_batch_keys({"x": 1, "ref": 2}, ("x", "y"))
    assert bad and "ref" in bad[0]
    assert check_train_batch_keys((1, 2, 3), ("x", "y")) != []
    assert check_train_batch_keys((1, 2), ("x", "y")) == []
    assert check_train_batch_keys({"anything": 1}, None) == []
    assert check_train_batch_keys(None, ("x",)) == []


# ── CLI ───────────────────────────────────────────────────────────

def test_cli_exit_codes(tmp_path):
    cli = _PKG / "scripts" / "lib" / "info_perm.py"
    ws = {"m.py": 'from scipy.io import loadmat\nloadmat("data/ssfm/field_ref.mat")\n'}
    r = _repo(tmp_path, PINN_RT % "False", ws=ws)
    p = subprocess.run([sys.executable, str(cli), str(r)], capture_output=True, text=True)
    assert p.returncode == 0
    r2 = _repo(tmp_path / "ok", PINN_RT % "False")
    assert subprocess.run([sys.executable, str(cli), str(r2)], capture_output=True).returncode == 0
    r3 = _repo(tmp_path / "ip0", "import os\nINFO_PERM = {'enforce': bool(os.environ.get('X'))}\n")
    p3 = subprocess.run([sys.executable, str(cli), str(r3)], capture_output=True, text=True)
    assert p3.returncode == 1 and "IP0" in p3.stdout + p3.stderr
