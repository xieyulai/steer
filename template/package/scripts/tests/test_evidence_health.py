"""D1 external_evidence_health — 4 case TDD。

Universal: 无 mammoth/fashionmnist 等业务夹具；用通用 bundle mock。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# 让 import scripts.lib.* 可解析（test 目录 layout: scripts/tests/*.py）
_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.external.evidence_health import (  # noqa: E402
    summarize_evidence_health,
    write_evidence_health,
)


def _fake_bundle_ok() -> dict:
    return {
        "paper": {"hits": [{"title": "x"}, {"title": "y"}], "excerpt": "m"},
        "code": {"hits": [{"full_name": "a/b"}], "linked_code": {"readme": "..."}},
        "docs": {"hits": [{"title": "doc1"}]},
        "skipped": [],
        "http_used": 4,
    }


def _fake_bundle_partial() -> dict:
    return {
        "paper": {"hits": []},
        "code": {"hits": [{"full_name": "a/b"}]},
        "docs": {"hits": []},
        "skipped": [
            {"provider": "arxiv", "reason": "budget_exceeded"},
            {"provider": "openalex", "reason": "no_key"},
        ],
        "http_used": 1,
    }


def _fake_bundle_empty() -> dict:
    return {"paper": {"hits": []}, "code": {"hits": []}, "docs": {"hits": []}, "skipped": [], "http_used": 0}


def test_evidence_health_all_ok_green():
    """D1: 3 个 provider 都 ok + 无 skipped → health=green。"""
    health = summarize_evidence_health(_fake_bundle_ok(), round_no=5)
    assert health["health"] == "green", f"期望 green: {health}"
    assert health["round"] == 5
    assert health["totals"]["hits"] == 4
    assert health["totals"]["http_calls"] == 4
    assert health["skipped"] == []


def test_evidence_health_partial_yellow():
    """D1: 部分 skipped + 部分 hits → health=yellow。"""
    health = summarize_evidence_health(_fake_bundle_partial(), round_no=6)
    assert health["health"] == "yellow", f"期望 yellow: {health}"
    assert len(health["skipped"]) == 2
    assert any(s["provider"] == "arxiv" for s in health["skipped"])
    assert health["totals"]["hits"] == 1


def test_evidence_health_empty_red():
    """D1: 全 skipped 或全空 → health=red。"""
    health = summarize_evidence_health(_fake_bundle_empty(), round_no=7)
    assert health["health"] == "red", f"期望 red: {health}"
    assert health["totals"]["hits"] == 0


def test_evidence_health_write_to_file(tmp_path):
    """D1: 写盘 saved/external_evidence_health.json。"""
    saved = tmp_path / "saved"
    saved.mkdir()
    out = write_evidence_health(_fake_bundle_ok(), round_no=8, saved_dir=saved)
    assert out.exists(), f"未写盘: {out}"
    parsed = json.loads(out.read_text())
    assert parsed["health"] == "green"
    assert parsed["round"] == 8
