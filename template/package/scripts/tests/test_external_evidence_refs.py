"""Ticket 04: round_decision evidence_refs/paper_hint — summarize + collect。

主体闭环切面（spec §4）：把外部证据包（saved/evidence_bundle.json）的关键命中
（标题 + 方法摘要 + URL）压成 round_decision 的 evidence_refs / paper_hint 字段。
- Slice 1: summarize_evidence(bundle)->dict 纯函数（无 IO）
- Slice 2: collect_round_evidence(saved_dir)->dict 读 saved/evidence_bundle.json（IO）
落盘（Slice 3）/ 注入下轮（Slice 4）在后。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.external.evidence_refs import collect_round_evidence, summarize_evidence  # noqa: E402


def _bundle(*, hits=None, method_excerpt=None, impl_hints=None, pdf_arxiv_id=None):
    """构造最小外部证据包 dict（对齐 empty_bundle['paper'] schema）。"""
    return {
        "schema_version": 1,
        "paper": {
            "hits": hits or [],
            "method_excerpt": method_excerpt,
            "impl_hints": impl_hints or [],
            "pdf_arxiv_id": pdf_arxiv_id,
        },
    }


def test_summarize_extracts_evidence_refs_from_hits():
    """有命中：evidence_refs 带 title+url（可追溯）；paper_hint 带方法摘要。"""
    hits = [
        {"title": "FooNet: Residual Attention Network", "abstract": "abc",
         "arxiv_id": "2401.00001", "url": "https://arxiv.org/abs/2401.00001", "sources": ["arxiv"]},
        {"title": "BarNet", "abstract": "def",
         "url": "https://doi.org/10.1000/bar", "sources": ["scholar"]},
    ]
    out = summarize_evidence(
        _bundle(
            hits=hits,
            method_excerpt="We propose FooNet with attention gating.",
            impl_hints=["Adam optimizer", "learning rate 1e-3"],
            pdf_arxiv_id="2401.00001",
        )
    )
    refs = out["evidence_refs"]
    assert isinstance(refs, list) and len(refs) == 2
    r0 = refs[0]
    assert r0["title"] == "FooNet: Residual Attention Network"
    assert r0["url"] == "https://arxiv.org/abs/2401.00001"
    # 可追溯（story #16）：带 arxiv_id 便于回查 bundle
    assert r0.get("arxiv_id") == "2401.00001"
    # paper_hint 把方法摘要喂给下轮 agent（字段注入的载体）
    assert "FooNet" in out["paper_hint"]
    assert "attention gating" in out["paper_hint"]


def test_summarize_empty_bundle_safe():
    """AC #4：空外部证据包 → evidence_refs=[] / paper_hint='' 不崩。"""
    out = summarize_evidence({})
    assert out["evidence_refs"] == []
    assert out["paper_hint"] == ""


def test_summarize_bundle_without_hits_safe():
    """bundle 存在但 paper.hits 空（检索了无命中）→ 同样不崩。"""
    out = summarize_evidence(_bundle(hits=[], method_excerpt=None))
    assert out["evidence_refs"] == []
    assert out["paper_hint"] == ""


def test_summarize_hit_without_url_derives_from_arxiv_id():
    """hit 无 url 字段 → 从 arxiv_id 兜底构造（防 URL 缺失导致 ref 无链接）。"""
    hits = [{"title": "BazNet", "abstract": "x", "arxiv_id": "2402.00002", "sources": ["arxiv"]}]
    out = summarize_evidence(_bundle(hits=hits))
    assert out["evidence_refs"][0]["url"] == "https://arxiv.org/abs/2402.00002"


def test_summarize_caps_evidence_refs():
    """evidence_refs 封顶（防 round_decision.json 被海量命中撑大）。"""
    hits = [
        {"title": f"Paper{i}", "abstract": "x", "arxiv_id": f"2401.{i:05d}",
         "url": f"https://arxiv.org/abs/2401.{i:05d}", "sources": ["arxiv"]}
        for i in range(10)
    ]
    out = summarize_evidence(_bundle(hits=hits))
    assert 1 <= len(out["evidence_refs"]) <= 5


# ---- Slice 2: collect_round_evidence IO 读取 ----

def _hit(title, *, arxiv_id=None, url=None):
    h = {"title": title, "abstract": "x", "sources": ["arxiv"]}
    if arxiv_id:
        h["arxiv_id"] = arxiv_id
    if url:
        h["url"] = url
    return h


def test_collect_reads_bundle_from_saved_dir(tmp_path):
    """saved/evidence_bundle.json 存在 → 摘要 evidence_refs / paper_hint。"""
    saved = tmp_path / "saved"
    saved.mkdir()
    bundle = {
        "schema_version": 1,
        "paper": {
            "hits": [_hit("FooNet", arxiv_id="2401.00001",
                          url="https://arxiv.org/abs/2401.00001")],
            "method_excerpt": "We propose FooNet with attention gating.",
            "impl_hints": ["Adam optimizer"],
        },
    }
    (saved / "evidence_bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
    out = collect_round_evidence(saved)
    assert out["evidence_refs"][0]["title"] == "FooNet"
    assert out["evidence_refs"][0]["url"] == "https://arxiv.org/abs/2401.00001"
    assert "attention gating" in out["paper_hint"]


def test_collect_missing_bundle_returns_empty(tmp_path):
    """AC #4：saved/ 无 evidence_bundle.json → 空摘要不崩。"""
    saved = tmp_path / "saved"
    saved.mkdir()
    out = collect_round_evidence(saved)
    # T4/ADR-6：collect_round_evidence 现带 find_candidates 字段（无寻找反馈时 = {}）
    assert out == {"evidence_refs": [], "paper_hint": "", "find_candidates": {}}


def test_collect_corrupt_bundle_returns_empty(tmp_path):
    """损坏 JSON → 空摘要（round_decision 落盘不可因坏 bundle 崩）。"""
    saved = tmp_path / "saved"
    saved.mkdir()
    (saved / "evidence_bundle.json").write_text("{ not valid json", encoding="utf-8")
    out = collect_round_evidence(saved)
    # T4/ADR-6：collect_round_evidence 现带 find_candidates 字段（无寻找反馈时 = {}）
    assert out == {"evidence_refs": [], "paper_hint": "", "find_candidates": {}}


def test_collect_empty_bundle_file_returns_empty(tmp_path):
    """bundle 文件 = {} → 空摘要。"""
    saved = tmp_path / "saved"
    saved.mkdir()
    (saved / "evidence_bundle.json").write_text("{}", encoding="utf-8")
    out = collect_round_evidence(saved)
    # T4/ADR-6：collect_round_evidence 现带 find_candidates 字段（无寻找反馈时 = {}）
    assert out == {"evidence_refs": [], "paper_hint": "", "find_candidates": {}}


def test_collect_accepts_string_path(tmp_path):
    """finalize_round 传 str 路径（Path 化）也能读。"""
    saved = tmp_path / "saved"
    saved.mkdir()
    bundle = {"paper": {"hits": [_hit("BazNet", arxiv_id="2403.00003",
          url="https://arxiv.org/abs/2403.00003")]}}
    (saved / "evidence_bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
    out = collect_round_evidence(str(saved))
    assert out["evidence_refs"][0]["title"] == "BazNet"
