"""数据契约入口（supervised：train/val loader）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

import torch
from torch.utils.data import DataLoader, Subset
from torchvision import datasets, transforms

from contract.runtime import (
    DEFAULT_VAL_LOADER_BATCH_SIZE,
    FMNIST_MEAN,
    FMNIST_STD,
    LOCKED_DATASET,
)

if TYPE_CHECKING:
    from experiment import ExperimentBase

_EVAL_TRANSFORM = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize(FMNIST_MEAN, FMNIST_STD),
])


def base_transform() -> transforms.Compose:
    """与 test 集相同的归一化（train 可在 cfg 覆盖 _train_transform）。"""
    return _EVAL_TRANSFORM


# ── 数据集注册表(范式锁死 / contract-frozen)──────────────────────
# 要求2:读哪个数据集 = LOCKED_DATASET(contract 常量,Agent 不可达);
#   怎么处理(transform/aug/batch)可改 = 走 cfg(见下方 DataLoader 参数)。
# 新增数据集 = 在 DATASET_REGISTRY 加一行(contract 改,非 agent 每轮动作)。
# 未知名 → KeyError(no-fallback;不静默回落 FashionMNIST)。
DATASET_REGISTRY: dict = {
    "fashionmnist": lambda root, train, transform: datasets.FashionMNIST(
        root, train=train, download=True, transform=transform,
    ),
}


def _build_dataset(name: str, root: str, *, train: bool, transform):
    """按 registry 名查表构造数据集(范式锁死:名来自 contract,非 cfg)。"""
    key = str(name).lower().strip()
    if key not in DATASET_REGISTRY:
        raise KeyError(
            f"DATASET={name!r} 不支持;"
            f"新增 = 在 DATASET_REGISTRY 加一行(contract 改,非 agent 每轮动作);"
            f"可用: {list(DATASET_REGISTRY.keys())}"
        )
    return DATASET_REGISTRY[key](root, train, transform)


def prepare_data(contract: ExperimentBase, cfg: dict) -> tuple[DataLoader, DataLoader]:
    """Supervised：从 contract.data_dir 构建 train/val DataLoader。"""
    batch_size = int(cfg["BATCH_SIZE"])
    num_workers = int(cfg["NUM_WORKERS"])
    train_transform = cfg.get("_train_transform", None)  # 小写键：config-section 访问，允许

    t_train = train_transform if train_transform is not None else base_transform()
    t_val = base_transform()

    train_dataset = _build_dataset(
        LOCKED_DATASET, contract.data_dir, train=True, transform=t_train,
    )
    val_source = _build_dataset(
        LOCKED_DATASET, contract.data_dir, train=True, transform=t_val,
    )

    n_total = len(train_dataset)
    n_val = int(n_total * contract.val_ratio)
    n_train = n_total - n_val

    gen = torch.Generator().manual_seed(contract.seed)
    indices = torch.randperm(n_total, generator=gen).tolist()
    train_indices = indices[:n_train]
    val_indices = indices[n_train:]

    pin = torch.cuda.is_available()
    train_loader = DataLoader(
        Subset(train_dataset, train_indices),
        batch_size=batch_size,
        shuffle=True,
        num_workers=num_workers,
        pin_memory=pin,
    )
    val_loader = DataLoader(
        Subset(val_source, val_indices),
        batch_size=DEFAULT_VAL_LOADER_BATCH_SIZE,
        shuffle=False,
        num_workers=num_workers,
        pin_memory=pin,
    )
    return train_loader, val_loader


def prepare_shared_context(contract: ExperimentBase, shared_context: dict) -> None:
    """RL profile：将数据根写入 shared_context（与 contract.test 同侧）。"""
    import os
    from pathlib import Path

    raw = os.environ.get("NN_DATA_DIR", "").strip()
    if raw:
        shared_context["dataset_path"] = str(Path(raw).expanduser().resolve())
    else:
        data_dir = getattr(contract, "DATA_DIR", None) or contract.data_dir
        shared_context["dataset_path"] = str(Path(data_dir).expanduser().resolve())
