"""EXPERIENCE.md compression helpers (spec: 2026-05-21-experience-compress-design)."""
from __future__ import annotations

import csv
import dataclasses
import hashlib
import re
from pathlib import Path

TIER_BLOCK_START = "<!-- nn-tier-block-start -->"
TIER_BLOCK_END = "<!-- nn-tier-block-end -->"
TIER_STATUS_HEADING = "## Tier 状态"
EXPERIENCE_LOG_START = "<!-- experience-log-start -->"
EXPERIENCE_LOG_END = "<!-- experience-log-end -->"
ESSENCE_HEADING = "## 精华摘要（滚动，compress 维护）"
INDEX_HEADING = "## 信息索引（按需 Read，默认不展开）"
RECENT_HEADING_TEMPLATE = "## 近期实验（保留最近 {n} 轮要点）"
DEFAULT_KEEP_N = 5
DEFAULT_KEEP_REFLECTS = 2
DEFAULT_TIER_CELL_MAX = 80
DEFAULT_SCENARIO_CELL_MAX = 120
DEFAULT_REFLECT_HIST_SUMMARY_MAX = 240

PRIORITY_TITLE_KEYS: tuple[str, ...] = (
    "禁忌",
    "当前最佳",
    "KEEP_THRESHOLD",
    "阈值",
    "数据与训练",
    "课题约束",
    "Tier Ladder",
    "值得探索",
    "工程备注",
    "台账状态",
    "场景与 KEEP",
    "关键结论",
    "KEEP 规则",
    "核心发现",
    "最佳历史",
)

_EXPERIMENT_NAME_RE = re.compile(r"\b([A-Za-z0-9][A-Za-z0-9_.-]{2,})\b")


@dataclasses.dataclass
class ExperienceParts:
    preamble: str
    tier_status: str
    scenario_block: str
    essence: str
    recent_experiments: list[str]
    archivable: list[str]
    reflects_recent: list[str]
    reflects_archivable: list[str]

    @property
    def protected(self) -> str:
        """Legacy accessor: scenario + tier status only."""
        chunks = [c for c in (self.scenario_block, self.tier_status) if c.strip()]
        return "\n\n".join(chunks)


def split_markdown_h2(md: str) -> list[tuple[str, str]]:
    lines = md.splitlines()
    sections: list[tuple[str, str]] = []
    title, buf = "", []
    for ln in lines:
        if ln.startswith("## ") and not ln.startswith("###"):
            sections.append((title, "\n".join(buf).strip()))
            title, buf = ln[3:].strip(), []
        else:
            buf.append(ln)
    sections.append((title, "\n".join(buf).strip()))
    return sections


def extract_tier_block(md: str) -> str:
    i0 = md.find(TIER_BLOCK_START)
    i1 = md.find(TIER_BLOCK_END)
    if i0 < 0 or i1 < 0:
        return ""
    return md[i0 : i1 + len(TIER_BLOCK_END)].strip()


def parse_tier_status_table(md: str) -> str:
    """提取 ## Tier 状态 段（含标题），无则返回空。
    仅匹配真正的 H2 标题行（## Tier 状态...），避免正文引用中的反引号片段。
    """
    # 找真正的标题行：以 "## Tier 状态" 开头（允许后面有括号等）
    m_start = re.search(r"(?m)^(##\s*Tier 状态[^\n]*)", md)
    if not m_start:
        return ""
    start = m_start.start()
    heading_line = m_start.group(1)
    # 从标题行之后找下一个 ## 标题
    rest = md[m_start.end() :]
    m_end = re.search(r"\n(?=##\s)", rest)
    if m_end:
        end = m_start.end() + m_end.start()
    else:
        end = len(md)
    block = md[start:end].strip()
    return block


