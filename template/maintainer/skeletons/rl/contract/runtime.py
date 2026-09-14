"""RL 契约常量占位（迁后钉死 DATA_DIR / eval 规模等）。"""
from __future__ import annotations

import os
from pathlib import Path

DATA_DIR = os.environ.get(
    "NN_DATA_DIR",
    str(Path(__file__).resolve().parent.parent / "data"),
)
EVAL_SEED = int(os.environ.get("NN_EVAL_SEED", "42"))
N_EVAL_EPISODES = int(os.environ.get("NN_N_EVAL_EPISODES", "100"))
N_EVAL_EPISODES_SMOKE = int(os.environ.get("NN_N_EVAL_SMOKE", "10"))
EVAL_KNN_K_NEIGHBORS = int(os.environ.get("NN_EVAL_KNEIGHBORS", "15"))

REWARD_TARGETS_FINAL: dict = {
    "min_delta_n_eff": 0.0675,
    "B": 2.0e6,
    "mode_number": 2,
}
