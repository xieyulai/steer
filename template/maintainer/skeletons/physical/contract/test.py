"""Physical 台账占位：迁项目后实现真实 rel_l2 评估。"""
from __future__ import annotations

from collections.abc import Callable

from contract.metrics import AUXILIARY_KEYS, METRIC_KEYS


def run(
    learner, ws, *, shared_context: dict,
    adapter_runner: Callable[[], dict[str, float]] | None = None,
) -> dict[str, float]:
    # ADAPTER 模式: learner=None + adapter_runner 注册 → 转发业务仓出分(与门面对齐)
    if learner is None:
        if adapter_runner is not None:
            return adapter_runner()
        raise ValueError(
            "contract.test.run: learner=None 且 adapter_runner=None,"
            " 请显式指定 ADAPTER 路径或确保 physical 路径传 learner"
        )
    out: dict[str, float] = {}
    for key in list(METRIC_KEYS) + list(AUXILIARY_KEYS):
        out[key] = 0.0
    return out
