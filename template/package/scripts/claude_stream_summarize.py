#!/usr/bin/env python3
"""将 Claude Code stream-json 的 NDJSON 行转为 stderr 结构化摘要（stdin → stderr）。

调用方：auto-nn-run.sh:1070
    ... | python3 -u scripts/claude_stream_summarize.py

输出格式（与 nn_stream_watch 对齐；色板见 formatter 顶部 docstring）：
  [think #N]                                                        ← 蓝标签
  ---                                                               ← 围栏 + 体色
  <thinking 内容，默认 2400 字截断 + [+ N chars] 标记>
  ---
  [text #N] / 同上围栏格式
  → <Tool>: <key args>                                              ← 绿
  ← ok (N lines, X KB)                                              ← 暗绿
  ← ERR: + --- fenced body                                           ← 红
  [HH:MM:SS] ♥ heartbeat …                                          ← 粗红
  <stamp> [claude-stream] system/<sub> | <hook>                     ← stamp 亮蓝 / 体暗灰
  （不打印 result/success 等终态行 — Agent 轮次结束由 auto-nn-run 批次日志体现）

去重：连续相同 summary 不重复打印（state 变化后恢复打印）。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# --- 加载同目录 nn_stream_watch 包（不依赖 governance-sync 顺序） ---
_SELF_DIR = Path(__file__).resolve().parent
if str(_SELF_DIR) not in sys.path:
    sys.path.insert(0, str(_SELF_DIR))

try:
    from nn_stream_watch import detectors, formatter, state  # type: ignore
    from nn_stream_watch.formatter import (  # type: ignore
        DEFAULT_MAX_RESULT as _FMT_MAX_RESULT,
        DEFAULT_MAX_TEXT as _FMT_MAX_TEXT,
    )
except Exception as _e:  # pragma: no cover
    sys.stderr.write(
        f"[claude-stream-summarize] FAIL: cannot import nn_stream_watch: {_e}\n"
    )
    raise

# --- 颜色 / 截断默认值（环境变量可覆盖；默认 = formatter 常量的 3× 基线） ---
DEFAULT_MAX_TEXT = int(os.environ.get("NN_AGENT_CLAUDE_STREAM_MAX_TEXT", str(_FMT_MAX_TEXT)))
DEFAULT_MAX_RESULT = int(os.environ.get("NN_AGENT_CLAUDE_STREAM_MAX_RESULT", str(_FMT_MAX_RESULT)))

# --- summarize 层独有色（formatter 之外；保持冷静蓝绿主调一致） ---
# stamp 频道标识: 亮蓝(94)
# system 体: 暗灰(90)        ← 元事件,降噪
ANSI_STAMP    = "94"
ANSI_BODY_SYS = "90"


def _stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _emit(block: str, last_block: str | None, *, body_code: str | None = None) -> str | None:
    """Write a (possibly multi-line) block to stderr; dedupe identical blocks.

    body_code: 若给 ANSI code,体每行用此色包裹(用于 system/result 整块降噪);
              None 时不重新套色(默认 — 体已由 formatter 上色)。
    Stamp [claude-stream] 始终套亮蓝 ANSI_STAMP,便于在终端扫到这一类事件。
    """
    if not block:
        return last_block
    if block == last_block:
        return last_block
    ansi = _is_ansi()
    head_plain = f"{_stamp()} [claude-stream] "
    head = formatter._c(ANSI_STAMP, head_plain, ansi) if ansi else head_plain
    indent = " " * len(head_plain)
    lines = block.split("\n")
    fenced = formatter.is_fenced_stream_block(block)

    rendered: list[str] = []
    for i, ln in enumerate(lines):
        if i == 0:
            prefix = head
        elif fenced:
            prefix = ""
        else:
            prefix = indent if not ansi else formatter._c(ANSI_STAMP, indent, ansi)
        body = formatter._c(body_code, ln, ansi) if (ansi and body_code) else ln
        rendered.append(prefix + body)
    out = "\n".join(rendered)
    print(out, file=sys.stderr, flush=True)
    return block


def _is_ansi() -> bool:
    # 走 stderr（这是 claude_stream_summarize 的标准目标），NN 强制开色便于阅读；
    # 关色可用 NN_AGENT_CLAUDE_STREAM_NO_COLOR=1
    if os.environ.get("NN_AGENT_CLAUDE_STREAM_NO_COLOR", "0") in ("1", "true", "yes", "on"):
        return False
    return True


def _system_summary(o: dict) -> str:
    sub = o.get("subtype") or "?"
    hn = o.get("hook_name") or ""
    big = 0
    for k in ("output", "stdout", "stderr"):
        v = o.get(k)
        if isinstance(v, str) and len(v) > 400:
            big += len(v)
    hn_s = str(hn)
    if len(hn_s) > 120:
        hn_s = hn_s[:119] + "…"
    if big:
        return f"system/{sub} | {hn_s} | long_fields≈{big}chars_omit"
    return f"system/{sub} | {hn_s}"


def _user_summary(o: dict) -> str:
    """渲染 user 事件（tool_result）为 ← ok / ← ERR 块。"""
    # claude_stream_summarize 走 formatter 的工具，ans 标记强制开启（看 stderr）
    return formatter.render_event(
        o, state=None, ansi=_is_ansi(),
        max_text=DEFAULT_MAX_TEXT, max_result=DEFAULT_MAX_RESULT,
    )


def _assistant_rendered(o: dict) -> tuple[str, str | None]:
    """返回 (rendered_text_block, key_event_kind)。

    key_event_kind 是 detectors.classify 命中的类型，用于让 main 决定
    是否额外发一行高亮 heartbeat/round/tsv/...。
    """
    rendered = formatter.render_event(
        o, state=None, ansi=_is_ansi(),
        max_text=DEFAULT_MAX_TEXT, max_result=DEFAULT_MAX_RESULT,
    )
    kind = detectors.classify(o, prior_result=None)
    return rendered, kind


def _key_event_block(o: dict, kind: str, prior_result) -> str:
    """构造 key event 的高亮行（与 watch 同样的 [HH:MM:SS] + 着色）。"""
    ts = datetime.now()
    ansi = _is_ansi()
    if kind == "heartbeat":
        # pull step line from prior_result content
        detail = ""
        if prior_result is not None:
            msg = prior_result.get("message") or {}
            for blk in (msg.get("content") or []):
                if blk.get("type") == "tool_result":
                    content = blk.get("content") or ""
                    if not isinstance(content, str):
                        content = str(content)
                    for line in content.splitlines():
                        if "step=" in line:
                            detail = line.strip()[:120]
                            break
                    if not detail and content.splitlines():
                        detail = content.splitlines()[0][:120]
                    break
        return formatter.render_key_event("heartbeat", ts=ts, detail=detail, ansi=ansi)

    if kind == "round_switch":
        msg = o.get("message") or {}
        command = ""
        for blk in (msg.get("content") or []):
            if blk.get("type") == "tool_use" and blk.get("name") == "Bash":
                command = (blk.get("input") or {}).get("command", "")
                break
        new_round = detectors.extract_round(command)
        if new_round is None:
            return ""
        # summarize 不维护 state，detail 显示目标 round；用 "→ new_round" 表达切换
        return formatter.render_key_event(
            "round_switch", ts=ts, detail=f"→ {new_round}", ansi=ansi,
        )

    if kind == "tsv_write":
        msg = o.get("message") or {}
        for blk in (msg.get("content") or []):
            if blk.get("type") == "tool_use":
                name = blk.get("name", "?")
                inp = blk.get("input") or {}
                path = inp.get("file_path") or inp.get("command", "")
                # basename only
                tail = path.rsplit("/", 1)[-1] if isinstance(path, str) else "?"
                return formatter.render_key_event(
                    "tsv_write", ts=ts, detail=f"{name} → {tail}", ansi=ansi,
                )
        return formatter.render_key_event("tsv_write", ts=ts, detail="tsv", ansi=ansi)

    if kind == "wait_train":
        msg = o.get("message") or {}
        for blk in (msg.get("content") or []):
            if blk.get("type") == "tool_use" and blk.get("name") == "Bash":
                command = (blk.get("input") or {}).get("command", "")
                return formatter.render_key_event(
                    "wait_train", ts=ts, detail=command, ansi=ansi,
                )
        return formatter.render_key_event("wait_train", ts=ts, detail="", ansi=ansi)

    if kind == "task_lifecycle":
        msg = o.get("message") or {}
        for blk in (msg.get("content") or []):
            if blk.get("type") == "tool_use" and blk.get("name") == "TaskUpdate":
                inp = blk.get("input") or {}
                detail = f"{inp.get('taskId', '?')} → {inp.get('status', '?')}"
                return formatter.render_key_event(
                    "task_lifecycle", ts=ts, detail=detail, ansi=ansi,
                )
        return formatter.render_key_event("task_lifecycle", ts=ts, detail="", ansi=ansi)

    return ""


def main() -> None:
    last_block: str | None = None
    prior_result = None  # for heartbeat detection (no state persisted)
    for raw in sys.stdin:
        line = raw.rstrip("\n\r")
        if not line.strip():
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            last_block = _emit("<JSON 解析失败>", last_block)
            continue

        t = o.get("type")
        body_code: str | None = None
        if t == "result":
            # 终态（turns/cost/stop）不刷屏；批次 SUCCESS 见 auto-nn-run 主日志
            continue
        elif t == "system":
            block = _system_summary(o)
            body_code = ANSI_BODY_SYS
        elif t == "assistant":
            rendered, kind = _assistant_rendered(o)
            if rendered:
                last_block = _emit(rendered, last_block)
            if kind is not None:
                key_block = _key_event_block(o, kind, prior_result)
                if key_block:
                    last_block = _emit(key_block, last_block)
            block = ""  # already emitted
        elif t == "user":
            block = _user_summary(o)
            # Track for next heartbeat classification
            msg = o.get("message") or {}
            for blk in (msg.get("content") or []):
                if blk.get("type") == "tool_result":
                    prior_result = o
                    break
        else:
            # unknown type — best-effort one-liner
            short = line if len(line) <= 120 else line[:119] + "…"
            block = f"{t} | {short}"
            body_code = ANSI_BODY_SYS  # unknown 也降噪

        if t != "assistant":
            last_block = _emit(block, last_block, body_code=body_code)


if __name__ == "__main__":
    main()
