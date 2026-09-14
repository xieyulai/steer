from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from lib.external.config import ExternalEvidenceConfig
from lib.external.models import (
    ExternalPlan,
    mode_to_external,
)
from lib.external.query import build_docs_symbols, build_paper_query

# (paper_depth, docs_depth, github_impl, github_ecosystem)
# RDDN migrate (T2)：5 tier × 4 depth = 20。
# derived←旧 extend（调度/搜索类），different←旧 novel（形式创新/AutoML/自研），
# novel=different 的镜像（T2 dormant，T3 升级成 L4 背书专属）。E 行是占位——
# build_external_plan 里 E tier 先短路 off_plan(tier_e)，到不了 _matrix_lookup，
# 这里只为凑齐 20 条让矩阵形状自洽（contract：_DEPTH_MATRIX 必须 5×4=20）。
_DEPTH_MATRIX: dict[tuple[str, str], tuple[str, str, bool, bool]] = {
    ("A", "routine"): ("P0", "D2", False, False),
    ("A", "derived"): ("P1", "D0", False, False),
    ("A", "different"): ("P2", "D1", False, True),
    ("A", "novel"): ("P2", "D1", False, True),
    ("B", "routine"): ("P0", "D2", False, False),
    ("B", "derived"): ("P2", "D0", True, False),
    ("B", "different"): ("P2", "D1", True, True),
    ("B", "novel"): ("P2", "D1", True, True),
    ("C", "routine"): ("P0", "D2", False, False),
    ("C", "derived"): ("P2", "D0", True, False),
    ("C", "different"): ("P2", "D1", True, True),
    ("C", "novel"): ("P2", "D1", True, True),
    ("D", "routine"): ("P0", "D1", False, False),
    ("D", "derived"): ("P2", "D0", True, False),
    ("D", "different"): ("P2", "D1", True, True),
    ("D", "novel"): ("P2", "D1", True, True),
    ("E", "routine"): ("P0", "D0", False, False),
    ("E", "derived"): ("P0", "D0", False, False),
    ("E", "different"): ("P0", "D0", False, False),
    ("E", "novel"): ("P0", "D0", False, False),
}

_PAPER_DEEPEN: dict[str, str] = {"P2": "P3"}


@dataclass
class RouterContext:
    tier: str  # A-E letter
    innovation_depth: str  # routine|derived|different|novel (effective for routing)
    gate: str  # run:R* | skip:* | manual:reflect
    beat_best: bool
    routine_mislabel: bool
    not_attested_extend: bool
    reflect_skipped: bool
    rationale: str = ""
    phase2_focus: str = ""
    config: ExternalEvidenceConfig | None = None
    fingerprint: dict | None = None
    agent_depth: str = ""
    fingerprint_depth: str = ""
    plateau_active: bool = False
    task_domain: str = ""
    # LLM 查询增强回调（reflect 注入 _call_agent）；catalog miss 时用于展开缩写、
    # 加领域、瞄 seminal 论文。None = 纯规则路径（v1 行为）。
    llm_query_fn: Callable[[str], str] | None = None


def _cfg(ctx: RouterContext) -> ExternalEvidenceConfig:
    return ctx.config or ExternalEvidenceConfig()


def _round_state(ctx: RouterContext) -> dict[str, object]:
    state: dict[str, object] = {
        "tier": ctx.tier.upper(),
        "innovation_depth": ctx.innovation_depth,
        "gate": ctx.gate,
        "beat_best": ctx.beat_best,
        "routine_mislabel": ctx.routine_mislabel,
        "not_attested_extend": ctx.not_attested_extend,
    }
    if ctx.agent_depth:
        state["agent_depth"] = ctx.agent_depth
    if ctx.fingerprint_depth:
        state["fingerprint_depth"] = ctx.fingerprint_depth
    state["plateau_active"] = ctx.plateau_active
    if ctx.task_domain:
        state["task_domain"] = ctx.task_domain[:120]
    fp = ctx.fingerprint or {}
    reasons = fp.get("reasons") or []
    if reasons:
        state["fingerprint_reasons"] = reasons[:6]
    return state


def _off_plan(ctx: RouterContext, *, reason: str) -> ExternalPlan:
    cfg = _cfg(ctx)
    state = _round_state(ctx)
    state["router_reason"] = reason
    return ExternalPlan(
        schema_version=1,
        round_state=state,
        paper_depth="P0",
        paper_hits_cap=cfg.paper_hits_default,
        docs_depth="D0",
        github_impl=False,
        github_ecosystem=False,
        budget_max_http=cfg.max_http_per_reflect,
        queries={},
    )


def _deepen_paper(paper_depth: str) -> str:
    return _PAPER_DEEPEN.get(paper_depth, paper_depth)


def _should_deepen_plateau(ctx: RouterContext) -> bool:
    depth = (ctx.innovation_depth or "").strip().lower()
    return (
        "plateau" in (ctx.gate or "")
        and ctx.not_attested_extend
        # ADR-6（寻找 stage）：只有 different/novel（形式创新）才触发 plateau-deepen。
        # derived（旧 extend，调度/搜索类）与 routine 同——不在"找 novel"射程内。
        and depth in ("different", "novel")
    )


