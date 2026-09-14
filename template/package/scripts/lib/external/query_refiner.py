"""B2: query 改写层 + LLM 增强。

输入:原始 query + ctx
输出:3-5 个候选查询 (awesome-pytorch / awesome-image-classification / ...)

启发式层 (无 LLM):
- framework name → awesome-<name>
- task name → awesome-<task>

LLM 层 (可选): build_llm_query_prompt → 解析回 list
失败 → 回退上一层输出。

附带 format_validation_feedback(把 ValidationVerdict 转 prompt 反馈,reflect.py 用)。
"""
from __future__ import annotations

import os
import re
from typing import Callable, Iterable

from lib.external.query_validator import ValidationVerdict


_FRAMEWORK_TOKENS = (
    "pytorch", "tensorflow", "jax", "lightgbm", "xgboost",
    "sklearn", "scikit-learn", "keras", "fastai",
)
_TASK_TOKENS = (
    "image-classification", "object-detection", "semantic-segmentation",
    "self-supervised", "nlp", "reinforcement-learning", "time-series",
    "few-shot", "tabular", "anomaly-detection",
)
_QUERY_REFINER_ENABLED_ENV = "NN_QUERY_REFINER_ENABLED"


def _heuristic_layer(query: str, ctx: dict | None) -> list[str]:
    text = ((ctx or {}).get("rationale", "") + " " + (query or "")).lower()
    out: list[str] = []
    for tok in _FRAMEWORK_TOKENS:
        if tok in text:
            out.append(f"awesome-{tok}")
    for tok in _TASK_TOKENS:
        if tok in text:
            out.append(f"awesome-{tok}")
    return out


def _llm_layer(query: str, ctx: dict | None, llm_query_fn: Callable[[str], str] | None) -> list[str]:
    if llm_query_fn is None:
        return []
    prompt = (
        f"Given the original paper/search query \"{query}\",\n"
        f"and the context rationale \"{(ctx or {}).get('rationale', '')}\",\n"
        f"output 3-5 GitHub awesome-list candidate query names.\n"
        f"Examples: awesome-pytorch, awesome-self-supervised-learning.\n"
        f"Output one per line, no prefix dash, the output itself."
    )
    try:
        raw = llm_query_fn(prompt) or ""
    except Exception:
        return []
    out: list[str] = []
    for line in raw.splitlines():
        cleaned = line.strip().lstrip("-*• ").strip()
        if not cleaned:
            continue
        # 仅保留 awesome-* 形式 或单 token 任务名
        if cleaned.startswith("awesome-") or re.match(r"^[a-z][a-z0-9-]+$", cleaned):
            out.append(cleaned)
    return out


def rewrite_for_awesome(
    query: str,
    *,
    ctx: dict | None = None,
    llm_query_fn: Callable[[str], str] | None = None,
) -> list[str]:
    """B2: 多路输出,启发式先,LLM 后;失败回退上一层。

    Returns:
        list[str] — 候选查询列表(最多 5 项)
    """
    if os.environ.get(_QUERY_REFINER_ENABLED_ENV) == "0":
        return [query] if query else []
    seen: list[str] = []
    seen_set: set[str] = set()

    def _add(items: Iterable[str]) -> None:
        for it in items:
            it = (it or "").strip()
            if it and it not in seen_set:
                seen.append(it)
                seen_set.add(it)

    _add(_heuristic_layer(query, ctx))
    _add(_llm_layer(query, ctx, llm_query_fn))
    if not seen and query:
        seen.append(query)
    return seen[:5]


def format_validation_feedback(
    verdict: ValidationVerdict,
    *,
    f1_scenarios: list[str] | None = None,
) -> str:
    """把 ValidationVerdict 转成可附加到 prompt 的 markdown 块。

    Args:
        verdict: validate_query_alignment 的输出
        f1_scenarios: 业务仓 F1 manifest scenario_ids（可选；append 一行 hint）

    Returns:
        verdict.ok=True → 空串
        verdict.ok=False → markdown 反馈块（errors / warnings / rules / F1 hint）
    """
    if verdict.ok:
        return ""

    lines: list[str] = [
        "## 上次 query 被拒（请根据下面问题重写）",
        "",
    ]
    for i, err in enumerate(verdict.errors, 1):
        lines.append(f"{i}. {err}")
    if verdict.warnings:
        lines.extend(["", "### 警告（非阻塞）"])
        for w in verdict.warnings:
            lines.append(f"- {w}")
    lines.extend(
        [
            "",
            "### 怎么写好（rules）",
            "- DO: 至少 1 个 F1 scenario_id token；用具体方法/算法名；总长 ≤ 200",
            "- DON'T: 用 'method/approach/analysis/study' 通用词；与 F1 scenario_ids 无重叠",
        ]
    )
    if f1_scenarios:
        lines.append(f"\nF1 scenarios: {f1_scenarios}")
    return "\n".join(lines)