def _parse_tier_matrix(table: str) -> dict[str, dict[str, str]]:
    """解析 Tier 状态表格。
    返回 { 'A': {'routine': '未试', 'derived': '未试', 'different': '未试'}, ... }
    兼容旧格式（单列 'status' + 可选 'remark'）。
    """
    if not table:
        return {}
    lines = [ln.strip() for ln in table.splitlines() if ln.strip().startswith("|")]
    if len(lines) < 2:
        return {}
    # 解析表头
    hdr = [c.strip().lower() for c in lines[0].strip("|").split("|") if c.strip()]
    is_2d = any(k in hdr for k in ("routine", "derived", "different"))

    result: dict[str, dict[str, str]] = {}
    for ln in lines[1:]:
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if not cells or not cells[0]:
            continue
        tier = cells[0].upper()
        if tier not in "ABCDE":
            continue
        if is_2d:
            d: dict[str, str] = {}
            for i, h in enumerate(hdr):
                if i == 0:
                    continue
                if i < len(cells):
                    d[h] = cells[i]
            result[tier] = d
        else:
            # 旧格式: | Tier | 状态 | 代表 | 备注 |
            status = cells[1] if len(cells) > 1 else "?"
            remark = cells[3] if len(cells) > 3 else ""
            result[tier] = {"status": status, "remark": remark}
    return result


def tier_snapshot_one_liner(md: str) -> str:
    """生成紧凑的 Tier 快照。
    2D 矩阵时输出各深度的状态（如 A-r:未试/e:未试/n:未试）。
    兼容旧单列格式。
    """
    table = parse_tier_status_table(md)
    mat = _parse_tier_matrix(table)
    if not mat:
        return "A:? B:? C:? D:? E:?"
    snaps: list[str] = []
    short = {"routine": "r", "derived": "d", "different": "f"}
    for letter in "ABCDE":
        depths = mat.get(letter, {})
        if any(k in depths for k in ("routine", "derived", "different")):
            parts = []
            for d in ("routine", "derived", "different"):
                if d in depths:
                    val = depths[d]
                    parts.append(f"{short.get(d, d[0])}:{val}")
            snaps.append(f"{letter}-" + "/".join(parts) if parts else f"{letter}:?")
        else:
            val = depths.get("status", "?")
            snaps.append(f"{letter}:{val}")
    return " ".join(snaps)


def tier_remarks_brief(md: str) -> str:
    """从 EXPERIENCE `## Tier 状态`（二维矩阵）摘各档/各格子要点。
    优先收集非「未试」的格子状态；旧格式回退到备注列。
    """
    table = parse_tier_status_table(md)
    mat = _parse_tier_matrix(table)
    if not mat:
        return "-"
    bits: list[str] = []
    short = {"routine": "r", "derived": "d", "different": "f"}
    for letter in "ABCDE":
        depths = mat.get(letter, {})
        for d in ("routine", "derived", "different"):
            if d in depths:
                val = (depths[d] or "").strip()
                if val and val not in ("未试", "—", "-", "?", ""):
                    if len(val) > 30:
                        val = val[:29] + "…"
                    bits.append(f"{letter}-{short[d]}:{val}")
        # 旧格式备注
        if "remark" in depths:
            rem = (depths.get("remark") or "").strip()
            if rem and rem not in ("—", "-", "?", ""):
                if len(rem) > 30:
                    rem = rem[:29] + "…"
                bits.append(f"{letter}:{rem}")
    return "；".join(bits) if bits else "-"


def parse_scenario_block(md: str) -> str:
    for title, body in split_markdown_h2(md):
        if not title:
            continue
        if title.startswith("场景") or "场景与 KEEP" in title:
            return f"## {title}\n{body}".strip()
    return ""


def is_reflect_section(title: str) -> bool:
    return title.startswith("[反思]")


def is_experiment_section(title: str) -> bool:
    if not title:
        return False
    if is_reflect_section(title):
        return False
    if title.startswith("精华摘要") or title.startswith("近期实验"):
        return False
    if title.startswith("Tier "):
        return False
    return True


def is_protected_section(title: str) -> bool:
    if not title:
        return True
    if title.startswith("Tier 状态"):
        return True
    if title.startswith("场景") or "场景与 KEEP" in title:
        return True
    if title.startswith("按需查阅") or title.startswith("信息索引"):
        return True
    return False


def _truncate_cell_text(text: str, max_len: int) -> str:
    s = " ".join(str(text).split())
    if len(s) <= max_len:
        return s
    if max_len <= 1:
        return "…"
    return s[: max_len - 1].rstrip() + "…"


