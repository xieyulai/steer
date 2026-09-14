"""layout 校验须走 nn_resolve（env 优先），不能只信跨机过期的 .auto-nn/template-root。"""
from __future__ import annotations

import os
from pathlib import Path

import verify_project_layout as vpl


def test_stale_file_falls_back_to_nn_template_root(tmp_path: Path, monkeypatch):
    repo = tmp_path / "biz"
    (repo / ".auto-nn").mkdir(parents=True)
    (repo / ".auto-nn" / "template-root").write_text(
        "/mnt/other-machine/does-not-exist/auto-nn-experiment\n",
        encoding="utf-8",
    )
    # 指向本仓模板维护根（含 .template-maintainer + template/package）
    maintainer = Path(__file__).resolve().parents[4]
    assert (maintainer / ".template-maintainer").is_file()
    monkeypatch.setenv("NN_TEMPLATE_ROOT", str(maintainer))
    # 隔离 symlink 探测：空 HOME
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))

    tpkg = vpl._template_package_root(repo)
    assert tpkg is not None
    assert (tpkg / "profiles.yaml").is_file()
    assert tpkg.resolve() == (maintainer / "template" / "package").resolve()


def test_skip_runtime_venv_and_poetry_toml_not_extra():
    assert vpl._skip_runtime_artifact(".venv") is True
    assert vpl._skip_runtime_artifact("venv") is True
    assert "poetry.toml" in vpl.EXTRA_ALLOWED_ROOT


def test_missing_all_sources_returns_none(tmp_path: Path, monkeypatch):
    repo = tmp_path / "biz"
    repo.mkdir()
    monkeypatch.delenv("NN_TEMPLATE_ROOT", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "empty-home"))
    (tmp_path / "empty-home").mkdir()
    assert vpl._template_package_root(repo) is None
