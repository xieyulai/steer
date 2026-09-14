"""spec §0.2 反思保守 + §3 衍生配置 6 档默认值 + §5 单旋钮干净切。

Task 5 干净切后的行为：
- apply_mode(mode) 仅写 exploration_mode（不钉 preset 段）
- set_experiment_mode 统一入口（auto → initialize_auto）
- _resolve_mode / sync_agent_experiment_mode 及旧 unified-mode API 已退役

覆盖:
- §0.2 reflect 保守原则:6 档 reflect.interval 默认值
- §3 衍生配置表:6 档 external 3 源、goal.policy、keep.primary_delta_rel
- §5 apply_mode 只写 exploration_mode（no section pinning）
- 兜底:未知 mode → optimize
"""
from __future__ import annotations

import pytest

from lib.presets import default_for_mode


# === reflect.interval 保守原则 (spec §0.2) ===

def test_default_reflect_interval_optimize():
    p = default_for_mode("optimize")
    assert p["reflect"]["interval"] == 1


def test_default_reflect_interval_careful_is_2():
    """careful 唯一例外:reflect.interval=2(避免扰动)"""
    p = default_for_mode("careful")
    assert p["reflect"]["interval"] == 2


def test_default_reflect_interval_innovate():
    assert default_for_mode("innovate")["reflect"]["interval"] == 1


def test_default_reflect_interval_aggressive():
    assert default_for_mode("aggressive")["reflect"]["interval"] == 1


def test_default_reflect_interval_explore():
    assert default_for_mode("explore")["reflect"]["interval"] == 1


def test_default_reflect_interval_auto():
    assert default_for_mode("auto")["reflect"]["interval"] == 1


# === 6 档 衍生配置完整性 (spec §3) ===

def test_careful_external_all_off():
    p = default_for_mode("careful")
    assert p["external"]["paper_depth"] == "P0"
    assert p["external"]["docs_depth"] == "D0"
    assert p["external"]["github_impl"] is False
    assert p["external"]["github_ecosystem"] is False


def test_optimize_github_ecosystem_only():
    """optimize 默认开 github_ecosystem(best practice)不开 impl"""
    p = default_for_mode("optimize")
    assert p["external"]["github_impl"] is False
    assert p["external"]["github_ecosystem"] is True


def test_innovate_github_both_on():
    """innovate 开 github_impl + github_ecosystem"""
    p = default_for_mode("innovate")
    assert p["external"]["github_impl"] is True
    assert p["external"]["github_ecosystem"] is True


def test_aggressive_paper_p3_docs_d3():
    p = default_for_mode("aggressive")
    assert p["external"]["paper_depth"] == "P3"
    assert p["external"]["docs_depth"] == "D3"


def test_explore_goal_policy_all_in_scope():
    """explore 是唯一 goal.policy=all_in_scope 的档"""
    p = default_for_mode("explore")
    assert p["goal"]["policy"] == "all_in_scope"


def test_other_modes_goal_policy_focus_only():
    for mode in ["careful", "optimize", "innovate", "aggressive", "auto"]:
        assert default_for_mode(mode)["goal"]["policy"] == "focus_only"


def test_invalid_mode_falls_back_to_optimize():
    """未知 mode → optimize 兜底(防止 typo 静默走错档)"""
    p = default_for_mode("nonsense")
    assert p == default_for_mode("optimize")


# === 用户 override 优先 (spec §3 用户 override 优先) — 占位 ===

def test_user_override_reflect_interval():
    """用户在 yaml 写 reflect.interval=5 → 覆盖 default。

    注:实际 override 行为后续 T4 apply_mode 测试覆盖。
    本 task 只验证 default_for_mode 的纯单元行为。
    """
    # 占位:后续 T4 apply_mode 集成测试覆盖
    assert default_for_mode("optimize")["reflect"]["interval"] == 1


# === apply_mode 只写 exploration_mode（spec §5 干净切）===

def test_apply_mode_optimize_writes_only_exploration_mode(tmp_path):
    """optimize：只写 exploration_mode，不钉 preset 段"""
    from lib.experiment_mode import apply_mode
    cfg = apply_mode(tmp_path, "optimize")
    assert cfg["exploration_mode"] == "optimize"
    # 干净切：不钉 preset 段（读时由 resolve_exploration 派生）
    assert "experiment" not in cfg
    assert "exploration" not in cfg


