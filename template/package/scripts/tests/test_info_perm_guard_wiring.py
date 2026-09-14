"""G-信息权限接线（experiment.py；需 torch 才能 import）。spec 20260905_1755 §4。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("torch")

_PKG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PKG))
import experiment as exp  # noqa: E402

from lib.info_perm import uninstall_eval_only_runtime_guard  # noqa: E402

RT = 'INFO_PERM = {"enforce": True, "eval_only_assets": ("data/**/*.mat",)}\n'
BAD_WS = 'from scipy.io import loadmat\nloadmat("data/a.mat")\n'


@pytest.fixture(autouse=True)
def _clean_info_perm_runtime():
    uninstall_eval_only_runtime_guard()
    yield
    uninstall_eval_only_runtime_guard()


def _repo(tmp_path: Path, rt: str = RT, ws_src: str = "X = 1\n") -> Path:
    # 不建 scripts/lib：让 experiment.py 用模板自己的 scripts/lib（否则 sys.modules['lib'] 被 tmp 包污染）
    r = tmp_path / "r"
    (r / "contract").mkdir(parents=True)
    (r / "workspace").mkdir()
    (r / "contract" / "runtime.py").write_text(rt, encoding="utf-8")
    (r / "contract" / "test.py").write_text("def run(learner, ws, *, shared_context):\n    return {}\n", encoding="utf-8")
    (r / "workspace" / "m.py").write_text(ws_src, encoding="utf-8")
    return r


def test_guard_raises_and_ignores_env_switch(tmp_path, monkeypatch):
    r = _repo(tmp_path, ws_src=BAD_WS)
    monkeypatch.setenv("NN_GUARD_INFO_PERM", "0")  # 家族特例：不存在此开关，设了也无效
    exp._guard_info_perm(r)  # 未调用字面量不再预检 FAIL；开关仍无效（无此 env）


def test_guard_passes_when_clean(tmp_path):
    exp._guard_info_perm(_repo(tmp_path))


def test_guard_noop_when_not_declared(tmp_path):
    exp._guard_info_perm(_repo(tmp_path, rt="X = 1\n", ws_src=BAD_WS))


def test_guard_ip0_non_literal(tmp_path):
    r = _repo(tmp_path, rt="import os\nINFO_PERM = {'enforce': os.environ.get('A') == '1'}\n")
    with pytest.raises(RuntimeError, match="IP0"):
        exp._guard_info_perm(r)


def test_static_guards_include_info_perm():
    import inspect

    src = inspect.getsource(exp._run_static_preflight_guards)
    assert "_guard_info_perm(root)" in src
    assert src.index("_guard_test_authority(root)") < src.index("_guard_info_perm(root)")


def test_train_batch_keys_guard(tmp_path):
    r = _repo(tmp_path, rt='INFO_PERM = {"enforce": True, "train_batch_keys": ("x", "y")}\n')
    exp._guard_train_batch_keys(r, {"x": 1, "y": 2})
    exp._guard_train_batch_keys(r, None)
    with pytest.raises(RuntimeError, match=r"G-信息权限[\s\S]*ref"):
        exp._guard_train_batch_keys(r, {"x": 1, "ref": 3})


def test_train_batch_keys_guard_noop_without_keys(tmp_path):
    exp._guard_train_batch_keys(_repo(tmp_path), {"anything": 1})


def test_guard_installs_runtime_hook(tmp_path):
    import inspect

    src = inspect.getsource(exp._guard_info_perm)
    assert "install_eval_only_runtime_guard" in src


def test_preflight_check_accepts_train_batch_kwarg():
    import inspect

    assert "train_batch" in inspect.signature(exp.ExperimentBase.preflight_check).parameters


def test_collect_guard_bypasses_reexport():
    assert exp.collect_guard_bypasses({"NN_PREFLIGHT": "0", "NN_GUARD_X": "off"}) == ["NN_GUARD_X=off", "NN_PREFLIGHT=0"]


def test_read_guards_bypassed(tmp_path):
    d = tmp_path / "exp"
    d.mkdir()
    assert exp._read_guards_bypassed(d) == []
    (d / "config.json").write_text(json.dumps({"_repro": {"guards_bypassed": ["NN_PREFLIGHT=0"]}}), encoding="utf-8")
    assert exp._read_guards_bypassed(d) == ["NN_PREFLIGHT=0"]


def test_finalize_bypass_veto_helper(tmp_path):
    """enforce=True + 旁路 → 抛错；未登记 / enforce=False / 无旁路 → 放行。"""
    r = _repo(tmp_path)
    with pytest.raises(RuntimeError, match=r"\[finalize G-旁路\]"):
        exp._raise_if_bypassed_under_enforce(r, ["NN_PREFLIGHT=0"])
    exp._raise_if_bypassed_under_enforce(r, [])
    r2 = _repo(tmp_path / "off", rt='INFO_PERM = {"enforce": False}\n')
    exp._raise_if_bypassed_under_enforce(r2, ["NN_PREFLIGHT=0"])
    r3 = _repo(tmp_path / "none", rt="X = 1\n")
    exp._raise_if_bypassed_under_enforce(r3, ["NN_PREFLIGHT=0"])
