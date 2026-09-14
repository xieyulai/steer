#!/usr/bin/env python3
"""G-hardcoded-params: 扫描 workspace 函数签名里的硬编码默认值（config-only 违规）。

用法：python3 scripts/scan_hardcoded_params.py <repo_root>

输出：每个硬编码参数一行 `[WARN] PARAM_NAME=default_value (source:line)`
exit 0（始终不阻断，仅 WARN）。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 复用 analyze_hardcoded_params 的扫描逻辑
sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_hardcoded_params import analyze_workspace


def main() -> None:
    if len(sys.argv) < 2:
        print("用法: python3 scan_hardcoded_params.py <repo_root>", file=sys.stderr)
        sys.exit(1)

    repo_root = Path(sys.argv[1]).resolve()
    if not (repo_root / "workspace").is_dir():
        sys.exit(0)  # 无 workspace 目录，SKIP

    # 扫描 workspace 函数签名默认值（train_env_covered=空，全量报告）
    hardcoded = analyze_workspace(repo_root, train_env_covered=set())

    if not hardcoded:
        sys.exit(0)

    for name, value in sorted(hardcoded.items()):
        print(f"[WARN] {name}={value}")

    sys.exit(0)  # 始终 exit 0（WARN-only，不阻断）


if __name__ == "__main__":
    main()