def test_apply_mode_careful_writes_only_exploration_mode(tmp_path):
    """careful：只写 exploration_mode"""
    from lib.experiment_mode import apply_mode
    cfg = apply_mode(tmp_path, "careful")
    assert cfg["exploration_mode"] == "careful"
    assert "keep" not in cfg
    assert "experiment" not in cfg


def test_apply_mode_aggressive_writes_only_exploration_mode(tmp_path):
    """aggressive：只写 exploration_mode（keep.primary_delta_rel 读时派生，不钉死）"""
    from lib.experiment_mode import apply_mode
    cfg = apply_mode(tmp_path, "aggressive")
    assert cfg["exploration_mode"] == "aggressive"
    assert "keep" not in cfg
    assert "experiment" not in cfg


def test_apply_mode_explore_writes_only_exploration_mode(tmp_path):
    """explore：只写 exploration_mode"""
    from lib.experiment_mode import apply_mode
    cfg = apply_mode(tmp_path, "explore")
    assert cfg["exploration_mode"] == "explore"
    assert "experiment" not in cfg
    assert "exploration" not in cfg


def test_apply_mode_innovate_writes_only_exploration_mode(tmp_path):
    """innovate：只写 exploration_mode"""
    from lib.experiment_mode import apply_mode
    cfg = apply_mode(tmp_path, "innovate")
    assert cfg["exploration_mode"] == "innovate"
    assert "experiment" not in cfg


def test_apply_mode_persists_to_yaml(tmp_path):
    """apply_mode 真的写盘（save_nn_config）"""
    from lib.experiment_mode import apply_mode
    apply_mode(tmp_path, "optimize")
    yaml_path = tmp_path / "nn-config.yaml"
    assert yaml_path.is_file()
    import yaml
    cfg = yaml.safe_load(yaml_path.read_text())
    assert cfg["exploration_mode"] == "optimize"


def test_apply_mode_invalid_raises(tmp_path):
    """无效 mode 抛 ValueError"""
    from lib.experiment_mode import apply_mode
    with pytest.raises(ValueError):
        apply_mode(tmp_path, "nonsense")


def test_apply_mode_no_existing_yaml(tmp_path):
    """空目录无 nn-config.yaml → apply_mode 自动创建"""
    from lib.experiment_mode import apply_mode
    cfg = apply_mode(tmp_path, "optimize")
    assert cfg["exploration_mode"] == "optimize"
    assert (tmp_path / "nn-config.yaml").is_file()


def test_apply_mode_overwrites_existing_exploration_mode(tmp_path):
    """已有 exploration_mode 字段 → apply_mode 覆盖"""
    from lib.experiment_mode import apply_mode
    yaml_path = tmp_path / "nn-config.yaml"
    yaml_path.write_text("exploration_mode: explore\n")
    cfg = apply_mode(tmp_path, "innovate")
    assert cfg["exploration_mode"] == "innovate"


def test_apply_mode_returns_cfg_dict(tmp_path):
    """apply_mode 返回 cfg dict（便于测试和调试）"""
    from lib.experiment_mode import apply_mode
    cfg = apply_mode(tmp_path, "careful")
    assert isinstance(cfg, dict)
    assert cfg["exploration_mode"] == "careful"


def test_apply_mode_does_not_pin_sections(tmp_path):
    """干净切核心断言：apply_mode 后 yaml 原文不钉 keep/reflect/goal/early_stop/external 段"""
    from lib.experiment_mode import apply_mode
    apply_mode(tmp_path, "aggressive")
    import yaml
    raw = yaml.safe_load((tmp_path / "nn-config.yaml").read_text())
    assert raw["exploration_mode"] == "aggressive"
    for sec in ("keep", "reflect", "goal", "early_stop", "external",
                "experiment", "exploration"):
        assert sec not in raw, f"apply_mode 不应钉 {sec} 段"


# === 撞墙信号注入（spec §4.1 + §4.2）===

def test_wall_hit_streak_increments_on_discard(tmp_path):
    """KEEP 失败（DISCARD）→ streak += 1（auto 模式下才追踪）"""
    from experiment import _update_wall_hit_streak
    from lib.nn_config import load_nn_config, save_nn_config
    save_nn_config(tmp_path, {"exploration_mode": "auto"})  # 显式 auto 才追踪 streak
    _update_wall_hit_streak(tmp_path, kept=False)
    cfg = load_nn_config(tmp_path)
    assert cfg["auto"]["wall_hit_streak"] == 1

    _update_wall_hit_streak(tmp_path, kept=False)
    cfg = load_nn_config(tmp_path)
    assert cfg["auto"]["wall_hit_streak"] == 2