def _matrix_lookup(ctx: RouterContext) -> tuple[str, str, bool, bool]:
    tier = ctx.tier.upper()
    depth = (ctx.innovation_depth or "routine").strip().lower()
    key = (tier, depth)
    if key not in _DEPTH_MATRIX:
        return ("P0", "D0", False, False)
    paper, docs, impl, ecosystem = _DEPTH_MATRIX[key]
    if tier == "A" and depth in ("different", "novel") and docs == "D1":
        lib_text = "\n".join(filter(None, [ctx.rationale, ctx.phase2_focus])).lower()
        if not any(
            token in lib_text for token in ("timm", "torchvision", "kornia", "torch.nn")
        ):
            docs = "D0"
    return paper, docs, impl, ecosystem


def build_external_plan(ctx: RouterContext) -> ExternalPlan:
    if ctx.reflect_skipped or (ctx.gate or "").startswith("skip:"):
        return _off_plan(ctx, reason="gate_skip")

    cfg = _cfg(ctx)
    exploration = (cfg.exploration or "conservative").strip().lower()

    if (
        ctx.beat_best
        and not ctx.routine_mislabel
        and "plateau" not in (ctx.gate or "")
        and not ctx.plateau_active
        # tier_exhaust_kw = 同一 tier 同质 rounds 已试尽，需要 escalate——
        # 外部检索正是寻找 escalate 出路。not_attested_extend 同理：
        # TAM 缺证据说明外部文献可补。这两种信号下不让 beat_best 短路。
        and "tier_exhaust" not in (ctx.gate or "")
        and not ctx.not_attested_extend
        # inductive/aggressive = 用户要求总是搜文献：beat_best 不应短路 paper 检索
        and exploration not in ("aggressive", "inductive")
    ):
        return _off_plan(ctx, reason="beat_best")

    if ctx.tier.upper() == "E":
        return _off_plan(ctx, reason="tier_e")

    # spec §2 3 源联动：mode 表提供 paper/docs/github_* 的 mode 默认值，
    # 比旧 router "只联动 paper"更聪明 —— optimize 默认开 github_ecosystem
    # (看 best practice 不需论文)、innovate+ 开 github_impl (看具体代码)、
    # aggressive 拉满 = 真"穷尽"。
    #
    # Merge 顺序：mode 默认打底 → 矩阵 A 形式创新(different/novel) lib token 收口 docs → escalation
    # (inductive/aggressive/plateau) 在 mode 默认之上叠加。
    mode_ext = mode_to_external(cfg.effective_mode)
    paper_depth = str(mode_ext["paper_depth"])
    docs_depth = str(mode_ext["docs_depth"])
    github_impl = bool(mode_ext["github_impl"])
    github_ecosystem = bool(mode_ext["github_ecosystem"])

    # 矩阵仍用于：A 形式创新(different/novel) lib token 收口(把 D2 降到 D1 / D0)。
    # matrix 与 mode 默认不冲突 — mode 默认 D2 + matrix 提示 doc 类 lib
    # → D2 降到 D0(非 deep-learning 框架就不查 API)。
    _, matrix_docs, _, _ = _matrix_lookup(ctx)
    if (
        ctx.tier.upper() == "A"
        and ctx.innovation_depth in ("different", "novel")
        and matrix_docs in ("D0", "D1")
        and docs_depth == "D2"
    ):
        docs_depth = matrix_docs

    if ctx.routine_mislabel:
        paper_depth = "P1"
        docs_depth = "D3"
        github_impl = False
        github_ecosystem = True

    # inductive/aggressive 必查论文（user intent：最后两档必须查）：
    # mode 默认对 careful 给 P0 → 抬到 P2，否则 careful+aggressive 仍不查论文。
    if exploration in ("aggressive", "inductive") and paper_depth in ("P0", "P1"):
        paper_depth = "P2"
    # aggressive 再把 paper 检索拉满（P2 → P3）
    if exploration == "aggressive":
        paper_depth = _deepen_paper(paper_depth)

    paper_hits_cap = cfg.paper_hits_default
    if _should_deepen_plateau(ctx):
        paper_hits_cap = cfg.paper_hits_deepen
        paper_depth = _deepen_paper(paper_depth)

    # 撞墙时强制加 github_ecosystem 源（已有 github_ecosystem 适配器）。
    # 比 _should_deepen_plateau 更宽：只要 plateau_active=True 就强制，
    # 不要求 not_attested_extend / different|novel — 撞墙的本质是同质 rounds
    # 试尽，需要换个工具（github awesome-* list 找生态）打破僵局。
    plateau_forced_github = False
    if ctx.plateau_active and not github_ecosystem:
        github_ecosystem = True
        plateau_forced_github = True

    docs_symbols = build_docs_symbols(ctx)
    queries: dict[str, str] = {"paper": build_paper_query(ctx)}
    if docs_symbols:
        queries["docs_symbols"] = ",".join(docs_symbols)

    round_state = _round_state(ctx)
    round_state["effective_mode"] = cfg.effective_mode
    if plateau_forced_github:
        round_state["github_forced_by_plateau"] = True

    return ExternalPlan(
        schema_version=1,
        round_state=round_state,
        paper_depth=paper_depth,
        paper_hits_cap=paper_hits_cap,
        docs_depth=docs_depth,
        github_impl=github_impl,
        github_ecosystem=github_ecosystem,
        budget_max_http=cfg.max_http_per_reflect,
        queries=queries,
    )
