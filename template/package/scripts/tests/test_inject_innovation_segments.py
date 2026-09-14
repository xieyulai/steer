"""T4: inject 切 manual cell + drift-lock（旧 schema no-op）。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from inject_innovation_segments import extract_manual_cell, render_tier_slice, parse_tier_state


_MANUAL = """# manual

## 对象类型判定（init）

## 2. 5×3 改码参考表
| 档\\深度 | routine | derived | different |
|---------|---------|---------|------------|
| A | **改什么**: 超参<br>**路径**: cfg | **改什么**: 调度<br>**路径**: cfg→注册制 | **改什么**: AutoML<br>**路径**: 注册制→源码 |
| B | bb-r | bb-e | bb-n |
| C | cc-r | cc-e | cc-n |
| D | dd-r | dd-e | dd-n |
| E | ee-r | ee-r | ee-r |
"""


def test_extract_manual_cell_finds_letter_depth():
    cell = extract_manual_cell(Path(_write_tmp(_MANUAL)), "A", "routine")
    assert "超参" in cell
    assert "cfg" in cell


def test_extract_manual_cell_missing_returns_empty(tmp_path):
    p = tmp_path / "nope.md"
    assert extract_manual_cell(p, "A", "routine") == ""


def test_render_tier_slice_reads_manual(tmp_path):
    (tmp_path / "references" / "manual").mkdir(parents=True)
    (tmp_path / "references" / "manual" / "abcde-manual.md").write_text(_MANUAL, encoding="utf-8")
    (tmp_path / "EXPERIENCE.md").write_text(
        "## Tier 状态（\n| Tier | routine | derived | different |\n|---|---|---|---|\n"
        "| A | 进行中 | 未试 | 未试 |\n| B | 未试 | 未试 | 未试 |\n"
        "| C | 未试 | 未试 | 未试 |\n| D | 未试 | 未试 | 未试 |\n| E | 未试 | 未试 | 未试 |\n",
        encoding="utf-8")
    out = render_tier_slice(tmp_path)
    assert "当前阶段的创新指南" in out
    assert "A 档" in out or "超参" in out
    # 不再拼 modifier_seeds 明细
    assert "modifier_examples" not in out


def test_render_tier_slice_drift_lock_no_manual(tmp_path):
    """无 manual / 无 EXPERIENCE → 空串（drift-lock）。"""
    assert render_tier_slice(tmp_path) == ""


def test_extract_manual_cell_old_header_drift_locks(tmp_path):
    """RDDN migrate (T2)：旧 schema 表头 routine|extend|novel 已退役 → drift-lock 空串。"""
    p = tmp_path / "old.md"
    p.write_text(
        "| 档\\深度 | routine | extend | novel |\n|---|---|---|---|\n| A | x | y | z |\n",
        encoding="utf-8",
    )
    assert extract_manual_cell(p, "A", "routine") == ""


def _write_tmp(text) -> str:
    import tempfile
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8")
    f.write(text)
    f.close()
    return f.name
