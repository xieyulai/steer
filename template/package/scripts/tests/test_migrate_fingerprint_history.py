"""migrate_fingerprint_history：saved/innovation_fingerprint.json 旧 depth 词 → RDDN（一次性）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from migrate_fingerprint_history import migrate


def _write(root: Path, obj: dict) -> Path:
    fp = root / "saved" / "innovation_fingerprint.json"
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return fp


def _read(root: Path) -> dict:
    return json.loads((root / "saved" / "innovation_fingerprint.json").read_text(encoding="utf-8"))


def test_depth_fields_remap(tmp_path):
    """extend→derived、novel→different（depth/agent_depth/effective_depth 三字段）。"""
    _write(tmp_path, {
        "depth": "extend", "agent_depth": "novel",
        "effective_depth": "extend", "depth_rank": 2,
    })
    r = migrate(tmp_path, write=True, backup=False)
    raw = _read(tmp_path)
    assert raw["depth"] == "derived"
    assert raw["agent_depth"] == "different"
    assert raw["effective_depth"] == "derived"
    assert r["changed"] is True
    assert r["wrote"] is True


def test_depth_rank_rederived(tmp_path):
    """depth 由 extend(旧 rank 2) → different(novel 旧 rank 3) 时 rank 重算到当前 schema。"""
    _write(tmp_path, {"depth": "novel", "depth_rank": 99})  # 故意脏 rank
    migrate(tmp_path, write=True, backup=False)
    raw = _read(tmp_path)
    assert raw["depth"] == "different"
    assert raw["depth_rank"] == 3   # _DEPTH_RANK["different"]


def test_summary_line_remap(tmp_path):
    """summary_line 内嵌的旧 depth 词按词边界改写。"""
    _write(tmp_path, {"depth": "routine", "summary_line": "[Fingerprint: Tier B novel{...}]"})
    r = migrate(tmp_path, write=True, backup=False)
    raw = _read(tmp_path)
    assert raw["summary_line"] == "[Fingerprint: Tier B different{...}]"
    assert r["summary_line_changed"] is True
    # depth 未变 → depth_rank 不重算、不进 changed_fields
    assert r["fields"] == []


def test_already_rddn_idempotent(tmp_path):
    """已是 RDDN 词 → no-op，不改不写。"""
    obj = {"depth": "different", "agent_depth": "derived",
           "effective_depth": "routine", "depth_rank": 3,
           "summary_line": "[Fingerprint: Tier B different{}]"}
    _write(tmp_path, obj)
    r = migrate(tmp_path, write=True, backup=False)
    assert r["changed"] is False
    assert r["wrote"] is False
    assert _read(tmp_path) == obj   # 原样未动


def test_no_saved_file_noop(tmp_path):
    """无 saved 文件 → no-op（新仓 / 还没跑过 fingerprint）。"""
    r = migrate(tmp_path, write=True, backup=False)
    assert r["changed"] is False
    assert r["wrote"] is False


def test_corrupt_json_fails_loud(tmp_path):
    """JSON 损坏 → ValueError（不静默吞）。"""
    fp = tmp_path / "saved" / "innovation_fingerprint.json"
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        migrate(tmp_path, write=True, backup=False)


def test_non_dict_fails_loud(tmp_path):
    """顶层非 dict（如 list）→ ValueError。"""
    _write(tmp_path, {"depth": "novel"})  # 先建合法 dict
    fp = tmp_path / "saved" / "innovation_fingerprint.json"
    fp.write_text(json.dumps(["extend", "novel"]), encoding="utf-8")
    with pytest.raises(ValueError):
        migrate(tmp_path, write=True, backup=False)


def test_backup_created(tmp_path):
    """write=True + backup=True + 实际改写 → 建 .deprecated.bak 一次。"""
    _write(tmp_path, {"depth": "extend"})
    migrate(tmp_path, write=True, backup=True)
    assert (tmp_path / "saved" / "innovation_fingerprint.json.deprecated.bak").is_file()


def test_dry_run_no_write(tmp_path):
    """dry-run 不写盘（命中旧词但文件原样未动）。"""
    _write(tmp_path, {"depth": "extend", "depth_rank": 2})
    r = migrate(tmp_path, write=False, backup=False)
    assert r["changed"] is True
    assert r["wrote"] is False
    assert _read(tmp_path)["depth"] == "extend"   # 未改


def test_double_run_idempotent(tmp_path):
    """跑两次 = 跑一次（第二次 no-op）。"""
    _write(tmp_path, {"depth": "novel", "depth_rank": 3})
    migrate(tmp_path, write=True, backup=False)
    r2 = migrate(tmp_path, write=True, backup=False)
    assert r2["changed"] is False
    assert r2["wrote"] is False


def test_empty_agent_depth_left_alone(tmp_path):
    """agent_depth='' 透传（不是旧词）。"""
    _write(tmp_path, {"depth": "extend", "agent_depth": "", "effective_depth": "extend"})
    migrate(tmp_path, write=True, backup=False)
    raw = _read(tmp_path)
    assert raw["agent_depth"] == ""
    assert raw["depth"] == "derived"
