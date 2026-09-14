"""数据契约入口（supervised：train/val loader；RL/physical：通常返回 None）。

⚠️ 这是骨架占位符。init 时根据 profile 自动替换为具体实现。
用户需要根据项目实现 prepare_data。

边界（D 档拆两半）：
- 本文件只负责「读哪个数据集」+ 返回标准 DataLoader（须带 .dataset）
- WeightedRandomSampler / 过采样等「怎么抽 batch」→ workspace
  ``@register_sampler`` + cfg ``DATA_SAMPLER``（见 ExperimentBase.wrap_train_loader）
- 禁止在本文件堆训练技巧分支（否则每加一种采样都要 NN_RELAUNCH）
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from experiment import ExperimentBase


def prepare_data(contract: ExperimentBase, cfg: dict):
    """准备数据源。

    返回值因 profile 而异：
    - supervised: (train_loader, val_loader)
    - rl: (None, None) — 数据在 train_step 中通过环境交互获取
    - physical: (None, None) — 数据在 train_step 中采样

    Raises:
        NotImplementedError: 用户需要根据项目实现此函数
    """
    # TODO: 根据你的项目实现 prepare_data
    # 示例（supervised）：
    # from torch.utils.data import DataLoader
    # from torchvision import datasets, transforms
    # ...
    # return train_loader, val_loader  # DataLoader 须暴露 .dataset
    #
    # 示例（rl/physical）：
    # return None, None
    raise NotImplementedError("请根据你的项目实现 prepare_data")


def prepare_shared_context(contract: ExperimentBase, shared_context: dict) -> None:
    """将数据根写入 shared_context（与 contract.test 同侧）。

    RL/physical 项目通常需要此函数。
    """
    raw = os.environ.get("NN_DATA_DIR", "").strip()
    if raw:
        shared_context["dataset_path"] = str(Path(raw).expanduser().resolve())
    else:
        data_dir = getattr(contract, "DATA_DIR", None) or contract.data_dir
        shared_context["dataset_path"] = str(Path(data_dir).expanduser().resolve())
