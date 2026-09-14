"""TSV 台账摘要与 reflect 门禁（与 auto-nn-run.sh 内嵌逻辑同源）。"""
from __future__ import annotations

import ast
import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lib.human_guidance_roadmap import RoadmapPhase, list_roadmap_phases
from lib.nn_config import load_nn_config


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def tsv_rows(repo_root: Path) -> list[dict[str, str]]:
    p = repo_root / "_runs" / "results.tsv"
    if not p.is_file():
        return []
    lines = [ln for ln in _read_text(p).splitlines() if ln.strip()]
    if len(lines) < 2:
        return []
    hdr = lines[0].split("\t")
    rows: list[dict[str, str]] = []
    for ln in lines[1:]:
        cells = ln.split("\t")
        if len(cells) < len(hdr):
            cells.extend([""] * (len(hdr) - len(cells)))
        rows.append(dict(zip(hdr, cells[: len(hdr)])))
    return rows


def _ast_dict(node: ast.AST) -> dict[str, str]:
    if not isinstance(node, ast.Dict):
        return {}
    out: dict[str, str] = {}
    for k, v in zip(node.keys, node.values):
        if isinstance(k, ast.Constant) and isinstance(k.value, str):
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                out[k.value] = v.value
    return out


def _parse_metrics_module(repo_root: Path) -> tuple[dict[str, str], dict[str, str]]:
    path = repo_root / "contract" / "metrics.py"
    if not path.is_file():
        return {}, {}
    try:
        tree = ast.parse(_read_text(path))
    except SyntaxError:
        return {}, {}
    metric_keys: dict[str, str] = {}
    auxiliary_keys: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "METRIC_KEYS":
                    metric_keys = _ast_dict(node.value)
                if isinstance(target, ast.Name) and target.id == "AUXILIARY_KEYS":
                    auxiliary_keys = _ast_dict(node.value)
    return metric_keys, auxiliary_keys


def _parse_contract_ast(repo_root: Path) -> dict[str, Any]:
    path = repo_root / "contract" / "__init__.py"
    mod_mk, mod_aux = _parse_metrics_module(repo_root)
    out: dict[str, Any] = {
        "metric_key": next(iter(mod_mk), "val_accuracy") if mod_mk else "val_accuracy",
        "metric_direction": next(iter(mod_mk.values()), "maximize") if mod_mk else "maximize",
        "auxiliary_keys": mod_aux,
    }
    if not path.is_file():
        return out
    try:
        tree = ast.parse(_read_text(path))
    except SyntaxError:
        return out
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if item.name == "metric_keys":
                for sub in ast.walk(item):
                    if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Dict) and sub.value.keys:
                        parsed = _ast_dict(sub.value)
                        if parsed:
                            out["metric_key"] = next(iter(parsed))
            if item.name == "metric_direction":
                for sub in ast.walk(item):
                    if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Constant):
                        if isinstance(sub.value.value, str):
                            out["metric_direction"] = sub.value.value
            if item.name == "auxiliary_keys":
                for sub in ast.walk(item):
                    if isinstance(sub, ast.Return) and isinstance(sub.value, ast.Dict):
                        parsed = _ast_dict(sub.value)
                        if parsed:
                            out["auxiliary_keys"] = parsed
    if mod_mk and out["metric_key"] == "val_accuracy":
        out["metric_key"] = next(iter(mod_mk))
    if mod_mk and out["metric_direction"] == "maximize":
        out["metric_direction"] = next(iter(mod_mk.values()), "maximize")
    if mod_aux and not out["auxiliary_keys"]:
        out["auxiliary_keys"] = mod_aux
    return out


def _try_load_contract(repo_root: Path) -> Any | None:
    import sys

    root = repo_root.resolve()
    root_str = str(root)
    if not (root / "contract" / "__init__.py").is_file():
        return None

    mod = sys.modules.get("contract")
    mod_file = getattr(mod, "__file__", "") or ""
    if mod is not None and mod_file:
        try:
            if not Path(mod_file).resolve().is_relative_to(root):
                return None
        except ValueError:
            return None

    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    try:
        from contract import create_contract  # noqa: WPS433

        return create_contract({})
    except Exception:
        return None


def metric_key(repo_root: Path) -> str:
    """主指标列名：yaml.goal.metric > profiles.metric_key > contract.metric_key。

    v2.5.4: 用户在 ``goal.metric`` 手写的值最优先；
    用户手改持久（不再被下次 save 静默吃掉）。fallback 顺序 profiles → contract。
    """
    c = _try_load_contract(repo_root)
    ast_mk = str(_parse_contract_ast(repo_root)["metric_key"])
    mk = getattr(c, "metric_key", None) if c is not None else None
    base = str(mk) if mk else ast_mk
    try:
        import yaml

        cfg = yaml.safe_load(_read_text(repo_root / "nn-config.yaml")) or {}
        # v2.5.4 yaml 优先: 用户在 goal 块手写了 metric 即生效
        yaml_mk = (cfg.get("goal") or {}).get("metric")
        if yaml_mk:
            return str(yaml_mk)
        # 其次 profiles.yaml override
        prof = cfg.get("profile", "supervised")
        locks = yaml.safe_load(_read_text(repo_root / "profiles.yaml")) or {}
        override = (locks.get("profiles") or {}).get(prof, {}).get("metric_key")
        if override:
            return str(override)
    except Exception:
        pass
    return base


def metric_direction(repo_root: Path) -> str:
    """metric 方向：yaml.goal.op > contract.metric_direction（默认 ``maximize``）。

    v2.5.4: yaml.goal.op ``">="`` 反推 ``maximize``、``"<="`` 反推 ``minimize`` 优先于 contract。
    用户手改持久。
    """
    contract_dir = ""
    c = _try_load_contract(repo_root)
    if c is not None:
        d = getattr(c, "metric_direction", None)
        if d:
            contract_dir = str(d)
    try:
        import yaml
        cfg = yaml.safe_load(_read_text(repo_root / "nn-config.yaml")) or {}
        yaml_op = (cfg.get("goal") or {}).get("op")
        if yaml_op == ">=":
            return "maximize"
        if yaml_op == "<=":
            return "minimize"
    except Exception:
        pass
    if contract_dir:
        return contract_dir
    ast_d = _parse_contract_ast(repo_root).get("metric_direction", "maximize")
    return str(ast_d) if ast_d else "maximize"


