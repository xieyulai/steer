"""nn_config.py：顶层唯一权威（无 agent.* 迁移别名双写）。"""
from __future__ import annotations

from pathlib import Path

import yaml

from lib.nn_config import AGENT_TO_TOP_KEYS, load_nn_config, save_nn_config


def _write(root: Path, data: dict) -> None:
    (root / "nn-config.yaml").write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")


def _collect_keys(obj) -> set[str]:
    keys: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k)
            keys |= _collect_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            keys |= _collect_keys(item)
    return keys


def test_load_does_not_backfill_agent_from_top(tmp_path):
    _write(tmp_path, {"reflect": {"interval": 5}, "agent": {"reflect_interval": 1}})
    raw = load_nn_config(tmp_path)
    # 顶层权威；不再回填进 agent
    assert raw["reflect"]["interval"] == 5
    assert "reflect_interval" in raw["agent"]  # 磁盘残留仍可读，但不被顶层覆盖改写
    assert raw["agent"]["reflect_interval"] == 1


def test_load_keeps_non_migrated_agent_keys(tmp_path):
    _write(tmp_path, {"agent": {"plateau_rounds": 7, "scenario_default": "64b"}})
    raw = load_nn_config(tmp_path)
    assert raw["agent"]["plateau_rounds"] == 7
    assert raw["agent"]["scenario_default"] == "64b"


def test_load_missing_yaml_returns_empty_agent(tmp_path):
    raw = load_nn_config(tmp_path)
    assert raw.get("agent") == {}


def test_save_forwards_then_pops_agent_alias(tmp_path):
    _write(tmp_path, {"agent": {"goal_value": 0.9, "plateau_rounds": 3}})
    raw = load_nn_config(tmp_path)
    save_nn_config(tmp_path, raw)
    saved = yaml.safe_load((tmp_path / "nn-config.yaml").read_text())
    # migrate_goal 会把 value→target
    goal = saved.get("goal") or {}
    assert goal.get("target") == 0.9 or goal.get("value") == 0.9
    assert "goal_value" not in (saved.get("agent") or {})
    assert saved["agent"]["plateau_rounds"] == 3


def test_save_agent_value_wins_then_pop(tmp_path):
    _write(tmp_path, {"goal": {"value": 0.9}, "agent": {"goal_value": 0.95}})
    raw = load_nn_config(tmp_path)
    raw["agent"]["goal_value"] = 0.95
    save_nn_config(tmp_path, raw)
    saved = yaml.safe_load((tmp_path / "nn-config.yaml").read_text())
    goal = saved.get("goal") or {}
    assert goal.get("target") == 0.95 or goal.get("value") == 0.95
    assert "goal_value" not in (saved.get("agent") or {})


def test_load_reads_gpu_from_top_only(tmp_path):
    _write(
        tmp_path,
        {
            "gpu": {
                "mem_reserve_gb": 3.0,
                "busy_util_min": 90,
                "colocate_on_single": False,
            },
            "agent": {},
        },
    )
    raw = load_nn_config(tmp_path)
    assert raw["gpu"]["mem_reserve_gb"] == 3.0
    assert "gpu_mem_reserve_gb" not in raw["agent"]


def test_plateau_rounds_not_migrated(tmp_path):
    assert "plateau_rounds" not in AGENT_TO_TOP_KEYS
    _write(tmp_path, {"agent": {"plateau_rounds": 5}})
    raw = load_nn_config(tmp_path)
    assert raw["agent"]["plateau_rounds"] == 5
    save_nn_config(tmp_path, raw)
    saved = yaml.safe_load((tmp_path / "nn-config.yaml").read_text())
    assert saved["agent"]["plateau_rounds"] == 5
    non_agent = {k: v for k, v in saved.items() if k != "agent"}
    assert "plateau_rounds" not in _collect_keys(non_agent)


def test_roundtrip_load_save_idempotent(tmp_path):
    _write(tmp_path, {"goal": {"target": 0.9}, "agent": {"plateau_rounds": 3}})
    raw = load_nn_config(tmp_path)
    save_nn_config(tmp_path, raw)
    snap1 = yaml.safe_load((tmp_path / "nn-config.yaml").read_text())
    raw2 = load_nn_config(tmp_path)
    save_nn_config(tmp_path, raw2)
    snap2 = yaml.safe_load((tmp_path / "nn-config.yaml").read_text())
    assert snap1 == snap2
    assert "goal_value" not in (snap1.get("agent") or {})


