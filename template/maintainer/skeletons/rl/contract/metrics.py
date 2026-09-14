"""RL 契约指标占位（立项骨架；迁项目后按 HARD-GATE E1/E5 确认）。"""
from __future__ import annotations

METRIC_KEYS: dict[str, str] = {
    "rect_norm_B": "maximize",
    "v1_eval": "maximize",
    "rect_norm_md": "maximize",
}

AUXILIARY_KEYS: dict[str, str] = {
    "perf_score_ellipse_core": "maximize",
    "perf_score_panda": "maximize",
    "perf_score_pp_ellipse_ring": "maximize",
    "perf_score_ellipse_ring": "maximize",
    "perf_score_rectangle": "maximize",
    "rect_norm_mode": "maximize",
}
