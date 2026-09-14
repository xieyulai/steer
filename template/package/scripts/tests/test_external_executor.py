"""C1: _run_docs auto-inference of docs_symbols from ctx (rationale/fingerprint).

Universal mocks only — no business fixtures (no mammoth/fmnist/cifar/resnet/timm
task fixtures); only generic nn.* symbols in mock rationale.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from lib.external import executor
from lib.external.models import ExternalPlan


def _make_plan(*, docs_symbols=None) -> ExternalPlan:
    queries: dict = {}
    if docs_symbols is not None:
        queries["docs_symbols"] = docs_symbols
    return ExternalPlan(
        schema_version=1,
        round_state={},
        paper_depth="P0",
        paper_hits_cap=0,
        docs_depth="D1",  # depth>=1 so _run_docs runs past short-circuit
        github_impl=False,
        github_ecosystem=False,
        budget_max_http=0,
        queries=queries,
    )


def _make_ctx(rationale: str) -> SimpleNamespace:
    return SimpleNamespace(
        rationale=rationale,
        phase2_focus="",
        fingerprint=None,
        task_domain="",
    )


def test_run_docs_auto_infer_from_text():
    plan = _make_plan()  # caller left docs_symbols unset
    ctx = _make_ctx("改用 nn.CrossEntropyLoss 重训")
    with patch.object(executor, "inspect_symbol", return_value={"symbol": "stub"}):
        docs, http = executor._run_docs(plan, skipped=[], http_used=0, ctx=ctx)
    assert "CrossEntropyLoss" in plan.queries["docs_symbols"]
    assert docs  # inspect_symbol ran on the inferred symbol


def test_run_docs_no_inference_when_caller_passed():
    plan = _make_plan(docs_symbols=["ExistingSymbol"])
    ctx = _make_ctx("改用 nn.CrossEntropyLoss 重训")
    with patch.object(executor, "inspect_symbol", return_value={"symbol": "stub"}):
        executor._run_docs(plan, skipped=[], http_used=0, ctx=ctx)
    # caller value must not be overwritten by inference
    assert plan.queries["docs_symbols"] == ["ExistingSymbol"]


def test_run_docs_inference_when_empty():
    plan = _make_plan()  # no docs_symbols
    ctx = _make_ctx("general english text without nn symbols")
    with patch.object(executor, "inspect_symbol", return_value={"symbol": "stub"}):
        docs, http = executor._run_docs(plan, skipped=[], http_used=0, ctx=ctx)
    # nothing inferred → legacy silent-skip, no exception
    assert docs == []
    assert http == 0
    assert not plan.queries.get("docs_symbols")
