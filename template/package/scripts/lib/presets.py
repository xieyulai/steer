"""presets.py — exploration_mode 单旋钮权威 bundle 表。

单一权威：default_for_mode(mode) = deep_merge(_BASE, _MODE_DEFAULTS[mode])。
exploration_mode（6 档）是唯一 selector；旧 _PRESETS 4-style 已退役。
"""
from __future__ import annotations

import copy
from typing import Any


# 公共基底（全 14 段默认；≈ 旧 balanced，对齐 v4：primary_delta_rel / goal.policy=focus_only）
_BASE: dict[str, Any] = {
    "checkpoint": "best",
    "keep": {
        "improve_mode": "any_primary",
        "mode": "relative",
        "primary_delta_rel": 0.005,
        "near_best_abs": 0.0,
    },
    "reflect": {
        "interval": 1,
        "force": False,
        "skip": False,
        "evidence_recent": 3,
        "evidence_attested_failures": 3,
        "evidence_include_flagged": True,
        "evidence_log_tail_lines": 200,
        "evidence_snapshot_diff": True,
        "evidence_git_log": True,
        "evidence_git_log_max": 12,
        "diversity_check": {"enabled": True, "window": 5,
                            "primary_repeat_threshold": 0.6,
                            "tier_repeat_threshold": 0.8},
        "leader_attribution": {"enabled": True},
        "tam_reconcile": {"enabled": True},
        "external": {"sources": ["arxiv", "scholar", "serper", "github"],
                     "plateau_force_all_sources": True},
    },
    "goal": {"value": None, "metric": None, "op": None,
             "policy": "focus_only", "scenario_goals": {}},
    "external": {"enabled": True, "max_http_per_reflect": 6,
                 "paper_hits_default": 3, "paper_hits_deepen": 5,
                 "pdf_enabled": True, "serper_key_env": "SERPER_API_KEY",
                 "task_domain": ""},
    "early_stop": {"patience": 0},
    "tier_attestation": {"enabled": True, "window": 12, "exhaust_min_attempts": 2},
    "gpu": {"mem_reserve_gb": 2.0, "estimated_mem_gb": 4.0,
            "exclusive_mem_ratio": 0.25, "exclusive_util_max": 10,
            "shareable_mem_ratio": 0.70, "shareable_util_max": 50,
            "busy_mem_ratio": 0.85, "busy_util_min": 80, "colocate_on_single": True},
    "training": {"train_poll_interval_sec": 300},
    "context": {"injection": "full", "journal_max_entries": 15,
                "recent_rows": 5, "language": "auto"},
    "analyse": {"recent_rows": 10, "aux_max": 5, "flat_pct": 0.5, "noise_std_hint": None},
    "compress": {"experience_auto_compress": "after_round",
                 "experience_compress_preset": "standard", "experience_compress_keep_n": 5,
                 "experience_compress_keep_reflects": 2, "experience_compress_tier_cell_max": 80,
                 "experience_compress_scenario_cell_max": 120,
                 "experience_compress_reflect_hist_summary_max": 240,
                 "experience_compress_min_lines": 400, "experience_compress_min_archivable": 10,
                 "experience_compress_cooldown_rounds": 2},
    "safety": {"human_guidance_gate_fail_fast": False, "skill_activity_log": True},
    "innovation": {"audit_enabled": True, "fingerprint_enabled": True,
                   "fingerprint_authoritative": True},
}


# 6 档 per-mode 覆盖（spec §4 权威表 + tier_start + runtime）
# experiment/exploration 过渡键已退役（Task 5 干净切）。
#
# paper_depth 双语义锁（T5/ADR-7，防漂移）：同一 paper_depth 兼两义——
#   ① 检索强度（P0 不检索 → P3 取全文）；
#   ② 深度天花板（P0→routine / P1→derived / P2→different / P3→different+novel-可证）。
# 两义由 apply_novel_ceiling（innovation_fingerprint.py）耦锁：different+supported ∧ P3+ 才升 novel。
# 改 paper_depth = 同时动两义，不可只调其一；见 test_find_phase::test_paper_depth_dual_semantics_guard。
#
# seek_plateau_rounds（T5/ADR-8 寻找 eagerness）：寻找(find)触发的撞墙阈值，按 mode 走，
#   ≠ 全局 agent.plateau_rounds（那是 verify/评估 的 deepen 阈值，find 不读）。eagerness 随
#   paper_depth 单调：aggressive(P3)=1 轮即找 / innovate(P2)=5 / optimize(P1)=7 / careful(P0)=None 永不找。
#   None = 永不寻找；explore 同 innovate=5（同 external profile）；auto 运行时由 effective_mode
#   重选 vanilla 档，此处 7 仅占位（运行时不读）。
_MODE_DEFAULTS: dict[str, dict[str, Any]] = {
    "careful": {
        "keep": {"primary_delta_rel": 0.01},
        "reflect": {"interval": 2},
        "external": {"paper_depth": "P0", "docs_depth": "D0",
                     "github_impl": False, "github_ecosystem": False,
                     "seek_plateau_rounds": None},  # 永不寻找
        "early_stop": {"patience": 5},
        "tier_start": "A", "runtime": "optimize",
    },
    "optimize": {
        "external": {"paper_depth": "P1", "docs_depth": "D1",
                     "github_impl": False, "github_ecosystem": True,
                     "seek_plateau_rounds": 7},
        "early_stop": {"patience": 3},
        "tier_start": "B", "runtime": "optimize",
    },
    "innovate": {
        "external": {"paper_depth": "P2", "docs_depth": "D2",
                     "github_impl": True, "github_ecosystem": True,
                     "seek_plateau_rounds": 5},
        "early_stop": {"patience": 3},
        "tier_start": "C", "runtime": "innovate",
    },
    "aggressive": {
        "keep": {"primary_delta_rel": 0.001},
        "external": {"paper_depth": "P3", "docs_depth": "D3",
                     "github_impl": True, "github_ecosystem": True,
                     "seek_plateau_rounds": 1},  # 1 轮撞墙即找
        "tier_start": "D", "runtime": "innovate",
    },
    "explore": {
        "external": {"paper_depth": "P2", "docs_depth": "D2",
                     "github_impl": True, "github_ecosystem": True,
                     "seek_plateau_rounds": 5},  # 同 innovate（同 external profile）
        "goal": {"policy": "all_in_scope"},
        "tier_start": "B", "runtime": "explore",
    },
    "auto": {
        "external": {"paper_depth": "P1", "docs_depth": "D1",
                     "github_impl": False, "github_ecosystem": True,
                     "seek_plateau_rounds": 7},  # 占位：运行时由 effective_mode 重选
        "early_stop": {"patience": 3},
        "tier_start": "B", "runtime": "optimize",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并；override 覆盖 base，dict 递归、其余直覆盖。返回新 dict。"""
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def default_for_mode(mode: str) -> dict[str, Any]:
    """exploration_mode（6 档）→ 完整 bundle = deep_merge(_BASE, _MODE_DEFAULTS[mode])。

    auto 档返回其起步 bundle（effective_mode=optimize）；运行时由 resolve_exploration
    用 auto.effective_mode 重选。未知 mode → optimize 兜底（防 typo）。
    """
    return _deep_merge(_BASE, _MODE_DEFAULTS.get(mode, _MODE_DEFAULTS["optimize"]))


__all__ = ["default_for_mode"]
