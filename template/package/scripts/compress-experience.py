#!/usr/bin/env python3
"""Compress EXPERIENCE.md — v2 索引式压缩（近 5 轮 + 历史债务清理）。"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.experience_compress import (  # noqa: E402
    TIER_STATUS_HEADING,
    assemble_experience,
    build_rule_essence,
    c0_stats,
    c1_dedupe_redundant_blocks,
    load_compress_options,
    load_facts_from_tsv,
    split_experience_sections,
    tier_remarks_brief,
    tier_snapshot_one_liner,
    truncate_scenario_block,
    truncate_tier_status_table,
    validate_essence,
)
from lib.metric_analysis import section_ma7  # noqa: E402
from lib.reflect_index import repair_reflect_index_history_summaries  # noqa: E402

PRESETS: dict[str, tuple[str, str]] = {
    "minimal": ("C1", "EXP"),
    "standard": ("C2", "EXP+REF-E"),
    "wide": ("C2", "EXP+REF-E"),
}


def resolve_metric(repo: Path) -> tuple[str, str]:
    try:
        if str(repo) not in sys.path:
            sys.path.insert(0, str(repo))
        from contract import create_contract

        c = create_contract({})
        direction = getattr(c, "metric_direction", None) or "maximize"
        return c.metric_key, direction
    except Exception:
        return "metric", "maximize"


def _repair_reflect_index(repo: Path, max_summary: int) -> int:
    idx_path = repo / "references" / "REFLECT_INDEX.md"
    if not idx_path.is_file():
        return 0
    text = idx_path.read_text(encoding="utf-8")
    new_text, fixed = repair_reflect_index_history_summaries(text, max_summary=max_summary)
    if fixed:
        idx_path.write_text(new_text, encoding="utf-8")
    return fixed


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="EXPERIENCE 压缩（facts-first，不碰 TSV；含历史债务清理）")
    p.add_argument("--repo-root", type=Path, default=Path.cwd())
    p.add_argument("--preset", choices=sorted(PRESETS.keys()), default="standard")
    p.add_argument("--tier", choices=["C0", "C1", "C2"], default=None)
    p.add_argument("--scope", default=None, help="如 EXP+REF-E")
    p.add_argument("--keep-n", type=int, default=None)
    p.add_argument("--keep-reflects", type=int, default=None)
    p.add_argument("--tier-cell-max", type=int, default=None)
    p.add_argument("--dry-run", action="store_true", help="默认不写文件")
    p.add_argument("--apply", action="store_true", help="写入 EXPERIENCE 与归档")
    args = p.parse_args(argv)

    dry_run = not args.apply
    tier = args.tier or PRESETS[args.preset][0]
    scope = args.scope or PRESETS[args.preset][1]

    repo = args.repo_root.resolve()
    opts = load_compress_options(repo)
    keep_n = args.keep_n if args.keep_n is not None else opts["keep_n"]
    keep_reflects = (
        args.keep_reflects if args.keep_reflects is not None else opts["keep_reflects"]
    )
    tier_cell_max = (
        args.tier_cell_max if args.tier_cell_max is not None else opts["tier_cell_max"]
    )
    scenario_cell_max = opts["scenario_cell_max"]
    reflect_hist_max = opts["reflect_hist_summary_max"]

    exp_path = repo / "EXPERIENCE.md"
    if not exp_path.is_file():
        print("ERROR: EXPERIENCE.md missing", file=sys.stderr)
        return 2

    md = exp_path.read_text(encoding="utf-8")

    if tier == "C0":
        print(json.dumps(c0_stats(md), ensure_ascii=False, indent=2))
        return 0

    md, c1_removed = c1_dedupe_redundant_blocks(md)
    if tier == "C1":
        print(f"C1 scope={scope} removed_duplicate_sections={c1_removed}")
        print(f"chars {len(exp_path.read_text(encoding='utf-8'))} -> {len(md)}")
        if not dry_run:
            exp_path.write_text(md, encoding="utf-8")
        else:
            print("DRY-RUN: EXPERIENCE not written")
        return 0

    if tier != "C2":
        print("ERROR: only C0/C1/C2 implemented", file=sys.stderr)
        return 2

    mk, direction = resolve_metric(repo)
    facts = load_facts_from_tsv(repo, mk, direction, keep_n)
    parts = split_experience_sections(md, keep_n=keep_n, keep_reflects=keep_reflects)
    archivable_n = len(parts.archivable) + len(parts.reflects_archivable)
    tier_snapshot = tier_snapshot_one_liner(md)
    ma7_lines, _ = section_ma7(repo)
    plateau_line = ma7_lines[0] if ma7_lines else None
    essence = build_rule_essence(
        facts,
        archivable_n,
        tier_snapshot=tier_snapshot,
        plateau_line=plateau_line,
        tier_remarks=tier_remarks_brief(md),
        repo_root=repo,
    )

    err = validate_essence(
        essence,
        facts.get("known_experiments") or [],
        tier_status_present=TIER_STATUS_HEADING in md,
    )
    if err:
        print(f"VALIDATION FAIL: {err}", file=sys.stderr)
        return 1

    tier_status = truncate_tier_status_table(parts.tier_status, tier_cell_max)
    scenario_block = truncate_scenario_block(parts.scenario_block, scenario_cell_max)
    new_md = assemble_experience(
        parts,
        essence,
        keep_n,
        tier_status=tier_status,
        scenario_block=scenario_block,
        tier_cell_max=tier_cell_max,
        scenario_cell_max=scenario_cell_max,
    )
    err = validate_essence(
        essence,
        facts.get("known_experiments") or [],
        tier_status_present=TIER_STATUS_HEADING in md,
        assembled_md=new_md,
    )
    if err:
        print(f"VALIDATION FAIL: {err}", file=sys.stderr)
        return 1

    archive_name = f"archive_{datetime.now().strftime('%Y%m%d_%H%M')}_compress.md"
    archive_dir = repo / "references" / "experience"
    archive_body = "\n\n---\n\n".join([*(parts.archivable), *(parts.reflects_archivable)])

    print(f"preset={args.preset} tier=C2 scope={scope} keep_n={keep_n} c1_removed={c1_removed}")
    print(f"facts: {json.dumps(facts, ensure_ascii=False)}")
    print(f"archive: {archive_dir / archive_name} ({len(archive_body)} chars)")
    print(
        f"EXPERIENCE: {len(md)} -> {len(new_md)} chars "
        f"({100 * (1 - len(new_md)/max(len(md),1)):.0f}% reduction)"
    )
    if (repo / "references" / "REFLECT_INDEX.md").is_file():
        print(f"REFLECT_INDEX: will truncate history summaries to {reflect_hist_max} chars")

    if dry_run:
        print("DRY-RUN: no files written")
        return 0

    if "REF-E" not in scope.upper() and archivable_n > 0:
        print("WARN: scope lacks REF-E but archive would be written", file=sys.stderr)

    if archive_body.strip():
        archive_dir.mkdir(parents=True, exist_ok=True)
        (archive_dir / archive_name).write_text(
            f"# EXPERIENCE archive ({archive_name})\n\n{archive_body}\n",
            encoding="utf-8",
        )

    exp_path.write_text(new_md, encoding="utf-8")
    runs = repo / "_runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "compress_facts.json").write_text(
        json.dumps(facts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    idx_fixed = _repair_reflect_index(repo, reflect_hist_max)
    if idx_fixed:
        print(f"REFLECT_INDEX: truncated {idx_fixed} history summary cell(s)")

    print(f"Wrote {exp_path}" + (f" and {archive_dir / archive_name}" if archive_body.strip() else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
