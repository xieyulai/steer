"""Policy must_individual O3 slug 对齐 hard-gate 真名。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.init_interaction_policy import is_must_individual, load_policy  # noqa: E402


def test_o3_baseline_anchors_is_must_individual():
    policy_path = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "init"
        / "init-interaction-policy.yaml"
    )
    policy = load_policy(policy_path)
    assert is_must_individual(policy, "O3-baseline-anchors")
    assert not is_must_individual(policy, "O3-exploration")
    mi = policy.get("must_individual") or []
    assert "O3-baseline-anchors" in mi
    assert "O3-exploration" not in mi
