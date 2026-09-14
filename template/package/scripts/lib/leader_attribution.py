"""Leader vs current 差距归因（Phase 1 内嵌）。

读 keeper（历史最好）和 current（本轮）的 config，diff primary_keys_changed：
- missing_in_current：leader 有但 current 没有（直接 actionable）
- extra_in_current：current 有但 leader 没有（可能冒险）
- confidence：leader 和 current 架构差异大时降为 low
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# primary keys 列表（与 innovation_fingerprint 一致）
_PRIMARY_KEYS = ("MODEL_ARCH", "LOSS", "OPTIMIZER", "SCHEDULER", "MIXUP_ALPHA",
                 "EMA_DECAY", "ACTIVATION")

# 当 MODEL_ARCH 两个值的最长公共子串（>=该长度）时认为同族架构，confidence=high。
# 经验值 5：``ema_coordconv`` / ``sgdr10_coordconv`` 共享 ``coordconv``(9 字符)
# → 同族 high；而 ``wrn_cnn`` / ``transformer_cnn`` 仅共享 ``cnn``(3 字符) → 不同族 low。
_ARCH_FAMILY_MIN_LCS = 5


def _longest_common_substring(a: str, b: str) -> int:
    """返回 ``a``、``b`` 的最长公共子串长度（无依赖，纯 Python）。"""
    if not a or not b:
        return 0
    m, n = len(a), len(b)
    if m < n:
        a, b = b, a
        m, n = n, m
    best = 0
    prev = [0] * (n + 1)
    curr = [0] * (n + 1)
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                curr[j] = prev[j - 1] + 1
                if curr[j] > best:
                    best = curr[j]
            else:
                curr[j] = 0
        prev, curr = curr, prev
    return best


@dataclass
class LeaderAttribution:
    leader_exp_dir: str
    leader_metric_value: float
    current_metric_value: float
    gap: float                                # leader - current（正 = 当前落后）
    missing_in_current: list[str] = field(default_factory=list)
    extra_in_current: list[str] = field(default_factory=list)
    confidence: str = "high"

    def to_dict(self) -> dict[str, Any]:
        return {
            "leader_exp_dir": self.leader_exp_dir,
            "leader_metric_value": self.leader_metric_value,
            "current_metric_value": self.current_metric_value,
            "gap": self.gap,
            "missing_in_current": self.missing_in_current,
            "extra_in_current": self.extra_in_current,
            "confidence": self.confidence,
        }


def _read_config(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def compute_leader_attribution(
    leader_config_path: Path,
    current_config_path: Path,
    leader_metric: float,
    current_metric: float,
    primary_keys: tuple[str, ...] = _PRIMARY_KEYS,
) -> LeaderAttribution:
    leader_cfg = _read_config(Path(leader_config_path))
    current_cfg = _read_config(Path(current_config_path))

    missing: list[str] = []
    extra: list[str] = []
    confidence = "high"
    for k in primary_keys:
        lv = leader_cfg.get(k)
        cv = current_cfg.get(k)
        arch_mismatch = False
        if lv and cv and lv != cv:
            if k == "MODEL_ARCH":
                # 同族判定：最长公共子串长度 ≥ 阈值即视为同族（high）；
                # 否则为不同族（low → 归因置信度不可信）。
                if _longest_common_substring(str(lv), str(cv)) < _ARCH_FAMILY_MIN_LCS:
                    arch_mismatch = True
                    confidence = "low"
        if lv and not cv:
            # Leader had it; current completely lacks the key.
            missing.append(f"{k}={lv}")
        if cv and not lv:
            # Current has it; leader never did (novel experimental choice).
            extra.append(f"{k}={cv}")
        if lv and cv and lv != cv:
            # Both sides set it but with different values → leader's setting is
            # not preserved in current; the leader's value is what's "missing"
            # from current (actionable for回滚/对齐 leader).
            missing.append(f"{k}={lv}")
            extra.append(f"{k}={cv}")
            if arch_mismatch:
                # Surface the major-arch mismatch explicitly so consumers can
                # see at a glance that confidence dropped due to family change.
                extra[-1] += f" [arch-mismatch, leader={lv}]"

    if not leader_cfg or not current_cfg:
        confidence = "low"

    return LeaderAttribution(
        leader_exp_dir=str(leader_config_path),
        leader_metric_value=leader_metric,
        current_metric_value=current_metric,
        gap=leader_metric - current_metric,
        missing_in_current=missing,
        extra_in_current=extra,
        confidence=confidence,
    )
