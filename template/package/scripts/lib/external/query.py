from __future__ import annotations

import json
import re
from typing import Any, Callable, Protocol

from lib.innovation_audit import scan_text_for_routine

_TIER_PREFIX_RE = re.compile(
    r"^(?:\[?\s*)?tier\s*[A-Ea-e]\s*[:：\]\-—]?\s*",
    re.IGNORECASE,
)

_NN_SYMBOL_RE = re.compile(
    r"(?:torch\.nn\.|nn\.)(CrossEntropyLoss|MSELoss|BCEWithLogitsLoss|NLLLoss|L1Loss|SmoothL1Loss)",
    re.IGNORECASE,
)

_CATALOG_EXACT_ARXIV_RE = re.compile(
    r"(?:arxiv:\s*\d{4}\.\d{4,5}|arXiv:\s*\d{4}\.\d{4,5})",
    re.IGNORECASE,
)

# 方法名 token 通用词停用表：短/泛化 ML 词，单独作查询词无辨识度
# （probe 实证：coordatt_se_cnn → 滤掉 se/cnn → 单辨识 token coordatt 命中原论文）
_METHOD_TOKEN_STOP = frozenset(
    "cnn net v1 v2 v3 v4 layer layers block blocks base model models se att self "
    "custom my test exp new old cls head tail ff proj bn drop module impl torch "
    "type kind learner objective loss optim scheduler dataset loader".split()
)

# fingerprint.reasons 形如 "new_register:learner:coordatt_se_cnn"
_NEW_REGISTER_RE = re.compile(r"new_register:[^:]+:([A-Za-z0-9_\-]+)")
# 方法名拆 token：下划线/连字符/空格 + camelCase/PascalCase
_METHOD_TOKEN_RE = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)|\d+")


class _QueryContext(Protocol):
    rationale: str
    phase2_focus: str
    fingerprint: dict[str, Any] | None
    task_domain: str


def _looks_like_exact_paper_id(q: str) -> bool:
    q = str(q or "").strip()
    if not q:
        return False
    if _CATALOG_EXACT_ARXIV_RE.search(q):
        return True
    return "arxiv:" in q.lower() and len(q) < 80


def _source_text(ctx: _QueryContext) -> str:
    text = (ctx.rationale or "").strip()
    if not text:
        text = (ctx.phase2_focus or "").strip()
    return text


def _paper_query_from_fingerprint(fingerprint: dict[str, Any] | None) -> str:
    if not fingerprint:
        return ""
    parts: list[str] = []
    for hit in fingerprint.get("catalog_hits") or []:
        pq = str(hit.get("paper_query") or "").strip()
        if pq and pq not in parts:
            parts.append(pq)
    if not parts:
        return ""
    return " ".join(parts)[:120]


def _method_names_from_fingerprint(fingerprint: dict[str, Any] | None) -> list[str]:
    """从 fingerprint 的 new_register / MODEL_ARCH 抽原始方法名（未拆分）。"""
    if not fingerprint:
        return []
    names: list[str] = []
    for reason in fingerprint.get("reasons") or []:
        m = _NEW_REGISTER_RE.search(str(reason))
        if m:
            names.append(m.group(1))
    pkc = fingerprint.get("primary_keys_changed") or {}
    for v in pkc.get("MODEL_ARCH") or []:
        names.append(str(v))
    return names


def _method_tokens_from_fingerprint(fingerprint: dict[str, Any] | None) -> str:
    """从 fingerprint 的 new_register / MODEL_ARCH 抽辨识方法 token 做查询词。

    未收录方法/自定义方法不在已知方法目录 → catalog_hits 空 → 旧逻辑退回整段项目描述
    （项目描述当查询词 → 全 provider 0 hit）。这里补上：拆方法名、滤通用词、
    取首个辨识 token（probe 实证：单辨识 token 三路命中最好）。

    全部 token 都被通用词停用表滤掉时返回 ''（走原兜底，不吐垃圾）。
    """
    for name in _method_names_from_fingerprint(fingerprint):
        for tok in (t.lower() for t in _METHOD_TOKEN_RE.findall(str(name))):
            if len(tok) >= 3 and tok not in _METHOD_TOKEN_STOP:
                return tok  # 首个辨识 token（probe：单 token 跨 provider 命中最好）
    return ""


_LLM_QUERY_LABELS = frozenset(("query", "查询", "method", "方法", "方法名", "q"))