def truncate_markdown_table_cells(block: str, max_cell: int, *, skip_cols: tuple[int, ...] = (0,)) -> str:
    """截断 markdown 表格数据行单元格（历史债务 Tier/场景长备注）。"""
    if not block.strip() or max_cell <= 0:
        return block
    out: list[str] = []
    past_sep = False
    pipe_rows = 0
    for ln in block.splitlines():
        if not ln.strip().startswith("|"):
            out.append(ln)
            continue
        if "---" in ln:
            out.append(ln)
            past_sep = True
            continue
        cells = [c.strip() for c in ln.strip("|").split("|")]
        is_data = past_sep or pipe_rows >= 1
        if is_data:
            cells = [
                c if i in skip_cols else _truncate_cell_text(c, max_cell)
                for i, c in enumerate(cells)
            ]
        out.append("| " + " | ".join(cells) + " |")
        pipe_rows += 1
    return "\n".join(out)


def truncate_tier_status_table(table: str, max_cell: int = DEFAULT_TIER_CELL_MAX) -> str:
    if not table.strip():
        return table
    return truncate_markdown_table_cells(table, max_cell, skip_cols=(0,))


def truncate_scenario_block(block: str, max_cell: int = DEFAULT_SCENARIO_CELL_MAX) -> str:
    if not block.strip():
        return block
    return truncate_markdown_table_cells(block, max_cell, skip_cols=(0, 1))


def build_source_index_block() -> str:
    return (
        f"{INDEX_HEADING}\n\n"
        "| 类型 | 路径 |\n"
        "|------|------|\n"
        "| 反思 pending | `references/REFLECT_INDEX.md` |\n"
        "| 反思详文 | `references/auto/<reflect_id>_auto_reflected.md` |\n"
        "| 外部证据 | `saved/evidence_bundle.json`、`saved/external_evidence/pdfs/`、`saved/reflect_evidence.json` |\n"
        "| 压缩归档 | `references/experience/archive_*.md` |\n"
        "| 台账 | `_runs/results.tsv` |\n"
        "| keeper | `saved/keepers.json` + `_runs/exp/<keeper>/config.json` |"
    )


def load_compress_options(repo_root: Path) -> dict[str, int]:
    """读 nn-config agent 压缩项；缺省为 v2 默认（近 5 轮）。"""
    opts = {
        "keep_n": DEFAULT_KEEP_N,
        "keep_reflects": DEFAULT_KEEP_REFLECTS,
        "tier_cell_max": DEFAULT_TIER_CELL_MAX,
        "scenario_cell_max": DEFAULT_SCENARIO_CELL_MAX,
        "reflect_hist_summary_max": DEFAULT_REFLECT_HIST_SUMMARY_MAX,
    }
    cfg_path = repo_root / "nn-config.yaml"
    if not cfg_path.is_file():
        return opts
    try:
        import yaml

        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        compress = raw.get("compress") if isinstance(raw, dict) else {}
        if not isinstance(compress, dict):
            return opts
        if compress.get("experience_compress_keep_n") is not None:
            opts["keep_n"] = int(compress["experience_compress_keep_n"])
        if compress.get("experience_compress_keep_reflects") is not None:
            opts["keep_reflects"] = int(compress["experience_compress_keep_reflects"])
        if compress.get("experience_compress_tier_cell_max") is not None:
            opts["tier_cell_max"] = int(compress["experience_compress_tier_cell_max"])
        if compress.get("experience_compress_scenario_cell_max") is not None:
            opts["scenario_cell_max"] = int(compress["experience_compress_scenario_cell_max"])
        if compress.get("experience_compress_reflect_hist_summary_max") is not None:
            opts["reflect_hist_summary_max"] = int(
                compress["experience_compress_reflect_hist_summary_max"]
            )
    except Exception:
        pass
    return opts


def count_experiment_sections(md: str) -> int:
    return sum(
        1
        for t, _ in split_markdown_h2(md)
        if is_experiment_section(t) and not is_protected_section(t)
    )


def _recent_experiment_container_index(sections: list[tuple[str, str]]) -> int | None:
    for idx, (title, _) in enumerate(sections):
        if title and title.startswith("近期实验"):
            return idx
    return None


