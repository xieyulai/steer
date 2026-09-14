"""migrate_to_exploration_mode：老 mode 字段 → exploration_mode（一次性，spec §9）。"""
from __future__ import annotations

import pytest
import yaml
from pathlib import Path

from migrate_to_exploration_mode import migrate


def _read(p: Path) -> dict:
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def test_agent_experiment_mode_maps(tmp_path):
    p = tmp_path / "nn-config.yaml"
    p.write_text("agent:\n  experiment_mode: innovate\n", encoding="utf-8")
    r = migrate(p, write=True, backup=False)
    raw = _read(p)
    assert raw["exploration_mode"] == "innovate"
    assert "experiment_mode" not in raw.get("agent", {})
    assert r["migrated_to"] == "innovate"


def test_exploration_style_maps(tmp_path):
    p = tmp_path / "nn-config.yaml"
    p.write_text("exploration:\n  style: aggressive\n  mode: balanced\n", encoding="utf-8")
    migrate(p, write=True, backup=False)
    raw = _read(p)
    assert raw["exploration_mode"] == "aggressive"   # style 优先于 mode
    assert raw.get("exploration") in (None, {})


def test_experiment_mode_block_maps(tmp_path):
    p = tmp_path / "nn-config.yaml"
    p.write_text("experiment:\n  mode: explore\n", encoding="utf-8")
    migrate(p, write=True, backup=False)
    raw = _read(p)
    assert raw["exploration_mode"] == "explore"
    assert "experiment" not in raw


def test_already_migrated_idempotent(tmp_path):
    p = tmp_path / "nn-config.yaml"
    p.write_text("exploration_mode: optimize\n", encoding="utf-8")
    r = migrate(p, write=True, backup=False)
    assert r["wrote"] is False
    assert r["migrated_to"] is None


def test_cannot_infer_fails_loud(tmp_path):
    """无任何 mode 信号 → ValueError（fail-loud，不静默选档）"""
    p = tmp_path / "nn-config.yaml"
    p.write_text("profile: supervised\n", encoding="utf-8")
    with pytest.raises(ValueError):
        migrate(p, write=True, backup=False)


def test_backup_created(tmp_path):
    p = tmp_path / "nn-config.yaml"
    p.write_text("agent:\n  experiment_mode: optimize\n", encoding="utf-8")
    migrate(p, write=True, backup=True)
    assert (tmp_path / "nn-config.yaml.deprecated.bak").is_file()


def test_dry_run_no_write(tmp_path):
    p = tmp_path / "nn-config.yaml"
    p.write_text("agent:\n  experiment_mode: aggressive\n", encoding="utf-8")
    r = migrate(p, write=False, backup=False)
    assert r["migrated_to"] == "aggressive"
    assert r["wrote"] is False
    assert "exploration_mode" not in _read(p)   # 未写盘
