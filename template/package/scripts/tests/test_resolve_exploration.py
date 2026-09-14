"""resolve_exploration：exploration_mode → bundle + 运行时旗标（spec §5）。自包含解析。"""
from __future__ import annotations

from pathlib import Path

import pytest

from lib.experiment_mode import resolve_exploration, ExplorationResolution


def _write(repo: Path, body: str) -> Path:
    (repo / "nn-config.yaml").write_text(body, encoding="utf-8")
    return repo


def test_vanilla_mode_resolves_bundle(tmp_path):
    _write(tmp_path, "exploration_mode: innovate\n")
    r = resolve_exploration(tmp_path)
    assert r.mode == "innovate"
    assert r.resolved_mode == "innovate"
    assert r.is_auto is False
    assert r.skip_goal_stop is False
    assert r.innovate_prompt_boost is True
    assert r.tier_start == "C"
    assert r.keep["primary_delta_rel"] == 0.005


def test_explore_skips_goal_stop(tmp_path):
    _write(tmp_path, "exploration_mode: explore\n")
    r = resolve_exploration(tmp_path)
    assert r.skip_goal_stop is True
    assert r.resolved_mode == "explore"
    assert r.goal["policy"] == "all_in_scope"


def test_auto_uses_effective_mode(tmp_path):
    _write(tmp_path, (
        "exploration_mode: auto\n"
        "auto:\n  effective_mode: aggressive\n  start_mode: optimize\n"
        "  promote_threshold: 5\n  max_mode: aggressive\n  wall_hit_streak: 0\n"))
    r = resolve_exploration(tmp_path)
    assert r.is_auto is True
    assert r.resolved_mode == "aggressive"
    assert r.keep["primary_delta_rel"] == 0.001
    assert r.innovate_prompt_boost is True


def test_missing_exploration_mode_raises(tmp_path):
    """no-fallback：旋钮缺失 → KeyError"""
    _write(tmp_path, "profile: supervised\n")
    with pytest.raises(KeyError):
        resolve_exploration(tmp_path)


def test_unknown_mode_falls_back_optimize(tmp_path):
    _write(tmp_path, "exploration_mode: nonsense\n")
    r = resolve_exploration(tmp_path)
    assert r.mode == "nonsense"
    assert r.resolved_mode == "optimize"


def test_leaf_override_wins(tmp_path):
    """用户叶覆盖 presence-check 胜出（spec §6）"""
    _write(tmp_path, "exploration_mode: innovate\nkeep:\n  primary_delta_rel: 0.02\n")
    r = resolve_exploration(tmp_path)
    assert r.keep["primary_delta_rel"] == 0.02
    assert r.reflect["interval"] == 1


def test_returns_exploration_resolution_instance(tmp_path):
    _write(tmp_path, "exploration_mode: optimize\n")
    r = resolve_exploration(tmp_path)
    assert isinstance(r, ExplorationResolution)
    # 所有 dataclass 字段可读
    for f in ("mode", "resolved_mode", "is_auto", "skip_goal_stop",
              "innovate_prompt_boost", "tier_start", "keep", "reflect",
              "goal", "external", "early_stop"):
        assert hasattr(r, f)


def test_auto_missing_effective_mode_falls_back_optimize(tmp_path):
    """auto 无 effective_mode（或缺 auto 段）→ resolved_mode=optimize（spec §8 起步档）"""
    _write(tmp_path, "exploration_mode: auto\n")  # 无 auto: 段
    r = resolve_exploration(tmp_path)
    assert r.is_auto is True
    assert r.resolved_mode == "optimize"
    assert r.tier_start == "B"


def test_non_dict_user_section_ignored_gracefully(tmp_path):
    """用户段写成非 dict（如裸字符串）→ 不 raise，走 bundle 默认"""
    _write(tmp_path, "exploration_mode: optimize\nkeep: not-a-dict\n")
    r = resolve_exploration(tmp_path)
    assert r.keep["primary_delta_rel"] == 0.005   # bundle 默认，未被坏值污染
