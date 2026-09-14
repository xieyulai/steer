"""Tests for manage_goal.py CLI writing v4 fields directly.

CLI surface must be preserved verbatim (same argv, same subcommands, same flags).
The v4 schema writes to `goal.target`, `goal.per_scenario`, `goal.policy`
instead of `agent.goal_value` / `agent.scenario_goals` / `agent.goal_stop_mode`.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
MANAGE_GOAL = REPO_ROOT / "template/package/scripts" / "manage_goal.py"


def _run(*args: str) -> subprocess.CompletedProcess:
    """Invoke manage_goal.py directly."""
    return subprocess.run(
        [sys.executable, str(MANAGE_GOAL), *args],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )


def _read_yaml(path: Path) -> dict:
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def test_cli_set_writes_v4_field():
    """CLI 'set 0.95' writes to goal.target (NOT agent.goal_value)."""
    with tempfile.TemporaryDirectory() as repo:
        repo_p = Path(repo)
        (repo_p / "nn-config.yaml").write_text("profile: supervised\n")
        result = _run("--repo-root", repo, "set", "0.95")
        assert result.returncode == 0, (result.stdout, result.stderr)
        cfg = _read_yaml(repo_p / "nn-config.yaml")
        # v4: must write goal.target
        assert isinstance(cfg.get("goal"), dict), cfg
        assert cfg["goal"]["target"] == 0.95, cfg
        # must NOT have written the v3 alias
        agent = cfg.get("agent") or {}
        assert "goal_value" not in agent, cfg


def test_cli_set_scenario_writes_per_scenario():
    """CLI 'set 128b 0.75' writes to goal.per_scenario (NOT agent.scenario_goals)."""
    with tempfile.TemporaryDirectory() as repo:
        repo_p = Path(repo)
        (repo_p / "nn-config.yaml").write_text("profile: supervised\n")
        # CLI argv: set <scenario> <value>
        result = _run("--repo-root", repo, "set", "128b", "0.75")
        assert result.returncode == 0, (result.stdout, result.stderr)
        cfg = _read_yaml(repo_p / "nn-config.yaml")
        assert isinstance(cfg.get("goal"), dict), cfg
        assert cfg["goal"]["per_scenario"] == {"128b": 0.75}, cfg
        # must NOT have written the v3 alias
        agent = cfg.get("agent") or {}
        assert "scenario_goals" not in agent, cfg


def test_cli_stop_mode_maps_all_in_scope_to_strict():
    """CLI 'stop-mode all_in_scope' → goal.policy=strict."""
    with tempfile.TemporaryDirectory() as repo:
        repo_p = Path(repo)
        (repo_p / "nn-config.yaml").write_text("profile: supervised\n")
        result = _run("--repo-root", repo, "stop-mode", "all_in_scope")
        assert result.returncode == 0, (result.stdout, result.stderr)
        cfg = _read_yaml(repo_p / "nn-config.yaml")
        assert isinstance(cfg.get("goal"), dict), cfg
        assert cfg["goal"]["policy"] == "strict", cfg
        # must NOT have written the v3 alias
        agent = cfg.get("agent") or {}
        assert "goal_stop_mode" not in agent, cfg


def test_cli_stop_mode_focus_only_maps_to_focus():
    """CLI 'stop-mode focus_only' → goal.policy=focus."""
    with tempfile.TemporaryDirectory() as repo:
        repo_p = Path(repo)
        (repo_p / "nn-config.yaml").write_text("profile: supervised\n")
        result = _run("--repo-root", repo, "stop-mode", "focus_only")
        assert result.returncode == 0, (result.stdout, result.stderr)
        cfg = _read_yaml(repo_p / "nn-config.yaml")
        assert isinstance(cfg.get("goal"), dict), cfg
        assert cfg["goal"]["policy"] == "focus", cfg
        agent = cfg.get("agent") or {}
        assert "goal_stop_mode" not in agent, cfg


def test_cli_show_reads_v4_fields():
    """CLI 'show' reads goal.target/per_scenario/policy (not agent.*)."""
    with tempfile.TemporaryDirectory() as repo:
        repo_p = Path(repo)
        (repo_p / "nn-config.yaml").write_text(
            "profile: supervised\n"
            "goal:\n"
            "  target: 0.9\n"
            "  policy: focus\n"
            "  per_scenario:\n"
            "    128b: 0.75\n"
        )
        # default `show` defers to check_goal.main; use --all to hit the v4 path directly.
        result = _run("--repo-root", repo, "show", "--all")
        assert result.returncode == 0, (result.stdout, result.stderr)
        # `show --all` should mention goal fields from v4 schema.
        # At minimum, the command must succeed with v4 yaml in place.
        assert (
            "goal" in result.stdout.lower()
            or "0.9" in result.stdout
            or "target" in result.stdout.lower()
        ), result.stdout


def test_cli_clear_removes_v4_target():
    """CLI 'clear' removes goal.target (NOT agent.goal_value)."""
    with tempfile.TemporaryDirectory() as repo:
        repo_p = Path(repo)
        (repo_p / "nn-config.yaml").write_text(
            "profile: supervised\n"
            "goal:\n"
            "  target: 0.9\n"
            "  policy: focus\n"
        )
        result = _run("--repo-root", repo, "clear")
        assert result.returncode == 0, (result.stdout, result.stderr)
        cfg = _read_yaml(repo_p / "nn-config.yaml")
        goal = cfg.get("goal") or {}
        # target cleared (load_nn_config may put the key back as None)
        assert goal.get("target") is None, cfg
        # policy untouched (clear without --overrides)
        assert goal.get("policy") == "focus", cfg


def test_cli_clear_scenario_removes_per_scenario_key():
    """CLI 'clear <scenario>' removes only that key from goal.per_scenario."""
    with tempfile.TemporaryDirectory() as repo:
        repo_p = Path(repo)
        (repo_p / "nn-config.yaml").write_text(
            "profile: supervised\n"
            "goal:\n"
            "  per_scenario:\n"
            "    128b: 0.75\n"
            "    256b: 0.80\n"
        )
        result = _run("--repo-root", repo, "clear", "128b")
        assert result.returncode == 0, (result.stdout, result.stderr)
        cfg = _read_yaml(repo_p / "nn-config.yaml")
        goal = cfg.get("goal") or {}
        assert goal.get("per_scenario") == {"256b": 0.80}, cfg


def test_cli_upgrade_is_noop_in_v4():
    """CLI 'upgrade' is a no-op in v4 (load_nn_config auto-migrates)."""
    with tempfile.TemporaryDirectory() as repo:
        repo_p = Path(repo)
        # write v4 input; load will leave it alone (idempotent)
        (repo_p / "nn-config.yaml").write_text(
            "profile: supervised\n"
            "goal:\n"
            "  target: 0.9\n"
        )
        result = _run("--repo-root", repo, "upgrade")
        assert result.returncode == 0, (result.stdout, result.stderr)
        # file should be untouched
        cfg = _read_yaml(repo_p / "nn-config.yaml")
        assert cfg["goal"]["target"] == 0.9, cfg