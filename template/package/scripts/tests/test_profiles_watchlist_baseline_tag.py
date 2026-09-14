"""T-A: profiles.yaml 三个 profile 的 default_watchlist 各加 baseline_tag，且仍 ≤10 项。

baseline_tag 经 default_watchlist → init_watchlist → nn-config ledger.watchlist
→ experiment.ledger_context_keys → _default_tsv_columns 传播为 results.tsv 列。
门禁 check_ledger_watchlist 要求 ≤10 项，加前 5/4/3 项 → 加后 6/5/4 仍安全。
"""

from __future__ import annotations

from pathlib import Path

import yaml

_PROFILES = Path(__file__).resolve().parent.parent.parent / "profiles.yaml"


def _watchlists() -> dict[str, list[str]]:
    data = yaml.safe_load(_PROFILES.read_text(encoding="utf-8"))
    return {
        name: list((p.get("default_watchlist") or []))
        for name, p in (data.get("profiles") or {}).items()
    }


def test_each_profile_has_baseline_tag():
    for name, wl in _watchlists().items():
        assert "baseline_tag" in wl, f"{name} default_watchlist 缺 baseline_tag: {wl}"


def test_each_profile_watchlist_under_limit():
    for name, wl in _watchlists().items():
        assert len(wl) <= 10, f"{name} watchlist 超 10 项门禁: {wl}"
