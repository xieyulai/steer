"""The ledger TSV header column order must be deterministic (template 4.1.1 fix:
the overlay keys used to be a frozenset).

Background: ``_LEDGER_OVERLAY_KEYS`` was a frozenset ⇒ its iteration order varies
with the process' PYTHONHASHSEED ⇒ the extra columns appended by
``_effective_ledger_context_keys()`` come out in a random order ⇒
``_default_tsv_columns()`` produces two different headers across two runs ⇒
the tsv_header check in verify/doctor "may FAIL right after a regen".
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PKG))

from experiment import ExperimentBase, _LEDGER_OVERLAY_KEYS  # noqa: E402

_PROBE = """
import sys
sys.path.insert(0, {pkg!r})
from experiment import ExperimentBase


class C(ExperimentBase):
    @property
    def metric_keys(self):
        return {{"acc": "maximize"}}


print("\\t".join(C()._default_tsv_columns()))
"""


def _columns_in_subprocess(hashseed: str, cwd: Path) -> str:
    env = dict(os.environ, PYTHONHASHSEED=hashseed)
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE.format(pkg=str(PKG))],
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def test_overlay_keys_are_ordered_tuple():
    """The overlay keys must be an ordered tuple (written as a set the column order
    could never be restored)."""
    assert isinstance(_LEDGER_OVERLAY_KEYS, tuple)
    assert list(_LEDGER_OVERLAY_KEYS) == [
        "exploration_space",
        "untrained",
        "rehearsal_score",
    ]


def test_tsv_header_stable_across_hashseeds(tmp_path):
    """Processes with different PYTHONHASHSEED values must produce a column-for-column
    identical header.

    The seeds are 1/3/4: under these three seeds the iteration order of a set of
    strings really does differ (seeds 1 and 2 happen to be identical, so comparing
    only 1/2 would miss the regression). With the old set-based implementation this
    case was guaranteed to fail.
    """
    columns = {seed: _columns_in_subprocess(seed, tmp_path) for seed in ("1", "3", "4")}
    assert len(set(columns.values())) == 1, columns
    cols = columns["1"].split("\t")
    assert cols[:2] == ["experiment", "scenario_id"]
    # The three overlay columns follow baseline_tag / exploration_space in a fixed order
    assert cols.index("baseline_tag") < cols.index("exploration_space")
    assert cols.index("exploration_space") < cols.index("untrained")
    assert cols.index("untrained") < cols.index("rehearsal_score")
