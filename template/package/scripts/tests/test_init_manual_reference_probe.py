"""③-i Task B: _generate_manual 输出含「基线 reference 探测」段。

镜像 test_init_o3_abcde_manual.py 的 LOCAL _tpls fixture。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from init_o3_abcde import _generate_manual
from init_workflow import Workflow


def _local_tpls(tmp_path):
    tpls = tmp_path / "_tpls"
    tpls.mkdir()
    # 两个 workflow template 都写（build 测用 build.md，migrate 测用 migrate.md）
    (tpls / "build.md").write_text(
        "# Build\n## 2. 5×3 改码参考表\n<!-- OVERLAY:5x3 -->\n", encoding="utf-8")
    (tpls / "migrate.md").write_text(
        "# Migrate\n## 2. 5×3 改码参考表\n<!-- OVERLAY:5x3 -->\n", encoding="utf-8")
    overlay_dir = tpls / "overlay"
    overlay_dir.mkdir()
    # 两个 object_type overlay 都写（data 测用 data.md，framework 测用 framework.md）
    (overlay_dir / "data.md").write_text(
        "| 档\\深度 | routine | derived | different |\n|---|---|---|---|\n"
        "| A | aa | bb | cc |\n", encoding="utf-8")
    (overlay_dir / "framework.md").write_text(
        "| 档\\深度 | routine | derived | different |\n|---|---|---|---|\n"
        "| A | 注册 | 注册 | 注册 |\n", encoding="utf-8")
    return tpls


def test_manual_contains_reference_probe_build(tmp_path):
    """BUILD + data：manual 末尾含 reference 探测段。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    md = _generate_manual(repo, Workflow.BUILD, "data", _local_tpls(tmp_path))
    assert "基线 reference 探测" in md
    assert "EXPERIENCE" in md  # 指令须提到写进 EXPERIENCE
    assert "请用户给出" in md or "O3-baseline-anchors" in md
    assert "测试条件" in md or "OFFICIAL_TEST" in md


def test_manual_contains_reference_probe_migrate(tmp_path):
    """MIGRATE + framework（带 pattern）：reference 段仍在（无条件追加，不依赖 workflow）。"""
    repo = tmp_path / "repo"
    repo.mkdir()
    md = _generate_manual(repo, Workflow.MIGRATE, "framework", _local_tpls(tmp_path), pattern="port_to_contract")
    assert "基线 reference 探测" in md
    assert "novel" in md  # 须说明 novel/无则留空
