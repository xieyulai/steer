"""指标相对变化、better-than-best 判定与尾部 plateau streak（direction 语义）。"""
from __future__ import annotations

import ast
import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lib.ledger_anchor import code_baseline_entry, focus_scenario_id, metric_leader_row
from lib.nn_config import load_nn_config
from lib.baseline_anchors_status import (  # noqa: E402
    assess_baseline_anchors,
    format_baseline_anchors_markdown,
)
from lib.run_ledger_summary import (
    _best_row_for_scenario,
    _float_cell,
    _parse_contract_ast,
    _parse_metrics_module,
    _plateau_streak_for_scenario,
    _read_text,
    _try_load_contract,
    agent_config,
    best_tsv_row,
    format_goal_progress_line,
    format_goal_matrix_lines,
    should_show_goal_matrix,
    metric_direction,
    metric_key,
    tsv_rows,
)

EPS = 1e-12


def delta_pct(new: float, ref: float) -> float | None:
    """相对 ref 的百分比变化 ``(new-ref)/ref*100``；``ref==0`` 时返回 ``None``。"""
    if ref == 0:
        return None
    return (new - ref) / ref * 100.0


def beat_best(new: float, best: float, *, direction: str) -> bool:
    """是否严格优于历史 best（``minimize``：更小更好；``maximize``：更大更好）。"""
    if direction == "minimize":
        return new < best - EPS
    return new > best + EPS


def plateau_streak_from_vals(
    vals: list[float], plateau_n: int, *, direction: str
) -> int:
    """与 ``run_ledger_summary.plateau_streak`` 同源：窗口内全局 best，自尾部向回数连续「未达 best」次数。

    ``minimize``：更差为 ``v > best + EPS``；``maximize``：更差为 ``v < best - EPS``。
    """
    if len(vals) < plateau_n + 1:
        return 0
    finite = [v for v in vals if v == v]
    if not finite:
        return 0
    if direction == "minimize":
        best = min(finite)
    else:
        best = max(finite)
    streak = 0
    for v in reversed(vals):
        if v != v:
            continue
        if direction == "minimize":
            if v > best + EPS:
                streak += 1
            else:
                break
        else:
            if v < best - EPS:
                streak += 1
            else:
                break
    return streak


def metric_direction_for_column(repo_root: Path | str, column: str) -> str:
    """列级优化方向：主指标列用 ``metric_direction``；其余列优先 ``primary_metric_directions``（即 ``METRIC_KEYS``），否则同主方向。"""
    root = Path(repo_root).resolve()
    col = str(column).strip()
    pk = metric_key(root)
    primary = metric_direction(root)
    if col == pk:
        return primary
    c = _try_load_contract(root)
    if c is not None:
        pmd = getattr(c, "primary_metric_directions", None) or {}
        if col in pmd:
            return str(pmd[col])
    metric_keys_dict, _ = _parse_metrics_module(root)
    if col in metric_keys_dict:
        return str(metric_keys_dict[col])
    return primary


def _parse_ledger_context_keys_ast(repo_root: Path) -> tuple[str, ...]:
    """从 contract/__init__.py AST 解析 ``ledger_context_keys``。"""
    path = repo_root / "contract" / "__init__.py"
    if not path.is_file():
        return ()
    try:
        tree = ast.parse(_read_text(path))
    except SyntaxError:
        return ()
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if item.name != "ledger_context_keys":
                continue
            for sub in ast.walk(item):
                if isinstance(sub, ast.Return) and sub.value is not None and isinstance(
                    sub.value, (ast.Tuple, ast.List)
                ):
                    vals: list[str] = []
                    for elt in sub.value.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            vals.append(elt.value)
                    return tuple(vals)
    return ()


def _contract_aux_and_ledger(repo_root: Path) -> tuple[dict[str, str], tuple[str, ...]]:
    """返回 (auxiliary_keys, ledger_context_keys)。"""
    c = _try_load_contract(repo_root)
    if c is not None:
        aux = dict(getattr(c, "auxiliary_keys", {}) or {})
        ledger = tuple(getattr(c, "ledger_context_keys", ()) or ())
        return aux, ledger
    parsed = _parse_contract_ast(repo_root)
    aux = dict(parsed.get("auxiliary_keys") or {})
    return aux, _parse_ledger_context_keys_ast(repo_root)


def _previous_row_in_scenario(
    repo_root: Path, row: dict[str, str]
) -> dict[str, str] | None:
    sid = str(row.get("scenario_id") or "").strip() or "default"
    exp = str(row.get("experiment") or "").strip()
    scenario_rows = rows_for_scenario(repo_root, sid)
    for i, candidate in enumerate(scenario_rows):
        if str(candidate.get("experiment") or "").strip() == exp:
            return scenario_rows[i - 1] if i > 0 else None
    return None


def _load_last_recommendation(repo_root: Path) -> dict[str, Any] | None:
    p = repo_root / "saved" / "experiment_journal.json"
    if not p.is_file():
        return None
    try:
        data = json.loads(_read_text(p))
        rec = (data.get("analyse") or {}).get("last_recommendation")
        return rec if isinstance(rec, dict) and rec else None
    except Exception:
        return None


