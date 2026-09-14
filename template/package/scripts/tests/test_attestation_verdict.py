"""T3：executor.py 的 routine_attestation.verdict 改成 LLM-judged（全文证据，ADR-2）。

旧糙判定 `supported if docs_hits else inconclusive` 换成：喂 method_excerpt（PDF 全文，
P3+ 才有）+ docs 摘要 + paper 摘要给 LLM，判文献是否真背书本轮库/API 用法。
llm_query_fn=None（无 LLM / 测试）→ 回退旧 crude 行为（docs 命中即 supported），不劣化。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.external import executor as exec_mod
from lib.external.executor import (
    _build_attestation_prompt,
    _judge_attestation_verdict,
    _parse_attestation_verdict,
    execute_plan,
)
from lib.external.models import ExternalPlan


# ── _parse_attestation_verdict ────────────────────────────────────────────
def test_parse_supported_variants():
    assert _parse_attestation_verdict("supported") == "supported"
    assert _parse_attestation_verdict("结论: SUPPORTED") == "supported"
    assert _parse_attestation_verdict("yes, the literature supports this usage") == "supported"


def test_parse_inconclusive_or_garbage():
    assert _parse_attestation_verdict("inconclusive") == "inconclusive"
    assert _parse_attestation_verdict("garbage / 无结论") == "inconclusive"
    assert _parse_attestation_verdict("") == "inconclusive"
    assert _parse_attestation_verdict(None) == "inconclusive"


# ── _judge_attestation_verdict ────────────────────────────────────────────
def test_judge_none_llm_crude_fallback():
    """无 LLM → 旧 crude：docs 命中即 supported，否则 inconclusive（不劣化）。"""
    assert _judge_attestation_verdict(
        None, docs_hits=[{"symbol": "x"}], paper_hits=[], method_excerpt=None,
    ) == "supported"
    assert _judge_attestation_verdict(
        None, docs_hits=[], paper_hits=[], method_excerpt=None,
    ) == "inconclusive"


def test_judge_llm_supported_wins_over_crude():
    """LLM 判 supported → supported（即使 docs 空，全文证据背书）。"""
    fn = lambda prompt: "SUPPORTED"
    assert _judge_attestation_verdict(
        fn, docs_hits=[], paper_hits=[{"title": "t"}], method_excerpt="full text",
    ) == "supported"


def test_judge_llm_inconclusive_overrides_crude_supported():
    """LLM 判 inconclusive → inconclusive，即使 docs 命中（糙 crude 会被推翻）。"""
    fn = lambda prompt: "inconclusive"
    assert _judge_attestation_verdict(
        fn, docs_hits=[{"symbol": "x"}], paper_hits=[], method_excerpt=None,
    ) == "inconclusive"


def test_judge_llm_exception_falls_back_crude():
    """LLM 抛错 → 静默回退 crude（外部证据非致命，与 query.py 同模式）。"""
    def boom(prompt):
        raise RuntimeError("agent down")
    # docs 命中 → crude supported
    assert _judge_attestation_verdict(
        boom, docs_hits=[{"symbol": "x"}], paper_hits=[], method_excerpt=None,
    ) == "supported"
    # docs 空 → crude inconclusive
    assert _judge_attestation_verdict(
        boom, docs_hits=[], paper_hits=[], method_excerpt=None,
    ) == "inconclusive"


def test_build_prompt_feeds_full_text_evidence():
    """prompt 必须含 method_excerpt（全文）+ docs + paper 证据。"""
    prompt = _build_attestation_prompt(
        docs_hits=[{"symbol": "nn.CrossEntropyLoss", "doc_excerpt": "combines logsoftmax"}],
        paper_hits=[{"title": "CoordAtt", "abstract": "coordinate attention"}],
        method_excerpt="We propose FooNet using coordinate attention gating.",
    )
    assert "FooNet" in prompt                       # 全文证据进 prompt
    assert "CrossEntropyLoss" in prompt             # docs 证据进 prompt
    assert "CoordAtt" in prompt                     # paper 证据进 prompt
    assert "supported" in prompt.lower() or "背书" in prompt or "佐证" in prompt


# ── execute_plan 接线：verdict 走 llm_query_fn ─────────────────────────────
def _fake_paper(*args, **kwargs):
    """(paper_hits, http, excerpt, impl_cands, pdf_path, arxiv_id, method_excerpt, impl_hints)"""
    return ([{"title": "FooNet", "abstract": "a b c d e"}], 0, None, [], None, None,
            "We propose FooNet with attention gating.", ["Adam"])


def _fake_docs(*args, **kwargs):
    return ([{"symbol": "timm.create_model", "doc_excerpt": "create a model"}], 0)


def _fake_eco(*args, **kwargs):
    return ([], 0)


def _make_plan(paper_depth="P3"):
    return ExternalPlan(
        schema_version=1,
        round_state={"round": 1},
        paper_depth=paper_depth,
        paper_hits_cap=5,
        docs_depth="D2",
        github_impl=False,
        github_ecosystem=False,
        budget_max_http=10,
        queries={"paper": "attention network", "docs_symbols": ["timm.create_model"]},
    )


def test_execute_plan_verdict_uses_llm(monkeypatch):
    """execute_plan 把 llm_query_fn 喂进 verdict（LLM inconclusive 推翻 crude supported）。"""
    monkeypatch.setattr(exec_mod, "_run_paper_no_serper", _fake_paper)
    monkeypatch.setattr(exec_mod, "_run_docs", _fake_docs)
    monkeypatch.setattr(exec_mod, "_run_github_ecosystem", _fake_eco)

    plan = _make_plan("P3")
    bundle = execute_plan(plan, has_serper=False, llm_query_fn=lambda p: "inconclusive")
    assert bundle["code"]["routine_attestation"]["verdict"] == "inconclusive"

    bundle2 = execute_plan(plan, has_serper=False, llm_query_fn=lambda p: "supported")
    assert bundle2["code"]["routine_attestation"]["verdict"] == "supported"


def test_execute_plan_verdict_crude_when_no_llm(monkeypatch):
    """无 llm_query_fn → crude（docs 命中即 supported），保持 v1 行为。"""
    monkeypatch.setattr(exec_mod, "_run_paper_no_serper", _fake_paper)
    monkeypatch.setattr(exec_mod, "_run_docs", _fake_docs)
    monkeypatch.setattr(exec_mod, "_run_github_ecosystem", _fake_eco)

    plan = _make_plan("P3")
    bundle = execute_plan(plan, has_serper=False)  # 默认 llm_query_fn=None
    assert bundle["code"]["routine_attestation"]["verdict"] == "supported"
