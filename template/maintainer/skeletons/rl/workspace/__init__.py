"""
工作区 — Workspace 侧 ExperimentBase 子类（RL 骨架）。

覆盖 build_learner / build_objective / train_step / predict / evaluate。
可变：Agent 每轮可自由改写本文件。

⚠️ 这是骨架框架。init 时根据 profile 自动生成。
用户需要填充具体的 RL 模型、训练逻辑、评估逻辑。
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
# RL 模型（在此添加你的 RL 模型）
# ─────────────────────────────────────────────────────────────────
# 使用 @register_learner 装饰器注册模型变体
# 示例：
# @register_learner("ppo")
# class PPOAgent(nn.Module):
#     def __init__(self, cfg):
#         super().__init__()
#         # TODO: 定义你的 RL 模型
#         pass
#
#     def forward(self, obs):
#         # TODO: 定义前向传播
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
    """RL workspace."""

    # ── build_learner ──────────────────────────────────────────
    def build_learner(self, cfg: dict[str, Any], source=None):
        """构建 RL 模型，返回 (nn.Module, metadata_dict)。"""
        arch = cfg.get("MODEL_ARCH", "ppo")
        if arch not in LEARNER_REGISTRY:
            raise KeyError(f"未知 RL 模型: {arch}（可用: {list(LEARNER_REGISTRY.keys())}）")
        model = LEARNER_REGISTRY[arch](cfg)
        return model, {}

    # ── build_objective ────────────────────────────────────────
    def build_objective(self, cfg: dict[str, Any]):
        """构建损失函数（RL 通常不需要，返回 None）。"""
        return None, {}

    # ── train_step ─────────────────────────────────────────────
    def train_step(self, learner, source, objective, *, epoch: int, shared_context: dict):
        """一轮训练（1 segment）。

        Args:
            learner: RL 模型
            source: 环境或数据源
            objective: None（RL 通常不需要）
            epoch: 当前 segment 序号（1-based）
            shared_context: 跨 epoch 共享字典

        Returns:
            dict: 训练指标（如 episode_reward、episode_length 等）
        """
        # TODO: 实现你的 RL 训练逻辑
        # 示例（stable-baselines3 风格）：
        # total_timesteps = cfg.get("SEGMENT_TIMESTEPS", 10000)
        # learner.learn(total_timesteps=total_timesteps)
        # return {"segment_timesteps": total_timesteps}
        raise NotImplementedError("请实现 train_step")

    # ── predict ────────────────────────────────────────────────
    def predict(self, learner, batch, *, shared_context: dict):
        """前向推理（RL 的 action 选择）。"""
        # TODO: 实现你的 RL 推理逻辑
        # 示例：
        # obs, _ = batch
        # action, _states = learner.predict(obs, deterministic=True)
        # return action
        raise NotImplementedError("请实现 predict")

    # ── evaluate ───────────────────────────────────────────────
    def evaluate(self, learner, *, shared_context: dict):
        """训练过程监控评估。

        注意：这是训练过程中的监控指标，不是官方 test。
        官方 test 由 contract.test() 实现。
        """
        # TODO: 实现你的 RL 评估逻辑
        # 示例：
        # env = shared_context.get("eval_env")
        # if env is None:
        #     return {}
        # obs, _ = env.reset()
        # total_reward = 0
        # done = False
        # while not done:
        #     action, _ = learner.predict(obs, deterministic=True)
        #     obs, reward, terminated, truncated, _ = env.step(action)
        #     total_reward += reward
        #     done = terminated or truncated
        # return {"eval_reward": total_reward}
        raise NotImplementedError("请实现 evaluate")

    # ── preflight_env_check ────────────────────────────────────
    def preflight_env_check(self, cfg: dict[str, Any]):
        """RL 特有：环境预检查。"""
        # TODO: 实现你的环境检查逻辑
        # 示例：
        # env = make_env(cfg)
        # obs, _ = env.reset()
        # assert obs.shape == (cfg["OBS_DIM"],), f"观测维度不匹配: {obs.shape}"
        # env.close()
        pass

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

        RL 通常用 SCHEDULER=none(无学习率调度),但保留 cosine/step 显式选项。
        cfg["SCHEDULER"] 强读分派:cosine / step / none(未知 raise KeyError)。
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
        """构建 DataLoader（RL 通常不需要）。"""
        return None


def create_workspace(cfg: dict[str, Any]) -> Workspace:
    """工厂函数：创建 Workspace 实例。"""
    return Workspace()