def split_experience_sections(
    md: str,
    keep_n: int = DEFAULT_KEEP_N,
    keep_reflects: int = DEFAULT_KEEP_REFLECTS,
) -> ExperienceParts:
    tier_status = parse_tier_status_table(md)
    scenario_block = parse_scenario_block(md)
    sections = split_markdown_h2(md)
    recent_container_idx = _recent_experiment_container_index(sections)
    preamble_parts: list[str] = []
    archivable_misc: list[str] = []
    experiments: list[tuple[str, str]] = []
    pre_container_experiments: list[tuple[str, str]] = []
    reflects: list[tuple[str, str]] = []
    essence_body = ""

    for idx, (title, body) in enumerate(sections):
        if TIER_BLOCK_START in body or TIER_BLOCK_END in body:
            continue
        full = f"## {title}\n{body}".strip() if title else body
        if not title:
            if body.strip():
                preamble_parts.append(body)
            continue
        if title.startswith("精华摘要"):
            essence_body = body
            continue
        if title.startswith("按需查阅") or title.startswith("信息索引"):
            continue
        if title.startswith("近期实验"):
            continue
        if title.startswith("Tier 状态"):
            continue
        if title.startswith("场景") or "场景与 KEEP" in title:
            continue
        if is_reflect_section(title):
            reflects.append((title, body))
            continue
        if is_experiment_section(title):
            if recent_container_idx is not None and idx < recent_container_idx:
                pre_container_experiments.append((title, body))
            else:
                experiments.append((title, body))
            continue
        if is_protected_section(title):
            continue
        archivable_misc.append(full)

    exp_blocks = [f"## {t}\n{b}".strip() for t, b in experiments]
    recent = exp_blocks[-keep_n:] if keep_n else []
    archivable_experiments = exp_blocks[:-keep_n] if keep_n else list(exp_blocks)
    pre_container_blocks = [f"## {t}\n{b}".strip() for t, b in pre_container_experiments]
    archivable = archivable_misc + pre_container_blocks + archivable_experiments

    ref_blocks = [f"## {t}\n{b}".strip() for t, b in reflects]
    ref_recent = ref_blocks[-keep_reflects:] if keep_reflects else []
    ref_arch = ref_blocks[:-keep_reflects] if keep_reflects else list(ref_blocks)

    return ExperienceParts(
        preamble="\n\n".join(preamble_parts).strip(),
        tier_status=tier_status.strip(),
        scenario_block=scenario_block.strip(),
        essence=essence_body.strip(),
        recent_experiments=recent,
        archivable=archivable,
        reflects_recent=ref_recent,
        reflects_archivable=ref_arch,
    )


def c0_stats(md: str) -> dict:
    return {
        "chars": len(md),
        "lines": md.count("\n") + (1 if md else 0),
        "h2_sections": sum(1 for t, _ in split_markdown_h2(md) if t),
        "experiment_sections": count_experiment_sections(md),
        "preflight_mentions": len(re.findall(r"preflight", md, re.I)),
        "has_tier_block": TIER_BLOCK_START in md and TIER_BLOCK_END in md,
    }


def _section_fingerprint(title: str, body: str) -> str:
    norm = re.sub(r"\s+", " ", (title + "\n" + body).strip().lower())[:500]
    return hashlib.sha256(norm.encode()).hexdigest()[:16]


def _is_tier_ladder_section(title: str) -> bool:
    return title.startswith("Tier A") or title.startswith("Tier A–E")


def _tier_status_remarks_len(table: str) -> int:
    """计算 Tier 状态表中有意义的备注/格子内容总长度，用于去重时选更丰富的一个。"""
    mat = _parse_tier_matrix(table)
    total = 0
    for depths in mat.values():
        for v in depths.values():
            if v and v not in ("未试", "—", "-", "?"):
                total += len(v)
    return total


def _strip_tier_block_markers(md: str) -> tuple[str, int]:
    removed = 0
    for marker in (TIER_BLOCK_START, TIER_BLOCK_END):
        while marker in md:
            md = md.replace(marker, "", 1)
            removed += 1
    return md, removed


def _remove_tier_ladder_sections(sections: list[tuple[str, str]]) -> tuple[list[tuple[str, str]], int]:
    out: list[tuple[str, str]] = []
    removed = 0
    for title, body in sections:
        if title and _is_tier_ladder_section(title):
            removed += 1
            continue
        if TIER_BLOCK_START in body or TIER_BLOCK_END in body:
            removed += 1
            continue
        out.append((title, body))
    return out, removed


def _merge_tier_status_sections(sections: list[tuple[str, str]]) -> tuple[list[tuple[str, str]], int]:
    tier_blocks: list[tuple[int, str, str, int]] = []
    for idx, (title, body) in enumerate(sections):
        if title and title.startswith("Tier 状态"):
            full = f"## {title}\n{body}".strip()
            tier_blocks.append((idx, title, body, _tier_status_remarks_len(full)))
    if len(tier_blocks) <= 1:
        return sections, 0
    best = max(tier_blocks, key=lambda x: x[3])
    keep_idx = best[0]
    removed = 0
    out: list[tuple[str, str]] = []
    for idx, (title, body) in enumerate(sections):
        if title and title.startswith("Tier 状态"):
            if idx != keep_idx:
                removed += 1
                continue
        out.append((title, body))
    return out, removed


