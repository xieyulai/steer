"""Init HARD-GATE 问答忠实 log — 读写 `.auto-nn/init-qa-log.md`。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

LOG_NAME = "init-qa-log.md"
LOG_MARKER = "## 日志"
META_MARKER = "## 元数据"

# workflow 维度(PR1.6 加,PR2.5 切到单维度)
MIN_ENTRIES_BY_WORKFLOW = {
    "build": 25,    # greenfield 24 步 + 准备（2026-09 信息权限 I1–I3 入题；原 22）
    "migrate": 28,  # 迁入 27 步 + 准备（含 H1-H3；原 25）
    "update": 15,   # 二次 init 步数
}


def log_path(repo_root: Path) -> Path:
    return repo_root / ".auto-nn" / LOG_NAME


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _read(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _ensure_skeleton(path: Path) -> str:
    text = _read(path)
    if text.strip():
        return text
    skeleton = """# Init 问答忠实记录（HARD-GATE）

> **状态**: 进行中
> **路径**: `.auto-nn/init-qa-log.md`
> **性质**: 迁后留档；运行时不读

## 元数据

## 日志

"""
    _write(path, skeleton)
    return skeleton


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str]
    warnings: list[str]
    entry_count: int
    closed: bool


def init_header(
    repo_root: Path,
    *,
    workflow: str,
    target_root: str,
    source_root: str | None = None,
) -> None:
    path = log_path(repo_root)
    text = _ensure_skeleton(path)
    ts = _now_iso()
    meta = [
        f"- **workflow**: {workflow}",
        f"- **target_root**: {target_root}",
    ]
    if source_root:
        meta.append(f"- **source_root**: {source_root}")
    meta.append(f"- **started**: {ts}")
    block = "\n".join(meta) + "\n"
    if META_MARKER in text:
        head, rest = text.split(META_MARKER, 1)
        _, log_part = rest.split(LOG_MARKER, 1) if LOG_MARKER in rest else ("", rest)
        text = head + META_MARKER + "\n\n" + block + "\n" + LOG_MARKER + log_part
    _write(path, text)


def _slug_rev_counts(text: str, slug: str) -> int:
    pattern = re.compile(
        rf"^### .* · {re.escape(slug)} · .* · rev=(\d+)\s*$",
        re.MULTILINE,
    )
    revs = [int(m.group(1)) for m in pattern.finditer(text)]
    return max(revs) if revs else 0


def append_entry(
    repo_root: Path,
    *,
    step: str,
    total: int | None,
    slug: str,
    theme: str,
    ask: str,
    options: str,
    user: str,
    lock: str,
) -> None:
    path = log_path(repo_root)
    text = _ensure_skeleton(path)
    rev = _slug_rev_counts(text, slug) + 1
    step_label = step if "/" in step or step in {"准备", "0", "签字"} else f"{step}/{total or '?'}"
    title = f"### {step_label} · {slug} · {theme} · rev={rev}"
    body = "\n".join(
        [
            title,
            "",
            f"- **问（摘要）**: {ask.strip()}",
            f"- **选项**: {options.strip()}",
            f"- **用户**: {user.strip()}",
            f"- **锁定（内部）**: {lock.strip()}",
            f"- **ts**: {_now_iso()}",
            "",
        ]
    )
    if LOG_MARKER not in text:
        text = text.rstrip() + "\n\n" + LOG_MARKER + "\n\n"
    idx = text.index(LOG_MARKER) + len(LOG_MARKER)
    text = text[:idx] + "\n\n" + body + text[idx:].lstrip("\n")
    _write(path, text)


def close_log(
    repo_root: Path,
    *,
    user: str,
    contradiction_fail: int = 0,
    note: str = "",
) -> None:
    append_entry(
        repo_root,
        step="签字",
        total=None,
        slug="F1-contract",
        theme="口径汇总",
        ask="口径汇总表请最终确认",
        options="确认 / 修改",
        user=user.strip(),
        lock=f"migration-summary 已覆盖；contradiction_check FAIL={contradiction_fail}"
        + (f"; {note}" if note else ""),
    )
    path = log_path(repo_root)
    text = _read(path)
    if "**closed**:" not in text:
        # 不依赖 header status 字符串的固定文本（init-header 的实际字符串可能变）：
        # 直接 append 一行 `> **closed>: <ts>`，validator 只要 `**closed**:` 命中即可。
        text += f"\n> **closed**: {_now_iso()}\n"
        _write(path, text)


_ENTRY_HEAD = re.compile(
    r"^### (?P<step>.+?) · (?P<slug>\S+) · (?P<theme>.+?) · rev=(?P<rev>\d+)\s*$"
)


@dataclass
class LogEntry:
    slug: str
    theme: str
    user: str
    lock: str
    rev: int
    step: str
    ask: str = ""
    options: str = ""


def parse_workflow(text: str) -> str | None:
    m = re.search(r"^- \*\*workflow\*\*: (\w+)", text, re.MULTILINE)
    return m.group(1) if m else None


def parse_entries(text: str) -> list[LogEntry]:
    """解析问答记录正文；同 slug 多 rev 都保留（导出时取最大 rev）。"""
    entries: list[LogEntry] = []
    current: dict[str, str] | None = None
    fields: dict[str, str] = {}

    def flush() -> None:
        nonlocal current, fields
        if not current:
            return
        entries.append(
            LogEntry(
                slug=current["slug"],
                theme=current["theme"],
                user=fields.get("user", "").strip(),
                lock=fields.get("lock", "").strip(),
                rev=int(current["rev"]),
                step=current["step"],
                ask=fields.get("ask", "").strip(),
                options=fields.get("options", "").strip(),
            )
        )
        current, fields = None, {}

    labels = {
        "问（摘要）": "ask",
        "选项": "options",
        "用户": "user",
        "锁定（内部）": "lock",
    }
    for line in text.splitlines():
        hm = _ENTRY_HEAD.match(line)
        if hm:
            flush()
            current = hm.groupdict()
            fields = {}
            continue
        if current is None:
            continue
        for label, key in labels.items():
            prefix = f"- **{label}**: "
            if line.startswith(prefix):
                fields[key] = line[len(prefix) :]
                break
    flush()
    return entries


def latest_by_slug(entries: list[LogEntry]) -> dict[str, LogEntry]:
    out: dict[str, LogEntry] = {}
    for e in entries:
        prev = out.get(e.slug)
        if prev is None or e.rev >= prev.rev:
            out[e.slug] = e
    return out


def count_entries(text: str) -> int:
    return len(re.findall(r"^### ", text, re.MULTILINE))


def is_closed(text: str) -> bool:
    return "**closed**:" in text or "> **状态**: 已闭合" in text


def validate(repo_root: Path, *, require_closed: bool = False) -> ValidationResult:
    path = log_path(repo_root)
    errors: list[str] = []
    warnings: list[str] = []
    if not path.is_file() or not path.stat().st_size:
        errors.append("缺少或非空 .auto-nn/init-qa-log.md")
        return ValidationResult(False, errors, warnings, 0, False)
    text = _read(path)
    if "- **workflow**:" not in text:
        errors.append("init-qa-log 缺少 init-header（workflow 元数据）")
    if "- **target_root**:" not in text:
        errors.append("init-qa-log 缺少 target_root")
    n = count_entries(text)
    closed = is_closed(text)
    workflow_m = re.search(r"- \*\*workflow\*\*: (\w+)", text)
    workflow = workflow_m.group(1) if workflow_m else ""
    min_n = MIN_ENTRIES_BY_WORKFLOW.get(workflow, 0)
    if n < min_n:
        warnings.append(f"init-qa-log 条目数 {n} < 期望约 {min_n}（可能 HARD-GATE 未完成或漏记）")
    if "F1-contract" not in text:
        warnings.append("init-qa-log 缺少 F1-contract 条目")
    if require_closed and not closed:
        errors.append("init-qa-log 未 close（缺 closed 时间戳）")
    if not re.search(r"^### .* · F1-contract ·", text, re.MULTILINE):
        if require_closed:
            errors.append("init-qa-log 缺少 F1-contract 三级标题条目")
    ok = not errors
    return ValidationResult(ok, errors, warnings, n, closed)
