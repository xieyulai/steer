"""模板骨架自带 INFO_PERM 登记表与交卷缝（spec 20260905_1755 §2/§5）；physical 软对齐。"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import yaml

_PKG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PKG / "scripts"))
from lib.info_perm import check_info_perm, load_info_perm  # noqa: E402


def test_skeleton_declares_permissive_info_perm():
    perm = load_info_perm(_PKG)
    assert perm is not None
    assert perm.enforce is True and perm.official_path == "full_model"
    assert perm.official_path_impl is None
    assert perm.eval_only_assets == () and perm.strict_no_train_files is False
    assert perm.train_batch_keys is None


def test_skeleton_passes_its_own_scan():
    assert check_info_perm(_PKG) == []


def test_skeleton_test_py_has_seams():
    tree = ast.parse((_PKG / "contract" / "test.py").read_text(encoding="utf-8"))
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert {"_official_path_enabled", "_official_forward", "run"} <= set(funcs)
    body = funcs["_official_path_enabled"].body
    ret = [s for s in body if isinstance(s, ast.Return)]
    assert len(ret) == 1 and isinstance(ret[0].value, ast.Constant) and ret[0].value.value is True


def test_physical_profile_no_longer_lists_workspace_prepare_data():
    prof = yaml.safe_load((_PKG / "profiles.yaml").read_text(encoding="utf-8"))
    physical = prof["profiles"]["physical"]
    assert "prepare_data" not in physical["workspace"]
    assert "prepare_data" in physical["contract"]
    assert "workspace_forbidden" not in physical  # 只软对齐，不加硬禁
