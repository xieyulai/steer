from __future__ import annotations

import re
from datetime import datetime

EXPERIENCE_LOG_START = "<!-- experience-log-start -->"

_H2_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)
_DATETIME_IN_TITLE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})")

# 非 Agent 实验轮标题（前缀匹配 title）
_EXCLUDE_PREFIXES: tuple[str, ...] = (
    "[反思]",
    "[反思消费]",
    "证据缺口",
    "Tier 举证摘要",
    "精华摘要",
    "近期实验",
    "Tier 状态",
    "场景",
)


def parse_round_heading_datetime(title: str) -> datetime | None:
    t = (title or "").strip()
    if not t:
        return None
    if any(t.startswith(p) for p in _EXCLUDE_PREFIXES):
        return None
    m = _DATETIME_IN_TITLE_RE.search(t)
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def is_experiment_round_heading(title: str) -> bool:
    return parse_round_heading_datetime(title) is not None


def latest_experiment_round_block(body: str) -> str | None:
    matches = list(_H2_RE.finditer(body))
    if not matches:
        return None
    best_idx: int | None = None
    best_dt: datetime | None = None
    for i, m in enumerate(matches):
        dt = parse_round_heading_datetime(m.group(1))
        if dt is None:
            continue
        if best_dt is None or dt > best_dt or (dt == best_dt and i > (best_idx or -1)):
            best_dt = dt
            best_idx = i
    if best_idx is None:
        return None
    start = matches[best_idx].start()
    end = matches[best_idx + 1].start() if best_idx + 1 < len(matches) else len(body)
    return body[start:end]


def recent_log_body(text: str) -> str:
    idx = text.find(EXPERIENCE_LOG_START)
    return text[idx + len(EXPERIENCE_LOG_START) :] if idx >= 0 else text