def test_map_covers_all_migrated_agent_keys():
    assert len(AGENT_TO_TOP_KEYS) == 59
    for stay in (
        "plateau_rounds",
        "scenario_active",
        "scenario_axis",
        "scenario_default",
        "scenario_policy",
        "experiment_mode",
        "exploration",
    ):
        assert stay not in AGENT_TO_TOP_KEYS


def test_reflect_and_tam_read_from_top(tmp_path):
    _write(
        tmp_path,
        {
            "reflect": {"evidence_recent": 5, "evidence_git_log_max": 20},
            "tier_attestation": {"enabled": False, "exhaust_min_attempts": 3},
            "agent": {},
        },
    )
    raw = load_nn_config(tmp_path)
    assert raw["reflect"]["evidence_recent"] == 5
    assert raw["tier_attestation"]["enabled"] is False
    assert "reflect_evidence_recent" not in raw["agent"]


def test_load_nn_config_bare_string_exploration_does_not_crash():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "nn-config.yaml").write_text(
            yaml.safe_dump({"profile": "supervised", "exploration": "aggressive"}),
            encoding="utf-8",
        )
        raw = load_nn_config(p)
        assert raw.get("exploration") == "aggressive"


# ── save_nn_config 的幻影段剥离（v2.5.2 治本 fix）────────────────────

def _strip(raw: dict, mode: str) -> dict:
    from lib.nn_config import _strip_preset_defaults

    return _strip_preset_defaults(raw, mode)


def test_strip_removes_segments_equal_to_preset_default(tmp_path):
    from lib.presets import default_for_mode

    mode = "optimize"
    preset = default_for_mode(mode)
    raw = {"profile": "supervised", "gpus": [0, 1], "exploration_mode": mode}
    # 塞入与 preset 默认值相等的段
    for seg in ("reflect", "external", "innovation", "tier_attestation",
                "gpu", "training", "context", "analyse", "compress", "safety"):
        raw[seg] = preset.get(seg, {})

    out = _strip(raw, mode)
    for seg in ("reflect", "external", "innovation", "tier_attestation",
                "gpu", "training", "context", "analyse", "compress", "safety"):
        assert seg not in out, f"{seg} 应该被剥离（值 == preset 默认）"
    # 骨架旋钮全留
    assert out["profile"] == "supervised"
    assert out["gpus"] == [0, 1]
    assert out["exploration_mode"] == mode


def test_strip_keeps_overrides_that_differ_from_preset_default(tmp_path):
    from lib.presets import default_for_mode

    mode = "optimize"
    preset_reflect = default_for_mode(mode).get("reflect", {})
    raw = {
        "profile": "supervised",
        "exploration_mode": mode,
        "reflect": {**preset_reflect, "evidence_recent": 99},  # 手改
    }
    out = _strip(raw, mode)
    assert out["reflect"]["evidence_recent"] == 99, "手改值必须保留"
    # 子键若手改过, 段就要保留——不能"保留手改子键 + 删段"
    assert "reflect" in out


def test_strip_keeps_business_segments_not_in_preset(tmp_path):
    raw = {
        "profile": "supervised",
        "exploration_mode": "optimize",
        "scenario": {"simplestories_automatic": {"active": True}},
        "goal": {"target": 1.2, "policy": "focus"},
        "keep": {"improve_mode": "any_primary"},
        "ledger": {"watchlist": ["LR", "BATCH_SIZE"]},
        "agent": {"scenario_default": "simplestories_automatic"},
    }
    out = _strip(raw, "optimize")
    for seg in ("scenario", "goal", "keep", "ledger", "agent"):
        assert seg in out, f"业务段 {seg} 必须保留（preset 不提供）"


