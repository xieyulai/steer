# tests/test_abcde_migrate.py
"""近版 abcde_migrate：detect() + write_init_outputs；idempotent。"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "template" / "package" / "scripts"))

from abcde_migrate import migrate_existing_project  # noqa: E402
from init_workflow import Workflow  # noqa: E402


def _template_dir() -> pathlib.Path:
    return ROOT / "skills" / "maintainer" / "auto-nn-init" / "templates"


def test_migrate_writes_manual_for_update_workflow(tmp_path):
    (tmp_path / "contract").mkdir()
    (tmp_path / "model.py").write_text("class Net: pass\n", encoding="utf-8")
    out = migrate_existing_project(repo_root=tmp_path, templates_dir=_template_dir())
    assert out["workflow"] == Workflow.UPDATE.value
    assert out["object_type"] == "code"
    md = tmp_path / "references" / "manual" / "abcde-manual.md"
    assert md.is_file()
    text = md.read_text(encoding="utf-8")
    assert "workspace_full" not in text
    assert "对象类型=code" in text


def test_migrate_idempotent_skips_when_manual_exists(tmp_path):
    (tmp_path / "contract").mkdir()
    (tmp_path / "model.py").write_text("class Net: pass\n", encoding="utf-8")
    first = migrate_existing_project(repo_root=tmp_path, templates_dir=_template_dir())
    second = migrate_existing_project(repo_root=tmp_path, templates_dir=_template_dir())
    assert second["workflow"] == "skipped (already migrated)"
    assert first["md_path"] == second["md_path"]