def agent_config(repo_root: Path) -> tuple[int, int]:
    plateau_n, interval = 3, 1
    cfg_path = repo_root / "nn-config.yaml"
    if not cfg_path.is_file():
        return plateau_n, interval
    try:
        cfg = load_nn_config(repo_root)
        agent = cfg.get("agent") or {}
        plateau_n = int(agent.get("plateau_rounds", plateau_n))
        ref = cfg.get("reflect") if isinstance(cfg.get("reflect"), dict) else {}
        interval = int(ref.get("interval", interval))
    except Exception:
        pass
    return plateau_n, interval


def _load_agent_section(repo_root: Path) -> dict:
    cfg = load_nn_config(repo_root)
    agent = cfg.get("agent")
    return agent if isinstance(agent, dict) else {}


def _load_goal_section(repo_root: Path) -> dict:
    """v4: 读 ``cfg.goal`` 块（``target`` / ``per_scenario`` / ``policy``）。

    load_nn_config 已在读取时把 v3 ``agent.*`` 别名迁移到 goal 块，
    所以这里不需要再回填。"""
    cfg = load_nn_config(repo_root)
    goal = cfg.get("goal")
    return goal if isinstance(goal, dict) else {}


# v4 policy → v3 stop_mode 兼容映射（legacy callers like manage_goal CLI）
_POLICY_TO_STOP_MODE: dict[str, str] = {
    "focus": "focus_only",
    "strict": "all_in_scope",
}
_STOP_MODE_TO_POLICY: dict[str, str] = {v: k for k, v in _POLICY_TO_STOP_MODE.items()}


def scenario_goals_map(goal: dict) -> dict[str, float | None]:
    """``goal.per_scenario`` → ``{sid: float|None}``（None = 显式豁免）。"""
    raw = goal.get("per_scenario")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float | None] = {}
    for key, val in raw.items():
        sid = str(key).strip()
        if not sid:
            continue
        if val is None:
            out[sid] = None
            continue
        try:
            out[sid] = float(val)
        except (TypeError, ValueError):
            continue
    return out


def effective_goal(goal: dict, scenario_id: str) -> float | None:
    """单场景有效目标：override > global > 无。"""
    sid = (scenario_id or "").strip()
    overrides = scenario_goals_map(goal)
    if sid in overrides:
        return overrides[sid]
    raw = goal.get("target", None)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def goal_source(goal: dict, scenario_id: str) -> str:
    """``global`` | ``override`` | ``exempt`` | ``none``。"""
    sid = (scenario_id or "").strip()
    overrides = scenario_goals_map(goal)
    if sid in overrides:
        return "exempt" if overrides[sid] is None else "override"
    if effective_goal(goal, sid) is not None:
        return "global"
    return "none"


def goal_stop_mode(goal: dict) -> str:
    """v4 ``goal.policy`` ∈ ``{focus, strict}``。

    legacy v3 值（focus_only / all_in_scope）作为回退接受 → 返回 v4 标准值。
    """
    raw = goal.get("policy")
    if raw is None:
        raw = goal.get("stop_mode")
    if raw is None:
        return "focus"
    s = str(raw).strip()
    if s in ("focus", "strict"):
        return s
    if s in _STOP_MODE_TO_POLICY:
        return _STOP_MODE_TO_POLICY[s]
    return "focus"


def has_any_configured_goal(goal: dict) -> bool:
    """是否存在至少一个场景的有效 goal（含 global 或 override 数值）。"""
    raw = goal.get("target", None)
    if raw is not None:
        try:
            float(raw)
            return True
        except (TypeError, ValueError):
            pass
    for sid, val in scenario_goals_map(goal).items():
        if val is not None:
            try:
                float(val)
                return True
            except (TypeError, ValueError):
                continue
    return False


def goals_in_scope(repo_root: Path) -> list[str]:
    """停批/矩阵用的场景 ID 列表（去重保序）。"""
    goal = _load_goal_section(repo_root)
    mode = goal_stop_mode(goal)
    from lib.scenario_inventory import focus_scenario_id, load_scenario_active, load_scenario_ids

    if mode == "focus":
        return [focus_scenario_id(repo_root)]
    active = load_scenario_active(repo_root)
    if active:
        return list(active)
    return load_scenario_ids(repo_root)


def goal_matrix_scenario_ids(repo_root: Path) -> list[str]:
    """``show --all`` / run-context 矩阵：in_scope + per_scenario 键。"""
    seen: set[str] = set()
    out: list[str] = []
    for sid in goals_in_scope(repo_root):
        if sid not in seen:
            seen.add(sid)
            out.append(sid)
    for sid in scenario_goals_map(_load_goal_section(repo_root)):
        if sid not in seen:
            seen.add(sid)
            out.append(sid)
    return out


def _goal_metric_op(repo_root: Path) -> tuple[str, str]:
    """v4: metric/op 来自 contract；yaml 不再有 goal_metric/goal_op。"""
    mk = metric_key(repo_root)
    direction = metric_direction(repo_root)
    op = ">=" if direction == "maximize" else "<="
    return str(mk).strip(), op


def _goal_met(current: float, goal: float, op: str) -> bool:
    return (current >= goal) if op == ">=" else (current <= goal)


def _goal_gap(current: float, goal: float, op: str) -> float:
    return (goal - current) if op == ">=" else (current - goal)


def goal_matrix(repo_root: Path) -> list[dict[str, Any]]:
    """每场景 goal 进度一行（只读，不判停批）。"""
    goal = _load_goal_section(repo_root)
    mk, op = _goal_metric_op(repo_root)
    rows: list[dict[str, Any]] = []
    for sid in goal_matrix_scenario_ids(repo_root):
        gv = effective_goal(goal, sid)
        src = goal_source(goal, sid)
        if gv is None and src == "none":
            continue
        best = _best_row_for_scenario(repo_root, sid, mk)
        current = _float_cell(best or {}, mk)
        met: bool | None = None
        gap: float | None = None
        if gv is not None and current is not None:
            met = _goal_met(current, gv, op)
            gap = _goal_gap(current, gv, op)
        rows.append(
            {
                "scenario_id": sid,
                "goal": gv,
                "metric": mk,
                "op": op,
                "current": current,
                "met": met,
                "gap": gap,
                "source": src,
            }
        )
    return rows


