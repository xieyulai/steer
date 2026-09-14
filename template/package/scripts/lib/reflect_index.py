"""REFLECT_INDEX.md 读写：pending 解析、消费归档、reflect 覆盖前归档、健康审计。"""
from __future__ import annotations

import re
from pathlib import Path

_PENDING_PLACEHOLDERS = frozenset({"（无）", "—", "-", "", "id"})
_PENDING_HEADER = (
    "| id | 时间 | 撞墙 | 下轮建议（一行） | Tier | 详文 |\n"
    "|----|------|------|------------------|------|------|\n"
)
_EMPTY_PENDING = "| （无） | — | — | — | — | — |"
_HIST_HEADER = (
    "| id | 时间 | 撞墙 | 下轮建议 | 结果摘要 |\n"
    "|----|------|------|----------|----------|\n"
)
_EMPTY_HIST = "| （尚无） | — | — | — | — |"
_MAX_HIST_ROWS = 15
_MAX_SUMMARY_CHARS = 240


def _truncate_summary(value: str, max_len: int = _MAX_SUMMARY_CHARS) -> str:
    s = re.sub(r"\s+", " ", (value or "").strip())
    if len(s) <= max_len:
        return s
    return s[: max(0, max_len - 1)] + "…"


def _sanitize_cell(value: str) -> str:
    return value.replace("|", "/")


def parse_pending_cells(text: str) -> list[str] | None:
    """解析 pending 首行：优先 ## 待消费；否则 legacy 首表（blockquote 后、## 历史 前）。"""
    m = re.search(r"##\s*待消费[^\n]*\n(.*?)(?=\n##\s|\Z)", text, re.DOTALL | re.I)
    if m:
        for line in m.group(1).splitlines():
            cells = _parse_pending_row(line)
            if cells:
                return cells
    legacy = re.search(r"##\s*历史[^\n]*", text, re.I)
    head = text[: legacy.start()] if legacy else text
    past_sep = False
    for line in head.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        if "---" in line:
            past_sep = True
            continue
        if not past_sep:
            continue
        cells = _parse_pending_row(line)
        if cells:
            return cells
    return None


def _parse_pending_row(line: str) -> list[str] | None:
    line = line.strip()
    if not line.startswith("|") or "---" in line:
        return None
    cells = [c.strip() for c in line.strip("|").split("|")]
    if len(cells) >= 6 and cells[0] not in _PENDING_PLACEHOLDERS:
        return cells[:6]
    return None


def _history_data_rows(hist_body: str) -> list[str]:
    rows: list[str] = []
    for line in hist_body.splitlines():
        line = line.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if cells and cells[0] not in _PENDING_PLACEHOLDERS and cells[0] != "（尚无）":
            rows.append(line)
    return rows


def _rebuild_history_section(
    existing_hist_body: str,
    new_row: str,
    *,
    max_summary: int = _MAX_SUMMARY_CHARS,
) -> str:
    rows = [_truncate_history_row(new_row, max_summary)]
    for row in _history_data_rows(existing_hist_body):
        if row != new_row:
            rows.append(_truncate_history_row(row, max_summary))
    rows = rows[:_MAX_HIST_ROWS]
    if not rows:
        return _HIST_HEADER + _EMPTY_HIST + "\n"
    return _HIST_HEADER + "\n".join(rows) + "\n"


def _truncate_history_row(row: str, max_summary: int) -> str:
    if not row.strip().startswith("|"):
        return row
    cells = [c.strip() for c in row.strip("|").split("|")]
    if len(cells) >= 5:
        cells[4] = _sanitize_cell(_truncate_summary(cells[4], max_summary))
    return "| " + " | ".join(cells) + " |"


def _split_pending_and_history(text: str) -> tuple[str, str, str]:
    """返回 (head含待消费标题, pending区原文, 历史区含标题)."""
    m = re.search(r"(##\s*待消费[^\n]*\n)", text, re.I)
    if not m:
        return text, "", ""
    head = text[: m.end()]
    rest = text[m.end() :]
    hist_m = re.search(r"\n(##\s*历史[^\n]*\n)", rest, re.I)
    if hist_m:
        pending_part = rest[: hist_m.start()]
        hist_part = rest[hist_m.start() + 1 :]
        return head, pending_part, hist_part
    return head, rest, ""


def append_history_row(text: str, hist_row: str) -> str:
    """将一行写入 ## 历史（已消费），保持表格结构。"""
    head, _pending_part, hist_part = _split_pending_and_history(text)
    if not hist_part.strip():
        hist_body = _rebuild_history_section("", hist_row)
        return head + _PENDING_HEADER + _EMPTY_PENDING + "\n\n## 历史（已消费）\n\n" + hist_body
    hist_m = re.match(r"(##\s*历史[^\n]*\n)(.*)", hist_part, re.DOTALL | re.I)
    if not hist_m:
        return text
    hist_hdr, hist_body = hist_m.group(1), hist_m.group(2)
    new_body = _rebuild_history_section(hist_body, hist_row)
    return head + _pending_part + hist_hdr + new_body


