"""Paper hits merge, dedupe, and cap (stdlib only)."""
from __future__ import annotations

import re
from typing import Any


def _normalize_title(title: str) -> str:
    t = str(title or "").lower()
    t = re.sub(r"[^\w\s]", "", t)
    return " ".join(t.split())


def _normalize_doi(doi: str) -> str:
    d = str(doi or "").strip().lower()
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", d)


def dedupe_key(hit: dict[str, Any]) -> str:
    """Dedupe key: arxiv_id > normalized doi > normalized title."""
    arxiv_id = str(hit.get("arxiv_id") or "").strip()
    if arxiv_id:
        return f"arxiv:{arxiv_id}"
    doi = _normalize_doi(str(hit.get("doi") or ""))
    if doi:
        return f"doi:{doi}"
    title = _normalize_title(str(hit.get("title") or ""))
    if title:
        return f"title:{title}"
    return ""


def _union_sources(a: list[str] | None, b: list[str] | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for src in list(a or []) + list(b or []):
        if src and src not in seen:
            seen.add(src)
            out.append(src)
    return out


def _prefer_arxiv_fields(out: dict[str, Any], a: dict[str, Any], b: dict[str, Any]) -> None:
    for hit in (a, b):
        if "arxiv" not in (hit.get("sources") or []):
            continue
        if hit.get("arxiv_id"):
            out["arxiv_id"] = hit["arxiv_id"]
        if hit.get("url"):
            out["url"] = hit["url"]
        return
    if not out.get("arxiv_id"):
        out["arxiv_id"] = a.get("arxiv_id") or b.get("arxiv_id")
    if not out.get("url"):
        out["url"] = a.get("url") or b.get("url")


def _merge_fields(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    out = dict(a)
    out["sources"] = _union_sources(a.get("sources"), b.get("sources"))

    abs_a = str(a.get("abstract") or "")
    abs_b = str(b.get("abstract") or "")
    out["abstract"] = abs_a if len(abs_a) >= len(abs_b) else abs_b

    title_a = str(a.get("title") or "")
    title_b = str(b.get("title") or "")
    out["title"] = title_a if len(title_a) >= len(title_b) else title_b

    _prefer_arxiv_fields(out, a, b)

    if not out.get("doi"):
        out["doi"] = a.get("doi") or b.get("doi")
    for field in ("published", "authors", "categories"):
        if not out.get(field):
            out[field] = a.get(field) or b.get(field)
    return out


def truncate_hits(hits: list[dict[str, Any]], cap: int) -> list[dict[str, Any]]:
    """Sort: has arxiv_id first, longer abstract first; then truncate to cap."""
    if cap <= 0:
        return []

    def _sort_key(hit: dict[str, Any]) -> tuple[int, int]:
        has_arxiv = 0 if hit.get("arxiv_id") else 1
        abstract_len = -len(str(hit.get("abstract") or ""))
        return (has_arxiv, abstract_len)

    return sorted(hits, key=_sort_key)[:cap]


def merge_paper_hits(
    hit_lists: list[list[dict[str, Any]]], *, cap: int
) -> list[dict[str, Any]]:
    """Merge provider hit lists, dedupe, merge fields, then truncate."""
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for hit_list in hit_lists:
        for hit in hit_list:
            key = dedupe_key(hit)
            if not key:
                continue
            if key not in merged:
                entry = dict(hit)
                entry["sources"] = list(entry.get("sources") or [])
                merged[key] = entry
                order.append(key)
            else:
                merged[key] = _merge_fields(merged[key], hit)

    return truncate_hits([merged[k] for k in order], cap)
