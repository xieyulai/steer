"""exploration_mode(6档) → cfg.exploration(4值 router escalation 词表)映射。

router 仍消费 conservative/balanced/inductive/aggressive；config.py 把 6 档
exploration_mode 映射到这 4 值（lib/external/config.py 的 _MODE_TO_ESCALATION）。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import tempfile, yaml
from lib.external.config import load_external_config


def _write_cfg(d: Path, cfg: dict):
    (d / "nn-config.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")


# ── 5 显式档 → 4 值映射 ─────────────────────────────────────────

def test_careful_maps_conservative():
    with tempfile.TemporaryDirectory() as d:
        _write_cfg(Path(d), {"profile": "supervised", "exploration_mode": "careful"})
        cfg = load_external_config(Path(d))
        assert cfg.exploration == "conservative"


def test_optimize_maps_balanced():
    with tempfile.TemporaryDirectory() as d:
        _write_cfg(Path(d), {"profile": "supervised", "exploration_mode": "optimize"})
        cfg = load_external_config(Path(d))
        assert cfg.exploration == "balanced"


def test_innovate_maps_inductive():
    with tempfile.TemporaryDirectory() as d:
        _write_cfg(Path(d), {"profile": "supervised", "exploration_mode": "innovate"})
        cfg = load_external_config(Path(d))
        assert cfg.exploration == "inductive"


def test_aggressive_maps_aggressive():
    with tempfile.TemporaryDirectory() as d:
        _write_cfg(Path(d), {"profile": "supervised", "exploration_mode": "aggressive"})
        cfg = load_external_config(Path(d))
        assert cfg.exploration == "aggressive"


def test_explore_maps_balanced():
    """explore 档不触发 router paper 强查（→ balanced，非 inductive/aggressive）。"""
    with tempfile.TemporaryDirectory() as d:
        _write_cfg(Path(d), {"profile": "supervised", "exploration_mode": "explore"})
        cfg = load_external_config(Path(d))
        assert cfg.exploration == "balanced"


# ── auto 档：跟 auto.effective_mode 联动 ──────────────────────────

def test_auto_follows_effective_mode():
    """auto + auto.effective_mode: innovate → inductive。"""
    with tempfile.TemporaryDirectory() as d:
        _write_cfg(Path(d), {
            "profile": "supervised",
            "exploration_mode": "auto",
            "auto": {"effective_mode": "innovate"},
        })
        cfg = load_external_config(Path(d))
        assert cfg.exploration == "inductive"


def test_auto_aggressive_effective_mode():
    """auto + auto.effective_mode: aggressive → aggressive。"""
    with tempfile.TemporaryDirectory() as d:
        _write_cfg(Path(d), {
            "profile": "supervised",
            "exploration_mode": "auto",
            "auto": {"effective_mode": "aggressive"},
        })
        cfg = load_external_config(Path(d))
        assert cfg.exploration == "aggressive"


def test_auto_missing_effective_mode_defaults_optimize_balanced():
    """auto 无 effective_mode（或缺 auto 段）→ optimize → balanced（起步档默认）"""
    with tempfile.TemporaryDirectory() as d:
        _write_cfg(Path(d), {"profile": "supervised", "exploration_mode": "auto"})
        cfg = load_external_config(Path(d))
        assert cfg.exploration == "balanced"


# ── 缺失 / 异常兜底 ─────────────────────────────────────────────

def test_missing_exploration_mode_defaults_balanced():
    """缺 exploration_mode → balanced（非 conservative）。"""
    with tempfile.TemporaryDirectory() as d:
        _write_cfg(Path(d), {"profile": "supervised"})
        cfg = load_external_config(Path(d))
        assert cfg.exploration == "balanced"


def test_unknown_mode_falls_back_balanced():
    """未知名 → _MODE_TO_ESCALATION.get(m, 'balanced') → balanced。"""
    with tempfile.TemporaryDirectory() as d:
        _write_cfg(Path(d), {"profile": "supervised", "exploration_mode": "reckless"})
        cfg = load_external_config(Path(d))
        assert cfg.exploration == "balanced"
