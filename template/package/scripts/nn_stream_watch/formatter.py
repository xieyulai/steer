"""Event → colored string renderer + status panel.

Public API:
  render_event(event, state, ansi, ...) -> str
  render_status_panel(state, ansi, terminal_width) -> str

Color scheme (see spec §视觉约定):
  thinking block : bright blue "[think #N]" label + --- fenced blue body
  text block     : bright white "[text #N]" label + --- fenced default body
  heartbeat      : bold red "♥ ..."
  round switch   : bold yellow "─── round X → Y ───"
  tsv            : cyan "[tsv]"
  wait-train     : magenta "[wait-train]"
  task lifecycle : magenta "[task]"
  tool call      : green "[tool #N]" label + green "→ Tool: args"
  tool result ok : green "[tool #N] ← ✓ ok (N lines, X KB)"
  tool result err: red "[tool #N] ← ✗ ERR:" + --- fenced body

Inline counters (#N) let the observer track session progress at a glance —
how many turns the agent has used, how many tool calls, how many errors.
tool_use and its matching tool_result share the same #N so call/result pairs
are visually linked.

Visual hierarchy: label = bright (catches the eye), body = normal color
(v2.8.4: 去 dim——原 "34;2"/"2"/"32;2"/"31;2" 在多数终端浅背景或 dim 渲染
太暗, 几乎看不清; 改正常色保可读). think block uses blue tones end-to-end
so reasoning stands out as a distinct visual unit.

All output is left-aligned (no leading indent); multi-block events use a blank line
as separator (think ↔ text transitions). think/text bodies use --- fences (no ┃).

Length limits (CLI / claude-stream summarize):
  max_text    : default 2400 chars (think/text；原 800 的 3×)
  max_result  : default 6 (tool ERR 预览行数 = max(5, max_result*2+3) → 默认 15 行)
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from typing import Optional

from nn_stream_watch.state import WatchState

DEFAULT_MAX_TEXT = 2400
DEFAULT_MAX_RESULT = 6


# --- ANSI helpers ---

def ansi_enabled(force_off: bool = False) -> bool:
    """Whether ANSI escapes should be emitted (TTY + no override)."""
    if force_off:
        return False
    return sys.stdout.isatty()


def _c(code: Optional[str], text: str, enabled: bool) -> str:
    """Wrap text in ANSI code if enabled. None / empty code = no wrapping."""
    if not enabled or not code:
        return text
    return f"\033[{code}m{text}\033[0m"


_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def is_fenced_stream_block(block: str) -> bool:
    """True for [think|text] or tool ERR blocks using --- fences (summarize: no indent)."""
    lines = block.split("\n")
    if len(lines) < 3:
        return False
    plain = [_strip_ansi(ln).strip() for ln in lines]
    if plain[1] != "---" or plain[-1] != "---":
        return False
    head = plain[0]
    return (
        head.startswith("[think")
        or head.startswith("[text")
        or "← ✗ ERR:" in head
    )


def is_fenced_assistant_block(block: str) -> bool:
    """Alias for think/text fenced blocks (backwards compat)."""
    return is_fenced_stream_block(block)


# --- Text truncation ---

def truncate_text(text: str, max_chars: int = DEFAULT_MAX_TEXT) -> tuple[str, bool]:
    """Truncate text to max_chars. Returns (text, was_truncated).

    When truncated, the returned text includes a "[+ N chars]" marker
    that counts toward max_chars.
    """
    if len(text) <= max_chars:
        return text, False
    remaining = len(text) - max_chars
    marker = f"[+ {remaining} chars]"
    head_budget = max_chars - len(marker)
    if head_budget < 0:
        head_budget = 0
    return text[:head_budget] + marker, True


# --- Text extraction ---

def _extract_text(event: dict) -> str:
    """Extract the text payload from an assistant event (text or thinking block)."""
    msg = event.get("message") or {}
    for block in (msg.get("content") or []):
        btype = block.get("type")
        if btype == "text":
            return block.get("text") or ""
        if btype == "thinking":
            return block.get("thinking") or ""
    return ""


# --- Text / thinking block rendering ---

def _render_text_block(text: str, block_type: str, ansi: bool, max_chars: int = DEFAULT_MAX_TEXT,
                       counter: Optional[int] = None) -> str:
    """Render a think/text block: label line + --- fenced body.

    block_type: "think" or "text" — labels the block so the reader can tell
    reasoning from answer at a glance.

    Visual hierarchy: label uses bright color, body uses dim version of the
    same color inside --- fences (no ┃ continuation prefix).
    """
    truncated_text, _ = truncate_text(text, max_chars=max_chars)
    lines = truncated_text.splitlines() or [""]
    # v2.8.4: body 去 dim(2) — 原 "34;2"/"2" 在多数终端(浅背景/dim 渲染暗)太浅看不清;
    # label 保留亮色抓眼, body 用正常色(可读)。think=蓝调区分 reasoning, text=默认色。
    if block_type == "think":
        label_code, body_code = "94", "34"   # label 亮蓝, body 正常蓝(去 dim)
    else:
        label_code, body_code = "97", None    # label 亮白, body 默认色(最可读)
    label_text = f"[{block_type} #{counter}]" if counter is not None else f"[{block_type}]"
    label = _c(label_code, label_text, ansi)
    fence = _c(body_code, "---", ansi)
    body_lines = [_c(body_code, ln, ansi) for ln in lines]
    return "\n".join([label, fence, *body_lines, fence])


# --- Status panel ---

def render_status_panel(state: WatchState, ansi: bool, terminal_width: int = 80) -> str:
    """Render the 4-line status panel (header / round / totals / TSV / footer)."""
    # field 1: round / heartbeat / tsv count
    round_str = f"round {state.round}" if state.round is not None else "round ?"
    hb_str = "♥ ?s ago"
    if state.last_hb_at is not None:
        age = state.heartbeat_age_seconds(datetime.now())
        if age is not None:
            hb_str = f"♥ {age}s ago"
    tsv_str = f"tsv: {state.ticks} ticks" if state.ticks else "tsv: -"

    # field 2: counters (always render — at zero it's still informative)
    err_str = f" (err {state.n_tool_err})" if state.n_tool_err else ""
    line2 = f"txt {state.n_text}  think {state.n_think}  tool {state.n_tool_call}{err_str}"

    line1 = f"{round_str}  {hb_str}  {tsv_str}"
    line3 = f"latest TSV: {state.latest_tsv or '(none)'}"

    bar = "═" * max(8, min(terminal_width - 20, 40))
    header = f"{bar} status {bar}"
    footer = bar

    if ansi:
        dim = "2"
        return (f"\033[{dim}m{header}\033[0m\n"
                f"{line1}\n"
                f"{line2}\n"
                f"{line3}\n"
                f"\033[{dim}m{footer}\033[0m")
    return f"{header}\n{line1}\n{line2}\n{line3}\n{footer}"


# --- Main render (text/thinking only at this stage) ---

def render_event(
    event: dict,
    state: Optional[WatchState],
    ansi: bool,
    max_text: int = DEFAULT_MAX_TEXT,
    max_result: int = DEFAULT_MAX_RESULT,
) -> str:
    """Render a single NDJSON event as a formatted string (no trailing newline).

    Handles text / thinking blocks + tool_use + tool_result.
    Status panel is rendered separately by the main loop.

    If state is provided, counters are bumped before render so labels carry
    inline "#N" sequence numbers. tool_use and its matching tool_result share
    the same number (tool_use bumps, tool_result reads n_tool_call).
    """
    msg = event.get("message") or {}
    blocks = msg.get("content") or []
    if not blocks:
        return ""
    block_type = blocks[0].get("type")

    if block_type in ("text", "thinking"):
        # Render all text/thinking blocks in this event (concat with blank line).
        parts: list[str] = []
        for blk in blocks:
            if blk.get("type") == "text":
                t = blk.get("text") or ""
                if t:
                    n = state.bump_text() if state is not None else None
                    parts.append(_render_text_block(t, "text", ansi=ansi, max_chars=max_text, counter=n))
            elif blk.get("type") == "thinking":
                t = blk.get("thinking") or ""
                if t:
                    n = state.bump_think() if state is not None else None
                    parts.append(_render_text_block(t, "think", ansi=ansi, max_chars=max_text, counter=n))
        return "\n\n".join(parts) if parts else ""

    if block_type == "tool_use":
        n = state.bump_tool_call() if state is not None else None
        return _render_tool_call(event, ansi=ansi, counter=n)

    if block_type == "tool_result":
        # tool_result does NOT bump n_tool_call — it uses the same #N as the
        # preceding tool_use so call/result pairs are visually linked.
        n = state.n_tool_call if state is not None else None
        is_err = False
        for blk in blocks:
            if blk.get("type") == "tool_result" and blk.get("is_error"):
                is_err = True
                break
        if is_err and state is not None:
            state.bump_tool_err()
        return _render_tool_result(event, ansi=ansi, max_result=max_result, counter=n)

    return ""


# --- Tool rendering helpers ---

def _summarize_args(name: str, inp: dict, terminal_width: int = 100) -> str:
    """Produce a one-line key-args summary for a tool_use call."""
    if name == "Bash":
        cmd = inp.get("command", "")
        # Strip leading whitespace from each line so multi-line commands stay left-aligned
        # in the formatter output (no inherited indent from the source command).
        cmd = "\n".join(ln.lstrip() for ln in cmd.splitlines())
        if len(cmd) > terminal_width - 20:
            return cmd[:terminal_width - 23] + "..."
        return cmd
    if name == "Read":
        return inp.get("file_path", "")
    if name == "Edit":
        return f"{inp.get('file_path', '')}"
    if name == "Write":
        return f"{inp.get('file_path', '')}"
    if name == "TaskUpdate":
        return f"{inp.get('taskId', '?')} → {inp.get('status', '?')}"
    if name == "TaskCreate":
        return inp.get("subject", "")
    # Generic fallback: comma-separated key=value
    parts = [f"{k}={v}" for k, v in inp.items() if isinstance(v, (str, int, float))]
    return ", ".join(parts)[:terminal_width]


def _render_tool_call(event: dict, ansi: bool, counter: Optional[int] = None) -> str:
    """Render a tool_use event as '→ Tool: args' (single line).

    Label '[tool #N]' is bright green; arrow + args are dim green so the
    tag catches the eye and the command stays scannable. The #N matches
    the tool_result that follows so call/result pairs are visually linked.
    """
    msg = event.get("message") or {}
    for block in (msg.get("content") or []):
        if block.get("type") != "tool_use":
            continue
        name = block.get("name", "?")
        inp = block.get("input") or {}
        args = _summarize_args(name, inp)
        label_text = f"[tool #{counter}]" if counter is not None else "[tool]"
        label = _c("32", label_text, ansi)
        body = _c("32", f" → {name}: {args}", ansi)
        return f"{label}{body}"
    return ""


def _render_tool_result(event: dict, ansi: bool, max_result: int = DEFAULT_MAX_RESULT,
                        counter: Optional[int] = None) -> str:
    """Render a tool_result event as '← ✓ ok / ✗ ERR: ...' (ERR 预览行数随 max_result).

    Status icon (✓/✗) sits right after the arrow so success vs failure is
    the first thing the eye lands on — critical for long stream sessions
    where errors must pop without scanning text. Shares counter with the
    preceding tool_use so [tool #12] on both call and result match.
    """
    msg = event.get("message") or {}
    label_prefix = f"[tool #{counter}]" if counter is not None else "[tool]"
    for block in (msg.get("content") or []):
        if block.get("type") != "tool_result":
            continue
        content = block.get("content") or ""
        if not isinstance(content, str):
            content = str(content)
        is_error = bool(block.get("is_error"))

        if is_error:
            header = _c("31", f"{label_prefix} ← ✗ ERR:", ansi)
            lines = content.splitlines()
            n_show = max(5, max_result * 2 + 3)
            preview = lines[:n_show]
            fence = _c("31", "---", ansi)
            body_lines = [_c("31", ln, ansi) for ln in preview]
            parts = [header, fence, *body_lines]
            if len(lines) > n_show:
                parts.append(_c("31", f"... ({len(lines) - n_show} more lines)", ansi))
            parts.append(fence)
            return "\n".join(parts)

        # ok case: count lines + bytes. Header is dim green ✓; result stats
        # stay in the same dim-green tone (no body to render).
        lines = content.splitlines()
        n_lines = len(lines)
        kb = len(content.encode("utf-8")) / 1024
        size_str = f"{kb:.1f} KB" if kb >= 1 else f"{len(content)} B"
        return _c("32", f"{label_prefix} ← ✓ ok ({n_lines} lines, {size_str})", ansi)
    return ""


# --- Key event rendering ---


def render_key_event(
    kind: str,
    ts: datetime,
    detail: str,
    ansi: bool,
) -> str:
    """Render a key event line (heartbeat / round / tsv / wait / task).

    `kind` is the key event type from detectors.classify.
    `ts` is the event timestamp (for [HH:MM:SS] prefix).
    `detail` is the kind-specific body text.
    """
    ts_prefix = f"[{ts.strftime('%H:%M:%S')}]"

    if kind == "heartbeat":
        # bold red, dedicated line, no truncation
        body = f"♥ heartbeat  {detail}"
        return _c("1;31", f"{ts_prefix} {body}", ansi)

    if kind == "round_switch":
        body = f"─── round {detail} ───"
        return _c("1;33", f"{ts_prefix} {body}", ansi)  # bold yellow

    if kind == "tsv_write":
        body = f"[tsv] {detail}"
        return _c("36", f"{ts_prefix} {body}", ansi)  # cyan

    if kind == "wait_train":
        body = f"[wait-train] {detail}"
        return _c("35", f"{ts_prefix} {body}", ansi)  # magenta

    if kind == "task_lifecycle":
        body = f"[task] {detail}"
        return _c("35", f"{ts_prefix} {body}", ansi)  # magenta

    # Fallback
    body = f"[{kind}] {detail}"
    return f"{ts_prefix} {body}"
