"""T2: init detect() 单轴分类 + 生成 manual 路径。

PR2.4: _classify_object_type → detect() (fs fixture + DetectionResult)。
detect(repo_root, source_root) 读文件系统判定 workflow(3) + object_type(3) + pattern。
_generate_manual 两测保留 LOCAL _tpls fixture（不依赖仓内真实 templates/）。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from init_o3_abcde import write_init_outputs
from init_workflow import Workflow, detect


# ---- detect() object_type 轴：读 fs 判定 data / code / framework ----

def test_detect_framework_with_register_decorator(tmp_path):
    """learner.py 带 @register_xxx → object_type=framework。"""
    (tmp_path / "learner.py").write_text(
        "@register_backbone\ndef build():\n    pass\n", encoding="utf-8")
    result = detect(tmp_path, None)
    assert result.object_type == "framework"
    assert result.workflow == Workflow.BUILD


def test_detect_code_with_py_no_register(tmp_path):
    """model.py 有 .py 但无 @register_* → object_type=code。"""
    (tmp_path / "model.py").write_text(
        "class Net:\n    pass\n", encoding="utf-8")
    result = detect(tmp_path, None)
    assert result.object_type == "code"


def test_detect_data_no_py(tmp_path):
    """无 .py（只有 raw.csv）→ object_type=data。"""
    (tmp_path / "raw.csv").write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    result = detect(tmp_path, None)
    assert result.object_type == "data"


# ---- detect() workflow 轴：读 source_root 判定 build / migrate / update ----

def test_detect_migrate_with_source_root(tmp_path):
    """source_root 存在且无 contract/ → workflow=migrate + pattern=port_to_contract。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "model.py").write_text("class Net: pass\n", encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    result = detect(repo, src)
    assert result.workflow == Workflow.MIGRATE
    assert result.pattern == "port_to_contract"


def test_detect_update_same_dir(tmp_path):
    """source_root == repo_root（且有 contract/）→ workflow=update。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "contract").mkdir()
    (repo / "model.py").write_text("class Net: pass\n", encoding="utf-8")
    result = detect(repo, repo)
    assert result.workflow == Workflow.UPDATE


# ---- _generate_manual：LOCAL _tpls fixture（不依赖仓内真实 templates/）----

def test_write_init_outputs_generates_manual(tmp_path):
    """init 产出 references/manual/abcde-manual.md（Workflow.BUILD + object_type=data）。

    自带最小 template，避免依赖仓内真实 skills/ 路径。write_init_outputs 新签名
    (target_root/workflow/object_type/templates_dir/pattern)。
    """
    repo = tmp_path
    tpls = tmp_path / "_tpls"
    tpls.mkdir()
    (tpls / "build.md").write_text(
        "# Build\n## 2. 5×3 改码参考表\n"
        "<!-- OVERLAY:5x3 -->\n",
        encoding="utf-8")
    overlay_dir = tpls / "overlay"
    overlay_dir.mkdir()
    (overlay_dir / "data.md").write_text(
        "| 档\\深度 | routine | derived | different |\n|---|---|---|---|\n"
        "| A | aa | bb | cc |\n",
        encoding="utf-8")
    out = write_init_outputs(repo, Workflow.BUILD, "data", tpls)
    assert out["md_path"].endswith("references/manual/abcde-manual.md")
    assert (repo / "references" / "manual" / "abcde-manual.md").is_file()
    manual = (repo / "references" / "manual" / "abcde-manual.md").read_text(encoding="utf-8")
    assert "对象类型判定" in manual
    assert "对象类型=data" in manual


def test_init_header_describes_fork_trigger_for_register_ceiling(tmp_path):
    """framework（register 上限）manual 头注须描述 fork 触发 + HUMAN_GUIDANCE 优先级。"""
    repo = tmp_path
    tpls = tmp_path / "_tpls"
    tpls.mkdir()
    (tpls / "migrate.md").write_text(
        "# Migrate\n## 2. 5×3 改码参考表\n"
        "<!-- OVERLAY:5x3 -->\n",
        encoding="utf-8")
    overlay_dir = tpls / "overlay"
    overlay_dir.mkdir()
    (overlay_dir / "framework.md").write_text(
        "| 档\\深度 | routine | derived | different |\n|---|---|---|---|\n"
        "| A | 注册 | 注册 | 注册 |\n"
        "| B | 注册 backbone | 注册 | 注册 |\n"
        "| C | 注册 | 注册 | 注册 |\n"
        "| D | 注册 | 注册 | 注册 |\n"
        "| E | 注册 | 注册 | 注册 |\n",
        encoding="utf-8")
    out = write_init_outputs(repo, Workflow.MIGRATE, "framework", tpls)
    manual_path = repo / "references" / "manual" / "abcde-manual.md"
    assert manual_path.is_file()
    manual = manual_path.read_text(encoding="utf-8")
    head = manual[:800]  # 头注在开头
    # 旧 marker 必须消失
    assert "_待 reflect 补实_" not in head
    # 新关键词必须出现（fork 触发描述 + HUMAN_GUIDANCE 优先级）
    assert "fork 触发" in head
    assert "HUMAN_GUIDANCE" in head and "manual 路径上限" in head
    assert "framework 档 fork 兜底格" in head
    assert "breakin 栏" not in head


def test_force_object_type_overrides_detect_framework(tmp_path):
    """--force-object-type code 压过 detect 的 framework。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "registry.py").write_text(
        "@register_learner\ndef f():\n    pass\n", encoding="utf-8")
    tpls = tmp_path / "_tpls"
    tpls.mkdir()
    (tpls / "build.md").write_text(
        "# Build\n## 2. 5×3 改码参考表\n<!-- OVERLAY:5x3 -->\n",
        encoding="utf-8")
    overlay_dir = tpls / "overlay"
    overlay_dir.mkdir()
    (overlay_dir / "code.md").write_text(
        "| 档\\深度 | routine | derived | different |\n|---|---|---|---|\n"
        "| A | aa | bb | cc |\n",
        encoding="utf-8")
    from init_o3_abcde import interactive_run
    out = interactive_run(repo, None, tpls, force_object_type="code")
    assert out["object_type"] == "code"
    manual = (repo / "references" / "manual" / "abcde-manual.md").read_text(encoding="utf-8")
    assert "对象类型=code" in manual