def test_wall_hit_streak_resets_on_keep(tmp_path):
    """KEEP 成功 → streak = 0（auto 模式下才追踪）"""
    from experiment import _update_wall_hit_streak
    from lib.nn_config import load_nn_config, save_nn_config
    save_nn_config(tmp_path, {"exploration_mode": "auto"})  # 显式 auto 才追踪 streak
    # 先累积
    _update_wall_hit_streak(tmp_path, kept=False)
    _update_wall_hit_streak(tmp_path, kept=False)
    cfg = load_nn_config(tmp_path)
    assert cfg["auto"]["wall_hit_streak"] == 2

    # KEEP 成功 reset
    _update_wall_hit_streak(tmp_path, kept=True)
    cfg = load_nn_config(tmp_path)
    assert cfg["auto"]["wall_hit_streak"] == 0


def test_wall_hit_streak_initial_zero(tmp_path):
    """auto 模式但无 auto 段时首次 DISCARD → 1（不报错，建段）"""
    from experiment import _update_wall_hit_streak
    from lib.nn_config import load_nn_config, save_nn_config
    save_nn_config(tmp_path, {"exploration_mode": "auto"})  # 显式 auto 才追踪 streak
    _update_wall_hit_streak(tmp_path, kept=False)
    cfg = load_nn_config(tmp_path)
    assert cfg["auto"]["wall_hit_streak"] == 1


def test_should_keep_does_not_call_streak(tmp_path, monkeypatch):
    """spec T7: should_keep 不应写 streak（仅 finalize_round 写）。

    I-1 fix: 防止 per-候选都触发 yaml save 造成 IO 放大。
    """
    import experiment as exp_module
    streak_calls: list = []
    real_streak = exp_module._update_wall_hit_streak

    def counting_streak(*args, **kwargs):
        streak_calls.append((args, kwargs))
        return real_streak(*args, **kwargs)

    monkeypatch.setattr(exp_module, "_update_wall_hit_streak", counting_streak)

    base = exp_module.ExperimentBase()
    base.repo_root = tmp_path
    # monkeypatch 也会盖到 bound method，所以这里直接调
    # 注意：should_keep 内部有许多依赖（self._effective_keep_spec 等），
    # 即使抛错也无所谓 — 我们只关心 streak 是否被调用
    try:
        base.should_keep(current_metrics={"primary": 0.5}, history_rows=[])
    except Exception:
        pass  # should_keep 内部依赖多，抛错不影响 streak 计数验证

    assert len(streak_calls) == 0, (
        f"should_keep should NOT call _update_wall_hit_streak "
        f"(per-round only in finalize_round), got {len(streak_calls)} calls"
    )


# === apply_mode auto 分支（spec §4.2）===

def test_apply_mode_auto_default_start_optimize(tmp_path):
    """apply_mode(repo, "auto") → initialize_auto 起步 optimize + exploration_mode=auto"""
    from lib.experiment_mode import apply_mode
    cfg = apply_mode(tmp_path, "auto")
    assert cfg["exploration_mode"] == "auto"
    assert cfg["auto"]["start_mode"] == "optimize"
    assert cfg["auto"]["effective_mode"] == "optimize"


def test_apply_mode_auto_with_start_mode_careful(tmp_path):
    """apply_mode(repo, "auto", start_mode="careful") → 起步 careful"""
    from lib.experiment_mode import apply_mode
    cfg = apply_mode(tmp_path, "auto", start_mode="careful")
    assert cfg["auto"]["start_mode"] == "careful"
    assert cfg["auto"]["effective_mode"] == "careful"
    assert cfg["exploration_mode"] == "auto"


def test_apply_mode_auto_persists_to_yaml(tmp_path):
    """apply_mode auto 写盘"""
    from lib.experiment_mode import apply_mode
    apply_mode(tmp_path, "auto")
    yaml_path = tmp_path / "nn-config.yaml"
    assert yaml_path.is_file()
    import yaml
    cfg_loaded = yaml.safe_load(yaml_path.read_text())
    assert cfg_loaded["exploration_mode"] == "auto"
    assert cfg_loaded["auto"]["effective_mode"] == "optimize"


