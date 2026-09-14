"""migrate_to_exploration_mode.py — 老 mode 字段 → 顶层 exploration_mode（一次性）。

供 governance-sync.sh 调用。干净切：推断等价 exploration_mode，删老键
（agent.experiment_mode / agent.objective_mode / experiment / exploration）。
无法推断 → ValueError（fail-loud）。幂等：已有 exploration_mode → no-op。
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

# 自举 path：governance-sync.sh 直接 `python3 .../migrate_to_exploration_mode.py` 调用，
# 无 PYTHONPATH=scripts。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml

# 老 4 值 style/mode → 6 档 exploration_mode
_STYLE_TO_MODE = {
    "conservative": "careful", "balanced": "optimize",
    "inductive": "innovate", "aggressive": "aggressive",
}
# 老 experiment.mode / agent.experiment_mode（3档 + 6档混用）→ exploration_mode
_EXP_TO_MODE = {
    "optimize": "optimize", "innovate": "innovate", "explore": "explore",
    "careful": "careful", "aggressive": "aggressive", "auto": "auto",
}


def _infer(raw: dict) -> str | None:
    """从老字段推断 exploration_mode；无信号 → None。优先级：agent.experiment_mode > experiment.mode > exploration.style > exploration.mode"""
    if isinstance(raw.get("agent"), dict):
        em = raw["agent"].get("experiment_mode")
        if isinstance(em, str) and em.strip().lower() in _EXP_TO_MODE:
            return _EXP_TO_MODE[em.strip().lower()]
    exp = raw.get("experiment")
    if isinstance(exp, dict) and isinstance(exp.get("mode"), str):
        m = exp["mode"].strip().lower()
        if m in _EXP_TO_MODE:
            return _EXP_TO_MODE[m]
    expl = raw.get("exploration")
    if isinstance(expl, dict):
        for key in ("style", "mode"):
            v = expl.get(key)
            if isinstance(v, str) and v.strip().lower() in _STYLE_TO_MODE:
                return _STYLE_TO_MODE[v.strip().lower()]
    return None


def migrate(yaml_path: Path, *, write: bool, backup: bool = True) -> dict:
    """返回 ``{migrated_to, wrote}``。

    - 已有 exploration_mode → no-op（幂等，migrated_to=None, wrote=False）
    - 推断出 mode → 写 exploration_mode + 删老键（agent.experiment_mode/objective_mode、experiment、exploration）
    - 无法推断 → ValueError（fail-loud）
    - backup=True + write=True + 实际写入 + 备份不存在 → 建 .deprecated.bak 一次
    """
    raw: dict = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raw = {}

    if isinstance(raw.get("exploration_mode"), str):
        return {"migrated_to": None, "wrote": False}   # 已迁移，幂等

    mode = _infer(raw)
    if mode is None:
        raise ValueError(
            "无法从老字段推断 exploration_mode（无 agent.experiment_mode / experiment.mode / "
            "exploration.{style,mode}）；请显式设 exploration_mode")

    raw["exploration_mode"] = mode
    # 删老键
    agent = raw.get("agent")
    if isinstance(agent, dict):
        agent.pop("experiment_mode", None)
        agent.pop("objective_mode", None)
    raw.pop("experiment", None)
    raw.pop("exploration", None)

    wrote = False
    if write:
        bak = yaml_path.with_suffix(".yaml.deprecated.bak")
        if backup and not bak.exists():
            shutil.copy2(yaml_path, bak)
        yaml_path.write_text(
            yaml.dump(raw, default_flow_style=False, allow_unicode=True, sort_keys=False),
            encoding="utf-8")
        wrote = True
    return {"migrated_to": mode, "wrote": wrote}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="migrate old mode fields → exploration_mode")
    ap.add_argument("yaml_path", type=Path)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="写盘（默认 dry-run）")
    mode.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args(argv)
    try:
        r = migrate(args.yaml_path, write=args.write, backup=not args.no_backup)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(f"migrated_to={r['migrated_to']} wrote={r['wrote']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
