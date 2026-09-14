"""D1: external_evidence_health — 每轮外部证据健康度落盘。

summarize_evidence_health(bundle, round) → 状态报告:
- providers 段: 各 provider 的 ok/hits/http_calls
- skipped 段: 跳过原因列表
- totals 段: 命中数 / HTTP 调用数
- health 段: 'green' / 'yellow' / 'red' 三档判定

write_evidence_health(bundle, round, saved_dir) → 落盘 saved/external_evidence_health.json

纯函数(无 IO 副作用); 调用方传 saved_dir 决定落盘位置。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_HEALTH_FILENAME = "external_evidence_health.json"

_PROVIDER_KEYS = ("paper", "code", "docs")


def _provider_stats(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for key in _PROVIDER_KEYS:
        section = bundle.get(key) or {}
        if not isinstance(section, dict):
            section = {}
        hits = section.get("hits") or []
        stats[key] = {
            "ok": len(hits) > 0,
            "hits": len(hits),
            "http_calls": int(bundle.get(f"{key}_http_calls", 0) or 0),
        }
    return stats


def _classify_health(providers: dict[str, dict[str, Any]], skipped: list[dict[str, str]], totals_hits: int) -> str:
    skipped_providers = {s.get("provider", "") for s in skipped}
    provider_names = set(providers.keys())
    all_skipped = provider_names and provider_names.issubset(
        {p for p in skipped_providers if p}
    )
    if totals_hits == 0 and all_skipped:
        return "red"
    if totals_hits == 0:
        return "red"
    if skipped:
        return "yellow"
    return "green"


def summarize_evidence_health(bundle: dict[str, Any], round_no: int) -> dict[str, Any]:
    """bundle → 健康度报告 dict。

    Args:
        bundle: executor 输出的外部证据包 (含 paper/code/docs/skipped/http_used 段)
        round_no: 当前轮号

    Returns:
        {
            "round": int,
            "providers": {paper/code/docs 各自的 {ok, hits, http_calls}},
            "skipped": [{provider, reason}, ...],
            "totals": {hits, http_calls},
            "health": "green" | "yellow" | "red",
        }
    """
    providers = _provider_stats(bundle)
    skipped = list(bundle.get("skipped") or [])
    totals_hits = sum(p["hits"] for p in providers.values())
    totals_http = int(bundle.get("http_used") or 0)
    health = _classify_health(providers, skipped, totals_hits)
    return {
        "round": int(round_no),
        "providers": providers,
        "skipped": skipped,
        "totals": {"hits": totals_hits, "http_calls": totals_http},
        "health": health,
    }


def write_evidence_health(
    bundle: dict[str, Any],
    round_no: int,
    saved_dir: Path | str,
) -> Path:
    """summarize_evidence_health + 落盘 saved_dir/external_evidence_health.json。

    Returns:
        落盘文件路径
    """
    saved = Path(saved_dir)
    saved.mkdir(parents=True, exist_ok=True)
    out = saved / _HEALTH_FILENAME
    health = summarize_evidence_health(bundle, round_no)
    out.write_text(json.dumps(health, indent=2, ensure_ascii=False))
    return out
