"""build_synthesis_prompt: A1 — PDF method_excerpt 注入。"""
from __future__ import annotations
from lib.external.synthesis import build_synthesis_prompt


def test_paper_method_excerpt_injected():
    """A1: bundle.paper.method_excerpt 非空时,prompt 必须含全文段 + 强引导标记。"""
    bundle = {
        "paper": {
            "method_excerpt": "Use MgNetAB blocks with polynomial smoother coefficients.",
            "excerpt": "Long abstract about MgNet...",
        }
    }
    prompt = build_synthesis_prompt(
        phase1={"key_insight": "x"},
        phase2={"focus": "y"},
        external_bundle=bundle,
        tam_not_attested=[],
        fingerprint=None,
    )
    assert "MgNetAB" in prompt
    assert "[PDF FULL-TEXT EXCERPT — read carefully, not a hint]" in prompt
    assert "<paper_method_excerpt>" in prompt


def test_paper_method_excerpt_empty_falls_back():
    """A1: method_excerpt 空 → 整段不渲染,旧 URL+title 形态保留。"""
    bundle = {
        "paper": {"hits": [{"url": "https://arxiv.org/abs/1234", "title": "t"}], "method_excerpt": "", "excerpt": ""}
    }
    prompt = build_synthesis_prompt(
        phase1={"key_insight": "x"},
        phase2={"focus": "y"},
        external_bundle=bundle,
        tam_not_attested=[],
        fingerprint=None,
    )
    assert "[PDF FULL-TEXT EXCERPT" not in prompt
    # 旧 <paper_hits> 仍命中
    assert "https://arxiv.org/abs/1234" in prompt


def test_paper_method_excerpt_truncated_at_1500():
    """A1: method_excerpt > 1500 字符 → 截断到 1500 + 标记 [TRUNCATED]。"""
    long_text = "x" * 2000
    bundle = {"paper": {"method_excerpt": long_text, "excerpt": ""}}
    prompt = build_synthesis_prompt(
        phase1={"key_insight": "x"},
        phase2={"focus": "y"},
        external_bundle=bundle,
        tam_not_attested=[],
        fingerprint=None,
    )
    # 全文不应出现 2000 字符的连续 x
    assert prompt.count("x" * 1500) >= 1
    assert "[TRUNCATED]" in prompt
    # 截断标记前后 200 字符不应含原始 2000 字符全文
    assert prompt.count("x" * 2001) == 0


def test_synthesis_prompt_injects_pending_skeleton_queue(tmp_path, monkeypatch):
    """A2: saved/skeleton_queue.json 有 pending item → prompt 含 [OVERDUE]/[PENDING] 段。"""
    import json
    from pathlib import Path
    from scripts.lib.external.synthesis import build_synthesis_prompt

    saved = tmp_path / "saved"
    saved.mkdir()
    (saved / "skeleton_queue.json").write_text(json.dumps({
        "v": 1,
        "items": [
            {"id": "R5-Poly", "round": 5, "deadline_round": 6, "status": "pending_fill",
             "registry": "learner", "registry_name": "Poly", "class_name": "Poly",
             "paper_ref": "arxiv:2503.10594"},  # OVERDUE (current=7 > deadline=6)
            {"id": "R7-Foo", "round": 7, "deadline_round": 9, "status": "pending_fill",
             "registry": "objective", "registry_name": "Foo", "class_name": "Foo",
             "paper_ref": "arxiv:2401.xxxxx"},  # PENDING
        ],
    }))

    monkeypatch.setenv("NN_SAVED_DIR", str(saved))

    prompt = build_synthesis_prompt(
        phase1={"key_insight": "x"},
        phase2={"focus": "y"},
        external_bundle={"paper": {}},
        tam_not_attested=[],
        fingerprint=None,
        current_round=7,
    )

    assert "<pending_skeleton_queue>" in prompt
    assert "[OVERDUE] Poly" in prompt
    assert "[PENDING] Foo" in prompt