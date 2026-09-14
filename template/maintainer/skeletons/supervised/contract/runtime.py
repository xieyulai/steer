"""契约常量：数据根、归一化、eval 规模等（供 prepare_data / test / 迁移参照）。"""
from __future__ import annotations

import os
from pathlib import Path

# ── 数据目录配置 ─────────────────────────────────────────────────
# 优先级：NN_DATA_DIR 环境变量 > DEFAULT_DATA_DIR > data/
# 数据量小（<1GB）：拷贝到 data/ 目录
# 数据量大（>=1GB）：软链接指向原始数据路径
#   ln -s /path/to/original/data data/dataset_name
DEFAULT_DATA_DIR = os.environ.get("NN_DATA_DIR", str(Path(__file__).resolve().parent.parent / "data"))

# ── Supervised 模板（FashionMNIST demo）────────────────────────────
# LOCKED_DATASET = 范式锁死的数据集身份(要求2):由 contract 钉死,不走 cfg,
# Agent 每轮动作不可达(改哪个数据集 = E 档/人审级,非 A-D 轮内动作)。
# 怎么处理(transform/aug/batch)仍可改 = 走 cfg(见 prepare_data 下游 DataLoader)。
# 新增数据集 = 在 prepare_data 的 DATASET_REGISTRY 加一行 + 改本常量。
LOCKED_DATASET = "fashionmnist"
FMNIST_MEAN = (0.2860,)
FMNIST_STD = (0.3530,)
DEFAULT_VAL_LOADER_BATCH_SIZE = 256

# ── 复现环境变量（HARD-GATE D4/O4 钉死；finalize 写入 config.json `_repro`）──
REPRO_ENV_KEYS: tuple[str, ...] = (
    "NN_SEED",
    "NN_DATA_DIR",
    "CUDA_VISIBLE_DEVICES",
)
