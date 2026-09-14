"""T8/ADR-3：catalog overlay（运行期软层）机制单测。

overlay = workspace/innovation_catalog.local.yaml，运行期累积、软、可回滚，由 reflect
「寻找」反馈边喂（04）。确定性判定器只硬信种子，overlay 当参考、不污染 depth（AC3）。
本文件测 overlay 自身的 load/append/rollback 机制；depth 不被污染的端到端见
test_innovation_fingerprint.py 的 overlay 软提示测试。
"""
from __future__ import annotations

from lib.external.catalog import (
    append_catalog_overlay,
    load_innovation_overlay,
    rollback_catalog_overlay,
)


# ── load：缺/空/坏 → {}（非致命，永不抛）──────────────────────────────────────
def test_load_overlay_missing_returns_empty(tmp_path):
    assert load_innovation_overlay(tmp_path) == {}


def test_load_overlay_corrupt_yaml_returns_empty(tmp_path):
    (tmp_path / "workspace").mkdir()
    (tmp_path / "workspace" / "innovation_catalog.local.yaml").write_text(
        "  : : not valid yaml ::", encoding="utf-8",
    )
    assert load_innovation_overlay(tmp_path) == {}


# ── append → load 回环 + source 打标 ─────────────────────────────────────────
def test_append_then_load_roundtrip(tmp_path):
    append_catalog_overlay(
        tmp_path,
        source="find_r5",
        table="objectives",
        key="focal",
        entry={"change": "drop_in", "paper_query": "Focal Loss"},
    )
    ov = load_innovation_overlay(tmp_path)
    assert "objectives" in ov and "focal" in ov["objectives"]
    rec = ov["objectives"]["focal"]
    assert rec["change"] == "drop_in"
    assert rec["source"] == "find_r5"  # source 打标（回滚依据）


def test_append_into_existing_table_merges(tmp_path):
    append_catalog_overlay(
        tmp_path, source="r1", table="objectives", key="focal", entry={"change": "drop_in"},
    )
    append_catalog_overlay(
        tmp_path, source="r2", table="objectives", key="polyloss", entry={"change": "drop_in"},
    )
    ov = load_innovation_overlay(tmp_path)
    assert set(ov["objectives"].keys()) == {"focal", "polyloss"}


def test_append_empty_table_or_key_is_noop(tmp_path):
    append_catalog_overlay(
        tmp_path, source="r1", table="", key="x", entry={"change": "drop_in"},
    )
    append_catalog_overlay(
        tmp_path, source="r1", table="objectives", key="", entry={"change": "drop_in"},
    )
    assert load_innovation_overlay(tmp_path) == {}


# ── rollback：按 source 批量清 + 空 overlay 文件自动删 ─────────────────────────
def test_rollback_by_source_removes_only_matching(tmp_path):
    append_catalog_overlay(
        tmp_path, source="r5", table="objectives", key="focal", entry={"change": "drop_in"},
    )
    append_catalog_overlay(
        tmp_path, source="r6", table="objectives", key="polyloss", entry={"change": "drop_in"},
    )
    removed = rollback_catalog_overlay(tmp_path, "r5")
    assert removed == 1
    ov = load_innovation_overlay(tmp_path)
    assert "focal" not in ov.get("objectives", {})
    assert "polyloss" in ov["objectives"]  # r6 保留


def test_rollback_last_entry_removes_file(tmp_path):
    """回滚到空 → overlay 文件删掉（恢复到无 overlay 初态，AC4③「恢复」）。"""
    append_catalog_overlay(
        tmp_path, source="r5", table="objectives", key="focal", entry={"change": "drop_in"},
    )
    rollback_catalog_overlay(tmp_path, "r5")
    assert not (tmp_path / "workspace" / "innovation_catalog.local.yaml").is_file()
    assert load_innovation_overlay(tmp_path) == {}


def test_rollback_cross_table_by_source(tmp_path):
    """同一 source 跨多表落盘 → 一次 rollback 全清。"""
    append_catalog_overlay(
        tmp_path, source="r5", table="objectives", key="focal", entry={"change": "drop_in"},
    )
    append_catalog_overlay(
        tmp_path, source="r5", table="data_strategies", key="mixup", entry={"change": "drop_in"},
    )
    append_catalog_overlay(
        tmp_path, source="r6", table="objectives", key="polyloss", entry={"change": "drop_in"},
    )
    removed = rollback_catalog_overlay(tmp_path, "r5")
    assert removed == 2
    ov = load_innovation_overlay(tmp_path)
    assert "focal" not in ov.get("objectives", {})
    assert "mixup" not in ov.get("data_strategies", {})
    assert "polyloss" in ov["objectives"]


def test_rollback_nonexistent_source_is_noop(tmp_path):
    append_catalog_overlay(
        tmp_path, source="r5", table="objectives", key="focal", entry={"change": "drop_in"},
    )
    removed = rollback_catalog_overlay(tmp_path, "never_existed")
    assert removed == 0
    ov = load_innovation_overlay(tmp_path)
    assert "focal" in ov["objectives"]  # 原条目不动


# ── find_discoveries 表：T4 反馈边原始候选落盘（非技法、不触 soft-hint）──────────
def test_append_find_discoveries_roundtrip(tmp_path):
    """寻找反馈边：原始 paper/ecosystem 候选落 find_discoveries 表（key=reflect_id）。"""
    append_catalog_overlay(
        tmp_path,
        source="r5",
        table="find_discoveries",
        key="r5",
        entry={
            "depth": "different",
            "paper_candidates": [{"title": "CoordAtt"}],
            "ecosystem_candidates": [{"name": "coord-att-lib"}],
        },
    )
    ov = load_innovation_overlay(tmp_path)
    assert ov["find_discoveries"]["r5"]["paper_candidates"][0]["title"] == "CoordAtt"
    assert ov["find_discoveries"]["r5"]["source"] == "r5"


def test_find_discoveries_rollback_by_reflect_id(tmp_path):
    """按 reflect_id 回滚 find 痕迹（反馈边可回滚，AC2）。"""
    append_catalog_overlay(
        tmp_path, source="r5", table="find_discoveries", key="r5", entry={"depth": "different"},
    )
    append_catalog_overlay(
        tmp_path, source="r6", table="find_discoveries", key="r6", entry={"depth": "novel"},
    )
    removed = rollback_catalog_overlay(tmp_path, "r5")
    assert removed == 1
    ov = load_innovation_overlay(tmp_path)
    assert "r5" not in ov.get("find_discoveries", {})
    assert "r6" in ov["find_discoveries"]
