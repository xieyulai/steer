"""Ticket 01 (#02): fetch_arxiv_excerpt 接线 — PDF 全文 → ToolResult 带 method_excerpt。

不触网 / 不调真 pdftotext：mock _download_pdf 返回字节、_pdftotext_excerpt 返回
样本全文。验证「PDF 下了能抽方法段」的接线，而非 pdftotext 本身。
"""
import shutil

from lib.external import pdf as pdf_mod
from lib.external.pdf import fetch_arxiv_excerpt


SAMPLE_PAPER = """\
1 Introduction

Prior work uses CNNs heavily on image classification.

2 Related Work

ResNet introduced residual connections.

3 Method

We propose a novel architecture called FooNet using stacked residual
blocks with an attention gate. We use the Adam optimizer with learning
rate 1e-3 and batch size 128. Algorithm 1 describes the training procedure.

4 Experiments

We evaluate on CIFAR-10 and achieve 95% accuracy.
"""


def test_fetch_arxiv_excerpt_populates_method_excerpt(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda cmd: "/fake/pdftotext")
    monkeypatch.setattr(
        pdf_mod, "_download_pdf", lambda aid, *, timeout_sec: b"%PDF-fake%%EOF"
    )
    monkeypatch.setattr(
        pdf_mod,
        "_pdftotext_excerpt",
        lambda pdf_path, *, max_chars, timeout_sec: SAMPLE_PAPER,
    )

    result = fetch_arxiv_excerpt("2401.00001")

    assert result.status == "ok"
    # method 段被抽出来
    assert result.method_excerpt is not None
    assert "FooNet" in result.method_excerpt
    assert result.impl_hints  # 非空
    joined = " ".join(result.impl_hints).lower()
    assert "adam" in joined or "learning rate" in joined
    # 原始 excerpt（截断全文）仍保留 — 向后兼容
    assert result.excerpt is not None


def test_fetch_arxiv_excerpt_empty_text_skips_not_crash(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda cmd: "/fake/pdftotext")
    monkeypatch.setattr(
        pdf_mod, "_download_pdf", lambda aid, *, timeout_sec: b"%PDF-fake%%EOF"
    )
    monkeypatch.setattr(
        pdf_mod, "_pdftotext_excerpt", lambda pdf_path, *, max_chars, timeout_sec: ""
    )

    result = fetch_arxiv_excerpt("2401.00002")

    # 空文本 → skipped，不崩；method 字段为空
    assert result.status == "skipped"
    assert result.method_excerpt is None
    assert result.impl_hints == []


# ── Ticket 02: .txt 落盘（PDF 全文持久化）───
def test_fetch_arxiv_excerpt_persists_txt_with_persist_dir(tmp_path, monkeypatch):
    """persist_dir 给定时,应同时落 {arxiv_id}.pdf 和 {arxiv_id}.txt。"""
    monkeypatch.setattr(shutil, "which", lambda cmd: "/fake/pdftotext")
    monkeypatch.setattr(
        pdf_mod, "_download_pdf", lambda aid, *, timeout_sec: b"%PDF-fake%%EOF"
    )
    monkeypatch.setattr(
        pdf_mod,
        "_pdftotext_excerpt",
        lambda pdf_path, *, max_chars, timeout_sec: SAMPLE_PAPER,
    )

    persist_dir = tmp_path / "pdfs"
    result = fetch_arxiv_excerpt("2403.06870", persist_dir=persist_dir)

    assert result.status == "ok"
    # .pdf 与 .txt 同级落盘
    assert (persist_dir / "2403.06870.pdf").is_file()
    assert (persist_dir / "2403.06870.txt").is_file()
    # .txt 内容 = pdftotext 抽出的全文（不被截断）
    txt_content = (persist_dir / "2403.06870.txt").read_text(encoding="utf-8")
    assert "FooNet" in txt_content
    # ToolResult schema 不变（向后兼容）
    assert result.excerpt is not None
    assert result.local_path is not None
    assert result.local_path.endswith("2403.06870.pdf")


def test_fetch_arxiv_excerpt_no_persist_no_txt(tmp_path, monkeypatch):
    """persist_dir=None 时不写任何文件到磁盘。"""
    monkeypatch.setattr(shutil, "which", lambda cmd: "/fake/pdftotext")
    monkeypatch.setattr(
        pdf_mod, "_download_pdf", lambda aid, *, timeout_sec: b"%PDF-fake%%EOF"
    )
    monkeypatch.setattr(
        pdf_mod,
        "_pdftotext_excerpt",
        lambda pdf_path, *, max_chars, timeout_sec: SAMPLE_PAPER,
    )

    result = fetch_arxiv_excerpt("2403.06870")  # no persist_dir

    assert result.status == "ok"
    # tmp_path 下不应出现 .pdf 或 .txt
    assert not list(tmp_path.glob("*.txt"))
    assert not list(tmp_path.glob("*.pdf"))


def test_fetch_arxiv_excerpt_reuse_path_writes_txt(tmp_path, monkeypatch):
    """已落 .pdf 时,第二次调用应补抽并写 .txt（若 .txt 缺失）。"""
    monkeypatch.setattr(shutil, "which", lambda cmd: "/fake/pdftotext")
    monkeypatch.setattr(
        pdf_mod, "_download_pdf", lambda aid, *, timeout_sec: b"%PDF-fake%%EOF"
    )
    monkeypatch.setattr(
        pdf_mod,
        "_pdftotext_excerpt",
        lambda pdf_path, *, max_chars, timeout_sec: SAMPLE_PAPER,
    )

    persist_dir = tmp_path / "pdfs"
    persist_dir.mkdir()
    # 预埋 .pdf 模拟已有 PDF（且 EOF 校验通过）
    (persist_dir / "2403.06870.pdf").write_bytes(b"%PDF-fake%%EOF")

    # 第一次调用 → 复用 .pdf 抽全文,应补写 .txt
    result = fetch_arxiv_excerpt("2403.06870", persist_dir=persist_dir)
    assert result.status == "ok"
    txt_path = persist_dir / "2403.06870.txt"
    assert txt_path.is_file()
    assert "FooNet" in txt_path.read_text(encoding="utf-8")
