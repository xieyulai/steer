"""migrate_wrap_train_loader — 在根级 train.py 的 prepare_data 后插入 wrap_train_loader。

governance-sync 默认 ``--apply``：老仓 train.py 不会被整文件覆盖，须补这一行才能启用
D 档 ``DATA_SAMPLER`` 钩子（逻辑在 ExperimentBase，随 experiment.py 下发）。

幂等：已含 ``wrap_train_loader`` 则跳过。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_INSERT_LINE = "    train_loader = ws.wrap_train_loader(train_loader, cfg)\n"

# 常见：train_loader, val_loader = contract.prepare_data(cfg)
# 亦兼容 test_loaders / _ 等第二槽命名
_PREPARE_ASSIGN = re.compile(
    r"^([ \t]*)(train_loader\s*,\s*\w+\s*=\s*contract\.prepare_data\s*\(\s*cfg\s*\))\s*$"
)


def needs_migrate(source: str) -> bool:
    if "wrap_train_loader" in source:
        return False
    return "contract.prepare_data" in source


def migrate_source(source: str) -> tuple[str, bool]:
    """Return (new_source, changed)."""
    if not needs_migrate(source):
        return source, False
    lines = source.splitlines(keepends=True)
    out: list[str] = []
    changed = False
    for line in lines:
        out.append(line)
        m = _PREPARE_ASSIGN.match(line.rstrip("\n\r"))
        if m and not changed:
            indent = m.group(1)
            out.append(f"{indent}train_loader = ws.wrap_train_loader(train_loader, cfg)\n")
            changed = True
    if not changed:
        return source, False
    return "".join(out), True


def scan_train_py(path: Path) -> list[str]:
    if not path.is_file():
        return []
    source = path.read_text(encoding="utf-8")
    if needs_migrate(source):
        return [
            f"{path}: missing ws.wrap_train_loader after contract.prepare_data "
            "(D-tier DATA_SAMPLER hook)"
        ]
    return []


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("repo_root", type=Path, help="业务仓根目录（只处理根级 train.py）")
    p.add_argument("--apply", action="store_true", help="改写 train.py")
    args = p.parse_args(argv)
    train_py = Path(args.repo_root).resolve() / "train.py"
    if not train_py.is_file():
        print(f"[migrate_wrap_train_loader] skip: no {train_py}", file=sys.stderr)
        return 0
    source = train_py.read_text(encoding="utf-8")
    hits = scan_train_py(train_py)
    if not hits:
        print("[migrate_wrap_train_loader] OK: wrap_train_loader already present or N/A")
        return 0
    if not args.apply:
        for h in hits:
            print(f"[migrate_wrap_train_loader] NEED: {h}")
        print("[migrate_wrap_train_loader] dry-run; re-run with --apply to write")
        return 0
    new_source, changed = migrate_source(source)
    if not changed:
        print(
            "[migrate_wrap_train_loader] FAIL: could not find "
            "`train_loader, <name> = contract.prepare_data(cfg)` line to patch",
            file=sys.stderr,
        )
        return 1
    train_py.write_text(new_source, encoding="utf-8")
    print(f"[migrate_wrap_train_loader] applied: {train_py}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
