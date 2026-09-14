"""契约指标：键名、方向（供 contract 门面与 workspace 引用）。

⚠️ 这是骨架占位符。init 时根据 profile 自动替换为具体实现。
用户需要根据项目定义指标。
"""
from __future__ import annotations

# TODO: 根据你的项目定义指标
# 示例（supervised）：
# METRIC_KEYS: dict[str, str] = {"val_accuracy": "maximize"}
# AUXILIARY_KEYS: dict[str, str] = {"val_loss": "minimize"}
#
# 示例（rl）：
# METRIC_KEYS: dict[str, str] = {"rect_norm_B": "maximize"}
# AUXILIARY_KEYS: dict[str, str] = {"average_forgetting": "minimize"}
#
# 示例（physical）：
# METRIC_KEYS: dict[str, str] = {"rel_l2": "minimize"}
# AUXILIARY_KEYS: dict[str, str] = {"val_phy_loss": "minimize"}

METRIC_KEYS: dict[str, str] = {}
AUXILIARY_KEYS: dict[str, str] = {}
