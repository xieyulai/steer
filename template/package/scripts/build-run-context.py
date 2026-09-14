#!/usr/bin/env python3
"""每轮 auto-run Run Context 快照（brief / keeper / MA-1 / journal / env / round_decision）。"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lib.baseline_anchors_status import has_plain_baseline_tag  # noqa: E402
from lib.ledger_anchor import anchors_dict, format_leader_baseline_lines  # noqa: E402
from lib.reflect_index import parse_pending_cells  # noqa: E402
from lib.run_ledger_summary import (  # noqa: E402
    _try_load_contract,
    build_summary,
    format_brief,
    format_floor_progress_line,
    format_goal_progress_line,
    format_goal_matrix_lines,
    should_show_goal_matrix,
    format_keeper_status,
    format_recent_ledger_window,
    run_context_recent_rows,
    tsv_rows,
)
from lib.gpu_snapshot import (  # noqa: E402
    assign_slots,
    format_gpu_table_lines,
    format_slot_assignment_lines,
)
from lib.train_dynamics import read_metrics_series_rows  # noqa: E402

_SENSITIVE_ENV_RE = re.compile(
    r"(KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|AUTH|PRIVATE)",
    re.IGNORECASE,
)
_EXTRA_ENV_VARS = ("NN_TIME_BUDGET", "NN_SEED")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _load_nn_config(repo_root: Path) -> dict[str, Any]:
    """真源：``lib.nn_config.load_nn_config``（preset；坏文件 raise）。"""
    from lib.nn_config import load_nn_config

    return load_nn_config(Path(repo_root).resolve())


def run_context_config(repo_root: Path) -> str:
    """返回 injection_mode（full | off）。"""
    ctx = _load_nn_config(repo_root).get("context") or {}
    if not isinstance(ctx, dict):
        ctx = {}
    mode = str(ctx.get("injection", "full") or "full").strip().lower()
    if mode not in ("full", "off"):
        mode = "full"
    return mode


def run_context_journal_max_entries(repo_root: Path) -> int:
    ctx = _load_nn_config(repo_root).get("context") or {}
    if not isinstance(ctx, dict):
        ctx = {}
    try:
        n = int(ctx.get("journal_max_entries", 15))
    except (TypeError, ValueError):
        n = 15
    return max(1, n)


def _is_sensitive_env(name: str) -> bool:
    return bool(_SENSITIVE_ENV_RE.search(name))


def _resolve_scenario_binding_env_vars(repo_root: Path) -> list[str]:
    agent = _load_nn_config(repo_root).get("agent") or {}
    if not isinstance(agent, dict):
        return []
    raw = agent.get("scenario_bindings")
    if isinstance(raw, list) and raw:
        return [
            str(x.get("env_var", "") or "").strip()
            for x in raw
            if isinstance(x, dict) and str(x.get("env_var", "") or "").strip()
        ]
    contract = _try_load_contract(repo_root)
    if contract is None:
        return []
    root_str = str(repo_root.resolve())
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    try:
        from experiment import _resolve_scenario_bindings  # noqa: WPS433

        return [b["env_var"] for b in _resolve_scenario_bindings(agent, contract)]
    except Exception:
        cb = getattr(contract, "agent_scenario_bindings", None)
        if callable(cb):
            cb = cb()
        if not cb:
            return []
        out: list[str] = []
        for x in cb:
            if isinstance(x, dict):
                ev = str(x.get("env_var", "") or "").strip()
                if ev:
                    out.append(ev)
        return out


def _env_snapshot_lines(repo_root: Path) -> list[str]:
    cfg = _load_nn_config(repo_root)
    lines: list[str] = []
    seen: set[str] = set()

    def add(name: str, value: str | None) -> None:
        if not name or name in seen or _is_sensitive_env(name):
            return
        seen.add(name)
        if value is None or value == "":
            lines.append(f"{name}=(unset)")
        else:
            lines.append(f"{name}={value}")

    for ev in _resolve_scenario_binding_env_vars(repo_root):
        add(ev, os.environ.get(ev, "").strip() or None)

    tb = os.environ.get("NN_TIME_BUDGET", "").strip()
    if not tb:
        tb = str(cfg.get("time_budget", "") or "").strip()
    add("NN_TIME_BUDGET", tb or None)

    seed = os.environ.get("NN_SEED", "").strip()
    if not seed:
        seed = str(cfg.get("seed", "") or "").strip()
    add("NN_SEED", seed or None)

    for name in _EXTRA_ENV_VARS:
        if name in seen:
            continue
        add(name, os.environ.get(name, "").strip() or None)

    if not lines:
        lines.append("(无 scenario_bindings 白名单 env)")
    return lines


def _format_ma1_brief_oneline(repo_root: Path) -> str:
    try:
        from lib.metric_analysis import format_ma1_brief_oneline  # noqa: WPS433

        return format_ma1_brief_oneline(repo_root)
    except Exception:
        return "(MA-1 不可用)"


def _format_e_feedback_line(repo_root: Path) -> str:
    """改题待办 pending 条数；无 pending → 「无改题待审」（纯提示，不阻塞）。"""
    try:
        from lib.e_feedback_store import pending_count  # noqa: WPS433

        n = pending_count(repo_root)
    except Exception:
        n = 0
    if n > 0:
        return f"有改题待审：{n} 条"
    return "无改题待审"


# --- PDH: Plain-Discovery Heuristic (2026-07-06 spec §4.2) -------------------
# 3 个 helper:_state_plain_anchor_value / _emit_plain_anchor_init / _emit_plain_anchor_check
# 在 format_run_context_md 函数 metric floor emit 之后被调用;非触发轮 0 字节。


def _load_baseline_start_intent(ctx: dict[str, Any]) -> dict[str, Any] | None:
    """读 saved/baseline_start_intent.json（O3-baseline-anchors 落盘；无则 None）。"""
    root = ctx.get("repo_root")
    if not isinstance(root, Path):
        return None
    p = root / "saved" / "baseline_start_intent.json"
    if not p.is_file():
        return None
    try:
        d = json.loads(_read_text(p))
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def _intent_wants_plain(intent: dict[str, Any] | None) -> bool:
    """intent 缺省视为要 plain（兼容无 O3 旧仓）；显式 skip 则否。"""
    if intent is None:
        return True
    if intent.get("plain_first") is False:
        return False
    sr = str(intent.get("start_runs") or "").lower()
    if sr in ("skip", "none", "reference", "reference_number"):
        return False
    if "plain" in sr or intent.get("plain_first") is True:
        return True
    # start_runs 未写但 plain_first 缺省 → 要
    return intent.get("plain_first", True) is not False


def _intent_wants_reference_run(intent: dict[str, Any] | None) -> bool:
    if not intent:
        return False
    if intent.get("reference_run") is True:
        return True
    sr = str(intent.get("start_runs") or "").lower().strip()
    if sr in ("reference_number", "number"):
        return False
    return "reference" in sr


def _pdh_bas_first_round(ctx: dict[str, Any]) -> bool:
    """BAS 第一轮主动触发判定:round==1 ∧ 仓尚未建 plain_anchor。

    设计意图(v0 2026-07-07):让新业务仓在 round==1 即被启发跑一次 plain 基线,
    避免后续只在 WPL(平台期/切场景/倒退)时回头补救。
    与 _emit_plain_anchor_init 原有「仓无 plain_anchor 即发 init 段」的被动路径
    语义等价但来源不同:被动路径无文件 IO 信号、主动路径用 ctx.run 显式注入。
    O3-baseline-anchors：若 intent 显式跳过 plain，则不发 FIRST-ROUND 强提示。
    """
    run = ctx.get("run")
    if run != 1:
        return False
    intent = _load_baseline_start_intent(ctx)
    if not _intent_wants_plain(intent):
        return False
    root = ctx.get("repo_root")
    if not isinstance(root, Path):
        return False
    scenario_id = str(intent["scenario_id"]) if intent and intent.get("scenario_id") else None
    return not has_plain_baseline_tag(root, scenario_id=scenario_id)


def _state_plain_anchor_value(ctx: dict[str, Any]) -> float | None:
    """读 plain_anchor_value。先查 saved/plain_anchor.json;fallback 解析 EXPERIENCE.md Tier 矩阵 P 行。"""
    root = ctx.get("repo_root")
    if not isinstance(root, Path):
        return None
    p = root / "saved" / "plain_anchor.json"
    if p.is_file():
        try:
            d = json.loads(_read_text(p))
            v = d.get("plain_anchor_value")
            if isinstance(v, (int, float)):
                return float(v)
        except Exception:
            pass
    exp = root / "EXPERIENCE.md"
    if exp.is_file():
        text = exp.read_text(encoding="utf-8")
        m = re.search(r"^## Tier 状态.*?\n(.*?)(?=^## |\Z)", text, re.M | re.S)
        if m:
            for line in m.group(1).splitlines():
                if not line.startswith("|"):
                    continue
                cells = [c.strip() for c in line.strip("|").split("|")]
                if len(cells) < 6:
                    continue
                # 末列 = plain(P) 列
                last = cells[-1]
                mm = re.search(r"plain_anchor_value\s*=\s*([\-+]?\d+(?:\.\d+)?(?:[eE][\-+]?\d+)?)", last)
                if mm:
                    try:
                        return float(mm.group(1))
                    except ValueError:
                        return None
    return None


def _state_reference_anchor_value(ctx: dict[str, Any]) -> float | None:
    """读 reference_anchor_value（外部/已发表公开最优）。

    ③-i 落地：镜像 _state_plain_anchor_value 读链。
    1) 先查 saved/reference_anchor.json（可选只读，照 plain :195 模式，无代码写它）；
    2) fallback regex 解析 EXPERIENCE.md「基线锚点（external reference）」段的 reference_anchor_value。
    novel/无公开参照 → 段缺失 → None（常态非缺失）。
    """
    root = ctx.get("repo_root")
    if not isinstance(root, Path):
        return None
    p = root / "saved" / "reference_anchor.json"
    if p.is_file():
        try:
            d = json.loads(_read_text(p))
            v = d.get("reference_anchor_value")
            if isinstance(v, (int, float)):
                return float(v)
        except Exception:
            pass
    exp = root / "EXPERIENCE.md"
    if exp.is_file():
        text = exp.read_text(encoding="utf-8")
        m = re.search(r"^## 基线锚点.*?\n(.*?)(?=^## |\Z)", text, re.M | re.S)
        if m:
            mm = re.search(
                r"reference_anchor_value\s*[:：=]\s*([\-+]?\d+(?:\.\d+)?(?:[eE][\-+]?\d+)?)",
                m.group(1),
            )
            if mm:
                try:
                    return float(mm.group(1))
                except ValueError:
                    return None
    return None


def _emit_baseline_anchors(ctx: dict[str, Any]) -> str:
    """靶子段：plain / reference / 当前最佳 + 差值（正=已超，对齐 _goal_gap 语义）。

    始终返回（公告栏稳定段）；plain 无值显示「未标定」，reference ② 桩恒 None。
    当前最佳 = anchors_dict(repo_root).metric_leader.value（仓内 internal SOTA，无则 None）。
    """
    root = ctx.get("repo_root")
    plain = _state_plain_anchor_value(ctx)
    ref = _state_reference_anchor_value(ctx)

    def _f(v: float) -> str:
        return f"{v:.4f}"

    cur: float | None = None
    if isinstance(root, Path):
        anchors = anchors_dict(root) or {}
        ml = anchors.get("metric_leader") or {}
        v = ml.get("value")
        if isinstance(v, (int, float)):
            cur = float(v)

    def _gap_tag(cur_v: float, anchor_v: float) -> str:
        gap = cur_v - anchor_v  # 对齐 _goal_gap(current, anchor, ">=")：正=已超
        return f"当前最佳已超 +{_f(gap)}" if gap >= 0 else f"当前最佳还差 {_f(-gap)}"

    lines = ["## 基线靶子 (baseline anchors)"]
    if plain is None:
        lines.append("- plain: 未标定")
    elif cur is None:
        lines.append(f"- plain: {_f(plain)}")
    else:
        lines.append(f"- plain: {_f(plain)} — {_gap_tag(cur, plain)}")
    if ref is None:
        lines.append("- reference: 未标定（novel/无公开参照）")
    elif cur is None:
        lines.append(f"- reference: {_f(ref)}")
    else:
        lines.append(f"- reference: {_f(ref)} — {_gap_tag(cur, ref)}")
    lines.append("- 当前最佳: " + (_f(cur) if cur is not None else "（无实验记录）"))
    return "\n".join(lines)


def _pdh_wpl_triggered(ctx: dict[str, Any]) -> bool:
    """WPL trigger:plateau_streak ≥ agent.plateau_rounds || scenario 切 || fancy<plain。

    plain_anchor_value 直接从 ctx 读(由调用方 build_run_context 注入),不重新解析文件;
    减少 IO,且对齐 trigger 字段来源。
    """
    plateau_streak = ctx.get("plateau_streak")
    plateau_rounds = ctx.get("agent_plateau_rounds")
    if (
        isinstance(plateau_streak, (int, float))
        and isinstance(plateau_rounds, (int, float))
        and plateau_streak >= plateau_rounds
    ):
        return True
    prev = ctx.get("prev_scenario_id")
    cur = ctx.get("current_scenario_id")
    if prev and cur and prev != cur:
        return True
    plain = ctx.get("plain_anchor_value")
    if plain is None:
        # fallback:从 saved/EXPERIENCE 解析(给首次 trigger 时 ctx 字段未注入的场景)
        plain = _state_plain_anchor_value(ctx)
    cur_metric = ctx.get("current_metric")
    if plain is not None and isinstance(cur_metric, (int, float)) and cur_metric < plain:
        return True
    return False


def _emit_plain_anchor_init(ctx: dict[str, Any]) -> str | None:
    """BAS trigger:仓无 plain_anchor 时返回 plain-anchor-init 段文本。

    主动路径(round==1 + 仓无 plain):显式标注「首轮 mandatory」,强制 agent 跑 plain。
    被动路径(round>=2 + 仓无 plain):保留原始文本,作为撞墙/跨场景兜底。
    注:TSV 已有 baseline_tag=plain 时返回 None,不重复发起（EXPERIENCE 锚值 alone 不挡）。
    intent 显式跳过 plain 且非 WPL 被动补救路径：round==1 不发；round>=2 无锚仍发兜底段。
    """
    root = ctx.get("repo_root")
    if not isinstance(root, Path):
        return None
    intent = _load_baseline_start_intent(ctx)
    scenario_id = str(intent["scenario_id"]) if intent and intent.get("scenario_id") else None
    if has_plain_baseline_tag(root, scenario_id=scenario_id):
        return None
    if not _intent_wants_plain(intent) and ctx.get("run") == 1:
        return None
    recipe_hint = ""
    if intent:
        bits = []
        if intent.get("plain_recipe"):
            bits.append(f"plain_recipe={intent['plain_recipe']}")
        if intent.get("plain_budget"):
            bits.append(f"plain_budget={intent['plain_budget']}")
        if intent.get("scenario_id"):
            bits.append(f"scenario_id={intent['scenario_id']}")
        if bits:
            recipe_hint = "按 init 口径：" + "; ".join(str(b) for b in bits) + "。\n"
    if _pdh_bas_first_round(ctx):
        return (
            "### plain-anchor-init (FIRST-ROUND, round=1)\n"
            "本仓刚开局，plain 朴素基线尚未建立（主动触发，非阻塞但强烈建议跑）。\n"
            f"{recipe_hint}"
            "Agent 须做 PDH 自悟:用 PDH 6 原则 "
            "(P1 弱于 random / P2 朴素经济 / P3 领域 worst sane baseline / "
            "P4 一眼看可解释 / P5 plain_why 必写 / P6 预算感知，见 base-prompt step 5 段) "
            "推 plain_recipe（根据 contract / profile / 数据形态 + 预算约束），"
            "跑 1 轮 plain（baseline_tag=plain），写 plain_anchor_value 到 EXPERIENCE Tier 矩阵 P 行。\n"
            "首轮命中，WPL trigger（plateau / 切场景 / fancy<plain）后续会自动校验。\n"
        )
    return (
        "### plain-anchor-init\n"
        f"{recipe_hint}"
        "本仓还没建立 plain_anchor。Agent 须先做 PDH 自悟：用 PDH 6 原则 "
        "(P1 弱于 random / P2 朴素经济 / P3 领域 worst sane baseline / "
        "P4 一眼看可解释 / P5 plain_why 必写 / P6 预算感知，见 base-prompt step 5 段) "
        "推 plain_recipe（根据 contract / profile / 数据形态 + 预算约束），"
        "跑 1 轮 plain，写 plain_anchor_value 到 EXPERIENCE Tier 矩阵 P 行。"
        "注：启发式，非阻塞，业务仓可跳过。\n"
    )


def _has_reference_run_signal(ctx: dict[str, Any]) -> bool:
    """粗判本仓是否已有 reference 实跑或对齐发表分。"""
    if _state_reference_anchor_value(ctx) is not None:
        return True
    root = ctx.get("repo_root")
    if not isinstance(root, Path):
        return False
    tsv = root / "_runs" / "results.tsv"
    if not tsv.is_file():
        return False
    try:
        text = tsv.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    lines = text.splitlines()
    if len(lines) < 2:
        return False
    headers = [h.strip() for h in lines[0].split("\t")]
    if "baseline_tag" not in headers:
        return False
    i = headers.index("baseline_tag")
    for row in lines[1:]:
        cells = row.split("\t")
        if len(cells) > i and cells[i].strip() == "reference":
            return True
    return False


def _emit_reference_start(ctx: dict[str, Any]) -> str | None:
    """满 10 轮仍无公开对照 → 注入必做段；已有标签/锚值则不发。"""
    root = ctx.get("repo_root")
    if not isinstance(root, Path):
        return None
    try:
        from lib.baseline_stamp import should_emit_reference_start
        from lib.ledger_anchor import focus_scenario_id
    except ImportError:
        return None
    sid = ""
    try:
        sid = (focus_scenario_id(root) or "").strip()
    except Exception:
        sid = ""
    if not should_emit_reference_start(root, sid or None):
        return None
    return (
        "### reference-anchor-init\n"
        "已满 10 轮仍无公开对照。本轮必须立尺：走 /auto-nn-reference 流程"
        "（先反思找公开方法；找不到则从已有成绩按当前最好与朴素下界的中点挑一行）。\n"
        "文献尺须本机原仓校准过线才可贴 --source literature；未过线禁止贴文献尺，"
        "本轮写清先校准或先修配方。否则中点代用（--source ledger_midpoint）可自动贴，不等人确认。\n"
        "禁止把当前最好或已是朴素下界的那一行贴成公开对照。贴上后衍生轮标签必须是 none。\n"
    )


def _emit_plain_anchor_check(ctx: dict[str, Any]) -> str | None:
    """WPL trigger 命中时返回 plain-anchor-check 段文本。"""
    if not _pdh_wpl_triggered(ctx):
        return None
    return (
        "### plain-anchor-check\n"
        "撞墙 / 切场景 / fancy<plain (WPL trigger)。Agent 须重新推 plain 并三分支决策:\n"
        "  - plain < best → fancy 有效但耗尽 → 升档（见 PROTOCOL §7.5.1）\n"
        "  - plain ≈ best → 撞 plain 墙 → 收手或换 baseline\n"
        "  - plain > best → SBN 派生，fancy 有 bug → DISCARD 本轮回退 plain\n"
        "写 plain_why 重审（若 WPL 触发而非 BAS 触发，plain_why 必填解释）。\n"
    )


# --- end PDH --------------------------------------------------------------


def _emit_audit_card(root: Path) -> str | None:
    """有审查卡片才返回 ### audit-card 段；无卡片整节省略。"""
    try:
        from lib.audit_core import format_audit_card_body, injection_for_scenario
        from lib.scenario_inventory import focus_scenario_id
    except ImportError:
        return None
    try:
        sid = (focus_scenario_id(root) or "").strip()
        if not sid:
            return None
        inj = injection_for_scenario(root, sid)
        if not inj:
            return None
        body = format_audit_card_body(root, inj)
        if not body:
            return None
        return "### audit-card\n" + body
    except Exception:
        return None


