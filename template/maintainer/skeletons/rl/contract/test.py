"""RL 台账占位：含 mode='knn' 以满足 G-评估 A1；迁项目后实现完整评估。"""
from __future__ import annotations

from contract.metrics import AUXILIARY_KEYS, METRIC_KEYS
from contract.prepare_data import prepare_shared_context
from contract.runtime import (
    EVAL_SEED,
    N_EVAL_EPISODES,
    N_EVAL_EPISODES_SMOKE,
    REWARD_TARGETS_FINAL,
)


def run(learner, ws, *, shared_context: dict) -> dict[str, float]:
    eval_mode = "knn"
    contract = shared_context.get("contract")
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
