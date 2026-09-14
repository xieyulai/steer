"""Ticket 04 Slice 4: build-run-context 把 round_decision.paper_hint 作字段注入下轮上下文。

spec §4：外部证据「随 round_decision 落盘并注入下轮 step 1 上下文（字段注入，不走
direction_full）」。本切片测 build-run-context 从 _runs/round_decision.json 读 paper_hint
并渲染为 md 独立段（与 round_decision 行分清；不混文本注入通道）。

build-run-context.py 是连字符脚本名（不能普通 import）→ importlib 按 path 加载。
"""
import importlib.util
import json
import sys
from pathlib import Path

# sys.path 已含 scripts/（convention）；这里按 path 加载连字符脚本模块。
_SCRIPTS = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("_build_run_context_under_test", _SCRIPTS / "build-run-context.py")
brc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(brc)


def _write_round_decision(repo_root: Path, payload: dict) -> None:
    runs = repo_root / "_runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "round_decision.json").write_text(json.dumps(payload), encoding="utf-8")


# ---- _format_round_paper_hint reader ----

def test_format_round_paper_hint_reads_field(tmp_path):
    """round_decision.json 带 paper_hint → 读出该字段字符串。"""
    _write_round_decision(tmp_path, {
        "keep_suggestion": True,
        "paper_hint": "FooNet with attention gating.",
        "evidence_refs": [{"title": "FooNet", "url": "https://arxiv.org/abs/2401.00001"}],
    })
    assert brc._format_round_paper_hint(tmp_path) == "FooNet with attention gating."


def test_format_round_paper_hint_missing_file(tmp_path):
    """无 round_decision.json → None（下轮上下文不注入该段）。"""
    assert brc._format_round_paper_hint(tmp_path) is None


def test_format_round_paper_hint_empty_field(tmp_path):
    """round_decision.json 存在但 paper_hint 空 → None。"""
    _write_round_decision(tmp_path, {"keep_suggestion": False, "paper_hint": "", "evidence_refs": []})
    assert brc._format_round_paper_hint(tmp_path) is None


def test_format_round_paper_hint_corrupt(tmp_path):
    """损坏 JSON → None 不崩（与 _format_round_decision_line 同型 best-effort）。"""
    runs = tmp_path / "_runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "round_decision.json").write_text("{ not json", encoding="utf-8")
    assert brc._format_round_paper_hint(tmp_path) is None


# ---- format_run_context_md 字段注入渲染 ----

def test_md_renders_paper_hint_as_own_section():
    """ctx 带 paper_hint → md 有独立 ### paper_hint 段（字段注入）。"""
    md = brc.format_run_context_md({
        "round_decision": "keep_suggestion=keep exp=x reason=...",
        "paper_hint": "FooNet with attention gating.",
    })
    assert "### paper_hint" in md
    assert "FooNet with attention gating." in md
    # round_decision 行原样保留（字段注入不污染决策行）
    assert "keep_suggestion=keep exp=x" in md


def test_md_omits_paper_hint_when_empty():
    """无 paper_hint → md 无该段（不渲染空段）。"""
    md = brc.format_run_context_md({"round_decision": "keep_suggestion=discard exp=y"})
    assert "### paper_hint" not in md


# ---- build_run_context wiring ----

def test_build_run_context_includes_paper_hint(tmp_path):
    """build_run_context 从 round_decision.json 收 paper_hint 进 ctx（端到端 wiring）。"""
    _write_round_decision(tmp_path, {
        "keep_suggestion": True,
        "paper_hint": "BarNet method excerpt here.",
        "evidence_refs": [{"title": "BarNet", "url": "https://arxiv.org/abs/2402.00002"}],
    })
    # results.tsv 缺只产生 warning，不阻断 ctx 构建
    ctx = brc.build_run_context(tmp_path)
    assert ctx.get("paper_hint") == "BarNet method excerpt here."


def test_build_run_context_omits_paper_hint_when_absent(tmp_path):
    """无 paper_hint → ctx 无该键（md 也不渲染）。"""
    _write_round_decision(tmp_path, {"keep_suggestion": False})
    ctx = brc.build_run_context(tmp_path)
    assert "paper_hint" not in ctx