def goal_config(repo_root: Path) -> tuple[float | None, str, str, str]:
    """v4: 读 ``cfg.goal`` 块（target / per_scenario）+ contract metric/op。

    返回 ``(goal_value, metric_key, op, scenario_default)``。
    ``scenario_default`` 仍来自 agent（v4 不迁移此键）。
    """
    goal = _load_goal_section(repo_root)
    mk, op = _goal_metric_op(repo_root)
    agent = _load_agent_section(repo_root)
    sid = str(agent.get("scenario_default") or "default").strip()
    goal_value = effective_goal(goal, sid)
    return goal_value, mk, op, sid


def yaml_safe_load_dict(path: Path) -> dict:
    import yaml  # noqa: WPS433

    raw = yaml.safe_load(_read_text(path)) or {}
    return raw if isinstance(raw, dict) else {}


def goal_progress(repo_root: Path) -> dict[str, Any] | None:
    """goal 进度快照（focus 场景；供 analyse / run-context / doctor 共用；只读）。

    focus 场景无有效 goal → ``None``。
    """
    goal_value, mk, op, sid = goal_config(repo_root)
    if goal_value is None:
        return None
    best = _best_row_for_scenario(repo_root, sid, mk) or best_tsv_row(repo_root, mk)
    current = _float_cell(best or {}, mk)
    met: bool | None = None
    gap: float | None = None
    if current is not None:
        met = (current >= goal_value) if op == ">=" else (current <= goal_value)
        gap = (goal_value - current) if op == ">=" else (current - goal_value)
    return {
        "goal": goal_value,
        "metric": mk,
        "op": op,
        "scenario_id": sid,
        "current": current,
        "met": met,
        "gap": gap,
    }


def format_goal_progress_line(repo_root: Path) -> str | None:
    """goal 进度一行：``goal: 0.95 | 当前最好: 0.93 | 差 0.02 | 达标: 否``。

    未配 goal → ``None``（调用方据此省略）。已配但缺数据 → 显示 ``(无数据)``。
    """
    info = goal_progress(repo_root)
    if info is None:
        return None
    cur = info["current"]
    cur_s = "(无数据)" if cur is None else f"{cur:.6g}"
    if info["gap"] is None:
        gap_s = "-"
    else:
        gap_s = f"{info['gap']:.6g}"
    met = info["met"]
    met_s = "-" if met is None else ("是" if met else "否")
    return (
        f"goal: {info['goal']:.6g} | 当前最好: {cur_s} | 差 {gap_s} | 达标: {met_s}"
    )


def format_goal_matrix_lines(repo_root: Path) -> list[str]:
    """多场景 goal 表（analyse / run-context）；无行 → 空列表。"""
    goal = _load_goal_section(repo_root)
    matrix = goal_matrix(repo_root)
    if not matrix:
        return []
    mode = goal_stop_mode(goal)
    lines = [f"goal_stop_mode: {mode}"]
    for row in matrix:
        sid = row["scenario_id"]
        gv = row["goal"]
        cur = row["current"]
        src = row["source"]
        if gv is None:
            lines.append(f"  {sid}: (豁免) source={src}")
            continue
        cur_s = "(无数据)" if cur is None else f"{cur:.6g}"
        met_s = "-"
        if row["met"] is not None:
            met_s = "是" if row["met"] else "否"
        gap_s = "-"
        if row["gap"] is not None:
            gap_s = f"{row['gap']:.6g}"
        lines.append(
            f"  {sid}: goal={gv:.6g} 当前={cur_s} 差={gap_s} 达标={met_s} ({src})"
        )
    return lines


def should_show_goal_matrix(repo_root: Path) -> bool:
    """run-context / analyse 是否附加多场景 goal 块。"""
    goal = _load_goal_section(repo_root)
    if goal_stop_mode(goal) == "strict":
        return True
    return bool(scenario_goals_map(goal))


def _metric_floor_value(repo_root: Path) -> float | None:
    agent = yaml_safe_load_dict(repo_root / "nn-config.yaml").get("agent") or {}
    explore = agent.get("explore")
    if not isinstance(explore, dict):
        return None
    raw = explore.get("metric_floor", None)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def floor_progress(repo_root: Path) -> dict[str, Any] | None:
    """explore 期 metric 底线进度（与 check_metric_floor 同源；只读，不判 exit）。

    非 explore 有效态或未配 metric_floor → ``None``。
    """
    from lib.experiment_mode import resolve_exploration  # noqa: WPS433

    # 缺 exploration_mode（未迁移）→ 当作非 explore 返 None（floor_progress 与
    # build-run-context 共享，run-context 构造不可崩；故此处吞 KeyError）
    try:
        if not resolve_exploration(repo_root).skip_goal_stop:
            return None
    except KeyError:
        return None
    floor = _metric_floor_value(repo_root)
    if floor is None:
        return None
    _, mk, _, sid = goal_config(repo_root)
    direction = metric_direction(repo_root)
    row = _best_row_for_scenario(repo_root, sid, mk, direction)
    current = _float_cell(row or {}, mk) if row else None
    breached: bool | None = None
    gap: float | None = None
    if current is not None:
        breached = (current < floor) if direction == "maximize" else (current > floor)
        gap = abs(floor - current)
    return {
        "floor": floor,
        "metric": mk,
        "scenario_id": sid,
        "current": current,
        "breached": breached,
        "gap": gap,
    }


def format_floor_progress_line(repo_root: Path) -> str | None:
    """floor 进度一行：``floor: 0.8 | 当前: 0.9 | 破线: 否``。

    非 explore 或未配 floor → ``None``。已配但缺 TSV 数据 → 当前显示 ``(无数据)``。
    """
    info = floor_progress(repo_root)
    if info is None:
        return None
    cur = info["current"]
    cur_s = "(无数据)" if cur is None else f"{cur:.6g}"
    breached = info["breached"]
    breach_s = "-" if breached is None else ("是" if breached else "否")
    return f"floor: {info['floor']:.6g} | 当前: {cur_s} | 破线: {breach_s}"


