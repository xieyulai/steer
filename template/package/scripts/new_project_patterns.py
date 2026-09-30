# new_project_patterns.py
"""migrate pattern 分流的单一真源 helper（消费 scenarios/migrate.yaml）。

new-project.sh 通过 CLI 调用：
  python3 new_project_patterns.py --source-root <src> --pattern   # 只输出 pattern 名
  python3 new_project_patterns.py --source-root <src> --emit      # pattern+复制参数 JSON
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

DEFAULT_SCENARIOS_DIR = pathlib.Path(__file__).resolve().parent.parent / "scenarios"


def load_patterns(scenarios_dir: pathlib.Path | None = None) -> dict:
    import yaml

    p = (scenarios_dir or DEFAULT_SCENARIOS_DIR) / "migrate.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def resolve_pattern(source_root: pathlib.Path | None) -> str:
    """源有 contract/ → full_copy；否则（含无源）port_to_contract（保守缺省）。

    与 migrate.yaml patterns.*.when 的「有无 contract/」判定保持一致。
    """
    if source_root is not None and (pathlib.Path(source_root) / "contract").is_dir():
        return "full_copy"
    return "port_to_contract"


def emit(data: dict, source_root: pathlib.Path | None) -> dict:
    """shell 消费用的参数包：pattern + 源侧禁拷 + (copy_targets | legacy_dir)。"""
    pattern = resolve_pattern(source_root)
    out: dict = {
        "pattern": pattern,
        "forbid": data.get("forbid", []),
        "port_targets": data.get("port_targets", {}),
    }
    if pattern == "full_copy":
        out["copy_targets"] = data["patterns"]["full_copy"]["copy_targets"]
    else:
        out["legacy_dir"] = data["patterns"]["port_to_contract"]["legacy_dir"]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="migrate pattern 分流（真源 migrate.yaml）")
    ap.add_argument("--scenarios-dir", type=pathlib.Path, default=DEFAULT_SCENARIOS_DIR)
    ap.add_argument("--source-root", type=pathlib.Path, default=None)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--emit", action="store_true", help="输出 pattern + 复制参数 JSON")
    g.add_argument("--pattern", action="store_true", help="只输出 pattern 名")
    args = ap.parse_args(argv)
    data = load_patterns(args.scenarios_dir)
    if args.pattern:
        print(resolve_pattern(args.source_root))
        return 0
    print(json.dumps(emit(data, args.source_root), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
