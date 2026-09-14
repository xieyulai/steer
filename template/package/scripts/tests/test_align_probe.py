"""align_probe + init_align 单测（方案 2 / C）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SCRIPTS))

from init_align import load_align, write_align  # noqa: E402
from lib.align_probe import probe  # noqa: E402


def test_build_scaffold_suggests_data(tmp_path):
    """拷入带 @register_* 的脚手架后，BUILD 建议仍为 data。"""
    (tmp_path / "workspace").mkdir()
    (tmp_path / "workspace" / "demo.py").write_text(
        "@register_learner\nclass X: pass\n", encoding="utf-8"
    )
    sug = probe(tmp_path, None, force_workflow="build")
    assert sug.workflow == "build"
    assert sug.object_type_suggested == "data"
    assert sug.detect_object_type == "framework"
    assert "build_default_object_type:data" in sug.evidence


def test_cleanrl_suggests_rl(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="cleanrl"\ndependencies=["gymnasium==0.29.1"]\n',
        encoding="utf-8",
    )
    (tmp_path / "ppo_atari.py").write_text("# algo\n", encoding="utf-8")
    repo = tmp_path / "tgt"
    repo.mkdir()
    sug = probe(repo, tmp_path, force_workflow="migrate")
    assert sug.profile_suggested == "rl"
    assert sug.migrate_allowed is True


def test_raw_data_rejects_migrate(tmp_path):
    src = tmp_path / "raw"
    src.mkdir()
    (src / "train-images-idx3-ubyte").write_bytes(b"\x00" * 16)
    repo = tmp_path / "tgt"
    repo.mkdir()
    sug = probe(repo, src, force_workflow="migrate")
    assert sug.object_type_suggested == "data" or sug.detect_object_type == "data"
    assert sug.migrate_allowed is False


def test_mammoth_path_suggests_framework_name(tmp_path):
    src = tmp_path / "mammoth"
    src.mkdir()
    (src / "models").mkdir()
    (src / "models" / "er.py").write_text(
        "@register_model\ndef f():\n    pass\n", encoding="utf-8"
    )
    repo = tmp_path / "tgt"
    repo.mkdir()
    sug = probe(repo, src, force_workflow="migrate")
    assert sug.detect_object_type == "framework"
    assert sug.framework_name_suggested == "mammoth"


def test_init_align_write_load(tmp_path):
    write_align(
        tmp_path,
        entry="B",
        source_root=None,
        workflow="build",
        object_type="data",
        profile="supervised",
    )
    data = load_align(tmp_path)
    assert data is not None
    assert data["object_type"] == "data"
    with pytest.raises(FileExistsError):
        write_align(
            tmp_path,
            entry="B",
            source_root=None,
            workflow="build",
            object_type="code",
            profile="supervised",
        )


def test_init_o3_consumes_init_align(tmp_path):
    tpls = tmp_path / "tpls"
    tpls.mkdir()
    (tpls / "build.md").write_text(
        "# B\n## 2. 5×3 改码参考表\n<!-- OVERLAY:5x3 -->\n", encoding="utf-8"
    )
    (tpls / "overlay").mkdir()
    (tpls / "overlay" / "code.md").write_text(
        "| A | a | b | c |\n", encoding="utf-8"
    )
    (tmp_path / "workspace").mkdir()
    (tmp_path / "workspace" / "x.py").write_text(
        "@register_learner\nclass Y: pass\n", encoding="utf-8"
    )
    write_align(
        tmp_path,
        entry="B",
        source_root=None,
        workflow="build",
        object_type="code",
        profile="supervised",
    )
    from init_o3_abcde import interactive_run
    from init_workflow import Workflow

    out = interactive_run(tmp_path, None, tpls)
    assert out["object_type"] == "code"
    md = (tmp_path / "references" / "manual" / "abcde-manual.md").read_text(encoding="utf-8")
    assert "对象类型=code" in md
    assert "workspace_full" not in md
