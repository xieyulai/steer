"""migrate_agent_keys.py — agent.* 迁移键 → 顶层 block，可选 cleanup pop。

供 governance-sync.sh 调用。
默认（无 --cleanup）：ADDITIVE copy agent→top（顶层已有则 top-wins），保留 agent 别名。
带 --cleanup：copy 后 pop 全部 AGENT_TO_TOP 别名（顶层唯一权威）。

AGENT_TO_TOP_KEYS 从 lib.nn_config import（单一真源）。
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

# 自举 path：governance-sync.sh 直接 `python3 .../lib/migrate_agent_keys.py` 调用本脚本，
# 无 PYTHONPATH=scripts，故 `from lib.nn_config` 会 ModuleNotFoundError。把 scripts/ 加进 path。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml

from lib.nn_config import AGENT_TO_TOP_KEYS


def migrate(
    yaml_path: Path, *, write: bool, backup: bool = True, cleanup: bool = False
) -> dict:
    """返回 ``{migrated, kept_top, popped, wrote}``.

    - migrated = ``[(old_key, block, new_key, value)]`` — 实际从 agent 拷到顶层的键
    - kept_top = ``[(old_key, block, new_key, top_value)]`` — 顶层已存在、未覆盖（top wins）
    - popped   = cleanup 时从 agent 删除的 old_key 列表
    - wrote    = 是否真的写了文件

    ADDITIVE：对每个 ``AGENT_TO_TOP_KEYS`` 条目：
      - old_key 在 agent 且顶层无 new_key → copy（migrated）
      - old_key 在 agent 但顶层已有 → top wins（kept_top）
    cleanup=True：再 pop 全部仍在 agent 的迁移别名（含 kept_top 对应别名）。
    """
    raw: dict = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raw = {}
    agent = raw.get("agent")
    if not isinstance(agent, dict):
        agent = {}
        raw["agent"] = agent

    migrated: list = []
    kept_top: list = []
    did_change = False

    for old_key, (block, new_key) in AGENT_TO_TOP_KEYS.items():
        if old_key not in agent:
            continue
        top_block = raw.get(block)
        if not isinstance(top_block, dict):
            top_block = {}
        if new_key in top_block:
            kept_top.append((old_key, block, new_key, top_block[new_key]))
        else:
            top_block[new_key] = agent[old_key]
            raw[block] = top_block
            migrated.append((old_key, block, new_key, agent[old_key]))
            did_change = True

    popped: list[str] = []
    if cleanup:
        # forward_and_pop：对 kept_top 也 pop；对未 copy 的不再改顶层（已有）
        # 但 forward 会用 agent 值覆盖顶层——cleanup 应对 kept_top 只 pop 不覆盖。
        agent = raw.get("agent") or {}
        for old_key, (block, new_key) in AGENT_TO_TOP_KEYS.items():
            if old_key not in agent:
                continue
            top = raw.get(block)
            if not isinstance(top, dict):
                top = {}
                raw[block] = top
            if new_key not in top:
                top[new_key] = agent[old_key]
            del agent[old_key]
            popped.append(old_key)
            did_change = True
        raw["agent"] = agent

    if not write or not did_change:
        return {
            "migrated": migrated,
            "kept_top": kept_top,
            "popped": popped,
            "wrote": False,
        }

    backup_path = yaml_path.with_suffix(".yaml.deprecated.bak")
    if backup and not backup_path.exists():
        shutil.copy2(yaml_path, backup_path)

    yaml_path.write_text(
        yaml.dump(raw, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return {
        "migrated": migrated,
        "kept_top": kept_top,
        "popped": popped,
        "wrote": True,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="把旧业务仓 yaml 的 agent.* 迁移键 copy 到顶层 block；可选 --cleanup pop 别名。"
    )
    ap.add_argument("--yaml", type=Path, required=True, help="目标 nn-config.yaml")
    ap.add_argument("--write", action="store_true", help="实际写文件（默认 dry-run）")
    ap.add_argument(
        "--cleanup",
        action="store_true",
        help="copy 后 pop 全部 AGENT_TO_TOP 别名（顶层唯一权威）",
    )
    args = ap.parse_args(argv)
    if not args.yaml.is_file():
        print(f"[migrate] FAIL: {args.yaml} 不存在", file=sys.stderr)
        return 1
    result = migrate(args.yaml, write=args.write, cleanup=args.cleanup)
    for old, block, new, val in result["migrated"]:
        print(f"[migrate] {'WROTE' if args.write else 'DRY-RUN'} agent.{old} -> {block}.{new} = {val!r}")
    for old, block, new, val in result["kept_top"]:
        print(f"[migrate] keep-top {block}.{new} = {val!r} (agent.{old})")
    for old in result["popped"]:
        print(f"[migrate] {'POP' if args.write else 'DRY-POP'} agent.{old}")
    print(
        f"[migrate] migrated={len(result['migrated'])} "
        f"kept_top={len(result['kept_top'])} "
        f"popped={len(result['popped'])} wrote={result['wrote']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
