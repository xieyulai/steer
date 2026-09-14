#!/usr/bin/env python3
"""external_tool.py — external evidence CLI (arxiv / openalex / docs / bundle dry-run)."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lib.external.arxiv import bundle_dict as arxiv_bundle  # noqa: E402
from lib.external.arxiv import format_hits_markdown, search_arxiv  # noqa: E402
from lib.external.config import load_external_config  # noqa: E402
from lib.external.docs_local import inspect_symbol  # noqa: E402
from lib.external.github_impl import search_repos  # noqa: E402
from lib.external.openalex import search_openalex  # noqa: E402
from lib.external.pdf import fetch_arxiv_excerpt  # noqa: E402
from lib.external.router import RouterContext, build_external_plan  # noqa: E402
from lib.external.scholar import search_scholar  # noqa: E402

DEFAULT_GATE = "manual:reflect_invoked"
_EXPERIENCE_MARKER = "<!-- experience-log-start -->"
_EXPERIENCE_END = "<!-- experience-log-end -->"


def _parse_last_round(exp_path: Path) -> dict[str, str]:
    """Parse the last EXPERIENCE log block after experience-log-start."""
    if not exp_path.is_file():
        return {}
    text = exp_path.read_text(encoding="utf-8")
    if _EXPERIENCE_MARKER not in text:
        return {}
    after = text.split(_EXPERIENCE_MARKER, 1)[1]
    if _EXPERIENCE_END in after:
        after = after.split(_EXPERIENCE_END, 1)[0]
    blocks = re.split(r"\n(?=### )", after.strip())
    if not blocks or not blocks[-1].strip():
        return {}
    last = blocks[-1]
    info: dict[str, str] = {}
    m = re.search(r"tier_this_round:\s*([A-Ea-e])", last)
    if m:
        info["tier_this_round"] = m.group(1).upper()
    m = re.search(r"innovation_depth:\s*(\w+)", last, re.I)
    if m:
        info["innovation_depth"] = m.group(1).strip().lower()
    m = re.search(r"innovation_rationale:\s*(.+?)(?:\n\s*-|\n\n|\Z)", last, re.I | re.S)
    if m:
        info["innovation_rationale"] = m.group(1).strip()
    m = re.search(r"phase2_focus:\s*(.+?)(?:\n\s*-|\n\n|\Z)", last, re.I | re.S)
    if m:
        info["phase2_focus"] = m.group(1).strip()
    return info


def _load_fingerprint(repo_root: Path) -> dict:
    p = repo_root / "saved" / "innovation_fingerprint.json"
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _router_context_from_experience(repo_root: Path) -> RouterContext:
    info = _parse_last_round(repo_root / "EXPERIENCE.md")
    fp = _load_fingerprint(repo_root)
    cfg = load_external_config(repo_root)
    tier_raw = str(fp.get("primary_tier") or info.get("tier_this_round", "B")).strip().upper()
    tier = tier_raw[0] if tier_raw else "B"
    if tier not in "ABCDE":
        tier = "B"
    agent_depth = info.get("innovation_depth", "routine")
    if fp.get("enabled", True) and fp and not fp.get("fallback"):
        depth = str(fp.get("effective_depth") or fp.get("depth") or agent_depth)
    else:
        depth = agent_depth
    return RouterContext(
        tier=tier,
        innovation_depth=depth,
        gate=DEFAULT_GATE,
        beat_best=False,
        routine_mislabel=False,
        not_attested_extend=False,
        reflect_skipped=False,
        rationale=info.get("innovation_rationale", ""),
        phase2_focus=info.get("phase2_focus", ""),
        config=cfg,
        fingerprint=fp or None,
        agent_depth=str(agent_depth),
        fingerprint_depth=str(fp.get("depth") or ""),
    )


def _openalex_bundle(query: str, hits: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "provider": "openalex",
        "ts": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "query": query,
        "count": len(hits),
        "hits": hits,
    }


def cmd_arxiv(args: argparse.Namespace) -> int:
    try:
        hits = search_arxiv(args.query, max_results=args.max)
    except Exception as ex:
        print(f"[external_tool] arxiv FAIL: {ex}", file=sys.stderr)
        return 1
    bundle = arxiv_bundle(args.query, hits)
    if args.json:
        print(json.dumps(bundle, ensure_ascii=False, indent=2))
    else:
        print(format_hits_markdown(hits, query=args.query))
    return 0


def cmd_openalex(args: argparse.Namespace) -> int:
    hits = search_openalex(args.query, max_results=args.max)
    bundle = _openalex_bundle(args.query, hits)
    if args.json:
        print(json.dumps(bundle, ensure_ascii=False, indent=2))
    else:
        if not hits:
            print("(no hits)")
        else:
            for i, h in enumerate(hits, start=1):
                print(f"{i}. {h.get('title', '')} [{h.get('arxiv_id', '')}] {h.get('url', '')}")
    return 0


def cmd_scholar(args: argparse.Namespace) -> int:
    tr = search_scholar(args.query, max_results=args.max)
    if tr.status == "skipped":
        print(f"[external_tool] scholar skipped: {tr.skip_reason}", file=sys.stderr)
        return 0 if not args.strict else 2
    if tr.status == "error":
        print(f"[external_tool] scholar FAIL: {tr.error}", file=sys.stderr)
        return 1
    bundle = {
        "schema_version": 1,
        "provider": "scholar",
        "ts": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "query": args.query,
        "count": len(tr.hits),
        "hits": tr.hits,
    }
    if args.json:
        print(json.dumps(bundle, ensure_ascii=False, indent=2))
    else:
        for i, h in enumerate(tr.hits, start=1):
            print(f"{i}. {h.get('title', '')} [{h.get('arxiv_id', '')}] {h.get('url', '')}")
    return 0


def cmd_pdf(args: argparse.Namespace) -> int:
    tr = fetch_arxiv_excerpt(args.id, max_chars=args.max_chars)
    if tr.status == "skipped":
        print(f"[external_tool] pdf skipped: {tr.skip_reason}", file=sys.stderr)
        return 0 if not args.strict else 2
    if tr.status == "error":
        print(f"[external_tool] pdf FAIL: {tr.error}", file=sys.stderr)
        return 1
    if args.json:
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "provider": "pdf",
                    "arxiv_id": args.id,
                    "excerpt": tr.excerpt,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(tr.excerpt or "")
    return 0


def cmd_github(args: argparse.Namespace) -> int:
    tr = search_repos(args.query, max_results=args.max)
    if tr.status == "skipped":
        print(f"[external_tool] github skipped: {tr.skip_reason}", file=sys.stderr)
        return 0 if not args.strict else 2
    if tr.status == "error":
        print(f"[external_tool] github FAIL: {tr.error}", file=sys.stderr)
        return 1
    bundle = {
        "schema_version": 1,
        "provider": "github_impl",
        "ts": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "query": args.query,
        "count": len(tr.hits),
        "hits": tr.hits,
    }
    if args.json:
        print(json.dumps(bundle, ensure_ascii=False, indent=2))
    else:
        for i, h in enumerate(tr.hits, start=1):
            print(
                f"{i}. {h.get('full_name', '')} "
                f"({h.get('stars', 0)} stars) {h.get('url', '')}"
            )
    return 0


def cmd_docs(args: argparse.Namespace) -> int:
    try:
        result = inspect_symbol(args.symbol)
    except Exception as ex:
        print(f"[external_tool] docs FAIL: {ex}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"symbol: {result['symbol']}")
        print(f"module: {result['module']}")
        print(f"source: {result['source']}")
        print(f"doc_excerpt:\n{result['doc_excerpt']}")
    return 0


def cmd_fingerprint(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    sys.path.insert(0, str(repo_root / "scripts"))
    from lib.innovation_fingerprint import load_innovation_catalog  # noqa: WPS433
    from lib.reflect_evidence import ReflectEvidenceBundle, build_reflect_evidence  # noqa: WPS433
    from lib.innovation_fingerprint import (  # noqa: WPS433
        build_innovation_fingerprint,
        write_fingerprint_artifact,
    )

    info = _parse_last_round(repo_root / "EXPERIENCE.md")
    reb = build_reflect_evidence(repo_root)
    fp = build_innovation_fingerprint(
        repo_root,
        reb_bundle=reb,
        agent_depth=str(info.get("innovation_depth") or ""),
        tier_fallback=str(info.get("tier_this_round") or "B")[:1],
    )
    if args.write:
        write_fingerprint_artifact(repo_root, fp)
    payload = fp.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(fp.summary_line)
        print(f"depth={fp.depth} effective={fp.effective_depth} catalog={len(fp.catalog_hits)}")
        _ = load_innovation_catalog(repo_root)
    return 0


def cmd_bundle(args: argparse.Namespace) -> int:
    if not args.dry_run:
        print("[external_tool] bundle requires --dry-run (prints plan JSON, no HTTP)", file=sys.stderr)
        return 2
    repo_root = Path(args.repo_root).resolve()
    ctx = _router_context_from_experience(repo_root)
    plan = build_external_plan(ctx)
    print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="外部证据 CLI（reflect Phase 1.85 调试）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_arxiv = sub.add_parser("arxiv", help="Search arXiv")
    p_arxiv.add_argument("-q", "--query", required=True, help="Search query")
    p_arxiv.add_argument("--max", type=int, default=5, help="Max results (default 5)")
    p_arxiv.add_argument("--json", action="store_true", help="JSON output")
    p_arxiv.set_defaults(func=cmd_arxiv)

    p_oa = sub.add_parser("openalex", help="Search OpenAlex")
    p_oa.add_argument("-q", "--query", required=True, help="Search query")
    p_oa.add_argument("--max", type=int, default=5, help="Max results (default 5)")
    p_oa.add_argument("--json", action="store_true", help="JSON output")
    p_oa.set_defaults(func=cmd_openalex)

    p_scholar = sub.add_parser("scholar", help="Search Google Scholar via Serper")
    p_scholar.add_argument("-q", "--query", required=True, help="Search query")
    p_scholar.add_argument("--max", type=int, default=5, help="Max results (default 5)")
    p_scholar.add_argument("--json", action="store_true", help="JSON output")
    p_scholar.add_argument(
        "--strict", action="store_true", help="Exit 2 when skipped (default: 0)"
    )
    p_scholar.set_defaults(func=cmd_scholar)

    p_pdf = sub.add_parser("pdf", help="Fetch arXiv PDF excerpt via pdftotext")
    p_pdf.add_argument("--id", required=True, help="arXiv id (e.g. 2203.07404)")
    p_pdf.add_argument(
        "--max-chars", type=int, default=4000, help="Max excerpt chars (default 4000)"
    )
    p_pdf.add_argument("--json", action="store_true", help="JSON output")
    p_pdf.add_argument(
        "--strict", action="store_true", help="Exit 2 when skipped (default: 0)"
    )
    p_pdf.set_defaults(func=cmd_pdf)

    p_github = sub.add_parser("github", help="Search GitHub repositories")
    p_github.add_argument("-q", "--query", required=True, help="Search query")
    p_github.add_argument("--max", type=int, default=3, help="Max results (default 3)")
    p_github.add_argument("--json", action="store_true", help="JSON output")
    p_github.add_argument(
        "--strict", action="store_true", help="Exit 2 when skipped (default: 0)"
    )
    p_github.set_defaults(func=cmd_github)

    p_docs = sub.add_parser("docs", help="Inspect local API symbol docs")
    p_docs.add_argument("--symbol", required=True, help="Symbol name (e.g. CrossEntropyLoss)")
    p_docs.add_argument("--json", action="store_true", help="JSON output")
    p_docs.set_defaults(func=cmd_docs)

    p_bundle = sub.add_parser("bundle", help="Build external_plan from EXPERIENCE (dry-run)")
    p_bundle.add_argument("--dry-run", action="store_true", help="Print plan JSON without HTTP")
    p_bundle.add_argument("--repo-root", default=".", help="Repository root (default .)")
    p_bundle.set_defaults(func=cmd_bundle)

    p_fp = sub.add_parser("fingerprint", help="Build innovation fingerprint (Phase 0.75)")
    p_fp.add_argument("--repo-root", default=".", help="Repository root (default .)")
    p_fp.add_argument("--json", action="store_true", help="JSON output")
    p_fp.add_argument("--write", action="store_true", help="Write saved/innovation_fingerprint.json")
    p_fp.set_defaults(func=cmd_fingerprint)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