def mark_pending_consumed(text: str, summary: str) -> tuple[str, str | None]:
    """pending → 历史；清空 pending。返回 (新文本, consumed_id)。"""
    cells = parse_pending_cells(text)
    if not cells:
        return text, None
    rid, ts, wall, suggest, _tier, _detail = cells
    hist_row = (
        f"| {rid} | {ts} | {wall} | {suggest} | {_sanitize_cell(_truncate_summary(summary))} |"
    )
    head, _pending_part, hist_part = _split_pending_and_history(text)
    if hist_part.strip():
        hist_m = re.match(r"(##\s*历史[^\n]*\n)(.*)", hist_part, re.DOTALL | re.I)
        hist_hdr, hist_body = hist_m.group(1), hist_m.group(2) if hist_m else ("## 历史（已消费）\n\n", "")
    else:
        hist_hdr, hist_body = "## 历史（已消费）\n\n", ""
    new_hist = _rebuild_history_section(hist_body, hist_row, max_summary=_MAX_SUMMARY_CHARS)
    new_text = (
        head
        + _PENDING_HEADER
        + _EMPTY_PENDING
        + "\n\n"
        + hist_hdr
        + new_hist
    )
    return new_text, rid


def set_pending_row(
    text: str,
    *,
    reflect_id: str,
    ts_display: str,
    wall_short: str,
    next_round: str,
    tier_letter: str,
    detail_rel: str,
    archive_summary: str = "被新反思覆盖（未消费）",
) -> str:
    """覆盖 pending；若已有未消费 pending 则先归档到历史。"""
    cells = parse_pending_cells(text)
    if cells:
        text, _ = mark_pending_consumed(text, archive_summary)
    nr = _sanitize_cell(next_round)
    ws = _sanitize_cell(wall_short)
    pending_row = f"| {reflect_id} | {ts_display} | {ws} | {nr} | {tier_letter} | {detail_rel} |"
    head, _pending_part, hist_part = _split_pending_and_history(text)
    if "## 待消费" not in text:
        text = (
            text.rstrip()
            + "\n\n## 待消费（pending）\n\n"
            + _PENDING_HEADER
            + pending_row
            + "\n\n## 历史（已消费）\n\n"
            + _HIST_HEADER
            + _EMPTY_HIST
            + "\n"
        )
        return text
    if hist_part.strip():
        return head + _PENDING_HEADER + pending_row + "\n\n" + hist_part
    return head + _PENDING_HEADER + pending_row + "\n\n## 历史（已消费）\n\n" + _HIST_HEADER + _EMPTY_HIST + "\n"


def default_index_template() -> str:
    return (
        "# Reflect index（机维护，勿手改 pending）\n\n"
        "> 实验 Agent：若 **`## 待消费`** 表格有数据行，须 `Read` 本文件并遵守「下轮建议」；"
        "在 EXPERIENCE 写 `reflect_ack:`。\n"
        "> 详文见 `references/auto/`；优先级低于 `HUMAN_GUIDANCE.md`（PROTOCOL §7.6）。\n\n"
        "## 待消费（pending）\n\n"
        f"{_PENDING_HEADER}"
        f"{_EMPTY_PENDING}\n\n"
        "## 历史（已消费）\n\n"
        f"{_HIST_HEADER}"
        f"{_EMPTY_HIST}\n"
    )


def _pending_data_rows(text: str) -> list[str]:
    m = re.search(r"##\s*待消费[^\n]*\n(.*?)(?=\n##\s|\Z)", text, re.DOTALL | re.I)
    if not m:
        return []
    rows: list[str] = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|") or "---" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 6 and cells[0] not in _PENDING_PLACEHOLDERS:
            rows.append(line)
    return rows


def _history_section_body(text: str) -> str:
    m = re.search(r"##\s*历史[^\n]*\n(.*)", text, re.DOTALL | re.I)
    return m.group(1) if m else ""


def history_table_malformed(text: str) -> bool:
    """历史区是否存在表头分隔符前的数据行（旧 mark-reflect-consumed bug）。"""
    body = _history_section_body(text)
    if not body.strip():
        return False
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    sep_idx = next(
        (i for i, ln in enumerate(lines) if ln.startswith("|") and "---" in ln),
        None,
    )
    if sep_idx is None:
        return bool(_history_data_rows(body))
    for ln in lines[:sep_idx]:
        if ln.startswith("|") and "---" not in ln:
            cells = [c.strip() for c in ln.strip("|").split("|")]
            if cells and cells[0] not in _PENDING_PLACEHOLDERS and cells[0] != "（尚无）":
                return True
    return False


