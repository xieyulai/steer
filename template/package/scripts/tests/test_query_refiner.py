"""B2 query_refiner.rewrite_for_awesome — 4 case TDD。

Universal: 无 mammoth/fashionmnist 等业务夹具；只用通用 mock llm_query_fn。
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

# 让 import scripts.lib.* 可解析（test 目录 layout: scripts/tests/*.py）
_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.external.query_refiner import rewrite_for_awesome  # noqa: E402


def test_query_refiner_heuristic_only():
    """B2: ctx.rationale 含 pytorch,无 llm_query_fn → 输出含 awesome-pytorch。"""
    ctx = {"rationale": "用 pytorch 实现 ResNet"}
    result = rewrite_for_awesome("ResNet He 2016", ctx=ctx, llm_query_fn=None)
    assert any("awesome-pytorch" in q for q in result), f"未命中 awesome-pytorch: {result}"


def test_query_refiner_llm_path():
    """B2: 注入 fake llm_query_fn 返回多行 awesome → 解析为 list。"""
    ctx = {"rationale": "image classification benchmark"}
    fake_llm = MagicMock(return_value="awesome-image-classification\nawesome-cnn-papers\n")
    result = rewrite_for_awesome("ResNet benchmark", ctx=ctx, llm_query_fn=fake_llm)
    assert "awesome-image-classification" in result
    assert "awesome-cnn-papers" in result
    fake_llm.assert_called_once()


def test_query_refiner_fallback_to_original():
    """B2: llm_query_fn 抛异常 → 走 heuristic + 原始 query。"""
    ctx = {"rationale": "no signal here"}
    fake_llm = MagicMock(side_effect=RuntimeError("provider down"))
    result = rewrite_for_awesome("原始 query", ctx=ctx, llm_query_fn=fake_llm)
    assert "原始 query" in result, f"应回退原始 query: {result}"


def test_query_refiner_disabled_via_env(monkeypatch):
    """B2: NN_QUERY_REFINER_ENABLED=0 → 走原始 query 一项。"""
    monkeypatch.setenv("NN_QUERY_REFINER_ENABLED", "0")
    ctx = {"rationale": "用 pytorch"}
    result = rewrite_for_awesome("原始", ctx=ctx, llm_query_fn=None)
    assert result == ["原始"]