"""T-C: run_context 靶子段（baseline anchors）渲染。

三态：plain 有值（显示 + 差值）/ plain None（未标定）/ reference 恒 None（② 桩，待 ③-i）。
当前最佳 = anchors_dict(repo_root).metric_leader.value；差值对齐 _goal_gap（正=已超）。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location("_brc_under_test", _SCRIPTS / "build-run-context.py")
brc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(brc)


def _ctx(repo_root: Path) -> dict:
    return {"repo_root": repo_root}


def _write_experience(repo_root: Path, plain_value: float | None) -> None:
    """写带 Tier 状态段的 EXPERIENCE.md（末列 plain(P) 含/不含 plain_anchor_value）。

    6 列：_state_plain_anchor_value 跳过 len(cells) < 6 的行（build-run-context.py:213），
    故 fixture 须 ≥6 列、plain_anchor_value 在末列，以真正走 EXPERIENCE 解析路径。
    """
    p_cell = "-" if plain_value is None else f"plain_anchor_value={plain_value}"
    (repo_root / "EXPERIENCE.md").write_text(
        "## Tier 状态\n"
        "| Tier | routine | extend | novel | extra | plain(P) |\n"
        "|------|---------|--------|-------|-------|----------|\n"
        f"| E    | a       | b      | c     | x     | {p_cell} |\n",
        encoding="utf-8",
    )


def test_plain_value_with_current_best(tmp_path, monkeypatch):
    _write_experience(tmp_path, 0.2845)
    monkeypatch.setattr(brc, "anchors_dict", lambda root: {"metric_leader": {"value": 0.82}})
    out = brc._emit_baseline_anchors(_ctx(tmp_path))
    assert "## 基线靶子 (baseline anchors)" in out
    assert "plain: 0.2845" in out
    assert "已超" in out  # 0.82 > 0.2845
    assert "reference: 未标定" in out  # ② 桩
    assert "当前最佳: 0.8200" in out


def test_plain_none(tmp_path, monkeypatch):
    _write_experience(tmp_path, None)
    monkeypatch.setattr(brc, "anchors_dict", lambda root: {})
    out = brc._emit_baseline_anchors(_ctx(tmp_path))
    assert "plain: 未标定" in out
    assert "当前最佳: （无实验记录）" in out


def test_current_below_plain(tmp_path, monkeypatch):
    _write_experience(tmp_path, 0.9)
    monkeypatch.setattr(brc, "anchors_dict", lambda root: {"metric_leader": {"value": 0.5}})
    out = brc._emit_baseline_anchors(_ctx(tmp_path))
    assert "还差" in out  # 0.5 < 0.9


def test_reference_anchor_stub_returns_none():
    # ② 桩：恒 None，待 ③-i 实现
    assert brc._state_reference_anchor_value({"repo_root": None}) is None
