# tests/test_check_copy_closure.py
"""D2: AST 闭包检查——扫描产物内部 import,逐个验证目标文件存在。"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "template" / "package" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_copy_closure as CC  # noqa: E402


def _tree(tmp_path):
    repo = tmp_path / "repo"
    for rel in ("contract/__init__.py", "contract/metrics.py", "contract/prepare_data.py",
                "workspace/__init__.py", "scripts/lib/nn_state.py"):
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("", encoding="utf-8")
    (repo / "workspace" / "legacy_transformer.py").write_text(
        "def make_model():\n    return None\n", encoding="utf-8")
    (repo / "workspace" / "__init__.py").write_text(
        "from workspace.legacy_transformer import make_model\n", encoding="utf-8")
    (repo / "train.py").write_text(
        "import contract.prepare_data\n"
        "from lib import nn_state\n"
        "import experiment\n"
        "import numpy as np\n"
        "from . import contract  # 相对\n",
        encoding="utf-8",
    )
    (repo / "experiment.py").write_text("pass\n", encoding="utf-8")
    return repo


def test_closure_ok_ignores_external_and_relative(tmp_path):
    repo = _tree(tmp_path)
    problems, notes = CC.check_closure(repo, CC.default_scan(repo))
    assert problems == []
    assert any("相对 import" in n for n in notes)


def test_closure_missing_workspace_module(tmp_path):
    repo = _tree(tmp_path)
    (repo / "workspace" / "legacy_transformer.py").unlink()
    problems, _ = CC.check_closure(repo, CC.default_scan(repo))
    assert len(problems) == 1
    assert "workspace/__init__.py" in problems[0] and "legacy_transformer" in problems[0]


def test_closure_source_root_module_not_copied(tmp_path):
    repo = _tree(tmp_path)
    src = tmp_path / "src"
    src.mkdir()
    (src / "helper.py").write_text("pass\n", encoding="utf-8")
    (repo / "train.py").write_text("import helper\n", encoding="utf-8")
    problems, _ = CC.check_closure(repo, CC.default_scan(repo), source_root=src)
    assert len(problems) == 1 and "源根级模块 helper.py 未复制" in problems[0]