def _emit_ablation_hint(ctx: dict[str, Any]) -> str | None:
    """KEEP 且主指标严格改善(≥ keep 阈值)时，注入一句组件归因消融引导(§4.1 路线A)。

    纯插入式：只读 _runs/round_decision.json 的 keep_suggestion/reason/primary_metric，
    复用 OVAT（单变量）通道，不新增技能。reason 含「提升满足阈值/严格改善/↑」即
    should_keep 的严格改善路径（= improvement >= delta，满足「improvement > delta」语义）；
    near_best / 无历史 / explore keep 不含这些标记 → 不触发（非真改善）。
    决策文件缺/损坏/格式漂移 → 静默返回 None（降级，非崩；与 paper_hint 同型 best-effort）。
    """
    root = ctx.get("repo_root")
    if not isinstance(root, Path):
        return None
    for name in ("round_decision.json", "evaluation_result.json"):
        p = root / "_runs" / name
        if not p.is_file():
            continue
        try:
            d = json.loads(_read_text(p))
        except Exception:
            return None
        ks = d.get("keep_suggestion")
        if isinstance(ks, dict):
            decision = str(ks.get("decision", ks.get("action", ""))).lower()
        elif isinstance(ks, bool):
            decision = "keep" if ks else "discard"
        else:
            decision = str(ks or "").lower()
        if decision != "keep":
            return None
        reason = str(d.get("reason") or "")
        if not any(m in reason for m in ("提升满足阈值", "严格改善", "↑")):
            return None  # KEEP 但非严格改善 → 不引导
        pm = d.get("primary_metric") or {}
        key = str(pm.get("key") or "primary")
        value = pm.get("value")
        val_tail = f"={value:.4f}" if isinstance(value, (int, float)) else ""
        return (
            "### ablation-hint (KEEP 且严格改善)\n"
            f"本轮 KEEP（主指标 {key}{val_tail} 较历史最佳严格改善，超过 keep 阈值）。"
            "建议下一步做**组件归因消融**（OVAT 单变量）：逐个关掉本轮新增/改动的组件，"
            "各跑一次对照，确认哪个组件真正贡献了这次提升——避免把运气当方法，也定位后续优化重点。"
            "复用 OVAT 通道（`/auto-nn-auto-run` 或 `/auto-nn-manual-run` 单键改动），不新增技能；"
            "启发式，非阻塞。\n"
        )
    return None


