"""REFLECT_INDEX 摘要（REFLECT-BRIEF + essence pending one-liner）。"""
from __future__ import annotations

import re
from pathlib import Path

from lib.reflect_index import parse_pending_cells

_PENDING_PLACEHOLDERS = frozenset({"（无）", "—", "-", "", "id", "（尚无）"})


def _history_data_rows(text: str) -> list[list[str]]:
    m = re.search(r"##\s*历史[^\n]*\n(.*)", text, re.DOTALL | re.I)
    if not m:
        return []
    rows: list[list[str]] = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells and cells[0] not in _PENDING_PLACEHOLDERS:
            rows.append(cells)
    return rows


def _truncate(text: str, max_chars: int) -> str:
    t = text.strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"


def reflect_pending_one_liner(repo_root: Path, max_chars: int = 80) -> str | None:
    p = repo_root / "references" / "REFLECT_INDEX.md"
    if not p.is_file():
        return None
    cells = parse_pending_cells(p.read_text(encoding="utf-8"))
    if not cells:
        return None
    rid, _ts, _wall, suggest, tier, _detail = cells
    s = _truncate(suggest, max_chars)
    return f"`{rid}` — {s} (tier={tier})"


def format_reflect_brief(repo_root: Path) -> str:
    """输出 REFLECT-BRIEF：pending（120 字截断）+ 最近 3 条历史（倒序）。"""
    root = repo_root.resolve()
    index_path = root / "references" / "REFLECT_INDEX.md"
    lines = ["### REFLECT-BRIEF", ""]

    pending_line = "（无）"
    hist_rows: list[list[str]] = []
    if index_path.is_file():
        text = index_path.read_text(encoding="utf-8")
        cells = parse_pending_cells(text)
        if cells:
            rid, _ts, wall, suggest, tier, detail = cells
            s = _truncate(suggest, 120)
            pending_line = f"`{rid}` wall={wall} — {s} (tier={tier}, detail={detail})"
        hist_rows = _history_data_rows(text)

    lines.append(f"**pending**: {pending_line}")
    lines.append("")
    lines.append("**recent consumed**:")
    if not hist_rows:
        lines.append("- （尚无）")
    else:
        for cells in list(reversed(hist_rows))[:3]:
            rid = cells[0] if cells else "?"
            ts = cells[1] if len(cells) > 1 else "—"
            wall = cells[2] if len(cells) > 2 else "—"
            suggest = cells[3] if len(cells) > 3 else "—"
            summary = cells[4] if len(cells) > 4 else "—"
            lines.append(f"- `{rid}` ({ts}) wall={wall} — {_truncate(suggest, 80)} → {summary}")
    return "\n".join(lines) + "\n"


def reflect_pending_id(repo_root: Path) -> str | None:
    """供 format_brief 末行 reflect_pending=id|none。"""
    p = repo_root / "references" / "REFLECT_INDEX.md"
    if not p.is_file():
        return None
    cells = parse_pending_cells(p.read_text(encoding="utf-8"))
    if not cells:
        return None
    return str(cells[0]).strip() or None
