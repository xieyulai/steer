#!/usr/bin/env python3
"""立尺 CLI：status / pick-reference / stamp。不改 keepers.json。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lib.baseline_anchors_status import assess_baseline_anchors  # noqa: E402
from lib.baseline_stamp import (  # noqa: E402
    completed_experiment_rounds,
    paths_match,
    pick_midpoint_reference,
    should_emit_reference_start,
    stamp_tag,
    _rel_exp,
)
from lib.ledger_anchor import focus_scenario_id  # noqa: E402
from lib.run_ledger_summary import _float_cell, metric_key, tsv_rows  # noqa: E402
from lib.source_calibration import CHECK_REL, enforce_before_stamp  # noqa: E402


def _sid(root: Path, explicit: str | None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    return (focus_scenario_id(root) or "default").strip() or "default"


def cmd_status(root: Path, scenario: str | None) -> int:
    sid = _sid(root, scenario)
    st = assess_baseline_anchors(root)
    payload = st.to_dict()
    payload["scenario_id"] = sid
    payload["completed_rounds"] = completed_experiment_rounds(root, sid)
    payload["emit_reference_start"] = should_emit_reference_start(root, sid)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_pick_reference(root: Path, scenario: str | None) -> int:
    sid = _sid(root, scenario)
    try:
        picked = pick_midpoint_reference(root, sid)
    except ValueError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps({"ok": True, **picked}, ensure_ascii=False, indent=2))
    return 0


def cmd_stamp(
    root: Path,
    *,
    tag: str,
    exp_dir: str,
    replace: bool,
    source: str,
    scenario: str | None,
) -> int:
    try:
        out = stamp_tag(
            root,
            exp_dir=exp_dir,
            tag=tag,
            replace=replace,
            source=source,
            scenario_id=scenario,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def _port_primary(root: Path, exp_dir: str) -> tuple[float | None, str]:
    rel = _rel_exp(root, exp_dir)
    mk = metric_key(root)
    for row in tsv_rows(root):
        exp = str(row.get("exp_dir") or "").strip()
        if exp and paths_match(exp, rel):
            return _float_cell(row, mk), rel
    return None, rel


def cmd_check_source_cal(root: Path, exp_dir: str) -> int:
    port, rel = _port_primary(root, exp_dir)
    try:
        check = enforce_before_stamp(
            root,
            tag="reference",
            source="literature",
            port_value=port,
            port_exp_dir=rel,
        )
    except (ValueError, FileNotFoundError) as exc:
        payload: dict = {"ok": False, "error": str(exc)}
        check_path = root / CHECK_REL
        if check_path.is_file():
            try:
                payload["check"] = json.loads(check_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps({"ok": True, "check": check, "skipped": check is None}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="立尺：朴素下界 / 公开对照")
    sub = p.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("status", help="看当前场景尺子与缺尺建议")
    st.add_argument("--repo-root", default=".")
    st.add_argument("--scenario", default=None)
    pk = sub.add_parser("pick-reference", help="按中点从已有成绩挑公开对照")
    pk.add_argument("--repo-root", default=".")
    pk.add_argument("--scenario", default=None)
    sm = sub.add_parser("stamp", help="给已有实验贴 plain/reference（不重跑）")
    sm.add_argument("--repo-root", default=".")
    sm.add_argument("--scenario", default=None)
    sm.add_argument("--tag", required=True, choices=("plain", "reference"))
    sm.add_argument("--exp-dir", required=True)
    sm.add_argument("--replace", action="store_true")
    sm.add_argument(
        "--source",
        default="",
        choices=("", "literature", "ledger_midpoint"),
    )
    ck = sub.add_parser("check-source-cal", help="校对本仓复现分与本机原仓校准分（不贴尺）")
    ck.add_argument("--repo-root", default=".")
    ck.add_argument("--exp-dir", required=True)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.repo_root).resolve()
    if args.cmd == "status":
        return cmd_status(root, args.scenario)
    if args.cmd == "pick-reference":
        return cmd_pick_reference(root, args.scenario)
    if args.cmd == "stamp":
        src = str(args.source or "")
        if args.tag == "reference" and not src:
            src = "ledger_midpoint"
        return cmd_stamp(
            root,
            tag=args.tag,
            exp_dir=args.exp_dir,
            replace=bool(args.replace),
            source=src,
            scenario=args.scenario,
        )
    if args.cmd == "check-source-cal":
        return cmd_check_source_cal(root, args.exp_dir)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
