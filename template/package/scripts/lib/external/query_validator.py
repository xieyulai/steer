"""paper_query 校验：3 道关卡（hard fail）+ ValidationVerdict dataclass。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_QUERY_MAX_LEN = 200
_GENERIC_WORD_DENSITY_MAX = 0.30

_STOPWORDS = frozenset({"the", "and", "for", "with", "from", "this", "that"})

# 项目无关：通用查询词（命中此表的词越多，query 越泛）
_GENERIC_QUERY_WORDS = frozenset({
    "method", "approach", "analysis", "study", "technique",
    "framework", "investigation", "exploration", "examination",
    "research", "paper", "algorithm",
})


@dataclass(frozen=True)
class ValidationVerdict:
    """3 道校验的结果。任一 errors 非空 → ok=False（hard fail）。"""

    ok: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def summary(self) -> str:
        if self.ok:
            n = len(self.warnings)
            if n:
                return f"pass ({n} warning{'s' if n != 1 else ''})"
            return "pass"
        return f"fail: {'; '.join(self.errors)}"


def _tokenize(text: str) -> set[str]:
    """≥3 字符的小写 token，去停用词。"""
    return {t for t in re.findall(r"\b\w{3,}\b", text.lower())} - _STOPWORDS


def validate_query_alignment(
    paper_query: str,
    *,
    f1_scenarios: list[str],
    metric_key: str = "",  # noqa: ARG001 软建议用，不进硬规则
) -> ValidationVerdict:
    """3 道关卡；任一 hard fail → ok=False。

    Rules:
    1. F1 token overlap ≥ 1（=0 → fail；=1 → warn；无 F1 → 跳过 Rule 1）
    2. 长度 ≤ 200
    3. 通用词密度 ≤ 30%（去停用词后）
    """
    errors: list[str] = []
    warnings: list[str] = []
    q = (paper_query or "").strip()
    if not q:
        return ValidationVerdict(ok=False, errors=("query 为空",))

    q_tokens = _tokenize(q) - _GENERIC_QUERY_WORDS

    # Rule 1: F1 token overlap（exact token 集合交集；spec §7.1）
    if f1_scenarios:
        f1_tokens: set[str] = set()
        for s in f1_scenarios:
            f1_tokens.update(_tokenize(s))
        f1_tokens -= _GENERIC_QUERY_WORDS
        if f1_tokens:  # f1_tokens 为空时跳过（与无 F1 同语义）
            overlap = q_tokens & f1_tokens
            if not overlap:
                errors.append(
                    f"query 与 F1 manifest scenario_ids 无 token 重叠；"
                    f"query 关键词={sorted(q_tokens)[:5]}，"
                    f"F1 关键词={sorted(f1_tokens)[:5]}"
                )
            elif len(overlap) == 1:
                warnings.append(
                    f"query 与 F1 仅 1 个 token 重叠（弱相关）：{sorted(overlap)}"
                )

    # Rule 2: 长度 ≤ 200
    if len(q) > _QUERY_MAX_LEN:
        errors.append(f"query 长度 {len(q)} > {_QUERY_MAX_LEN}")

    # Rule 3: 通用词密度 ≤ 30%
    all_tokens = _tokenize(q)
    if all_tokens:
        generic_count = len(all_tokens & _GENERIC_QUERY_WORDS)
        density = generic_count / len(all_tokens)
        if density > _GENERIC_WORD_DENSITY_MAX:
            errors.append(
                f"query 通用词占比 {density:.0%} > {_GENERIC_WORD_DENSITY_MAX:.0%}（{sorted(all_tokens & _GENERIC_QUERY_WORDS)}）"
            )

    return ValidationVerdict(
        ok=len(errors) == 0,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )
