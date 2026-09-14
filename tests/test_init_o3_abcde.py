# tests/test_init_o3_abcde.py
"""init 产物结构测试（PR2 单轴改造后）。

write_init_outputs 产 1 文件:
  - references/manual/abcde-manual.md（workflow 头 + object_type 头 + 场景 5×3 表 + decision_tree 附录）

3 object_type（data/code/framework） + 3 workflow（build/migrate/update） 单轴决定产物结构。
"""
import sys, pathlib, pytest
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "template/package/scripts"))
from init_o3_abcde import write_init_outputs
from init_workflow import Workflow


def _template_dir():
    return pathlib.Path(__file__).parent.parent / "skills" / "maintainer" / "auto-nn-init" / "templates"


def test_write_init_outputs_creates_manual(tmp_path):
    out = write_init_outputs(
        target_root=tmp_path,
        workflow=Workflow.BUILD,
        object_type="data",
        templates_dir=_template_dir(),
    )
    assert (tmp_path / "references" / "manual" / "abcde-manual.md").exists()
    assert "md_path" in out


@pytest.mark.parametrize("workflow,object_type", [
    (Workflow.BUILD, "data"),
    (Workflow.BUILD, "code"),
    (Workflow.BUILD, "framework"),
    (Workflow.MIGRATE, "code"),
    (Workflow.MIGRATE, "framework"),
    (Workflow.UPDATE, "code"),
])
def test_manual_header_reflects_workflow_and_object_type(tmp_path, workflow, object_type):
    write_init_outputs(tmp_path, workflow, object_type, _template_dir())
    txt = (tmp_path / "references" / "manual" / "abcde-manual.md").read_text(encoding="utf-8")
    assert f"对象类型={object_type}" in txt
    assert f"workflow={workflow.value}" in txt


def test_migrate_pattern_workspace_wrapper(tmp_path):
    write_init_outputs(tmp_path, Workflow.MIGRATE, "framework", _template_dir(),
                       pattern="workspace_wrapper")
    txt = (tmp_path / "references" / "manual" / "abcde-manual.md").read_text(encoding="utf-8")
    assert "workspace_wrapper" in txt


def test_migrate_pattern_port_to_contract(tmp_path):
    write_init_outputs(tmp_path, Workflow.MIGRATE, "code", _template_dir(),
                       pattern="port_to_contract")
    txt = (tmp_path / "references" / "manual" / "abcde-manual.md").read_text(encoding="utf-8")
    assert "port_to_contract" in txt


def test_framework_path_ceiling_register(tmp_path):
    write_init_outputs(tmp_path, Workflow.BUILD, "framework", _template_dir())
    txt = (tmp_path / "references" / "manual" / "abcde-manual.md").read_text(encoding="utf-8")
    assert "路径上限=register" in txt