def last_reflect_row_ts(repo_root: Path) -> str:
    idx = repo_root / "references" / "REFLECT_INDEX.md"
    if idx.is_file():
        for line in _read_text(idx).splitlines():
            if line.startswith("| R") and "---" not in line:
                parts = [c.strip() for c in line.strip("|").split("|")]
                if len(parts) >= 2:
                    return parts[1]
    st = repo_root / "saved" / "reflect_latest.json"
    if st.is_file():
        try:
            return str(json.loads(_read_text(st)).get("timestamp", ""))[:16]
        except Exception:
            pass
    auto = repo_root / "references" / "auto"
    if auto.is_dir():
        files = sorted(auto.glob("*_auto_reflected.md"))
        if files:
            return files[-1].name[:8]
    return ""


def rounds_since_reflect(repo_root: Path) -> int:
    rows = tsv_rows(repo_root)
    if not rows:
        return 0
    last_ts = last_reflect_row_ts(repo_root)
    if not last_ts:
        return len(rows)
    n = 0
    for r in reversed(rows):
        ts = r.get("timestamp", r.get("experiment", ""))
        if last_ts and last_ts in ts:
            break
        n += 1
    return n


def plateau_streak(repo_root: Path, plateau_n: int, mk: str | None = None) -> int:
    """尾部连续「未达窗口内全局 best」次数（方向由 contract / 列映射决定，见 ``metric_analysis``）。"""
    from lib.metric_analysis import metric_direction_for_column, plateau_streak_from_vals  # noqa: WPS433

    rows = tsv_rows(repo_root)
    if len(rows) < 2:
        return 0
    metric = mk or metric_key(repo_root)
    direction = metric_direction_for_column(repo_root.resolve(), metric)
    vals: list[float] = []
    for r in rows[-max(plateau_n + 2, 8) :]:
        try:
            vals.append(float(r.get(metric, "nan")))
        except ValueError:
            vals.append(float("nan"))
    return plateau_streak_from_vals(vals, plateau_n, direction=direction)


def round_decision_status(repo_root: Path) -> str:
    for name in ("round_decision.json", "evaluation_result.json"):
        p = repo_root / "_runs" / name
        if not p.is_file():
            continue
        try:
            d = json.loads(_read_text(p))
            ks = d.get("keep_suggestion") or d.get("keep") or {}
            if isinstance(ks, dict):
                return str(ks.get("decision", ks.get("action", ""))).upper()
        except Exception:
            pass
    return ""


def tier_exhaust_keywords(repo_root: Path) -> bool:
    """reflect R5：仅扫 EXPERIENCE + journal entries（summary/note/decision），不读 progress。"""
    keywords = ("tier 穷尽", "tier穷尽", "撞墙", "plateau", "升 tier", "升档")

    exp = repo_root / "EXPERIENCE.md"
    if exp.is_file():
        text = _read_text(exp).lower()
        if any(kw in text for kw in keywords):
            return True

    try:
        from lib.experiment_journal import journal_path, read_journal  # noqa: WPS433

        journal = read_journal(journal_path(repo_root))
        for entry in journal.get("entries") or []:
            if not isinstance(entry, dict):
                continue
            parts: list[str] = []
            for field in ("summary", "note", "decision"):
                val = entry.get(field)
                if val is not None and str(val).strip():
                    parts.append(str(val))
            if not parts:
                continue
            text = " ".join(parts).lower()
            if any(kw in text for kw in keywords):
                return True
    except ImportError:
        pass

    return False


def agent_reflect_flags(repo_root: Path) -> tuple[bool, bool]:
    """nn-config reflect.force / reflect.skip（一次性 env：NN_REFLECT_FORCE / NN_REFLECT_SKIP）。"""
    force = False
    skip = False
    env_force = os.environ.get("NN_REFLECT_FORCE", "").strip().lower()
    env_skip = os.environ.get("NN_REFLECT_SKIP", "").strip().lower()
    if env_force in ("1", "true", "yes", "on"):
        force = True
    if env_skip in ("1", "true", "yes", "on"):
        skip = True
    cfg_path = repo_root / "nn-config.yaml"
    if cfg_path.is_file():
        try:
            import yaml

            cfg = yaml.safe_load(_read_text(cfg_path)) or {}
            ref = cfg.get("reflect") if isinstance(cfg.get("reflect"), dict) else {}
            if not force:
                force = bool(ref.get("force", False))
            if not skip:
                skip = bool(ref.get("skip", False))
        except Exception:
            pass
    return force, skip


def human_guidance_reflect_mode(repo_root: Path) -> str:
    """已废弃：HUMAN_GUIDANCE 不再含 reflect:；保留别名供旧脚本 import。"""
    force, skip = agent_reflect_flags(repo_root)
    if skip:
        return "skip"
    if force:
        return "force"
    return "auto"