def _format_journal_tail(repo_root: Path) -> list[str]:
    from lib.experiment_journal import journal_path, read_journal  # noqa: WPS433

    max_entries = run_context_journal_max_entries(repo_root)
    path = journal_path(repo_root)
    if not path.is_file():
        return ["(无 experiment_journal.json)"]
    journal = read_journal(path)
    entries = journal.get("entries") or []
    if not entries:
        return ["(entries 为空)"]
    lines: list[str] = []
    for entry in entries[-max_entries:]:
        if not isinstance(entry, dict):
            continue
        kind = str(entry.get("kind") or "?")
        ts = str(entry.get("ts") or "")
        exp = str(entry.get("experiment") or "").strip()
        decision = str(entry.get("decision") or "").strip()
        summary = str(entry.get("summary") or "").strip()
        note = str(entry.get("note") or "").strip()
        parts = [f"[{ts}] {kind}"]
        if exp:
            parts.append(f"exp={exp}")
        if decision and decision != "-":
            parts.append(f"decision={decision}")
        if summary:
            parts.append(f"summary={summary}")
        if note:
            parts.append(f"note={note[:120]}")
        lines.append(" ".join(parts))
    return lines if lines else ["(entries 为空)"]


def _format_last_recommendation_line(repo_root: Path) -> str | None:
    from lib.experiment_journal import journal_path, read_journal  # noqa: WPS433

    path = journal_path(repo_root)
    if not path.is_file():
        return None
    rec = (read_journal(path).get("analyse") or {}).get("last_recommendation")
    if not isinstance(rec, dict):
        return None
    summary = str(rec.get("summary") or "").strip()
    if not summary:
        return None
    return f"last_recommendation: {summary}"


