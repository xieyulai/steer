"""spec §4.2 + §5：auto 模式撞墙升档 + effective_mode 跟踪。

Task 5 干净切后的行为：
- initialize_auto：写 exploration_mode="auto" + auto 段（effective_mode=start_mode）
- check_and_promote_auto：仅 bump auto.effective_mode + reset streak（不调 apply_mode / 不钉段）
- is_auto_mode：判 exploration_mode=="auto" 或 auto 段存在

覆盖：
- 升档链 PROMOTE_CHAIN：optimize → innovate → aggressive（不含 explore / careful）
- initialize_auto：默认 optimize，start_mode 可显式指定
- check_and_promote_auto：撞墙 promote_threshold 轮 → 升档；aggressive 撞墙 → 保持
- is_auto_mode：判断 exploration_mode=="auto"
"""
from __future__ import annotations

import yaml

from lib.auto_mode import (
    PROMOTE_CHAIN,
    check_and_promote_auto,
    initialize_auto,
    is_auto_mode,
)
from lib.nn_config import load_nn_config, save_nn_config


# === 升档链 ===

def test_promote_chain_optimize_to_innovate():
    """升档链：optimize → innovate"""
    assert PROMOTE_CHAIN["optimize"] == "innovate"


def test_promote_chain_innovate_to_aggressive():
    """升档链：innovate → aggressive"""
    assert PROMOTE_CHAIN["innovate"] == "aggressive"


def test_promote_chain_no_explore():
    """升档链不含 explore（哲学冲突）"""
    assert "explore" not in PROMOTE_CHAIN
    assert "explore" not in PROMOTE_CHAIN.values()


def test_promote_chain_no_careful():
    """升档链不含 careful（用户主动选 = 已最保守）"""
    assert "careful" not in PROMOTE_CHAIN


# === initialize_auto ===

def test_initialize_auto_default_start_optimize(tmp_path):
    """initialize_auto() 默认起步 optimize"""
    cfg = initialize_auto(tmp_path)
    auto = cfg["auto"]
    assert auto["start_mode"] == "optimize"
    assert auto["effective_mode"] == "optimize"
    assert cfg["exploration_mode"] == "auto"  # 单旋钮记 auto


def test_initialize_auto_with_start_mode_careful(tmp_path):
    """initialize_auto(start_mode="careful") → 起步 careful"""
    cfg = initialize_auto(tmp_path, start_mode="careful")
    assert cfg["auto"]["start_mode"] == "careful"
    assert cfg["auto"]["effective_mode"] == "careful"
    assert cfg["exploration_mode"] == "auto"


def test_initialize_auto_explicit_auto_uses_default(tmp_path):
    """initialize_auto(start_mode="auto") → 用 default optimize"""
    cfg = initialize_auto(tmp_path, start_mode="auto")
    assert cfg["auto"]["effective_mode"] == "optimize"
    assert cfg["exploration_mode"] == "auto"


def test_initialize_auto_persists_to_yaml(tmp_path):
    """initialize_auto 写盘"""
    initialize_auto(tmp_path)
    yaml_path = tmp_path / "nn-config.yaml"
    assert yaml_path.is_file()
    cfg = yaml.safe_load(yaml_path.read_text())
    assert cfg["auto"]["effective_mode"] == "optimize"
    assert cfg["exploration_mode"] == "auto"


# === check_and_promote_auto ===

def test_check_promote_wall_hit_threshold_promotes(tmp_path):
    """撞墙 promote_threshold 轮 → 升档"""
    initialize_auto(tmp_path)
    # 模拟 T7 _update_wall_hit_streak 累积 streak=5
    cfg = load_nn_config(tmp_path)
    cfg["auto"]["wall_hit_streak"] = 5
    save_nn_config(tmp_path, cfg)

    promoted = check_and_promote_auto(tmp_path)
    assert promoted["auto"]["effective_mode"] == "innovate"
    assert promoted["exploration_mode"] == "auto"  # 保持 auto 不变
    assert promoted["auto"]["wall_hit_streak"] == 0  # reset


