#!/usr/bin/env python3
"""literature_search.py — arXiv 检索（reflect / auto-nn-literature 共用入口）

用法（项目根）：
  python3 scripts/literature_search.py --query "causal physics-informed neural networks"
  python3 scripts/literature_search.py --query "residual adaptive refinement PINN" --max 3 --format json
  python3 scripts/literature_search.py --query "Fourier neural operator PDE" --out saved/literature_hits.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lib.literature_search import (  # noqa: E402
    bundle_dict,
    format_hits_markdown,
    format_hits_table,
    search_arxiv,
)


def main() -> int:
    p = argparse.ArgumentParser(description="arXiv literature search (auto-nn)")
    p.add_argument("--query", "-q", required=True, help="检索词（自然语言或关键词）")
    p.add_argument("--max", type=int, default=5, help="最多返回条数（默认 5，上限 50）")
    p.add_argument(
        "--format",
        choices=("json", "markdown", "table"),
        default="markdown",
        help="输出格式（默认 markdown）",
    )
    p.add_argument("--out", type=Path, default=None, help="可选：写入 JSON 文件路径")
    p.add_argument("--timeout", type=float, default=30.0, help="HTTP 超时秒数")
    args = p.parse_args()

    try:
        hits = search_arxiv(args.query, max_results=args.max, timeout_sec=args.timeout)
    except Exception as ex:
        print(f"[literature_search] FAIL: {ex}", file=sys.stderr)
        return 1

    bundle = bundle_dict(args.query, hits)
    if args.out:
        out_path = args.out
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[literature_search] wrote {out_path} ({len(hits)} hits)", file=sys.stderr)

    if args.format == "json":
        print(json.dumps(bundle, ensure_ascii=False, indent=2))
    elif args.format == "table":
        print(format_hits_table(hits))
    else:
        print(format_hits_markdown(hits, query=args.query))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
