"""Ticket 01 (#02): 从 PDF 全文文本抽取方法段 + 实现要点（纯函数，无 I/O）。

确定性策略：按编号章节标题切块 → 命中 method/approach/model/architecture 等
→ 取该章节正文为 method_excerpt；正文内匹配实现信号行（optimizer / lr /
batch size / Algorithm N / layer / dimension …）为 impl_hints。

LLM 增强留待后续；本模块只做可单测的确定性抽取（tracer-bullet 最薄内核）。
"""
from __future__ import annotations

import re

# 编号章节标题：行首 数字(.数字)* + 空格 + 大写开头的标题
_HEADING_RE = re.compile(
    r"^[ \t]*(\d+(?:\.\d+)*)\s+([A-Z][A-Za-z0-9 \-:]+?)\s*$",
    re.MULTILINE,
)
# 方法段标题关键词（小写子串匹配）
_METHOD_KEYWORDS = (
    "method", "methods", "approach", "model", "architecture",
    "methodology", "framework", "our approach", "proposed",
)
# 实现信号行模式（方法段正文内逐行匹配）
_IMPL_PATTERNS = (
    re.compile(r"learning rate", re.I),
    re.compile(r"batch size", re.I),
    re.compile(r"\bAdam\b"),
    re.compile(r"\bSGD\b"),
    re.compile(r"\bepochs?\b", re.I),
    re.compile(r"hidden (dimension|size|unit)", re.I),
    re.compile(r"dropout", re.I),
    re.compile(r"Algorithm \d+"),
    re.compile(r"layer", re.I),
    re.compile(r"embed", re.I),
    re.compile(r"optimizer", re.I),
    re.compile(r"\bdimension", re.I),
)


def _find_method_section(text: str):
    """Return (title, body) for first method-like numbered section, else (None, None)."""
    matches = list(_HEADING_RE.finditer(text))
    for i, m in enumerate(matches):
        title = m.group(2).strip()
        if any(k in title.lower() for k in _METHOD_KEYWORDS):
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            return title, text[start:end].strip()
    return None, None


def _collect_impl_hints(body: str) -> list:
    hints = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and any(p.search(stripped) for p in _IMPL_PATTERNS):
            hints.append(stripped)
    return hints


def extract_method_excerpt(full_text, *, max_chars=2000):
    """Extract method section + implementation hints from paper full text.

    Pure / no I/O. Returns dict(section_title, method_excerpt, impl_hints).
    No method-like heading found → all-None / empty (graceful, no crash).
    """
    if not full_text:
        return {"section_title": None, "method_excerpt": None, "impl_hints": []}
    title, body = _find_method_section(full_text)
    if not body:
        return {"section_title": None, "method_excerpt": None, "impl_hints": []}
    return {
        "section_title": title,
        "method_excerpt": body[:max_chars],
        "impl_hints": _collect_impl_hints(body),
    }
