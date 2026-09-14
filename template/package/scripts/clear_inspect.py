#!/usr/bin/env python3
"""C0 inspect — 只读运行态清理报告（junk / TSV / EXPERIENCE）。"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))


_PENDING_PLACEHOLDERS = frozenset({"（无）", "—", "-", "", "id"})


def _reflect_index_has_pending(text: str) -> bool:
    m = re.search(r"^##\s*待消费[^\n]*\n(.*?)(?=\n##\s|\Z)", text, re.DOTALL | re.I | re.MULTILINE)
    if not m:
        return False
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 6 and cells[0] not in _PENDING_PLACEHOLDERS:
            return True
    return False

JUNK_SUFFIXES = ("_preflight_check", "_smoke_check")
JUNK_EXPERIMENTS = frozenset({"preflight_check", "smoke_check"})
PHASE0_THRESHOLD = 24_000
SAVED_REFLECT_FILES = (
    "saved/reflect_latest.json",
    "saved/reflect_evidence.json",
    "saved/reflect_evidence.md",
    "saved/reflect_evidence_gaps.json",
    "saved/tier_attestation.json",
    "saved/tier_attestation.md",
    "saved/evidence_bundle.json",
    "saved/external_plan.json",
    "saved/innovation_audit.json",
)


def _count_junk_exp_dirs(repo_root: Path) -> list[str]:
    exp_root = repo_root / "_runs" / "exp"
    names: list[str] = []
    if not exp_root.is_dir():
        return names
    for child in sorted(exp_root.iterdir()):
        if not child.is_dir():
            continue
        n = child.name
        if any(n.endswith(s) for s in JUNK_SUFFIXES):
            names.append(n)
    return names


def _count_tsv_data_rows(tsv: Path) -> int:
    if not tsv.is_file():
        return 0
    lines = tsv.read_text(encoding="utf-8").splitlines()
    return max(0, len(lines) - 1) if lines else 0


def _count_jsonl(path: Path) -> int:
    if not path.is_file():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _count_reflect_artifacts(repo_root: Path) -> dict:
    auto_dir = repo_root / "references" / "auto"
    auto_md = sorted(auto_dir.glob("*_auto_reflected.md")) if auto_dir.is_dir() else []
    saved = [rel for rel in SAVED_REFLECT_FILES if (repo_root / rel).is_file()]
    index_path = repo_root / "references" / "REFLECT_INDEX.md"
    pending = False
    if index_path.is_file():
        pending = _reflect_index_has_pending(index_path.read_text(encoding="utf-8"))
    return {
        "auto_reflected_md": [p.name for p in auto_md],
        "auto_reflected_count": len(auto_md),
        "saved_reflect_files": saved,
        "saved_reflect_count": len(saved),
        "reflect_index_pending": pending,
        "has_reflect_artifacts": bool(auto_md or saved or pending),
    }


def _junk_tsv_rows(repo_root: Path, tsv: Path) -> int:
    if not tsv.is_file():
        return 0
    n = 0
    with tsv.open(encoding="utf-8") as f:
        header = f.readline()
        if not header.strip():
            return 0
        cols = header.rstrip("\n").split("\t")
        try:
            ex_i = cols.index("experiment")
        except ValueError:
            return 0
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) > ex_i and parts[ex_i].strip() in JUNK_EXPERIMENTS:
                n += 1
    return n


def inspect(repo_root: Path) -> dict:
    tsv = repo_root / "_runs" / "results.tsv"
    jsonl = repo_root / "_runs" / "results.jsonl"
    exp_root = repo_root / "_runs" / "exp"
    exp_count = 0
    if exp_root.is_dir():
        exp_count = sum(1 for p in exp_root.iterdir() if p.is_dir())

    junk_dirs = _count_junk_exp_dirs(repo_root)
    exp_path = repo_root / "EXPERIENCE.md"
    exp_chars = len(exp_path.read_text(encoding="utf-8")) if exp_path.is_file() else 0

    reflect = _count_reflect_artifacts(repo_root)

    suggested = "inspect"
    if junk_dirs or _junk_tsv_rows(repo_root, tsv) > 0:
        suggested = "junk"
    if exp_chars > PHASE0_THRESHOLD:
        suggested = "experience" if suggested == "inspect" else suggested
    if reflect["has_reflect_artifacts"]:
        suggested = "reflect"

    return {
        "repo_root": str(repo_root.resolve()),
        "exp_dir_count": exp_count,
        "junk_exp_dirs": junk_dirs,
        "junk_exp_dir_count": len(junk_dirs),
        "tsv_data_rows": _count_tsv_data_rows(tsv),
        "junk_tsv_rows": _junk_tsv_rows(repo_root, tsv),
        "jsonl_lines": _count_jsonl(jsonl),
        "experience_chars": exp_chars,
        "experience_over_phase0_threshold": exp_chars > PHASE0_THRESHOLD,
        "reflect_auto_md_count": reflect["auto_reflected_count"],
        "reflect_saved_count": reflect["saved_reflect_count"],
        "reflect_index_pending": reflect["reflect_index_pending"],
        "has_reflect_artifacts": reflect["has_reflect_artifacts"],
        "suggested_tier": suggested,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", type=Path, default=Path("."))
    ap.add_argument("--json", action="store_true", help="仅输出 JSON")
    args = ap.parse_args()
    repo_root = args.repo_root.resolve()
    report = inspect(repo_root)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    print(f"[clear-inspect] repo={report['repo_root']}", file=sys.stderr)
    print(f"  exp 目录数: {report['exp_dir_count']}", file=sys.stderr)
    print(f"  junk exp 目录 ({report['junk_exp_dir_count']}):", file=sys.stderr)
    for name in report["junk_exp_dirs"][:20]:
        print(f"    - {name}", file=sys.stderr)
    if report["junk_exp_dir_count"] > 20:
        print(f"    … +{report['junk_exp_dir_count'] - 20} more", file=sys.stderr)
    print(f"  TSV 数据行: {report['tsv_data_rows']}（junk 行: {report['junk_tsv_rows']}）", file=sys.stderr)
    print(f"  jsonl 行: {report['jsonl_lines']}", file=sys.stderr)
    print(
        f"  EXPERIENCE 字符: {report['experience_chars']}"
        f"（Phase0 阈值 {PHASE0_THRESHOLD}: "
        f"{'超' if report['experience_over_phase0_threshold'] else '未超'}）",
        file=sys.stderr,
    )
    print(
        f"  reflect 产物: auto_md={report['reflect_auto_md_count']}, "
        f"saved={report['reflect_saved_count']}, "
        f"INDEX pending={'有' if report['reflect_index_pending'] else '无'}",
        file=sys.stderr,
    )
    print(f"  建议 tier: {report['suggested_tier']}", file=sys.stderr)
    print(f"  示例: bash scripts/govern-runs.sh clear --tier {report['suggested_tier']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
