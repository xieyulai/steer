"""Agent CLI 路径解析（auto-nn-run.sh 与 reflect.py 共用）。"""
from __future__ import annotations

import os
import shutil
from pathlib import Path


def resolve_claude_executable() -> str | None:
    """NN_CLAUDE_BIN > PATH which('claude')。"""
    override = os.environ.get("NN_CLAUDE_BIN", "").strip()
    if override and Path(override).is_file():
        return override
    return shutil.which("claude")


def claude_invoke_argv(*extra: str) -> list[str]:
    exe = resolve_claude_executable()
    if not exe:
        raise FileNotFoundError("claude CLI not found (set NN_CLAUDE_BIN or PATH)")
    return [exe, "-p", "--dangerously-skip-permissions", *extra]
