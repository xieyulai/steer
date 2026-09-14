"""experiment.py source_block sidecar 3 个纯函数单测（fork 触发，spec §4 步2→3）。"""
from __future__ import annotations

import json
import os
import sys

_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from experiment import (  # noqa: E402
    SOURCE_BLOCK_BASENAME,
    load_source_block,
    merge_source_block,
    _collect_round_source_block,
)


def test_load_source_block_present(tmp_path):
    d = tmp_path / "exp"
    d.mkdir()
    (d / SOURCE_BLOCK_BASENAME).write_text(
        json.dumps({"blocked": True, "cell": "C-different", "evidence": "tried register + adapter"}), encoding="utf-8"
    )
    sb = load_source_block(d)
    assert sb == {"blocked": True, "cell": "C-different", "evidence": "tried register + adapter"}


def test_load_source_block_missing(tmp_path):
    assert load_source_block(tmp_path / "nope") is None


def test_load_source_block_corrupt(tmp_path):
    d = tmp_path / "exp"; d.mkdir()
    (d / SOURCE_BLOCK_BASENAME).write_text("{not json", encoding="utf-8")
    assert load_source_block(d) is None


def test_load_source_block_non_dict(tmp_path):
    d = tmp_path / "exp"; d.mkdir()
    (d / SOURCE_BLOCK_BASENAME).write_text(json.dumps(["a", "b"]), encoding="utf-8")
    assert load_source_block(d) is None


def test_load_source_block_normalizes_and_clamps(tmp_path):
    d = tmp_path / "exp"; d.mkdir()
    (d / SOURCE_BLOCK_BASENAME).write_text(
        json.dumps({"blocked": 1, "cell": "X" * 100, "evidence": "Y" * 5000}), encoding="utf-8"
    )
    sb = load_source_block(d)
    assert sb["blocked"] is True
    assert len(sb["cell"]) == 32
    assert len(sb["evidence"]) == 2000


def test_merge_source_block_adds_when_present(tmp_path):
    d = tmp_path / "exp"; d.mkdir()
    (d / SOURCE_BLOCK_BASENAME).write_text(
        json.dumps({"blocked": True, "cell": "C-different", "evidence": "register 改不动"}), encoding="utf-8"
    )
    out = merge_source_block({"keep_suggestion": False}, d)
    assert out["source_block"]["blocked"] is True
    assert "source_block" not in merge_source_block({"keep_suggestion": True}, tmp_path / "absent")


def test_collect_round_source_block_first_blocked_wins(tmp_path):
    ok = tmp_path / "s0"; ok.mkdir()
    wall = tmp_path / "s1"; wall.mkdir()
    (wall / SOURCE_BLOCK_BASENAME).write_text(
        json.dumps({"blocked": True, "cell": "D-different", "evidence": "slim 不够"}), encoding="utf-8"
    )
    got = _collect_round_source_block([ok, wall])
    assert got is not None and got["cell"] == "D-different"
    assert _collect_round_source_block([ok]) is None
