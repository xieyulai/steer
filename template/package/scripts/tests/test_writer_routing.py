"""Writers route through save_nn_config：forward + pop 迁移别名。"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml


def _read_raw(root: Path) -> dict:
    return yaml.safe_load((root / "nn-config.yaml").read_text(encoding="utf-8")) or {}


def test_save_then_load_top_level_fresh_no_alias(tmp_path):
    from lib.nn_config import load_nn_config, save_nn_config

    (tmp_path / "nn-config.yaml").write_text(
        "goal:\n  value: 0.9\nagent:\n  goal_value: 0.9\n  plateau_rounds: 3\n",
        encoding="utf-8",
    )
    raw = load_nn_config(tmp_path)
    raw["agent"]["goal_value"] = 0.95
    save_nn_config(tmp_path, raw)
    final = load_nn_config(tmp_path)
    goal = final.get("goal") or {}
    assert goal.get("target") == 0.95 or goal.get("value") == 0.95
    assert "goal_value" not in (final.get("agent") or {})
    assert final["agent"]["plateau_rounds"] == 3


def test_manage_goal_save_cfg_pops_alias(tmp_path):
    (tmp_path / "nn-config.yaml").write_text(
        "goal:\n  value: 0.9\nagent:\n  goal_value: 0.9\n  plateau_rounds: 3\n",
        encoding="utf-8",
    )
    mg_path = Path(__file__).resolve().parent.parent / "manage_goal.py"
    spec = importlib.util.spec_from_file_location("_test_manage_goal", mg_path)
    assert spec is not None and spec.loader is not None
    mg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mg)

    cfg = mg._load_cfg(tmp_path)
    cfg.setdefault("agent", {})["goal_value"] = 0.95
    mg._save_cfg(tmp_path, cfg)

    saved = _read_raw(tmp_path)
    goal = saved.get("goal") or {}
    assert goal.get("target") == 0.95 or goal.get("value") == 0.95
    assert "goal_value" not in (saved.get("agent") or {})
