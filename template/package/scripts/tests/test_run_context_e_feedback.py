"""Task 11：build-run-context 注入改题待审一行（pending 条数 / 无改题待审）。"""
import importlib.util
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SCRIPTS))

from lib.e_feedback_store import append_event  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "_build_run_context_under_test_ef", _SCRIPTS / "build-run-context.py"
)
brc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(brc)


def _shout(tmp_path: Path, proposed: str = "改主指标") -> None:
    append_event(
        tmp_path,
        kind="shout",
        proposed=proposed,
        why_abcd_insufficient="A-D 扫不动",
        ask="开闸改题面",
        quote="建议改题",
        experiment="exp_demo",
        source="reflect",
        round_hint=1,
    )


def test_format_e_feedback_line_none(tmp_path):
    assert brc._format_e_feedback_line(tmp_path) == "无改题待审"


def test_format_e_feedback_line_pending(tmp_path):
    _shout(tmp_path)
    assert brc._format_e_feedback_line(tmp_path) == "有改题待审：1 条"


def test_md_renders_e_feedback_none():
    md = brc.format_run_context_md({"e_feedback_line": "无改题待审"})
    assert "### 改题待审" in md
    assert "无改题待审" in md


def test_md_renders_e_feedback_pending():
    md = brc.format_run_context_md({"e_feedback_line": "有改题待审：2 条"})
    assert "### 改题待审" in md
    assert "有改题待审：2 条" in md


def test_build_run_context_includes_e_feedback(tmp_path):
    _shout(tmp_path)
    ctx = brc.build_run_context(tmp_path)
    assert ctx["e_feedback_line"] == "有改题待审：1 条"
    md = brc.format_run_context_md(ctx)
    assert "有改题待审：1 条" in md