def reflect_gate_decision(repo_root: Path, run: int, interval: int, plateau_n: int) -> str:
    """返回 auto-run 同款前缀：run:R* 或 skip:*"""
    force, skip = agent_reflect_flags(repo_root)
    if skip:
        return "skip:reflect_skip"
    # R8 paradigm_mismatch（最高优先级，软警告——不中断批次，只让下一轮强制 reflect）
    # agent 无自决切范式权（要求1）：R8 只产出信号 → 强制 reflect 一次让 agent 自检，
    # 切范式决策锁在 human（经 check/analyze 技能读 paradigm_fit 字段发现）。
    try:
        from lib.auto_mode import check_paradigm_mismatch
        if check_paradigm_mismatch(repo_root):
            return "run:R8:paradigm_mismatch"
    except ImportError:
        pass
    if force and interval > 0:
        return "run:R1:reflect_force"

    try:
        from lib.explore_objective import (  # noqa: WPS433
            coverage_stall_streak,
            effective_objective,
            load_explore_config,
        )

        res = effective_objective(repo_root)
        if res.mode == "explore" and not res.migration_blocked:
            stall_n = load_explore_config(repo_root)["reflect_gate_coverage_stall"]
            if coverage_stall_streak(repo_root) >= stall_n:
                return f"run:R7:coverage_stall>={stall_n}"
    except ImportError:
        pass

    rd = repo_root / "_runs" / "round_decision.json"
    if not rd.is_file() or rd.stat().st_size < 3:
        return "run:R3:no_round_decision"

    status = round_decision_status(repo_root)
    if status == "DISCARD":
        return "run:R4:discard"

    ps = plateau_streak(repo_root, plateau_n)
    if ps >= plateau_n:
        return f"run:R2:plateau>={plateau_n}"

    if tier_exhaust_keywords(repo_root):
        return "run:R5:tier_exhaust_kw"

    since = rounds_since_reflect(repo_root)
    if since >= interval:
        return f"run:R6:interval>={interval}(since={since})"

    rows = tsv_rows(repo_root)
    if status == "KEEP" and rows:
        mk = metric_key(repo_root)
        try:
            last_v = float(rows[-1].get(mk, "nan"))
            prev = [float(r.get(mk, "nan")) for r in rows[:-1] if r.get(mk)]
            if prev and last_v == last_v and last_v >= max(prev):
                return "skip:keep_new_best"
        except ValueError:
            pass

    return f"skip:no_gate(since_reflect={since},plateau={ps})"


def _float_cell(row: dict[str, str], key: str) -> float | None:
    raw = row.get(key, "")
    if raw is None or str(raw).strip() == "":
        return None
    try:
        v = float(raw)
    except ValueError:
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


def best_tsv_row(repo_root: Path, mk: str | None = None, direction: str | None = None) -> dict[str, str] | None:
    mk = mk or metric_key(repo_root)
    direction = direction or metric_direction(repo_root)
    best_row: dict[str, str] | None = None
    best_v: float | None = None
    for row in tsv_rows(repo_root):
        if row.get("experiment") == "preflight_check":
            continue
        v = _float_cell(row, mk)
        if v is None:
            continue
        if best_v is None:
            best_v, best_row = v, row
            continue
        if direction == "minimize":
            if v < best_v:
                best_v, best_row = v, row
        elif v > best_v:
            best_v, best_row = v, row
    return best_row


def load_keeper(repo_root: Path) -> dict[str, Any]:
    """向后兼容：读 legacy ``saved/keeper.json``（优先用 ``load_keepers``）。"""
    p = repo_root / "saved" / "keeper.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(_read_text(p))
    except Exception:
        return {}


def load_keepers(repo_root: Path) -> dict[str, dict]:
    """读取 ``saved/keepers.json``；必要时自 ``keeper.json`` 迁移（委托 ``experiment.load_keepers``）。"""
    root = repo_root.resolve()
    pkg = str(root)
    import sys

    if pkg not in sys.path:
        sys.path.insert(0, pkg)
    try:
        from experiment import load_keepers as _exp_load_keepers  # noqa: WPS433

        return _exp_load_keepers(root)
    except ImportError:
        keepers_path = root / "saved" / "keepers.json"
        if not keepers_path.is_file():
            return {}
        try:
            data = json.loads(_read_text(keepers_path))
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(k): v for k, v in data.items() if isinstance(v, dict)}


def _tsv_rows_for_scenario(
    repo_root: Path, scenario_id: str
) -> list[dict[str, str]]:
    sid = (scenario_id or "").strip()
    if not sid:
        return []
    return [
        r
        for r in tsv_rows(repo_root)
        if r.get("experiment") != "preflight_check"
        and str(r.get("scenario_id", "")).strip() == sid
    ]


def _best_row_for_scenario(
    repo_root: Path,
    scenario_id: str,
    mk: str | None = None,
    direction: str | None = None,
) -> dict[str, str] | None:
    mk = mk or metric_key(repo_root)
    direction = direction or metric_direction(repo_root)
    best_row: dict[str, str] | None = None
    best_v: float | None = None
    for row in _tsv_rows_for_scenario(repo_root, scenario_id):
        v = _float_cell(row, mk)
        if v is None:
            continue
        if best_v is None:
            best_v, best_row = v, row
            continue
        if direction == "minimize":
            if v < best_v:
                best_v, best_row = v, row
        elif v > best_v:
            best_v, best_row = v, row
    return best_row


def _plateau_streak_for_scenario(
    repo_root: Path,
    scenario_id: str,
    plateau_n: int,
    mk: str | None = None,
) -> int:
    from lib.metric_analysis import metric_direction_for_column, plateau_streak_from_vals  # noqa: WPS433

    rows = _tsv_rows_for_scenario(repo_root, scenario_id)
    if len(rows) < 2:
        return 0
    metric = mk or metric_key(repo_root)
    direction = metric_direction_for_column(repo_root.resolve(), metric)
    vals: list[float] = []
    for r in rows[-max(plateau_n + 2, 8) :]:
        try:
            vals.append(float(r.get(metric, "nan")))
        except ValueError:
            vals.append(float("nan"))
    return plateau_streak_from_vals(vals, plateau_n, direction=direction)


