"""v1.24.0 — 跨单位 metric 归一 + None-safe 取值 helper。

设计原则 (三层 + 三不变量):
- 零模板依赖 (只 stdlib + typing),三件套共用
- helper 默认无副作用:missing → ratio fallback,None → default 兜底,不抛
- ADAPTER 必须显式 opt-in,本文件不感知 contract 子模块
"""
from __future__ import annotations

import logging
from typing import Literal

# ── 公开类型 ───────────────────────────────────────────────────────
UnitKind = Literal["ratio", "percent"]


# ── 静态查表 ───────────────────────────────────────────────────────
# 收敛业务仓最常见的 7 个 metric。未知 metric → ratio fallback + warning。
METRIC_UNITS: dict[str, UnitKind] = {
    "val_accuracy": "percent",
    "accuracy": "percent",
    "f1": "percent",
    "top1": "percent",
    "loss": "ratio",
    "perplexity": "ratio",
    "forgetting": "ratio",
}


# ── helpers ────────────────────────────────────────────────────────
# 同 metric 重复警告的全局去重集合(production 调用方一行一行 metric_unit,避免日志洪水)
_warned_metrics: set[str] = set()


def metric_unit(name: str | None) -> UnitKind:
    """查表 → 缺则 fallback 'ratio' + 每个未知 metric 仅 warning 一次。

    不抛业务仓错:任何「未知 metric」场景都安全回落 ratio。
    """
    if not name:
        return "ratio"
    if name in METRIC_UNITS:
        return METRIC_UNITS[name]
    if name not in _warned_metrics:
        _warned_metrics.add(name)
        logging.getLogger(__name__).warning(
            "metric_unit: 未知 metric=%r,fallback 'ratio'(可在 METRIC_UNITS 加登记)", name
        )
    return "ratio"


def normalize_to(value: float | None, unit: UnitKind, target: UnitKind = "ratio") -> float | None:
    """跨单位归一。None → None 透传。

    ratio → percent: *100;percent → ratio: /100;同单位: identity。
    """
    if value is None:
        return None
    if unit == target:
        return float(value)
    if unit == "percent" and target == "ratio":
        return float(value) / 100.0
    if unit == "ratio" and target == "percent":
        return float(value) * 100.0
    raise ValueError(f"normalize_to 未知 unit→target: {unit} → {target}")


def _safe_metric(value, *, default: float = 0.0) -> float:
    """None-safe 取值:None/非数 → default(默认 0.0)。"""
    if value is None:
        return default
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    # nan/inf 也视作无效
    if v != v or v in (float("inf"), float("-inf")):
        return default
    return v