def _format_round_decision_line(repo_root: Path) -> str:
    for name in ("round_decision.json", "evaluation_result.json"):
        p = repo_root / "_runs" / name
        if not p.is_file():
            continue
        try:
            d = json.loads(_read_text(p))
        except Exception:
            return f"(无法解析 {name})"
        ks = d.get("keep_suggestion")
        if isinstance(ks, dict):
            decision = str(ks.get("decision", ks.get("action", ""))).lower()
        elif isinstance(ks, bool):
            decision = "keep" if ks else "discard"
        else:
            decision = str(ks or "").lower()
        reason = str(d.get("reason") or "").strip()
        if len(reason) > 200:
            reason = reason[:197] + "..."
        exp = str(d.get("evaluated_exp_dir") or d.get("keeper_exp_dir") or "")
        exp_base = Path(exp).name if exp else "?"
        parts = [f"keep_suggestion={decision or '?'}", f"exp={exp_base}"]
        if reason:
            parts.append(f"reason={reason}")
        return " ".join(parts)
    return "(无 round_decision.json)"


def _format_round_paper_hint(repo_root: Path) -> str | None:
    """读 round_decision.json 的 paper_hint（字段注入载体；spec §4 主体闭环）。

    外部证据「随 round_decision 落盘 → 注入下轮 step1」：本函数从决策文件读回 paper_hint，
    与 _format_round_decision_line 同文件优先级；空/缺/损坏 → None（下轮不注入该段）。
    注意：与 bundle-direct 的 `_last_external_lines`（FYI）是不同通道——这里读决策落盘字段。
    """
    for name in ("round_decision.json", "evaluation_result.json"):
        p = repo_root / "_runs" / name
        if not p.is_file():
            continue
        try:
            d = json.loads(_read_text(p))
        except Exception:
            return None
        hint = str(d.get("paper_hint") or "").strip()
        return hint or None
    return None


def _render_find_candidates(fc: dict) -> str | None:
    """find_candidates dict → markdown 块（下轮 agent 可读的候选部件清单）。

    无论文候选/生态候选/代码片段/方法段 → None（本轮虽触发但没捞到可借力的东西，不注入）。
    """
    paper: list[str] = []
    for cand in (fc.get("paper_candidates") or [])[:5]:
        if not isinstance(cand, dict):
            continue
        title = str(cand.get("title") or "").strip()
        if not title:
            continue
        url = str(cand.get("url") or "").strip()
        aid = str(cand.get("arxiv_id") or "").strip()
        tag = f" [{aid}]" if aid else ""
        paper.append(f"- 论文：{title}{tag}" + (f"（{url}）" if url else ""))
    method = str(fc.get("method_excerpt") or "").strip()
    hints = [
        f"- 实现信号：{str(h).strip()}"
        for h in (fc.get("impl_hints") or [])[:5]
        if str(h).strip()
    ]
    eco: list[str] = []
    for c in (fc.get("ecosystem_candidates") or [])[:5]:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name") or "").strip()
        if not name:
            continue
        url = str(c.get("url") or "").strip()
        desc = str(c.get("description") or "").strip()
        eco.append(
            f"- 生态库：{name}"
            + (f"（{url}）" if url else "")
            + (f" — {desc}" if desc else "")
        )
    # T9/ADR-9：linked_code raw 片段 → 代码候选（P3+ 抓的 top impl_candidate 实际代码，
    # 喂下轮作借力素材；与论文/生态候选同注 find_candidates 块）。
    code: list[str] = []
    for c in (fc.get("code_candidates") or [])[:5]:
        if not isinstance(c, dict):
            continue
        repo = str(c.get("repo") or "").strip()
        path = str(c.get("path") or "").strip()
        if not repo and not path:
            continue
        url = str(c.get("url") or "").strip()
        excerpt = str(c.get("excerpt") or "").strip()
        label = path or repo
        src = f"（{repo}）" if repo and repo != label else ""
        code.append(
            f"- 代码：{label}{src}"
            + (f"（{url}）" if url else "")
            + (f" — {excerpt[:200]}" if excerpt else "")
        )
    if not paper and not eco and not code and not method:
        return None
    lines: list[str] = []
    depth = str(fc.get("depth") or "").strip()
    if depth:
        lines.append(f"depth: {depth}")
    lines.extend(paper)
    if method:
        lines.append(f"方法段：{method[:400]}")
    lines.extend(hints)
    lines.extend(eco)
    lines.extend(code)
    return "\n".join(lines)


