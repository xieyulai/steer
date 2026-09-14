#!/usr/bin/env python3
"""CLI：将 REFLECT_INDEX pending 移至历史（auto-run / 手调）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.experiment_journal import write_reflect_last_consumed  # noqa: E402
from lib.reflect_index import mark_pending_consumed, parse_pending_cells  # noqa: E402


def main() -> int:
    index_path = ROOT / "references" / "REFLECT_INDEX.md"
    if not index_path.is_file():
        return 0
    summary = sys.argv[1] if len(sys.argv) > 1 else "已消费（auto-run）"
    text = index_path.read_text(encoding="utf-8")
    cells = parse_pending_cells(text)
    new_text, rid = mark_pending_consumed(text, summary)
    if rid is None:
        return 0
    index_path.write_text(new_text, encoding="utf-8")
    if cells:
        _rid, _ts, wall, suggest, tier, detail = cells
        write_reflect_last_consumed(
            ROOT,
            reflect_id=rid,
            wall_short=wall,
            suggest_one_liner=suggest,
            tier_hint=tier,
            detail_rel=detail,
            consume_summary=summary,
        )
    print(f"[mark-reflect-consumed] {rid} -> 历史")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
