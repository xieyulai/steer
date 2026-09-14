"""Explore objective mode：effective_objective、coverage、explore-KEEP 判定。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lib.human_guidance_roadmap import roadmap_section_body
from lib.nn_config import load_nn_config

_OBJECTIVE_RE = re.compile(
    r"^\s*-\s*\*\*objective\*\*\s*:\s*(explore|optimize)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_PHASE_HEADER_RE = re.compile(r"^###\s*阶段\s*(\d+)\s*—\s*(.+)$", re.MULTILINE | re.IGNORECASE)


@dataclass
class ObjectiveResolution:
    mode: str  # "optimize" | "explore"
    source: str  # "default" | "nn-config" | "human_phase" | "migration_override"
    phase_num: str = ""
    migration_blocked: bool = False


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _load_nn_agent(repo_root: Path) -> dict[str, Any]:
    try:
        raw = load_nn_config(repo_root)
        agent = raw.get("agent") if isinstance(raw, dict) else None
        return agent if isinstance(agent, dict) else {}
    except Exception:
        return {}


def is_migration_in_progress(repo_root: Path) -> bool:
    """迁移未完成 ⇔ 根仍有 CHECKLIST.md。
    verify 通过时 CHECKLIST.md 被 best-effort 归档到
    .auto-nn/migration-completed-checklist-<ts>.md（spec §2.2 的完成信号件），
    故根无 CHECKLIST.md ⇔ 已完成 ⇔ 不在迁移中 ⇔ 放行 explore。

    注：764816d 曾加 glob 检查却把信号件读反（archive 存在→True），与 docstring/
    spec §2.2 相反，导致已归档仓被 migration_override 永久锁在 optimize。
    glob 本身亦冗余（归档的副作用就是把 CHECKLIST 移出根），故移除，回到根 CHECKLIST
    单一信号；归档的语义改由 verify-migration-complete.sh 的归档动作承担。"""
    return (Path(repo_root) / "CHECKLIST.md").is_file()


def _roadmap_body(repo_root: Path) -> str:
    p = repo_root / "HUMAN_GUIDANCE.md"
    if not p.is_file():
        return ""
    return roadmap_section_body(_read_text(p))


def _phase_section(body: str, phase_num: str) -> str:
    if not body.strip() or not phase_num:
        return ""
    parts = re.split(r"(?=^###\s*阶段\s*\d+)", body, flags=re.MULTILINE | re.I)
    target = str(phase_num).strip()
    for part in parts:
        m = _PHASE_HEADER_RE.match(part.strip().splitlines()[0] if part.strip() else "")
        if m and m.group(1) == target:
            return part
    return ""


def parse_phase_objective_from_human(repo_root: Path, inferred_phase: str) -> str | None:
    """从当前阶段块 NOTE 解析 `- **objective**: explore|optimize`。"""
    if not inferred_phase or inferred_phase in ("empty", "done", "(无)"):
        return None
    section = _phase_section(_roadmap_body(repo_root), inferred_phase)
    if not section:
        return None
    m = _OBJECTIVE_RE.search(section)
    if not m:
        return None
    return m.group(1).strip().lower()


def _inferred_phase(repo_root: Path) -> str:
    scripts = repo_root / "scripts"
    import sys

    scripts_str = str(scripts.resolve())
    if scripts.is_dir() and scripts_str not in sys.path:
        sys.path.insert(0, scripts_str)
    try:
        from lib.run_ledger_summary import roadmap_status  # noqa: WPS433

        return str(roadmap_status(repo_root, attach_coverage=False).inferred_phase or "").strip()
    except ImportError:
        return ""


def objective_mode_from_config(repo_root: Path) -> str:
    try:
        raw = load_nn_config(repo_root)
    except Exception:
        return "optimize"
    expl = raw.get("exploration") if isinstance(raw.get("exploration"), dict) else {}
    mode = str(expl.get("objective_mode", "") or "").strip().lower()
    if mode in ("explore", "optimize"):
        return mode
    return "optimize"


def effective_objective(repo_root: Path) -> ObjectiveResolution:
    """HUMAN 阶段 objective > nn-config > 默认 optimize；迁移中强制 optimize。"""
    root = repo_root.resolve()
    phase = _inferred_phase(root)
    human = parse_phase_objective_from_human(root, phase)
    cfg_mode = objective_mode_from_config(root)

    if human in ("explore", "optimize"):
        mode = human
        source = "human_phase"
    elif cfg_mode == "explore":
        mode = "explore"
        source = "nn-config"
    else:
        mode = "optimize"
        source = "default"

    blocked = is_migration_in_progress(root)
    if blocked and mode == "explore":
        return ObjectiveResolution(
            mode="optimize",
            source="migration_override",
            phase_num=phase,
            migration_blocked=True,
        )

    return ObjectiveResolution(
        mode=mode,
        source=source,
        phase_num=phase,
        migration_blocked=False,
    )


def load_explore_config(repo_root: Path) -> dict[str, Any]:
    """读取 agent.explore 块（缺省 keep_on 等）。"""
    agent = _load_nn_agent(repo_root)
    raw = agent.get("explore")
    if not isinstance(raw, dict):
        raw = {}
    keep_on = raw.get("keep_on") or [
        "first_in_cell",
        "attested_novel",
        "scenario_debut",
    ]
    if isinstance(keep_on, str):
        keep_on = [keep_on]
    return {
        "keep_on": [str(x) for x in keep_on],
        "scenario_policy": str(raw.get("scenario_policy", "rotate") or "rotate"),
        "reflect_gate_coverage_stall": int(raw.get("reflect_gate_coverage_stall", 3) or 3),
    }


def _train_tsv_rows(
    repo_root: Path,
    history_rows: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    if history_rows is not None:
        rows = history_rows
    else:
        from lib.run_ledger_summary import tsv_rows  # noqa: WPS433

        rows = tsv_rows(repo_root)
    return [r for r in rows if str(r.get("experiment", "")).strip() != "preflight_check"]


def scenario_has_prior_train(
    repo_root: Path,
    scenario_id: str,
    *,
    history_rows: list[dict[str, str]] | None = None,
) -> bool:
    """TSV 中该 scenario_id 是否已有有效 train 行（不含 preflight）。"""
    sid = (scenario_id or "").strip()
    if not sid:
        return False
    for row in _train_tsv_rows(repo_root, history_rows):
        if str(row.get("scenario_id", "")).strip() == sid:
            return True
    return False


def scenario_debut(
    repo_root: Path,
    scenario_id: str,
    *,
    history_rows: list[dict[str, str]] | None = None,
) -> bool:
    sid = (scenario_id or "").strip()
    if not sid:
        return False
    return not scenario_has_prior_train(repo_root, sid, history_rows=history_rows)


def _attested_recent_count(repo_root: Path) -> int:
    tam_path = repo_root / "saved" / "tier_attestation.json"
    if tam_path.is_file():
        try:
            data = json.loads(_read_text(tam_path))
            rollup = data.get("rollup") if isinstance(data, dict) else None
            if isinstance(rollup, dict):
                total = 0
                for val in rollup.values():
                    if not isinstance(val, dict):
                        continue
                    total += int(val.get("attested", 0) or 0) + int(val.get("shallow", 0) or 0)
                return total
        except Exception:
            pass
    rows = _train_tsv_rows(repo_root)[-12:]
    n = 0
    for row in rows:
        keep = str(row.get("keep", "")).strip().lower()
        if keep in ("0", "false", "no"):
            n += 1
    return n


def format_coverage_brief(repo_root: Path) -> list[str]:
    """Run Context explore 段：台账侧 coverage 摘要。"""
    res = effective_objective(repo_root)
    src = res.source
    if res.phase_num:
        src = f"{src} phase {res.phase_num}"
    lines = [f"effective_objective: {res.mode} (source={src})"]

    try:
        from lib.scenario_inventory import load_scenario_ids  # noqa: WPS433

        inventory = load_scenario_ids(repo_root)
    except ImportError:
        inventory = []

    seen: set[str] = set()
    for row in _train_tsv_rows(repo_root):
        sid = str(row.get("scenario_id", "")).strip()
        if sid:
            seen.add(sid)
    n_with = len(seen)
    n_inv = len(inventory) if inventory else max(n_with, 1)
    lines.append(f"grid_progress: {n_with}/{n_inv} scenarios")

    if inventory:
        queue = " → ".join(inventory[:8])
        if len(inventory) > 8:
            queue += " …"
        lines.append(f"scenario_queue: {queue} (inventory order; NOTE overrides)")
    else:
        lines.append("scenario_queue: (no scenario_inventory)")

    lines.append(f"attested_recent: {_attested_recent_count(repo_root)} (TAM window heuristic)")
    return lines


def coverage_progress_line(repo_root: Path) -> str:
    """roadmap-status 信息行。"""
    res = effective_objective(repo_root)
    if res.mode != "explore" or res.migration_blocked:
        return ""
    for line in format_coverage_brief(repo_root):
        if line.startswith("grid_progress:"):
            return line.replace("grid_progress:", "coverage_progress:", 1)
    return ""


def _cell_has_prior(
    repo_root: Path,
    scenario_id: str,
    tier_label: str,
    *,
    history_rows: list[dict[str, str]] | None = None,
) -> bool:
    label = (tier_label or "").strip()
    sid = (scenario_id or "").strip()
    if not label or not sid:
        return True
    needle = label.lower()
    rows = _train_tsv_rows(repo_root, history_rows)[-30:]
    for row in rows:
        if str(row.get("scenario_id", "")).strip() != sid:
            continue
        blob = " ".join(
            [
                str(row.get("experiment", "")),
                str(row.get("description", "")),
            ]
        ).lower()
        if needle in blob or f"tier {needle}" in blob or f"tier_{needle}" in blob:
            return True
    return False


def coverage_stall_streak(repo_root: Path, *, window: int | None = None) -> int:
    """连续 window 轮无新 scenario / explore 信号 → 返回 streak（否则 0）。"""
    cfg = load_explore_config(repo_root)
    stall_n = window or cfg["reflect_gate_coverage_stall"]
    rows = _train_tsv_rows(repo_root)
    if len(rows) < stall_n:
        return 0
    prior_ids: set[str] = set()
    for row in rows[:-stall_n]:
        sid = str(row.get("scenario_id", "")).strip()
        if sid:
            prior_ids.add(sid)
    for row in rows[-stall_n:]:
        sid = str(row.get("scenario_id", "")).strip()
        if sid and sid not in prior_ids:
            return 0
        blob = " ".join(
            [
                str(row.get("experiment", "")),
                str(row.get("description", "")),
                str(row.get("keep_reason", "")),
            ]
        ).lower()
        if "explore:first_in_cell" in blob or "explore:attested" in blob:
            return 0
        if sid:
            prior_ids.add(sid)
    return stall_n


def human_note_forbidden_terms(repo_root: Path) -> list[str]:
    """当前阶段 NOTE 内「禁止」段落的简单词条（第一版：按行 split）。"""
    phase = _inferred_phase(repo_root)
    section = _phase_section(_roadmap_body(repo_root), phase)
    if not section:
        return []
    m = re.search(r"禁止[^\n]*\n(.*?)(?=\n-\s*\*\*|\Z)", section, re.DOTALL | re.I)
    if not m:
        return []
    terms: list[str] = []
    for line in m.group(1).splitlines():
        line = line.strip().lstrip("-").strip()
        if line and len(line) >= 3:
            terms.append(line)
    return terms


def explore_attested_for_exp(repo_root: Path, exp_dir: Path) -> bool:
    """TAM 窗口内该 exp 为 attested/shallow/false_claim 且非 primary 改善 → 证伪信号。"""
    tam = repo_root / "saved" / "tier_attestation.json"
    if not tam.is_file():
        return False
    try:
        data = json.loads(_read_text(tam))
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    exp_s = str(exp_dir.resolve())
    rows = data.get("rows")
    if not isinstance(rows, list):
        return False
    for row in rows[-20:]:
        if not isinstance(row, dict):
            continue
        row_exp = str(row.get("exp_dir") or "").strip()
        if not row_exp:
            continue
        if str(Path(row_exp).resolve()) != exp_s:
            continue
        v = str(row.get("verdict") or "")
        if v in ("attested", "shallow", "false_claim"):
            out = row.get("outcome") or {}
            if isinstance(out, dict) and not out.get("primary_improved"):
                return True
    return False


def evaluate_explore_keep(
    repo_root: Path,
    *,
    scenario_id: str,
    tier_label: str = "",
    history_rows: list[dict[str, str]] | None = None,
    keep_on: list[str] | None = None,
    attested: bool = False,
) -> tuple[bool, str]:
    """explore 模式 OR 分支 KEEP 判定（K1 探索链锚点）。"""
    cfg = load_explore_config(repo_root)
    rules = keep_on if keep_on is not None else cfg["keep_on"]
    sid = (scenario_id or "").strip()

    if "scenario_debut" in rules and sid and scenario_debut(repo_root, sid, history_rows=history_rows):
        return True, f"explore:scenario_debut {sid}"

    if "first_in_cell" in rules and sid and tier_label:
        if not _cell_has_prior(repo_root, sid, tier_label, history_rows=history_rows):
            return True, f"explore:first_in_cell tier={tier_label} scenario={sid}"

    if "attested_novel" in rules and attested:
        return True, "explore:attested_novel"

    return False, ""


def pending_conflicts_with_human_note(repo_root: Path, pending_text: str) -> bool:
    """pending 文本是否明显触犯 NOTE 禁止项（子串匹配）。"""
    pending = (pending_text or "").lower()
    if not pending:
        return False
    for term in human_note_forbidden_terms(repo_root):
        t = term.lower()
        if len(t) >= 4 and t in pending:
            return True
    return False
