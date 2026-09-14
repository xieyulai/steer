"""Resolve framework doc URLs from framework_docs_registry.yaml (link_only, no HTTP)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml  # type: ignore

_REGISTRY_PATH = Path(__file__).with_name("framework_docs_registry.yaml")


@lru_cache(maxsize=1)
def _load_registry() -> dict[str, dict[str, str]]:
    raw = yaml.safe_load(_REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    symbols = raw.get("symbols") or {}
    out: dict[str, dict[str, str]] = {}
    for key, entry in symbols.items():
        if not isinstance(entry, dict):
            continue
        out[str(key)] = {
            "framework": str(entry.get("framework") or ""),
            "url_template": str(entry.get("url_template") or ""),
        }
    return out


def _registry_hit(symbol_key: str, entry: dict[str, str]) -> dict[str, str]:
    return {
        "symbol": symbol_key,
        "url": entry["url_template"],
        "framework": entry["framework"],
        "source": "registry",
    }


def _match_keys(symbol: str, registry: dict[str, dict[str, str]]) -> list[str]:
    sym = symbol.strip()
    if not sym:
        return []

    if sym in registry:
        return [sym]

    base = sym.rsplit(".", 1)[-1]
    if base in registry:
        return [base]

    if sym in ("torch.nn", "nn"):
        return [
            key
            for key, entry in registry.items()
            if entry.get("framework") == "pytorch"
        ]

    return []


def resolve_docs(symbols: list[str]) -> list[dict[str, str]]:
    registry = _load_registry()
    hits: list[dict[str, str]] = []
    seen: set[str] = set()

    for symbol in symbols:
        for key in _match_keys(symbol, registry):
            if key in seen:
                continue
            entry = registry.get(key)
            if not entry or not entry.get("url_template"):
                continue
            seen.add(key)
            hits.append(_registry_hit(key, entry))

    return hits
