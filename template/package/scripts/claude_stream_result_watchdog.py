#!/usr/bin/env python3
"""Kill Claude CLI when stream-json emits type=result but the process hangs."""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def kill_pid(pid: int) -> None:
    if not pid_alive(pid):
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return
    for _ in range(10):
        if not pid_alive(pid):
            return
        time.sleep(0.5)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass


def line_is_result(line: str) -> bool:
    line = line.strip()
    if not line:
        return False
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return False
    return obj.get("type") == "result"


def watch_stream_for_result(stream: Path, offset: int) -> tuple[bool, int]:
    if not stream.is_file():
        return False, offset
    try:
        with stream.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(offset)
            while True:
                line = handle.readline()
                if not line:
                    break
                offset = handle.tell()
                if line_is_result(line):
                    return True, offset
    except OSError:
        return False, offset
    return False, offset


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stream", required=True, help="Path to *_stream.jsonl")
    parser.add_argument("--pid", type=int, required=True, help="Claude CLI pid")
    parser.add_argument(
        "--grace-sec",
        type=int,
        default=60,
        help="Seconds to wait after result before SIGTERM (default 60)",
    )
    parser.add_argument(
        "--poll-sec",
        type=float,
        default=5.0,
        help="Poll interval while waiting for result line",
    )
    parser.add_argument("--round", default="?", help="Run index for log messages")
    args = parser.parse_args()

    stream = Path(args.stream)
    offset = 0
    result_seen = False

    while pid_alive(args.pid):
        found, offset = watch_stream_for_result(stream, offset)
        if found:
            result_seen = True
            print(
                f"[claude-watchdog {time.strftime('%Y-%m-%d %H:%M:%S')}] "
                f"Run {args.round}: stream result seen; "
                f"grace {args.grace_sec}s then SIGTERM pid={args.pid}",
                file=sys.stderr,
                flush=True,
            )
            break
        time.sleep(max(0.1, args.poll_sec))

    if not result_seen:
        return 0

    time.sleep(max(0, args.grace_sec))
    if pid_alive(args.pid):
        print(
            f"[claude-watchdog {time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"Run {args.round}: pid {args.pid} still alive after grace; killing",
            file=sys.stderr,
            flush=True,
        )
        kill_pid(args.pid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
