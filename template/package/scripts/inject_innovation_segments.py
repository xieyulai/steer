"""Render the Tier-sliced guidance segment appended to _inject_innovation_prompt.

纯函数，被 tests 与 auto-nn-run.sh 的 bash append 块共用（tests 直调 Python，不 shell out）。

改造后（enforcement + modifier_seeds 退役）：只剩一条链路——
  render_tier_slice(repo_root): 读 EXPERIENCE.md Tier 状态矩阵找最高 rank cell
    (letter, depth) → 切 references/manual/abcde-manual.md 的对应 cell 注入。

与 yaml 载体零耦合（直接切 references/manual/abcde-manual.md 的 cell）。
旧 schema（无 manual / 无 EXPERIENCE）→ 空串 no-op（drift-lock）。
"""
from __future__ import annotations

import re
from pathlib import Path

_DEPTH_ORDER = ["routine", "derived", "different"]
_STATE_RANK = {"未试": 0, "假升档": 1, "浅尝": 2, "进行中": 3, "已穷尽": 4}
_DEPTH_COL = {"routine": 0, "derived": 1, "different": 2}


def parse_tier_state(experience_md: Path) -> dict[str, str]:
    """Find the highest-rank cell in the Tier 状态矩阵.

    Returns {"letter": "A".."E", "depth": "routine"|"derived"|"different",
             "score": int} or {} when no matrix is found.
    """
    if not experience_md.exists():
        return {}
    txt = experience_md.read_text(encoding="utf-8")
    sec = re.search(r"^## Tier 状态（", txt, re.M)
    if not sec:
        return {}
    block = txt[sec.start():]
    nxt = re.search(r"\n^## ", block[1:], re.M)
    if nxt:
        block = block[: nxt.start() + 1]
    best: dict = {"letter": "A", "depth": "routine", "score": -1}
    for row in block.splitlines():
        if "|" not in row or "Tier" in row or row.strip().startswith("|-"):
            continue
        parts = [p.strip() for p in row.strip("|").split("|") if p.strip()]
        if len(parts) < 4:
            continue
        letter = parts[0]
        for depth_idx, cell in enumerate(parts[1:4]):
            score = _STATE_RANK.get(cell, -1)
            if score > best["score"]:
                best = {"letter": letter, "depth": _DEPTH_ORDER[depth_idx], "score": score}
    return best


def extract_manual_cell(manual_md: Path, letter: str, depth: str) -> str:
    """从 manual 的 5×3 表里切 (letter, depth) 对应 cell 的文本。

    表头行含 routine/derived/different 三列；定位 letter 行 → 取 depth 对应列单元格。
    缺文件 / 无表 / 无行 → ""（graceful no-op；旧 schema extend/novel 表头 drift-lock）。
    """
    if not manual_md.exists():
        return ""
    txt = manual_md.read_text(encoding="utf-8")
    # 找 5×3 表：含 routine | derived | different 的表头行
    m = re.search(r"^\|.*\broutine\b.*\bderived\b.*\bdifferent\b.*\|\s*$", txt, re.M)
    if not m:
        return ""
    rest = txt[m.start():]
    # 表行 = 以 | 开头、含 4 段（档|routine|derived|different）；到下一个非表行或 ## 结束
    lines = []
    for ln in rest.splitlines()[1:]:  # 跳表头
        if not ln.strip().startswith("|"):
            break
        if re.match(r"^\|[-:\s|]+\|\s*$", ln.strip()):
            continue  # 分隔行
        lines.append(ln)
    col_idx = _DEPTH_COL.get(depth, 0)
    L = letter.upper()
    for ln in lines:
        cells = [c.strip() for c in ln.strip("|").split("|")]
        if len(cells) < 4:
            continue
        if cells[0].upper().startswith(L):
            return cells[col_idx + 1]
    return ""


def render_tier_slice(repo_root: Path) -> str:
    """Return the injected Tier-sliced guidance block (or empty string).

    Reads EXPERIENCE.md and references/manual/abcde-manual.md from repo_root.
    Returns "" if either file is missing or no Tier matrix is present (drift-lock:
    旧 schema 无 manual → no-op，不炸).
    """
    exp = repo_root / "EXPERIENCE.md"
    manual = repo_root / "references" / "manual" / "abcde-manual.md"
    if not exp.exists() or not manual.exists():
        return ""
    best = parse_tier_state(exp)
    if not best:
        return ""
    cell = extract_manual_cell(manual, best["letter"], best["depth"])
    if not cell:
        return ""
    return (
        f"\n## 当前阶段的创新指南（按 Tier 切片自 references/manual/abcde-manual.md）\n\n"
        f"**当前最高 Tier 状态**: {best['letter']} 档 / {best['depth']}\n\n"
        f"{cell}\n"
    )