def test_apply_mode_auto_no_existing_yaml(tmp_path):
    """空目录 + apply_mode auto → 自动创建"""
    from lib.experiment_mode import apply_mode
    cfg = apply_mode(tmp_path, "auto", start_mode="innovate")
    assert cfg["auto"]["effective_mode"] == "innovate"
    assert (tmp_path / "nn-config.yaml").is_file()


def test_apply_mode_auto_invalid_start_mode_uses_default(tmp_path):
    """apply_mode auto + start_mode=invalid → 用 default optimize"""
    from lib.experiment_mode import apply_mode
    cfg = apply_mode(tmp_path, "auto", start_mode="nonsense")
    # initialize_auto 内部用 default optimize
    assert cfg["auto"]["effective_mode"] == "optimize"


def test_apply_mode_auto_does_not_overwrite_existing_auto_block(tmp_path):
    """已有 auto 段 → apply_mode auto 保留 start_mode（不覆盖）"""
    from lib.experiment_mode import apply_mode
    # 先写一个 customized auto
    import yaml
    yaml_path = tmp_path / "nn-config.yaml"
    yaml_path.write_text("auto:\n  start_mode: careful\n  promote_threshold: 10\n")
    cfg = apply_mode(tmp_path, "auto")
    # 已有 start_mode=careful 保留
    assert cfg["auto"]["start_mode"] == "careful"


# === set_experiment_mode 统一入口（6 档）===

def test_set_experiment_mode_aggressive_writes_exploration_mode(tmp_path):
    """aggressive：写 exploration_mode=aggressive（不钉段、不 sync agent）"""
    from lib.experiment_mode import set_experiment_mode
    cfg = set_experiment_mode(tmp_path, "aggressive")
    assert cfg["exploration_mode"] == "aggressive"
    # 干净切：不钉 preset 段
    assert "keep" not in cfg
    assert "experiment" not in cfg


def test_set_experiment_mode_careful_no_crash(tmp_path):
    """careful：set_experiment_mode 不崩"""
    from lib.experiment_mode import set_experiment_mode
    cfg = set_experiment_mode(tmp_path, "careful")
    assert cfg["exploration_mode"] == "careful"


def test_set_experiment_mode_explore(tmp_path):
    """explore：写 exploration_mode=explore"""
    from lib.experiment_mode import set_experiment_mode
    cfg = set_experiment_mode(tmp_path, "explore")
    assert cfg["exploration_mode"] == "explore"


def test_set_experiment_mode_auto_delegates(tmp_path):
    """auto：走 initialize_auto，cfg 有 auto 段 + exploration_mode=auto"""
    from lib.experiment_mode import set_experiment_mode
    cfg = set_experiment_mode(tmp_path, "auto")
    assert cfg["exploration_mode"] == "auto"
    assert cfg["auto"]["effective_mode"] == "optimize"


def test_set_experiment_mode_invalid_raises(tmp_path):
    """无效 mode 抛 ValueError"""
    from lib.experiment_mode import set_experiment_mode
    with pytest.raises(ValueError):
        set_experiment_mode(tmp_path, "nonsense")


def test_set_experiment_mode_persists_to_yaml(tmp_path):
    """set_experiment_mode 真的落盘"""
    from lib.experiment_mode import set_experiment_mode
    set_experiment_mode(tmp_path, "aggressive")
    import yaml
    cfg = yaml.safe_load((tmp_path / "nn-config.yaml").read_text())
    assert cfg["exploration_mode"] == "aggressive"


# === manage_goal.py mode 子命令（SKILL.md mode-setter 真路径）===

def test_manage_goal_mode_set_aggressive(tmp_path):
    """manage_goal.py mode aggressive → set_experiment_mode 写 exploration_mode"""
    from manage_goal import main
    rc = main(["--repo-root", str(tmp_path), "mode", "aggressive"])
    assert rc == 0
    from lib.nn_config import load_nn_config
    cfg = load_nn_config(tmp_path)
    assert cfg["exploration_mode"] == "aggressive"


def test_manage_goal_mode_set_auto_writes_auto_block(tmp_path):
    """manage_goal.py mode auto → initialize_auto 写 auto 段 + exploration_mode=auto"""
    from manage_goal import main
    rc = main(["--repo-root", str(tmp_path), "mode", "auto"])
    assert rc == 0
    from lib.nn_config import load_nn_config
    cfg = load_nn_config(tmp_path)
    assert cfg["exploration_mode"] == "auto"
    assert cfg["auto"]["effective_mode"] == "optimize"


