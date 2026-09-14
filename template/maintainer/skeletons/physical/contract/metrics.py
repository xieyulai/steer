"""Physical 契约指标占位。"""
from __future__ import annotations

METRIC_KEYS: dict[str, str] = {
    "rel_l2": "minimize",
}

AUXILIARY_KEYS: dict[str, str] = {
    "val_phy_loss": "minimize",
}