def test_check_promote_chain_optimize_to_innovate_to_aggressive(tmp_path):
    """连升两档"""
    initialize_auto(tmp_path)
    cfg = load_nn_config(tmp_path)
    cfg["auto"]["effective_mode"] = "innovate"
    cfg["auto"]["wall_hit_streak"] = 5
    save_nn_config(tmp_path, cfg)

    promoted = check_and_promote_auto(tmp_path)
    assert promoted["auto"]["effective_mode"] == "aggressive"
    assert promoted["exploration_mode"] == "auto"


def test_check_promote_aggressive_does_not_promote(tmp_path):
    """aggressive 撞墙 → 不退"""
    initialize_auto(tmp_path)
    cfg = load_nn_config(tmp_path)
    cfg["auto"]["effective_mode"] = "aggressive"
    cfg["auto"]["wall_hit_streak"] = 5
    save_nn_config(tmp_path, cfg)

    promoted = check_and_promote_auto(tmp_path)
    assert promoted["auto"]["effective_mode"] == "aggressive"  # 保持
    assert promoted["exploration_mode"] == "auto"


def test_check_promote_below_threshold_no_promote(tmp_path):
    """streak < threshold → 不升档"""
    initialize_auto(tmp_path)
    cfg = load_nn_config(tmp_path)
    cfg["auto"]["wall_hit_streak"] = 3  # < 5
    save_nn_config(tmp_path, cfg)

    promoted = check_and_promote_auto(tmp_path)
    assert promoted["auto"]["effective_mode"] == "optimize"  # 仍 optimize
    assert promoted["auto"]["wall_hit_streak"] == 3  # 未 reset


def test_check_promote_writes_yaml(tmp_path):
    """升档后 yaml 有 auto.effective_mode=innovate"""
    initialize_auto(tmp_path)
    cfg = load_nn_config(tmp_path)
    cfg["auto"]["wall_hit_streak"] = 5
    save_nn_config(tmp_path, cfg)

    check_and_promote_auto(tmp_path)

    # 重新读 yaml
    yaml_path = tmp_path / "nn-config.yaml"
    cfg_loaded = yaml.safe_load(yaml_path.read_text())
    assert cfg_loaded["auto"]["effective_mode"] == "innovate"
    assert cfg_loaded["exploration_mode"] == "auto"  # 不变


def test_check_promote_no_explore_in_chain(tmp_path):
    """effective_mode=explore → 不在升档链 → 保持"""
    initialize_auto(tmp_path)
    cfg = load_nn_config(tmp_path)
    cfg["auto"]["effective_mode"] = "explore"
    cfg["auto"]["wall_hit_streak"] = 5
    save_nn_config(tmp_path, cfg)

    promoted = check_and_promote_auto(tmp_path)
    # explore 不在 PROMOTE_CHAIN → 不升
    assert promoted["auto"]["effective_mode"] == "explore"


def test_check_promote_promote_threshold_default_is_5(tmp_path):
    """默认 promote_threshold = 5"""
    initialize_auto(tmp_path)
    cfg = load_nn_config(tmp_path)
    assert cfg["auto"]["promote_threshold"] == 5


def test_check_promote_max_mode_default_is_aggressive(tmp_path):
    """默认 max_mode = aggressive"""
    initialize_auto(tmp_path)
    cfg = load_nn_config(tmp_path)
    assert cfg["auto"]["max_mode"] == "aggressive"


