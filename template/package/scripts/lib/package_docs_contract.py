"""PROTOCOL/CLAUDE 包文档契约 lint（banned_primary_path + required_mentions）。"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

_DEFAULT_CONTRACT = Path(__file__).resolve().parent / "package_docs_contract.yaml"


def load_contract(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"contract must be mapping: {path}")
    return data


def _window_has_allow(lines: list[str], idx: int, radius: int, allows: list[str]) -> bool:
    lo = max(0, idx - radius)
    hi = min(len(lines), idx + radius + 1)
    blob = "\n".join(lines[lo:hi])
    return any(a in blob for a in allows)


def scan_docs(package_root: Path, contract: dict[str, Any]) -> tuple[list[str], list[str]]:
    fails: list[str] = []
    warns: list[str] = []
    radius = int(contract.get("allow_context_radius", 2))
    allows = list(contract.get("allow_context_substrings") or [])
    scan_files = list(contract.get("scan_files") or [])

    banned = list(contract.get("banned_primary_path") or [])
    for rel in scan_files:
        path = package_root / rel
        if not path.is_file():
            fails.append(f"[FAIL] missing scan file: {rel}")
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for bi in banned:
            bid = str(bi.get("id", "?"))
            pat = str(bi.get("pattern", ""))
            if not pat:
                continue
            cre = re.compile(pat)
            for i, line in enumerate(lines):
                if not cre.search(line):
                    continue
                if _window_has_allow(lines, i, radius, allows):
                    continue
                fails.append(
                    f"[FAIL] {rel}:{i + 1}: {bid} banned_primary_path matched /{pat}/"
                )

    for req in contract.get("required_mentions") or []:
        term = str(req.get("term", ""))
        rel = str(req.get("file", ""))
        if not term or not rel:
            continue
        path = package_root / rel
        if not path.is_file():
            fails.append(f"[FAIL] required missing file: {rel} (term={term!r})")
            continue
        text = path.read_text(encoding="utf-8")
        if term not in text:
            fails.append(
                f"[FAIL] {rel}: required_mention missing {term!r}"
            )

    return fails, warns


def check_code_docs_drift(
    repo_root: Path,
    package_rel: str,
    base: str,
    head: str,
) -> list[str]:
    """若 package 下 py/sh 有变更且 PROTOCOL/CLAUDE/intent-map 未变 → WARN。"""
    try:
        out = subprocess.check_output(
            ["git", "diff", "--name-only", f"{base}..{head}"],
            cwd=str(repo_root),
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    names = [n.strip() for n in out.splitlines() if n.strip()]
    pkg_prefix = package_rel.rstrip("/") + "/"
    code_hit = False
    doc_hit = False
    doc_suffixes = (
        "PROTOCOL.md",
        "CLAUDE.md",
        "docs/nn-routing/intent-map.md",
    )
    for n in names:
        if not n.startswith(pkg_prefix) and n != package_rel.rstrip("/"):
            if not n.startswith("template/package/") and package_rel == "template/package":
                continue
        rel_in_pkg = n
        if n.startswith(pkg_prefix):
            rel_in_pkg = n[len(pkg_prefix) :]
        elif n.startswith("template/package/"):
            rel_in_pkg = n[len("template/package/") :]
        else:
            continue

        if rel_in_pkg in doc_suffixes:
            doc_hit = True
            continue
        norm = rel_in_pkg.replace("\\", "/")
        if "/tests/" in f"/{norm}" or Path(norm).name.startswith("test_"):
            continue
        if Path(norm).suffix in {".py", ".sh"}:
            code_hit = True

    if code_hit and not doc_hit:
        return [
            "[WARN] code touched under template/package but PROTOCOL.md / "
            "CLAUDE.md / docs/nn-routing/intent-map.md untouched — "
            "翻 docs/AUTO-NN-package-docs-checklist.md 触发表"
        ]
    return []


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="package docs contract lint")
    ap.add_argument(
        "--package-root",
        type=Path,
        default=None,
        help="template/package 根（默认：仓根/template/package）",
    )
    ap.add_argument("--contract", type=Path, default=None)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--no-git", action="store_true", help="跳过 code-touched WARN")
    ap.add_argument("--base", default="HEAD~1")
    ap.add_argument("--head", default="HEAD")
    args = ap.parse_args(argv)

    here = Path(__file__).resolve()
    default_pkg = here.parents[2]  # template/package
    default_repo = here.parents[4]  # auto-nn-experiment
    package_root = (args.package_root or default_pkg).resolve()
    contract_path = (args.contract or (package_root / "scripts" / "lib" / "package_docs_contract.yaml")).resolve()

    contract = load_contract(contract_path)
    fails, warns = scan_docs(package_root, contract)

    if not args.no_git:
        try:
            repo_root = default_repo
            if args.package_root is not None:
                repo_root = package_root.parents[1] if package_root.name == "package" else default_repo
            if (package_root.parent.parent / ".git").exists():
                repo_root = package_root.parent.parent
            warns.extend(
                check_code_docs_drift(
                    repo_root,
                    "template/package",
                    args.base,
                    args.head,
                )
            )
        except Exception:
            pass

    for line in fails:
        print(line, file=sys.stderr)
    for line in warns:
        print(line, file=sys.stderr)
    print(f"FAIL={len(fails)} WARN={len(warns)}", file=sys.stderr)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
