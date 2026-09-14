"""说明书卫生：退役旧名 + 头注释对象类型 vs 正文默认类型冲突（doctor WARN）。"""
from __future__ import annotations

import re
from pathlib import Path

MANUAL_REL = Path("references/manual/abcde-manual.md")

# 首版：子串命中即记；不豁免「原 xxx」（SPEC 默认更吵更安全）
LEGACY_TOKENS: tuple[str, ...] = (
    "workspace_full",
    "Greenfield",
    "O3-exploration",
    "4-scenario router",
)

_HEADER_OT = re.compile(
    r"(?:对象类型|object_type)\s*=\s*(data|code|framework)",
    re.IGNORECASE,
)
_BODY_DEFAULT_OT = re.compile(
    r"默认对象类型\s*[:：]\s*\*?\*?(data|code|framework)\*?\*?",
    re.IGNORECASE,
)


def find_abcde_manual_hygiene_issues(repo_root: Path) -> list[str]:
    """返回警告文案列表；空 = 通过。手册不存在 → 空（由 abcde_manual 存在性闸处理）。"""
    path = Path(repo_root).resolve() / MANUAL_REL
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"无法读取 abcde-manual.md: {exc}"]

    issues: list[str] = []
    for tok in LEGACY_TOKENS:
        if tok in text:
            issues.append(f"正文含退役旧名 `{tok}`")

    header_m = _HEADER_OT.search(text)
    body_m = _BODY_DEFAULT_OT.search(text)
    if header_m and body_m:
        h = header_m.group(1).lower()
        b = body_m.group(1).lower()
        if h != b:
            issues.append(f"头注释对象类型={h} 与正文默认对象类型={b} 冲突")

    return issues


def doctor_abcde_manual_hygiene(repo_root: Path) -> tuple[str, str] | None:
    """None = 无手册、跳过不报行；否则 (PASS|WARN, msg)。"""
    path = Path(repo_root).resolve() / MANUAL_REL
    if not path.is_file():
        return None
    issues = find_abcde_manual_hygiene_issues(repo_root)
    if not issues:
        return ("PASS", "abcde-manual 无旧名/头身冲突")
    return ("WARN", "; ".join(issues))
