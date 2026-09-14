"""Serper site: search for framework documentation."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from lib.external.config import resolve_serper_key
from lib.external.models import ToolResult

SERPER_SEARCH_API = "https://google.serper.dev/search"
_SNIPPET_MAX = 480
_TITLE_MAX = 200


def _clamp(text: str, max_len: int) -> str:
    t = " ".join(str(text or "").split())
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


def _organic_to_hit(item: dict[str, Any], *, symbol: str) -> dict[str, Any] | None:
    title = _clamp(str(item.get("title") or ""), _TITLE_MAX)
    url = str(item.get("link") or item.get("url") or "").strip()
    if not title or not url:
        return None
    snippet = _clamp(str(item.get("snippet") or ""), _SNIPPET_MAX)
    return {
        "symbol": symbol,
        "title": title,
        "url": url,
        "snippet": snippet,
        "source": "serper_site",
    }


def search_site(
    query: str,
    *,
    site: str = "pytorch.org/docs",
    max_results: int = 3,
    timeout_sec: float = 25.0,
) -> ToolResult:
    """POST Serper web search with site: filter; no API key → skipped."""
    key = resolve_serper_key()
    if not key:
        return ToolResult.skipped("serper_site", "no_serper_key")

    q = " ".join(str(query or "").split()).strip()
    if not q:
        return ToolResult.skipped("serper_site", "empty_query")

    site_filter = str(site or "").strip()
    search_q = f"{q} site:{site_filter}" if site_filter else q
    num = max(1, min(int(max_results), 10))
    payload = json.dumps({"q": search_q, "num": num}).encode("utf-8")
    req = urllib.request.Request(
        SERPER_SEARCH_API,
        data=payload,
        headers={
            "X-API-KEY": key,
            "Content-Type": "application/json",
            "User-Agent": "auto-nn-literature/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return ToolResult.skipped("serper_site", "no_serper_key")
        return ToolResult(
            status="error",
            provider="serper_site",
            error=f"HTTP {exc.code}",
            http_calls=1,
        )
    except OSError as exc:
        return ToolResult.skipped("serper_site", f"no_network: {exc}")

    organic = data.get("organic") if isinstance(data, dict) else None
    hits: list[dict[str, Any]] = []
    if isinstance(organic, list):
        for item in organic:
            if not isinstance(item, dict):
                continue
            hit = _organic_to_hit(item, symbol=q)
            if hit:
                hits.append(hit)
    return ToolResult.ok("serper_site", hits, http_calls=1)
