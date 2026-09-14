#!/usr/bin/env python3
"""管理 nn-config goal：全局 + 按场景 + v4 字段直写。

v4 schema: ``goal.target`` / ``goal.per_scenario`` / ``goal.policy``。
``load_nn_config`` 在读时已自动 migrate v3 ``agent.*`` 别名；写路径直写 v4。

用法：
  python3 scripts/manage_goal.py set 0.95
  python3 scripts/manage_goal.py set 128b 0.75
  python3 scripts/manage_goal.py clear [--overrides]
  python3 scripts/manage_goal.py clear 128b
  python3 scripts/manage_goal.py show [--all]
  python3 scripts/manage_goal.py stop-mode focus_only|all_in_scope
  python3 scripts/manage_goal.py mode careful|optimize|innovate|aggressive|explore|auto|show
  python3 scripts/manage_goal.py upgrade   # v4 no-op（load 时自动 migrate）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lib.nn_config import load_nn_config, save_nn_config  # noqa: E402
from lib.run_ledger_summary import (  # noqa: E402
    format_goal_matrix_lines,
    format_goal_progress_line,
)
from lib.goal_spec import GOAL_SPEC_KEY  # noqa: E402

# CLI argv → v4 field
STOP_MODE_MAP: dict[str, str] = {
    "focus_only": "focus",
    "all_in_scope": "strict",
}
STOP_MODE_INVERSE: dict[str, str] = {v: k for k, v in STOP_MODE_MAP.items()}

# 6 档实验模式（exploration_mode 单旋钮）+ show 查 resolve_exploration
MODE_CHOICES: list[str] = [
    "careful", "optimize", "innovate", "aggressive", "explore", "auto", "show",
]


def _load_cfg(repo_root: Path) -> dict:
    return load_nn_config(repo_root)


def _save_cfg(repo_root: Path, cfg: dict) -> None:
    save_nn_config(repo_root, cfg)


def _goal(cfg: dict) -> dict:
    goal = cfg.setdefault("goal", {})
    if not isinstance(goal, dict):
        goal = {}
        cfg["goal"] = goal
    return goal


def cmd_set(repo_root: Path, a: str, b: str | None) -> int:
    cfg = _load_cfg(repo_root)
    goal = _goal(cfg)
    if b is None:
        goal["target"] = float(a)
        print(f"[goal] set goal.target={a}")
    else:
        ps = goal.get("per_scenario")
        if not isinstance(ps, dict):
            ps = {}
        ps[str(a)] = float(b)
        goal["per_scenario"] = ps
        print(f"[goal] set goal.per_scenario[{a!r}]={b}")
    _save_cfg(repo_root, cfg)
    return 0


def cmd_clear(repo_root: Path, args: argparse.Namespace) -> int:
    cfg = _load_cfg(repo_root)
    goal = _goal(cfg)
    if args.scenario:
        ps = goal.get("per_scenario")
        if isinstance(ps, dict) and args.scenario in ps:
            del ps[args.scenario]
            if not ps:
                goal.pop("per_scenario", None)
            else:
                goal["per_scenario"] = ps
        print(f"[goal] cleared goal.per_scenario[{args.scenario!r}]")
    else:
        goal.pop("target", None)
        if args.overrides:
            goal.pop("per_scenario", None)
            print("[goal] cleared goal.target + goal.per_scenario")
        else:
            print("[goal] cleared goal.target")
    _save_cfg(repo_root, cfg)
    return 0


def cmd_show(repo_root: Path, args: argparse.Namespace) -> int:
    if args.all:
        cfg = load_nn_config(repo_root)
        goal = cfg.get("goal") or {}
        # v4 read path
        target = goal.get("target")
        per_scenario = goal.get("per_scenario") or {}
        policy = goal.get("policy")
        # v2.5.5 补 UX: cmd_show 之前漏读 yaml.goal.metric / goal.op（持久化
        # + fallback + 校验已在 v2.5.4 修; 这里补 CLI 输出, 让用户看得到自己写的)
        metric = goal.get("metric")
        op = goal.get("op")
        print(f"goal_stop_mode: {STOP_MODE_INVERSE.get(policy, 'focus_only')}")
        if target is not None:
            print(f"goal.target: {target}")
        if per_scenario:
            print(f"goal.per_scenario: {per_scenario}")
        if policy is not None:
            print(f"goal.policy: {policy}")
        if metric is not None:
            print(f"goal.metric: {metric}")
        if op is not None:
            print(f"goal.op: {op}")
        # v3 goal_spec 优先（保留多 metric / 多停批语义）
        agent = cfg.get("agent") or {}
        if isinstance(agent.get(GOAL_SPEC_KEY), dict) and agent[GOAL_SPEC_KEY]:
            from lib.goal_spec import (  # noqa: WPS433
                evaluate_goal_spec,
                format_goal_spec_matrix_lines,
                format_goal_spec_progress,
                parse_goal_spec,
            )
            try:
                spec = parse_goal_spec(agent)
                if spec is not None:
                    result = evaluate_goal_spec(spec, repo_root)
                    line = format_goal_spec_progress(result)
                    if line:
                        print(f"focus: {line}")
                    matrix = format_goal_spec_matrix_lines(result)
                    if matrix:
                        print("\n".join(matrix))
                    return 0
            except Exception as e:
                print(f"ERROR: {e}", file=sys.stderr)
                return 1
        # fallback：v2-style matrix（goal_matrix 仍读 agent.* 通过 load_nn_config 回填）
        line = format_goal_progress_line(repo_root)
        if line:
            print(f"focus: {line}")
        matrix = format_goal_matrix_lines(repo_root)
        if matrix:
            print("\n".join(matrix))
        elif target is None and not per_scenario:
            print("NO_GOAL")
        return 0
    import check_goal  # noqa: WPS433

    return check_goal.main([str(repo_root)])


def cmd_stop_mode(repo_root: Path, mode: str) -> int:
    if mode not in STOP_MODE_MAP:
        print(f"ERROR: 无效 mode {mode!r}", file=sys.stderr)
        return 1
    cfg = _load_cfg(repo_root)
    goal = _goal(cfg)
    mapped = STOP_MODE_MAP[mode]
    goal["policy"] = mapped
    _save_cfg(repo_root, cfg)
    print(f"[goal] set goal.policy={mapped}")
    return 0


def cmd_mode(repo_root: Path, mode_value: str) -> int:
    """6 档实验模式（exploration_mode 单旋钮）。

    ``mode <M>`` → set_experiment_mode（6 档统一入口；auto→initialize_auto）。
    ``mode show`` → 打印 resolve_exploration（运行时解析；check_goal 读此判 goal 硬停）。
    """
    if mode_value == "show":
        from lib.experiment_mode import resolve_exploration

        try:
            res = resolve_exploration(repo_root)
            print(f"exploration_mode: {res.mode}")
            print(f"resolved_mode: {res.resolved_mode}")
            print(f"skip_goal_stop: {res.skip_goal_stop}")
            print(f"tier_start: {res.tier_start}")
        except KeyError as e:
            print(f"ERROR: {e}（未迁移配置？）", file=sys.stderr)
            return 1
        return 0
    from lib.experiment_mode import set_experiment_mode

    cfg = set_experiment_mode(repo_root, mode_value)
    print(f"[mode] set exploration_mode={mode_value}")
    return 0


# ── v3 → v4 迁移：load_nn_config 已自动 migrate；upgrade 留作 no-op ──


def cmd_upgrade(repo_root: Path, apply: bool) -> int:
    """v4 兼容层：``load_nn_config`` 读时已自动 v3 → v4 migrate，本命令是 no-op。"""
    _ = load_nn_config(repo_root)  # 触发 migrate；让用户看到当前生效配置
    print("[goal] upgrade is a no-op in v4 (load_nn_config auto-migrates v3 → v4)")
    if apply:
        print("[goal] --apply ignored: nothing to do")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="管理 nn-config goal（全局 + 按场景 + v4 字段直写）")
    parser.add_argument("--repo-root", default=".", help="项目根")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_set = sub.add_parser("set", help="set 0.95 或 set 128b 0.75")
    p_set.add_argument("a")
    p_set.add_argument("b", nargs="?", default=None)

    p_clear = sub.add_parser("clear", help="清全局或场景 override")
    p_clear.add_argument("scenario", nargs="?", default=None)
    p_clear.add_argument("--overrides", action="store_true", help="同时清空 per_scenario")

    p_show = sub.add_parser("show", help="show 或 show --all")
    p_show.add_argument("--all", action="store_true")

    p_mode = sub.add_parser("stop-mode", help="focus_only | all_in_scope")
    p_mode.add_argument("mode")

    p_exp_mode = sub.add_parser(
        "mode", help="6 档实验模式：careful/optimize/innovate/aggressive/explore/auto 或 show"
    )
    p_exp_mode.add_argument("mode_value", choices=MODE_CHOICES)

    p_up = sub.add_parser("upgrade", help="v4 no-op（load 时自动 migrate）")
    p_up.add_argument("--apply", action="store_true")

    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()

    if args.cmd == "set":
        return cmd_set(repo_root, args.a, args.b)
    if args.cmd == "clear":
        return cmd_clear(repo_root, args)
    if args.cmd == "show":
        return cmd_show(repo_root, args)
    if args.cmd == "stop-mode":
        return cmd_stop_mode(repo_root, args.mode)
    if args.cmd == "mode":
        return cmd_mode(repo_root, args.mode_value)
    if args.cmd == "upgrade":
        return cmd_upgrade(repo_root, args.apply)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())