def _load_last_consumed_reflect(
    repo_root: Path,
) -> tuple[dict[str, Any] | None, list[str]]:
    """journal.reflect.last_consumed 优先；缺失时 fallback INDEX 历史首行。"""
    warnings: list[str] = []
    root = repo_root.resolve()
    try:
        from lib.experiment_journal import journal_path, read_journal  # noqa: WPS433

        journal = read_journal(journal_path(root))
        reflect = journal.get("reflect")
        if isinstance(reflect, dict):
            lc = reflect.get("last_consumed")
            if isinstance(lc, dict) and str(lc.get("reflect_id") or "").strip():
                return lc, warnings
    except Exception:
        pass

    index_path = root / "references" / "REFLECT_INDEX.md"
    if not index_path.is_file():
        return None, warnings
    text = index_path.read_text(encoding="utf-8")
    import re

    m = re.search(r"##\s*历史[^\n]*\n(.*)", text, re.DOTALL | re.I)
    if not m:
        return None, warnings
    placeholders = frozenset({"（无）", "—", "-", "", "id", "（尚无）"})
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 4 and cells[0] not in placeholders:
            warnings.append(
                "WARN: MA-R fallback to INDEX history (no journal.reflect.last_consumed)"
            )
            tier_hint = ""
            suggest = cells[3]
            tm = re.search(r"Tier\s*([A-E])", suggest, re.I)
            if tm:
                tier_hint = tm.group(1).upper()
            return {
                "reflect_id": cells[0],
                "wall_short": cells[2] if len(cells) > 2 else "",
                "suggest_one_liner": suggest,
                "tier_hint": tier_hint,
                "consume_summary": cells[4] if len(cells) > 4 else "",
            }, warnings
    return None, warnings


def _row_matches_tier_hint(row: dict[str, str], tier_hint: str) -> bool:
    hint = str(tier_hint or "").strip().upper()
    if not hint or hint not in "ABCDE":
        return False
    hay = " ".join(
        [
            str(row.get("description") or ""),
            str(row.get("notes") or ""),
            str(row.get("experiment") or ""),
            str(row.get("tier_this_round") or ""),
        ]
    )
    patterns = (f"Tier {hint}", f"tier {hint.lower()}", f"Tier{hint}")
    return any(p in hay for p in patterns)


def _ma_r_candidate_rows(
    repo_root: Path,
    *,
    incr_rows: list[dict[str, str]] | None,
    since_analyse: bool,
) -> list[dict[str, str]]:
    root = repo_root.resolve()
    if incr_rows is not None:
        rows = incr_rows
    elif since_analyse:
        rows, full_mode, _ = _incremental_rows(root, since_analyse=True)
        if full_mode:
            focus = focus_scenario_id(root) or "default"
            scenario_rows = rows_for_scenario(root, focus)
            return scenario_rows[-1:] if scenario_rows else []
    else:
        focus = focus_scenario_id(root) or "default"
        scenario_rows = rows_for_scenario(root, focus)
        return scenario_rows[-1:] if scenario_rows else []
    return rows


def _metric_verdict(
    new: float | None,
    ref: float | None,
    *,
    direction: str,
    flat_pct: float,
) -> str:
    if new is None or ref is None:
        return "inconclusive"
    d_pct = delta_pct(new, ref)
    if d_pct is not None and abs(d_pct) <= flat_pct:
        return "flat"
    if direction == "minimize":
        if new < ref - EPS:
            return "improved"
        if new > ref + EPS:
            return "regressed"
        return "flat"
    if new > ref + EPS:
        return "improved"
    if new < ref - EPS:
        return "regressed"
    return "flat"


def _row_matches_recommendation(
    row: dict[str, str],
    prev_row: dict[str, str] | None,
    rec: dict[str, Any],
    ledger_keys: tuple[str, ...],
) -> bool:
    sv = str(rec.get("single_variable") or "").strip()
    if not sv:
        return True
    if sv in ledger_keys:
        if prev_row is None:
            return False
        return str(prev_row.get(sv, "")).strip() != str(row.get(sv, "")).strip()
    sv_base = Path(sv).name if ("/" in sv or "\\" in sv) else sv
    hay = " ".join(
        [
            str(row.get("notes") or ""),
            str(row.get("description") or ""),
            str(row.get("experiment") or ""),
        ]
    ).lower()
    return sv_base.lower() in hay or sv.lower() in hay


