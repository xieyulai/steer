"""Tests for scripts/new_project_scenarios.py — resolve_init_workflow (3-workflow)."""
from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "template" / "package" / "scripts"))

from new_project_scenarios import resolve_init_workflow  # noqa: E402


def test_no_source_returns_build(tmp_path):
    assert resolve_init_workflow(repo=str(tmp_path), source=None, force_update=False) == "build"


def test_empty_source_returns_build(tmp_path):
    assert resolve_init_workflow(repo=str(tmp_path), source="", force_update=False) == "build"


def test_source_different_repo_returns_migrate(tmp_path):
    src = tmp_path / "external"
    src.mkdir()
    (src / "contract").mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    assert resolve_init_workflow(repo=str(repo), source=str(src), force_update=False) == "migrate"


def test_source_same_repo_returns_update(tmp_path):
    (tmp_path / "contract").mkdir()
    assert (
        resolve_init_workflow(repo=str(tmp_path), source=str(tmp_path), force_update=False)
        == "update"
    )


def test_force_update_takes_priority(tmp_path):
    src = tmp_path / "external"
    src.mkdir()
    assert resolve_init_workflow(repo=str(tmp_path), source=str(src), force_update=True) == "update"


def test_workflow_override(tmp_path):
    assert (
        resolve_init_workflow(
            repo=str(tmp_path), source=None, force_update=False, workflow_override="migrate"
        )
        == "migrate"
    )


def test_invalid_workflow_override_raises(tmp_path):
    with pytest.raises(ValueError, match="未知"):
        resolve_init_workflow(
            repo=str(tmp_path), source=None, force_update=False, workflow_override="bogus"
        )
