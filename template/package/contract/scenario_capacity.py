"""场景容量登记 — M1 反射上下文机制。

模板默认实现。业务仓可填 `SCENARIO_CAPACITY` 表覆盖默认。
`list_capacity(scenario_id)` 永远不抛错（找不到返回空 dict），
让 reflect Phase 0.5 在"业务仓没填表"时优雅降级（跳过 M1 段）。

字段语义（业务仓填哪个用哪个，缺省视为 None）：
    - bits: 信息瓶颈（比特预算 / 互信息上界）
    - input_dim: 输入维度（展平后）
    - num_classes: 类别数（分类任务）
    - seq_len: 序列长度（时序/序列任务）
    - sample_count: 训练样本数
    - task_kind: 任务类型（compression / classification / cl / regression / generation）
"""
from __future__ import annotations

from typing import Any


# 业务仓可填：scenario_id → {字段: 值}
# 空 dict = 业务仓没填（reflect 跳 M1 段，零成本）
SCENARIO_CAPACITY: dict[str, dict[str, Any]] = {}

# 业务仓可设 True 关闭 WARN（不推荐；保留作 opt-out）
SCENARIO_CAPACITY_OPT_OUT: bool = False


def list_capacity(scenario_id: str) -> dict[str, Any]:
    """返回本场景的"规模参数"。永远不抛错。

    匹配规则：
    1. 精确匹配 scenario_id
    2. 兜底：按 "前缀_" 切分，找最长的 key prefix 匹配（如
       "compress_256b_r2_31_random_quant_deploy" 命中 "compress_256b"）

    返回 dict：缺字段 = None（reflect 渲染时跳过该字段）
    """
    if not scenario_id:
        return _empty_capacity()
    cap = SCENARIO_CAPACITY.get(scenario_id)
    if cap is not None:
        return _normalize(cap)
    # 前缀兜底匹配：按 `_` 切，从最长的前缀试到最短
    parts = scenario_id.split("_")
    for i in range(len(parts), 0, -1):
        prefix = "_".join(parts[:i])
        cap = SCENARIO_CAPACITY.get(prefix)
        if cap is not None:
            return _normalize(cap)
    return _empty_capacity()


def _empty_capacity() -> dict[str, Any]:
    return {
        "bits": None,
        "input_dim": None,
        "num_classes": None,
        "seq_len": None,
        "sample_count": None,
        "task_kind": None,
    }


def _normalize(cap: dict[str, Any]) -> dict[str, Any]:
    """统一字段名，缺字段填 None。"""
    out = _empty_capacity()
    for k, v in cap.items():
        if k in out:
            out[k] = v
    return out


def check_scenario_capacity(scenario_id: str, opt_out: bool = False) -> list[str]:
    """P2 preflight gate：业务仓忘填 SCENARIO_CAPACITY 时返回 WARN 列表。

    默认 WARN（不阻断），让 reflect Phase 0.5 注入 stderr 提醒业务仓。
    业务仓可设 SCENARIO_CAPACITY_OPT_OUT=True 关闭（不推荐）。
    """
    if opt_out or SCENARIO_CAPACITY_OPT_OUT:
        return []
    # opt_out 参数也允许单次调用关掉
    sid = scenario_id or "（未指定 scenario_id）"
    # 检查：表空 或 找不到匹配
    has_match = False
    if SCENARIO_CAPACITY:
        # 用 list_capacity 的匹配规则
        if scenario_id and SCENARIO_CAPACITY.get(scenario_id):
            has_match = True
        else:
            for prefix_len in range(
                len(scenario_id.split("_")), 0, -1
            ) if scenario_id else []:
                prefix = "_".join(scenario_id.split("_")[:prefix_len])
                if SCENARIO_CAPACITY.get(prefix):
                    has_match = True
                    break
    if has_match:
        return []
    return [
        f"[SCENARIO_CAPACITY] ⚠ 本场景 {sid!r} 在 SCENARIO_CAPACITY 表中未登记。"
        f"reflect 将看不到 M1（容量卡）和 M2（经验律）段。"
        f"业务仓零代码即可获益：在 contract/scenario_capacity.py 的 SCENARIO_CAPACITY 表中加一行，"
        f"格式 {{'bits': ..., 'input_dim': ..., 'num_classes': ..., ...}}。"
        f"（设 SCENARIO_CAPACITY_OPT_OUT=True 关闭此警告）"
    ]

