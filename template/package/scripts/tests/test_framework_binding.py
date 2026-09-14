"""framework_binding 总表：schema / 对账 / doctor / smoke。"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from lib.framework_binding import (
    assert_eval_binding,
    check_eval_binding_smoke,
    framework_binding_doctor,
    load_framework_binding,
    validate_framework_binding,
    write_eval_export_raw,
)


def _minimal_doc(**overrides) -> dict:
    doc = {
        "version": 1,
        "data": {
            "status": "bound",
            "kind": "framework_dataset",
            "entry": "x",
            "notes": "n",
        },
        "train": {
            "status": "bound",
            "mech": "in_process",
            "hooks": ["framework_train"],
            "notes": "n",
        },
        "eval": {
            "status": "bound",
            "kind": "api",
            "primary_raw_key": "score",
            "ledger_primary_key": "avg_acc",
            "callable": "framework_eval_raw",
            "notes": "n",
        },
        "train_log": {"status": "bound", "mode": "post_hoc_files", "notes": "n"},
        "checkpoint": {
            "status": "unavailable",
            "reason": "no map",
            "maps_to": "unavailable",
            "notes": "n",
        },
    }
    doc.update(overrides)
    return doc


def _write_binding(tmp_path: Path, doc: dict) -> Path:
    p = tmp_path / "contract" / "framework_binding.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return p


def test_load_missing_returns_none(tmp_path: Path):
    assert load_framework_binding(tmp_path) is None


def test_validate_minimal_bound_ok():
    assert validate_framework_binding(_minimal_doc()) == []


def test_validate_missing_section_fails():
    doc = {"version": 1, "data": {"status": "unavailable", "reason": "x"}}
    errs = validate_framework_binding(doc)
    assert any("train" in e for e in errs)


def test_unavailable_requires_reason():
    doc = {
        "version": 1,
        "data": {"status": "unavailable"},
        "train": {"status": "unavailable", "reason": "t"},
        "eval": {"status": "unavailable", "reason": "e"},
        "train_log": {"status": "unavailable", "reason": "l"},
        "checkpoint": {"status": "unavailable", "reason": "c"},
    }
    errs = validate_framework_binding(doc)
    assert any("data" in e and "reason" in e for e in errs)


def test_assert_eval_binding_pass():
    assert_eval_binding(
        {"score": 0.8},
        {"avg_acc": 0.8},
        {"primary_raw_key": "score", "ledger_primary_key": "avg_acc"},
    )


def test_assert_eval_binding_mean_invent_fails():
    with pytest.raises(ValueError, match="mismatch"):
        assert_eval_binding(
            {"score": 0.9},
            {"avg_acc": 0.75},
            {"primary_raw_key": "score", "ledger_primary_key": "avg_acc"},
        )


def test_doctor_skip_when_no_file_and_not_framework(tmp_path: Path):
    assert framework_binding_doctor(tmp_path) == []


def test_doctor_fail_when_framework_missing_file(tmp_path: Path):
    (tmp_path / "EXPERIENCE.md").write_text("对象类型=framework\n", encoding="utf-8")
    rows = framework_binding_doctor(tmp_path)
    assert any(r[0] == "fw_binding_decl" and r[1] == "FAIL" for r in rows)


def test_doctor_warn_unavailable(tmp_path: Path):
    doc = {
        "version": 1,
        "data": {"status": "unavailable", "reason": "d"},
        "train": {"status": "unavailable", "reason": "t"},
        "eval": {"status": "unavailable", "reason": "e"},
        "train_log": {"status": "unavailable", "reason": "l"},
        "checkpoint": {
            "status": "unavailable",
            "reason": "c",
            "maps_to": "unavailable",
        },
    }
    _write_binding(tmp_path, doc)
    rows = framework_binding_doctor(tmp_path)
    assert any(r[0] == "fw_binding_gaps" and r[1] == "WARN" for r in rows)
    assert any(r[0] == "fw_binding_decl" and r[1] == "PASS" for r in rows)


def test_doctor_eval_hook_fail(tmp_path: Path):
    _write_binding(tmp_path, _minimal_doc())
    (tmp_path / "workspace").mkdir()
    (tmp_path / "workspace" / "__init__.py").write_text("# empty\n", encoding="utf-8")
    rows = framework_binding_doctor(tmp_path)
    assert any(r[0] == "fw_binding_eval_hook" and r[1] == "FAIL" for r in rows)


def test_doctor_eval_hook_pass(tmp_path: Path):
    _write_binding(tmp_path, _minimal_doc())
    (tmp_path / "workspace").mkdir()
    (tmp_path / "workspace" / "__init__.py").write_text(
        "def framework_eval_raw():\n    return {}\n",
        encoding="utf-8",
    )
    rows = framework_binding_doctor(tmp_path)
    assert any(r[0] == "fw_binding_eval_hook" and r[1] == "PASS" for r in rows)


def test_smoke_check_mismatch(tmp_path: Path):
    _write_binding(tmp_path, _minimal_doc())
    exp = tmp_path / "_runs" / "exp" / "t1"
    exp.mkdir(parents=True)
    write_eval_export_raw(exp, {"score": 0.9})
    (exp / "results.json").write_text('{"avg_acc": 0.5}', encoding="utf-8")
    with pytest.raises(ValueError, match="mismatch"):
        check_eval_binding_smoke(tmp_path)


def test_smoke_check_ok(tmp_path: Path):
    _write_binding(tmp_path, _minimal_doc())
    exp = tmp_path / "_runs" / "exp" / "t1"
    exp.mkdir(parents=True)
    write_eval_export_raw(exp, {"score": 0.9})
    (exp / "results.json").write_text('{"avg_acc": 0.9}', encoding="utf-8")
    check_eval_binding_smoke(tmp_path)


def test_smoke_noop_without_binding(tmp_path: Path):
    check_eval_binding_smoke(tmp_path)
