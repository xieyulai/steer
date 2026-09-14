"""创新维度审计（Phase 0.7）。

仅生成 WARN，不硬阻断。供 reflect.py 调用，也可独立运行。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from lib.nn_config import load_nn_config

_DEFAULT_ROUTINE_HINTS: List[str] = [
    r"torchvision",
    r"\btimm\b",
    r"\bkornia\b",
    r"torch\.nn\.(CrossEntropyLoss|MSELoss|BCE|NLLLoss)",
    r"from torchvision\.",
    r"import torchvision",
    r"nn\.CrossEntropyLoss",
    r"nn\.MSELoss",
]

@dataclass
class InnovationAuditConfig:
    enabled: bool = True
    routine_hints: List[str] = field(default_factory=lambda: list(_DEFAULT_ROUTINE_HINTS))

@dataclass
class AuditWarning:
    kind: str  # "invalid_depth" | "routine_mislabel" | "missing_rationale" | "legacy_depth"
    message: str
    level: str = "WARN"  # "WARN" | "FAIL"（v2.8.1: legacy_depth 旧词 = FAIL 硬拦）

@dataclass
class InnovationAuditResult:
    warnings: List[AuditWarning] = field(default_factory=list)
    summary_line: str = ""
    agent_depth: str = ""
    fingerprint_depth: str = ""
    effective_depth: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": 2,
            "agent_depth": self.agent_depth,
            "fingerprint_depth": self.fingerprint_depth,
            "effective_depth": self.effective_depth,
            "summary_line": self.summary_line,
            "warnings": [{"kind": w.kind, "level": w.level, "message": w.message} for w in self.warnings],
        }

def load_innovation_config(repo_root: str | Path = ".") -> InnovationAuditConfig:
    """从 nn-config.yaml 读取 innovation 顶层段，合并默认 hints。"""
    root = Path(repo_root)
    enabled = True
    extra_hints: List[str] = []
    try:
        data = load_nn_config(root)
        innov = data.get("innovation") if isinstance(data.get("innovation"), dict) else {}
        if "audit_enabled" in innov:
            enabled = bool(innov["audit_enabled"])
        # routine hints：仍允许挂在 agent（非迁移表）或 innovation 段
        agent = data.get("agent", {}) or {}
        hints = innov.get("routine_hints") or agent.get("innovation_routine_hints") or []
        if isinstance(hints, list):
            extra_hints = [str(h) for h in hints]
    except Exception:
        pass
    hints = list(_DEFAULT_ROUTINE_HINTS) + extra_hints
    # 去重保持顺序
    seen = set()
    deduped = []
    for h in hints:
        if h not in seen:
            seen.add(h)
            deduped.append(h)
    return InnovationAuditConfig(enabled=enabled, routine_hints=deduped)

# v2.8.1: RDDN 深度词正名映射（旧词已退役，audit 硬拦逼 agent 用新词）
# 只含 exploration_space 列 / innovation_depth 字段现实出现的旧词。
# formal-novel 是 fingerprint_history 域的历史词（由 migrate_fingerprint_history.py
# 处理），exploration_space 列标签 = {tier}-{depth} 不含它（含 - 与分隔符冲突），
# 故不归本 audit；若 innovation_depth 误填 formal-novel，由下方 invalid_depth 兜底。
_LEGACY_DEPTH_MAP = {"extend": "derived"}
_VALID_DEPTHS = {"routine", "derived", "different", "novel"}


def _depth_from_exploration_space(es: str) -> str:
    """exploration_space 格式 ``{tier}-{depth}``（如 ``B-extend``）→ 深度词。

    兼容裸深度词（``extend``）。非深度尾部 → ``""``。
    exploration_space 列标签 = {A-E}-{routine|extend|derived|different|novel}，
    不含 formal-novel（含 ``-`` 与 tier 分隔符冲突，实测三仓均无）。
    """
    s = (es or "").strip().lower()
    if not s:
        return ""
    for d in ("extend", "routine", "derived", "different", "novel"):
        if s == d or s.endswith("-" + d):
            return d
    return ""


def find_legacy_depth_in_tsv(repo_root: str | Path = ".") -> List[Dict[str, Any]]:
    """v2.8.3: 扫 ``_runs/results.tsv`` exploration_space 列, 返回 RDDN 旧词命中。

    供 nn-doctor innovation_vocab 检查 + 业务仓自查。旧词 (extend→derived) 在
    v2.8.1 audit 已硬拦新轮, 本函数扫**存量 TSV** 残留旧词 → doctor FAIL。

    返回 ``[{"row": <行号>, "experiment": ..., "exploration_space": "B-extend",
    "legacy": "extend", "suggest": "derived"}, ...]``。无 TSV / 无命中 → 空列表。
    """
    import csv

    tsv = Path(repo_root) / "_runs" / "results.tsv"
    if not tsv.is_file():
        return []
    hits: List[Dict[str, Any]] = []
    with tsv.open(encoding="utf-8", newline="") as f:
        for i, row in enumerate(csv.DictReader(f, delimiter="\t"), start=2):
            es = (row.get("exploration_space") or "").strip()
            d = _depth_from_exploration_space(es)
            if d in _LEGACY_DEPTH_MAP:
                hits.append({
                    "row": i,
                    "experiment": row.get("experiment", ""),
                    "exploration_space": es,
                    "legacy": d,
                    "suggest": _LEGACY_DEPTH_MAP[d],
                })
    return hits


def scan_text_for_routine(text: str, hints: Optional[List[str]] = None) -> List[str]:
    """返回命中的 hint 描述列表（用于 mislabel 判断）。"""
    if not text:
        return []
    hits: List[str] = []
    use_hints = hints if hints is not None else _DEFAULT_ROUTINE_HINTS
    for pat in use_hints:
        try:
            if re.search(pat, text, re.I):
                hits.append(pat)
        except re.error:
            # 容忍坏正则
            if pat.lower() in text.lower():
                hits.append(pat)
    return hits

def audit_round(
    tier_this_round: str,
    innovation_depth: str,
    rationale: str = "",
    diff_text: str = "",
    config: Optional[InnovationAuditConfig] = None,
    exploration_space: str = "",
) -> List[AuditWarning]:
    """单轮审计。返回警告列表（可为空）。"""
    warns: List[AuditWarning] = []
    depth = (innovation_depth or "").strip().lower()
    es_depth = _depth_from_exploration_space(exploration_space)

    # v2.8.1 legacy 旧词硬拦（RDDN 正名）：innovation_depth 或 exploration_space
    # 深度命中 extend/formal-novel → FAIL（逼 agent 改 derived/different）
    for _raw in (depth, es_depth):
        if _raw in _LEGACY_DEPTH_MAP:
            warns.append(AuditWarning(
                kind="legacy_depth",
                level="FAIL",
                message=(
                    f"旧深度词 '{_raw}' 已退役 → 应改 '{_LEGACY_DEPTH_MAP[_raw]}'"
                    f"（RDDN 正名：extend→derived）；"
                    f"检查 round_decision.innovation_depth / TSV exploration_space 列"
                ),
            ))
            return warns

    if depth not in _VALID_DEPTHS:
        warns.append(AuditWarning(kind="invalid_depth", message=f"非法 innovation_depth: {innovation_depth}"))
        return warns

    if not rationale or not rationale.strip():
        warns.append(AuditWarning(kind="missing_rationale", message="innovation_rationale 为空或缺失"))

    # routine_mislabel：声明形式创新（novel / different）但命中 routine 提示。
    # RDDN expand：different 是“形式创新”的新名，与 novel 同享该检查。
    if depth in ("novel", "different"):
        text = (diff_text or "") + "\n" + (rationale or "")
        hits = scan_text_for_routine(text, config.routine_hints if config else None)
        if hits:
            warns.append(
                AuditWarning(
                    kind="routine_mislabel",
                    message=f"声明 novel 但命中 routine 提示: {', '.join(hits[:3])}",
                )
            )
    return warns


def audit_fingerprint_mismatch(
    agent_depth: str,
    fingerprint_depth: str,
    *,
    fingerprint_fallback: bool = False,
    fingerprint_ambiguous: bool = False,
) -> List[AuditWarning]:
    warns: List[AuditWarning] = []
    agent = (agent_depth or "").strip().lower()
    fp = (fingerprint_depth or "").strip().lower()
    valid = {"routine", "derived", "different", "novel"}

    if fingerprint_fallback:
        warns.append(
            AuditWarning(
                kind="fingerprint_fallback",
                message="创新指纹失败或不可用，外部检索回退 Agent 声明",
            )
        )
    if fingerprint_ambiguous or fp == "ambiguous":
        warns.append(
            AuditWarning(
                kind="fingerprint_ambiguous",
                message="创新指纹无法判定档位（ambiguous）",
            )
        )
    if agent in valid and fp in valid and agent != fp:
        warns.append(
            AuditWarning(
                kind="depth_mismatch",
                message=f"Agent 标 {agent}，指纹判 {fp}；检索以指纹/effective 为准",
            )
        )
    return warns


def format_innovation_line(matrix: Dict[str, Dict[str, str]]) -> str:
    """把二维状态矩阵格式化为一行摘要，供 prompt / pending 使用。"""
    if not matrix:
        return ""
    parts: List[str] = []
    for tier in ["A", "B", "C", "D", "E"]:
        if tier not in matrix:
            continue
        depths = matrix[tier]
        dparts = []
        for d in ["routine", "derived", "different", "novel"]:
            if d in depths:
                dparts.append(f"{d}:{depths[d]}")
        if dparts:
            parts.append(f"{tier}-" + "/".join(dparts))
    if not parts:
        return ""
    return "[Innovation: " + " ; ".join(parts) + "]"

def run_innovation_audit(
    repo_root: str | Path = ".",
    recent_rounds: Optional[List[Dict[str, Any]]] = None,
    fingerprint: Optional[Dict[str, Any]] = None,
) -> InnovationAuditResult:
    """主入口。供 reflect Phase 0.7 调用。

    recent_rounds 形如 [{"tier_this_round": "B", "innovation_depth": "novel", ...}, ...]
    fingerprint 为 Phase 0.75 的 innovation_fingerprint.json 内容（可选）。
    """
    root = Path(repo_root)
    cfg = load_innovation_config(root)
    result = InnovationAuditResult()
    if not cfg.enabled:
        result.summary_line = "[Innovation: 已禁用]"
        return result

    fp = fingerprint or {}
    agent_depth = ""
    if recent_rounds:
        agent_depth = str(recent_rounds[-1].get("innovation_depth") or "").strip().lower()
    fp_depth = str(fp.get("depth") or "").strip().lower()
    effective = str(fp.get("effective_depth") or agent_depth or "routine").strip().lower()
    result.agent_depth = agent_depth
    result.fingerprint_depth = fp_depth
    result.effective_depth = effective

    warnings_all: List[AuditWarning] = []
    if recent_rounds:
        for r in recent_rounds:
            ws = audit_round(
                tier_this_round=r.get("tier_this_round", ""),
                innovation_depth=r.get("innovation_depth", ""),
                rationale=r.get("innovation_rationale", "") or r.get("rationale", ""),
                diff_text=r.get("diff_text", "") or r.get("code_diff", ""),
                config=cfg,
                exploration_space=r.get("exploration_space", ""),
            )
            warnings_all.extend(ws)

    if fp.get("enabled", True) and fp:
        warnings_all.extend(
            audit_fingerprint_mismatch(
                agent_depth,
                fp_depth,
                fingerprint_fallback=bool(fp.get("fallback")),
                fingerprint_ambiguous=fp_depth == "ambiguous",
            )
        )

    # 也扫描最近的 workspace / train.py 作为辅助证据（简化版）
    try:
        for p in ["train.py", "workspace/__init__.py"]:
            fp_path = root / p
            if fp_path.exists():
                txt = fp_path.read_text(encoding="utf-8", errors="ignore")
                hits = scan_text_for_routine(txt, cfg.routine_hints)
                if hits:
                    pass
    except Exception:
        pass

    result.warnings = warnings_all
    fp_line = str(fp.get("summary_line") or "").strip()
    if warnings_all:
        kinds = ",".join(sorted(set(w.kind for w in warnings_all)))
        base = f"[Innovation: WARN {kinds}; agent={agent_depth or '?'} fp={fp_depth or '?'} effective={effective}]"
        result.summary_line = base
    else:
        result.summary_line = (
            f"[Innovation: clean; agent={agent_depth or '?'} fp={fp_depth or '?'} effective={effective}]"
        )
    if fp_line:
        result.summary_line += f" {fp_line}"
    return result


def record_symbol_introspection(
    repo_root: str | Path,
    snapshots: List[Dict[str, Any]],
) -> None:
    """T6/AC③：把命名空间扫描快照合并写入 saved/innovation_audit.json（可复现审计）。

    合并语义：只覆盖 symbol_introspection 字段，保留既存的 external_attestation /
    attested_depth 等。非致命：读/写炸了不抛（与 reflect_hook.update_innovation_audit_external
    同模式）——审计落盘失败不得阻断 fingerprint 主流程。
    """
    root = Path(repo_root)
    audit_path = root / "saved" / "innovation_audit.json"
    data: Dict[str, Any] = {}
    if audit_path.is_file():
        try:
            data = json.loads(audit_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["symbol_introspection"] = list(snapshots or [])
    try:
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8",
        )
    except Exception:
        pass