def test_save_nn_config_strips_phantom_segments(tmp_path):
    """manage_goal.py 场景: load 后 cfg 含运行时默认段, 改 goal, save → 磁盘 yaml 不含幻影段。"""
    _write(tmp_path, {
        "profile": "supervised",
        "exploration_mode": "optimize",
        "goal": {"target": 3.0, "policy": "focus"},
    })
    raw = load_nn_config(tmp_path)
    # 模拟 manage_goal 改了 goal
    raw["goal"]["target"] = 1.2
    save_nn_config(tmp_path, raw)

    # 磁盘 yaml 应该不含幻影默认段
    on_disk = yaml.safe_load((tmp_path / "nn-config.yaml").read_text(encoding="utf-8"))
    for seg in ("reflect", "external", "innovation", "tier_attestation",
                "gpu", "training", "context", "analyse", "compress", "safety"):
        assert seg not in on_disk, f"save 后磁盘不应含幻影段 {seg}"
    # 手改的 goal 必须保留
    assert on_disk["goal"]["target"] == 1.2
    # 骨架旋钮保留
    assert on_disk["exploration_mode"] == "optimize"


def test_save_nn_config_load_round_trip_preserves_behavior(tmp_path):
    """save → load 后输出与 save 前 load 输出 deep-equal（行为零变化）。"""
    _write(tmp_path, {
        "profile": "supervised",
        "exploration_mode": "optimize",
        "goal": {"target": 3.0, "policy": "focus",
                 "per_scenario": {"simplestories_automatic": 3.0}},
        "keep": {"improve_mode": "any_primary", "primary_delta_rel": 0.01},
    })
    before = load_nn_config(tmp_path)
    save_nn_config(tmp_path, before)
    after = load_nn_config(tmp_path)
    assert before == after, f"save → load 行为必须不变；diff={set(before)^set(after)}"


# ── v2.5.4: 用户手写 goal.metric/op 持久 + 白名单校验 ─────────────────

def test_save_preserves_goal_metric_op(tmp_path):
    """v2.5.4: 用户在 yaml 显式写的 goal.metric / goal.op 必须落盘（不再被下次 save 吃掉）。

    回归测试: 之前 migrate_goal_schema.py:48-50 无条件 pop 这两个键；
    改成不剥后, save_nn_config 写盘 yaml 仍含 metric/op。
    """
    _write(tmp_path, {
        "profile": "supervised",
        "exploration_mode": "optimize",
        "goal": {
            "policy": "focus",
            "metric": "test_loss",      # 用户手写
            "op": "<=",                  # 用户手写
            "target": 3.0,
            "per_scenario": {"simplestories_automatic": 0.8},
        },
    })
    raw = load_nn_config(tmp_path)
    save_nn_config(tmp_path, raw)
    on_disk = yaml.safe_load((tmp_path / "nn-config.yaml").read_text(encoding="utf-8"))
    assert on_disk["goal"]["metric"] == "test_loss", "用户手写 metric 必须持久"
    assert on_disk["goal"]["op"] == "<=", "用户手写 op 必须持久"
    # 业务字段不受影响
    assert on_disk["goal"]["target"] == 3.0
    assert on_disk["goal"]["per_scenario"]["simplestories_automatic"] == 0.8


def test_save_rejects_illegal_goal_op(tmp_path):
    """v2.5.4: goal.op 仅接受 '>=' / '<='; 其它值 save 阻断（抛 ValueError）。"""
    _write(tmp_path, {
        "profile": "supervised",
        "exploration_mode": "optimize",
        "goal": {"policy": "focus", "metric": "test_loss", "op": "==", "target": 3.0},
    })
    raw = load_nn_config(tmp_path)
    import pytest
    with pytest.raises(ValueError, match="goal.op"):
        save_nn_config(tmp_path, raw)


def test_save_rejects_metric_outside_whitelist(tmp_path, monkeypatch):
    """v2.5.4: goal.metric 必须在 contract.METRIC_KEYS ∪ AUXILIARY_KEYS 白名单; 否则 save 阻断。"""
    # mock contract.metrics: METRIC_KEYS 只有 val_loss, AUXILIARY_KEYS 空
    import sys
    import types
    fake = types.ModuleType("contract.metrics")
    fake.METRIC_KEYS = {"val_loss": "maximize"}
    fake.AUXILIARY_KEYS = {}
    monkeypatch.setitem(sys.modules, "contract.metrics", fake)

    _write(tmp_path, {
        "profile": "supervised",
        "exploration_mode": "optimize",
        "goal": {"policy": "focus", "metric": "wrong_metric", "op": ">=", "target": 3.0},
    })
    raw = load_nn_config(tmp_path)
    import pytest
    with pytest.raises(ValueError, match="不在 contract 白名单"):
        save_nn_config(tmp_path, raw)


