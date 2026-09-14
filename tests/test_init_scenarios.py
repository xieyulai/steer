"""Tests for scripts/init_workflow.py — 3-workflow classifier (PR1 of single-axis).

classify() returns one of:
    BUILD    (no source_root)
    MIGRATE  (source_root != repo_root, with or without contract/)
    UPDATE   (source_root == repo_root, regardless of contract/)

PR1 keeps the old contract/ check (behavior-equivalent to init_scenarios.py).
PR2 will simplify to (None check + same-dir check) only.
"""
import os
import sys
import pathlib
import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "template/package/scripts"))

from init_workflow import classify, Workflow  # noqa: E402


def test_no_source_root_returns_build(tmp_path):
    assert classify(repo_root=tmp_path, source_root=None) == Workflow.BUILD


def test_source_root_without_contract_returns_migrate(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    assert classify(repo_root=tmp_path, source_root=src) == Workflow.MIGRATE


def test_source_root_with_contract_same_repo_returns_update(tmp_path):
    src = tmp_path
    (src / "contract").mkdir()
    (src / ".git").mkdir()
    assert classify(repo_root=tmp_path, source_root=src) == Workflow.UPDATE


def test_source_root_with_contract_different_repo_returns_migrate(tmp_path):
    src = tmp_path / "external"
    src.mkdir()
    (src / "contract").mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    assert classify(repo_root=repo, source_root=src) == Workflow.MIGRATE


def test_resolve_workflow_override_build(tmp_path):
    from init_workflow import resolve_workflow
    assert resolve_workflow(tmp_path, None, override="build") == Workflow.BUILD


def test_resolve_workflow_override_invalid(tmp_path):
    from init_workflow import resolve_workflow
    with pytest.raises(ValueError, match="未知"):
        resolve_workflow(tmp_path, None, override="bogus")


def test_detect_data_build(tmp_path):
    from init_workflow import detect, Workflow
    r = detect(tmp_path, None)
    assert r.workflow == Workflow.BUILD and r.object_type == "data" and r.pattern is None


def test_detect_code_build(tmp_path):
    (tmp_path / "model.py").write_text("import torch")
    from init_workflow import detect, Workflow
    r = detect(tmp_path, None)
    assert r.workflow == Workflow.BUILD and r.object_type == "code"


def test_detect_framework_build(tmp_path):
    (tmp_path / "learner.py").write_text("@register_learner\nclass Foo: pass")
    from init_workflow import detect, Workflow
    r = detect(tmp_path, None)
    assert r.workflow == Workflow.BUILD and r.object_type == "framework"


def test_detect_migrate_port_to_contract(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    repo = tmp_path / "repo"; repo.mkdir()
    from init_workflow import detect, Workflow
    r = detect(repo, src)
    assert r.workflow == Workflow.MIGRATE and r.pattern == "port_to_contract"


def test_detect_migrate_workspace_wrapper(tmp_path):
    src = tmp_path / "ext"; src.mkdir(); (src / "contract").mkdir()
    repo = tmp_path / "repo"; repo.mkdir()
    from init_workflow import detect, Workflow
    r = detect(repo, src)
    assert r.workflow == Workflow.MIGRATE and r.pattern == "workspace_wrapper"


def test_detect_update_same_repo_with_py(tmp_path):
    (tmp_path / "contract").mkdir()
    (tmp_path / "main.py").write_text("print('hi')")
    from init_workflow import detect, Workflow
    r = detect(tmp_path, tmp_path)
    assert r.workflow == Workflow.UPDATE and r.object_type == "code"