def format_keeper_status(repo_root: Path) -> list[str]:
    """分场景 keeper 摘要；focus 场景排第一并带 ``*`` 标记。

    场景来源（union 去重保序）：
    1. F1 manifest（``load_scenario_ids``）
    2. ``agent.scenario_active`` 解析（逗号/分号分隔）
    3. ``saved/keepers.json`` 实际存在的 key

    状态（每行前缀）：
    - ``[KEEP'd]`` 有 keeper_exp_dir 且路径存在
    - ``[stale]`` 有 keeper_exp_dir 但路径不存在
    - ``[best-only]`` 无 keeper 但 TSV 有 best 行
    - ``[empty]`` 完全无数据
    """
    root = repo_root.resolve()
    scripts = root / "scripts"
    import sys

    scripts_str = str(scripts.resolve())
    if scripts.is_dir() and scripts_str not in sys.path:
        sys.path.insert(0, scripts_str)

    from lib.scenario_inventory import focus_scenario_id, load_scenario_ids  # noqa: WPS433

    focus = focus_scenario_id(root)

    # Union sources
    sources: list[str] = []
    for s in (load_scenario_ids(root) or []):
        if s and s not in sources:
            sources.append(s)

    # scenario_active 解析（str 逗号/分号分隔 或 list）
    agent_cfg = _load_agent_section(root)
    active = agent_cfg.get("scenario_active")
    if isinstance(active, str) and active.strip():
        for s in active.replace(";", ",").split(","):
            s = s.strip()
            if s and s not in sources:
                sources.append(s)
    elif isinstance(active, list):
        for s in active:
            ss = str(s).strip()
            if ss and ss not in sources:
                sources.append(ss)

    # keepers.json keys
    for s in (load_keepers(root) or {}).keys():
        if s and s not in sources:
            sources.append(s)

    # focus 排第一
    scenario_ids: list[str] = []
    if focus and focus in sources:
        scenario_ids.append(focus)
    for s in sources:
        if s not in scenario_ids:
            scenario_ids.append(s)

    keepers = load_keepers(root)
    mk = metric_key(root)
    plateau_n, _ = agent_config(root)

    lines = [f"keepers (focus={focus or '(无)'}):"]
    for sid in scenario_ids:
        entry = keepers.get(sid) or {}
        keeper_dir = str(entry.get("keeper_exp_dir") or "").strip()
        # v2.7.4: keeper_exp_dir 存相对 repo_root; 按 repo_root 判存在, 不能按 cwd
        _kp = Path(keeper_dir)
        if keeper_dir and (_kp if _kp.is_absolute() else (Path(root) / _kp)).exists():
            status = "KEEP'd"
            keeper_label = f"keeper={keeper_dir}"
        elif keeper_dir:
            status = "stale"
            keeper_label = f"keeper={keeper_dir} (无效)"
        elif _best_row_for_scenario(root, sid, mk):
            status = "best-only"
            keeper_label = "keeper=(无)"
        else:
            status = "empty"
            keeper_label = "keeper=(无)"

        best = _best_row_for_scenario(root, sid, mk)
        best_v = _float_cell(best or {}, mk)
        metric_label = f"{mk}={best_v if best_v is not None else ''}"

        ps = _plateau_streak_for_scenario(root, sid, plateau_n, mk)
        marker = "*" if sid == focus else " "
        lines.append(
            f"  {marker} {sid:<14} [{status}] {keeper_label}  {metric_label}  plateau={ps}"
        )
    if len(lines) == 1:
        lines.append("  (无 F1 场景清单 + 无 keepers)")
    return lines


def aux_column_empty_rates(repo_root: Path) -> dict[str, float]:
    c = _try_load_contract(repo_root)
    if c is not None:
        aux = dict(getattr(c, "auxiliary_keys", {}) or {})
    else:
        aux = dict(_parse_contract_ast(repo_root).get("auxiliary_keys") or {})
    if not aux:
        return {}
    rows = [r for r in tsv_rows(repo_root) if r.get("experiment") != "preflight_check"]
    if not rows:
        return {col: 1.0 for col in aux}
    hdr = set(rows[0].keys())
    rates: dict[str, float] = {}
    for col in aux:
        if col not in hdr:
            rates[col] = 1.0
            continue
        empty = sum(1 for r in rows if not str(r.get(col, "")).strip())
        rates[col] = empty / len(rows)
    return rates


@dataclass
class RunLedgerSummary:
    metric_key: str
    metric_direction: str
    plateau_rounds: int
    reflect_interval: int
    plateau_streak: int
    rounds_since_reflect: int
    reflect_mode: str
    reflect_gate_auto: str
    reflect_would_trigger: bool
    keeper_exp_dir: str
    best_experiment: str
    best_metric_value: str
    last_experiment: str
    last_metric_value: str
    tsv_data_rows: int
    aux_empty_rates: dict[str, float]
    round_decision: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_key": self.metric_key,
            "metric_direction": self.metric_direction,
            "plateau_rounds": self.plateau_rounds,
            "reflect_interval": self.reflect_interval,
            "plateau_streak": self.plateau_streak,
            "rounds_since_reflect": self.rounds_since_reflect,
            "reflect_mode": self.reflect_mode,
            "reflect_gate_auto": self.reflect_gate_auto,
            "reflect_would_trigger": self.reflect_would_trigger,
            "keeper_exp_dir": self.keeper_exp_dir,
            "best_experiment": self.best_experiment,
            "best_metric_value": self.best_metric_value,
            "last_experiment": self.last_experiment,
            "last_metric_value": self.last_metric_value,
            "tsv_data_rows": self.tsv_data_rows,
            "aux_empty_rates": self.aux_empty_rates,
            "round_decision": self.round_decision,
        }


def build_summary(repo_root: Path, *, run: int = 1) -> RunLedgerSummary:
    root = repo_root.resolve()
    mk = metric_key(root)
    direction = metric_direction(root)
    plateau_n, interval = agent_config(root)
    ps = plateau_streak(root, plateau_n, mk)
    since = rounds_since_reflect(root)
    reflect_mode = human_guidance_reflect_mode(root)
    gate_auto = reflect_gate_decision(root, run, interval, plateau_n)
    would_trigger = gate_auto.startswith("run:")
    gate_label = gate_auto

    try:
        from lib.ledger_anchor import code_baseline_entry, metric_leader_row  # noqa: WPS433

        baseline = code_baseline_entry(root)
        keeper_dir = str(baseline.keeper_exp_dir if baseline else "").strip()
        leader = metric_leader_row(root)
        best = leader.row if leader else best_tsv_row(root, mk, direction)
    except ImportError:
        keeper = load_keeper(root)
        keeper_dir = str(keeper.get("keeper_exp_dir") or "").strip()
        best = best_tsv_row(root, mk, direction)
    rows = tsv_rows(root)
    data_rows = [r for r in rows if r.get("experiment") != "preflight_check"]
    last = data_rows[-1] if data_rows else {}

    return RunLedgerSummary(
        metric_key=mk,
        metric_direction=direction,
        plateau_rounds=plateau_n,
        reflect_interval=interval,
        plateau_streak=ps,
        rounds_since_reflect=since,
        reflect_mode=reflect_mode,
        reflect_gate_auto=gate_label,
        reflect_would_trigger=would_trigger,
        keeper_exp_dir=keeper_dir,
        best_experiment=str((best or {}).get("experiment", "")),
        best_metric_value=str(_float_cell(best or {}, mk) if best else ""),
        last_experiment=str(last.get("experiment", "")),
        last_metric_value=str(_float_cell(last, mk) if last else ""),
        tsv_data_rows=len(data_rows),
        aux_empty_rates=aux_column_empty_rates(root),
        round_decision=round_decision_status(root),
    )


