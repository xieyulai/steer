#!/usr/bin/env python3
"""扫 TSV exploration_space：禁 E-、空格 WARN/FAIL、e_feedback schema。

供 nn-doctor exploration_space_stamp 检查。发版戳
``.auto-nn/exploration-stamp-since`` 之前的历史空格 WARN，之后正式行空格 FAIL。

另：``--check-unregistered`` → doctor 独立行 ``unregistered_config_keys``：
最近两行已训 config 相对变化的键若不在 catalog
``primary_keys`` ∪ ``scalar_keys`` ∪ ``ignore_config_keys`` → WARN。

用法:
  python3 scripts/check_exploration_stamp.py --check --repo-root .
    → 只读检查, 首行 ``PASS:`` / ``WARN:`` / ``FAIL:`` 供 nn-doctor 解析
  python3 scripts/check_exploration_stamp.py --check-unregistered --repo-root .
    → 未登记键 WARN（独立行，勿并入 exploration_space_stamp）
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

CELL_RE = re.compile(r"^[ABCD]-(routine|derived|different|novel)$")
UNTRAINED_ELAPSED = 1.0


@dataclass(frozen=True)
class Issue:
    severity: str  # FAIL | WARN
    message: str


def parse_elapsed(row: dict[str, str]) -> float:
    raw = (row.get("elapsed_sec") or "").strip()
    if not raw:
        return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


def parse_row_date(timestamp: str | None) -> date | None:
    text = (timestamp or "").strip()
    if not text:
        return None
    # ISO date or datetime (with optional Z / offset)
    try:
        if len(text) >= 10 and text[4] == "-" and text[7] == "-":
            return date.fromisoformat(text[:10])
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def parse_since_date(path: Path) -> date | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def check_tsv_rows(
    rows: list[dict[str, str]],
    *,
    since: date | None,
) -> list[Issue]:
    issues: list[Issue] = []
    for i, row in enumerate(rows, start=2):  # header = line 1
        cell = (row.get("exploration_space") or "").strip()
        exp = (row.get("experiment") or "").strip() or f"L{i}"
        elapsed = parse_elapsed(row)

        if "E-" in cell:
            issues.append(Issue("FAIL", f"L{i} {exp}: exploration_space 含 E- ({cell!r})"))
            continue

        if cell and not CELL_RE.match(cell):
            issues.append(
                Issue(
                    "FAIL",
                    f"L{i} {exp}: exploration_space 非法 {cell!r} "
                    f"(须 ^[ABCD]-(routine|derived|different|novel)$ 或空)",
                )
            )
            continue

        if cell:
            continue

        # 空格：未开训（墙钟 <1s 或 untrained 列）允许；旧表无列则仍只靠 elapsed
        raw_untrained = str(row.get("untrained") or "").strip().lower()
        if raw_untrained in {"1", "true", "yes", "y"}:
            continue
        if elapsed < UNTRAINED_ELAPSED:
            continue

        row_d = parse_row_date(row.get("timestamp"))
        if since is None:
            issues.append(
                Issue(
                    "WARN",
                    f"L{i} {exp}: 已训空格且无 .auto-nn/exploration-stamp-since（历史/未戳）",
                )
            )
            continue
        if row_d is None:
            issues.append(
                Issue(
                    "WARN",
                    f"L{i} {exp}: 已训空格但 timestamp 不可解析（无法与发版戳比对）",
                )
            )
            continue
        if row_d < since:
            issues.append(
                Issue(
                    "WARN",
                    f"L{i} {exp}: 发版戳前历史空格 ({row_d.isoformat()} < {since.isoformat()})",
                )
            )
        else:
            issues.append(
                Issue(
                    "FAIL",
                    f"L{i} {exp}: 发版戳后正式行空格 "
                    f"({row_d.isoformat()} >= {since.isoformat()})",
                )
            )
    return issues


def check_e_feedback_file(path: Path) -> list[Issue]:
    if not path.is_file():
        return []
    issues: list[Issue] = []
    text = path.read_text(encoding="utf-8")
    for n, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            issues.append(Issue("FAIL", f"e_feedback.jsonl L{n}: 坏 JSON ({e})"))
            continue
        if not isinstance(obj, dict):
            issues.append(Issue("FAIL", f"e_feedback.jsonl L{n}: 须为 object"))
            continue
        missing = [k for k in ("id", "kind") if k not in obj]
        res = obj.get("resolution")
        if not isinstance(res, dict) or "status" not in res:
            missing.append("resolution.status")
        if missing:
            issues.append(
                Issue(
                    "FAIL",
                    f"e_feedback.jsonl L{n}: 缺字段 {','.join(missing)}",
                )
            )
    return issues


def aggregate_severity(issues: list[Issue]) -> str:
    if any(i.severity == "FAIL" for i in issues):
        return "FAIL"
    if any(i.severity == "WARN" for i in issues):
        return "WARN"
    return "PASS"


def collect_issues(repo_root: Path) -> list[Issue]:
    issues: list[Issue] = []
    since = parse_since_date(repo_root / ".auto-nn" / "exploration-stamp-since")
    tsv = repo_root / "_runs" / "results.tsv"
    if tsv.is_file():
        with tsv.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f, delimiter="\t")
            rows = list(reader)
        if reader.fieldnames and "exploration_space" in reader.fieldnames:
            issues.extend(check_tsv_rows(rows, since=since))
        # 无 exploration_space 列 → 不报（旧表头由其他 doctor 项管）
    issues.extend(check_e_feedback_file(repo_root / "_runs" / "analysis" / "e_feedback.jsonl"))
    return issues


def format_report(issues: list[Issue]) -> str:
    sev = aggregate_severity(issues)
    if sev == "PASS":
        return "PASS: exploration_space 格子合规且 e_feedback schema OK（或无文件）"
    n_fail = sum(1 for i in issues if i.severity == "FAIL")
    n_warn = sum(1 for i in issues if i.severity == "WARN")
    head = f"{sev}: exploration_space/e_feedback 问题 FAIL={n_fail} WARN={n_warn}"
    # 详情放后续行；doctor 用整段 stdout 做 FAIL:* / WARN:* 前缀匹配
    detail_lines = [f"  [{i.severity}] {i.message}" for i in issues[:20]]
    if len(issues) > 20:
        detail_lines.append(f"  ... 共 {len(issues)} 条")
    return "\n".join([head, *detail_lines])


def unregistered_changed_keys(
    prev_cfg: dict[str, Any],
    run_cfg: dict[str, Any],
    catalog: dict[str, Any],
) -> list[str]:
    """相对上一 config 有变化、且不在 catalog 登记集合的键（排序）。"""
    primary = set((catalog.get("primary_keys") or {}).keys())
    scalar = {str(k) for k in (catalog.get("scalar_keys") or [])}
    ignore = {str(k) for k in (catalog.get("ignore_config_keys") or [])}
    registered = primary | scalar | ignore
    out: list[str] = []
    for key in sorted(set(prev_cfg) | set(run_cfg)):
        if prev_cfg.get(key) == run_cfg.get(key):
            continue
        if key not in registered:
            out.append(key)
    return out


def _load_config_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def collect_unregistered_issues(
    repo_root: Path,
    *,
    catalog: dict[str, Any] | None = None,
) -> list[Issue]:
    """最近两行已训 config 相对变化的未登记键 → WARN；缺数据/catalog → 空（PASS）。"""
    root = Path(repo_root)
    if catalog is None:
        try:
            from lib.innovation_fingerprint import load_innovation_catalog
        except ImportError:
            return []
        catalog = load_innovation_catalog(root) or load_innovation_catalog(None) or {}
    if not catalog:
        return []

    try:
        from lib.exploration_stamp import (
            is_trained_row,
            prev_trained_exp_dir,
        )
    except ImportError:
        return []

    tsv = root / "_runs" / "results.tsv"
    if not tsv.is_file():
        return []

    with tsv.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    if not rows:
        return []

    trained: list[dict[str, str]] = [
        r for r in rows if is_trained_row(r, metric_key="")
    ]
    if len(trained) < 2:
        return []

    cur_row = trained[-1]
    cur_raw = (cur_row.get("exp_dir") or "").strip()
    if not cur_raw:
        return []
    cur_dir = Path(cur_raw)
    if not cur_dir.is_absolute():
        cur_dir = (root / cur_dir).resolve()
    else:
        cur_dir = cur_dir.resolve()

    scenario = (cur_row.get("scenario_id") or "").strip()
    prev_dir = prev_trained_exp_dir(
        root,
        scenario_id=scenario,
        before_exp_dir=cur_dir,
        metric_key="",
    )
    if prev_dir is None:
        # 同场景无上一行：退化为全局倒数第二已训行
        prev_raw = (trained[-2].get("exp_dir") or "").strip()
        if not prev_raw:
            return []
        prev_dir = Path(prev_raw)
        if not prev_dir.is_absolute():
            prev_dir = (root / prev_dir).resolve()
        else:
            prev_dir = prev_dir.resolve()

    prev_cfg = _load_config_json(prev_dir / "config.json")
    run_cfg = _load_config_json(cur_dir / "config.json")
    if not prev_cfg or not run_cfg:
        return []

    keys = unregistered_changed_keys(prev_cfg, run_cfg, catalog)
    if not keys:
        return []
    return [
        Issue(
            "WARN",
            f"未登记配置键变化（相对上一已训行）: {', '.join(keys)}",
        )
    ]


def format_unregistered_report(issues: list[Issue]) -> str:
    sev = aggregate_severity(issues)
    if sev == "PASS":
        return "PASS: 无未登记配置键变化（或缺对照/catalog，跳过）"
    n_warn = sum(1 for i in issues if i.severity == "WARN")
    head = f"WARN: 未登记配置键 WARN={n_warn}"
    detail_lines = [f"  [{i.severity}] {i.message}" for i in issues[:20]]
    return "\n".join([head, *detail_lines])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repo-root", type=Path, default=Path.cwd(), help="业务仓根 (默认 cwd)")
    p.add_argument(
        "--check",
        action="store_true",
        help="只读检查模式: 首行 PASS:/WARN:/FAIL: 供 nn-doctor exploration_space_stamp",
    )
    p.add_argument(
        "--check-unregistered",
        action="store_true",
        help="未登记配置键检查: 首行 PASS:/WARN: 供 nn-doctor unregistered_config_keys",
    )
    args = p.parse_args(argv)
    root = args.repo_root.resolve()

    if args.check_unregistered:
        ureg = collect_unregistered_issues(root)
        print(format_unregistered_report(ureg))
        return 0

    issues = collect_issues(root)
    report = format_report(issues)
    if args.check:
        print(report)
        return 0

    # 非 --check：同样打印报告（便于人手跑）
    print(report)
    return 0 if aggregate_severity(issues) != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
