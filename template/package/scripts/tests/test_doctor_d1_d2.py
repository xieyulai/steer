"""doctor D1: init_align 轻闸；D2: abcde_manual_hygiene。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from init_align import doctor_check_init_align, write_align  # noqa: E402
from lib.scan_abcde_manual_hygiene import (  # noqa: E402
    doctor_abcde_manual_hygiene,
    find_abcde_manual_hygiene_issues,
)


def test_init_align_missing_warn(tmp_path: Path):
    st, msg = doctor_check_init_align(tmp_path)
    assert st == "WARN"
    assert "init-align.json" in msg


def test_init_align_bad_json_fail(tmp_path: Path):
    d = tmp_path / ".auto-nn"
    d.mkdir()
    (d / "init-align.json").write_text("{not json", encoding="utf-8")
    st, msg = doctor_check_init_align(tmp_path)
    assert st == "FAIL"
    assert "损坏" in msg or "JSON" in msg


def test_init_align_bad_schema_fail(tmp_path: Path):
    d = tmp_path / ".auto-nn"
    d.mkdir()
    (d / "init-align.json").write_text(
        json.dumps({"schema_version": 1, "workflow": "nope"}),
        encoding="utf-8",
    )
    st, _ = doctor_check_init_align(tmp_path)
    assert st == "FAIL"


def test_init_align_profile_mismatch_warn(tmp_path: Path):
    write_align(
        tmp_path,
        entry="A",
        source_root=None,
        workflow="build",
        object_type="code",
        profile="rl",
    )
    (tmp_path / "nn-config.yaml").write_text("profile: supervised\n", encoding="utf-8")
    st, msg = doctor_check_init_align(tmp_path)
    assert st == "WARN"
    assert "不一致" in msg


def test_init_align_ok_pass(tmp_path: Path):
    write_align(
        tmp_path,
        entry="A",
        source_root=None,
        workflow="build",
        object_type="code",
        profile="supervised",
    )
    (tmp_path / "nn-config.yaml").write_text("profile: supervised\n", encoding="utf-8")
    st, _ = doctor_check_init_align(tmp_path)
    assert st == "PASS"


def test_hygiene_no_manual_empty(tmp_path: Path):
    assert find_abcde_manual_hygiene_issues(tmp_path) == []
    assert doctor_abcde_manual_hygiene(tmp_path) is None


def test_hygiene_legacy_token_warn(tmp_path: Path):
    p = tmp_path / "references" / "manual"
    p.mkdir(parents=True)
    (p / "abcde-manual.md").write_text(
        "<!-- 对象类型=code -->\n默认对象类型: **code**\n\nworkspace_full junk\n",
        encoding="utf-8",
    )
    issues = find_abcde_manual_hygiene_issues(tmp_path)
    assert any("workspace_full" in i for i in issues)
    st, msg = doctor_abcde_manual_hygiene(tmp_path)
    assert st == "WARN"
    assert "workspace_full" in msg


def test_hygiene_header_body_conflict(tmp_path: Path):
    p = tmp_path / "references" / "manual"
    p.mkdir(parents=True)
    (p / "abcde-manual.md").write_text(
        "<!-- init 生成；对象类型=data；workflow=build -->\n"
        "## 1\n默认对象类型: **code**（说明）\n",
        encoding="utf-8",
    )
    issues = find_abcde_manual_hygiene_issues(tmp_path)
    assert any("冲突" in i for i in issues)


def test_hygiene_clean_pass(tmp_path: Path):
    p = tmp_path / "references" / "manual"
    p.mkdir(parents=True)
    (p / "abcde-manual.md").write_text(
        "<!-- init 生成；对象类型=code；workflow=build -->\n"
        "默认对象类型: **code**\n",
        encoding="utf-8",
    )
    assert find_abcde_manual_hygiene_issues(tmp_path) == []
    st, _ = doctor_abcde_manual_hygiene(tmp_path)
    assert st == "PASS"


def test_governance_sync_lists_hygiene():
    sync = SCRIPTS / "governance-sync.sh"
    text = sync.read_text(encoding="utf-8")
    assert "scan_abcde_manual_hygiene.py" in text
    manifest = SCRIPTS / "lib" / "governance_sync_manifest.yaml"
    assert "scan_abcde_manual_hygiene.py" in manifest.read_text(encoding="utf-8")
