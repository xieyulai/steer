"""query.py LLM 查询增强单测（v2：规则 + LLM 混合）。

LLM 总触发（catalog miss 时）、规则回退。本测覆盖 prompt 构造 + 解析 + 回退链
（LLM 真调由沙箱实证；这里用假 callback 测编排）。
"""
from __future__ import annotations

import os, sys
_PKG = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PKG not in sys.path:
    sys.path.insert(0, _PKG)

from types import SimpleNamespace

from lib.external.query import (
    build_llm_paper_query_prompt,
    build_paper_query,
    parse_llm_paper_query,
)


def _ctx(fingerprint, *, llm_fn=None, task_domain="FashionMNIST 监督图像分类"):
    return SimpleNamespace(
        rationale="", phase2_focus="", fingerprint=fingerprint,
        task_domain=task_domain, llm_query_fn=llm_fn,
    )


# --- build_llm_paper_query_prompt ---

def test_prompt_contains_method_name_and_domain():
    fp = {"reasons": ["new_register:learner:coordatt_se_cnn"], "catalog_hits": []}
    p = build_llm_paper_query_prompt(_ctx(fp))
    assert "coordatt_se_cnn" in p
    assert "coordatt" in p  # 规则 token


def test_prompt_handles_empty_signals():
    p = build_llm_paper_query_prompt(_ctx({"reasons": [], "catalog_hits": []}))
    assert isinstance(p, str) and len(p) > 0  # 不崩


# --- parse_llm_paper_query ---

def test_parse_bare_line():
    assert parse_llm_paper_query("coordinate attention mobile network") == "coordinate attention mobile network"


def test_parse_strips_quotes():
    assert parse_llm_paper_query('  "coordinate attention"  ') == "coordinate attention"


def test_parse_strips_markdown_fence():
    assert parse_llm_paper_query("```json\ncoordinate attention\n```") == "coordinate attention"


def test_parse_json_object():
    assert parse_llm_paper_query('{"query": "squeeze excitation network"}') == "squeeze excitation network"


def test_parse_takes_first_line():
    # LLM 输出查询 + 尾随解释 → 只取首行
    assert parse_llm_paper_query("coordinate attention\n\nThis finds the seminal paper.") == "coordinate attention"


def test_parse_rejects_label_only_and_empty():
    assert parse_llm_paper_query("") == ""
    assert parse_llm_paper_query("查询:") == ""
    assert parse_llm_paper_query("Query") == ""


# --- build_paper_query 编排（用假 llm_fn）---

def test_llm_query_used_when_provided():
    fp = {"reasons": ["new_register:learner:coordatt_se_cnn"], "catalog_hits": []}
    ctx = _ctx(fp, llm_fn=lambda p: "coordinate attention mobile network")
    assert build_paper_query(ctx) == "coordinate attention mobile network"


def test_llm_exception_falls_back_to_rule_token():
    fp = {"reasons": ["new_register:learner:coordatt_se_cnn"], "catalog_hits": []}

    def boom(p):
        raise RuntimeError("timeout")
    ctx = _ctx(fp, llm_fn=boom)
    assert build_paper_query(ctx) == "coordatt"  # 规则层兜底


def test_llm_garbage_falls_back_to_rule_token():
    fp = {"reasons": ["new_register:learner:coordatt_se_cnn"], "catalog_hits": []}
    ctx = _ctx(fp, llm_fn=lambda p: "查询:")  # 解析为空
    assert build_paper_query(ctx) == "coordatt"


def test_catalog_hit_skips_llm():
    # catalog 命中不应调 LLM（已知方法不浪费）
    called = []
    fp = {"catalog_hits": [{"paper_query": "timm efficient model"}], "reasons": []}

    def spy(p):
        called.append(p)
        return "should not be used"
    assert build_paper_query(_ctx(fp, llm_fn=spy)) == "timm efficient model"
    assert called == []  # LLM 未被调用
