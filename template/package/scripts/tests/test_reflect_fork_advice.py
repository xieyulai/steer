"""reflect.py fork 触发核验 + 升级建议单测（spec §11 ① + §4 步4）。"""
from __future__ import annotations

import os
import sys

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

import reflect  # noqa: E402


def _rd(evidence, blocked=True, cell="C-different"):
    return {"source_block": {"blocked": blocked, "cell": cell, "evidence": evidence}}


def test_verify_confirmed_when_evidence_names_lightweight():
    ok, reason = reflect.verify_source_block_exhaustion(
        _rd("试过 register 与 adapter shim，均无法表达自定义 loss 组合")
    )
    assert ok is True
    assert "confirmed" in reason


def test_verify_rejects_lazy_no_marker():
    ok, reason = reflect.verify_source_block_exhaustion(_rd("就是改不动，放弃"))
    assert ok is False
    assert "未点名" in reason


def test_verify_rejects_too_short():
    ok, _ = reflect.verify_source_block_exhaustion(_rd("register 不行"))
    assert ok is False


def test_verify_no_source_block():
    ok, _ = reflect.verify_source_block_exhaustion({"keep_suggestion": True})
    assert ok is False
    ok2, _ = reflect.verify_source_block_exhaustion(None)
    assert ok2 is False


def test_verify_not_blocked():
    ok, _ = reflect.verify_source_block_exhaustion(_rd("register 搞定了", blocked=False))
    assert ok is False


def test_advice_produced_when_confirmed():
    advice = reflect._fork_upgrade_advice(_rd("试过 register + adapter，自定义 loss 表达不了"))
    assert "[升级建议]" in advice
    assert "C-different" in advice
    assert "register" in advice and "fork" in advice


def test_advice_empty_when_not_confirmed():
    assert reflect._fork_upgrade_advice(_rd("改不动")) == ""
    assert reflect._fork_upgrade_advice({"keep_suggestion": True}) == ""
