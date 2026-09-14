from __future__ import annotations

import re
from pathlib import Path

from lib.experience_sections import latest_experiment_round_block, recent_log_body

_ACK_IN_LINE_RE = re.compile(
    r"reflect_ack\s*:\s*(.*)$",
    re.MULTILINE | re.IGNORECASE,
)
_QUALITY_KEYWORDS = (
    "adopt",
    "采纳",
    "defer",
    "推迟",
    "conflict",
    "冲突",
    "roadmap",
    "路线图",
)


def _clean_ack(raw: str) -> str:
    s = (raw or "").strip()
    s = re.sub(r"^\*+\s*", "", s)
    s = re.sub(r"\s*\*+\s*$", "", s)
    return s.strip()


def extract_reflect_ack(text: str) -> str | None:
    """从 EXPERIENCE 提取最新 reflect_ack（兼容 C2 压缩后 blockquote 尾段）。"""
    bodies = (recent_log_body(text), text)
    for body in bodies:
        block = latest_experiment_round_block(body)
        if block:
            m = _ACK_IN_LINE_RE.search(block)
            if m:
                ack = _clean_ack(m.group(1) or "")
                if ack:
                    return ack
    tail = recent_log_body(text)
    matches = list(_ACK_IN_LINE_RE.finditer(tail))
    if matches:
        ack = _clean_ack(matches[-1].group(1) or "")
        if ack:
            return ack
    return None


def extract_reflect_ack_from_path(path: Path) -> str | None:
    if not path.is_file():
        return None
    return extract_reflect_ack(path.read_text(encoding="utf-8", errors="replace"))


def reflect_ack_quality_ok(ack: str) -> bool:
    s = (ack or "").strip()
    if len(s) < 8:
        return False
    low = s.lower()
    return any(k in low or k in s for k in _QUALITY_KEYWORDS)
