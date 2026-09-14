"""T4/ADR-6 Slice：build-run-context 把 round_decision.find_candidates 作字段注入下轮上下文。

反馈边（issue 04 AC4）：寻找阶段（plateau ∧ depth∈{different,novel}）捞的可借力候选部件
→ saved/find_candidates.json → collect_round_evidence → round_decision.find_candidates →
build-run-context 注入下轮 step1（字段注入，与 paper_hint 同通道）。

本切片测 build-run-context 从 _runs/round_decision.json 读 find_candidates 并渲染为 md
独立段；与 test_run_context_paper_hint.py 同型（importlib 按 path 加载连字符脚本）。
"""
import importlib.util
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("_build_run_context_under_test_fc", _SCRIPTS / "build-run-context.py")
brc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(brc)


def _write_round_decision(repo_root: Path, payload: dict) -> None:
    runs = repo_root / "_runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "round_decision.json").write_text(json.dumps(payload), encoding="utf-8")


def _fc(**overrides):
    base = {"triggered": True, "depth": "different"}
    base.update(overrides)
    return base


# ---- _format_round_find_candidates reader ----

def test_format_round_find_candidates_reads_paper_candidates(tmp_path):
    """triggered + paper_candidates → 渲染出含标题/URL 的 markdown 字符串。"""
    _write_round_decision(tmp_path, {
        "keep_suggestion": False,
        "find_candidates": _fc(paper_candidates=[
            {"title": "CoordAtt", "url": "https://arxiv.org/abs/2103.1", "arxiv_id": "2103.1"},
        ]),
    })
    out = brc._format_round_find_candidates(tmp_path)
    assert out is not None
    assert "CoordAtt" in out
    assert "2103.1" in out


def test_format_round_find_candidates_reads_ecosystem(tmp_path):
    """triggered + ecosystem_candidates（无论文）→ 渲染生态库名。"""
    _write_round_decision(tmp_path, {
        "find_candidates": _fc(ecosystem_candidates=[
            {"name": "coord-att-lib", "url": "http://g/1", "description": "impl"},
        ]),
    })
    out = brc._format_round_find_candidates(tmp_path)
    assert out is not None
    assert "coord-att-lib" in out


def test_format_round_find_candidates_reads_code_candidates(tmp_path):
    """T9：triggered + code_candidates（无论文/生态）→ 渲染 repo/path/url/excerpt。

    端到端反馈边最后一段：P3+ 抓的 linked_code raw 片段经 collect_round_evidence 透传进
    round_decision.find_candidates → 渲染成下轮 agent 可读的「- 代码：」行。修 renderer
    曾静默丢 code_candidates 的缺陷（Spec 复审发现）。
    """
    _write_round_decision(tmp_path, {
        "find_candidates": _fc(code_candidates=[
            {"repo": "owner/repo", "path": "model.py",
             "url": "https://raw/owner/repo/HEAD/model.py",
             "excerpt": "class FooNet(nn.Module): ..."},
        ]),
    })
    out = brc._format_round_find_candidates(tmp_path)
    assert out is not None
    assert "model.py" in out
    assert "owner/repo" in out
    assert "class FooNet" in out  # excerpt 透传


def test_format_round_find_candidates_code_only_not_empty(tmp_path):
    """T9：仅 code_candidates（无论文/生态/方法段）→ 不再 None（None-guard 纳入 code）。

    修前 None-guard `if not paper and not eco and not method` 漏 code → 仅代码候选的本轮
    被当成「没捞到东西」丢掉；修后 code 入守卫，代码候选足以注入下轮。
    """
    _write_round_decision(tmp_path, {
        "find_candidates": _fc(
            paper_candidates=[], ecosystem_candidates=[], method_excerpt="",
            code_candidates=[{"repo": "o/r", "path": "README.md", "excerpt": "x"}],
        ),
    })
    assert brc._format_round_find_candidates(tmp_path) is not None


def test_format_round_find_candidates_missing_file(tmp_path):
    """无 round_decision.json → None。"""
    assert brc._format_round_find_candidates(tmp_path) is None


def test_format_round_find_candidates_not_triggered(tmp_path):
    """triggered=False → None（寻找未触发，下轮不注入）。"""
    _write_round_decision(tmp_path, {"find_candidates": {"triggered": False}})
    assert brc._format_round_find_candidates(tmp_path) is None


def test_format_round_find_candidates_triggered_but_empty(tmp_path):
    """triggered=True 但无任何候选/方法段 → None（本轮没捞到可借力的，不注入噪声）。"""
    _write_round_decision(tmp_path, {
        "find_candidates": _fc(paper_candidates=[], ecosystem_candidates=[], method_excerpt=""),
    })
    assert brc._format_round_find_candidates(tmp_path) is None


def test_format_round_find_candidates_corrupt(tmp_path):
    """损坏 JSON → None 不崩。"""
    runs = tmp_path / "_runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "round_decision.json").write_text("{ not json", encoding="utf-8")
    assert brc._format_round_find_candidates(tmp_path) is None


# ---- format_run_context_md 字段注入渲染 ----

def test_md_renders_find_candidates_as_own_section():
    """ctx 带 find_candidates → md 有独立 ### find_candidates 段。"""
    md = brc.format_run_context_md({
        "round_decision": "keep_suggestion=discard exp=x reason=...",
        "find_candidates": "depth: different\n- 论文：CoordAtt（https://arxiv.org/abs/2103.1）",
    })
    assert "### find_candidates" in md
    assert "CoordAtt" in md
    # round_decision 行原样保留
    assert "keep_suggestion=discard exp=x" in md


def test_md_omits_find_candidates_when_empty():
    """无 find_candidates → md 无该段。"""
    md = brc.format_run_context_md({"round_decision": "keep_suggestion=keep exp=y"})
    assert "### find_candidates" not in md


# ---- build_run_context wiring ----

def test_build_run_context_includes_find_candidates(tmp_path):
    """build_run_context 从 round_decision.json 收 find_candidates 进 ctx（端到端 wiring）。"""
    _write_round_decision(tmp_path, {
        "keep_suggestion": False,
        "find_candidates": _fc(paper_candidates=[{"title": "FooNet", "url": "u"}]),
    })
    ctx = brc.build_run_context(tmp_path)
    assert "find_candidates" in ctx
    assert "FooNet" in ctx["find_candidates"]


def test_build_run_context_omits_find_candidates_when_absent(tmp_path):
    """无 find_candidates → ctx 无该键。"""
    _write_round_decision(tmp_path, {"keep_suggestion": False})
    ctx = brc.build_run_context(tmp_path)
    assert "find_candidates" not in ctx
