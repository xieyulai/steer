"""Serper Google Scholar provider."""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from lib.external.config import resolve_serper_key
from lib.external.models import ToolResult
from lib.external.retry import with_retry

SERPER_SCHOLAR_API = "https://google.serper.dev/scholar"
_SNIPPET_MAX = 480
_TITLE_MAX = 200


def _clamp(text: str, max_len: int) -> str:
    t = " ".join(str(text or "").split())
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


def _arxiv_id_from_url(url: str) -> str:
    m = re.search(r"arxiv\.org/abs/([^/?#]+)", url or "", re.I)
    if m:
        return re.sub(r"v\d+$", "", m.group(1))
    m = re.search(r"arxiv\.(\d+\.\d+)(?:v\d+)?", url or "", re.I)
    if m:
        return m.group(1)
    return ""


def _organic_to_hit(item: dict[str, Any]) -> dict[str, Any] | None:
    title = _clamp(str(item.get("title") or ""), _TITLE_MAX)
    url = str(item.get("link") or item.get("url") or "").strip()
    if not title or not url:
        return None
    snippet = _clamp(str(item.get("snippet") or ""), _SNIPPET_MAX)
    hit: dict[str, Any] = {
        "title": title,
        "url": url,
        "abstract": snippet,
        "sources": ["scholar"],
    }
    aid = _arxiv_id_from_url(url)
    if aid:
        hit["arxiv_id"] = aid
    pub = str(item.get("publicationInfo") or item.get("publication_info") or "").strip()
    if pub:
        hit["publication_info"] = pub
    cited = item.get("citedBy") if item.get("citedBy") is not None else item.get("cited_by")
    if cited is not None:
        try:
            hit["cited_by"] = int(cited)
        except (TypeError, ValueError):
            pass
    return hit


def search_scholar(
    query: str,
    *,
    max_results: int = 5,
    timeout_sec: float = 30.0,
    max_retries: int = 2,
) -> ToolResult:
    """POST Serper Scholar; no API key → skipped。

    Args:
        max_retries: 失败后重试次数（默认 2；429/5xx/网络/timeout 重试；401/403 立即 skipped）
    """
    key = resolve_serper_key()
    if not key:
        return ToolResult.skipped("scholar", "no_serper_key")

    q = " ".join(str(query or "").split()).strip()
    if not q:
        return ToolResult.skipped("scholar", "empty_query")

    num = max(1, min(int(max_results), 20))
    payload = json.dumps({"q": q, "num": num}).encode("utf-8")
    req = urllib.request.Request(
        SERPER_SCHOLAR_API,
        data=payload,
        headers={
            "X-API-KEY": key,
            "Content-Type": "application/json",
            "User-Agent": "auto-nn-literature/1.0",
        },
        method="POST",
    )

    def _do() -> dict[str, Any]:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))

    try:
        data = with_retry(_do, max_retries=max_retries)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return ToolResult.skipped("scholar", "no_serper_key")
        return ToolResult(
            status="error",
            provider="scholar",
            error=f"HTTP {exc.code} after {max_retries + 1} attempts",
            http_calls=max_retries + 1,
        )
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return ToolResult.skipped("scholar", f"no_network_after_{max_retries + 1}: {exc}")

    organic = data.get("organic") if isinstance(data, dict) else None
    hits: list[dict[str, Any]] = []
    if isinstance(organic, list):
        for item in organic:
            if not isinstance(item, dict):
                continue
            hit = _organic_to_hit(item)
            if hit:
                hits.append(hit)
    return ToolResult.ok("scholar", hits, http_calls=max_retries + 1)
