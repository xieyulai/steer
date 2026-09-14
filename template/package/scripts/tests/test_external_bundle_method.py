"""Ticket 01 (#02→bundle): PDF 抽出的 method_excerpt / impl_hints 落进外部证据包。

喂入层闭环最后一环：Slice 2 让 fetch_arxiv_excerpt 产出 method_excerpt/impl_hints，
本切片把它们写进 bundle['paper']（落盘 saved/external_evidence/{reflect_id}.json），
下游主体闭环（ticket 05）才能读到论文方法。

不触网：mock search_arxiv / search_openalex / fetch_arxiv_excerpt。
paper_depth=P3 触发 PDF 分支（_paper_depth_rank>=3）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.external import executor as exec_mod
from lib.external.executor import execute_plan
from lib.external.models import ExternalPlan, ToolResult, empty_bundle


def _make_plan(*, paper_depth="P3") -> ExternalPlan:
    return ExternalPlan(
        schema_version=1,
        round_state={"round": 1},
        paper_depth=paper_depth,
        paper_hits_cap=5,
        docs_depth="D0",
        github_impl=False,
        github_ecosystem=False,
        budget_max_http=10,
        queries={"paper": "residual attention network"},
    )


def test_empty_bundle_paper_has_method_fields():
    """bundle['paper'] 默认带 method_excerpt=None / impl_hints=[]（schema 完整）。"""
    plan = _make_plan()
    paper = empty_bundle(plan=plan)["paper"]
    assert "method_excerpt" in paper
    assert paper["method_excerpt"] is None
    assert paper["impl_hints"] == []


def test_pdf_method_excerpt_lands_in_bundle(monkeypatch):
    """PDF 分支抽出的 method_excerpt / impl_hints 写进 bundle['paper']。"""

    def fake_arxiv(query, *, max_results=5):
        return [{"title": "FooNet", "abstract": "a b c d e",
                 "arxiv_id": "2401.00001", "sources": ["arxiv"]}]

    def fake_openalex(query, *, max_results=5):
        return []

    def fake_pdf(aid, *, max_chars=4000, timeout_sec=300.0, persist_dir=None, repo_root=None):
        return ToolResult(
            status="ok", provider="pdf", excerpt="raw excerpt text",
            method_excerpt="We propose FooNet with attention gating.",
            impl_hints=["Adam optimizer", "learning rate 1e-3"],
            local_path="saved/external_evidence/pdfs/2401.00001.pdf",
            http_calls=1,
        )

    monkeypatch.setattr(exec_mod, "search_arxiv", fake_arxiv)
    monkeypatch.setattr(exec_mod, "search_openalex", fake_openalex)
    monkeypatch.setattr(exec_mod, "fetch_arxiv_excerpt", fake_pdf)

    plan = _make_plan(paper_depth="P3")
    bundle = execute_plan(plan, has_serper=False)  # no_serper 路径

    paper = bundle["paper"]
    assert paper["pdf_arxiv_id"] == "2401.00001", "PDF 分支应已触发"
    assert paper["method_excerpt"] is not None
    assert "FooNet" in paper["method_excerpt"]
    assert paper["impl_hints"], "impl_hints 应非空"
    assert any("Adam" in h for h in paper["impl_hints"])
