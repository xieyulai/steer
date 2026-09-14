"""HUMAN_GUIDANCE.md 解析：路线图节 + 文首公平约束节（忽略 <!-- -->）。"""
from __future__ import annotations

import re
from dataclasses import dataclass

_ROADMAP_SECTION_RE = re.compile(
    r"##\s*路线图\s*\n(.*?)(?=\n##\s|\Z)", re.DOTALL | re.I
)
_FAIR_SECTION_RE = re.compile(
    r"##\s*公平约束\s*\n(.*?)(?=\n##\s|\Z)", re.DOTALL | re.I
)
_PHASE_HEADER_RE = re.compile(
    r"^###\s*阶段\s*(\d+)\s*—\s*(.+)$", re.MULTILINE | re.I
)


@dataclass
class RoadmapPhase:
    num: int
    title: str


def strip_html_comments(text: str) -> str:
    """移除 HTML/XML 风格块注释 <!-- ... -->（含换行），用于路线图解析前置清洗。"""
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def fair_constraints_section_body(text: str) -> str:
    """抽取文首「公平约束」章节正文（去注释后）；无实质内容则空串。"""
    cleaned = strip_html_comments(text)
    m = _FAIR_SECTION_RE.search(cleaned)
    if not m:
        return ""
    body = m.group(1).strip()
    return body if body else ""


def roadmap_section_body(text: str) -> str:
    """抽取「路线图」章节正文（全篇去 HTML 注释后匹配 ``## 路线图``）；无则空串。"""
    cleaned = strip_html_comments(text)
    m = _ROADMAP_SECTION_RE.search(cleaned)
    return m.group(1) if m else ""


def list_roadmap_phases(text: str) -> list[RoadmapPhase]:
    """在路线图正文内枚举 ``### 阶段 N — title``（忽略注释内占位）。"""
    body = roadmap_section_body(text)
    phases: list[RoadmapPhase] = []
    for m in _PHASE_HEADER_RE.finditer(body):
        phases.append(RoadmapPhase(int(m.group(1)), m.group(2).strip()))
    return phases


def count_roadmap_phases(text: str) -> int:
    """路线图内阶段标题数量（与 ``list_roadmap_phases`` 一致）。"""
    return len(list_roadmap_phases(text))
