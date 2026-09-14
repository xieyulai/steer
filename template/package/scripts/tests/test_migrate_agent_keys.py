"""migrate_agent_keys：additive copy + 可选 --cleanup pop。"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from lib.migrate_agent_keys import migrate
from lib.nn_config import AGENT_TO_TOP_KEYS


def _write(root: Path, data: dict) -> None:
    (root / "nn-config.yaml").write_text(
        yaml.dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def _read(root: Path) -> dict:
    return yaml.safe_load((root / "nn-config.yaml").read_text(encoding="utf-8")) or {}


def test_dry_run_doesnt_write(tmp_path):
    _write(tmp_path, {"agent": {"goal_value": 0.9}})
    original = (tmp_path / "nn-config.yaml").read_text(encoding="utf-8")
    result = migrate(tmp_path / "nn-config.yaml", write=False)
    assert any(old == "goal_value" for old, *_ in result["migrated"])
    assert (tmp_path / "nn-config.yaml").read_text(encoding="utf-8") == original
    assert result["wrote"] is False


def test_writes_when_alias_present(tmp_path):
    _write(tmp_path, {"agent": {"goal_value": 0.9}})
    result = migrate(tmp_path / "nn-config.yaml", write=True)
    parsed = _read(tmp_path)
    assert parsed["goal"]["target"] == 0.9
    assert parsed["agent"]["goal_value"] == 0.9  # 无 cleanup：别名仍保留
    assert result["wrote"] is True


def test_cleanup_pops_aliases(tmp_path):
    _write(tmp_path, {"agent": {"goal_value": 0.9, "reflect_interval": 2}})
    result = migrate(tmp_path / "nn-config.yaml", write=True, cleanup=True)
    parsed = _read(tmp_path)
    assert parsed["goal"]["target"] == 0.9
    assert parsed["reflect"]["interval"] == 2
    assert "goal_value" not in parsed.get("agent", {})
    assert "reflect_interval" not in parsed.get("agent", {})
    assert "goal_value" in result["popped"]
    assert "reflect_interval" in result["popped"]


def test_cleanup_keep_top_still_pops(tmp_path):
    _write(tmp_path, {"goal": {"target": 0.95}, "agent": {"goal_value": 0.9}})
    result = migrate(tmp_path / "nn-config.yaml", write=True, cleanup=True)
    parsed = _read(tmp_path)
    assert parsed["goal"]["target"] == 0.95  # top wins，不覆盖
    assert "goal_value" not in parsed.get("agent", {})
    assert any(old == "goal_value" for old, *_ in result["kept_top"])
    assert "goal_value" in result["popped"]


def test_idempotent(tmp_path):
    _write(tmp_path, {"agent": {"goal_value": 0.9}})
    migrate(tmp_path / "nn-config.yaml", write=True)
    snap1 = (tmp_path / "nn-config.yaml").read_text(encoding="utf-8")
    result2 = migrate(tmp_path / "nn-config.yaml", write=True)
    snap2 = (tmp_path / "nn-config.yaml").read_text(encoding="utf-8")
    assert snap1 == snap2
    assert result2["migrated"] == []


def test_backup_created_only_when_migration_actually_happens(tmp_path):
    _write(tmp_path, {"agent": {"goal_value": 0.9}})
    backup = tmp_path / "nn-config.yaml.deprecated.bak"
    migrate(tmp_path / "nn-config.yaml", write=True)
    assert backup.exists()
    backup.unlink()
    migrate(tmp_path / "nn-config.yaml", write=True)
    assert not backup.exists()


def test_imports_agent_to_top_keys_not_redefine():
    from lib import migrate_agent_keys as m

    assert m.AGENT_TO_TOP_KEYS is AGENT_TO_TOP_KEYS
    assert len(AGENT_TO_TOP_KEYS) == 59


def test_script_runs_standalone_with_cleanup(tmp_path):
    import subprocess
    import sys

    (tmp_path / "nn-config.yaml").write_text(
        "agent:\n  goal_value: 0.9\n  reflect_interval: 2\n", encoding="utf-8"
    )
    script = Path(__file__).resolve().parent.parent / "lib" / "migrate_agent_keys.py"
    env = {k: v for k, v in __import__("os").environ.items() if k != "PYTHONPATH"}
    r = subprocess.run(
        [
            sys.executable,
            str(script),
            "--yaml",
            str(tmp_path / "nn-config.yaml"),
            "--write",
            "--cleanup",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert r.returncode == 0, f"standalone run failed:\n{r.stderr}"
    m = yaml.safe_load((tmp_path / "nn-config.yaml").read_text())
    assert m["goal"]["target"] == 0.9
