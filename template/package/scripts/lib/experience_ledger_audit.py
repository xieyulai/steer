"""EXPERIENCE 叙事 vs 台账 TSV 一致性审计（doctor WARN）。"""
from __future__ import annotations

import re
from pathlib import Path

from lib.experience_compress import parse_tier_status_table, tier_snapshot_one_liner

# EXPERIENCE 里常见、且应在 TSV experiment/description 留痕的技术 token
_LEDGER_TOKENS = (
    "gridmask",
    "random_erasing",
    "trivialaugment",
    "randaugment",
    "tta_k",
    "temperature_scaling",
    "multi-seed",
    "multiseed",
)

_EXHAUST_RE = re.compile(
    r"(已穷尽|已试|饱和|退步|discard|证伪|失败|exhausted|attested)",
    re.I,
)
_RUN_ID_RE = re.compile(r"\br(\d+)\b", re.I)


def _tsv_search_corpus(tsv_path: Path) -> str:
    if not tsv_path.is_file():
        return ""
    lines = tsv_path.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(lines) <= 1:
        return ""
    hdr = lines[0].split("\t")
    try:
        exp_i = hdr.index("experiment")
    except ValueError:
        exp_i = 0
    desc_i = hdr.index("description") if "description" in hdr else None
    bits: list[str] = []
    for ln in lines[1:]:
        cells = ln.split("\t")
        if exp_i < len(cells):
            bits.append(cells[exp_i])
        if desc_i is not None and desc_i < len(cells):
            bits.append(cells[desc_i])
    return "\n".join(bits).lower()


def _experience_audit_blocks(md: str) -> str:
    """精华摘要 + Tier 状态（声称「已试/穷尽」的主要区域）。"""
    parts: list[str] = []
    if "## 精华摘要" in md:
        i = md.index("## 精华摘要")
        parts.append(md[i : i + 4000])
    table = parse_tier_status_table(md)
    if table:
        parts.append(table)
    snap = tier_snapshot_one_liner(md)
    if snap and snap != "A:? B:? C:? D:? E:?":
        parts.append(snap)
    return "\n".join(parts)


def audit_experience_vs_tsv(repo_root: Path) -> list[str]:
    """返回 WARN 消息列表（空 = 通过）。"""
    exp_path = repo_root / "EXPERIENCE.md"
    tsv_path = repo_root / "_runs" / "results.tsv"
    if not exp_path.is_file() or not tsv_path.is_file():
        return []

    md = exp_path.read_text(encoding="utf-8", errors="replace")
    block = _experience_audit_blocks(md)
    if not block.strip():
        return []

    corpus = _tsv_search_corpus(tsv_path)
    if not corpus:
        return []

    warns: list[str] = []

    # rNN 引用：在穷尽/已试语境出现但 TSV 无对应 experiment 子串
    for m in _RUN_ID_RE.finditer(block):
        rid = m.group(0).lower()
        start = max(0, m.start() - 80)
        end = min(len(block), m.end() + 80)
        ctx = block[start:end]
        if not _EXHAUST_RE.search(ctx):
            continue
        if rid not in corpus and f"_{rid}" not in corpus:
            warns.append(f"EXPERIENCE 引用 {rid}（已试/穷尽语境）但 TSV 无匹配 experiment")

    # 技术 token：在穷尽语境出现但 TSV 无留痕
    block_lower = block.lower()
    for tok in _LEDGER_TOKENS:
        if tok not in block_lower:
            continue
        # 粗定位：含 token 的片段是否带穷尽语义
        for m in re.finditer(re.escape(tok), block_lower):
            ctx = block_lower[max(0, m.start() - 60) : m.end() + 60]
            if not _EXHAUST_RE.search(ctx):
                continue
            norm = tok.replace("_", "")
            if tok in corpus or norm in corpus.replace("_", ""):
                break
        else:
            warns.append(
                f"EXPERIENCE 声称已试/穷尽「{tok}」但 TSV experiment/description 无匹配行"
            )

    # 去重保序
    seen: set[str] = set()
    out: list[str] = []
    for w in warns:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return out[:8]
