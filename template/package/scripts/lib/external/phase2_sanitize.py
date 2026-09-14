from __future__ import annotations

import re
from typing import Callable

from lib.external.validate_urls import _arxiv_id_from_url

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _token_set(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(str(text or "").lower()))


def title_jaccard(a: str, b: str) -> float:
    sa, sb = _token_set(a), _token_set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def sanitize_phase2_finding(
    finding: dict,
    *,
    title_fetcher: Callable[[str], str],
    min_jaccard: float = 0.15,
) -> dict:
    out = dict(finding)
    if str(out.get("source") or "") != "trained_knowledge":
        return out
    url = str(out.get("url") or "").strip()
    aid = _arxiv_id_from_url(url)
    if not aid:
        return out
    try:
        real_title = title_fetcher(aid)
    except Exception:
        return out
    if not real_title:
        return out
    score = title_jaccard(str(out.get("summary") or ""), real_title)
    if score >= min_jaccard:
        return out
    out["url"] = ""
    summary = str(out.get("summary") or "")
    if not summary.startswith("[UNVERIFIED"):
        out["summary"] = f"[UNVERIFIED arXiv title mismatch] {summary}"
    return out


def sanitize_phase2_findings(
    phase2: dict,
    *,
    title_fetcher: Callable[[str], str],
    max_checks: int = 6,
) -> tuple[dict, int]:
    findings = list(phase2.get("findings") or [])
    mismatches = 0
    checks = 0
    for i, f in enumerate(findings):
        if checks >= max_checks:
            break
        if str(f.get("source") or "") != "trained_knowledge":
            continue
        if not _arxiv_id_from_url(str(f.get("url") or "")):
            continue
        checks += 1
        new_f = sanitize_phase2_finding(f, title_fetcher=title_fetcher)
        if new_f.get("url") == "" and f.get("url"):
            mismatches += 1
        findings[i] = new_f
    return {**phase2, "findings": findings}, mismatches
