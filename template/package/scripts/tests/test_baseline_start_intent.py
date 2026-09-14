"""O3-baseline-anchors: baseline_start_intent → plain-anchor-init / reference-start。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location("_brc_intent", _SCRIPTS / "build-run-context.py")
brc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(brc)


def _write_intent(root: Path, data: dict) -> None:
    saved = root / "saved"
    saved.mkdir(parents=True, exist_ok=True)
    (saved / "baseline_start_intent.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def test_plain_init_includes_recipe_from_intent(tmp_path):
    _write_intent(
        tmp_path,
        {
            "scenario_id": "cifar10",
            "start_runs": "plain+reference",
            "plain_first": True,
            "plain_recipe": "simple_cnn",
            "plain_budget": "5min",
            "reference_run": True,
            "reference_method": "er",
            "reference_conditions": "aligned",
        },
    )
    out = brc._emit_plain_anchor_init({"repo_root": tmp_path, "run": 1})
    assert out is not None
    assert "FIRST-ROUND" in out
    assert "plain_recipe=simple_cnn" in out
    assert "scenario_id=cifar10" in out


def test_plain_init_skipped_when_tsv_has_plain_tag(tmp_path):
    _write_intent(
        tmp_path,
        {
            "scenario_id": "cifar10",
            "start_runs": "plain+reference",
            "plain_first": True,
            "plain_recipe": "simple_cnn",
        },
    )
    runs = tmp_path / "_runs"
    runs.mkdir()
    (runs / "results.tsv").write_text(
        "run_id\tscenario_id\tbaseline_tag\n1\tcifar10\tplain\n",
        encoding="utf-8",
    )
    assert brc._emit_plain_anchor_init({"repo_root": tmp_path, "run": 1}) is None


def test_plain_init_still_emits_when_experience_has_value_but_no_tag(tmp_path):
    """标签优先：仅有 EXPERIENCE 锚值、无 plain 标签 → 仍可发 init。"""
    _write_intent(
        tmp_path,
        {
            "start_runs": "plain",
            "plain_first": True,
            "plain_recipe": "cnn",
        },
    )
    (tmp_path / "EXPERIENCE.md").write_text(
        "## Tier 状态\n"
        "| Tier | routine | extend | novel | extra | plain(P) |\n"
        "|------|---------|--------|-------|-------|----------|\n"
        "| E    | - | - | - | - | plain_anchor_value=0.5 |\n",
        encoding="utf-8",
    )
    out = brc._emit_plain_anchor_init({"repo_root": tmp_path, "run": 1})
    assert out is not None
    assert "plain" in out.lower() or "plain_recipe" in out


def test_plain_skip_no_first_round(tmp_path):
    _write_intent(
        tmp_path,
        {
            "start_runs": "skip",
            "plain_first": False,
            "plain_skip_why": "smoke only",
        },
    )
    assert brc._emit_plain_anchor_init({"repo_root": tmp_path, "run": 1}) is None


def test_reference_start_emits_when_no_signal(tmp_path):
    """轮次不足 10 时不注入（即使 intent 要求 reference）。"""
    _write_intent(
        tmp_path,
        {
            "scenario_id": "default",
            "start_runs": "plain+reference",
            "reference_run": True,
            "reference_method": "derpp",
            "reference_conditions": "aligned",
            "reference_conditions_notes": "same OFFICIAL_TEST",
        },
    )
    assert brc._emit_reference_start({"repo_root": tmp_path, "run": 1}) is None


def test_reference_start_skipped_when_anchor_exists(tmp_path):
    _write_intent(
        tmp_path,
        {"start_runs": "plain+reference", "reference_run": True, "reference_method": "er"},
    )
    (tmp_path / "EXPERIENCE.md").write_text(
        "## 基线锚点（external reference）\n\n"
        "- reference_anchor_value: 0.91\n",
        encoding="utf-8",
    )
    assert brc._emit_reference_start({"repo_root": tmp_path}) is None


def test_reference_start_skipped_when_tsv_has_tag(tmp_path):
    _write_intent(
        tmp_path,
        {"start_runs": "plain+reference", "reference_run": True, "reference_method": "er"},
    )
    runs = tmp_path / "_runs"
    runs.mkdir()
    (runs / "results.tsv").write_text(
        "run_id\tbaseline_tag\n1\treference\n", encoding="utf-8"
    )
    assert brc._emit_reference_start({"repo_root": tmp_path}) is None


def test_misaligned_number_doc_contract_in_emit_text(tmp_path):
    """轮次不足时 misaligned intent 也不 emit。"""
    _write_intent(
        tmp_path,
        {
            "start_runs": "plain+reference",
            "reference_run": True,
            "reference_method": "paper_x",
            "reference_conditions": "misaligned",
        },
    )
    assert brc._emit_reference_start({"repo_root": tmp_path}) is None


def test_reference_start_always_none_even_with_intent(tmp_path):
    _write_intent(
        tmp_path,
        {
            "start_runs": "plain+reference",
            "reference_run": True,
            "reference_method": "er",
            "reference_conditions": "aligned",
        },
    )
    assert brc._emit_reference_start({"repo_root": tmp_path, "run": 1}) is None
