"""load_external_config: exploration_mode(6档) → router escalation 词表(4值)。"""
from __future__ import annotations
from pathlib import Path
import textwrap
from lib.external.config import load_external_config

def _write(root: Path, txt: str):
    (root / "nn-config.yaml").write_text(textwrap.dedent(txt), encoding="utf-8")

def test_exploration_mode_aggressive(tmp_path):
    _write(tmp_path, "exploration_mode: aggressive\nagent:\n  external_evidence_enabled: true\n")
    cfg = load_external_config(tmp_path)
    assert cfg.exploration == "aggressive"

def test_exploration_mode_innovate_maps_inductive(tmp_path):
    _write(tmp_path, "exploration_mode: innovate\nagent:\n  external_evidence_enabled: true\n")
    cfg = load_external_config(tmp_path)
    assert cfg.exploration == "inductive"

def test_exploration_mode_unknown_falls_back_balanced(tmp_path):
    """未知 exploration_mode → balanced（_MODE_TO_ESCALATION 兜底）。"""
    _write(tmp_path, "exploration_mode: reckless\nagent:\n  external_evidence_enabled: true\n")
    cfg = load_external_config(tmp_path)
    assert cfg.exploration == "balanced"
