"""arXiv API provider（stdlib only）。"""
from __future__ import annotations

import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

from lib.external.retry import with_retry  # noqa: E402

ARXIV_API = "https://export.arxiv.org/api/query"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
_SUMMARY_MAX = 480
_TITLE_MAX = 200


def _clamp(text: str, max_len: int) -> str:
    t = " ".join(str(text or "").split())
    if len(t) <= max_len:
        return t
    return t[: max_len - 1].rstrip() + "…"


def fetch_arxiv_title_by_id(arxiv_id: str, *, timeout_sec: float = 15.0) -> str:
    """按 arXiv ID 拉单条 entry title，仅返回第一个 hit 的 title（strip vN 后缀）。

    失败（HTTP/parse）抛 urllib.error.URLError；调用方负责 try/except。
    """
    aid = re.sub(r"v\d+$", "", str(arxiv_id or "").strip())
    if not aid:
        return ""
    params = {"id_list": aid}
    url = f"{ARXIV_API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "auto-nn-literature/1.0 (maintainer; mailto:template)"},
    )
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        xml_text = resp.read().decode("utf-8", errors="replace")
    hits = _parse_arxiv_atom(xml_text)
    if not hits:
        return ""
    return str(hits[0].get("title") or "")


def _arxiv_id_from_entry_id(entry_id: str) -> str:
    """http://arxiv.org/abs/2203.07404v2 → 2203.07404"""
    m = re.search(r"arxiv\.org/abs/([^/]+)", entry_id or "")
    if not m:
        return entry_id
    return re.sub(r"v\d+$", "", m.group(1))


def _parse_arxiv_atom(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    hits: list[dict[str, Any]] = []
    for entry in root.findall("atom:entry", ATOM_NS):
        raw_id = (entry.findtext("atom:id", default="", namespaces=ATOM_NS) or "").strip()
        aid = _arxiv_id_from_entry_id(raw_id)
        title = _clamp(entry.findtext("atom:title", default="", namespaces=ATOM_NS), _TITLE_MAX)
        abstract = _clamp(
            entry.findtext("atom:summary", default="", namespaces=ATOM_NS), _SUMMARY_MAX
        )
        published = (entry.findtext("atom:published", default="", namespaces=ATOM_NS) or "")[:10]
        authors = [
            (a.findtext("atom:name", default="", namespaces=ATOM_NS) or "").strip()
            for a in entry.findall("atom:author", ATOM_NS)
        ]
        authors = [a for a in authors if a][:6]
        categories = [
            c.get("term", "").strip()
            for c in entry.findall("atom:category", ATOM_NS)
            if c.get("term")
        ]
        if not aid or not title:
            continue
        hits.append(
            {
                "arxiv_id": aid,
                "title": title,
                "url": f"https://arxiv.org/abs/{aid}",
                "abstract": abstract,
                "published": published,
                "authors": authors,
                "categories": categories[:5],
                "sources": ["arxiv"],
            }
        )
    return hits


def build_arxiv_search_query(user_query: str) -> str:
    """用户 query → arXiv API search_query（all: 字段，词间 + 即 AND）。"""
    q = " ".join(str(user_query or "").split()).strip()
    if not q:
        raise ValueError("empty query")
    if q.startswith('"') and q.endswith('"'):
        inner = q[1:-1].strip()
        if not inner:
            raise ValueError("empty quoted query")
        return "all:" + inner.replace(" ", "+")
    terms = [t for t in re.split(r"\s+", q) if t]
    return "all:" + "+".join(terms)


def search_arxiv(
    query: str,
    *,
    max_results: int = 5,
    timeout_sec: float = 30.0,
    sort_by: str = "relevance",
    max_retries: int = 2,
) -> list[dict[str, Any]]:
    """调用 export.arxiv.org API；失败抛 urllib.error 或 ValueError。

    Args:
        max_retries: 失败后重试次数（默认 2；429/5xx/网络/timeout 重试；其他异常不重试）
    """
    if max_results < 1:
        raise ValueError("max_results must be >= 1")
    if max_results > 50:
        max_results = 50
    search_query = build_arxiv_search_query(query)
    params = {
        "search_query": search_query,
        "start": "0",
        "max_results": str(max_results),
        "sortBy": sort_by if sort_by in ("relevance", "lastUpdatedDate", "submittedDate") else "relevance",
        "sortOrder": "descending",
    }
    url = f"{ARXIV_API}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "auto-nn-literature/1.0 (maintainer; mailto:template)"},
    )

    def _do() -> list[dict[str, Any]]:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            xml_text = resp.read().decode("utf-8", errors="replace")
        return _parse_arxiv_atom(xml_text)

    return with_retry(_do, max_retries=max_retries)


def format_hits_markdown(hits: list[dict[str, Any]], *, query: str = "") -> str:
    lines = ["## arXiv 检索结果", ""]
    if query:
        lines.append(f"- **query**: `{query}`")
        lines.append(f"- **hits**: {len(hits)}")
        lines.append("")
    if not hits:
        lines.append("（无结果）")
        return "\n".join(lines)
    for i, h in enumerate(hits, start=1):
        authors = h.get("authors") or []
        auth = ", ".join(authors[:3])
        if len(authors) > 3:
            auth += " et al."
        lines.extend([
            f"### {i}. {h['title']}",
            f"- **id**: `{h['arxiv_id']}` | **date**: {h.get('published', '')}",
            f"- **url**: {h['url']}",
            f"- **authors**: {auth or '（无）'}",
            f"- **abstract**: {h.get('abstract', '')}",
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def format_hits_table(hits: list[dict[str, Any]]) -> str:
    if not hits:
        return "(no hits)"
    lines = ["arxiv_id\tpublished\ttitle\turl"]
    for h in hits:
        lines.append(
            f"{h['arxiv_id']}\t{h.get('published', '')}\t{h['title']}\t{h['url']}"
        )
    return "\n".join(lines)


def bundle_dict(query: str, hits: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "provider": "arxiv",
        "ts": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "query": query,
        "count": len(hits),
        "hits": hits,
    }
