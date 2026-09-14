"""
工作区 — Workspace 侧 ExperimentBase 子类（supervised 骨架）。

覆盖 build_learner / build_objective / train_step / predict / evaluate。
可变：Agent 每轮可自由改写本文件。

⚠️ 这是骨架框架。init 时根据 profile 自动生成。
用户需要填充具体的模型架构、数据增强、评估逻辑。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torchvision import transforms

from experiment import ExperimentBase


# ═══════════════════════════════════════════════════════════════
# 可插拔注册表（pluggable）
# ─────────────────────────────────────────────────────────────────
# 新增模型/损失变体 = 用 @register_* 装饰一个类 + 在 cfg 设键，
# 无需改 build_learner / build_objective 的分派逻辑。
# 未知键 → KeyError（no-fallback；不静默回落到默认变体）。
# ═══════════════════════════════════════════════════════════════

LEARNER_REGISTRY: dict[str, type] = {}
OBJECTIVE_REGISTRY: dict[str, type] = {}
AUGMENTATION_REGISTRY: dict[str, type] = {}


def register_learner(name: str):
    def _decorator(cls):
        LEARNER_REGISTRY[name] = cls
        return cls
    return _decorator


def register_objective(name: str):
    def _decorator(cls):
        OBJECTIVE_REGISTRY[name] = cls
        return cls
    return _decorator


def register_augmentation(name: str):
    def _decorator(cls):
        AUGMENTATION_REGISTRY[name] = cls
        return cls
    return _decorator


# ═══════════════════════════════════════════════════════════════
# 模型架构（在此添加你的模型）
# ─────────────────────────────────────────────────────────────────
# 使用 @register_learner 装饰器注册模型变体
# 示例：
# @register_learner("cnn")
# class SimpleCNN(nn.Module):
#     def __init__(self, cfg):
#         super().__init__()
#         # TODO: 定义你的模型架构
#         pass
#
#     def forward(self, x):
#         # TODO: 定义前向传播
#         pass
# ═══════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
# 损失函数（在此添加你的损失函数）
# ─────────────────────────────────────────────────────────────────
# 使用 @register_objective 装饰器注册损失函数变体
# 示例：
# @register_objective("cross_entropy")
# class CrossEntropyLoss(nn.Module):
#     def __init__(self, cfg):
#         super().__init__()
#         # TODO: 定义你的损失函数
#         pass
#
#     def forward(self, pred, target):
#         # TODO: 定义损失计算
#         pass
# ═══════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
# 数据增强（在此添加你的数据增强）
# ─────────────────────────────────────────────────────────────────
# 使用 @register_augmentation 装饰器注册数据增强变体
# 示例：
# @register_augmentation("baseline")
# class BaselineAugmentation:
#     def __init__(self, cfg):
#         # TODO: 定义你的数据增强
#         pass
#
#     def __call__(self, x):
#         # TODO: 应用数据增强
#         return x
# ═══════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
# _NullScheduler — no-fallback 的具名 no-op 调度器
# ─────────────────────────────────────────────────────────────────
# build_scheduler 显式 "none" 时返回它(而非 None),消除调用方判 None 的
# 隐式兜底分支。step()/get_last_lr() 空实现,语义=「确实无调度,非遗漏」。
# 注:skeleton 各自带一份 —— skeleton 是独立 cp 单元,重复是设计意图。
# ═══════════════════════════════════════════════════════════════
class _NullScheduler:
    """具名 no-op 调度器:替代 build_scheduler 的 `return None` 兜底。"""
    def step(self, epoch=None):
        pass

    def get_last_lr(self):
        return []

    def state_dict(self):
        return {}

    def load_state_dict(self, state_dict):
        pass


class Workspace(ExperimentBase):
    """Supervised learning workspace."""

    # ── build_learner ──────────────────────────────────────────
    def build_learner(self, cfg: dict[str, Any], source=None):
        """构建模型，返回 (nn.Module, metadata_dict)。"""
        arch = cfg.get("MODEL_ARCH", "cnn")
        if arch not in LEARNER_REGISTRY:
            raise KeyError(f"未知模型架构: {arch}（可用: {list(LEARNER_REGISTRY.keys())}）")
        model = LEARNER_REGISTRY[arch](cfg)
        return model, {}

    # ── build_objective ────────────────────────────────────────
    def build_objective(self, cfg: dict[str, Any]):
        """构建损失函数，返回 (nn.Module, metadata_dict)。"""
        loss_name = cfg.get("LOSS", "cross_entropy")
        if loss_name not in OBJECTIVE_REGISTRY:
            raise KeyError(f"未知损失函数: {loss_name}（可用: {list(OBJECTIVE_REGISTRY.keys())}）")
        objective = OBJECTIVE_REGISTRY[loss_name](cfg)
        return objective, {}

    # ── build_transforms ───────────────────────────────────────
    def build_transforms(self, cfg: dict[str, Any], *, for_test: bool = False):
        """构建数据增强 pipeline。"""
        aug_name = cfg.get("AUGMENTATION", "baseline")
        if aug_name not in AUGMENTATION_REGISTRY:
            raise KeyError(f"未知数据增强: {aug_name}（可用: {list(AUGMENTATION_REGISTRY.keys())}）")
        return AUGMENTATION_REGISTRY[aug_name](cfg)

    # ── train_step ─────────────────────────────────────────────
    def train_step(self, learner, source, objective, *, epoch: int, shared_context: dict):
        """一轮训练（1 epoch）。

        Args:
            learner: 模型
            source: DataLoader 或数据源
            objective: 损失函数
            epoch: 当前 epoch 序号（1-based）
            shared_context: 跨 epoch 共享字典

        Returns:
            dict: 训练指标（如 loss、accuracy 等）
        """
        # TODO: 实现你的训练逻辑
        # 示例（supervised）：
        # learner.train()
        # total_loss = 0
        # for batch in source:
        #     x, y = batch
        #     pred = learner(x)
        #     loss = objective(pred, y)
        #     loss.backward()
        #     shared_context["optimizer"].step()
        #     shared_context["optimizer"].zero_grad()
        #     total_loss += loss.item()
        # return {"train_loss": total_loss / len(source)}
        raise NotImplementedError("请实现 train_step")

    # ── predict ────────────────────────────────────────────────
    def predict(self, learner, batch, *, shared_context: dict):
        """前向推理。"""
        # TODO: 实现你的推理逻辑
        # 示例（supervised）：
        # x, y = batch
        # return learner(x)
        raise NotImplementedError("请实现 predict")

    # ── evaluate ───────────────────────────────────────────────
    def evaluate(self, learner, *, shared_context: dict):
        """训练过程监控评估。

        注意：这是训练过程中的监控指标，不是官方 test。
        官方 test 由 contract.test() 实现。
        """
        # TODO: 实现你的评估逻辑
        # 示例（supervised）：
        # learner.eval()
        # val_loader = shared_context["val_loader"]
        # correct = 0
        # total = 0
        # with torch.no_grad():
        #     for batch in val_loader:
        #         x, y = batch
        #         pred = learner(x)
        #         correct += (pred.argmax(1) == y).sum().item()
        #         total += y.size(0)
        # return {"val_accuracy": correct / total}
        raise NotImplementedError("请实现 evaluate")

    # ── build_optimizer ────────────────────────────────────────
    def build_optimizer(self, model, cfg):
        """构建优化器,返回 (Optimizer, metadata_dict)。

        cfg["OPTIMIZER"] 强读分派:adam / adamw / sgd(未知 raise KeyError)。
        """
        name = str(cfg["OPTIMIZER"]).lower().strip()
        lr = float(cfg["LR"])
        weight_decay = float(cfg["WEIGHT_DECAY"])
        if name == "adam":
            optimizer = optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)
        elif name == "adamw":
            optimizer = optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
        elif name == "sgd":
            optimizer = optim.SGD(model.parameters(), lr=lr, weight_decay=weight_decay, momentum=float(cfg["MOMENTUM"]))
        else:
            raise KeyError(f"OPTIMIZER={name!r} 不支持;新增请在此加分派分支(adam/adamw/sgd)")
        return optimizer, {"OPTIMIZER": name, "LR": lr, "WEIGHT_DECAY": weight_decay, **({"MOMENTUM": float(cfg["MOMENTUM"])} if name == "sgd" else {})}

    # ── build_scheduler ────────────────────────────────────────
    def build_scheduler(self, optimizer, cfg):
        """构建学习率调度器,返回 (Scheduler or _NullScheduler, metadata_dict)。

        cfg["SCHEDULER"] 强读分派:cosine / step / none(未知 raise KeyError)。
        "none" → _NullScheduler(),消除 return None 兜底。
        """
        name = str(cfg["SCHEDULER"]).lower().strip()
        if name == "cosine":
            return optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=int(cfg["EPOCHS"])), {"SCHEDULER": name}
        if name == "step":
            return optim.lr_scheduler.StepLR(optimizer, step_size=int(cfg["STEP_SIZE"]), gamma=float(cfg["GAMMA"])), {"SCHEDULER": name}
        if name == "none":
            return _NullScheduler(), {"SCHEDULER": name}
        raise KeyError(f"SCHEDULER={name!r} 不支持;新增请在此加分派分支(cosine/step/none)")

    # ── build_dataloader ───────────────────────────────────────
    def build_dataloader(self, cfg):
        """构建 DataLoader。"""
        # 通常由 contract.prepare_data 提供
        # 这里可以添加自定义的 DataLoader 逻辑
        return None


def create_workspace(cfg: dict[str, Any]) -> Workspace:
    """工厂函数：创建 Workspace 实例。"""
    return Workspace()