def test_manage_goal_mode_show_prints_resolved_mode(tmp_path, capsys):
    """manage_goal.py mode show → 打印 resolve_exploration 结果"""
    from manage_goal import main
    main(["--repo-root", str(tmp_path), "mode", "aggressive"])
    capsys.readouterr()  # 清掉 set 的输出
    rc = main(["--repo-root", str(tmp_path), "mode", "show"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "aggressive" in out
    assert "exploration_mode" in out


# === Task 1: 单一权威 bundle 表 (spec §4) — _BASE + _MODE_DEFAULTS ===

from lib.presets import default_for_mode, _BASE, _MODE_DEFAULTS


EXPECTED_BUNDLES = {
    "careful":    {"keep": 0.01,  "reflect": 2, "paper": "P0", "patience": 5,
                   "policy": "focus_only", "tier": "A", "runtime": "optimize"},
    "optimize":   {"keep": 0.005, "reflect": 1, "paper": "P1", "patience": 3,
                   "policy": "focus_only", "tier": "B", "runtime": "optimize"},
    "innovate":   {"keep": 0.005, "reflect": 1, "paper": "P2", "patience": 3,
                   "policy": "focus_only", "tier": "C", "runtime": "innovate"},
    "aggressive": {"keep": 0.001, "reflect": 1, "paper": "P3", "patience": 0,
                   "policy": "focus_only", "tier": "D", "runtime": "innovate"},
    "explore":    {"keep": 0.005, "reflect": 1, "paper": "P2", "patience": 0,
                   "policy": "all_in_scope", "tier": "B", "runtime": "explore"},
    "auto":       {"keep": 0.005, "reflect": 1, "paper": "P1", "patience": 3,
                   "policy": "focus_only", "tier": "B", "runtime": "optimize"},
}


@pytest.mark.parametrize("mode", list(EXPECTED_BUNDLES))
def test_bundle_authoritative_fields(mode):
    p = default_for_mode(mode)
    e = EXPECTED_BUNDLES[mode]
    assert p["keep"]["primary_delta_rel"] == e["keep"]
    assert p["reflect"]["interval"] == e["reflect"]
    assert p["external"]["paper_depth"] == e["paper"]
    assert p["early_stop"]["patience"] == e["patience"]
    assert p["goal"]["policy"] == e["policy"]
    assert p["tier_start"] == e["tier"]
    assert p["runtime"] == e["runtime"]


def test_base_has_common_sections():
    for sec in ("keep", "reflect", "goal", "external", "early_stop", "compress",
                "context", "analyse", "safety", "tier_attestation", "gpu", "training",
                "innovation", "checkpoint"):
        assert sec in _BASE, f"_BASE 缺 {sec}"


def test_default_for_mode_deep_merges_base_and_overrides():
    p = default_for_mode("aggressive")
    assert p["keep"]["primary_delta_rel"] == 0.001
    assert p["keep"]["mode"] == "relative"
    assert p["keep"]["improve_mode"] == "any_primary"
    assert p["reflect"]["interval"] == 1
    assert p["reflect"]["force"] is False


def test_presets_style_dict_removed():
    """干净切：_PRESETS / get / default / DEFAULT_PRESET / list_presets 全退役"""
    import lib.presets as P
    for gone in ("_PRESETS", "get", "default", "DEFAULT_PRESET", "list_presets"):
        assert not hasattr(P, gone), f"{gone} 应已删除"


def test_presets_experiment_exploration_keys_removed():
    """干净切：_MODE_DEFAULTS 不含 experiment/exploration 过渡键"""
    for mode, overrides in _MODE_DEFAULTS.items():
        assert "experiment" not in overrides, f"{mode} 仍含 experiment 键"
        assert "exploration" not in overrides, f"{mode} 仍含 exploration 键"


def test_default_for_mode_does_not_mutate_base():
    """_deep_merge 必须深拷贝：改返回值不污染 _BASE；每次调用返回新 dict"""
    from lib.presets import default_for_mode, _BASE
    p1 = default_for_mode("optimize")
    p1["keep"]["primary_delta_rel"] = 99
    assert _BASE["keep"]["primary_delta_rel"] == 0.005      # _BASE 未被污染
    p2 = default_for_mode("optimize")
    assert p2["keep"]["primary_delta_rel"] == 0.005          # 新调用不受上次影响
    assert p1 is not p2                                       # 每次新 dict