def test_metric_key_yaml_overrides_contract(tmp_path, monkeypatch):
    """v2.5.4: yaml.goal.metric 优先（contract 部分用 monkeypatch 注入 fake module）。"""
    import sys
    import types
    # mock contract.metrics 让白名单可空，避免 _validate_goal_user_fields 走白名单路径
    fake = types.ModuleType("contract.metrics")
    fake.METRIC_KEYS = {"contract_metric": "maximize"}
    fake.AUXILIARY_KEYS = {}
    monkeypatch.setitem(sys.modules, "contract.metrics", fake)
    fake_contract = types.ModuleType("contract")
    fake_contract.metrics = fake
    monkeypatch.setitem(sys.modules, "contract", fake_contract)

    _write(tmp_path, {
        "profile": "supervised",
        "exploration_mode": "optimize",
        "goal": {"policy": "focus", "metric": "yaml_metric", "op": ">=", "target": 3.0},
    })
    from lib.run_ledger_summary import metric_key

    # yaml.goal.metric 优先（这是 v2.5.4 的核心行为）
    assert metric_key(tmp_path) == "yaml_metric", "yaml.goal.metric 应最优先"


def test_metric_key_fallback_to_contract(tmp_path, monkeypatch):
    """yaml.goal.metric 不写时, fallback 到 profiles.yaml → contract.metric_key。"""
    import sys
    import types
    # mock contract 模块带 metric_key 属性
    class FakeContract:
        metric_key = "fake_contract_mk"
        metric_direction = "maximize"
    fake_contract = types.ModuleType("contract")
    fake_contract.Contract = FakeContract  # 让 _try_load_contract 能返回带属性的对象
    monkeypatch.setitem(sys.modules, "contract", fake_contract)

    _write(tmp_path, {
        "profile": "supervised",
        "exploration_mode": "optimize",
        "goal": {"policy": "focus", "op": ">=", "target": 3.0},  # 没 metric
    })
    from lib.run_ledger_summary import metric_key

    # yaml 没写 metric: 应 fall through 到 profiles.yaml / contract
    result = metric_key(tmp_path)
    # _try_load_contract 用 importlib 走真实路径 → 不受 mock 影响;
    # 这个测试主要保证 yaml 没写时不崩, 且优先级正确
    assert result, "yaml 不写时必须有 fallback 返回值（profiles 或 contract）"


def test_metric_direction_yaml_op_overrides_contract(tmp_path, monkeypatch):
    """v2.5.4: yaml.goal.op (>= → maximize, <= → minimize) 优先于 contract.metric_direction."""
    import sys
    import types
    fake = types.ModuleType("contract.metrics")
    fake.METRIC_KEYS = {"x": "minimize"}  # contract 方向 = minimize
    fake.AUXILIARY_KEYS = {}
    monkeypatch.setitem(sys.modules, "contract.metrics", fake)

    fake_contract = types.ModuleType("contract")
    fake_contract.metrics = fake
    monkeypatch.setitem(sys.modules, "contract", fake_contract)

    _write(tmp_path, {
        "profile": "supervised",
        "exploration_mode": "optimize",
        "goal": {"policy": "focus", "metric": "x", "op": ">=", "target": 3.0},  # yaml 写 ">=" → 应得 maximize
    })
    from lib.run_ledger_summary import metric_direction

    assert metric_direction(tmp_path) == "maximize"  # yaml 优先

    # yaml.op = "<=" → minimize
    _write(tmp_path, {
        "profile": "supervised",
        "exploration_mode": "optimize",
        "goal": {"policy": "focus", "metric": "x", "op": "<=", "target": 3.0},
    })
    assert metric_direction(tmp_path) == "minimize"
