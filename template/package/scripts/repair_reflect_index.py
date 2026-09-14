#!/usr/bin/env python3
"""修复 REFLECT_INDEX 历史表结构。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.reflect_index import audit_reflect_index, repair_reflect_index_text  # noqa: E402


def main() -> int:
    index_path = ROOT / "references" / "REFLECT_INDEX.md"
    apply = os.environ.get("NN_REPAIR_APPLY", "0") in ("1", "true", "yes")
    if not index_path.is_file():
        print("[repair-reflect-index] 无 REFLECT_INDEX.md，跳过")
        return 0
    text = index_path.read_text(encoding="utf-8")
    new_text, changed = repair_reflect_index_text(text)
    if not changed:
        print("[repair-reflect-index] 无需修复")
        return 0
    if apply:
        index_path.write_text(new_text, encoding="utf-8")
        print("[repair-reflect-index] 已写回 references/REFLECT_INDEX.md")
    else:
        print("[repair-reflect-index] dry-run：检测到损坏历史表，加 --apply 写回")
    for level, msg in audit_reflect_index(ROOT):
        print(f"{level}: {msg}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
