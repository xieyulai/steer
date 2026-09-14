#!/usr/bin/env python3
"""场景完整性门禁：F1 清单、nn-config、TSV scenario_id、keepers.json 对齐。

迁后 nn-doctor 调用；模板根（.template-maintainer）跳过。
"""
from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.scenario_inventory import audit_scenario_completeness  # noqa: E402


def check(repo_root: str | Path) -> list[dict[str, str]]:
    root = Path(repo_root).resolve()
    if (root / ".template-maintainer").is_file():
        return []
    return audit_scenario_completeness(root)


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    items = check(root)
    fails = [i for i in items if i.get("level") == "fail"]
    warns = [i for i in items if i.get("level") == "warn"]
    for item in warns:
        print(f"WARN: {item['detail']} → {item['fix']}", file=sys.stderr)
    for item in fails:
        print(f"FAIL: {item['detail']} → {item['fix']}", file=sys.stderr)
    if fails:
        return 1
    if warns:
        return 0
    if not items:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
