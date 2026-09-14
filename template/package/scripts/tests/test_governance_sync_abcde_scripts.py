"""Lock ABCDE governance-sync copy list: ship init_workflow, not init_scenarios."""
from __future__ import annotations

import re
from pathlib import Path

_SYNC = Path(__file__).resolve().parents[1] / "governance-sync.sh"


def _abcde_for_block(text: str) -> str:
    """Extract the ABCDE ``for _abcde_script in ...; do`` list body."""
    m = re.search(
        r"for _abcde_script in \\\n(.*?)\n\s*do",
        text,
        flags=re.DOTALL,
    )
    assert m is not None, "ABCDE for-loop not found in governance-sync.sh"
    return m.group(1)


def test_abcde_sync_ships_init_workflow_not_init_scenarios():
    text = _SYNC.read_text(encoding="utf-8")
    block = _abcde_for_block(text)
    assert "init_workflow.py" in block
    assert "init_scenarios.py" not in block
    # Still ship the other ABCDE companions
    assert "init_o3_abcde.py" in block
    assert "abcde_migrate.py" in block
    assert "init_watchlist.py" in block
    assert "init_align.py" in block
    assert "write_baseline_start_intent.py" in block
    assert "align_probe.py" in _SYNC.read_text(encoding="utf-8")
