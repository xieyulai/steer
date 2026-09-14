"""WatchState: in-memory state for the watcher.

Holds current round, last heartbeat timestamp, latest TSV summary line.
Single source of truth mutated by detectors and read by formatter.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class WatchState:
    round: Optional[int] = None
    last_hb_at: Optional[datetime] = None
    latest_tsv: Optional[str] = None
    ticks: int = 0
    # Counters — bumped by render_event as it iterates blocks. Counters help
    # the observer see at a glance how many turns the agent has used.
    n_text: int = 0       # assistant text blocks (visible answers)
    n_think: int = 0      # assistant thinking blocks (internal reasoning)
    n_tool_call: int = 0  # tool_use blocks (incremented before n_tool_result is read)
    n_tool_err: int = 0   # tool_result blocks with is_error=True

    def update_round(self, new_round: int) -> None:
        """Switch to a new round number (heartbeat detector / Bash arg parser)."""
        self.round = new_round

    def update_heartbeat(self, ts: datetime) -> None:
        """Record a detected heartbeat at timestamp ts."""
        self.last_hb_at = ts
        self.ticks += 1

    def update_tsv(self, summary: str) -> None:
        """Record the latest TSV line summary (one-liner)."""
        self.latest_tsv = summary
        self.ticks += 1

    def bump_text(self) -> int:
        """Increment text-block counter; returns the new value (1-based)."""
        self.n_text += 1
        return self.n_text

    def bump_think(self) -> int:
        """Increment thinking-block counter; returns the new value (1-based)."""
        self.n_think += 1
        return self.n_think

    def bump_tool_call(self) -> int:
        """Increment tool_use counter; returns the new value (1-based).
        The matching tool_result event will use this same number so call/result
        pairs are visually linked (e.g. "[tool #12]" on both).
        """
        self.n_tool_call += 1
        return self.n_tool_call

    def bump_tool_err(self) -> None:
        """Increment tool-error counter (called when is_error=True)."""
        self.n_tool_err += 1

    def heartbeat_age_seconds(self, now: datetime) -> Optional[int]:
        """Seconds since last heartbeat; None if no heartbeat seen yet."""
        if self.last_hb_at is None:
            return None
        return int((now - self.last_hb_at).total_seconds())