def analyse_agent_config(repo_root: Path | str) -> dict[str, Any]:
    """读取 analyse 顶层段 + agent.plateau_rounds。"""
    root = Path(repo_root).resolve()
    out: dict[str, Any] = {
        "analyse_recent_rows": 10,
        "analyse_aux_max": 5,
        "analyse_flat_pct": 0.5,
        "analyse_noise_std_hint": None,
    }
    plateau_n, _ = agent_config(root)
    out["plateau_rounds"] = plateau_n
    cfg_path = root / "nn-config.yaml"
    if not cfg_path.is_file():
        return out
    try:
        cfg = load_nn_config(root)
        analyse = cfg.get("analyse") if isinstance(cfg.get("analyse"), dict) else {}
        if "recent_rows" in analyse:
            out["analyse_recent_rows"] = int(analyse["recent_rows"])
        if "aux_max" in analyse:
            out["analyse_aux_max"] = int(analyse["aux_max"])
        if "flat_pct" in analyse:
            out["analyse_flat_pct"] = float(analyse["flat_pct"])
        if "noise_std_hint" in analyse:
            hint = analyse["noise_std_hint"]
            out["analyse_noise_std_hint"] = None if hint is None else float(hint)
        agent = cfg.get("agent") or {}
        if "plateau_rounds" in agent:
            out["plateau_rounds"] = int(agent["plateau_rounds"])
    except Exception:
        pass
    return out


def _data_rows(repo_root: Path) -> list[dict[str, str]]:
    return [r for r in tsv_rows(repo_root) if r.get("experiment") != "preflight_check"]


def _tsv_has_scenario_id(repo_root: Path) -> bool:
    p = repo_root / "_runs" / "results.tsv"
    if not p.is_file():
        return False
    lines = [ln for ln in _read_text(p).splitlines() if ln.strip()]
    if not lines:
        return False
    return "scenario_id" in lines[0].split("\t")


def rows_for_scenario(repo_root: Path, scenario_id: str) -> list[dict[str, str]]:
    """focus 场景对应 TSV 行；无 ``scenario_id`` 列时 ``default`` 视为全表。"""
    sid = (scenario_id or "").strip() or "default"
    rows = _data_rows(repo_root)
    if not rows:
        return []
    if not _tsv_has_scenario_id(repo_root):
        return rows if sid == "default" else []
    return [r for r in rows if str(r.get("scenario_id", "")).strip() == sid]


def _format_delta_pair(new: float, ref: float) -> str:
    d_abs = new - ref
    d_pct = delta_pct(new, ref)
    pct_s = "n/a" if d_pct is None else f"{d_pct:+.2f}%"
    return f"Δ={d_abs:+.6g} Δ%={pct_s}"


def _format_metric_value(v: float | None) -> str:
    if v is None:
        return "(无)"
    return f"{v:.6g}"


def _row_decision(row: dict[str, str]) -> str:
    notes = str(row.get("notes") or "").strip()
    if notes:
        return notes
    decision = str(row.get("decision") or row.get("round_decision") or "").strip()
    return decision or "-"


def _keeper_tsv_row(repo_root: Path, scenario_id: str) -> dict[str, str] | None:
    baseline = code_baseline_entry(repo_root, scenario_id)
    if not baseline or not baseline.experiment:
        return None
    exp = baseline.experiment.strip()
    for row in rows_for_scenario(repo_root, scenario_id):
        if str(row.get("experiment") or "").strip() == exp:
            return row
    return None


def _load_analyse_cursor(repo_root: Path) -> int | None:
    from lib.experiment_journal import load_analyse_cursor  # noqa: WPS433

    return load_analyse_cursor(repo_root)


def _incremental_rows(
    repo_root: Path, *, since_analyse: bool
) -> tuple[list[dict[str, str]], bool, list[str]]:
    """返回 (增量行, 是否全量模式, stderr 警告)。"""
    warnings: list[str] = []
    all_rows = _data_rows(repo_root)
    if not since_analyse:
        return all_rows, True, warnings
    cursor = _load_analyse_cursor(repo_root)
    if cursor is None:
        warnings.append("WARN: MA-3 全量模式（无 journal 游标）")
        return all_rows, True, warnings
    if cursor < 0:
        cursor = 0
    if cursor >= len(all_rows):
        return [], False, warnings
    return all_rows[cursor:], False, warnings


