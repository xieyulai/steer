# tests/test_migrate_goal_schema.py
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "template/package"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from scripts.lib.migrate_goal_schema import migrate_goal  # noqa: E402


def test_goal_value_to_target():
    raw = {"goal": {"value": 0.85, "scenario_goals": {"a": 0.7}}, "agent": {"goal_value": 0.85}}
    out, warns = migrate_goal(raw)
    assert out["goal"]["target"] == 0.85
    assert out["goal"]["per_scenario"] == {"a": 0.7}
    assert "value" not in out["goal"]
    assert "goal_value" not in out.get("agent", {})


def test_goal_stop_mode_to_policy():
    raw = {"goal": {"stop_mode": "all_in_scope"}}
    out, warns = migrate_goal(raw)
    assert out["goal"]["policy"] == "strict"
    assert "stop_mode" not in out["goal"]


def test_presence_check_preserves_null():
    """'target: null' = user explicitly set no-autostop; don't overwrite"""
    raw = {"goal": {"target": None}}
    out, warns = migrate_goal(raw)
    assert "target" in out["goal"]  # presence preserved
    assert out["goal"]["target"] is None  # value is None


def test_idempotent():
    raw_v3 = {"goal": {"value": 0.85}, "agent": {"goal_value": 0.85}}
    once, _ = migrate_goal(raw_v3)
    twice, _ = migrate_goal(once)
    assert once == twice  # 幂等


def test_scenario_goals_number_or_dict():
    """per_scenario 值可为 number (覆盖 target) 或 dict (覆盖 targets)"""
    raw = {"goal": {"value": 0.85, "scenario_goals": {"a": 0.70, "b": {"targets": [{"target": 0.80}]}}}}
    out, _ = migrate_goal(raw)
    assert out["goal"]["per_scenario"]["a"] == 0.70
    assert out["goal"]["per_scenario"]["b"] == {"targets": [{"target": 0.80}]}