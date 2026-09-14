"""OpenAlex API provider（stdlib only）。"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from typing import Any

from lib.external.retry import with_retry  # noqa: E402

OPENALEX_API = "https://api.openalex.org/works"
_USER_AGENT = "auto-nn-literature/1.0 (mailto:{mailto})"


def _mailto() -> str:
    return (os.environ.get("OPENALEX_MAILTO") or "template@example.com").strip()


def _user_agent() -> str:
    return _USER_AGENT.format(mailto=_mailto())


def _abstract_from_inverted_index(idx: dict[str, Any] | None) -> str:
    if not idx:
        return ""
    pairs: list[tuple[int, str]] = []
    for word, positions in idx.items():
        for pos in positions or []:
            pairs.append((int(pos), str(word)))
    return " ".join(word for _, word in sorted(pairs))


def _normalize_arxiv_id(arxiv_id: str) -> str:
    return re.sub(r"v\d+$", "", str(arxiv_id or "").strip())


def _doi_str(raw: str | None) -> str:
    if not raw:
        return ""
    return raw.replace("https://doi.org/", "").strip()


def _arxiv_id_from_doi(doi: str, *, fallback: str = "") -> str:
    m = re.search(r"arxiv\.(\d+\.\d+)(?:v\d+)?", doi, re.I)
    if m:
        return m.group(1)
    return fallback


def _work_to_hit(work: dict[str, Any], *, arxiv_id: str = "") -> dict[str, Any]:
    doi = _doi_str(work.get("doi"))
    aid = _arxiv_id_from_doi(doi, fallback=_normalize_arxiv_id(arxiv_id))
    title = str(work.get("display_name") or "").strip()
    abstract = _abstract_from_inverted_index(work.get("abstract_inverted_index"))
    url = str(work.get("id") or work.get("landing_page_url") or "").strip()
    if not url and aid:
        url = f"https://arxiv.org/abs/{aid}"
    if not doi and aid:
        doi = f"10.48550/arxiv.{aid}"
    return {
        "arxiv_id": aid,
        "title": title,
        "url": url,
        "abstract": abstract,
        "doi": doi,
        "sources": ["openalex"],
    }


def _fetch_json(url: str, *, timeout_sec: float = 30.0) -> dict[str, Any] | None:
    from lib.external.retry import is_retryable

    try:
        req = urllib.request.Request(url, headers={"User-Agent": _user_agent()})
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        if isinstance(data, dict):
            return data
    except Exception as exc:
        if is_retryable(exc):
            raise  # 429/5xx/网络/timeout → 让 with_retry 重试
        # 不可重试（4xx 非 429 / ValueError / 其他）→ 返回 None（保留原行为）
        return None
    return None


def _works_from_payload(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not payload:
        return []
    results = payload.get("results")
    if isinstance(results, list):
        return [w for w in results if isinstance(w, dict)]
    if payload.get("id") or payload.get("display_name"):
        return [payload]
    return []


def lookup_by_arxiv_doi(arxiv_id: str, *, timeout_sec: float = 30.0) -> dict[str, Any] | None:
    """通过 arXiv DOI（10.48550/arxiv.{id}）直查 OpenAlex；失败返回 None。"""
    aid = _normalize_arxiv_id(arxiv_id)
    if not aid:
        return None
    doi_filter = f"10.48550/arxiv.{aid}"
    params = {
        "filter": f"doi:{doi_filter}",
        "per-page": "1",
        "mailto": _mailto(),
    }
    url = f"{OPENALEX_API}?{urllib.parse.urlencode(params)}"
    payload = _fetch_json(url, timeout_sec=timeout_sec)
    works = _works_from_payload(payload)
    if not works:
        return None
    return _work_to_hit(works[0], arxiv_id=aid)


def search_openalex(
    query: str,
    *,
    max_results: int = 5,
    timeout_sec: float = 30.0,
    max_retries: int = 2,
) -> list[dict[str, Any]]:
    """OpenAlex 关键词检索；失败或无结果返回 []。

    Args:
        max_retries: 失败后重试次数（默认 2；429/5xx/网络/timeout 重试）
    """
    q = " ".join(str(query or "").split()).strip()
    if not q:
        return []
    per_page = max(1, min(int(max_results), 25))
    params = {
        "search": q,
        "per-page": str(per_page),
        "mailto": _mailto(),
    }
    url = f"{OPENALEX_API}?{urllib.parse.urlencode(params)}"

    def _do() -> list[dict[str, Any]]:
        payload = _fetch_json(url, timeout_sec=timeout_sec)
        hits: list[dict[str, Any]] = []
        for work in _works_from_payload(payload):
            hit = _work_to_hit(work)
            if hit.get("title") or hit.get("arxiv_id"):
                hits.append(hit)
        return hits[:per_page]

    try:
        return with_retry(_do, max_retries=max_retries)
    except Exception:
        return []  # 失败兜底：与原行为一致
