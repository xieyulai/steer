# tests/test_init_overlay.py
"""对象类型 overlay：3 object_type → 5×3 表体按 object_type 分支 + drift-lock。"""
import sys, pathlib, shutil
import pytest
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "template/package/scripts"))
from init_o3_abcde import write_init_outputs
from inject_innovation_segments import extract_manual_cell
from init_workflow import Workflow


def _template_dir():
    return pathlib.Path(__file__).parent.parent / "skills" / "maintainer" / "auto-nn-init" / "templates"


def _manual_path(tmp_path):
    return tmp_path / "references" / "manual" / "abcde-manual.md"


# object_type → B 档 routine cell 必含短语
_CASES = [
    ("framework", "注册 backbone"),
    ("code", "改 workspace/"),
    ("data", "无源码"),
]


def test_manual_b_row_differs_per_object_type(tmp_path):
    """B 档 routine cell 按对象类型分支（overlay 接通的核心证据）。"""
    for object_type, phrase in _CASES:
        workflow = Workflow.MIGRATE if object_type == "code" else Workflow.BUILD
        write_init_outputs(tmp_path, workflow, object_type, _template_dir())
        txt = _manual_path(tmp_path).read_text(encoding="utf-8")
        assert f"对象类型={object_type}" in txt, f"{object_type} 头部标注缺失"
        cell = extract_manual_cell(_manual_path(tmp_path), "B", "routine")
        assert phrase in cell, f"{object_type} B-routine 期望含「{phrase}」，实得：{cell}"


def test_overlay_drift_lock_extract_cell_still_works(tmp_path):
    """overlay 接通后 extract_manual_cell 仍能取 A–E routine cell（drift-lock）。"""
    write_init_outputs(tmp_path, Workflow.MIGRATE, "framework", _template_dir())
    for letter in ("A", "B", "C", "D"):
        cell = extract_manual_cell(_manual_path(tmp_path), letter, "routine")
        assert cell.strip() != "", f"{letter}-routine cell 为空（drift-lock 破坏）"


def test_missing_marker_in_template_raises(tmp_path):
    """场景模板缺 marker → ValueError（fail-loud，不静默产无表 manual）。"""
    bad_dir = tmp_path / "bad_templates"
    shutil.copytree(_template_dir(), bad_dir)
    gf = bad_dir / "build.md"
    gf.write_text(gf.read_text(encoding="utf-8").replace("<!-- OVERLAY:5x3 -->", ""), encoding="utf-8")
    with pytest.raises(ValueError, match="期望恰好 1 个"):
        write_init_outputs(tmp_path / "repo", Workflow.BUILD, "data", bad_dir)


def test_empty_overlay_raises(tmp_path):
    """overlay 文件存在但为空 → ValueError（fail-loud）。"""
    bad_dir = tmp_path / "bad_templates"
    shutil.copytree(_template_dir(), bad_dir)
    (bad_dir / "overlay" / "data.md").write_text("   \n  ", encoding="utf-8")
    with pytest.raises(ValueError, match="overlay 表为空"):
        write_init_outputs(tmp_path / "repo", Workflow.MIGRATE, "data", bad_dir)
