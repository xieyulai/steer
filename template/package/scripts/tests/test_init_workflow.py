"""v1.33.0 — init_workflow.detect() framework_kind 字段 + 既有 detect() 行为保留。

覆盖:detect() 在 object_type=framework 时推断 framework_kind;
data/code 仓时 framework_kind 为 None。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from init_workflow import Workflow, detect


# ---- detect() 既有 workflow + object_type 行为保留 ----

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
    """无 .py(只有 raw.csv) → object_type=data。"""
    (tmp_path / "raw.csv").write_text("a,b,c\n1,2,3\n", encoding="utf-8")
    result = detect(tmp_path, None)
    assert result.object_type == "data"


# ---- v1.33.0 — detect() 增 framework_kind 字段 ----

def test_init_workflow_detect_emits_framework_kind_for_framework_repo(tmp_path):
    """framework 仓 → detect() framework_kind 字段非 None。"""
    (tmp_path / "models.py").write_text(
        "@register_model\nclass MyMammothModel:\n    pass\n",
        encoding="utf-8",
    )
    result = detect(repo_root=tmp_path, source_root=None)
    assert result.object_type == "framework"
    assert result.framework_kind in {"mammoth", "lightning", "hf_trainer", "timm", "avalanche", "unknown"}


def test_init_workflow_detect_emits_framework_kind_none_for_data_repo(tmp_path):
    """data 仓 → framework_kind 字段为 None。"""
    result = detect(repo_root=tmp_path, source_root=None)
    assert result.object_type == "data"
    assert result.framework_kind is None


def test_init_workflow_detect_infers_mammoth_from_module_hint(tmp_path):
    """模块名含 mammoth → framework_kind=mammoth。"""
    (tmp_path / "mammoth_models.py").write_text(
        "@register_model\nclass CLModel:\n    pass\n",
        encoding="utf-8",
    )
    result = detect(repo_root=tmp_path, source_root=None)
    assert result.object_type == "framework"
    assert result.framework_kind == "mammoth"


# ---- 2026-07-20 — MIGRATE 扫 source_root（不被 target 脚手架误报）----

def test_migrate_source_data_ignores_target_register(tmp_path):
    """target 含 @register_*，source 仅 csv → object_type=data。"""
    target = tmp_path / "target"
    source = tmp_path / "source"
    target.mkdir()
    source.mkdir()
    (target / "registry.py").write_text(
        "@register_learner\ndef f():\n    pass\n", encoding="utf-8")
    (source / "raw.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    result = detect(target, source)
    assert result.workflow == Workflow.MIGRATE
    assert result.object_type == "data"
    assert result.pattern == "port_to_contract"
    assert result.framework_kind is None


def test_migrate_source_code_no_register(tmp_path):
    """migrate：source 有自有 .py 无 register → code。"""
    target = tmp_path / "target"
    source = tmp_path / "source"
    target.mkdir()
    source.mkdir()
    (target / "registry.py").write_text(
        "@register_learner\ndef f():\n    pass\n", encoding="utf-8")
    (source / "train.py").write_text("class Net:\n    pass\n", encoding="utf-8")
    result = detect(target, source)
    assert result.workflow == Workflow.MIGRATE
    assert result.object_type == "code"


def test_migrate_source_framework_register(tmp_path):
    """migrate：source 有 @register_* → framework。"""
    target = tmp_path / "target"
    source = tmp_path / "source"
    target.mkdir()
    source.mkdir()
    (target / "model.py").write_text("x = 1\n", encoding="utf-8")
    (source / "models.py").write_text(
        "@register_model\nclass M:\n    pass\n", encoding="utf-8")
    result = detect(target, source)
    assert result.workflow == Workflow.MIGRATE
    assert result.object_type == "framework"


def test_detect_skips_venv_py_for_has_py(tmp_path):
    """仅 .venv 内有 .py → 仍判 data（跳过噪声树）。"""
    venv = tmp_path / ".venv" / "lib"
    venv.mkdir(parents=True)
    (venv / "sitecustomize.py").write_text("pass\n", encoding="utf-8")
    (tmp_path / "raw.csv").write_text("a\n1\n", encoding="utf-8")
    result = detect(tmp_path, None)
    assert result.object_type == "data"