def test_framework_mutability_breakin_not_in_init_o3_source():
    """init_o3_abcde.py 不再把 breakin 列入 --framework-mutability choices。"""
    src = Path(__file__).resolve().parent.parent / "init_o3_abcde.py"
    text = src.read_text(encoding="utf-8")
    assert 'choices=["cfg", "register", "source"]' in text
    assert 'choices=["cfg", "register", "source", "breakin"]' not in text


def _repo_templates_dir() -> Path:
    """仓内真源：skills/maintainer/auto-nn-init/templates（锁 build.md 双源）。"""
    # test → scripts → package → template → repo root
    return (
        Path(__file__).resolve().parents[4]
        / "skills"
        / "maintainer"
        / "auto-nn-init"
        / "templates"
    )


def test_build_manual_body_has_no_workspace_full(tmp_path):
    """BUILD + code：真源模板生成的 manual 头/正文均无 workspace_full，默认类型=code。"""
    tpls = _repo_templates_dir()
    assert tpls.is_dir(), f"缺仓内 templates: {tpls}"
    assert (tpls / "build.md").is_file()
    assert (tpls / "overlay" / "code.md").is_file()
    write_init_outputs(tmp_path, Workflow.BUILD, "code", tpls)
    md = (tmp_path / "references" / "manual" / "abcde-manual.md").read_text(
        encoding="utf-8"
    )
    assert "workspace_full" not in md
    assert "对象类型=code" in md
    assert "默认对象类型: **code**" in md
    assert "Greenfield 场景" not in md
