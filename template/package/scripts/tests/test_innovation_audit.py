"""RDDN migrate (T2)：audit 只认 routine/derived/different/novel，extend 已退役。"""
from __future__ import annotations

from lib.innovation_audit import (
    audit_fingerprint_mismatch,
    audit_round,
    format_innovation_line,
)


def test_audit_round_accepts_rddn_depths():
    # 合法档词 + 有 rationale → 无警告
    assert audit_round("B", "routine", rationale="why") == []
    assert audit_round("B", "derived", rationale="why") == []
    assert audit_round("B", "different", rationale="why") == []


def test_audit_round_still_rejects_unknown_depth():
    warns = audit_round("B", "bogus", rationale="why")
    assert any(w.kind == "invalid_depth" for w in warns)


def test_audit_round_rejects_retired_extend():
    """v2.8.1: 旧 extend 已退役 → audit 硬拦 legacy_depth (FAIL, 带映射提示)。"""
    warns = audit_round("B", "extend", rationale="why")
    legacy = [w for w in warns if w.kind == "legacy_depth"]
    assert len(legacy) == 1
    assert legacy[0].level == "FAIL"
    assert "extend" in legacy[0].message and "derived" in legacy[0].message


def test_audit_round_legacy_exploration_space_column():
    """v2.8.1: TSV exploration_space 列旧词 (B-extend) 也硬拦。

    业务仓报告: agent 自报 exploration_space='B-extend' 但 innovation_depth='derived',
    audit 之前只校验 innovation_depth 不碰 exploration_space → 漏拦。
    """
    warns = audit_round("B", "derived", rationale="why", exploration_space="B-extend")
    legacy = [w for w in warns if w.kind == "legacy_depth"]
    assert len(legacy) == 1
    assert legacy[0].level == "FAIL"


def test_audit_round_new_depth_words_pass():
    """v2.8.1: RDDN 新词 routine/derived/different/novel 不触发 legacy_depth。"""
    for d in ("routine", "derived", "different", "novel"):
        warns = audit_round("B", d, rationale="why")
        assert not any(w.kind == "legacy_depth" for w in warns), f"{d} 不该被拦"


def test_depth_from_exploration_space():
    """helper: exploration_space = {tier}-{RDDN depth}; 旧 extend, 新 derived/different/novel。

    formal-novel 不在此域（含 - 与 tier 分隔符冲突, exploration_space 列从不出现）。
    """
    from lib.innovation_audit import _depth_from_exploration_space
    assert _depth_from_exploration_space("B-extend") == "extend"
    assert _depth_from_exploration_space("B-derived") == "derived"
    assert _depth_from_exploration_space("B-different") == "different"
    assert _depth_from_exploration_space("C-novel") == "novel"
    assert _depth_from_exploration_space("different") == "different"
    assert _depth_from_exploration_space("") == ""
    assert _depth_from_exploration_space("pdebench_fno2d") == ""


def test_find_legacy_depth_in_tsv(tmp_path):
    """v2.8.3: 扫 TSV exploration_space 列旧词 (extend→derived)。"""
    from lib.innovation_audit import find_legacy_depth_in_tsv
    tsv = tmp_path / "_runs" / "results.tsv"
    tsv.parent.mkdir(parents=True)
    tsv.write_text(
        "experiment\texploration_space\n"
        "r1\tB-routine\n"
        "r2\tB-extend\n"      # 旧词
        "r3\tC-derived\n"
        "r4\tB-extend\n"      # 旧词
        "r5\tA-novel\n",
        encoding="utf-8",
    )
    hits = find_legacy_depth_in_tsv(tmp_path)
    assert len(hits) == 2, f"应命中 2 行 extend; 实际 {len(hits)}"
    assert {h["row"] for h in hits} == {3, 5}  # 行号从 2 起(r2=L3, r4=L5)
    assert all(h["legacy"] == "extend" and h["suggest"] == "derived" for h in hits)
    assert hits[0]["exploration_space"] == "B-extend"


def test_find_legacy_depth_in_tsv_no_tsv(tmp_path):
    """无 TSV → 空列表（doctor 跳过）"""
    from lib.innovation_audit import find_legacy_depth_in_tsv
    assert find_legacy_depth_in_tsv(tmp_path) == []


def test_find_legacy_depth_in_tsv_clean(tmp_path):
    """全 RDDN 新词 → 空列表"""
    from lib.innovation_audit import find_legacy_depth_in_tsv
    tsv = tmp_path / "_runs" / "results.tsv"
    tsv.parent.mkdir(parents=True)
    tsv.write_text(
        "experiment\texploration_space\n"
        "r1\tB-routine\nr2\tB-derived\nr3\tC-different\n",
        encoding="utf-8",
    )
    assert find_legacy_depth_in_tsv(tmp_path) == []


def test_audit_routine_mislabel_flags_different_like_novel():
    """different 是形式创新（旧 novel 的别名）→ 命中 routine 提示应判 mislabel。"""
    warns = audit_round(
        "B", "different", rationale="x", diff_text="import torchvision; nn.CrossEntropyLoss",
    )
    assert any(w.kind == "routine_mislabel" for w in warns)


def test_audit_fingerprint_mismatch_accepts_new_depths():
    # derived/different 是合法档，agent=derived fp=different → 触发 depth_mismatch（而非 invalid）
    warns = audit_fingerprint_mismatch("derived", "different")
    assert any(w.kind == "depth_mismatch" for w in warns)
    # 同档不 mismatch
    assert audit_fingerprint_mismatch("different", "different") == []


def test_format_innovation_line_renders_new_depths():
    matrix = {"B": {"derived": "x", "different": "y"}}
    line = format_innovation_line(matrix)
    assert "derived:x" in line
    assert "different:y" in line
