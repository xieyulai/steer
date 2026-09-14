"""GitHub search for awesome-list style library/ecosystem repos."""
from __future__ import annotations

import re
from typing import Any

from lib.external.github_impl import search_repos
from lib.external.models import ToolResult


def _awesome_query(user_query: str) -> str:
    q = " ".join(str(user_query or "").split()).strip()
    if not q:
        return ""
    tokens = [t for t in re.split(r"\s+", q.lower()) if t and t not in ("awesome", "list")]
    topic = " ".join(tokens[:4]) if tokens else q
    return f"awesome {topic} in:name,description"


def search_library_repos(query: str, *, max_results: int = 3) -> ToolResult:
    """Search GitHub for awesome-* style ecosystem/list repositories."""
    q = _awesome_query(query)
    if not q:
        return ToolResult.skipped("github_ecosystem", "empty_query")

    tr = search_repos(q, max_results=max_results)
    if tr.status != "ok":
        return ToolResult(
            status=tr.status,
            provider="github_ecosystem",
            hits=tr.hits,
            skip_reason=tr.skip_reason,
            error=tr.error,
            http_calls=tr.http_calls,
        )

    hits: list[dict[str, Any]] = []
    for hit in tr.hits:
        entry = dict(hit)
        entry["kind"] = "awesome_list"
        hits.append(entry)
    return ToolResult.ok("github_ecosystem", hits, http_calls=tr.http_calls)