def c1_dedupe_duplicate_log_markers(md: str) -> tuple[str, int]:
    """C1: collapse duplicate experience-log-start markers (Agent 误插) into one."""
    if md.count(EXPERIENCE_LOG_START) <= 1:
        return md, 0
    first = md.find(EXPERIENCE_LOG_START)
    if first < 0:
        return md, 0
    head = md[: first + len(EXPERIENCE_LOG_START)]
    tail = md[first + len(EXPERIENCE_LOG_START) :]
    removed = tail.count(EXPERIENCE_LOG_START)
    tail = tail.replace(EXPERIENCE_LOG_START, "\n")
    if EXPERIENCE_LOG_END in tail:
        tail = tail.replace(EXPERIENCE_LOG_END, "")
    return head + tail, removed


def c1_dedupe_redundant_blocks(md: str) -> tuple[str, int]:
    """C1: strip legacy tier ladder/markers, merge duplicate Tier 状态, dedupe adjacent h2."""
    removed = 0
    md, n_log_markers = c1_dedupe_duplicate_log_markers(md)
    removed += n_log_markers
    md, n_markers = _strip_tier_block_markers(md)
    removed += n_markers

    sections = split_markdown_h2(md)
    if not sections:
        return md, removed

    sections, n_ladder = _remove_tier_ladder_sections(sections)
    removed += n_ladder

    sections, n_tier = _merge_tier_status_sections(sections)
    removed += n_tier

    out: list[tuple[str, str]] = []
    prev_fp: str | None = None
    for title, body in sections:
        fp = _section_fingerprint(title, body) if title else None
        if fp and fp == prev_fp:
            removed += 1
            continue
        out.append((title, body))
        prev_fp = fp

    parts: list[str] = []
    for title, body in out:
        if not title:
            if body:
                parts.append(body)
        else:
            parts.append(f"## {title}\n{body}".strip())
    return "\n\n".join(parts).strip() + ("\n" if md.endswith("\n") else ""), removed


