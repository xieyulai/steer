"""Reflect 认知锚：metric_leader（TSV 最优）与 code_baseline（keepers diff 基线）。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lib.run_ledger_summary import (
    _best_row_for_scenario,
    _float_cell,
    best_tsv_row,
    load_keepers,
    metric_direction,
    metric_key,
)


@dataclass
class MetricLeaderRow:
    scenario_id: str
    experiment: str
    exp_dir: str
    metric_key: str
    metric_value: float
    row: dict[str, str]


@dataclass
class CodeBaselineEntry:
    scenario_id: str
    experiment: str
    keeper_exp_dir: str
    git_commit: str
    updated_at: str


def focus_scenario_id(repo_root: Path) -> str:
    root = repo_root.resolve()
    scripts = root / "scripts"
    import sys

    scripts_str = str(scripts.resolve())
    if scripts.is_dir() and scripts_str not in sys.path:
        sys.path.insert(0, scripts_str)
    try:
        from lib.scenario_inventory import focus_scenario_id as _focus  # noqa: WPS433

        sid = (_focus(root) or "").strip()
        if sid:
            return sid
    except ImportError:
        pass
    p = root / "nn-config.yaml"
    if p.is_file():
        try:
            import yaml

            raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            sid = str((raw.get("agent") or {}).get("scenario_default") or "").strip()
            if sid:
                return sid
        except Exception:
            pass
    return "default"


def metric_leader_row(repo_root: Path, scenario_id: str | None = None) -> MetricLeaderRow | None:
    root = repo_root.resolve()
    sid = (scenario_id or focus_scenario_id(root)).strip() or "default"
    mk = metric_key(root)
    best = _best_row_for_scenario(root, sid, mk, metric_direction(root))
    if not best:
        return None
    val = _float_cell(best, mk)
    if val is None:
        return None
    exp_d = str(best.get("exp_dir") or "").strip()
    if not exp_d:
        return None
    return MetricLeaderRow(
        scenario_id=sid,
        experiment=str(best.get("experiment") or "?"),
        exp_dir=exp_d,
        metric_key=mk,
        metric_value=val,
        row=best,
    )


def code_baseline_entry(repo_root: Path, scenario_id: str | None = None) -> CodeBaselineEntry | None:
    root = repo_root.resolve()
    sid = (scenario_id or focus_scenario_id(root)).strip() or "default"
    entry = load_keepers(root).get(sid) or {}
    keeper_dir = str(entry.get("keeper_exp_dir") or "").strip()
    if not keeper_dir:
        return None
    return CodeBaselineEntry(
        scenario_id=sid,
        experiment=str(entry.get("experiment") or ""),
        keeper_exp_dir=keeper_dir,
        git_commit=str(entry.get("git_commit") or ""),
        updated_at=str(entry.get("updated_at") or ""),
    )


def format_leader_baseline_lines(repo_root: Path) -> list[str]:
    leader = metric_leader_row(repo_root)
    baseline = code_baseline_entry(repo_root)
    mk = metric_key(repo_root)
    explore_chain = False
    try:
        from lib.explore_objective import effective_objective  # noqa: WPS433

        res = effective_objective(repo_root)
        explore_chain = res.mode == "explore" and not res.migration_blocked
    except ImportError:
        pass
    lines: list[str] = []
    if leader:
        lines.append(
            f"metric_leader={leader.experiment} {mk}={leader.metric_value}"
        )
    else:
        # 撞墙信号：focus scenario 无 leader 时回落到 cross-scenario best，避免硬编码 (无)
        # （与 format_recent_ledger_window / format_brief 的 best_tsv_row fallback 同源）
        try:
            fallback = best_tsv_row(repo_root, mk, metric_direction(repo_root))
        except Exception:
            fallback = None
        if fallback:
            fv = _float_cell(fallback, mk)
            fexp = str(fallback.get("experiment") or "?")
            if fv is not None:
                lines.append(
                    f"metric_leader={fexp} {mk}={fv} (cross-scenario)"
                )
            else:
                lines.append("metric_leader=(无)")
        else:
            lines.append("metric_leader=(无)")
    if baseline:
        suffix = " (explore chain)" if explore_chain else ""
        lines.append(f"code_baseline={baseline.experiment or baseline.keeper_exp_dir}{suffix}")
    else:
        lines.append("code_baseline=(无)")
    if (
        leader
        and baseline
        and leader.exp_dir
        and leader.exp_dir == baseline.keeper_exp_dir
    ):
        return [f"leader=baseline={leader.experiment} {mk}={leader.metric_value}"]
    return lines


def anchors_dict(repo_root: Path) -> dict[str, Any]:
    leader = metric_leader_row(repo_root)
    baseline = code_baseline_entry(repo_root)
    out: dict[str, Any] = {}
    if leader:
        out["metric_leader"] = {
            "experiment": leader.experiment,
            "exp_dir": leader.exp_dir,
            "metric_key": leader.metric_key,
            "value": leader.metric_value,
        }
    if baseline:
        out["code_baseline"] = {
            "experiment": baseline.experiment,
            "exp_dir": baseline.keeper_exp_dir,
            "git_commit": baseline.git_commit,
        }
    return out


def is_baseline_role(role: str) -> bool:
    return role in ("keeper", "code_baseline")