def repair_reflect_index_history_summaries(
    text: str,
    *,
    max_summary: int = _MAX_SUMMARY_CHARS,
) -> tuple[str, int]:
    """C2 配套：截断历史表「结果摘要」列（清理历史债务长 ack）。"""
    head, pending_part, hist_part = _split_pending_and_history(text)
    if not hist_part.strip():
        return text, 0
    hist_m = re.match(r"(##\s*历史[^\n]*\n)(.*)", hist_part, re.DOTALL | re.I)
    if not hist_m:
        return text, 0
    hist_hdr, hist_body = hist_m.group(1), hist_m.group(2)
    rows = _history_data_rows(hist_body)
    if not rows:
        return text, 0
    fixed = 0
    new_rows: list[str] = []
    for row in rows:
        cells = [c.strip() for c in row.strip("|").split("|")]
        if len(cells) >= 5 and len(cells[4]) > max_summary:
            fixed += 1
        new_rows.append(_truncate_history_row(row, max_summary))
    hist_content = _HIST_HEADER + "\n".join(new_rows[:_MAX_HIST_ROWS]) + "\n"
    new_text = head + pending_part + hist_hdr + hist_content
    return new_text, fixed


def repair_reflect_index_text(text: str) -> tuple[str, bool]:
    """重建历史表结构；保留 pending 与全部有效历史行。"""
    if not history_table_malformed(text):
        return text, False
    head, _pending_part, hist_part = _split_pending_and_history(text)
    hist_body = _history_section_body(text)
    rows = _history_data_rows(hist_body)
    # 5 列历史行（旧 bug 可能缺表头）
    rebuilt_rows: list[str] = []
    for row in rows:
        cells = [c.strip() for c in row.strip("|").split("|")]
        if len(cells) == 5:
            rebuilt_rows.append(row)
        elif len(cells) >= 6:
            rebuilt_rows.append(
                f"| {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} | {cells[4]} |"
            )
    hist_content = _HIST_HEADER
    if rebuilt_rows:
        hist_content += "\n".join(rebuilt_rows[:_MAX_HIST_ROWS]) + "\n"
    else:
        hist_content += _EMPTY_HIST + "\n"
    if hist_part.strip():
        hist_m = re.match(r"(##\s*历史[^\n]*\n)", hist_part, re.I)
        hist_hdr = hist_m.group(1) if hist_m else "## 历史（已消费）\n\n"
    else:
        hist_hdr = "## 历史（已消费）\n\n"
    pending_block = _pending_part.strip()
    if not pending_block:
        pending_block = _PENDING_HEADER + _EMPTY_PENDING
    new_text = head + pending_block + "\n\n" + hist_hdr + hist_content
    return new_text, True


def audit_reflect_index(repo_root: Path) -> list[tuple[str, str]]:
    """返回 (FAIL|WARN, message) 列表；空列表 = 健康。"""
    issues: list[tuple[str, str]] = []
    root = repo_root.resolve()
    index_path = root / "references" / "REFLECT_INDEX.md"
    if not index_path.is_file():
        issues.append(("FAIL", "缺少 references/REFLECT_INDEX.md"))
        return issues

    for rel in (
        "scripts/lib/reflect_index.py",
        "scripts/mark_reflect_consumed.py",
        "scripts/mark-reflect-consumed.sh",
    ):
        if not (root / rel).is_file():
            issues.append(("WARN", f"缺少 {rel} — governance-sync"))

    text = index_path.read_text(encoding="utf-8", errors="replace")
    if "## 待消费" not in text:
        issues.append(("FAIL", "REFLECT_INDEX 缺少 ## 待消费"))
    if "## 历史" not in text:
        issues.append(("FAIL", "REFLECT_INDEX 缺少 ## 历史"))

    pending_rows = _pending_data_rows(text)
    if len(pending_rows) > 1:
        issues.append(("FAIL", f"待消费 pending 超过 1 条（{len(pending_rows)}）"))

    if history_table_malformed(text):
        issues.append(("FAIL", "历史表结构损坏（数据行在表头之前）— 运行 repair-reflect-index.sh --apply"))

    cells = parse_pending_cells(text)
    if cells:
        _rid, _ts, _wall, suggest, _tier, detail = cells
        if len(suggest) > 480:
            issues.append(("WARN", "pending 下轮建议单元格过长（>480），TAM 应进详文"))
        detail_path = root / detail
        if detail and not detail_path.is_file():
            issues.append(("WARN", f"pending 详文不存在: {detail}"))

    auto_dir = root / "references" / "auto"
    auto_n = len(list(auto_dir.glob("*_auto_reflected.md"))) if auto_dir.is_dir() else 0
    hist_n = len(_history_data_rows(_history_section_body(text)))
    if auto_n >= 2 and hist_n == 0 and not pending_rows:
        issues.append(
            (
                "WARN",
                f"references/auto/ 有 {auto_n} 份长文但 INDEX 历史为空 — 消费链可能未记账",
            )
        )

    return issues


def format_audit_lines(repo_root: Path) -> list[str]:
    issues = audit_reflect_index(repo_root)
    if not issues:
        return ["PASS:reflect_index 结构正常"]
    return [f"{level}:reflect_index {msg}" for level, msg in issues]
