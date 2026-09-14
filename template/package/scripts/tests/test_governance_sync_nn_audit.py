"""governance-sync 必须下发 nn_audit.py 与审查 lib。"""
from __future__ import annotations

from pathlib import Path

_SYNC = Path(__file__).resolve().parents[1] / "governance-sync.sh"


def test_governance_sync_ships_nn_audit():
    text = _SYNC.read_text(encoding="utf-8")
    assert "scripts/nn_audit.py" in text
    assert "scripts/lib/audit_core.py" in text
    assert "scripts/lib/audit_attest.py" in text
    assert 'cp "$TEMPLATE_PKG/scripts/nn_audit.py"' in text
    assert 'cp "$TEMPLATE_PKG/scripts/lib/audit_core.py"' in text
    assert "scripts/nn_baseline.py" in text
    assert "scripts/lib/baseline_stamp.py" in text
    assert 'cp "$TEMPLATE_PKG/scripts/nn_baseline.py"' in text
    assert 'cp "$TEMPLATE_PKG/scripts/lib/baseline_stamp.py"' in text