def load_facts_from_tsv(
    repo_root: Path,
    metric_key: str,
    metric_direction: str = "maximize",
    recent_n: int = 15,
) -> dict:
    tsv = repo_root / "_runs" / "results.tsv"
    empty = {
        "best_experiment": None,
        "best_primary": None,
        "metric_key": metric_key,
        "recent_rows": [],
        "preflight_ratio": 0.0,
        "known_experiments": [],
    }
    if not tsv.is_file():
        return dict(empty)

    rows: list[dict[str, str]] = []
    with open(tsv, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            rows.append(row)
    if not rows:
        return dict(empty)

    def parse_metric(val: str | None) -> float | None:
        if val is None or str(val).strip() == "":
            return None
        try:
            x = float(val)
        except ValueError:
            return None
        if x != x:  # nan
            return None
        return x

    non_pf = [
        r
        for r in rows
        if "preflight" not in (r.get("experiment") or "").lower()
    ]
    pf_ratio = 1.0 - (len(non_pf) / len(rows)) if rows else 0.0
    best_exp, best_val = None, None
    for r in non_pf:
        v = parse_metric(r.get(metric_key))
        if v is None:
            continue
        if best_val is None:
            best_exp, best_val = r.get("experiment"), v
            continue
        if metric_direction == "minimize":
            if v < best_val:
                best_exp, best_val = r.get("experiment"), v
        else:
            if v > best_val:
                best_exp, best_val = r.get("experiment"), v

    recent = non_pf[-recent_n:]
    recent_rows = [
        {"experiment": r.get("experiment"), metric_key: r.get(metric_key)}
        for r in recent
    ]
    known = sorted({r.get("experiment") or "" for r in rows if r.get("experiment")})
    return {
        "best_experiment": best_exp,
        "best_primary": best_val,
        "metric_key": metric_key,
        "recent_rows": recent_rows,
        "preflight_ratio": round(pf_ratio, 4),
        "known_experiments": known,
    }


def build_rule_essence(
    facts: dict,
    archivable_count: int,
    *,
    tier_snapshot: str | None = None,
    plateau_line: str | None = None,
    tier_remarks: str | None = None,
    repo_root: Path | None = None,
) -> str:
    mk = facts.get("metric_key") or "metric"
    best_exp = facts.get("best_experiment") or "（无，见 TSV）"
    best_val = facts.get("best_primary")
    val_s = f"{best_val:.6g}" if isinstance(best_val, (int, float)) else "?"
    lines = [
        f"- **当前 SOTA（来自 _runs/results.tsv）**: `{best_exp}` · {mk}={val_s}",
        f"- **Plateau**: {plateau_line or 'focus=? plateau=?/?'}",
        f"- **Tier 快照**: {tier_snapshot or 'A:? B:? C:? D:? E:?'}",
        f"- **本档要点**: {tier_remarks if tier_remarks is not None else '-'}",
        f"- **preflight 行占比**: {facts.get('preflight_ratio', 0):.1%}",
        f"- **本轮归档实验段**: {archivable_count} 条（全文见 `references/experience/archive_*.md`）",
    ]
    if facts.get("recent_rows"):
        lines.append("- **近端台账（摘要）**:")
        for row in facts["recent_rows"][-5:]:
            lines.append(f"  - `{row.get('experiment')}`: {mk}={row.get(mk, '?')}")
    if repo_root is not None:
        from lib.reflect_brief import reflect_pending_one_liner

        pending = reflect_pending_one_liner(repo_root)
        if pending:
            lines.append(f"- **REFLECT pending**: {pending}")
    return "\n".join(lines)


def _extract_candidate_experiments(text: str) -> set[str]:
    found: set[str] = set()
    for m in _EXPERIMENT_NAME_RE.finditer(text):
        tok = m.group(1)
        if tok.lower() in ("tsv", "json", "jsonl", "tier", "compress", "markdown"):
            continue
        if tok.startswith("20") and len(tok) >= 8:
            continue
        found.add(tok)
    return found


def validate_essence(
    essence: str,
    known_experiments: list[str],
    *,
    tier_status_present: bool,
    assembled_md: str | None = None,
) -> str | None:
    if not tier_status_present:
        return "missing ## Tier 状态 in source EXPERIENCE"
    if assembled_md is not None:
        head = "\n".join(assembled_md.splitlines()[:30])
        if "## 精华摘要" not in head:
            return "## 精华摘要 not in first 30 lines after apply"
    known = set(known_experiments)
    for tok in _extract_candidate_experiments(essence):
        if tok in known:
            continue
        if any(tok in k for k in known if k):
            continue
        if "unknown" in tok.lower() and tok not in known:
            return f"essence mentions unknown experiment token: {tok}"
        if tok.startswith("exp_") and tok not in known:
            return f"essence mentions experiment not in TSV: {tok}"
    return None


def assemble_experience(
    parts: ExperienceParts,
    essence: str,
    keep_n: int,
    *,
    tier_status: str | None = None,
    scenario_block: str | None = None,
    tier_cell_max: int = DEFAULT_TIER_CELL_MAX,
    scenario_cell_max: int = DEFAULT_SCENARIO_CELL_MAX,
) -> str:
    tier_status = parts.tier_status if tier_status is None else tier_status
    scenario_block = parts.scenario_block if scenario_block is None else scenario_block
    if tier_status.strip():
        tier_status = truncate_tier_status_table(tier_status, tier_cell_max)
    if scenario_block.strip():
        scenario_block = truncate_scenario_block(scenario_block, scenario_cell_max)
    recent_hdr = RECENT_HEADING_TEMPLATE.format(n=keep_n)
    title_line = parts.preamble.split("\n", 1)[0].strip() if parts.preamble.strip() else "# EXPERIENCE"
    chunks: list[str] = [
        title_line,
        ESSENCE_HEADING + "\n\n" + essence.strip(),
        build_source_index_block(),
    ]
    if scenario_block.strip():
        chunks.append(scenario_block.strip())
    if tier_status.strip():
        chunks.append(tier_status.strip())
    chunks.append(recent_hdr)
    if parts.recent_experiments:
        chunks.extend(parts.recent_experiments)
    else:
        chunks.append("（无近期实验段；见归档与 TSV）")
    chunks.extend(parts.reflects_recent)
    chunks.append(EXPERIENCE_LOG_START)
    return "\n\n".join(chunks) + "\n"
