"""S5: 答卷指定 reference 起步尺 → 首轮主动注入 reference-anchor-init (FIRST-ROUND)。

照 plain FIRST-ROUND 同型：round==1 ∧ intent 要求 reference ∧ 仓无 reference 信号。
intent 不要求（含缺省无 intent）→ 不发（原有逻辑：plain 照推、reference 走满 10 轮兜底）。
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location("_brc_ref_first", _SCRIPTS / "build-run-context.py")
brc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(brc)


def _write_intent(root: Path, data: dict) -> None:
    saved = root / "saved"
    saved.mkdir(parents=True, exist_ok=True)
    (saved / "baseline_start_intent.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def test_first_round_emits_for_reference_intent(tmp_path):
    _write_intent(
        tmp_path,
        {
            "schema_version": 1,
            "start_runs": "reference",
            "scenario_id": "b16",
            "reference_run": True,
            "reference_method": "paper_x",
        },
    )
    out = brc._emit_reference_anchor_first_round({"repo_root": tmp_path, "run": 1})
    assert out is not None
    assert "FIRST-ROUND" in out
    assert "reference_method=paper_x" in out
    assert "check-source-cal" in out
    assert "ledger_midpoint" in out


def test_first_round_emits_for_plain_plus_reference(tmp_path):
    _write_intent(tmp_path, {"start_runs": "plain+reference", "reference_run": True})
    assert brc._emit_reference_anchor_first_round({"repo_root": tmp_path, "run": 1}) is not None


def test_first_round_silent_when_anchor_exists(tmp_path):
    """已有锚值（EXPERIENCE external reference 段）→ 不发。"""
    _write_intent(tmp_path, {"start_runs": "reference", "reference_run": True})
    (tmp_path / "EXPERIENCE.md").write_text(
        "## 基线锚点（external reference）\n\n"
        "- reference_anchor_value: 0.91\n",
        encoding="utf-8",
    )
    assert brc._emit_reference_anchor_first_round({"repo_root": tmp_path, "run": 1}) is None


def test_first_round_silent_when_anchor_json_exists(tmp_path):
    _write_intent(tmp_path, {"start_runs": "reference", "reference_run": True})
    saved = tmp_path / "saved"
    (saved / "reference_anchor.json").write_text(
        json.dumps({"reference_anchor_value": 0.88}), encoding="utf-8"
    )
    assert brc._emit_reference_anchor_first_round({"repo_root": tmp_path, "run": 1}) is None


def test_first_round_silent_when_tsv_has_tag(tmp_path):
    _write_intent(tmp_path, {"start_runs": "reference", "reference_run": True})
    runs = tmp_path / "_runs"
    runs.mkdir()
    (runs / "results.tsv").write_text(
        "run_id\tbaseline_tag\n1\treference\n", encoding="utf-8"
    )
    assert brc._emit_reference_anchor_first_round({"repo_root": tmp_path, "run": 1}) is None


def test_no_emit_after_round_1(tmp_path):
    _write_intent(tmp_path, {"start_runs": "reference", "reference_run": True})
    assert brc._emit_reference_anchor_first_round({"repo_root": tmp_path, "run": 2}) is None


def test_no_emit_when_intent_wants_plain_only(tmp_path):
    """intent 只要 plain（含缺省无 intent）→ 不发，维持原有逻辑。"""
    _write_intent(tmp_path, {"start_runs": "plain", "plain_recipe": "cnn"})
    assert brc._emit_reference_anchor_first_round({"repo_root": tmp_path, "run": 1}) is None


def test_no_emit_without_intent(tmp_path):
    assert brc._emit_reference_anchor_first_round({"repo_root": tmp_path, "run": 1}) is None
