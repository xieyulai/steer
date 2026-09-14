"""load_nn_config preset expansion 单测：exploration_mode 选 bundle（Task 3）。

旧探索（exploration.style）已退役；load_nn_config 改为按顶层 ``exploration_mode``
选 ``default_for_mode`` bundle。本文件覆盖：
- ``exploration_mode`` 选对应档 bundle（aggressive → primary_delta_rel=0.001）
- 缺 ``exploration_mode`` → optimize bundle（不 raise；resolve_exploration 才 strict）
- 显式 yaml 段 leaf 覆盖 bundle 默认值（显式 win，bundle 其余字段保留）
"""
from __future__ import annotations

from pathlib import Path

from lib.nn_config import load_nn_config


def test_load_yaml_expands_by_exploration_mode(tmp_path):
    """exploration_mode 选 bundle（替代旧 exploration.style）"""
    (tmp_path / "nn-config.yaml").write_text(
        "profile: supervised\nexploration_mode: aggressive\n", encoding="utf-8")
    cfg = load_nn_config(tmp_path)
    for key in ("keep", "reflect", "compress", "context", "analyse",
                "safety", "innovation", "tier_attestation", "gpu", "training",
                "external", "goal", "early_stop"):
        assert key in cfg
    assert cfg["keep"]["primary_delta_rel"] == 0.001   # aggressive bundle


def test_missing_exploration_mode_defaults_optimize(tmp_path):
    """load_nn_config 缺 exploration_mode → optimize bundle（不 raise；resolve_exploration 才 strict）"""
    (tmp_path / "nn-config.yaml").write_text("profile: supervised\n", encoding="utf-8")
    cfg = load_nn_config(tmp_path)
    assert cfg["keep"]["primary_delta_rel"] == 0.005   # optimize/balanced base


def test_explicit_leaf_overrides_bundle(tmp_path):
    (tmp_path / "nn-config.yaml").write_text(
        "profile: supervised\nexploration_mode: optimize\n"
        "keep:\n  primary_delta_rel: 0.02\n", encoding="utf-8")
    cfg = load_nn_config(tmp_path)
    assert cfg["keep"]["primary_delta_rel"] == 0.02   # 显式 win
    assert cfg["keep"]["mode"] == "relative"          # bundle 保留


def test_exploration_mode_normalized_case_and_whitespace(tmp_path):
    """strip().lower() 归一化：大写+空格 → 正确 bundle（锁契约，防 Task 5 清理回归）"""
    (tmp_path / "nn-config.yaml").write_text(
        'profile: supervised\nexploration_mode: "  AGGRESSIVE  "\n', encoding="utf-8")
    cfg = load_nn_config(tmp_path)
    assert cfg["keep"]["primary_delta_rel"] == 0.001   # aggressive bundle


def test_exploration_mode_empty_string_defaults_optimize(tmp_path):
    """显式空串 → optimize 基底（不 raise）"""
    (tmp_path / "nn-config.yaml").write_text(
        'profile: supervised\nexploration_mode: ""\n', encoding="utf-8")
    cfg = load_nn_config(tmp_path)
    assert cfg["keep"]["primary_delta_rel"] == 0.005   # optimize 基底