def _format_round_find_candidates(repo_root: Path) -> str | None:
    """读 round_decision.json 的 find_candidates（T4/ADR-6 反馈边载体）。

    寻找阶段（撞墙 ∧ depth∈{different,novel}）捞的可借力候选部件 → 注入下轮 step1。
    与 paper_hint 同走「round_decision 字段注入」通道；空/缺/未触发/无候选 → None。
    """
    for name in ("round_decision.json", "evaluation_result.json"):
        p = repo_root / "_runs" / name
        if not p.is_file():
            continue
        try:
            d = json.loads(_read_text(p))
        except Exception:
            return None
        fc = d.get("find_candidates") or {}
        if not isinstance(fc, dict) or not fc.get("triggered"):
            return None
        return _render_find_candidates(fc)
    return None


_KEEPER_RECIPE_KEYS = (
    "MODEL_ARCH",
    "LOSS",
    "OBJECTIVE",
    "SCHEDULER",
    "AUGMENT",
    "MIXUP_ALPHA",
)


def _format_keeper_recipe_keys(repo_root: Path) -> list[str] | None:
    try:
        from lib.ledger_anchor import code_baseline_entry, focus_scenario_id  # noqa: WPS433
    except ImportError:
        return None
    baseline = code_baseline_entry(repo_root)
    if baseline is None or not baseline.keeper_exp_dir:
        return None
    # v2.7.4: keeper_exp_dir 存相对 repo_root; join repo_root 定位 config.json
    _kd = baseline.keeper_exp_dir
    _kp = Path(_kd) if Path(_kd).is_absolute() else (repo_root / _kd)
    cfg_path = _kp / "config.json"
    if not cfg_path.is_file():
        return None
    try:
        data = json.loads(_read_text(cfg_path))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    try:
        sid = focus_scenario_id(repo_root)
    except Exception:
        sid = "default"
    parts = [f"scenario={sid}", f"exp_dir={Path(baseline.keeper_exp_dir).name}"]
    for key in _KEEPER_RECIPE_KEYS:
        if key in data and str(data[key]).strip():
            parts.append(f"{key}={data[key]}")
    if len(parts) <= 2:
        return None
    return parts


def _has_reflect_pending(repo_root: Path) -> bool:
    idx = repo_root / "references" / "REFLECT_INDEX.md"
    if not idx.is_file():
        return False
    return parse_pending_cells(_read_text(idx)) is not None


def _format_external_skipped_summary(skipped: list[Any]) -> str:
    parts: list[str] = []
    for s in skipped[:5]:
        if not isinstance(s, dict):
            continue
        provider = str(s.get("provider") or "?").strip()
        reason = str(s.get("reason") or "").strip()
        parts.append(f"{provider}:{reason}" if reason else provider)
    return ",".join(parts)


def _last_external_lines(repo_root: Path) -> list[str]:
    """末次 reflect 外部检索 FYI（仅 bundle 与 reflect_latest reflect_id 一致时）。"""
    saved = repo_root / "saved"
    bundle_path = saved / "evidence_bundle.json"
    latest_path = saved / "reflect_latest.json"
    if not bundle_path.is_file() or not latest_path.is_file():
        return []
    try:
        bundle = json.loads(_read_text(bundle_path))
        latest = json.loads(_read_text(latest_path))
    except Exception:
        return []
    if not isinstance(bundle, dict) or not isinstance(latest, dict):
        return []

    bundle_rid = str(bundle.get("reflect_id") or "").strip()
    if not bundle_rid:
        return []

    latest_rid = str(latest.get("reflect_id") or "").strip()
    ext = latest.get("external") if isinstance(latest.get("external"), dict) else {}
    ext_rid = str(ext.get("reflect_id") or "").strip()
    if bundle_rid != latest_rid and bundle_rid != ext_rid:
        return []

    paper = bundle.get("paper") if isinstance(bundle.get("paper"), dict) else {}
    hits = paper.get("hits") or []
    hits_count = len(hits) if isinstance(hits, list) else 0
    if hits_count == 0 and isinstance(ext, dict) and ext.get("hits_count") is not None:
        try:
            hits_count = int(ext["hits_count"])
        except (TypeError, ValueError):
            pass

    skipped = (bundle.get("meta") or {}).get("skipped") or []
    if not skipped and isinstance(ext, dict):
        skipped = ext.get("skipped") or []
    if not isinstance(skipped, list):
        skipped = []

    if hits_count == 0:
        return []

    parts = [f"reflect_id={bundle_rid}", f"hits={hits_count}"]
    skipped_s = _format_external_skipped_summary(skipped)
    if skipped_s:
        parts.append(f"skipped={skipped_s}")
    return [" ".join(parts)]


def _reflect_anchors_lines(repo_root: Path) -> list[str]:
    if not _has_reflect_pending(repo_root):
        return []
    anchors = anchors_dict(repo_root)
    if not anchors:
        return []
    lines: list[str] = []
    ml = anchors.get("metric_leader") or {}
    cb = anchors.get("code_baseline") or {}
    if ml:
        lines.append(
            f"metric_leader={ml.get('experiment', '?')} "
            f"{ml.get('metric_key', '?')}={ml.get('value', '?')}"
        )
    if cb:
        lines.append(f"code_baseline={cb.get('experiment', cb.get('exp_dir', '?'))}")
    return lines


def _ledger_context_line(repo_root: Path) -> str | None:
    contract = _try_load_contract(repo_root)
    if contract is None:
        return None
    keys = tuple(getattr(contract, "ledger_context_keys", ()) or ())
    if not keys:
        return None
    try:
        from lib.ledger_anchor import focus_scenario_id  # noqa: WPS433

        sid = focus_scenario_id(repo_root)
    except ImportError:
        sid = str((_load_nn_config(repo_root).get("agent") or {}).get("scenario_default") or "default")
    rows = [
        r
        for r in tsv_rows(repo_root)
        if r.get("experiment") != "preflight_check" and str(r.get("scenario_id") or "") == sid
    ]
    if not rows:
        rows = [r for r in tsv_rows(repo_root) if r.get("experiment") != "preflight_check"]
    if not rows:
        return None
    last = rows[-1]
    parts = [f"{k}={last.get(k, '')}" for k in keys if str(last.get(k, "")).strip()]
    if not parts:
        return None
    return " ".join(parts)


