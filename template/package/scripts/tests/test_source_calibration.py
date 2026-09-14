"""本机原仓校准门禁：解析原仓、比对容差、stamp 前 enforce。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.audit_core import repro_tolerance
from lib.source_calibration import (
    enforce_before_stamp,
    evaluate_check,
    gate_applies,
    resolve_source_repo,
    source_cal_skip_why,
)


def _write_migration_source(root: Path, text: str) -> None:
    d = root / ".auto-nn"
    d.mkdir(parents=True, exist_ok=True)
    (d / "migration-source").write_text(text + "\n", encoding="utf-8")


def _write_intent(root: Path, payload: dict) -> None:
    saved = root / "saved"
    saved.mkdir(parents=True, exist_ok=True)
    (saved / "baseline_start_intent.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def _write_cal(root: Path, payload: dict) -> None:
    saved = root / "saved"
    saved.mkdir(parents=True, exist_ok=True)
    (saved / "source_calibration.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def test_greenfield_gate_does_not_apply(tmp_path: Path):
    _write_migration_source(tmp_path, "# greenfield")
    assert resolve_source_repo(tmp_path) is None
    assert gate_applies(tmp_path, tag="reference", source="literature") is False
    assert enforce_before_stamp(
        tmp_path, tag="reference", source="literature", port_value=0.87
    ) is None


def test_midpoint_gate_does_not_apply_even_with_source_repo(tmp_path: Path):
    src = tmp_path / "upstream"
    src.mkdir()
    _write_migration_source(tmp_path, str(src))
    assert resolve_source_repo(tmp_path) == src.resolve()
    assert gate_applies(tmp_path, tag="reference", source="ledger_midpoint") is False
    assert enforce_before_stamp(
        tmp_path, tag="reference", source="ledger_midpoint", port_value=0.5
    ) is None


def test_skip_why_disables_gate(tmp_path: Path):
    src = tmp_path / "upstream"
    src.mkdir()
    _write_migration_source(tmp_path, str(src))
    _write_intent(tmp_path, {"source_cal_skip_why": "用户确认无原入口可跑"})
    assert source_cal_skip_why(tmp_path)
    assert gate_applies(tmp_path, tag="reference", source="literature") is False
    assert enforce_before_stamp(
        tmp_path, tag="reference", source="literature", port_value=0.87
    ) is None


def test_literature_without_calibration_file_raises_incomplete(tmp_path: Path):
    src = tmp_path / "upstream"
    src.mkdir()
    _write_migration_source(tmp_path, str(src))
    with pytest.raises(ValueError, match="校准"):
        enforce_before_stamp(
            tmp_path, tag="reference", source="literature", port_value=0.878
        )
    check = json.loads(
        (tmp_path / "saved" / "source_cal_check.json").read_text(encoding="utf-8")
    )
    assert check["verdict"] == "incomplete"
    assert "论文" not in check["next_action"] or "不要" in check["next_action"]
    assert "尺子" in check["next_action"] or "贴" in check["next_action"]


def test_calibration_value_unreadable_is_incomplete(tmp_path: Path):
    src = tmp_path / "upstream"
    src.mkdir()
    _write_migration_source(tmp_path, str(src))
    _write_cal(tmp_path, {"schema_version": 1, "source_cal_value": "not-a-number"})
    with pytest.raises(ValueError):
        enforce_before_stamp(
            tmp_path, tag="reference", source="literature", port_value=0.9
        )
    check = json.loads(
        (tmp_path / "saved" / "source_cal_check.json").read_text(encoding="utf-8")
    )
    assert check["verdict"] == "incomplete"


def test_delta_over_tolerance_raises_fail(tmp_path: Path):
    src = tmp_path / "upstream"
    src.mkdir()
    _write_migration_source(tmp_path, str(src))
    _write_cal(tmp_path, {"schema_version": 1, "source_cal_value": 0.95})
    with pytest.raises(ValueError, match="容差"):
        enforce_before_stamp(
            tmp_path, tag="reference", source="literature", port_value=0.87
        )
    check = json.loads(
        (tmp_path / "saved" / "source_cal_check.json").read_text(encoding="utf-8")
    )
    assert check["verdict"] == "fail"
    assert check["port_value"] == pytest.approx(0.87)
    assert check["source_cal_value"] == pytest.approx(0.95)
    assert "禁止" in check["next_action"] or "不要" in check["next_action"]


def test_delta_within_tolerance_passes_and_writes_check(tmp_path: Path):
    src = tmp_path / "upstream"
    src.mkdir()
    _write_migration_source(tmp_path, str(src))
    _write_cal(tmp_path, {"schema_version": 1, "source_cal_value": 0.95})
    out = enforce_before_stamp(
        tmp_path, tag="reference", source="literature", port_value=0.948
    )
    assert out is not None
    assert out["verdict"] == "pass"
    check = json.loads(
        (tmp_path / "saved" / "source_cal_check.json").read_text(encoding="utf-8")
    )
    assert check["verdict"] == "pass"
    assert check["port_value"] == pytest.approx(0.948)


def test_evaluate_check_shares_repro_tolerance():
    near = 0.0
    check = evaluate_check(port_value=0.87, source_cal_value=0.95, near_best_abs=near)
    assert check["tolerance"] == pytest.approx(repro_tolerance(0.95, near))
    assert check["verdict"] == "fail"
    tight = evaluate_check(port_value=0.948, source_cal_value=0.95, near_best_abs=near)
    assert tight["verdict"] == "pass"
    wide = evaluate_check(port_value=0.87, source_cal_value=0.95, near_best_abs=0.1)
    assert wide["tolerance"] == pytest.approx(0.1)
    assert wide["verdict"] == "pass"


def test_intent_source_repo_path_when_migration_is_greenfield(tmp_path: Path):
    src = tmp_path / "paper-repo"
    src.mkdir()
    _write_migration_source(tmp_path, "# greenfield")
    _write_intent(tmp_path, {"source_repo_path": str(src)})
    assert resolve_source_repo(tmp_path) == src.resolve()
    assert gate_applies(tmp_path, tag="reference", source="literature") is True


def test_incomparable_status_forbids_stamp(tmp_path: Path):
    src = tmp_path / "upstream"
    src.mkdir()
    _write_migration_source(tmp_path, str(src))
    _write_cal(
        tmp_path,
        {
            "schema_version": 1,
            "source_cal_value": 0.95,
            "source_cal_status": "incomparable",
        },
    )
    with pytest.raises(ValueError):
        enforce_before_stamp(
            tmp_path, tag="reference", source="literature", port_value=0.95
        )
    check = json.loads(
        (tmp_path / "saved" / "source_cal_check.json").read_text(encoding="utf-8")
    )
    assert check["verdict"] == "incomparable"
