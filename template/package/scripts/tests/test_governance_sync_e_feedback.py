"""governance-sync 必须下发打格与改题待办脚本及 lib。"""
from __future__ import annotations

from pathlib import Path

_SYNC = Path(__file__).resolve().parents[1] / "governance-sync.sh"


def test_governance_sync_ships_e_feedback_and_exploration_stamp():
    text = _SYNC.read_text(encoding="utf-8")
    for rel in (
        "scripts/e_feedback.py",
        "scripts/check_exploration_stamp.py",
        "scripts/lib/exploration_stamp.py",
        "scripts/lib/e_feedback_store.py",
    ):
        assert rel in text
    assert 'cp "$TEMPLATE_PKG/scripts/e_feedback.py"' in text
    assert 'cp "$TEMPLATE_PKG/scripts/check_exploration_stamp.py"' in text
    assert 'cp "$TEMPLATE_PKG/scripts/lib/exploration_stamp.py"' in text
    assert 'cp "$TEMPLATE_PKG/scripts/lib/e_feedback_store.py"' in text


def test_governance_sync_regens_existing_tsv_header():
    """已有成绩表时 sync 末必须 regen，避免 overlay 列顺序导致 tsv_header FAIL。"""
    text = _SYNC.read_text(encoding="utf-8")
    assert "_runs/results.tsv" in text
    assert "regen_results_tsv.py" in text
    assert "--sync-jsonl" in text
