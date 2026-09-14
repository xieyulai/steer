"""反思证据包注入审查卡片摘要（结论，不是下一步建议）。"""
from __future__ import annotations

import json
from pathlib import Path

from lib.audit_core import write_index_entry
from lib.reflect_evidence import ReflectEvidenceBundle, build_reflect_evidence, format_evidence_markdown


def _seed(repo: Path, *, keeper_dir: str, audited: str) -> None:
    (repo / "nn-config.yaml").write_text(
        "agent:\n  scenario_default: seq\n", encoding="utf-8"
    )
    saved = repo / "saved"
    saved.mkdir(exist_ok=True)
    (saved / "keepers.json").write_text(
        json.dumps({"seq": {"keeper_exp_dir": keeper_dir}}), encoding="utf-8"
    )
    card_dir = saved / "audit" / "t1_seq"
    card_dir.mkdir(parents=True)
    (card_dir / "card.md").write_text(
        "# 审查卡片\n"
        "审的是：场景 seq\n"
        "复现：对上\n"
        "新不新：本次审查 novel\n",
        encoding="utf-8",
    )
    (card_dir / "card.json").write_text(
        json.dumps({"attested_depth": "novel", "repro_ok": True, "n_seeds": 3}),
        encoding="utf-8",
    )
    write_index_entry(
        repo,
        scenario_id="seq",
        card_dir=str(card_dir),
        audited_exp_dir=audited,
        config_sha256="aa",
    )


def test_bundle_default_audit_card_md_empty():
    b = ReflectEvidenceBundle()
    assert b.audit_card_md == ""


def test_build_reflect_evidence_injects_current_audit_card(tmp_path: Path):
    _seed(tmp_path, keeper_dir="_runs/exp/best", audited="_runs/exp/best")
    bundle = build_reflect_evidence(tmp_path)
    assert bundle.audit_card_md
    assert "当前这套已审查" in bundle.audit_card_md
    assert "## audit-card" in bundle.markdown
    assert "当前这套已审查" in bundle.markdown
    assert "建议下一步" not in bundle.audit_card_md


def test_build_reflect_evidence_superseded_prefixes_old_novel(tmp_path: Path):
    _seed(tmp_path, keeper_dir="_runs/exp/best", audited="_runs/exp/best")
    (tmp_path / "saved" / "keepers.json").write_text(
        json.dumps({"seq": {"keeper_exp_dir": "_runs/exp/newer"}}), encoding="utf-8"
    )
    bundle = build_reflect_evidence(tmp_path)
    assert "上一套已审查" in bundle.audit_card_md
    assert "上一套：" in bundle.audit_card_md
    assert "当前这套已审查" not in bundle.audit_card_md
    assert "## audit-card" in bundle.markdown
    assert "novel" in bundle.audit_card_md[bundle.audit_card_md.index("上一套：") :]


def test_build_reflect_evidence_omits_audit_card_without_index(tmp_path: Path):
    bundle = build_reflect_evidence(tmp_path)
    assert bundle.audit_card_md == ""
    assert "## audit-card" not in bundle.markdown


def test_format_evidence_truncation_keeps_audit_card():
    bundle = ReflectEvidenceBundle(
        summary_brief="X" * 20000,
        audit_card_md="审的是：场景 seq\n复现：对上",
    )
    md = format_evidence_markdown(bundle, max_chars=12000)
    assert "## audit-card" in md
    assert "审的是：场景 seq" in md
    assert "…(truncated)" in md
