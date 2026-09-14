"""governance-sync 必须下发 check_brief.py（auto-nn-check / console brief）。"""
from __future__ import annotations

from pathlib import Path

_SYNC = Path(__file__).resolve().parents[1] / "governance-sync.sh"


def test_governance_sync_ships_check_brief():
    text = _SYNC.read_text(encoding="utf-8")
    assert "scripts/check_brief.py" in text
    assert 'cp "$TEMPLATE_PKG/scripts/check_brief.py"' in text
