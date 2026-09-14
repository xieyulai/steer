"""T3/ADR-2 Piece 3：attested_depth wiring in reflect_hook。

attested_depth = apply_novel_ceiling(fingerprint.depth, bundle raw verdict, paper_depth)。
关键：用 bundle 的 raw verdict（LLM-judged，喂全文），不用 compute_external_attestation
的宽口径（后者 paper_hits≥1 即 supported，会误升 novel）。无 fingerprint → None。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.external.reflect_hook import (
    compute_attested_depth,
    update_innovation_audit_external,
)


# ── compute_attested_depth（gate 接线：不同→novel 只在 supported∧P3+）─────────
def test_attested_p3_supported_different_to_novel():
    fp = {"depth": "different"}
    bundle = {"code": {"routine_attestation": {"verdict": "supported"}}}
    assert compute_attested_depth(fp, bundle, {"paper_depth": "P3"}) == "novel"


def test_attested_p2_supported_stays_different():
    fp = {"depth": "different"}
    bundle = {"code": {"routine_attestation": {"verdict": "supported"}}}
    assert compute_attested_depth(fp, bundle, {"paper_depth": "P2"}) == "different"


def test_attested_inconclusive_stays_different():
    fp = {"depth": "different"}
    bundle = {"code": {"routine_attestation": {"verdict": "inconclusive"}}}
    assert compute_attested_depth(fp, bundle, {"paper_depth": "P3"}) == "different"


def test_attested_routine_passthrough():
    """novel 只从 different 升：routine 透传，背书不抬档。"""
    fp = {"depth": "routine"}
    bundle = {"code": {"routine_attestation": {"verdict": "supported"}}}
    assert compute_attested_depth(fp, bundle, {"paper_depth": "P3"}) == "routine"


def test_attested_no_fingerprint_returns_none():
    """novel 是 fingerprint different 的背书 overlay；无 different → 无 overlay（None）。"""
    assert compute_attested_depth(
        None, {"code": {"routine_attestation": {"verdict": "supported"}}}, {"paper_depth": "P3"}
    ) is None
    assert compute_attested_depth({"depth": ""}, {}, {"paper_depth": "P3"}) is None


def test_attested_missing_verdict_defaults_inconclusive():
    """empty_bundle skip 路径无 verdict → 默认 inconclusive → different（不升 novel）。"""
    fp = {"depth": "different"}
    bundle = {"code": {}}  # 无 routine_attestation
    assert compute_attested_depth(fp, bundle, {"paper_depth": "P3"}) == "different"


# ── update_innovation_audit_external 持久化 attested_depth ──────────────────
def test_update_audit_persists_attested_depth(tmp_path):
    audit = tmp_path / "saved" / "innovation_audit.json"
    update_innovation_audit_external(tmp_path, "supported", attested_depth="novel")
    data = json.loads(audit.read_text(encoding="utf-8"))
    assert data["external_attestation"] == "supported"
    assert data["attested_depth"] == "novel"


def test_update_audit_none_attested_omits_field(tmp_path):
    update_innovation_audit_external(tmp_path, "skipped", attested_depth=None)
    data = json.loads(
        (tmp_path / "saved" / "innovation_audit.json").read_text(encoding="utf-8")
    )
    assert data["external_attestation"] == "skipped"
    assert "attested_depth" not in data
