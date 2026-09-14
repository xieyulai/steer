"""Fingerprint 跨轮同质化检测。

每次 reflect 时算一次，看过去 N 轮 fingerprint 重复率：
- 同一 primary swap 占比高 → agent 在原地打转，触发 downshift 建议
- 同一 Tier 占比高 → 当前档已饱和，触发 downshift 建议
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


# 默认阈值（nn-config 可覆盖）
DEFAULT_PRIMARY_REPEAT_THRESHOLD = 0.6
DEFAULT_TIER_REPEAT_THRESHOLD = 0.8
DEFAULT_WINDOW = 5

# Tier 降档映射（不可降到 E——E 需 NN_RELAUNCH）
_TIER_DOWNSHIFT = {
    "A": "A",  # A 已是最低，不降
    "B": "A",
    "C": "B",
    "D": "C",
    "E": "D",
}


@dataclass
class DiversityReport:
    """Fingerprint 多样性报告。"""

    window: int
    primary_swap_repeat_pct: float
    tier_repeat_pct: float
    dominant_swap: str
    downshift_recommended: bool
    downshift_target_tier: str
    n_unique_swaps: int
    n_unique_tiers: int
    swap_counts: dict[str, int] = field(default_factory=dict)
    tier_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "window": self.window,
            "primary_swap_repeat_pct": self.primary_swap_repeat_pct,
            "tier_repeat_pct": self.tier_repeat_pct,
            "dominant_swap": self.dominant_swap,
            "downshift_recommended": self.downshift_recommended,
            "downshift_target_tier": self.downshift_target_tier,
            "n_unique_swaps": self.n_unique_swaps,
            "n_unique_tiers": self.n_unique_tiers,
            "swap_counts": self.swap_counts,
            "tier_counts": self.tier_counts,
        }


def _extract_swap(fp: Any) -> str:
    """从 InnovationFingerprintResult-like 提取 primary swap 描述。

    格式："{key}={old}→{new}"（如 "MODEL_ARCH=cnn→coordconv_cnn"）
    若无 primary_keys_changed → "(no primary swap)"
    """
    pkc = getattr(fp, "primary_keys_changed", {}) or {}
    if not pkc:
        return "(no primary swap)"
    key = next(iter(pkc.keys()))
    val = pkc[key]
    if not val:
        return "(no primary swap)"
    swap = str(val[0])
    return f"{key}={swap}"


def _extract_tier(fp: Any) -> str:
    return str(getattr(fp, "primary_tier", "") or "?")


def _downshift_target(current_tier: str) -> str:
    return _TIER_DOWNSHIFT.get(current_tier, current_tier)


def compute_diversity(
    recent_fingerprints: Iterable[Any],
    window: int = DEFAULT_WINDOW,
    primary_repeat_threshold: float = DEFAULT_PRIMARY_REPEAT_THRESHOLD,
    tier_repeat_threshold: float = DEFAULT_TIER_REPEAT_THRESHOLD,
) -> DiversityReport:
    """算多样性报告。"""
    fps = list(recent_fingerprints)
    if window > 0:
        fps = fps[-window:]
    n = len(fps)
    if n == 0:
        return DiversityReport(
            window=0,
            primary_swap_repeat_pct=0.0,
            tier_repeat_pct=0.0,
            dominant_swap="(no primary swap)",
            downshift_recommended=False,
            downshift_target_tier="A",
            n_unique_swaps=0,
            n_unique_tiers=0,
        )

    from collections import Counter
    raw_swap_counts = Counter(_extract_swap(fp) for fp in fps)
    tier_counts = Counter(_extract_tier(fp) for fp in fps)

    # 过滤掉 "(no primary swap)" 哨兵：routine 标量微调不应算作「同一 swap 重复」
    swap_counts = Counter(
        {k: v for k, v in raw_swap_counts.items() if k != "(no primary swap)"}
    )

    if swap_counts:
        dominant_swap, dominant_count = swap_counts.most_common(1)[0]
        primary_repeat = dominant_count / n
    else:
        dominant_swap = "(no primary swap)"
        primary_repeat = 0.0
    dominant_tier, dominant_tier_count = tier_counts.most_common(1)[0]
    tier_repeat = dominant_tier_count / n

    # 降档触发条件：
    # - primary_repeat ≥ 阈值（同一 primary swap 占比过高）
    # - 或 tier_repeat ≥ 阈值 且 n_unique_swaps == 1（所有 real swap 全是同一档）
    # 单独 tier 重复不算 downshift——换不同的 swap 仍在当前档打转不算饱和
    downshift = (primary_repeat >= primary_repeat_threshold
                 or (tier_repeat >= tier_repeat_threshold
                     and len(swap_counts) == 1))
    downshift_target = _downshift_target(dominant_tier) if downshift else "A"

    return DiversityReport(
        window=n,
        primary_swap_repeat_pct=primary_repeat,
        tier_repeat_pct=tier_repeat,
        dominant_swap=dominant_swap,
        downshift_recommended=downshift,
        downshift_target_tier=downshift_target,
        n_unique_swaps=len(swap_counts),
        n_unique_tiers=len(tier_counts),
        swap_counts=dict(swap_counts),
        tier_counts=dict(tier_counts),
    )