def _group_rows_by_scenario(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    has_sid = bool(rows) and any(str(r.get("scenario_id", "")).strip() for r in rows)
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        sid = str(row.get("scenario_id") or "").strip() if has_sid else "default"
        if not sid:
            sid = "default"
        grouped.setdefault(sid, []).append(row)
    return grouped


def _leader_for_analyse(
    repo_root: Path, scenario_id: str
) -> tuple[str, float | None, dict[str, str] | None]:
    """MA-1 leader：优先 ``metric_leader_row``，无 exp_dir 时回落 focus-scenario best，
    仍空时回落 cross-scenario best（与 format_recent_ledger_window / format_brief 同源）。
    """
    leader = metric_leader_row(repo_root, scenario_id)
    if leader is not None:
        return leader.experiment, leader.metric_value, leader.row
    mk = metric_key(repo_root)
    direction = metric_direction(repo_root)
    best = _best_row_for_scenario(repo_root, scenario_id, mk, direction)
    if best:
        v = _float_cell(best, mk)
        if v is not None:
            return str(best.get("experiment") or "?"), v, best
    # 撞墙信号：focus scenario 无数据时回落到 cross-scenario best
    try:
        cross = best_tsv_row(repo_root, mk, direction)
    except Exception:
        cross = None
    if cross:
        cv = _float_cell(cross, mk)
        if cv is not None:
            return str(cross.get("experiment") or "?"), cv, cross
    return "", None, None


def format_ma1_brief_oneline(repo_root: Path | str) -> str:
    """MA-1 一行摘要：leader / last / Δ% / plateau（供 Run Context 注入）。"""
    root = Path(repo_root).resolve()
    focus = focus_scenario_id(root) or "default"
    mk = metric_key(root)
    leader_exp, leader_v, _ = _leader_for_analyse(root, focus)
    scenario_rows = rows_for_scenario(root, focus)
    last_row = scenario_rows[-1] if scenario_rows else None
    last_exp = str(last_row.get("experiment") or "?") if last_row else "?"
    last_v = _float_cell(last_row or {}, mk) if last_row else None

    cfg = analyse_agent_config(root)
    plateau_n = int(cfg["plateau_rounds"])
    ps = _plateau_streak_for_scenario(root, focus, plateau_n, mk)

    parts: list[str] = []
    if leader_v is not None:
        parts.append(f"leader={leader_exp} {mk}={_format_metric_value(leader_v)}")
    else:
        parts.append("leader=(无)")

    if last_v is not None:
        delta_part = ""
        if leader_v is not None:
            d_pct = delta_pct(last_v, leader_v)
            pct_s = "n/a" if d_pct is None else f"{d_pct:+.2f}%"
            delta_part = f" Δ%={pct_s}"
        parts.append(f"last={last_exp} {mk}={_format_metric_value(last_v)}{delta_part}")
    else:
        parts.append("last=(无)")

    parts.append(f"plateau={ps}/{plateau_n}")
    return " | ".join(parts)


def section_ma1(repo_root: Path) -> list[str]:
    """MA-1 锚点对比。"""
    root = repo_root.resolve()
    focus = focus_scenario_id(root) or "default"
    mk = metric_key(root)
    direction = metric_direction(root)
    leader_exp, leader_v, leader_row = _leader_for_analyse(root, focus)
    keeper_row = _keeper_tsv_row(root, focus)
    scenario_rows = rows_for_scenario(root, focus)
    last_row = scenario_rows[-1] if scenario_rows else None

    keeper_v = _float_cell(keeper_row or {}, mk) if keeper_row else None
    last_v = _float_cell(last_row or {}, mk) if last_row else None

    lines = [
        f"focus={focus} metric={mk} direction={direction}",
    ]

    baseline = code_baseline_entry(root, focus)
    leader_exp_dir = str((leader_row or {}).get("exp_dir") or "").strip()
    merged = (
        leader_v is not None
        and baseline is not None
        and leader_exp_dir
        and leader_exp_dir == baseline.keeper_exp_dir
    )
    if merged:
        lines.append(
            f"leader=baseline={leader_exp} {mk}={_format_metric_value(leader_v)}"
        )
    else:
        if leader_v is not None:
            lines.append(
                f"leader={leader_exp} {mk}={_format_metric_value(leader_v)}"
            )
        else:
            lines.append("leader=(无)")
        if keeper_row and keeper_v is not None:
            keeper_exp = str(keeper_row.get("experiment") or baseline.experiment if baseline else "?")
            if leader_v is not None:
                lines.append(
                    f"keeper={keeper_exp} {mk}={_format_metric_value(keeper_v)} "
                    f"{_format_delta_pair(keeper_v, leader_v)}"
                )
            else:
                lines.append(
                    f"keeper={keeper_exp} {mk}={_format_metric_value(keeper_v)}"
                )
        else:
            lines.append("keeper=(无)")

    if last_row and last_v is not None:
        last_exp = str(last_row.get("experiment") or "?")
        if leader_v is not None:
            lines.append(
                f"last={last_exp} {mk}={_format_metric_value(last_v)} "
                f"{_format_delta_pair(last_v, leader_v)}"
            )
        else:
            lines.append(f"last={last_exp} {mk}={_format_metric_value(last_v)}")
    else:
        lines.append("last=(无)")

    goal_line = format_goal_progress_line(root)
    if goal_line:
        lines.append(goal_line)
    if should_show_goal_matrix(root):
        matrix = format_goal_matrix_lines(root)
        if matrix:
            lines.append("goal matrix:")
            lines.extend(matrix)

    return lines


def section_ma2(repo_root: Path) -> tuple[list[str], list[dict[str, str]]]:
    """MA-2 最近 K 轮；返回 (markdown 行, 行数据)。"""
    root = repo_root.resolve()
    cfg = analyse_agent_config(root)
    k = int(cfg["analyse_recent_rows"])
    focus = focus_scenario_id(root) or "default"
    mk = metric_key(root)
    direction = metric_direction(root)
    scenario_rows = rows_for_scenario(root, focus)
    recent = scenario_rows[-k:] if k > 0 else scenario_rows

    best_row = _best_row_for_scenario(root, focus, mk, direction)
    best_v = _float_cell(best_row or {}, mk)

    lines = [f"focus={focus} recent={len(recent)}"]
    table_rows: list[dict[str, str]] = []
    if not recent:
        lines.append("(无数据行)")
        return lines, table_rows

    lines.append("| experiment | metric | Δ_vs_best | decision |")
    lines.append("| --- | --- | --- | --- |")
    for row in recent:
        exp = str(row.get("experiment") or "?")
        v = _float_cell(row, mk)
        metric_s = _format_metric_value(v)
        if v is not None and best_v is not None:
            delta_best = f"{v - best_v:+.6g}"
        else:
            delta_best = "-"
        decision = _row_decision(row)
        lines.append(f"| {exp} | {metric_s} | {delta_best} | {decision} |")
        table_rows.append(
            {
                "experiment": exp,
                "metric": metric_s,
                "delta_vs_best": delta_best,
                "decision": decision,
            }
        )
    return lines, table_rows


def section_ma3(
    repo_root: Path, *, since_analyse: bool, full_mode: bool
) -> tuple[list[str], list[dict[str, Any]]]:
    """MA-3 增量数值。"""
    root = repo_root.resolve()
    mk = metric_key(root)
    direction = metric_direction(root)
    incr_rows, _, _ = _incremental_rows(root, since_analyse=since_analyse)
    grouped = _group_rows_by_scenario(incr_rows)

    title_suffix = " — 全量" if full_mode else ""
    lines = [f"rows={len(incr_rows)}{title_suffix}"]

    if not incr_rows:
        lines.append("(无增量行)")
        return lines, []

    detail_rows: list[dict[str, Any]] = []
    for sid in sorted(grouped.keys()):
        rows = grouped[sid]
        prior_in_scenario = rows_for_scenario(root, sid)
        prior_count = len(prior_in_scenario) - len(rows)
        running_best: float | None = None
        if prior_count > 0:
            for prev in prior_in_scenario[:prior_count]:
                v = _float_cell(prev, mk)
                if v is None:
                    continue
                if running_best is None:
                    running_best = v
                elif beat_best(v, running_best, direction=direction):
                    running_best = v

        lines.append(f"#### scenario={sid}")
        lines.append("| experiment | metric | beat_best | Δ_prev |")
        lines.append("| --- | --- | --- | --- |")
        prev_v: float | None = None
        if prior_count > 0:
            prev_v = _float_cell(prior_in_scenario[prior_count - 1], mk)

        for row in rows:
            exp = str(row.get("experiment") or "?")
            v = _float_cell(row, mk)
            metric_s = _format_metric_value(v)
            if v is not None and running_best is not None:
                beat = "yes" if beat_best(v, running_best, direction=direction) else "no"
                if beat:
                    running_best = v
            elif v is not None and running_best is None:
                beat = "yes"
                running_best = v
            else:
                beat = "-"
            if v is not None and prev_v is not None:
                delta_prev = f"{v - prev_v:+.6g}"
            else:
                delta_prev = "-"
            if v is not None:
                prev_v = v
            lines.append(f"| {exp} | {metric_s} | {beat} | {delta_prev} |")
            detail_rows.append(
                {
                    "scenario_id": sid,
                    "experiment": exp,
                    "metric": metric_s,
                    "beat_best": beat,
                    "delta_prev": delta_prev,
                }
            )
    return lines, detail_rows


def _ma4_panel_columns(repo_root: Path) -> list[tuple[str, str]]:
    """主指标 + auxiliary 前 N 列，附带 direction。"""
    root = repo_root.resolve()
    cfg = analyse_agent_config(root)
    aux_max = int(cfg["analyse_aux_max"])
    mk = metric_key(root)
    aux, _ = _contract_aux_and_ledger(root)
    cols: list[tuple[str, str]] = [(mk, metric_direction_for_column(root, mk))]
    for col in list(aux.keys())[:aux_max]:
        cols.append((col, metric_direction_for_column(root, col)))
    return cols


def section_ma4(
    repo_root: Path,
    *,
    since_analyse: bool,
    full_mode: bool,
    incr_rows: list[dict[str, str]],
    ma2_rows_data: list[dict[str, str]],
) -> tuple[list[str], list[dict[str, Any]]]:
    """MA-4 多指标面板（主指标 + auxiliary）。"""
    root = repo_root.resolve()
    aux, _ = _contract_aux_and_ledger(root)
    if not aux:
        return [], []

    panel_cols = _ma4_panel_columns(root)
    if len(panel_cols) <= 1:
        return [], []

    focus = focus_scenario_id(root) or "default"
    if since_analyse and not full_mode and incr_rows:
        source_label = "incremental"
        source_rows = incr_rows
    else:
        source_label = "recent"
        scenario_rows = rows_for_scenario(root, focus)
        k = int(analyse_agent_config(root)["analyse_recent_rows"])
        source_rows = scenario_rows[-k:] if k > 0 else scenario_rows

    lines = [f"source={source_label} rows={len(source_rows)}"]
    if not source_rows:
        lines.append("(无数据行)")
        return lines, []

    hdr_cells = ["experiment"] + [f"{col} ({direction})" for col, direction in panel_cols]
    lines.append("| " + " | ".join(hdr_cells) + " |")
    lines.append("| " + " | ".join(["---"] * len(hdr_cells)) + " |")

    detail_rows: list[dict[str, Any]] = []
    for row in source_rows:
        exp = str(row.get("experiment") or "?")
        cells = [exp]
        row_detail: dict[str, Any] = {"experiment": exp}
        for col, direction in panel_cols:
            v = _float_cell(row, col)
            cells.append(_format_metric_value(v))
            row_detail[col] = {"value": v, "direction": direction}
        lines.append("| " + " | ".join(cells) + " |")
        detail_rows.append(row_detail)
    return lines, detail_rows


def section_ma5(
    repo_root: Path, incr_rows: list[dict[str, str]]
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    """MA-5 变更归因；``ledger_context_keys`` 为空时仅返回 skip 警告。"""
    root = repo_root.resolve()
    _, ledger_keys = _contract_aux_and_ledger(root)
    if not ledger_keys:
        return [], ["MA-5 skip: no ledger_context_keys"], []

    lines: list[str] = []
    detail_rows: list[dict[str, Any]] = []
    if not incr_rows:
        lines.append("(无增量行)")
        return lines, [], detail_rows

    for row in incr_rows:
        prev = _previous_row_in_scenario(root, row)
        if prev is None:
            continue
        exp = str(row.get("experiment") or "?")
        changes: list[str] = []
        change_map: dict[str, str] = {}
        for key in ledger_keys:
            old = str(prev.get(key, "")).strip()
            new = str(row.get(key, "")).strip()
            if old != new:
                change_s = f"{key}: {old}→{new}"
                changes.append(change_s)
                change_map[key] = f"{old}→{new}"
        if changes:
            lines.append(f"{exp}: " + "; ".join(changes))
            detail_rows.append(
                {
                    "experiment": exp,
                    "changes": change_map,
                }
            )
    if not lines:
        lines.append("(无 ledger 列变更)")
    return lines, [], detail_rows


def verify_recommendation(
    repo_root: Path | str,
    *,
    incr_rows: list[dict[str, str]] | None = None,
    since_analyse: bool = False,
) -> tuple[list[str], list[str], dict[str, Any] | None]:
    """MA-6：对照 ``journal.analyse.last_recommendation`` 验证增量实验。"""
    root = Path(repo_root).resolve()
    rec = _load_last_recommendation(root)
    if rec is None:
        return [], ["MA-6 skip: no prior recommendation"], None

    if incr_rows is None:
        incr_rows, _, _ = _incremental_rows(root, since_analyse=since_analyse)

    cfg = analyse_agent_config(root)
    flat_pct = float(cfg["analyse_flat_pct"])
    mk = metric_key(root)
    direction = metric_direction(root)
    _, ledger_keys = _contract_aux_and_ledger(root)

    summary = str(rec.get("summary") or rec.get("single_variable") or "?").strip()
    tier = str(rec.get("tier_hint") or "").strip()
    rec_header = f"last_recommendation: {summary}"
    if tier:
        rec_header += f" (tier={tier})"

    lines: list[str] = []
    verdicts: list[dict[str, Any]] = []

    if not incr_rows:
        lines.append(f"{rec_header} → verdict: inconclusive (无增量行)")
        return lines, [], {"recommendation": rec, "verdicts": verdicts}

    for row in incr_rows:
        prev = _previous_row_in_scenario(root, row)
        if not _row_matches_recommendation(row, prev, rec, ledger_keys):
            continue
        exp = str(row.get("experiment") or "?")
        new_v = _float_cell(row, mk)
        ref_v = _float_cell(prev or {}, mk) if prev else None
        verdict = _metric_verdict(new_v, ref_v, direction=direction, flat_pct=flat_pct)
        detail = (
            f"metric {mk}={_format_metric_value(ref_v)}→{_format_metric_value(new_v)}"
        )
        if new_v is not None and ref_v is not None:
            d_pct = delta_pct(new_v, ref_v)
            if d_pct is not None:
                detail += f" Δ%={d_pct:+.2f}%"
        lines.append(f"{rec_header} → {exp}: verdict: {verdict} ({detail})")
        verdicts.append(
            {
                "experiment": exp,
                "verdict": verdict,
                "metric": mk,
                "ref": ref_v,
                "new": new_v,
            }
        )

    if not lines:
        lines.append(f"{rec_header} → verdict: inconclusive (无匹配实验)")

    return lines, [], {"recommendation": rec, "verdicts": verdicts}


def verify_reflect_recommendation(
    repo_root: Path | str,
    *,
    incr_rows: list[dict[str, str]] | None = None,
    since_analyse: bool = False,
) -> tuple[list[str], list[str], dict[str, Any] | None]:
    """MA-R：对照 journal.reflect.last_consumed 验证增量实验 Tier 匹配。"""
    root = Path(repo_root).resolve()
    consumed, load_warnings = _load_last_consumed_reflect(root)
    if consumed is None:
        return [], ["MA-R skip: no consumed reflect", *load_warnings], None

    rows = _ma_r_candidate_rows(root, incr_rows=incr_rows, since_analyse=since_analyse)
    cfg = analyse_agent_config(root)
    flat_pct = float(cfg["analyse_flat_pct"])
    mk = metric_key(root)
    direction = metric_direction(root)
    _, ledger_keys = _contract_aux_and_ledger(root)

    rid = str(consumed.get("reflect_id") or "?").strip()
    suggest = str(consumed.get("suggest_one_liner") or "").strip()
    tier = str(consumed.get("tier_hint") or "").strip()
    header = f"last_consumed: {rid}"
    if suggest:
        header += f" — {_truncate_ma_header(suggest)}"
    if tier:
        header += f" (tier={tier})"

    lines: list[str] = []
    verdicts: list[dict[str, Any]] = []

    if not rows:
        lines.append(f"{header} → verdict: inconclusive (无增量行)")
        return lines, load_warnings, {"last_consumed": consumed, "verdicts": verdicts}

    matched = False
    for row in rows:
        if not _row_matches_tier_hint(row, tier):
            continue
        matched = True
        prev = _previous_row_in_scenario(root, row)
        exp = str(row.get("experiment") or "?")
        new_v = _float_cell(row, mk)
        ref_v = _float_cell(prev or {}, mk) if prev else None
        verdict = _metric_verdict(new_v, ref_v, direction=direction, flat_pct=flat_pct)
        detail = (
            f"metric {mk}={_format_metric_value(ref_v)}→{_format_metric_value(new_v)}"
        )
        if new_v is not None and ref_v is not None:
            d_pct = delta_pct(new_v, ref_v)
            if d_pct is not None:
                detail += f" Δ%={d_pct:+.2f}%"
        tag = ""
        if ledger_keys and prev is not None:
            for key in ledger_keys:
                if str(prev.get(key, "")).strip() != str(row.get(key, "")).strip():
                    tag = " [有单变量变更]"
                    break
        lines.append(f"{header} → {exp}: verdict: {verdict} ({detail}){tag}")
        verdicts.append(
            {
                "experiment": exp,
                "verdict": verdict,
                "metric": mk,
                "ref": ref_v,
                "new": new_v,
            }
        )

    if not matched:
        lines.append(f"{header} → verdict: inconclusive (无 Tier 匹配实验)")

    return lines, load_warnings, {"last_consumed": consumed, "verdicts": verdicts}


def _truncate_ma_header(text: str, max_chars: int = 60) -> str:
    t = text.strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"


def section_ma7(repo_root: Path) -> tuple[list[str], dict[str, Any]]:
    """MA-7 plateau + 可选噪声提示。"""
    root = repo_root.resolve()
    cfg = analyse_agent_config(root)
    plateau_n = int(cfg["plateau_rounds"])
    focus = focus_scenario_id(root) or "default"
    mk = metric_key(root)
    ps = _plateau_streak_for_scenario(root, focus, plateau_n, mk)

    scenario_rows = rows_for_scenario(root, focus)
    recent_vals: list[float] = []
    for row in scenario_rows[-max(plateau_n + 2, 8) :]:
        v = _float_cell(row, mk)
        if v is not None:
            recent_vals.append(v)

    std_val: float | None = None
    if len(recent_vals) >= 2:
        std_val = statistics.pstdev(recent_vals)

    std_s = f"{std_val:.6g}" if std_val is not None else "n/a"
    lines = [f"focus={focus} plateau={ps}/{plateau_n} std={std_s}"]

    hint = cfg.get("analyse_noise_std_hint")
    if hint is not None and std_val is not None and std_val > float(hint):
        lines.append(f"INFO: 高噪声（std={std_s} > hint={hint}），慎判 plateau")

    meta = {
        "focus": focus,
        "plateau_streak": ps,
        "plateau_rounds": plateau_n,
        "std": std_val,
        "high_noise": bool(
            hint is not None and std_val is not None and std_val > float(hint)
        ),
    }
    return lines, meta


@dataclass
class AnalyseMetricsReport:
    markdown: str
    warnings: list[str] = field(default_factory=list)
    sections: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "warnings": self.warnings,
            "sections": self.sections,
            "markdown": self.markdown,
        }


def warn_aux_metrics_always_zero(
    repo_root: Path | str, *, min_rows: int = 3
) -> list[str]:
    """辅指标在最近若干行恒为 0 → WARN（不 FAIL；合法真 0 可能误报，仅提示未接线）。"""
    root = Path(repo_root).resolve()
    aux, _ = _contract_aux_and_ledger(root)
    if not aux:
        return []
    focus = focus_scenario_id(root) or "default"
    rows = rows_for_scenario(root, focus)
    if len(rows) < min_rows:
        return []
    window = rows[-min_rows:]
    warnings: list[str] = []
    for col in aux:
        vals: list[float] = []
        ok = True
        for row in window:
            v = _float_cell(row, col)
            if v is None or v != v:
                ok = False
                break
            vals.append(float(v))
        if not ok or len(vals) < min_rows:
            continue
        if all(abs(v) <= EPS for v in vals):
            warnings.append(
                f"WARN: 辅指标 {col!r} 近 {min_rows} 轮均为 0——"
                "若本应反映遗忘/迁移等，请检查是否未接入真值（合法恒零可忽略）"
            )
    return warnings


def build_analyse_report(
    repo_root: Path | str, *, since_analyse: bool = False, quiet: bool = False
) -> AnalyseMetricsReport:
    """构建 MA-1～MA-7 报告（markdown + 结构化 sections + stderr 警告）。"""
    root = Path(repo_root).resolve()
    warnings: list[str] = []
    incr_rows, full_mode, incr_warnings = _incremental_rows(root, since_analyse=since_analyse)
    if not quiet:
        warnings.extend(incr_warnings)
    if not quiet:
        warnings.extend(warn_aux_metrics_always_zero(root))

    ma1_lines = section_ma1(root)
    ma2_lines, ma2_rows = section_ma2(root)
    ma3_lines, ma3_rows = section_ma3(root, since_analyse=since_analyse, full_mode=full_mode)
    ma4_lines, ma4_rows = section_ma4(
        root,
        since_analyse=since_analyse,
        full_mode=full_mode,
        incr_rows=incr_rows,
        ma2_rows_data=ma2_rows,
    )
    ma5_lines, ma5_warnings, ma5_rows = section_ma5(root, incr_rows)
    if not quiet:
        warnings.extend(ma5_warnings)
    ma6_lines, ma6_warnings, ma6_meta = verify_recommendation(
        root, incr_rows=incr_rows, since_analyse=since_analyse
    )
    if not quiet:
        warnings.extend(ma6_warnings)
    ma_r_lines, ma_r_warnings, ma_r_meta = verify_reflect_recommendation(
        root, incr_rows=incr_rows, since_analyse=since_analyse
    )
    warnings.extend(ma_r_warnings)
    ma7_lines, ma7_meta = section_ma7(root)

    ba_status = assess_baseline_anchors(root)
    ba_md = format_baseline_anchors_markdown(ba_status)
    if ba_status.missing:
        warnings.append(
            "WARN: 基线尺子缺口 "
            + ",".join(ba_status.missing)
            + " — 见报告「基线尺子」节；建议先补 plain/reference 再 fancy"
        )

    cursor = _load_analyse_cursor(root) if since_analyse else None

    if quiet:
        parts = [
            ba_md.rstrip(),
            "",
            "## 数值摘要",
            "### 锚点（MA-1）",
            *ma1_lines,
        ]
        # 仅「上次 analyse 之后」的新行；游标 0 / 全量 / 无游标 → MA-1 已够
        show_ma3 = (
            bool(incr_rows)
            and not full_mode
            and cursor is not None
            and cursor > 0
        )
        if show_ma3:
            parts.extend(["", "### 增量（MA-3）", *ma3_lines])
        plateau_n = int(ma7_meta.get("plateau_rounds") or 0)
        plateau_streak = int(ma7_meta.get("plateau_streak") or 0)
        show_ma7 = plateau_streak >= plateau_n or bool(ma7_meta.get("high_noise"))
        if ma6_lines:
            parts.extend(["", "### 建议验证（MA-6）", *ma6_lines])
        if ma_r_lines:
            parts.extend(["", "### reflect 建议验证（MA-R）", *ma_r_lines])
        if show_ma7:
            parts.extend(["", "### plateau（MA-7）", *ma7_lines])
    else:
        ma3_title = "### 增量（MA-3） — 全量" if full_mode else "### 增量（MA-3）"
        parts = [
            ba_md.rstrip(),
            "",
            "## 数值摘要（analyse_metrics）",
            "### 锚点（MA-1）",
            *ma1_lines,
            "",
            "### 最近 K 轮（MA-2）",
            *ma2_lines,
            "",
            ma3_title,
            *ma3_lines,
        ]
        if ma4_lines:
            parts.extend(["", "### 多指标（MA-4）", *ma4_lines])
        if ma5_lines:
            parts.extend(["", "### 变更归因（MA-5）", *ma5_lines])
        if ma6_lines:
            parts.extend(["", "### 建议验证（MA-6）", *ma6_lines])
        if ma_r_lines:
            parts.extend(["", "### reflect 建议验证（MA-R）", *ma_r_lines])
        parts.extend(
            [
                "",
                "### plateau（MA-7）",
                *ma7_lines,
            ]
        )
    markdown = "\n".join(parts).rstrip() + "\n"

    sections: dict[str, Any] = {
        "baseline_anchors": ba_status.to_dict(),
        "ma1": {"lines": ma1_lines},
        "ma2": {"focus": focus_scenario_id(root) or "default", "rows": ma2_rows},
        "ma3": {
            "full_mode": full_mode,
            "row_count": len(incr_rows),
            "rows": ma3_rows,
        },
        "ma7": ma7_meta,
    }
    if ma4_lines:
        sections["ma4"] = {"rows": ma4_rows}
    if ma5_lines:
        sections["ma5"] = {"rows": ma5_rows}
    if ma6_lines:
        sections["ma6"] = ma6_meta or {"verdicts": []}
    if ma_r_lines:
        sections["ma_r"] = ma_r_meta or {"verdicts": []}
    return AnalyseMetricsReport(markdown=markdown, warnings=warnings, sections=sections)


def build_markdown_report(
    repo_root: Path | str, *, since_analyse: bool = False, quiet: bool = False
) -> str:
    """仅返回 markdown 块（供 SKILL 粘贴）。"""
    return build_analyse_report(
        repo_root, since_analyse=since_analyse, quiet=quiet
    ).markdown
