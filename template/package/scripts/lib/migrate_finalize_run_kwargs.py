"""migrate_finalize_run_kwargs — 根级 train.py 去掉 finalize_run(best_metrics=)。

默认 scan；``--apply`` 用 AST 改写为 ``precomputed_official_metrics=`` 或删除冗余 ``best_metrics``。
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path


class UnparseableFinalizeRunError(Exception):
    """finalize_run 调用含 best_metrics 且 **kwargs，无法安全改写。"""


def _is_finalize_run_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Attribute) and func.attr == "finalize_run":
        return True
    if isinstance(func, ast.Name) and func.id == "finalize_run":
        return True
    return False


def _finalize_run_best_metrics_hits(tree: ast.AST) -> list[str]:
    hits: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _is_finalize_run_call(node):
            continue
        for kw in node.keywords:
            if kw.arg == "best_metrics":
                hits.append(
                    f"line {kw.lineno}: finalize_run(..., best_metrics=...) "
                    "→ use precomputed_official_metrics= or remove"
                )
    return hits


def scan_train_py(path: Path) -> list[str]:
    """Return human-readable hit lines; empty if clean or file missing."""
    if not path.is_file():
        return []
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []
    return _finalize_run_best_metrics_hits(tree)


class _FinalizeRunMigrator(ast.NodeTransformer):
    def visit_Call(self, node: ast.Call) -> ast.Call:
        self.generic_visit(node)
        if not _is_finalize_run_call(node):
            return node

        has_best_metrics = False
        has_kwargs = False
        has_precomputed = False
        for kw in node.keywords:
            if kw.arg is None:
                has_kwargs = True
            elif kw.arg == "best_metrics":
                has_best_metrics = True
            elif kw.arg == "precomputed_official_metrics":
                has_precomputed = True

        if has_best_metrics and has_kwargs:
            raise UnparseableFinalizeRunError(
                f"line {node.lineno}: finalize_run has best_metrics= and **kwargs"
            )

        if not has_best_metrics:
            return node

        new_keywords: list[ast.keyword] = []
        for kw in node.keywords:
            if kw.arg == "best_metrics":
                if has_precomputed:
                    continue
                new_keywords.append(
                    ast.keyword(
                        arg="precomputed_official_metrics",
                        value=kw.value,
                        lineno=kw.lineno,
                        col_offset=kw.col_offset,
                    )
                )
            else:
                new_keywords.append(kw)
        node.keywords = new_keywords
        return node


def _migrate_source(source: str, *, filename: str) -> str:
    tree = ast.parse(source, filename=filename)
    migrated = _FinalizeRunMigrator().visit(tree)
    ast.fix_missing_locations(migrated)
    return ast.unparse(migrated)


def apply_train_py(path: Path, *, backup: bool = True) -> None:
    """Rewrite train.py in place; raise on unsafe parse without modifying file."""
    original = path.read_text(encoding="utf-8")
    try:
        new_content = _migrate_source(original, filename=str(path))
    except Exception:
        raise
    if new_content == original:
        return
    if backup:
        backup_path = path.with_suffix(path.suffix + ".bak")
        if not backup_path.exists():
            backup_path.write_text(original, encoding="utf-8")
    path.write_text(new_content, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan/apply migrate finalize_run best_metrics → precomputed_official_metrics"
    )
    parser.add_argument("repo_root", type=Path, help="业务仓根目录（只处理根级 train.py）")
    parser.add_argument("--apply", action="store_true", help="改写 train.py")
    parser.add_argument("--no-backup", action="store_true", help="不写 .bak 备份")
    args = parser.parse_args(argv)

    train_py = Path(args.repo_root).resolve() / "train.py"
    if not train_py.is_file():
        return 0

    if args.apply:
        apply_train_py(train_py, backup=not args.no_backup)
        return 0

    hits = scan_train_py(train_py)
    for hit in hits:
        print(hit, file=sys.stderr)
    return 1 if hits else 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.exit(main())
