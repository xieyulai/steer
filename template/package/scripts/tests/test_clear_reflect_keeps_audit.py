"""clear reflect 不删审查卡片 saved/audit/。"""
from __future__ import annotations

from pathlib import Path

from clear_reflect import SAVED_REFLECT_FILES, apply_clear_reflect

_CLEAR = Path(__file__).resolve().parents[1] / "clear_reflect.py"


def test_clear_reflect_does_not_list_audit_dir():
    text = _CLEAR.read_text(encoding="utf-8")
    assert "saved/audit" not in text or "不删" in text
    assert "saved/audit" not in SAVED_REFLECT_FILES
    assert "saved/audit/index.json" not in SAVED_REFLECT_FILES


def test_clear_reflect_apply_keeps_audit_index(tmp_path: Path):
    audit_index = tmp_path / "saved" / "audit" / "index.json"
    audit_index.parent.mkdir(parents=True)
    marker = '{"by_scenario": {"seq": {"latest": {"card_dir": "saved/audit/t1"}}}}\n'
    audit_index.write_text(marker, encoding="utf-8")
    reflect_latest = tmp_path / "saved" / "reflect_latest.json"
    reflect_latest.write_text('{"ok": true}\n', encoding="utf-8")

    apply_clear_reflect(tmp_path, dry_run=True)
    assert audit_index.is_file()
    assert audit_index.read_text(encoding="utf-8") == marker

    apply_clear_reflect(tmp_path, dry_run=False)
    assert audit_index.is_file(), "apply 后 saved/audit/index.json 必须仍在"
    assert audit_index.read_text(encoding="utf-8") == marker
    assert not reflect_latest.is_file()
