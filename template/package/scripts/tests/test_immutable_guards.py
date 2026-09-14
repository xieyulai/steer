"""G-框架 / G-契约：无 NN_RELAUNCH 时三源改动必须 raise（spec 20260717_1810）。"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_PKG = Path(__file__).resolve().parents[2]
import sys

sys.path.insert(0, str(_PKG))
import experiment as exp  # noqa: E402


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@t.com")
    _git(repo, "config", "user.name", "t")
    (repo / "experiment.py").write_text("# base\n", encoding="utf-8")
    (repo / "contract").mkdir()
    (repo / "contract" / "__init__.py").write_text("# c\n", encoding="utf-8")
    (repo / "workspace").mkdir()
    (repo / "workspace" / "x.py").write_text("# w\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    return repo


def test_working_tree_experiment_raises(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    monkeypatch.delenv("NN_RELAUNCH", raising=False)
    monkeypatch.setenv("NN_PREFLIGHT", "1")
    monkeypatch.setenv("NN_GUARD_EXPERIMENT_DIFF", "1")
    (repo / "experiment.py").write_text("# dirty\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match=r"\[Pre-flight G-框架\]"):
        exp._guard_experiment_unchanged(repo)


def test_relaunch_skips_experiment(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    monkeypatch.setenv("NN_RELAUNCH", "1")
    monkeypatch.setenv("NN_PREFLIGHT", "1")
    (repo / "experiment.py").write_text("# dirty\n", encoding="utf-8")
    exp._guard_experiment_unchanged(repo)  # 不 raise


def test_workspace_only_does_not_trip_experiment(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    monkeypatch.delenv("NN_RELAUNCH", raising=False)
    monkeypatch.setenv("NN_PREFLIGHT", "1")
    (repo / "workspace" / "x.py").write_text("# dirty w\n", encoding="utf-8")
    exp._guard_experiment_unchanged(repo)


def test_working_tree_contract_raises(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    monkeypatch.delenv("NN_RELAUNCH", raising=False)
    monkeypatch.setenv("NN_PREFLIGHT", "1")
    monkeypatch.setenv("NN_GUARD_CONTRACT_DIFF", "1")
    (repo / "contract" / "__init__.py").write_text("# dirty c\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match=r"\[Pre-flight G-契约\]"):
        exp._guard_contract_unchanged(repo)


def test_working_tree_claude_raises(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path)
    (repo / "CLAUDE.md").write_text("# base\n", encoding="utf-8")
    _git(repo, "add", "CLAUDE.md")
    _git(repo, "commit", "-m", "add claude")
    monkeypatch.delenv("NN_RELAUNCH", raising=False)
    monkeypatch.setenv("NN_PREFLIGHT", "1")
    monkeypatch.setenv("NN_GUARD_GOVERNANCE_DOCS", "1")
    (repo / "CLAUDE.md").write_text("# dirty\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match=r"\[Pre-flight G-治理文档\]"):
        exp._guard_governance_docs_unchanged(repo)