def format_brief(summary: RunLedgerSummary, *, repo_root: Path | None = None) -> str:
    lines = [
        f"metric_key={summary.metric_key} direction={summary.metric_direction}",
        f"plateau_streak={summary.plateau_streak}/{summary.plateau_rounds}",
        f"rounds_since_reflect={summary.rounds_since_reflect} reflect_interval={summary.reflect_interval}",
        f"reflect_mode={summary.reflect_mode} gate={summary.reflect_gate_auto} trigger={'yes' if summary.reflect_would_trigger else 'no'}",
        f"code_baseline_exp_dir={summary.keeper_exp_dir or '(无)'}",
        f"last={summary.last_experiment} {summary.metric_key}={summary.last_metric_value}",
        f"tsv_data_rows={summary.tsv_data_rows} round_decision={summary.round_decision or '(无)'}",
    ]
    if repo_root is not None:
        try:
            from lib.ledger_anchor import format_leader_baseline_lines  # noqa: WPS433

            lines.extend(format_leader_baseline_lines(repo_root.resolve()))
        except ImportError:
            lines.append(
                f"metric_leader={summary.best_experiment} {summary.metric_key}={summary.best_metric_value}"
            )
    else:
        lines.insert(
            5,
            f"metric_leader={summary.best_experiment} {summary.metric_key}={summary.best_metric_value}",
        )
    if summary.aux_empty_rates:
        aux_parts = [
            f"{k}={v:.0%}空"
            for k, v in sorted(summary.aux_empty_rates.items())
            if v >= 0.5
        ]
        if aux_parts:
            lines.append("aux_empty: " + ", ".join(aux_parts))
    if repo_root is not None:
        try:
            from lib.reflect_brief import reflect_pending_id  # noqa: WPS433

            rid = reflect_pending_id(repo_root.resolve())
            lines.append(f"reflect_pending={rid or 'none'}")
        except ImportError:
            pass
    return "\n".join(lines)


@dataclass
class RoadmapStatus:
    roadmap: str
    n_phases: int
    inferred_phase: str
    phase_title: str
    criteria_met: str
    keep_in_phase: int
    plateau_streak_in_phase: int
    plateau_rounds: int
    coverage_progress: str = ""


def parse_roadmap_phases(repo_root: Path) -> list[RoadmapPhase]:
    p = repo_root / "HUMAN_GUIDANCE.md"
    if not p.is_file():
        return []
    return list_roadmap_phases(_read_text(p))


def _row_had_keep(repo_root: Path, row: dict[str, str]) -> bool:
    if str(row.get("keep", "")).strip().lower() in ("1", "true", "yes"):
        return True
    exp = str(row.get("exp_dir", "")).strip()
    if not exp:
        return False
    for name in ("keep_suggestion.json", "evaluation_result.json"):
        ks = Path(exp) / name
        if not ks.is_file():
            continue
        try:
            d = json.loads(_read_text(ks))
            if d.get("keep_suggestion") is True:
                return True
            inner = d.get("keep_suggestion")
            if isinstance(inner, dict) and str(inner.get("decision", "")).upper() == "KEEP":
                return True
        except Exception:
            continue
    return False


def _segment_plateau_streak(
    repo_root: Path, rows: list[dict[str, str]], mk: str, plateau_n: int
) -> int:
    from lib.metric_analysis import metric_direction_for_column, plateau_streak_from_vals  # noqa: WPS433

    if len(rows) < 2:
        return 0
    direction = metric_direction_for_column(repo_root.resolve(), mk)
    vals: list[float] = []
    for r in rows[-max(plateau_n + 2, 8) :]:
        try:
            vals.append(float(r.get(mk, "nan")))
        except ValueError:
            vals.append(float("nan"))
    return plateau_streak_from_vals(vals, plateau_n, direction=direction)


def _segment_criteria_met(
    rows: list[dict[str, str]], repo_root: Path, mk: str, plateau_n: int
) -> str | None:
    if any(_row_had_keep(repo_root, r) for r in rows):
        return "keep_once"
    if (
        len(rows) >= plateau_n
        and _segment_plateau_streak(repo_root, rows, mk, plateau_n) >= plateau_n
    ):
        return "plateau"
    return None


def roadmap_status(repo_root: Path, *, attach_coverage: bool = True) -> RoadmapStatus:
    phases = parse_roadmap_phases(repo_root)
    plateau_n, _ = agent_config(repo_root)
    mk = metric_key(repo_root)

    def _done(status: RoadmapStatus) -> RoadmapStatus:
        if not attach_coverage:
            return status
        return _attach_coverage_progress(repo_root, status)

    if not phases:
        return _done(RoadmapStatus("empty", 0, "empty", "", "none", 0, 0, plateau_n))

    data_rows = [r for r in tsv_rows(repo_root) if r.get("experiment") != "preflight_check"]
    start = 0
    last_met = "none"
    for i, phase in enumerate(phases):
        seg = data_rows[start:]
        if not seg:
            return _done(
                RoadmapStatus(
                    "active",
                    len(phases),
                    str(i + 1),
                    phase.title,
                    "none",
                    0,
                    0,
                    plateau_n,
                )
            )
        met_prefix: tuple[int, str] | None = None
        for j in range(1, len(seg) + 1):
            crit = _segment_criteria_met(seg[:j], repo_root, mk, plateau_n)
            if crit:
                met_prefix = (j, crit)
                break
        if met_prefix is None:
            keep_n = sum(1 for r in seg if _row_had_keep(repo_root, r))
            ps = _segment_plateau_streak(repo_root, seg, mk, plateau_n)
            return _done(
                RoadmapStatus(
                    "active",
                    len(phases),
                    str(i + 1),
                    phase.title,
                    "none",
                    keep_n,
                    ps,
                    plateau_n,
                )
            )
        start += met_prefix[0]
        last_met = met_prefix[1]

    return _done(
        RoadmapStatus(
            "active",
            len(phases),
            "done",
            phases[-1].title,
            last_met,
            0,
            0,
            plateau_n,
        )
    )


