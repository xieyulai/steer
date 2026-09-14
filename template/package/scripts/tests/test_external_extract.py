"""Ticket 01 (#02): PDF 方法段抽取 — 纯函数 seam。

不测 I/O（下载 / pdftotext），只测确定性文本切块 + 关键句检索。
这是喂入层「arXiv PDF 不再只落 .txt」的可单测内核。
"""
from lib.external.extract import extract_method_excerpt


SAMPLE_PAPER = """\
1 Introduction

Image classification is a fundamental task. Prior work uses CNNs heavily.

2 Related Work

ResNet introduced residual connections. Many follow-ups exist in the literature.

3 Method

We propose a novel architecture called FooNet. It uses stacked residual
blocks with an attention gate. The key idea is to gate each residual block
by a learned scalar. We use the Adam optimizer with learning rate 1e-3 and
batch size 128. Algorithm 1 describes the full training procedure.

4 Experiments

We evaluate on CIFAR-10. Our method achieves 95% accuracy.
"""


def test_method_section_isolated_from_intro():
    out = extract_method_excerpt(SAMPLE_PAPER)
    assert out["method_excerpt"] is not None
    assert "FooNet" in out["method_excerpt"]
    assert "attention gate" in out["method_excerpt"]
    assert "Prior work uses CNNs" not in out["method_excerpt"]
    assert "CIFAR-10" not in out["method_excerpt"]
    assert out["section_title"] is not None
    assert "Method" in out["section_title"]


def test_impl_hints_collected_from_method_section():
    out = extract_method_excerpt(SAMPLE_PAPER)
    assert out["impl_hints"]
    joined = " ".join(out["impl_hints"]).lower()
    assert "adam" in joined or "learning rate" in joined
    assert "batch size" in joined


def test_no_method_section_returns_empty_not_crash():
    out = extract_method_excerpt("No headings here. Just abstract text.")
    assert out["method_excerpt"] is None
    assert out["impl_hints"] == []
    assert out["section_title"] is None
