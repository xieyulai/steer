"""Physical：train.py 经 contract.prepare_data 入口；返回 (None, None)，采样在 train_step。"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from contract.runtime import DEFAULT_DATA_DIR

if TYPE_CHECKING:
    from experiment import ExperimentBase


def prepare_data(contract: ExperimentBase, cfg: dict) -> tuple[Any, Any]:
    _ = DEFAULT_DATA_DIR
    return None, None
