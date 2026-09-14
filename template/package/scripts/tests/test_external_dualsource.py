"""Ticket 01 (#01): serper 在场时 _run_paper_scholar_only 双源（Scholar + arXiv）。

根因（#01）：有 serper 时只调 scholar，scholar 命中不带 arxiv_id →
_finish_paper_extras 取 merged[0].arxiv_id 为空 → PDF 全文永不下载、方法段缺失。
修法：scholar 之后再调 arxiv；merge 的 truncate_hits 自动把带 arxiv_id 的命中浮顶，
前列即可带 arxiv_id（PDF 触发的前置条件）。

不触网：mock search_scholar / search_arxiv。paper_depth=P2 避免 PDF 分支（>=3 才下 PDF），
聚焦「双源搜索」本身。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.external import executor as exec_mod
from lib.external.executor import execute_plan
from lib.external.models import ExternalPlan, ToolResult


def _make_plan(*, paper_depth="P2", budget_max_http=10) -> ExternalPlan:
    return ExternalPlan(
        schema_version=1,
        round_state={"round": 1},
        paper_depth=paper_depth,
        paper_hits_cap=5,
        docs_depth="D0",
        github_impl=False,
        github_ecosystem=False,
        budget_max_http=budget_max_http,
        queries={"paper": "residual attention network"},
    )


def test_serper_present_calls_both_scholar_and_arxiv(monkeypatch):
    """AC #1/#6: serper 在场时 Scholar + arXiv 双源都调；AC #2: 前列带 arxiv_id；AC #4: budget 不超。"""
    calls = {"scholar": 0, "arxiv": 0}

    def fake_scholar(query, *, max_results=5):
        calls["scholar"] += 1
        # scholar 命中不带 arxiv_id（Google Scholar 不返回 arxiv_id）— 这正是 #01 根因
        return ToolResult.ok(
            "scholar",
            [{"title": "FooNet: Residual Attention Network", "abstract": "abc",
              "doi": "10.1000/foo", "sources": ["scholar"]}],
            http_calls=1,
        )

    def fake_arxiv(query, *, max_results=5):
        calls["arxiv"] += 1
        return [{"title": "FooNet: Residual Attention Network", "abstract": "abcdef",
                 "arxiv_id": "2401.00001", "sources": ["arxiv"]}]

    monkeypatch.setattr(exec_mod, "search_scholar", fake_scholar)
    monkeypatch.setattr(exec_mod, "search_arxiv", fake_arxiv)

    plan = _make_plan()
    bundle = execute_plan(plan, has_serper=True)

    # AC #1/#6: 双源都调（#01 根因修复点 — 原只单源）
    assert calls["scholar"] == 1, f"scholar 应调一次，实际 {calls['scholar']}"
    assert calls["arxiv"] == 1, f"arxiv 应调一次，实际 {calls['arxiv']}"

    # AC #2: merge 前列带 arxiv_id（PDF 全文下载的前置条件）
    hits = bundle["paper"]["hits"]
    assert hits, "merge 后应有命中"
    assert hits[0].get("arxiv_id"), f"前列命中应带 arxiv_id，实际 {hits[0]}"

    # AC #4: budget 不超
    assert bundle["meta"]["http_calls_used"] <= plan.budget_max_http
