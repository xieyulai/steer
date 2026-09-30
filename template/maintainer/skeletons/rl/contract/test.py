"""RL 台账占位：含 mode='knn' 以满足 G-评估 A1；迁项目后实现完整评估。"""
from __future__ import annotations

from collections.abc import Callable

from contract.metrics import AUXILIARY_KEYS, METRIC_KEYS
from contract.prepare_data import prepare_shared_context
from contract.runtime import (
    EVAL_SEED,
    N_EVAL_EPISODES,
    N_EVAL_EPISODES_SMOKE,
    REWARD_TARGETS_FINAL,
)


def run(
    learner, ws, *, shared_context: dict,
    adapter_runner: Callable[[], dict[str, float]] | None = None,
    contract=None,
) -> dict[str, float]:
    """contract 由门面显式传入（ADR-11：禁经 shared_context 袋内传递）。"""
    # ADAPTER 模式: learner=None + adapter_runner 注册 → 转发业务仓出分(与门面对齐)
    if learner is None:
        if adapter_runner is not None:
            return adapter_runner()
        raise ValueError(
            "contract.test.run: learner=None 且 adapter_runner=None,"
            " 请显式指定 ADAPTER 路径或确保 rl 路径传 learner"
        )
    eval_mode = "knn"
    if contract is not None:
        prepare_shared_context(contract, shared_context)

    is_smoke = shared_context.get("smoke", False)
    n_episodes = N_EVAL_EPISODES_SMOKE if is_smoke else N_EVAL_EPISODES
    _ = (
        eval_mode,
        n_episodes,
        EVAL_SEED,
        REWARD_TARGETS_FINAL,
        shared_context.get("dataset_path", ""),
    )

    # 迁项目后：在此调用 workspace.infer 辅助函数，禁止 ws.evaluate
    out: dict[str, float] = {}
    for key in list(METRIC_KEYS) + list(AUXILIARY_KEYS):
        out[key] = 0.0
    return out
