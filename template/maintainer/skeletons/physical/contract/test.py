"""Physical 台账占位：迁项目后实现真实 rel_l2 评估。"""
from __future__ import annotations

from contract.metrics import AUXILIARY_KEYS, METRIC_KEYS


def run(learner, ws, *, shared_context: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    for key in list(METRIC_KEYS) + list(AUXILIARY_KEYS):
        out[key] = 0.0
    return out
