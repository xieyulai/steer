"""v3 goal schema → v4 goal schema."""
from typing import Any

GOAL_FIELD_MAP = {"value": "target", "scenario_goals": "per_scenario"}
STOP_MODE_MAP = {"focus_only": "focus", "all_in_scope": "strict"}
AGENT_FIELD_MAP = {
    "goal_value": ("goal", "target"),
    "scenario_goals": ("goal", "per_scenario"),
    "goal_stop_mode": ("goal", "policy"),
}


def migrate_goal(raw: dict) -> tuple[dict, list[str]]:
    """Migrate v3 goal schema to v4 goal schema.

    Returns (migrated, warnings). Idempotent; user presence wins.

    Mutation semantics: returns a new top-level dict; nested dicts
    (`goal`, `agent`) are mutated in place by callers that pass them in.
    Safe for the read-once pattern used by `governance-sync` (yaml → dict
    → migrate → write); unsafe if caller retains a reference to the
    nested dicts and expects them unchanged.

    v2.5.4 (P0 用户体验修复): 不再 pop ``goal.metric`` / ``goal.op``。
    用户在 yaml 显式写的 metric/op 必须持久,不再被下次 save 静默吃掉。
    校验下沉到 ``save_nn_config._validate_goal_user_fields`` (save 时白名单
    + direction 一致性检查)。fallback 路径由 ``run_ledger_summary.metric_key``
    / ``metric_direction`` 处理(yaml 优先 → profiles → contract)。
    """
    out: dict[str, Any] = {}
    for k, v in raw.items():
        out[k] = dict(v) if isinstance(v, dict) else v
    warnings: list[str] = []

    # Top-level goal block
    if isinstance(out.get("goal"), dict):
        goal = out["goal"]
        # Rename value → target, scenario_goals → per_scenario (presence check)
        for old, new in GOAL_FIELD_MAP.items():
            if old in goal and new not in goal:
                goal[new] = goal.pop(old)
            elif old in goal and new in goal:
                goal.pop(old)  # both present → keep new, drop old
        # Map stop_mode → policy (value mapping)
        if "stop_mode" in goal:
            old_mode = goal.pop("stop_mode")
            new_mode = STOP_MODE_MAP.get(old_mode, old_mode)
            if "policy" not in goal:
                goal["policy"] = new_mode
            if old_mode in STOP_MODE_MAP:
                warnings.append(
                    f"goal.stop_mode '{old_mode}' → goal.policy '{new_mode}'"
                )
        # v2.5.4 之前: 这里会无条件 pop metric/op → 用户手写被下次 save 静默吃掉
        # 现在: 保留 yaml.metric/op (用户手写必持久), 校验下沉到 save_nn_config

    # agent.* 旧字段 (5 keys) → goal block
    if isinstance(out.get("agent"), dict):
        agent = out["agent"]
        for old_key, (target_block, target_field) in AGENT_FIELD_MAP.items():
            if old_key in agent:
                old_val = agent.pop(old_key)
                if target_block not in out or not isinstance(out[target_block], dict):
                    out[target_block] = {}
                if target_field not in out[target_block]:
                    if old_key == "goal_stop_mode":
                        out[target_block][target_field] = STOP_MODE_MAP.get(
                            old_val, old_val
                        )
                    else:
                        out[target_block][target_field] = old_val

    return out, warnings


if __name__ == "__main__":
    import argparse
    import sys

    import yaml

    p = argparse.ArgumentParser()
    p.add_argument("--yaml", required=True)
    p.add_argument("--write", action="store_true")
    args = p.parse_args()
    with open(args.yaml) as f:
        raw = yaml.safe_load(f) or {}
    migrated, warns = migrate_goal(raw)
    for w in warns:
        print(f"[migrate_goal] {w}", file=sys.stderr)
    if args.write:
        with open(args.yaml, "w") as f:
            yaml.safe_dump(migrated, f, sort_keys=False, allow_unicode=True)
        print(f"[migrate_goal] wrote {args.yaml}", file=sys.stderr)
    else:
        print(yaml.safe_dump(migrated, sort_keys=False, allow_unicode=True))
