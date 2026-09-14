"""framework overlay（register 上限对象）cell drift-lock（fork 触发，spec §6）。

register 上限对象的 overlay 不应出现越界「→改源码」或废弃标记「_待 reflect 补实_」；
different/derived cell 应是「注册制优先 + 兜底 fork（runtime 触发）」。
"""
from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_OVERLAY = _REPO_ROOT / "skills/maintainer/auto-nn-init/templates/overlay"


def _read(name):
    return (_OVERLAY / name).read_text(encoding="utf-8")


def test_framework_no_vacuous_marker_or_arrow_source():
    c = _read("framework.md")
    assert "_待 reflect 补实_" not in c
    assert "→改源码" not in c
    assert "注册制优先 + 兜底 fork（runtime 触发）" in c
