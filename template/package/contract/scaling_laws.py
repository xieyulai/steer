"""经验律 — M2 反射上下文机制。

模板内置 4 条通用经验律（不绑任何具体项目/业务域）。业务仓可
`SCALING_LAW_OVERRIDE` 字典覆盖/追加。

律的设计原则：
    1. 纯函数（无状态、无 IO），业务仓 override 也是纯函数
    2. 缺字段优雅降级（不抛错，返回 None 或不输出该 cfg 键）
    3. 跨场景 delta 提示：当历史 best 在不同 cap 时，给出 ratio 建议

通用律的物理/经验依据：
    - encoder_hidden ∝ √bits：信息瓶颈 → 表达力（开方律，避免过/欠配）
    - num_heads 随 hidden 平滑涨（head_dim 16-32 最佳）
    - ffn_ratio 在小 hidden 时 2，大 hidden 时 4（参数量平衡）
    - backbone 按 num_classes 阶梯：≥100 → 至少 resnet18
"""
from __future__ import annotations

import math
from typing import Any, Callable


# 模板内置 4 条通用律
def _law_encoder_hidden(cap: dict[str, Any]) -> int | None:
    bits = cap.get("bits")
    if bits is None or bits <= 0:
        return None
    return int(math.sqrt(bits) * 8)


def _law_num_heads(cap: dict[str, Any]) -> int | None:
    hidden = _law_encoder_hidden(cap)
    if hidden is None:
        return None
    # head_dim 控制在 16-32，最少 2 head 最多 8
    return max(2, min(8, hidden // 16))


def _law_ffn_ratio(cap: dict[str, Any]) -> int | None:
    bits = cap.get("bits")
    if bits is None:
        return None
    return 4 if bits >= 256 else 2


def _law_backbone(cap: dict[str, Any]) -> str | None:
    nc = cap.get("num_classes")
    if nc is None or nc < 1:
        return None
    if nc >= 100:
        return "resnet50"
    if nc >= 10:
        return "resnet18"
    return "mlp"


SCALING_LAWS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "encoder_hidden": _law_encoder_hidden,
    "num_heads": _law_num_heads,
    "ffn_ratio": _law_ffn_ratio,
    "backbone": _law_backbone,
}


# 业务仓可填：覆盖或追加模板默认律
SCALING_LAW_OVERRIDE: dict[str, Callable[[dict[str, Any]], Any]] = {}


def apply(
    cap: dict[str, Any],
    history_best_cap: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """根据本场景 capacity + 历史 best capacity 算推荐 cfg 值。

    返回 {"cfg_key": recommended_value, ...}。
    跨场景 delta 提示：若 history_best_cap 与 cap 差 >1.5x，
    在结果里加 "delta_<field>_ratio" 字段。
    """
    laws = {**SCALING_LAWS, **SCALING_LAW_OVERRIDE}
    rec: dict[str, Any] = {}
    for key, fn in laws.items():
        try:
            v = fn(cap)
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as e:
            # optional: 业务仓 override 律可能不识本场景字段，优雅跳过
            print(f"[scaling_laws] skip law {key!r} for cap={cap}: {e}", file=__import__("sys").stderr)
            continue
        if v is not None:
            rec[key] = v

    # 跨场景 delta 提示
    if history_best_cap:
        for dim in ("bits", "num_classes", "input_dim"):
            cur = cap.get(dim)
            hist = history_best_cap.get(dim)
            if cur and hist and isinstance(cur, (int, float)) and isinstance(hist, (int, float)) and hist > 0:
                ratio = cur / hist
                if ratio >= 1.5 or ratio <= 0.67:
                    rec[f"delta_{dim}_ratio"] = round(ratio, 2)

    return rec
