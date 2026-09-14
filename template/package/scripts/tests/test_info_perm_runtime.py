"""只评材料运行时门禁（spec 20260907_0945）：真用才拦，未调用不 FAIL。"""
from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

_PKG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PKG / "scripts"))
from lib.info_perm import (  # noqa: E402
    check_info_perm,
    install_eval_only_runtime_guard,
    inventory_eval_only_literals,
    uninstall_eval_only_runtime_guard,
)

from test_info_perm import PINN_RT, _repo  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_guards():
    uninstall_eval_only_runtime_guard()
    yield
    uninstall_eval_only_runtime_guard()


def _write_mat(repo: Path, rel: str = "data/a.mat") -> Path:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"mat")
    return p


def _load_ws(repo: Path, mod: str = "workspace.m"):
    root_s = str(repo)
    if root_s in sys.path:
        sys.path.remove(root_s)
    sys.path.insert(0, root_s)
    for key in list(sys.modules):
        if key == "workspace" or key.startswith("workspace.") or key == "contract" or key.startswith("contract."):
            del sys.modules[key]
    return importlib.import_module(mod)


def test_unused_literal_check_info_perm_empty(tmp_path):
    ws = {"m.py": 'from scipy.io import loadmat\nfield = loadmat("data/ssfm/field_ref.mat")\n'}
    r = _repo(tmp_path, PINN_RT % "False", ws=ws)
    assert check_info_perm(r) == []
    inv = inventory_eval_only_literals(r)
    assert [v.rule for v in inv] == ["IP1"]


def test_cli_unused_literal_exit_0(tmp_path):
    cli = _PKG / "scripts" / "lib" / "info_perm.py"
    ws = {"m.py": 'from scipy.io import loadmat\nloadmat("data/ssfm/field_ref.mat")\n'}
    r = _repo(tmp_path, PINN_RT % "False", ws=ws)
    p = subprocess.run([sys.executable, str(cli), str(r)], capture_output=True, text=True)
    assert p.returncode == 0
    assert "IP1" not in p.stdout or "WARN" in p.stdout or "清单" in p.stdout


def test_runtime_blocks_workspace_open(tmp_path):
    rt = '''
INFO_PERM = {
    "enforce": True,
    "official_path": "full_model",
    "official_path_impl": None,
    "eval_only_assets": ("data/**/*.mat",),
    "eval_only_readers": ("contract/test.py",),
    "train_batch_keys": None,
    "strict_no_train_files": False,
}
'''
    ws = {
        "m.py": (
            "from pathlib import Path\n"
            "ROOT = Path(__file__).resolve().parent.parent\n"
            "def sneak():\n"
            "    return (ROOT / 'data' / 'a.mat').open('rb').read()\n"
        )
    }
    r = _repo(tmp_path, rt, ws=ws)
    _write_mat(r)
    install_eval_only_runtime_guard(r)
    m = _load_ws(r)
    with pytest.raises(RuntimeError, match="真用了只评材料"):
        m.sneak()


def test_runtime_allows_reader_stack(tmp_path):
    rt = '''
INFO_PERM = {
    "enforce": True,
    "official_path": "full_model",
    "official_path_impl": None,
    "eval_only_assets": ("data/**/*.mat",),
    "eval_only_readers": ("contract/test.py",),
    "train_batch_keys": None,
    "strict_no_train_files": False,
}
'''
    test_py = (
        "from pathlib import Path\n"
        "ROOT = Path(__file__).resolve().parent.parent\n"
        "def run(learner=None, ws=None, *, shared_context=None):\n"
        "    return (ROOT / 'data' / 'a.mat').open('rb').read()\n"
    )
    r = _repo(tmp_path, rt, test_py=test_py)
    _write_mat(r)
    install_eval_only_runtime_guard(r)
    t = _load_ws(r, "contract.test")
    assert t.run() == b"mat"


def test_enforce_false_runtime_allows(tmp_path):
    rt = PINN_RT.replace('"enforce": True', '"enforce": False') % "False"
    ws = {
        "m.py": (
            "from pathlib import Path\n"
            "ROOT = Path(__file__).resolve().parent.parent\n"
            "def sneak():\n"
            "    return (ROOT / 'data' / 'a.mat').open('rb').read()\n"
        )
    }
    r = _repo(tmp_path, rt, ws=ws)
    _write_mat(r)
    install_eval_only_runtime_guard(r)
    m = _load_ws(r)
    assert m.sneak() == b"mat"


def test_callable_asset_workspace_blocked_reader_allowed(tmp_path):
    rt = '''
INFO_PERM = {
    "enforce": True,
    "official_path": "full_model",
    "official_path_impl": None,
    "eval_only_assets": ("contract.ssfm.load_ssfm",),
    "eval_only_readers": ("contract/test.py",),
    "train_batch_keys": None,
    "strict_no_train_files": False,
}
'''
    r = _repo(
        tmp_path,
        rt,
        test_py=(
            "from contract.ssfm import load_ssfm\n"
            "def run(learner=None, ws=None, *, shared_context=None):\n"
            "    return load_ssfm('x')\n"
        ),
        ws={
            "m.py": (
                "from contract.ssfm import load_ssfm\n"
                "def sneak():\n"
                "    return load_ssfm('x')\n"
            )
        },
    )
    (r / "contract" / "ssfm.py").write_text("def load_ssfm(path):\n    return 'field'\n", encoding="utf-8")
    root_s = str(r)
    if root_s in sys.path:
        sys.path.remove(root_s)
    sys.path.insert(0, root_s)
    for key in list(sys.modules):
        if key == "workspace" or key.startswith("workspace.") or key == "contract" or key.startswith("contract."):
            del sys.modules[key]
    install_eval_only_runtime_guard(r)
    t = importlib.import_module("contract.test")
    assert t.run() == "field"
    m = importlib.import_module("workspace.m")
    with pytest.raises(RuntimeError, match="真用了只评材料"):
        m.sneak()


def test_strict_does_not_block_unrelated_path_with_data_in_name(tmp_path):
    rt = PINN_RT % "True"
    ws = {
        "m.py": (
            "from pathlib import Path\n"
            "def sneak():\n"
            "    p = Path('/usr/lib/python3/dist-packages/transformers/data/METADATA')\n"
            "    return str(p)\n"
            "def read_if_exists():\n"
            "    p = Path(__file__).resolve().parent / 'notes.txt'\n"
            "    return p.read_text(encoding='utf-8')\n"
        )
    }
    r = _repo(tmp_path, rt, ws=ws)
    (r / "workspace" / "notes.txt").write_text("ok\n", encoding="utf-8")
    install_eval_only_runtime_guard(r)
    m = _load_ws(r)
    assert m.sneak().endswith("METADATA")
    assert m.read_if_exists() == "ok\n"


def test_strict_unused_ok_used_np_load_blocked(tmp_path):
    numpy = pytest.importorskip("numpy")
    rt = PINN_RT % "True"
    ws = {
        "m.py": (
            "import numpy as np\n"
            "from pathlib import Path\n"
            "ROOT = Path(__file__).resolve().parent.parent\n"
            "def sneak():\n"
            "    return np.load(ROOT / 'data' / 'other.npz')\n"
        )
    }
    r = _repo(tmp_path, rt, ws=ws)
    npz = r / "data" / "other.npz"
    npz.parent.mkdir(parents=True, exist_ok=True)
    numpy.savez(npz, x=numpy.array([1.0]))
    assert check_info_perm(r) == []
    install_eval_only_runtime_guard(r)
    m = _load_ws(r)
    with pytest.raises(RuntimeError, match="真用了只评材料"):
        m.sneak()
