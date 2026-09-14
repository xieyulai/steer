"""
工作区 — Workspace 侧 ExperimentBase 子类（physical 骨架）。

覆盖 build_learner / build_objective / train_step / predict / evaluate。
可变：Agent 每轮可自由改写本文件。

⚠️ 这是骨架框架。init 时根据 profile 自动生成。
用户需要填充具体的 PINN 模型、训练逻辑、评估逻辑。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
import torch.optim as optim

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


# ═══════════════════════════════════════════════════════════════
# OPTIMIZER_SCHEME 分派（physical 范式专属,β）
# ─────────────────────────────────────────────────────────────────
# B-soft 后:β 走 build_optimizer 的 elif 链(与 α 同形态,只是 cfg key
# 是 OPTIMIZER_SCHEME 而非 OPTIMIZER),不再用 registry / @register_optim_scheme。
# 新增 scheme = 在 build_optimizer 加 elif 分支(范式锁死,Agent 不可改 key)。
# ═══════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
# PINN 模型（在此添加你的 PINN 模型）
# ─────────────────────────────────────────────────────────────────
# 使用 @register_learner 装饰器注册模型变体
# 示例：
# @register_learner("mlp")
# class PINN_MLP(nn.Module):
#     def __init__(self, cfg):
#         super().__init__()
#         # TODO: 定义你的 PINN 模型
#         pass
#
#     def forward(self, x):
#         # TODO: 定义前向传播
#         pass
# ═══════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
# 物理约束损失（在此添加你的物理约束损失）
# ─────────────────────────────────────────────────────────────────
# 使用 @register_objective 装饰器注册损失函数变体
# 示例：
# @register_objective("pde_residual")
# class PDEResidualLoss(nn.Module):
#     def __init__(self, cfg):
#         super().__init__()
#         # TODO: 定义你的物理约束损失
#         pass
#
#     def forward(self, pred, x):
#         # TODO: 计算 PDE 残差
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
    """Physical-constrained learning workspace (PINN etc.)."""

    # ── build_learner ──────────────────────────────────────────
    def build_learner(self, cfg: dict[str, Any], source=None):
        """构建 PINN 模型，返回 (nn.Module, metadata_dict)。"""
        arch = cfg.get("MODEL_ARCH", "mlp")
        if arch not in LEARNER_REGISTRY:
            raise KeyError(f"未知 PINN 模型: {arch}（可用: {list(LEARNER_REGISTRY.keys())}）")
        model = LEARNER_REGISTRY[arch](cfg)
        return model, {}

    # ── build_objective ────────────────────────────────────────
    def build_objective(self, cfg: dict[str, Any]):
        """构建物理约束损失，返回 (nn.Module, metadata_dict)。"""
        loss_name = cfg.get("LOSS", "pde_residual")
        if loss_name not in OBJECTIVE_REGISTRY:
            raise KeyError(f"未知物理约束损失: {loss_name}（可用: {list(OBJECTIVE_REGISTRY.keys())}）")
        objective = OBJECTIVE_REGISTRY[loss_name](cfg)
        return objective, {}

    # ── prepare_data ───────────────────────────────────────────
    def prepare_data(self, cfg: dict[str, Any]):
        """准备数据（physical 通常在 train_step 中采样）。"""
        # TODO: 实现你的数据准备逻辑
        # 示例：
        # collocation_points = sample_collocation(cfg)
        # boundary_points = sample_boundary(cfg)
        # return collocation_points, boundary_points
        return None, None

    # ── train_step ─────────────────────────────────────────────
    def train_step(self, learner, source, objective, *, epoch: int, shared_context: dict):
        """一轮训练（1 stage）。

        Args:
            learner: PINN 模型
            source: 配置点或数据源
            objective: 物理约束损失
            epoch: 当前 stage 序号（1-based）
            shared_context: 跨 epoch 共享字典

        Returns:
            dict: 训练指标（如 pde_loss、bc_loss 等）
        """
        # TODO: 实现你的 PINN 训练逻辑
        # 示例（Adam + LBFGS 两阶段）：
        # if epoch == 1:  # Adam 阶段
        #     for i in range(cfg.get("ADAM_STEPS", 1000)):
        #         x = sample_collocation(cfg)
        #         pred = learner(x)
        #         loss = objective(pred, x)
        #         loss.backward()
        #         shared_context["optimizer"].step()
        #         shared_context["optimizer"].zero_grad()
        #     return {"adam_loss": loss.item()}
        # elif epoch == 2:  # LBFGS 阶段
        #     def closure():
        #         x = sample_collocation(cfg)
        #         pred = learner(x)
        #         loss = objective(pred, x)
        #         loss.backward()
        #         return loss
        #     shared_context["optimizer"].step(closure)
        #     return {"lbfgs_loss": closure().item()}
        raise NotImplementedError("请实现 train_step")

    # ── predict ────────────────────────────────────────────────
    def predict(self, learner, batch, *, shared_context: dict):
        """前向推理。"""
        # TODO: 实现你的推理逻辑
        # 示例：
        # x, _ = batch
        # return learner(x)
        raise NotImplementedError("请实现 predict")

    # ── evaluate ───────────────────────────────────────────────
    def evaluate(self, learner, *, shared_context: dict):
        """训练过程监控评估。

        注意：这是训练过程中的监控指标，不是官方 test。
        官方 test 由 contract.test() 实现。
        """
        # TODO: 实现你的评估逻辑
        # 示例：
        # x_val = shared_context.get("val_points")
        # if x_val is None:
        #     return {}
        # with torch.no_grad():
        #     pred = learner(x_val)
        #     # 计算验证损失
        #     val_loss = ...
        # return {"val_phy_loss": val_loss}
        raise NotImplementedError("请实现 evaluate")

    # ── build_optimizer ────────────────────────────────────────
    def build_optimizer(self, model, cfg):
        """构建优化器,返回 (Optimizer, metadata_dict)。

        cfg["OPTIMIZER_SCHEME"] 强读 elif 分派(β,与 α 同形态;只是 cfg key
        是 OPTIMIZER_SCHEME 而非 OPTIMIZER):
            - "adam"      → 单阶段 Adam
            - "lbfgs"     → 单阶段 LBFGS(读 cfg["LBFGS_MAX_ITER"])
            - "adam_lbfgs"→ PINN 典型分阶段;返回第 1 阶段 Adam,
                           阶段切换由 train_step 管(WP3 边界保留)
        未知 scheme → KeyError(no-fallback;新增 = 在此加 elif 分支)。
        注:physical 范式不再读 cfg["OPTIMIZER"](原 adam/adamw/sgd 分派被
        OPTIMIZER_SCHEME 取代;supervised/rl 骨架仍走 cfg["OPTIMIZER"] 分派)。
        范式锁死:分派形态(elif)与 cfg key(OPTIMIZER_SCHEME)由骨架写死,
        Agent 不可改;Agent 只能在 build_* 范围内改各分支的具体构造。
        """
        scheme = str(cfg["OPTIMIZER_SCHEME"]).lower().strip()
        lr = float(cfg["LR"])
        if scheme == "adam":
            weight_decay = float(cfg["WEIGHT_DECAY"])
            optimizer = optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)
            return optimizer, {
                "OPTIMIZER_SCHEME": "adam",
                "LR": lr,
                "WEIGHT_DECAY": weight_decay,
                "STAGES": ["adam"],
            }
        elif scheme == "lbfgs":
            max_iter = int(cfg["LBFGS_MAX_ITER"])
            optimizer = optim.LBFGS(model.parameters(), lr=lr, max_iter=max_iter)
            return optimizer, {
                "OPTIMIZER_SCHEME": "lbfgs",
                "LR": lr,
                "LBFGS_MAX_ITER": max_iter,
                "STAGES": ["lbfgs"],
            }
        elif scheme == "adam_lbfgs":
            # β 经典分阶段:第 1 阶段 Adam;第 2 阶段 LBFGS 由 train_step
            # 读 metadata["STAGES"][1] 自行构造(WP3 边界保留 — 治理层接入处)。
            weight_decay = float(cfg["WEIGHT_DECAY"])
            optimizer = optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)
            return optimizer, {
                "OPTIMIZER_SCHEME": "adam_lbfgs",
                "LR": lr,
                "WEIGHT_DECAY": weight_decay,
                "STAGES": ["adam", "lbfgs"],
            }
        raise KeyError(
            f"OPTIMIZER_SCHEME={scheme!r} 不支持;"
            f"新增 = 在 build_optimizer 加 elif 分支;"
            f"可用: adam / lbfgs / adam_lbfgs"
        )

    # ── build_scheduler ────────────────────────────────────────
    def build_scheduler(self, optimizer, cfg):
        """构建学习率调度器,返回 (Scheduler or _NullScheduler, metadata_dict)。

        cfg["SCHEDULER"] 强读分派:cosine / step / none(未知 raise KeyError)。
        物理训练通常 SCHEDULER=none(LBFGS 段靠内部重新求步长,不再调外部 scheduler),
        但保留 cosine/step 显式选项。
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
        """构建 DataLoader（physical 通常不需要）。"""
        return None


def create_workspace(cfg: dict[str, Any]) -> Workspace:
    """工厂函数：创建 Workspace 实例。"""
    return Workspace()