def _render_watchlist_suggestion(ctx: dict[str, Any]) -> str:
    """扫 _runs/exp/*/config.json × 当前 watchlist 差集，输出 top-5 推荐段。
    缺数据 / 解析失败 → 静默返回空（doctor 不 FAIL，仅 skip）。
    仿 _render_abcde_summary() 模式（build-run-context.py:62-91）。"""
    root = Path(ctx.get("repo_root") or Path.cwd())
    nn_cfg_path = root / "nn-config.yaml"
    if not nn_cfg_path.is_file():
        return ""
    try:
        cfg = yaml.safe_load(nn_cfg_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return ""
    watchlist = set((cfg.get("ledger") or {}).get("watchlist") or [])
    if not watchlist and watchlist != set():  # 段存在但空 → 不推荐
        return ""
    cfg_union: Counter = Counter()
    runs_dir = root / "_runs" / "exp"
    if not runs_dir.is_dir():
        return ""
    for cfg_path in runs_dir.glob("*/config.json"):
        try:
            d = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        for k in d:
            if k not in watchlist and not k.startswith("_") and isinstance(d[k], (int, float, str, bool)):
                cfg_union[str(k)] += 1
    if not cfg_union:
        return ""
    top = cfg_union.most_common(5)
    n_runs = sum(1 for _ in runs_dir.glob("*/config.json"))
    lines = ["", f"### 📋 Watchlist 建议（基于 {n_runs} 轮 cfg 扫描）"]
    for k, n in top:
        lines.append(f"- `{k}`（出现 {n}/{n_runs} 次）")
    lines.append("")
    lines.append("如要采纳：`vim nn-config.yaml` 加到 `ledger.watchlist`，然后 `python3 scripts/regen_results_tsv.py --repo-root . --sync-jsonl`")
    return "\n".join(lines)


def _last_data_row(repo_root: Path) -> dict[str, str] | None:
    rows = [r for r in tsv_rows(repo_root) if r.get("experiment") != "preflight_check"]
    return rows[-1] if rows else None


def _format_train_dynamics_block(repo_root: Path) -> dict[str, Any] | None:
    """上一轮 exp 的 train_dynamics 摘要（≤15 行 md；不注入 TSV 全文）。"""
    last = _last_data_row(repo_root)
    if not last:
        return None
    exp_s = str(last.get("exp_dir") or "").strip()
    if not exp_s:
        return None
    exp_dir = Path(exp_s)
    if not exp_dir.is_dir():
        return None

    md_path = exp_dir / "train_dynamics.md"
    dyn_path = exp_dir / "train_dynamics.json"
    block: dict[str, Any] = {
        "exp_dir": exp_s,
        "experiment": str(last.get("experiment") or ""),
    }
    if md_path.is_file():
        md_lines = md_path.read_text(encoding="utf-8", errors="replace").splitlines()
        block["summary_md"] = "\n".join(md_lines[:15])
    elif dyn_path.is_file():
        try:
            block["summary_md"] = json.dumps(json.loads(dyn_path.read_text(encoding="utf-8")), ensure_ascii=False)
        except (json.JSONDecodeError, OSError):
            block["summary_md"] = "(train_dynamics.json 无法解析)"
    else:
        block["summary_md"] = "(无 train_dynamics — 旧 run 或未接 hook)"
        block["n_points"] = 0
        return block

    if dyn_path.is_file():
        try:
            dyn = json.loads(dyn_path.read_text(encoding="utf-8"))
            block["n_points"] = int(dyn.get("n_points") or 0)
            block["plateau"] = (dyn.get("plateau") or {}).get("detected")
            block["train_loss_trend"] = (dyn.get("train_loss") or {}).get("trend")
        except (json.JSONDecodeError, OSError):
            pass

    series_rows = read_metrics_series_rows(exp_dir)
    block["series_path"] = f"{exp_s}/metrics_series.tsv"
    block["series_n_rows"] = len(series_rows)
    return block


def _load_gpu_snapshot_arg(
    *,
    gpu_snapshot: dict[str, Any] | None = None,
    gpu_snapshot_file: Path | None = None,
) -> dict[str, Any] | None:
    if gpu_snapshot is not None:
        return gpu_snapshot
    if gpu_snapshot_file is not None and gpu_snapshot_file.is_file():
        try:
            raw = json.loads(gpu_snapshot_file.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else None
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _batch_scheduling_block(
    *,
    batch_run: int | None,
    batch_total: int | None,
    max_parallel: int | None,
    free_gpus: str | None,
    gpus_whitelist: str | None,
    gpu_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if batch_run is None or batch_total is None or batch_total <= 0:
        return None
    if batch_run < 1:
        batch_run = 1
    remaining = max(0, batch_total - batch_run)
    try:
        mp = int(max_parallel if max_parallel is not None else 1)
    except (TypeError, ValueError):
        mp = 1
    mp = max(1, mp)
    free = (free_gpus or "").strip() or "unknown"
    if isinstance(gpu_snapshot, dict) and gpu_snapshot.get("smi_ok"):
        snap_free = str(gpu_snapshot.get("free_gpus") or "").strip()
        if snap_free:
            free = snap_free
    block: dict[str, Any] = {
        "batch_run": batch_run,
        "batch_total": batch_total,
        "remaining_in_batch": remaining,
        "max_parallel": mp,
        "free_gpus": free,
        "gpus_whitelist": (gpus_whitelist or "").strip() or "auto-detect",
    }
    if isinstance(gpu_snapshot, dict):
        block["gpu_snapshot"] = gpu_snapshot
        block["usable_gpu_count"] = int(gpu_snapshot.get("usable_count") or 0)
        if mp > 1:
            block["slot_assignment"] = assign_slots(gpu_snapshot, mp)
    return block


def _count_free_gpus(free_gpus: str) -> int:
    s = (free_gpus or "").strip()
    if not s or s.lower() == "unknown":
        return -1  # 未知（无法探测）
    return len([x for x in s.split(",") if x.strip()])


def _format_batch_scheduling_lines(block: dict[str, Any]) -> list[str]:
    br = int(block["batch_run"])
    bt = int(block["batch_total"])
    rem = int(block["remaining_in_batch"])
    mp = int(block["max_parallel"])
    snap = block.get("gpu_snapshot")
    if isinstance(snap, dict) and snap.get("smi_ok"):
        free_n = int(snap.get("usable_count") or 0)
    else:
        free_n = _count_free_gpus(str(block["free_gpus"]))
    lines = [
        f"batch_run={br}/{bt}  remaining_in_batch={rem}",
        f"max_parallel={mp}  free_gpus={block['free_gpus']}  gpus_whitelist={block['gpus_whitelist']}",
        (
            "scheduling: 用 batch_run 与 remaining 规划本轮 train 进程数（1..max_parallel）；"
            "本轮若有 ≥2 个各自独立、各自站得住的候选（不同架构/loss/场景/种子）→ 优先并行，别让空闲卡闲置；"
            "多槽并行时各槽不同 CUDA_VISIBLE_DEVICES + NN_SLOT(0..N-1) + 相同 NN_PARALLEL_TOTAL=N，全部 wait 后一次 finalize-round；"
            "每槽仍须单变量；C/D-深单变量、结构大改、batch 末轮优先单槽。"
        ),
    ]
    if isinstance(snap, dict) and snap.get("gpus"):
        lines.extend(format_gpu_table_lines(snap))
        if mp > 1:
            lines.extend(format_slot_assignment_lines(snap, mp))
    if mp > 1 and free_n >= 1:
        cap = min(mp, free_n) if free_n >= 0 else mp
        if free_n >= 2:
            lines.append(
                f"调度提示: 当前可用 GPU≈{free_n}（独占+可共享）且 max_parallel={mp} —— "
                f"有多个独立候选时本轮优先并行（≤{cap} 槽），充分利用算力。"
            )
        elif free_n == 1 and mp >= 2:
            lines.append(
                f"调度提示: 仅 1 张可用卡但 max_parallel={mp} —— 多槽可同卡并行（显存够则设相同 CUDA_VISIBLE_DEVICES）。"
            )
    lines.append(
        f"进程预算: 本 batch 尚余 {rem} 轮实验机会（每轮 batch_run 计 1 次，不论单槽或多槽并行）。"
    )
    return lines


def build_run_context(
    repo_root: Path,
    *,
    run: int = 1,
    batch_run: int | None = None,
    batch_total: int | None = None,
    max_parallel: int | None = None,
    free_gpus: str | None = None,
    gpus_whitelist: str | None = None,
    gpu_snapshot: dict[str, Any] | None = None,
    gpu_snapshot_file: Path | None = None,
) -> dict[str, Any]:
    root = repo_root.resolve()
    warnings: list[str] = []
    if not (root / "_runs" / "results.tsv").is_file():
        warnings.append("WARN: 缺少 _runs/results.tsv")

    summary = build_summary(root, run=run)
    ctx: dict[str, Any] = {
        "brief": format_brief(summary, repo_root=root),
        "keeper_status": format_keeper_status(root),
        "ma1_brief_oneline": _format_ma1_brief_oneline(root),
        "journal_tail": _format_journal_tail(root),
        "round_decision": _format_round_decision_line(root),
        "e_feedback_line": _format_e_feedback_line(root),
        "env": _env_snapshot_lines(root),
        "warnings": warnings,
        "repo_root": root,
        # v0 2026-07-07:_pdh_bas_first_round 读 ctx["run"] 判定 round==1 主动 BAS 触发。
        "run": run,
    }
    # spec §4 主体闭环：round_decision.paper_hint 作字段注入下轮 step1（区别于
    # bundle-direct 的 last_external FYI 通道）。空/缺 → 不注入。
    paper_hint = _format_round_paper_hint(root)
    if paper_hint:
        ctx["paper_hint"] = paper_hint
    # T4/ADR-6 反馈边：round_decision.find_candidates（撞墙∧depth∈{different,novel}
    # 时寻找阶段捞的可借力候选部件）作字段注入下轮 step1。空/缺/未触发/无候选 → 不注入。
    find_candidates = _format_round_find_candidates(root)
    if find_candidates:
        ctx["find_candidates"] = find_candidates
    recent = format_recent_ledger_window(root, k=run_context_recent_rows(root))
    if recent:
        ctx["recent_ledger_window"] = recent
    recipe = _format_keeper_recipe_keys(root)
    if recipe:
        ctx["keeper_recipe_keys"] = recipe
    goal_line = None
    try:
        from lib.run_ledger_summary import (
            format_goal_spec_progress,
            format_goal_progress_line,
        )
        goal_line = format_goal_spec_progress(root)  # v3 优先
        if goal_line is None:
            goal_line = format_goal_progress_line(root)  # v2 兜底
    except Exception:
        from lib.run_ledger_summary import format_goal_progress_line
        goal_line = format_goal_progress_line(root)
    if goal_line:
        ctx["goal_progress"] = goal_line
    if should_show_goal_matrix(root):
        matrix = format_goal_matrix_lines(root)
        if matrix:
            ctx["goal_matrix"] = matrix
    rec_line = _format_last_recommendation_line(root)
    if rec_line:
        ctx["last_recommendation"] = rec_line
    anchors = _reflect_anchors_lines(root)
    if anchors:
        ctx["reflect_anchors"] = anchors
    last_ext = _last_external_lines(root)
    if last_ext:
        ctx["last_external"] = last_ext
    ledger = _ledger_context_line(root)
    if ledger:
        ctx["ledger_context"] = ledger
    td = _format_train_dynamics_block(root)
    if td:
        ctx["train_dynamics"] = td
    try:
        from lib.explore_objective import effective_objective, format_coverage_brief  # noqa: WPS433

        res = effective_objective(root)
        if res.mode == "explore" and not res.migration_blocked:
            ctx["coverage_brief"] = format_coverage_brief(root)
            floor_line = format_floor_progress_line(root)
            if floor_line:
                ctx["metric_floor_progress"] = floor_line
    except ImportError:
        pass
    snap = _load_gpu_snapshot_arg(
        gpu_snapshot=gpu_snapshot,
        gpu_snapshot_file=gpu_snapshot_file,
    )
    batch = _batch_scheduling_block(
        batch_run=batch_run,
        batch_total=batch_total,
        max_parallel=max_parallel,
        free_gpus=free_gpus,
        gpus_whitelist=gpus_whitelist,
        gpu_snapshot=snap,
    )
    if batch:
        ctx["batch_scheduling"] = batch
    if snap:
        ctx["gpu_snapshot"] = snap
    if not batch and not snap:
        persisted = _load_persisted_batch_fields(root)
        if persisted.get("batch_scheduling"):
            ctx["batch_scheduling"] = persisted["batch_scheduling"]
        if persisted.get("gpu_snapshot"):
            ctx["gpu_snapshot"] = persisted["gpu_snapshot"]
    # Agent 回答语言（context.language；"auto"/空=不提示）
    ctx_cfg = _load_nn_config(repo_root).get("context") or {}
    if not isinstance(ctx_cfg, dict):
        ctx_cfg = {}
    ctx["agent_language"] = str(ctx_cfg.get("language") or "").strip()
    return ctx


def format_run_context_md(ctx: dict[str, Any]) -> str:
    lines = [
        "=== RUN CONTEXT（auto-run 每轮注入；事实快照，优先于 Agent 臆测）===",
        "",
    ]
    # 语言提示（仅当显式配置时注入；auto=不提示）
    lang = str(ctx.get("agent_language") or "").strip()
    if lang and lang.lower() != "auto":
        lines.extend([f"### language（Agent 回答语种）", f"{lang}", ""])
    batch = ctx.get("batch_scheduling")
    if isinstance(batch, dict):
        lines.extend(["### batch（编排位置 · 分配 train 进程/槽位）", *_format_batch_scheduling_lines(batch), ""])
    lines.extend([
        "### 台账 brief",
        str(ctx.get("brief") or ""),
        "",
    ])
    recent = ctx.get("recent_ledger_window") or []
    if recent:
        lines.extend([
            "### recent ledger window（近 K 行；事实陈述，非阶段建议）",
            *recent,
            "",
        ])
    lines.extend([
        "### keeper-status",
        "\n".join(ctx.get("keeper_status") or []),
        "",
    ])
    root = ctx.get("repo_root")
    if isinstance(root, Path):
        audit_md = _emit_audit_card(root)
        if audit_md:
            lines.extend(["", audit_md])
    recipe = ctx.get("keeper_recipe_keys") or []
    if recipe:
        lines.extend([
            "### keeper recipe keys（只读摘要）",
            " ".join(recipe),
            "",
        ])
    lines.extend([
        "### MA-1 brief-oneline",
        str(ctx.get("ma1_brief_oneline") or ""),
        "",
    ])
    goal_progress = ctx.get("goal_progress")
    if goal_progress:
        lines.extend([
            "### goal progress",
            str(goal_progress),
            "",
        ])
    goal_matrix = ctx.get("goal_matrix") or []
    if goal_matrix:
        lines.extend([
            "### goal matrix（多场景）",
            "\n".join(goal_matrix),
            "",
        ])
    lines.extend([
        "### journal（最近 entries）",
        "\n".join(ctx.get("journal_tail") or []),
        "",
        "### round_decision",
        str(ctx.get("round_decision") or ""),
        "",
        "### 改题待审",
        str(ctx.get("e_feedback_line") or "无改题待审"),
        "",
        "### env（scenario_bindings 白名单）",
        "\n".join(ctx.get("env") or []),
    ])
    # ablation-hint：KEEP 且严格改善 → 注入组件归因消融引导（§4.1 路线A，纯插入式）
    ablation_hint = _emit_ablation_hint(ctx)
    if ablation_hint is not None:
        lines.extend(["", ablation_hint])
    paper_hint = ctx.get("paper_hint")
    if paper_hint:
        lines.extend([
            "",
            "### paper_hint（本轮外部证据方法摘要 · 字段注入，非文献真源）",
            str(paper_hint),
        ])
    find_candidates = ctx.get("find_candidates")
    if find_candidates:
        lines.extend([
            "",
            "### find_candidates（上轮寻找捞的可借力候选部件 · 撞墙反馈边）",
            str(find_candidates),
        ])
    anchors = ctx.get("reflect_anchors") or []
    if anchors:
        lines.extend(["", "### reflect anchors（pending 时）", *anchors])
    last_ext = ctx.get("last_external") or []
    if last_ext:
        lines.extend(["", "### 上轮外部证据（仅供参考，非文献真源）", *last_ext])
    rec = ctx.get("last_recommendation")
    if rec:
        lines.extend(["", "### last_recommendation", str(rec)])
    ledger = ctx.get("ledger_context")
    if ledger:
        lines.extend(["", "### ledger_context（focus 末行）", str(ledger)])
    td = ctx.get("train_dynamics")
    if td:
        lines.extend(["", "### train_dynamics（上轮）"])
        lines.append(str(td.get("summary_md") or ""))
        if td.get("series_path"):
            lines.append(
                f"series: {td['series_path']} (n_rows={td.get('series_n_rows', '?')})"
            )
    coverage = ctx.get("coverage_brief") or []
    if coverage:
        lines.extend(["", "### coverage brief（explore）", *coverage])
    floor_progress_line = ctx.get("metric_floor_progress")
    if floor_progress_line:
        lines.extend(["", "### metric floor（explore 护栏）", str(floor_progress_line)])
    # ② 层1：基线靶子段（plain / reference / 当前最佳）
    lines.extend(["", _emit_baseline_anchors(ctx)])
    # PDH: plain-anchor-init (BAS) + plain-anchor-check (WPL)
    plain_init = _emit_plain_anchor_init(ctx)
    if plain_init is not None:
        lines.extend(["", plain_init])
    plain_check = _emit_plain_anchor_check(ctx)
    if plain_check is not None:
        lines.extend(["", plain_check])
    ref_start = _emit_reference_start(ctx)
    if ref_start is not None:
        lines.extend(["", ref_start])
    for w in ctx.get("warnings") or []:
        lines.extend(["", str(w)])
    # 现有末尾 extend 后追加：
    watchlist_suggestion = _render_watchlist_suggestion(ctx)
    if watchlist_suggestion:
        lines.extend(watchlist_suggestion.splitlines())
    lines.extend(["", "=== END RUN CONTEXT ==="])
    return "\n".join(lines)


def _load_persisted_batch_fields(repo_root: Path) -> dict[str, Any]:
    """nn-doctor 等无 batch/gpu 参数 --write 时，保留上轮 auto-run 写入的快照。"""
    json_path = repo_root.resolve() / "saved" / "run_context.json"
    if not json_path.is_file():
        return {}
    try:
        prev = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(prev, dict):
        return {}
    out: dict[str, Any] = {}
    if isinstance(prev.get("batch_scheduling"), dict):
        out["batch_scheduling"] = prev["batch_scheduling"]
    if isinstance(prev.get("gpu_snapshot"), dict):
        out["gpu_snapshot"] = prev["gpu_snapshot"]
    if not out.get("gpu_snapshot"):
        snap_path = repo_root.resolve() / "saved" / "gpu_last_snapshot.json"
        if snap_path.is_file():
            try:
                snap = json.loads(snap_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                snap = None
            if isinstance(snap, dict) and snap:
                out["gpu_snapshot"] = snap
    return out


def write_run_context(
    repo_root: Path,
    *,
    run: int = 1,
    batch_run: int | None = None,
    batch_total: int | None = None,
    max_parallel: int | None = None,
    free_gpus: str | None = None,
    gpus_whitelist: str | None = None,
    gpu_snapshot: dict[str, Any] | None = None,
    gpu_snapshot_file: Path | None = None,
) -> tuple[Path, Path]:
    root = repo_root.resolve()
    ctx = build_run_context(
        root,
        run=run,
        batch_run=batch_run,
        batch_total=batch_total,
        max_parallel=max_parallel,
        free_gpus=free_gpus,
        gpus_whitelist=gpus_whitelist,
        gpu_snapshot=gpu_snapshot,
        gpu_snapshot_file=gpu_snapshot_file,
    )
    saved = root / "saved"
    saved.mkdir(parents=True, exist_ok=True)
    md_path = saved / "run_context.md"
    json_path = saved / "run_context.json"
    md_path.write_text(format_run_context_md(ctx), encoding="utf-8")
    json_path.write_text(json.dumps(ctx, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    snap = ctx.get("gpu_snapshot")
    if isinstance(snap, dict) and snap:
        (saved / "gpu_last_snapshot.json").write_text(
            json.dumps(snap, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    return md_path, json_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Build auto-run Run Context snapshot")
    ap.add_argument("--repo-root", type=Path, default=Path.cwd())
    ap.add_argument("--format", choices=("md", "json", "batch-md"), default="md")
    ap.add_argument("--write", action="store_true", help="写入 saved/run_context.{md,json}")
    ap.add_argument("--run", type=int, default=1)
    ap.add_argument("--batch-run", type=int, default=None, help="auto-run 当前 batch 轮次（1-based）")
    ap.add_argument("--batch-total", type=int, default=None, help="auto-run batch 总轮数 N")
    ap.add_argument("--max-parallel", type=int, default=None, help="nn-config max_parallel 上限")
    ap.add_argument("--free-gpus", default=None, help="当前空闲 GPU 列表（逗号分隔）")
    ap.add_argument("--gpus-whitelist", default=None, help="nn-config gpus 白名单")
    ap.add_argument("--gpu-snapshot-file", type=Path, default=None, help="gpu_snapshot.py --format json 输出文件")
    args = ap.parse_args()
    root = args.repo_root.resolve()
    mode = run_context_config(root)
    if mode == "off" and not args.write:
        print("(run_context_injection=off)")
        return 0

    batch_kw = {
        "batch_run": args.batch_run,
        "batch_total": args.batch_total,
        "max_parallel": args.max_parallel,
        "free_gpus": args.free_gpus,
        "gpus_whitelist": args.gpus_whitelist,
        "gpu_snapshot_file": args.gpu_snapshot_file,
    }
    ctx = build_run_context(root, run=args.run, **batch_kw)
    if args.write:
        write_run_context(root, run=args.run, **batch_kw)

    if args.format == "json":
        print(json.dumps(ctx, ensure_ascii=False, indent=2, default=str))
    elif args.format == "batch-md":
        batch = ctx.get("batch_scheduling")
        if isinstance(batch, dict):
            print("### batch（编排位置 · 分配 train 进程/槽位）")
            print("\n".join(_format_batch_scheduling_lines(batch)))
    else:
        print(format_run_context_md(ctx))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
