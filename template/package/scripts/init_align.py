#!/usr/bin/env python3
"""init_align.py — 读写校验 .auto-nn/init-align.json；CLI: probe|write|load。"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib.align_probe import AlignSuggestion, probe, suggestion_to_dict  # noqa: E402

ALIGN_NAME = "init-align.json"
SCHEMA_VERSION = 1
PROFILES = frozenset({"supervised", "rl", "physical"})
OBJECT_TYPES = frozenset({"data", "code", "framework"})
WORKFLOWS = frozenset({"build", "migrate", "update"})


def align_path(repo_root: Path) -> Path:
    return Path(repo_root) / ".auto-nn" / ALIGN_NAME


def load_align(repo_root: Path) -> dict | None:
    p = align_path(repo_root)
    if not p.is_file():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"invalid init-align: {p}")
    return data


def validate_align(data: dict) -> None:
    if int(data.get("schema_version") or 0) != SCHEMA_VERSION:
        raise ValueError(f"unsupported schema_version: {data.get('schema_version')}")
    if data.get("workflow") not in WORKFLOWS:
        raise ValueError(f"bad workflow: {data.get('workflow')}")
    if data.get("object_type") not in OBJECT_TYPES:
        raise ValueError(f"bad object_type: {data.get('object_type')}")
    if data.get("profile") not in PROFILES:
        raise ValueError(f"bad profile: {data.get('profile')}")


def write_align(
    repo_root: Path,
    *,
    entry: str,
    source_root: str | None,
    workflow: str,
    object_type: str,
    profile: str,
    pattern: str | None = None,
    framework_name: str | None = None,
    framework_mutability: str | None = None,
    detect_snapshot: dict | None = None,
    probe_snapshot: dict | None = None,
    overrides: dict | None = None,
    amend: bool = False,
) -> Path:
    root = Path(repo_root)
    out = align_path(root)
    if out.is_file() and not amend:
        raise FileExistsError(
            f"{out} 已存在；改正请传 --amend（禁止静默覆盖）"
        )
    data = {
        "schema_version": SCHEMA_VERSION,
        "confirmed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "entry": entry,
        "source_root": source_root,
        "target_root": str(root.resolve()),
        "workflow": workflow,
        "object_type": object_type,
        "pattern": pattern,
        "profile": profile,
        "framework_name": framework_name,
        "framework_mutability": framework_mutability,
        "detect_snapshot": detect_snapshot or {},
        "probe_snapshot": probe_snapshot or {},
        "overrides": overrides or {"profile": False, "object_type": False},
    }
    validate_align(data)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def _nn_config_profile(repo_root: Path) -> str | None:
    """读 nn-config.yaml 的 profile；失败或缺失返回 None（不因一致性报 WARN）。"""
    cfg_path = Path(repo_root) / "nn-config.yaml"
    if not cfg_path.is_file():
        return None
    try:
        from lib.nn_config import load_nn_config

        cfg = load_nn_config(Path(repo_root))
        p = cfg.get("profile")
        return str(p) if p else None
    except Exception:
        return None


def doctor_check_init_align(repo_root: Path) -> tuple[str, str]:
    """轻量 doctor：缺卡 WARN；坏卡 FAIL；profile 不一致 WARN；否则 PASS。"""
    root = Path(repo_root).resolve()
    p = align_path(root)
    if not p.is_file():
        return (
            "WARN",
            "缺 .auto-nn/init-align.json（近版 new-project 应写入；老仓可忽略）",
        )
    try:
        raw = p.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return ("FAIL", "init-align 非 JSON object")
        validate_align(data)
    except json.JSONDecodeError as exc:
        return ("FAIL", f"init-align JSON 损坏: {exc}")
    except ValueError as exc:
        return ("FAIL", f"init-align schema 非法: {exc}")
    except OSError as exc:
        return ("FAIL", f"无法读取 init-align: {exc}")

    cfg_profile = _nn_config_profile(root)
    align_profile = str(data.get("profile") or "")
    if cfg_profile and align_profile and cfg_profile != align_profile:
        return (
            "WARN",
            f"对齐卡 profile={align_profile} 与 nn-config profile={cfg_profile} 不一致",
        )
    return ("PASS", "init-align.json 合法")


def cmd_probe(args: argparse.Namespace) -> int:
    sug = probe(args.repo_root, args.source_root, force_workflow=args.force_workflow)
    print(json.dumps(suggestion_to_dict(sug), indent=2, ensure_ascii=False))
    if not sug.migrate_allowed:
        return 2
    return 0


def cmd_write(args: argparse.Namespace) -> int:
    path = write_align(
        Path(args.repo_root),
        entry=args.entry,
        source_root=args.source_root,
        workflow=args.workflow,
        object_type=args.object_type,
        profile=args.profile,
        pattern=args.pattern,
        framework_name=args.framework_name,
        framework_mutability=args.framework_mutability,
        detect_snapshot=json.loads(args.detect_snapshot) if args.detect_snapshot else None,
        probe_snapshot=json.loads(args.probe_snapshot) if args.probe_snapshot else None,
        overrides=json.loads(args.overrides) if args.overrides else None,
        amend=args.amend,
    )
    print(str(path))
    return 0


def cmd_load(args: argparse.Namespace) -> int:
    data = load_align(Path(args.repo_root))
    if data is None:
        print("{}", end="")
        return 1
    validate_align(data)
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="init-align probe/write/load")
    sub = p.add_subparsers(dest="cmd", required=True)

    pp = sub.add_parser("probe", help="Print AlignSuggestion JSON")
    pp.add_argument("--repo-root", required=True)
    pp.add_argument("--source-root", default=None)
    pp.add_argument("--force-workflow", default=None)
    pp.set_defaults(func=cmd_probe)

    pw = sub.add_parser("write", help="Write .auto-nn/init-align.json")
    pw.add_argument("--repo-root", required=True)
    pw.add_argument("--entry", required=True, choices=["A", "B"])
    pw.add_argument("--source-root", default=None)
    pw.add_argument("--workflow", required=True, choices=sorted(WORKFLOWS))
    pw.add_argument("--object-type", required=True, choices=sorted(OBJECT_TYPES))
    pw.add_argument("--profile", required=True, choices=sorted(PROFILES))
    pw.add_argument("--pattern", default=None)
    pw.add_argument("--framework-name", default=None)
    pw.add_argument("--framework-mutability", default=None)
    pw.add_argument("--detect-snapshot", default=None)
    pw.add_argument("--probe-snapshot", default=None)
    pw.add_argument("--overrides", default=None)
    pw.add_argument("--amend", action="store_true")
    pw.set_defaults(func=cmd_write)

    pl = sub.add_parser("load", help="Load and validate init-align.json")
    pl.add_argument("--repo-root", required=True)
    pl.set_defaults(func=cmd_load)

    args = p.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
