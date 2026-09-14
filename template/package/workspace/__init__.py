"""
工作区 — Workspace 侧 ExperimentBase 子类。

覆盖 build_learner / build_objective / train_step / predict / evaluate。
可变：Agent 每轮可自由改写本文件。

⚠️ 这是骨架框架。init 时根据 profile 自动生成具体实现。
用户需要填充具体的模型架构、数据增强、评估逻辑。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Literal

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torchvision import transforms

from experiment import ExperimentBase
from experiment import SAMPLER_REGISTRY, register_sampler  # D 档；真源在 experiment.py


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
#
#     @classmethod
#     def from_cfg(cls, cfg, **kwargs):
#         # TODO: 从 cfg 构造模型
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
#
#     @classmethod
#     def from_cfg(cls, cfg):
#         # TODO: 从 cfg 构造损失函数
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
#
#     @classmethod
#     def from_cfg(cls, cfg):
#         # TODO: 从 cfg 构造数据增强
#         pass
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
    """Workspace 实现（骨架框架）。

    用户需要根据项目实现以下方法：
    - build_learner: 构建模型
    - build_objective: 构建损失函数
    - train_step: 一轮训练
    - predict: 前向推理
    - evaluate: 训练过程监控评估

    评 runner（MetricsShape.EVALUATE_RUNNER）时，在实例上设置
    ``adapter_runner`` 可调用对象（返回 dict[str, float]）；默认 None。
    """

    adapter_runner = None  # Callable[[], dict[str, float]] | None；训末官方评估取数源

    # ── build_learner ──────────────────────────────────────────
    def build_learner(self, cfg: dict, source=None) -> tuple[nn.Module, dict]:
        """构建模型，返回 (nn.Module, metadata_dict)。"""
        arch = str(cfg["MODEL_ARCH"]).lower().strip()
        if arch not in LEARNER_REGISTRY:
            raise KeyError(
                f"MODEL_ARCH={arch!r} 不在 registry {sorted(LEARNER_REGISTRY)}；"
                f"新增结构请 @register_learner(<name>) 装饰模型类（无需改 build_learner）"
            )
        cls = LEARNER_REGISTRY[arch]
        return cls.from_cfg(cfg, **({"source": source} if source is not None else {}))

    # ── build_objective ────────────────────────────────────────
    def build_objective(self, cfg: dict) -> tuple[nn.Module, dict]:
        """构建损失函数，返回 (nn.Module, metadata_dict)。"""
        loss = str(cfg["LOSS"]).lower().strip()
        if loss not in OBJECTIVE_REGISTRY:
            raise KeyError(
                f"LOSS={loss!r} 不在 registry {sorted(OBJECTIVE_REGISTRY)}；"
                f"新增 loss 请 @register_objective(<name>) 装饰目标类（无需改 build_objective）"
            )
        cls = OBJECTIVE_REGISTRY[loss]
        return cls.from_cfg(cfg)

    # ── train_step ─────────────────────────────────────────────
    def train_step(self, learner: nn.Module, source: Any, objective: nn.Module, *, epoch: int, shared_context: dict) -> dict[str, float]:
        """一轮训练。

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
        # cfg = shared_context["cfg"]
        # if "optimizer" not in shared_context:
        #     shared_context["optimizer"], _m = self.build_optimizer(learner, cfg)
        #     cfg.update(_m)
        #     shared_context["scheduler"], _m = self.build_scheduler(shared_context["optimizer"], cfg)
        #     cfg.update(_m)
        # optimizer = shared_context["optimizer"]
        # scheduler = shared_context["scheduler"]
        # learner.train()
        # total_loss, n = 0.0, 0
        # for batch in source:
        #     logits, target = self.predict(learner, batch, shared_context=shared_context)
        #     optimizer.zero_grad()
        #     loss = objective(logits, target)
        #     loss.backward()
        #     optimizer.step()
        #     total_loss += loss.item() * target.size(0)
        #     n += target.size(0)
        # if scheduler is not None:
        #     scheduler.step()
        # return {"train_loss": total_loss / n if n else 0.0}
        raise NotImplementedError("请实现 train_step")

    # ── predict ────────────────────────────────────────────────
    def predict(self, learner: nn.Module, batch: Any, *, shared_context: dict) -> tuple[torch.Tensor, torch.Tensor]:
        """前向推理。

        Returns:
            tuple: (logits, target) 或 (prediction, target)
        """
        # TODO: 实现你的推理逻辑
        # 示例（supervised）：
        # data, target = batch
        # device = shared_context["device"]
        # data = data.to(device, non_blocking=True)
        # target = target.to(device, non_blocking=True)
        # logits = learner(data)
        # return logits, target
        raise NotImplementedError("请实现 predict")

    # ── evaluate ───────────────────────────────────────────────
    @torch.no_grad()
    def evaluate(self, learner: nn.Module, *, shared_context: dict) -> dict[str, float]:
        """训练过程监控评估。

        注意：这是训练过程中的监控指标，不是官方 test。
        官方 test 由 contract.test() 实现。
        """
        # TODO: 实现你的评估逻辑
        # 示例（supervised）：
        # learner.eval()
        # device = shared_context["device"]
        # val_loader = shared_context["val_loader"]
        # correct = 0
        # total = 0
        # for data, target in val_loader:
        #     logits, target = self.predict(learner, (data, target), shared_context=shared_context)
        #     pred = logits.argmax(dim=1)
        #     correct += pred.eq(target).sum().item()
        #     total += target.size(0)
        # return {"val_accuracy": correct / total if total > 0 else 0.0}
        raise NotImplementedError("请实现 evaluate")

    # ── build_transforms ───────────────────────────────────────
    def build_transforms(self, cfg: dict) -> tuple[transforms.Compose, dict]:
        """构建数据增强 pipeline。"""
        aug = str(cfg["AUGMENTATION"]).lower().strip()
        if aug not in AUGMENTATION_REGISTRY:
            raise KeyError(
                f"AUGMENTATION={aug!r} 不在 registry {sorted(AUGMENTATION_REGISTRY)}；"
                f"新增增强请 @register_augmentation(<name>) 装饰类（无需改 build_transforms）"
            )
        cls = AUGMENTATION_REGISTRY[aug]
        return cls.from_cfg(cfg)

    # ── build_optimizer ────────────────────────────────────────
    def build_optimizer(self, model: nn.Module, cfg: dict) -> tuple[optim.Optimizer, dict]:
        """构建优化器,返回 (Optimizer, metadata_dict)。

        cfg["OPTIMIZER"] 强读分派:adam / adamw / sgd(未知 raise KeyError,no-fallback)。
        与 build_transforms 的 registry 语义一致:未知键即失败,不静默回落默认。
        """
        name = str(cfg["OPTIMIZER"]).lower().strip()
        lr = float(cfg["LR"])
        wd = float(cfg["WEIGHT_DECAY"])
        if name == "adam":
            opt = optim.Adam(model.parameters(), lr=lr, weight_decay=wd)
        elif name == "adamw":
            opt = optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)
        elif name == "sgd":
            opt = optim.SGD(model.parameters(), lr=lr, weight_decay=wd, momentum=float(cfg["MOMENTUM"]))
        else:
            raise KeyError(f"OPTIMIZER={name!r} 不支持;新增请在此加分派分支(adam/adamw/sgd)")
        return opt, {"OPTIMIZER": name, "LR": lr, "WEIGHT_DECAY": wd, **({"MOMENTUM": float(cfg["MOMENTUM"])} if name == "sgd" else {})}

    # ── build_scheduler ────────────────────────────────────────
    def build_scheduler(self, optimizer: optim.Optimizer, cfg: dict) -> tuple[Any, dict]:
        """构建学习率调度器,返回 (Scheduler or _NullScheduler, metadata_dict)。

        cfg["SCHEDULER"] 强读分派:cosine / step / none(未知 raise KeyError,no-fallback)。
        "none" → _NullScheduler()(具名 no-op),消除 return None 兜底。
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
    def build_dataloader(self, cfg: dict):
        """构建 DataLoader。"""
        # 通常由 contract.prepare_data 提供
        # D 档采样：勿在此重写整条管线；用 @register_sampler + cfg DATA_SAMPLER，
        # 由 ExperimentBase.wrap_train_loader（train.py 在 prepare_data 后调用）重包。
        return None


def create_workspace(cfg: dict) -> ExperimentBase:
    """工厂函数：创建 Workspace 实例。"""
    return Workspace()


# ═══════════════════════════════════════════════════════════════
# v1.33.0 — workspace_kind 注册表 + train.py 入口分桶支持
# ─────────────────────────────────────────────────────────────────
# 设计: 不绑任何具体业务 — business 可在 workspace 子类用
# @register_workspace_kind(MetricsShape.EVALUATE_RUNNER) 一行启用 ADAPTER 路径。
# 接受 MetricsShape enum 或老字符串("supervised"/"adapter"/"mammoth_cl")。
# 未注册默认 MetricsShape.EVALUATE_LEARNER,向后兼容 v1.23.0。
# ═══════════════════════════════════════════════════════════════
# v1.33.0 — WorkspaceKind 改为 MetricsShape 别名,import 路径保留
from scripts.lib.train_branch_types import (
    FrameworkKind,
    MetricsShape,
    TrainingMech,
)

# 保留 WorkspaceKind 名称(向后兼容 v1.24–v1.32 业务仓代码)
WorkspaceKind = MetricsShape

_KIND_REGISTRY: dict[str, MetricsShape] = {}
_MECH_REGISTRY: dict[str, TrainingMech] = {}


def register_workspace_kind(
    kind: MetricsShape | str,
    *,
    training_mech: TrainingMech = TrainingMech.NATIVE,
) -> Callable:
    """装饰器:标记 workspace build 函数的 metrics_shape(评估形态)+ training_mech(训练调度)。

    接受 MetricsShape enum 或老字符串("supervised"/"adapter"/"mammoth_cl")。
    老字符串走 MetricsShape.from_legacy() 归一 + DeprecationWarning。
    training_mech 默认 NATIVE(向后兼容);framework workspace 显式声明 IN_PROCESS/SUBPROCESS。

    Usage:
        @register_workspace_kind(MetricsShape.EVALUATE_RUNNER, training_mech=TrainingMech.SUBPROCESS)
        def build_external_cli_workspace(...): ...
    """
    import warnings

    if isinstance(kind, str):
        warnings.warn(
            f"register_workspace_kind 接收字符串字面 {kind!r} 是 v1.32.0 之前用法;v1.33.0 请改用 MetricsShape enum",
            DeprecationWarning,
            stacklevel=2,
        )
        kind = MetricsShape.from_legacy(kind)

    def _decorator(build_fn: Callable) -> Callable:
        name = build_fn.__name__
        _KIND_REGISTRY[name] = kind
        _MECH_REGISTRY[name] = training_mech

        def _wrapped(*args, **kwargs):
            ws = build_fn(*args, **kwargs)
            # 戳稳定名供训末查询；标量/None 非工作区实例，不戳
            if ws is None or isinstance(ws, (str, bytes, int, float, bool)):
                return ws
            setattr(ws, "__workspace_name__", name)  # 失败上抛（no-fallback）
            return ws

        _wrapped.__name__ = name
        _wrapped.__doc__ = build_fn.__doc__
        _wrapped.__wrapped__ = build_fn  # type: ignore[attr-defined]
        return _wrapped

    return _decorator


def get_workspace_kind(workspace_name: str) -> MetricsShape:
    """查注册表;未注册 → 默认 EVALUATE_LEARNER (向后兼容 v1.23.0)。

    v1.33.0 改动:默认从 "supervised" 字符串升为 MetricsShape.EVALUATE_LEARNER enum。
    """
    return _KIND_REGISTRY.get(workspace_name, MetricsShape.EVALUATE_LEARNER)


def get_training_mech(workspace_name: str) -> TrainingMech:
    """查 mech 注册表;未注册 → 默认 TrainingMech.NATIVE(向后兼容,①supervised/②RL 都走 native loop)。"""
    return _MECH_REGISTRY.get(workspace_name, TrainingMech.NATIVE)


__all__ = [
    "register_workspace_kind",
    "get_workspace_kind",
    "get_training_mech",
    "WorkspaceKind",
    # v1.33.0 — 业务仓可从 workspace 直接 import 三个 enum
    "MetricsShape",
    "TrainingMech",
    "FrameworkKind",
]
