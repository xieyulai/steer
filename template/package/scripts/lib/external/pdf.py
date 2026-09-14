"""arXiv PDF download + pdftotext excerpt; optional persist under saved/external_evidence/pdfs/."""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from lib.external.extract import extract_method_excerpt
from lib.external.models import ToolResult

_PDF_TIMEOUT_SEC = 300.0
_DEFAULT_MAX_CHARS = 4000
# pdftotext 取全文上限：method 段常位于摘要/intro 之后（>4000 字），excerpt 字段
# 仍按 max_chars 截断向后兼容，但方法抽取须跑在全文上（否则 #02 半残）。
_MAX_FULL_CHARS = 2_000_000


def _truncate_excerpt(full: str, *, max_chars: int) -> str | None:
    if not full:
        return None
    limit = max(1, int(max_chars))
    return full if len(full) <= limit else full[: limit - 1].rstrip() + "…"


def _build_ok_result(
    full_text: str | None, *, max_chars: int, local_path: str | None, http_calls: int
) -> ToolResult:
    """全文 → ToolResult：excerpt 截断向后兼容 + method_excerpt/impl_hints 抽取。"""
    excerpt = _truncate_excerpt(full_text, max_chars=max_chars)
    if not excerpt:
        return ToolResult.skipped("pdf", "empty_text")
    method = extract_method_excerpt(full_text)
    return ToolResult(
        status="ok",
        provider="pdf",
        excerpt=excerpt,
        method_excerpt=method["method_excerpt"],
        impl_hints=method["impl_hints"],
        local_path=local_path,
        http_calls=http_calls,
    )


def _normalize_arxiv_id(arxiv_id: str) -> str:
    raw = str(arxiv_id or "").strip()
    raw = re.sub(r"^https?://arxiv\.org/pdf/", "", raw, flags=re.I)
    raw = raw.removesuffix(".pdf")
    raw = re.sub(r"^https?://arxiv\.org/abs/", "", raw, flags=re.I)
    return re.sub(r"v\d+$", "", raw)


def _pdf_has_eof(data: bytes) -> bool:
    if not data:
        return False
    tail = data[-2048:] if len(data) > 2048 else data
    return b"%%EOF" in tail


def _repo_relative(repo_root: Path | None, path: Path) -> str:
    if repo_root is not None:
        try:
            return path.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            pass
    return path.as_posix()


def _download_pdf(aid: str, *, timeout_sec: float) -> bytes | ToolResult:
    pdf_url = f"https://arxiv.org/pdf/{aid}.pdf"
    req = urllib.request.Request(
        pdf_url,
        headers={"User-Agent": "auto-nn-literature/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            pdf_bytes = resp.read()
    except urllib.error.HTTPError as exc:
        return ToolResult.skipped("pdf", f"download_http_{exc.code}")
    except OSError as exc:
        return ToolResult.skipped("pdf", f"download_failed: {exc}")

    if not _pdf_has_eof(pdf_bytes):
        return ToolResult.skipped("pdf", "incomplete_pdf")
    return pdf_bytes


def _pdftotext_excerpt(pdf_path: Path, *, max_chars: int, timeout_sec: float) -> str | None:
    try:
        proc = subprocess.run(
            ["pdftotext", str(pdf_path), "-"],
            capture_output=True,
            text=True,
            timeout=min(timeout_sec, 120.0),
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    text = (proc.stdout or "").strip()
    if not text:
        return None
    limit = max(1, int(max_chars))
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def fetch_arxiv_excerpt(
    arxiv_id: str,
    *,
    max_chars: int = _DEFAULT_MAX_CHARS,
    timeout_sec: float = _PDF_TIMEOUT_SEC,
    persist_dir: Path | None = None,
    repo_root: Path | None = None,
) -> ToolResult:
    """Download arXiv PDF, extract text via pdftotext; optionally persist PDF for archive."""
    if not shutil.which("pdftotext"):
        return ToolResult.skipped("pdf", "binary_missing")

    aid = _normalize_arxiv_id(arxiv_id)
    if not aid:
        return ToolResult.skipped("pdf", "empty_arxiv_id")

    http_calls = 0
    local_path: str | None = None
    work_pdf: Path

    if persist_dir is not None:
        persist_dir.mkdir(parents=True, exist_ok=True)
        work_pdf = persist_dir / f"{aid}.pdf"
        work_txt = persist_dir / f"{aid}.txt"
        if work_pdf.is_file() and _pdf_has_eof(work_pdf.read_bytes()):
            full = _pdftotext_excerpt(work_pdf, max_chars=_MAX_FULL_CHARS, timeout_sec=timeout_sec)
            if full:
                _persist_txt(work_txt, full)
                return _build_ok_result(
                    full, max_chars=max_chars, local_path=_repo_relative(repo_root, work_pdf), http_calls=0
                )
        dl = _download_pdf(aid, timeout_sec=timeout_sec)
        if isinstance(dl, ToolResult):
            return dl
        work_pdf.write_bytes(dl)
        http_calls = 1
        local_path = _repo_relative(repo_root, work_pdf)
    else:
        dl = _download_pdf(aid, timeout_sec=timeout_sec)
        if isinstance(dl, ToolResult):
            return dl
        http_calls = 1
        with tempfile.TemporaryDirectory(prefix="auto-nn-pdf-") as tmp_name:
            work_pdf = Path(tmp_name) / f"{aid}.pdf"
            work_pdf.write_bytes(dl)
            full = _pdftotext_excerpt(work_pdf, max_chars=_MAX_FULL_CHARS, timeout_sec=timeout_sec)
        return _build_ok_result(full, max_chars=max_chars, local_path=None, http_calls=http_calls)

    full = _pdftotext_excerpt(work_pdf, max_chars=_MAX_FULL_CHARS, timeout_sec=timeout_sec)
    if persist_dir is not None and full:
        _persist_txt(persist_dir / f"{aid}.txt", full)
    return _build_ok_result(full, max_chars=max_chars, local_path=local_path, http_calls=http_calls)


def _persist_txt(txt_path: Path, full: str) -> None:
    """落盘 pdftotext 抽出的全文；UTF-8 无 BOM LF；落盘失败不阻断主路径。"""
    try:
        txt_path.write_text(full, encoding="utf-8")
    except OSError:
        pass