def build_llm_paper_query_prompt(ctx: _QueryContext) -> str:
    """构造 LLM 查询生成 prompt：方法名 + 规则 token + 领域 → seminal 论文检索词。"""
    fp = getattr(ctx, "fingerprint", None) or {}
    names = _method_names_from_fingerprint(fp)
    rule_tok = _method_tokens_from_fingerprint(fp)
    domain = str(getattr(ctx, "task_domain", "") or "").strip()
    tier = str(getattr(ctx, "tier", "") or "").strip()
    depth = str(getattr(ctx, "innovation_depth", "") or "").strip()
    return (
        "你是学术检索查询生成器。给定自定义方法名 + 任务领域，输出 **1 行 3-6 词英文** 检索查询，"
        "用于在 arXiv / Google Scholar 找到该方法的 seminal（原始）论文。\n\n"
        f"方法名: {', '.join(names) if names else '(无)'}\n"
        f"规则拆出的 token: {rule_tok or '(无)'}\n"
        f"任务领域: {domain or '(未知)'}\n"
        f"Tier/depth: {tier or '?'}/{depth or '?'}\n\n"
        "规则：\n"
        "- 展开缩写为全称（coordatt→coordinate attention；senet/se→squeeze excitation；resnet→residual network）\n"
        "- 3-6 词，英文小写，无引号无 markdown 无解释，只输出查询本身\n"
        "- 瞄准 seminal 原论文，不是应用论文\n\n"
        "示例：\n"
        "coordatt_se_cnn → coordinate attention mobile network\n"
        "senet_se → squeeze excitation network\n\n"
        "查询:"
    )


def parse_llm_paper_query(raw: str) -> str:
    """解析 LLM 输出为查询字符串；无法解析返回 ''（让上层回退规则层）。"""
    s = str(raw or "").strip()
    if not s:
        return ""
    if s.startswith("```"):  # markdown fence
        s = s.split("```", 2)[1] if s.count("```") >= 2 else s
        if s.lower().startswith("json"):
            s = s[4:]
        s = s.strip()
    if s.startswith("{"):  # {"query": "..."}
        try:
            obj = json.JSONDecoder().raw_decode(s[s.find("{"):])[0]
            if isinstance(obj, dict):
                s = str(obj.get("query") or obj.get("q") or "").strip()
        except json.JSONDecodeError:
            pass
    s = s.split("\n", 1)[0].strip().strip("`'\"").strip()  # 首行 + 去引号
    if len(s) < 2 or len(s) > 120:
        return ""
    if s.lower().rstrip(":：") in _LLM_QUERY_LABELS:  # LLM 复述标签
        return ""
    return s


def _docs_symbols_from_fingerprint(fingerprint: dict[str, Any] | None) -> list[str]:
    if not fingerprint:
        return []
    symbols: list[str] = []
    seen: set[str] = set()
    for hit in fingerprint.get("catalog_hits") or []:
        for sym in hit.get("docs_symbols") or []:
            s = str(sym).strip()
            if s and s not in seen:
                seen.add(s)
                symbols.append(s)
    return symbols


def build_paper_query(ctx: _QueryContext) -> str:
    domain = str(getattr(ctx, "task_domain", "") or "").strip()
    fp = getattr(ctx, "fingerprint", None)
    fp_q = _paper_query_from_fingerprint(fp)
    if fp_q and domain and _looks_like_exact_paper_id(fp_q):
        return domain[:120]
    if fp_q:
        return fp_q[:120]
    # catalog 未命中：LLM 增强（总触发；展开缩写、加领域、瞄 seminal 论文）。
    # 任何失败（异常/解析空）静默回退规则层，绝不劣化。
    llm_fn: Callable[[str], str] | None = getattr(ctx, "llm_query_fn", None)
    if llm_fn:
        try:
            q = parse_llm_paper_query(llm_fn(build_llm_paper_query_prompt(ctx)))
            if q:
                return q[:120]
        except Exception:
            pass
    # 规则层：从方法名抽辨识 token（未收录方法），别退回整段项目描述
    method_q = _method_tokens_from_fingerprint(fp)
    if method_q:
        return method_q[:120]
    if domain:
        return domain[:120]
    text = _source_text(ctx)
    text = _TIER_PREFIX_RE.sub("", text).strip()
    return text[:120]


def build_docs_symbols(ctx: _QueryContext) -> list[str]:
    fp_symbols = _docs_symbols_from_fingerprint(getattr(ctx, "fingerprint", None))
    if fp_symbols:
        return fp_symbols

    text = "\n".join(filter(None, [ctx.rationale, ctx.phase2_focus]))
    if not text.strip():
        return []

    symbols: list[str] = []
    seen: set[str] = set()

    def add(sym: str) -> None:
        s = sym.strip()
        if s and s not in seen:
            seen.add(s)
            symbols.append(s)

    for match in _NN_SYMBOL_RE.finditer(text):
        add(match.group(1))

    if re.search(r"\btimm\b", text, re.IGNORECASE):
        add("timm")
    if re.search(r"torchvision", text, re.IGNORECASE):
        add("torchvision")
    if re.search(r"\bkornia\b", text, re.IGNORECASE):
        add("kornia")

    if not symbols and scan_text_for_routine(text):
        for match in _NN_SYMBOL_RE.finditer(text):
            add(match.group(1))
        if re.search(r"\btimm\b", text, re.IGNORECASE):
            add("timm")
        if re.search(r"torchvision", text, re.IGNORECASE):
            add("torchvision")
        if re.search(r"\bkornia\b", text, re.IGNORECASE):
            add("kornia")

    return symbols
