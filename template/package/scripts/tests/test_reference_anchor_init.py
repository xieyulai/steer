"""满 10 轮才注入 reference-anchor-init。"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location("_brc_ref", _SCRIPTS / "build-run-context.py")
brc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(brc)


def _journal(root: Path, n: int) -> None:
    saved = root / "saved"
    saved.mkdir(parents=True, exist_ok=True)
    entries = [{"kind": "round", "experiment": f"r{i}"} for i in range(n)]
    (saved / "experiment_journal.json").write_text(
        json.dumps({"schema_version": 1, "facts": {}, "analyse": {}, "entries": entries}),
        encoding="utf-8",
    )


def test_nine_rounds_no_emit(tmp_path: Path):
    _journal(tmp_path, 9)
    assert brc._emit_reference_start({"repo_root": tmp_path}) is None


def test_ten_rounds_emits(tmp_path: Path):
    _journal(tmp_path, 10)
    out = brc._emit_reference_start({"repo_root": tmp_path})
    assert out is not None
    assert "### reference-anchor-init" in out
    assert "/auto-nn-reference" in out
    assert "校准" in out
    assert "ledger_midpoint" in out


def test_has_reference_tag_no_emit(tmp_path: Path):
    _journal(tmp_path, 12)
    runs = tmp_path / "_runs"
    runs.mkdir()
    (runs / "results.tsv").write_text(
        "experiment\tscenario_id\tbaseline_tag\texp_dir\n"
        "r1\tseq\treference\t_runs/exp/r1\n",
        encoding="utf-8",
    )
    assert brc._emit_reference_start({"repo_root": tmp_path}) is None
