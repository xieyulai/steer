"""arXiv 文献检索（reflect Phase 2 前置；thin wrapper → lib.external.arxiv）。"""
from __future__ import annotations

from lib.external.arxiv import (  # noqa: F401
    _parse_arxiv_atom,
    build_arxiv_search_query,
    bundle_dict,
    format_hits_markdown,
    format_hits_table,
    search_arxiv,
)
