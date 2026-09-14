"""契约指标：键名、方向（供 contract 门面与 workspace 引用）。"""
from __future__ import annotations

METRIC_KEYS: dict[str, str] = {
    "val_accuracy": "maximize",
}

AUXILIARY_KEYS: dict[str, str] = {
    "val_loss": "minimize",
    "val_top2_accuracy": "maximize",
}
