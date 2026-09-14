"""RL 数据契约：无 DataLoader，仅解析 dataset_path。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from experiment import ExperimentBase


def prepare_shared_context(contract: ExperimentBase, shared_context: dict) -> None:
    raw = os.environ.get("NN_DATA_DIR", "").strip()
    if raw:
        shared_context["dataset_path"] = str(Path(raw).expanduser().resolve())
    else:
        from contract.runtime import DATA_DIR

        data_dir = getattr(contract, "DATA_DIR", None) or DATA_DIR
        shared_context["dataset_path"] = str(Path(data_dir).expanduser().resolve())


def prepare_data(contract: ExperimentBase, cfg: dict) -> tuple[Any, Any]:
    """RL：train.py 仍解包两值；实际路径在 test 前经 shared_context 写入。"""
    return None, None
