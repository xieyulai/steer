"""Heuristic key event detection from claude-stream NDJSON events.

Given an event (and optionally the prior tool_result), returns:
  - "heartbeat"        : Bash invoked python train.py AND result has step=\\d+/
  - "round_switch"     : tool_use command arg contains --round N
  - "tsv_write"        : tool_use writes results.tsv
  - "wait_train"       : tool_use invokes wait-train or tail train.log
  - "task_lifecycle"   : tool_use TaskUpdate changes status
  - None               : not a key event

Detection is heuristic — false positives acceptable (extra line), false
negatives tunable via the regex set below.
"""
from __future__ import annotations

import re
from typing import Any, Optional


def _tool_input(event: dict) -> Optional[dict]:
    """Extract tool_use input dict from an event, or None."""
    msg = event.get("message") or {}
    for block in (msg.get("content") or []):
        if block.get("type") == "tool_use":
            return block.get("input") or {}
    return None


def _tool_name(event: dict) -> Optional[str]:
    msg = event.get("message") or {}
    for block in (msg.get("content") or []):
        if block.get("type") == "tool_use":
            return block.get("name")
    return None


def _tool_result_content(result_event: dict) -> str:
    """Extract stdout content string from a tool_result event."""
    msg = result_event.get("message") or {}
    for block in (msg.get("content") or []):
        if block.get("type") == "tool_result":
            content = block.get("content") or ""
            return content if isinstance(content, str) else str(content)
    return ""


# Regex sets (tunable in one place)
_RE_TRAIN_PY = re.compile(r"\bpython\s+\S*train\.py\b")
_RE_STEP = re.compile(r"step=\d+/\d+")
_RE_ROUND_ARG = re.compile(r"--round\s+(\d+)")
_RE_TSV_PATH = re.compile(r"results\.tsv\b")
_RE_WAIT_TRAIN = re.compile(r"(wait-train|tail\s+-f\s+train\.log)")


def classify(event: dict, prior_result: Optional[dict] = None) -> Optional[str]:
    """Return key event type for `event`, or None.

    `prior_result` should be the immediately preceding tool_result event
    (when classifying a tool_use event that has one).
    """
    name = _tool_name(event)
    if name is None:
        return None

    inp = _tool_input(event) or {}
    command = inp.get("command", "")
    file_path = inp.get("file_path", "")
    status = inp.get("status", "")

    # heartbeat: Bash + train.py + result has step=
    if name == "Bash" and _RE_TRAIN_PY.search(command):
        if prior_result is not None and _RE_STEP.search(_tool_result_content(prior_result)):
            return "heartbeat"

    # round_switch: --round N in Bash command
    if name == "Bash" and _RE_ROUND_ARG.search(command):
        return "round_switch"

    # tsv_write: Edit/Write/Bash on results.tsv
    if _RE_TSV_PATH.search(command) or _RE_TSV_PATH.search(file_path):
        return "tsv_write"

    # wait_train: wait-train or tail train.log
    if name == "Bash" and _RE_WAIT_TRAIN.search(command):
        return "wait_train"

    # task_lifecycle: TaskUpdate with status change
    if name == "TaskUpdate" and status in ("in_progress", "completed"):
        return "task_lifecycle"

    return None


def extract_round(command: str) -> Optional[int]:
    """Parse --round N from a Bash command string."""
    m = _RE_ROUND_ARG.search(command)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None
