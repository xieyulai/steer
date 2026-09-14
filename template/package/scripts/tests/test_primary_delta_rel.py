"""primary_delta_rel 字段重命名（spec §0.1）— 防误读百分点。

核心问题: ``primary_delta`` 字段名暗示「加 1 个百分点」，但实际语义是
**相对值** (``best × (1 + delta)``)。用户在 60% 平台期配 ``primary_delta: 0.01``
会以为是 61%（绝对），实际是 60.6%（相对）。

保守做法：字段重命名 ``keep.primary_delta`` → ``keep.primary_delta_rel``，
老字段作 derived read-only（向后兼容）。

强制验证（spec §0.1 4 个例子防误读）:
- 0.5 (50%) + delta=0.005 = 0.5025（不是 0.505）
- 0.6 (60%) + delta=0.01  = 0.606  (不是 0.61)  ← 关键！
- 0.9 (90%) + delta=0.005 = 0.9045（不是 0.905）
- 0.95(95%) + delta=0.01  = 0.9595（不是 0.96）
"""
from __future__ import annotations

from pathlib import Path

import pytest

from lib.experiment_mode import _resolve_keep_threshold


# ── 核心测试: 4 个比例例子（spec §0.1 强制验证） ─────────────────────────


def test_relative_50pct_with_delta_005():
    """0.5 (50%) + delta=0.005 → 0.5025（不是 0.505）。"""
    assert _resolve_keep_threshold(0.5, 0.005) == pytest.approx(0.5025)


def test_relative_60pct_with_delta_01_key():
    """0.6 (60%) + delta=0.01 → 0.606（不是 0.61）— spec 标为「关键」。"""
    assert _resolve_keep_threshold(0.6, 0.01) == pytest.approx(0.606)


def test_relative_90pct_with_delta_005():
    """0.9 (90%) + delta=0.005 → 0.9045（不是 0.905）。"""
    assert _resolve_keep_threshold(0.9, 0.005) == pytest.approx(0.9045)


def test_relative_95pct_with_delta_01():
    """0.95 (95%) + delta=0.01 → 0.9595（不是 0.96）。"""
    assert _resolve_keep_threshold(0.95, 0.01) == pytest.approx(0.9595)


# ── 边界：default_delta 路径（不传 cfg_path） ────────────────────────────


def test_default_delta_path_no_cfg():
    """不传 cfg_path → 走 default_delta，公式 = best × (1 + delta)。"""
    # 0.6 + 0.005 = 0.603
    assert _resolve_keep_threshold(0.6, 0.005) == pytest.approx(0.603)
    # 0.0 + 任意 delta → best（baseline 无改善也算）
    assert _resolve_keep_threshold(0.7, 0.0) == pytest.approx(0.7)


def test_cfg_path_none_falls_back_to_default():
    """cfg_path=None 显式 → 也走 default_delta。"""
    assert _resolve_keep_threshold(0.5, 0.01, cfg_path=None) == pytest.approx(0.505)


# ── 新字段 primary_delta_rel 优先（spec §0.1 核心：rel 字段） ──────────────


def test_rel_field_from_yaml(tmp_path: Path):
    """nn-config.yaml 写 primary_delta_rel → 用新字段。"""
    cfg = tmp_path / "nn-config.yaml"
    cfg.write_text(
        "keep:\n  primary_delta_rel: 0.02\n",
        encoding="utf-8",
    )
    # 0.5 + 0.02 = 0.51
    assert _resolve_keep_threshold(0.5, 0.005, cfg_path=cfg) == pytest.approx(0.51)


def test_rel_field_overrides_default(tmp_path: Path):
    """primary_delta_rel 覆盖 default_delta。"""
    cfg = tmp_path / "nn-config.yaml"
    cfg.write_text(
        "keep:\n  primary_delta_rel: 0.05\n",
        encoding="utf-8",
    )
    # 0.4 + 0.05 = 0.42
    assert _resolve_keep_threshold(0.4, 0.01, cfg_path=cfg) == pytest.approx(0.42)


# ── 老字段向后兼容（derived read-only, 不报错） ──────────────────────────


def test_legacy_field_still_works(tmp_path: Path):
    """nn-config.yaml 只写老 primary_delta → 仍可读（向后兼容）。"""
    cfg = tmp_path / "nn-config.yaml"
    cfg.write_text(
        "keep:\n  primary_delta: 0.01\n",
        encoding="utf-8",
    )
    # 0.6 + 0.01 = 0.606
    assert _resolve_keep_threshold(0.6, 0.005, cfg_path=cfg) == pytest.approx(0.606)


def test_rel_field_wins_over_legacy(tmp_path: Path):
    """同时写两个字段时，_rel 优先（spec §0.1：derived read-only）。"""
    cfg = tmp_path / "nn-config.yaml"
    cfg.write_text(
        "keep:\n  primary_delta_rel: 0.02\n  primary_delta: 0.01\n",
        encoding="utf-8",
    )
    # 0.5 + 0.02 = 0.51（用 _rel，不用老字段）
    assert _resolve_keep_threshold(0.5, 0.005, cfg_path=cfg) == pytest.approx(0.51)


# ── 缺/坏 cfg 处理 ───────────────────────────────────────────────────────


def test_missing_keep_section_uses_default(tmp_path: Path):
    """cfg 没有 keep 段 → 走 default_delta。"""
    cfg = tmp_path / "nn-config.yaml"
    cfg.write_text("agent:\n  experiment_mode: optimize\n", encoding="utf-8")
    assert _resolve_keep_threshold(0.5, 0.005, cfg_path=cfg) == pytest.approx(0.5025)


def test_empty_keep_section_uses_default(tmp_path: Path):
    """keep 段空 → 走 default_delta。"""
    cfg = tmp_path / "nn-config.yaml"
    cfg.write_text("keep: {}\n", encoding="utf-8")
    assert _resolve_keep_threshold(0.5, 0.01, cfg_path=cfg) == pytest.approx(0.505)


def test_cfg_path_does_not_exist_uses_default(tmp_path: Path):
    """cfg_path 不存在 → 走 default_delta（不抛异常）。"""
    cfg = tmp_path / "does-not-exist.yaml"
    assert _resolve_keep_threshold(0.5, 0.01, cfg_path=cfg) == pytest.approx(0.505)


def test_non_numeric_delta_falls_back_to_default(tmp_path: Path):
    """primary_delta_rel 不是数字 → 走 default_delta。"""
    cfg = tmp_path / "nn-config.yaml"
    cfg.write_text(
        'keep:\n  primary_delta_rel: "0.01"\n',  # 字符串类型，非 (int, float)
        encoding="utf-8",
    )
    assert _resolve_keep_threshold(0.5, 0.005, cfg_path=cfg) == pytest.approx(0.5025)


def test_bool_delta_falls_back_to_default(tmp_path: Path):
    """YAML true/false/yes/no 不应被当作 1.0/0.0。"""
    cfg = tmp_path / "nn-config.yaml"
    cfg.write_text("keep:\n  primary_delta_rel: true\n", encoding="utf-8")
    # 不抛异常，fallback to default_delta=0.005
    assert _resolve_keep_threshold(0.5, 0.005, cfg_path=cfg) == pytest.approx(0.5025)