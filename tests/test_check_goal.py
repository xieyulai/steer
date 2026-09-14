"""v4 check_goal reads goal.target/per_scenario/policy (not agent.*).

After Tasks 1-3, load_nn_config() migrates v3 agent.* aliases into a top-level
goal block on every read. check_goal.py / run_ledger_summary.py should therefore
read from cfg['goal'] (target/per_scenario/policy), not cfg['agent'].goal_*

Metric/op come from contract, not yaml.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest
import yaml

# Make scripts/ importable for `lib.run_ledger_summary` etc.
_SCRIPTS = Path(__file__).resolve().parent.parent / "template/package"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


@pytest.fixture(autouse=True)
def _isolate_contract_imports():
    """check_goal.main 会在测试时把临时 repo 插入 sys.path 并 import 一个 fake
    contract；本 fixture 在每个测试前后保存/恢复 sys.path 与 sys.modules 中的
    contract / check_goal，避免污染后续测试（如 test_contract_facade 的 import contract）。"""
    saved_path = sys.path[:]
    saved_contract = sys.modules.get("contract")
    saved_check_goal = sys.modules.get("check_goal")
    yield
    sys.path[:] = saved_path
    for _name, _saved in (("contract", saved_contract), ("check_goal", saved_check_goal)):
        if _saved is not None:
            sys.modules[_name] = _saved
        else:
            sys.modules.pop(_name, None)


def _write_cfg(repo: Path, **fields) -> None:
    """Write a minimal nn-config.yaml. ``fields`` is merged into ``goal``."""
    goal = {}
    if "target" in fields:
        goal["target"] = fields["target"]
    if "per_scenario" in fields:
        goal["per_scenario"] = fields["per_scenario"]
    if "policy" in fields:
        goal["policy"] = fields["policy"]
    payload = {"profile": "supervised"}
    if goal:
        payload["goal"] = goal
    if "agent_overlay" in fields:
        payload["agent"] = fields["agent_overlay"]
    (repo / "nn-config.yaml").write_text(yaml.safe_dump(payload, sort_keys=False))


def _write_contract(repo: Path, metric_key: str = "test_acc", direction: str = "maximize") -> None:
    cdir = repo / "contract"
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "__init__.py").write_text(
        "def create_contract(cfg: dict):\n"
        "    class C:\n"
        f"        metric_key = {metric_key!r}\n"
        f"        metric_keys = {{{metric_key!r}: {direction!r}}}\n"
        "        auxiliary_keys = {}\n"
        "        ledger_context_keys = ()\n"
        "    return C()\n",
        encoding="utf-8",
    )


def test_check_goal_reads_v4_target_and_policy():
    """check_goal goal_config reads goal.target + goal.policy from a v4 yaml."""
    from scripts.lib.nn_config import load_nn_config
    from scripts.lib.run_ledger_summary import goal_config, goal_stop_mode

    with tempfile.TemporaryDirectory() as repo:
        repo_p = Path(repo)
        _write_cfg(
            repo_p,
            target=0.85,
            policy="focus",
            per_scenario={"a": 0.95},
        )
        cfg = goal_config(repo_p)
        # goal_config returns (goal_value, metric_key, op, scenario_default)
        assert cfg[0] == 0.85
        # metric_key comes from contract; no contract → default "val_accuracy"
        assert cfg[1] == "val_accuracy"
        assert cfg[2] == ">="        # direction=maximize → >=
        # policy from goal block
        goal = load_nn_config(repo_p).get("goal", {})
        assert goal_stop_mode(goal) == "focus"


def test_check_goal_handles_v3_aliases_via_load_migration():
    """Old v3 input still works because load_nn_config migrates on read."""
    from scripts.lib.nn_config import load_nn_config
    from scripts.lib.run_ledger_summary import goal_config, goal_stop_mode

    with tempfile.TemporaryDirectory() as repo:
        repo_p = Path(repo)
        (repo_p / "nn-config.yaml").write_text(yaml.safe_dump({
            "profile": "supervised",
            "agent": {"goal_value": 0.77, "goal_stop_mode": "all_in_scope"},
        }))
        cfg = goal_config(repo_p)
        # v3 alias migrated to v4 via load_nn_config + migrate_goal
        assert cfg[0] == 0.77
        # all_in_scope → strict (v4 policy name)
        goal = load_nn_config(repo_p).get("goal", {})
        assert goal_stop_mode(goal) == "strict"


def test_effective_goal_uses_v4_per_scenario():
    """effective_goal reads goal.per_scenario (NOT agent.scenario_goals)."""
    from scripts.lib.run_ledger_summary import effective_goal

    with tempfile.TemporaryDirectory() as repo:
        _write_cfg(
            Path(repo),
            target=0.90,
            per_scenario={"a": 0.95, "b": 0.99},
        )
        goal_block = {"target": 0.90, "per_scenario": {"a": 0.95, "b": 0.99}}
        assert effective_goal(goal_block, "a") == 0.95
        assert effective_goal(goal_block, "b") == 0.99
        assert effective_goal(goal_block, "c") == 0.90  # falls back to global


def test_scenario_goals_map_reads_v4_per_scenario():
    """scenario_goals_map reads goal.per_scenario."""
    from scripts.lib.run_ledger_summary import scenario_goals_map

    goal = {"per_scenario": {"a": 0.95, "b": None}}
    out = scenario_goals_map(goal)
    assert out == {"a": 0.95, "b": None}


def test_has_any_configured_goal_uses_v4_target():
    """has_any_configured_goal detects goal.target (NOT agent.goal_value)."""
    from scripts.lib.run_ledger_summary import has_any_configured_goal

    with tempfile.TemporaryDirectory() as repo:
        _write_cfg(Path(repo), target=0.92)
        goal = {"target": 0.92, "per_scenario": {}, "policy": "focus"}
        assert has_any_configured_goal(goal) is True

    goal_empty: dict = {"target": None, "per_scenario": {}, "policy": "focus"}
    assert has_any_configured_goal(goal_empty) is False


def test_check_goal_main_no_goal_exit2():
    """check_goal.main with v4 yaml lacking goal.target returns exit 2 NO_GOAL."""
    import io
    import sys
    from contextlib import redirect_stderr, redirect_stdout

    with tempfile.TemporaryDirectory() as repo:
        repo_p = Path(repo)
        _write_contract(repo_p, "test_acc")
        _write_cfg(repo_p)  # no goal fields
        (repo_p / "_runs").mkdir()
        (repo_p / "_runs" / "results.tsv").write_text(
            "experiment\tscenario_id\ttest_acc\n"
            "a\tdefault\t0.99\n",
            encoding="utf-8",
        )
        # Ensure scripts path is importable
        scripts_dir = Path(repo_p).parent  # not used; we'll insert repo to sys.path
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "template/package"))

        # Reset cached contract module
        sys.modules.pop("contract", None)

        import check_goal  # noqa: E402

        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = check_goal.main([str(repo_p)])
        assert rc == 2, (out.getvalue(), err.getvalue())
        assert "NO_GOAL" in out.getvalue()


def test_check_goal_main_focus_met_v4_yaml():
    """check_goal.main returns exit 0 GOAL_MET with v4 goal.target yaml."""
    import io
    import sys
    from contextlib import redirect_stderr, redirect_stdout

    with tempfile.TemporaryDirectory() as repo:
        repo_p = Path(repo)
        _write_contract(repo_p, "test_acc", "maximize")
        _write_cfg(repo_p, target=0.95)
        (repo_p / "_runs").mkdir()
        (repo_p / "_runs" / "results.tsv").write_text(
            "experiment\tscenario_id\ttest_acc\ttimestamp\n"
            "a\tdefault\t0.90\t2026-06-01T00:00:00+00:00\n"
            "b\tdefault\t0.96\t2026-06-02T00:00:00+00:00\n",
            encoding="utf-8",
        )
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "template/package"))
        sys.modules.pop("contract", None)

        import check_goal  # noqa: E402

        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = check_goal.main([str(repo_p)])
        assert rc == 0, (out.getvalue(), err.getvalue())
        assert "GOAL_MET" in out.getvalue()