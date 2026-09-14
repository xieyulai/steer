"""EXPERIENCE ↔ TAM 一致性 reconcile。

每次 reflect Phase 3 compact 前调一次：
- 解析 EXPERIENCE.md "**已穷尽** X + Y + Z" 列表
- 与 TSV 实际跑过的 A 档实验数 diff
- 若 EXPERIENCE 列举数 ≤ TSV 行数 → promote TAM（A:not_attested → attested）
- 否则 conflict（不静默 promote，WARN）
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class TamReconcileResult:
    action: str
    tier: str
    tam_before: str
    tam_after: str
    evidence_count: int = 0
    exhausted_count: int = 0
    conflict_reason: str = ""
    tier_attested_marker: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "tier": self.tier,
            "tam_before": self.tam_before,
            "tam_after": self.tam_after,
            "evidence_count": self.evidence_count,
            "exhausted_count": self.exhausted_count,
            "conflict_reason": self.conflict_reason,
            "tier_attested_marker": self.tier_attested_marker,
        }


def parse_exhausted_scalars(md_text: str, tier: str = "A") -> list[str]:
    """从 EXPERIENCE.md 解析 "**已穷尽** X + Y + Z" 列表。

    只解析明确 pattern：
        ### Tier <X>
        - **已穷尽** scalar1 value1 + scalar2 value2 + ...

    每条 item 只保留 scalar 名（空格前），去掉后面的数值。
    """
    scalars: list[str] = []
    tier_pat = re.compile(
        rf"###\s*Tier\s*{re.escape(tier)}\b[^\n]*\n((?:(?!###\s*Tier\s).)*?)(?=###|\Z)",
        re.S,
    )
    m = tier_pat.search(md_text)
    if not m:
        return scalars
    body = m.group(1)
    exhausted_pat = re.compile(r"\*\*已穷尽\*\*\s*([^\n]+)")
    for em in exhausted_pat.finditer(body):
        items = [s.strip() for s in em.group(1).split("+")]
        for item in items:
            # 只保留 scalar 名（空格前），忽略后面数值
            name = item.split()[0] if item else ""
            if name:
                scalars.append(name)
    return scalars


def _read_tsv_rows(tsv_path: Path) -> list[dict[str, str]]:
    if not tsv_path.is_file():
        return []
    rows: list[dict[str, str]] = []
    with tsv_path.open(encoding="utf-8", errors="replace") as f:
        header = f.readline().rstrip("\n").split("\t")
        for line in f:
            cells = line.rstrip("\n").split("\t")
            if len(cells) < len(header):
                continue
            rows.append(dict(zip(header, cells)))
    return rows


def reconcile_tam_with_experience(
    repo_root: Path,
    experience_md_path: Path,
    tam_path: Path | None = None,
) -> TamReconcileResult:
    if tam_path is None:
        tam_path = repo_root / "saved" / "tier_attestation.json"

    if not experience_md_path.is_file():
        return TamReconcileResult(
            action="noop", tier="A", tam_before="?", tam_after="?",
            conflict_reason="EXPERIENCE.md not found",
        )
    md_text = experience_md_path.read_text(encoding="utf-8", errors="replace")

    tam_data: dict[str, Any] = {}
    if tam_path.is_file():
        try:
            tam_data = json.loads(tam_path.read_text(encoding="utf-8"))
        except Exception:
            tam_data = {}

    target_tier = "A"
    tier_state = tam_data.get(target_tier, {"status": "not_attested", "evidence": []})
    tam_before = tier_state.get("status", "not_attested")

    exhausted = parse_exhausted_scalars(md_text, tier=target_tier)
    exhausted_count = len(exhausted)

    tsv_rows = _read_tsv_rows(repo_root / "_runs" / "results.tsv")
    # 取 TSV 总行数（不按关键字过滤）作为 A 档 evidence 计数
    evidence_count = len(tsv_rows)

    if tam_before == "attested":
        return TamReconcileResult(
            action="noop", tier=target_tier,
            tam_before=tam_before, tam_after=tam_before,
            evidence_count=evidence_count, exhausted_count=exhausted_count,
        )

    if evidence_count >= max(exhausted_count, 1):
        marker = f"[tier_attested {datetime.now(timezone.utc).strftime('%Y-%m-%d')}]"
        return TamReconcileResult(
            action="promote", tier=target_tier,
            tam_before=tam_before, tam_after="attested",
            evidence_count=evidence_count, exhausted_count=exhausted_count,
            tier_attested_marker=marker,
        )

    return TamReconcileResult(
        action="conflict", tier=target_tier,
        tam_before=tam_before, tam_after=tam_before,
        evidence_count=evidence_count, exhausted_count=exhausted_count,
        conflict_reason=f"EXPERIENCE 列了 {exhausted_count} 个标量，TSV 只跑过 {evidence_count} 个",
    )