def test_check_promote_does_not_pin_preset_sections(tmp_path):
    """干净切：升档不钉 preset 段到 yaml（bundle 读时由 resolve_exploration 派生）。

    注意：load_nn_config 做 preset expansion（填入 keep/reflect 等），故测试 setup
    用 raw yaml 写 streak（避免 load→save 往返把 preset 段钉死到 yaml）。
    """
    initialize_auto(tmp_path)
    # 用 raw yaml 写 streak（不经 load_nn_config，避免 preset expansion 钉段）
    raw = yaml.safe_load((tmp_path / "nn-config.yaml").read_text())
    raw["auto"]["wall_hit_streak"] = 5
    (tmp_path / "nn-config.yaml").write_text(
        yaml.dump(raw, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    check_and_promote_auto(tmp_path)
    # 读 raw yaml 断言：升档后仍未钉 preset 段
    raw = yaml.safe_load((tmp_path / "nn-config.yaml").read_text())
    assert raw["auto"]["effective_mode"] == "innovate"  # 确认升档确实发生了
    for sec in ("keep", "reflect", "goal", "early_stop", "external",
                "experiment", "exploration"):
        assert sec not in raw, f"check_and_promote_auto 不应钉 {sec} 段"


# === is_auto_mode ===

def test_is_auto_mode_true():
    cfg = {"exploration_mode": "auto"}
    assert is_auto_mode(cfg) is True


def test_is_auto_mode_false_for_5_explicit():
    for mode in ["careful", "optimize", "innovate", "aggressive", "explore"]:
        assert is_auto_mode({"exploration_mode": mode}) is False


def test_is_auto_mode_false_for_empty():
    assert is_auto_mode({}) is False
    assert is_auto_mode({"exploration_mode": "optimize"}) is False


# === 守卫回归（auto-promote 半接线修复后干净切）===

def test_check_promote_non_auto_mode_no_op(tmp_path):
    """is_auto_mode 守卫：显式档（无 auto 段且 exploration_mode!=auto）→ no-op。"""
    save_nn_config(tmp_path, {"exploration_mode": "optimize", "keep": {"primary_delta_rel": 0.01}})
    promoted = check_and_promote_auto(tmp_path)
    assert promoted["exploration_mode"] == "optimize"    # 未改
    assert "auto" not in promoted                        # 未注入 auto 段
    assert promoted["keep"]["primary_delta_rel"] == 0.01  # 未动 keep


def test_is_auto_mode_auto_block_present():
    """运行时判定：exploration_mode=非 auto 但 auto 段存在 → 仍算 auto 模式。"""
    assert is_auto_mode({"exploration_mode": "optimize", "auto": {}}) is True
    assert is_auto_mode({"exploration_mode": "innovate", "auto": {"effective_mode": "innovate"}}) is True


def test_finalize_round_wired_to_check_and_promote_auto():
    """断点① 防半接线回归：experiment.py 源码须含 check_and_promote_auto 调用。"""
    from pathlib import Path

    src = Path(__file__).resolve().parents[2].joinpath("experiment.py").read_text(encoding="utf-8")
    assert "check_and_promote_auto" in src


def test_explicit_mode_not_auto_promoted_after_streak(tmp_path):
    """断点① 守卫集成：显式 optimize 档连撞 6 轮墙 → 不升档、不注入 auto 段。

    _update_wall_hit_streak 对显式档 no-op（is_auto_mode 守卫），故 6 轮 DISCARD
    后 cfg 仍无 auto 段；check_and_promote_auto 的 is_auto_mode 守卫 → no-op，
    exploration_mode 保持 optimize。
    """
    from experiment import _update_wall_hit_streak
    save_nn_config(tmp_path, {"exploration_mode": "optimize"})  # 显式档（非 auto）
    for _ in range(6):
        _update_wall_hit_streak(tmp_path, kept=False)

    promoted = check_and_promote_auto(tmp_path)
    assert promoted["exploration_mode"] == "optimize"   # 未升档
    assert "auto" not in promoted                        # 未注入 auto 段

    cfg = load_nn_config(tmp_path)
    assert cfg["exploration_mode"] == "optimize"
    assert "auto" not in cfg