def _attach_coverage_progress(repo_root: Path, status: RoadmapStatus) -> RoadmapStatus:
    try:
        from lib.explore_objective import coverage_progress_line  # noqa: WPS433

        line = coverage_progress_line(repo_root)
    except ImportError:
        line = ""
    if not line:
        return status
    return RoadmapStatus(
        status.roadmap,
        status.n_phases,
        status.inferred_phase,
        status.phase_title,
        status.criteria_met,
        status.keep_in_phase,
        status.plateau_streak_in_phase,
        status.plateau_rounds,
        coverage_progress=line,
    )


def format_roadmap_status(status: RoadmapStatus) -> str:
    lines = [
        f"roadmap: {status.roadmap}",
        f"n_phases: {status.n_phases}",
        f"inferred_phase: {status.inferred_phase}",
        f"phase_title: {status.phase_title or '(无)'}",
        f"criteria_met: {status.criteria_met}",
        f"keep_in_phase: {status.keep_in_phase}",
        f"plateau_streak_in_phase: {status.plateau_streak_in_phase}/{status.plateau_rounds}",
    ]
    if status.coverage_progress:
        lines.append(status.coverage_progress)
    return "\n".join(lines)


def run_context_recent_rows(repo_root: Path) -> int:
    ctx: dict = {}
    cfg_path = repo_root / "nn-config.yaml"
    if cfg_path.is_file():
        try:
            import yaml

            raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            ctx = (raw.get("context") or {}) if isinstance(raw, dict) else {}
            if not isinstance(ctx, dict):
                ctx = {}
        except Exception:
            ctx = {}
    try:
        n = int(ctx.get("recent_rows", 5))
    except (TypeError, ValueError):
        n = 5
    return max(1, min(10, n))


def _load_near_best_abs(repo_root: Path) -> float:
    cfg_path = repo_root / "nn-config.yaml"
    if not cfg_path.is_file():
        return 0.0
    try:
        import yaml

        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        keep = (raw.get("keep") or {}) if isinstance(raw, dict) else {}
        return float(keep.get("near_best_abs") or 0.0)
    except Exception:
        return 0.0


def format_recent_ledger_window(repo_root: Path, *, k: int | None = None) -> list[str]:
    from lib.ledger_anchor import metric_leader_row  # noqa: WPS433

    root = repo_root.resolve()
    if k is None:
        k = run_context_recent_rows(root)
    rows = [r for r in tsv_rows(root) if r.get("experiment") != "preflight_check"]
    if not rows:
        return []
    mk = metric_key(root)
    direction = metric_direction(root)
    leader = metric_leader_row(root)
    if leader is not None:
        leader_val = float(leader.metric_value)
        leader_exp = leader.experiment
    else:
        best = best_tsv_row(root, mk, direction)
        if not best:
            return []
        bv = _float_cell(best, mk)
        if bv is None:
            return []
        leader_val = bv
        leader_exp = str(best.get("experiment", ""))
    window = rows[-k:]
    total = len(rows)
    near_tol = _load_near_best_abs(root)

    def delta(cur: float) -> float:
        return cur - leader_val if direction == "maximize" else leader_val - cur

    def strict_improve(cur: float) -> bool:
        return cur > leader_val if direction == "maximize" else cur < leader_val

    def near_leader(cur: float) -> bool:
        if near_tol <= 0.0:
            return False
        if direction == "maximize":
            return cur >= leader_val - near_tol
        return cur <= leader_val + near_tol

    lines = [
        f"recent_window: last {len(window)} of {total} rows | metric_key={mk} | leader={leader_val} ({leader_exp})",
    ]
    strict_n = 0
    near_n = 0
    valid = 0
    for i, r in enumerate(window, start=total - len(window) + 1):
        cur = _float_cell(r, mk)
        if cur is None:
            continue
        valid += 1
        d = delta(cur)
        si = strict_improve(cur)
        nl = near_leader(cur)
        if si:
            strict_n += 1
        if nl:
            near_n += 1
        extra = f" near_leader={'yes' if nl else 'no'}" if near_tol > 0 else ""
        lines.append(
            f"  - [{i}] exp={r.get('experiment', '?')} {mk}={cur} delta_vs_leader={d:+.6f}{extra}"
        )
    denom = valid or len(window)
    summary = f"summary: {strict_n}/{denom} strict_improve_vs_leader"
    if near_tol > 0:
        summary += f" | {near_n}/{denom} near_leader (tol={near_tol})"
    lines.append(summary)
    last_cur = _float_cell(window[-1], mk)
    if last_cur is not None:
        lines.append(f"last_row_vs_leader: {delta(last_cur):+.6f}")
    return lines


# ── v3 goal_spec format 转发（spec §9.1；lib/goal_spec.py 为真源）──


def format_goal_spec_progress(repo_root: Path) -> str | None:
    """v3 progress line（Run Context 注入用）。若 goal_spec 未配 → None。"""
    from lib.goal_spec import (
        evaluate_goal_spec,
        format_goal_spec_progress as _fmt,
        parse_goal_spec,
    )
    agent = _load_agent_section(repo_root)
    spec = parse_goal_spec(agent or {})
    if spec is None:
        return None
    try:
        result = evaluate_goal_spec(spec, repo_root)
    except Exception:
        return None
    return _fmt(result)


def format_goal_spec_matrix_lines(repo_root: Path) -> list[str]:
    """v3 matrix lines（`show --all` 用）。"""
    from lib.goal_spec import (
        evaluate_goal_spec,
        format_goal_spec_matrix_lines as _fmt,
        parse_goal_spec,
    )
    agent = _load_agent_section(repo_root)
    spec = parse_goal_spec(agent or {})
    if spec is None:
        return []
    try:
        result = evaluate_goal_spec(spec, repo_root)
    except Exception:
        return []
    return _fmt(result)
