#!/usr/bin/env python3
"""init_watchlist.py — F1.5 一次性脚本：profiles.yaml default_watchlist → nn-config.yaml ledger.watchlist

仿 migrate_agent_keys.py argparse + dry-run + backup 模式。
仅在 /auto-nn-init F1 签字后调用一次。
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

import yaml

# 系统 ledger 键：写盘前必须保留（不因与 cfg 求交而丢弃）
SYSTEM_LEDGER_KEYS: tuple[str, ...] = ("baseline_tag",)


def pin_system_ledger_keys(watchlist: list[str]) -> list[str]:
    """保证 SYSTEM_LEDGER_KEYS 均在列表中（缺则 append，保序去重）。"""
    out = list(watchlist)
    seen = {k for k in out}
    for k in SYSTEM_LEDGER_KEYS:
        if k not in seen:
            out.append(k)
            seen.add(k)
    return out


def load_profiles_default(template_root: Path, profile: str) -> list[str]:
    """读 profiles.yaml 的 profiles.<profile>.default_watchlist"""
    profiles_path = template_root / "profiles.yaml"
    if not profiles_path.is_file():
        print(f"[init_watchlist] ERR: profiles.yaml not found at {profiles_path}", file=sys.stderr)
        sys.exit(2)
    cfg = yaml.safe_load(profiles_path.read_text(encoding="utf-8")) or {}
    p = cfg.get("profiles", {}).get(profile, {})
    wl = p.get("default_watchlist", [])
    if not isinstance(wl, list):
        print(f"[init_watchlist] ERR: default_watchlist for '{profile}' is not list", file=sys.stderr)
        sys.exit(2)
    return [str(x).strip() for x in wl if x]


def first_cfg_keys(repo_root: Path) -> set[str]:
    """扫 _runs/exp/*/config.json 取 union keys（作为推荐上下限）"""
    runs_dir = repo_root / "_runs" / "exp"
    if not runs_dir.is_dir():
        return set()
    keys: set[str] = set()
    for cfg_path in runs_dir.glob("*/config.json"):
        try:
            d = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        keys.update(str(k) for k in d if not str(k).startswith("_"))
    return keys


def recommend_watchlist(default_wl: list[str], cfg_keys: set[str]) -> list[str]:
    """求交推荐，再钉系统键。"""
    if cfg_keys:
        rec = [k for k in default_wl if k in cfg_keys]
        if not rec:
            rec = list(default_wl)
    else:
        rec = list(default_wl)
    return pin_system_ledger_keys(rec)


def write_ledger_watchlist(repo_root: Path, watchlist: list[str], *, dry_run: bool) -> None:
    """读 nn-config.yaml → 写 ledger.watchlist（保留其它段）；无 yaml 则新建"""
    cfg_path = repo_root / "nn-config.yaml"
    if cfg_path.is_file():
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        if not isinstance(cfg, dict):
            cfg = {}
        if not dry_run:
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy2(cfg_path, cfg_path.with_suffix(f".yaml.bak.{ts}"))
    else:
        cfg = {}

    cfg.setdefault("ledger", {})
    if not isinstance(cfg["ledger"], dict):
        cfg["ledger"] = {}
    cfg["ledger"]["watchlist"] = watchlist

    if dry_run:
        print(f"[init_watchlist] DRY-RUN: would write {len(watchlist)} keys to ledger.watchlist")
        for k in watchlist:
            print(f"  - {k}")
    else:
        cfg_path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
        print(f"[init_watchlist] wrote {len(watchlist)} keys to {cfg_path}")


def main() -> int:
    ap = argparse.ArgumentParser(description="F1.5 init_watchlist")
    ap.add_argument("--repo-root", default=".", help="业务仓根（默认 cwd）")
    ap.add_argument("--template-root", default="template/package", help="模板根（相对 repo-root）")
    ap.add_argument("--profile", required=True, choices=["supervised", "rl", "physical"])
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写")
    ap.add_argument("--yes", action="store_true", help="跳过确认")
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    template_root = (repo_root / args.template_root).resolve()

    default_wl = load_profiles_default(template_root, args.profile)
    cfg_keys = first_cfg_keys(repo_root)
    rec = recommend_watchlist(default_wl, cfg_keys)

    print(f"[init_watchlist] profile={args.profile}; recommended {len(rec)} keys")
    for k in rec:
        print(f"  - {k}")

    if args.dry_run:
        return 0

    if not args.yes:
        ans = input("Continue? [y/N] ")
        if ans.lower() != "y":
            print("[init_watchlist] abort")
            return 1

    write_ledger_watchlist(repo_root, rec, dry_run=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
