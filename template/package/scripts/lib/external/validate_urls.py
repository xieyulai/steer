"""Phase 2 references_to_add URL validation against evidence bundle."""
from __future__ import annotations

import re
import sys
from typing import Any
from urllib.parse import urlparse, urlunparse

_ARXIV_ABS = re.compile(r"arxiv\.org/abs/([^/?#]+)", re.I)
_ARXIV_PDF = re.compile(r"arxiv\.org/pdf/([^/?#]+)", re.I)


def _arxiv_id_from_url(url: str) -> str:
    raw = str(url or "").strip()
    m = _ARXIV_ABS.search(raw) or _ARXIV_PDF.search(raw)
    if not m:
        return ""
    aid = re.sub(r"v\d+$", "", m.group(1))
    return re.sub(r"\.pdf$", "", aid, flags=re.I)


def normalize_url(url: str) -> str:
    """Normalize URL: http→https, strip trailing slash; arxiv abs/pdf → canonical abs."""
    raw = str(url or "").strip()
    if not raw:
        return ""
    aid = _arxiv_id_from_url(raw)
    if aid:
        return f"https://arxiv.org/abs/{aid}"
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    scheme = "https" if parsed.scheme in ("http", "https", "") else parsed.scheme
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or ""
    return urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))


def _collect_item_urls(item: dict[str, Any], urls: set[str]) -> None:
    u = normalize_url(str(item.get("url") or ""))
    if u:
        urls.add(u)
    aid = str(item.get("arxiv_id") or "").strip()
    if aid:
        urls.add(normalize_url(f"https://arxiv.org/abs/{aid}"))


def allowed_url_set(bundle: dict) -> set[str]:
    """Normalize urls from paper hits/impl/linked_code and routine_attestation.docs."""
    urls: set[str] = set()
    paper = bundle.get("paper") or {}
    for key in ("hits", "impl_candidates", "linked_code"):
        for item in paper.get(key) or []:
            if isinstance(item, dict):
                _collect_item_urls(item, urls)
    code = bundle.get("code") or {}
    attestation = code.get("routine_attestation") or {}
    for doc in attestation.get("docs") or []:
        if isinstance(doc, dict):
            _collect_item_urls(doc, urls)
    return urls


def bundle_empty_for_refs(bundle: dict) -> bool:
    """True when bundle has no paper hits and no routine docs."""
    paper = bundle.get("paper") or {}
    hits = paper.get("hits") or []
    code = bundle.get("code") or {}
    docs = (code.get("routine_attestation") or {}).get("docs") or []
    return not hits and not docs


def filter_references_to_add(refs: list[dict], bundle: dict) -> list[dict]:
    """Drop refs whose url is not in bundle; WARN on stderr for each drop."""
    allowed = allowed_url_set(bundle)
    kept: list[dict] = []
    for ref in refs or []:
        url = str(ref.get("url") or "").strip()
        if not url or normalize_url(url) not in allowed:
            print(
                f"external_url_not_in_bundle: url={url!r} title={ref.get('title', '?')}",
                file=sys.stderr,
            )
            continue
        kept.append(ref)
    return kept


def format_external_plan_summary(bundle: dict, plan_dict: dict | None = None) -> str:
    """One-line meta for references/auto header."""
    plan_dict = plan_dict or {}
    paper = bundle.get("paper") or {}
    paper_depth = paper.get("depth") or plan_dict.get("paper_depth") or "P0"
    hits_count = len(paper.get("hits") or [])
    skipped = (bundle.get("meta") or {}).get("skipped") or []
    skipped_s = ",".join(
        f"{s.get('provider', '?')}:{s.get('reason', '')}" for s in skipped[:5]
    )
    rs = bundle.get("round_state") or plan_dict.get("round_state") or {}
    tier = rs.get("tier") or "?"
    depth = rs.get("innovation_depth") or "?"
    gate = rs.get("gate") or "?"
    parts = [f"外部证据：{paper_depth}，命中={hits_count}"]
    if skipped_s:
        parts.append(f"已跳过={skipped_s}")
    parts.append(f"计划={depth}/{tier}/{gate}")
    return ", ".join(parts)


def render_verified_external_lines(
    bundle: dict,
    refs_to_add: list[dict] | None = None,
) -> list[str]:
    """Render body lines for ## 外部证据（已验证） from bundle fields."""
    lines: list[str] = []
    reflect_id = str(bundle.get("reflect_id") or "").strip()
    if reflect_id:
        lines.extend([f"**reflect_id**: `{reflect_id}`", ""])

    llm_by_url: dict[str, dict] = {}
    for ref in refs_to_add or []:
        norm = normalize_url(str(ref.get("url") or ""))
        if norm:
            llm_by_url[norm] = ref

    paper = bundle.get("paper") or {}
    hits = paper.get("hits") or []
    if hits:
        lines.extend(["### 论文检索", ""])
        for hit in hits:
            title = hit.get("title") or "(no title)"
            url = str(hit.get("url") or "").strip()
            lines.append(f"- **{title}** — {url}")
            abstract = str(hit.get("abstract") or "").strip()
            if abstract:
                lines.append(f"  - abstract: {abstract[:300]}")
            llm = llm_by_url.get(normalize_url(url))
            if llm and llm.get("summary"):
                lines.append(f"  - summary: {llm.get('summary')}")
        lines.append("")

    impl = list(paper.get("impl_candidates") or [])
    linked = list(paper.get("linked_code") or [])
    if impl or linked:
        lines.extend(["### 实现候选", ""])
        for item in impl + linked:
            title = item.get("full_name") or item.get("title") or item.get("url") or "?"
            url = str(item.get("url") or "").strip()
            lines.append(f"- **{title}** — {url}")
        lines.append("")

    code = bundle.get("code") or {}
    docs = (code.get("routine_attestation") or {}).get("docs") or []
    if docs:
        lines.extend(["### 文档 attestation", ""])
        for doc in docs:
            symbol = doc.get("symbol") or doc.get("module") or "?"
            url = str(doc.get("url") or "").strip()
            lines.append(f"- **{symbol}** — {url}")
            excerpt = str(doc.get("doc_excerpt") or "").strip()
            if excerpt:
                lines.append(f"  - {excerpt[:200]}")
        lines.append("")

    if not hits and not impl and not linked and not docs:
        lines.extend(["（本轮无已验证外部条目）", ""])

    return lines
