"""Format evidence_bundle for Phase 1 prompt injection."""
from __future__ import annotations

from typing import Any

from lib.external.models import ExternalPlan


def _truncate(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def render_3source_status(plan: ExternalPlan | dict[str, Any]) -> str:
    """spec §2 + §5: 3 源状态行（任一源未启用 → 显式 "未启用" 提示，避免 silent skip）。

    接受 ExternalPlan 实例或 plan.to_dict() 字典（reflect.py 持 dict 即可调用）。
    返回 3 行 markdown bullet（paper / docs / github）：

        - paper: depth=P3, hits_cap=5
        - docs: depth=D3
        - github: impl, ecosystem

    关时显式标 "未启用"（paper/docs 看 depth，github 看 impl+ecosystem）。
    """
    p = plan.to_dict() if isinstance(plan, ExternalPlan) else plan
    paper_depth = str(p.get("paper_depth") or "P0")
    paper_hits_cap = int(p.get("paper_hits_cap") or 0)
    docs_depth = str(p.get("docs_depth") or "D0")
    github_impl = bool(p.get("github_impl"))
    github_ecosystem = bool(p.get("github_ecosystem"))

    lines: list[str] = []
    # paper
    if paper_depth == "P0" or paper_hits_cap <= 0:
        if paper_depth == "P0":
            reason = "depth=P0"
        else:
            reason = f"hits_cap={paper_hits_cap}"
        lines.append(f"- paper: [未启用] ({reason})")
    else:
        lines.append(f"- paper: depth={paper_depth}, hits_cap={paper_hits_cap}")
    # docs
    if docs_depth == "D0":
        lines.append("- docs: [未启用] (depth=D0)")
    else:
        lines.append(f"- docs: depth={docs_depth}")
    # github — impl 和 ecosystem 单独行（spec 要求）
    if github_impl:
        lines.append("- github_impl: 已启用")
    else:
        lines.append("- github_impl: [未启用]")
    if github_ecosystem:
        lines.append("- github_ecosystem: 已启用")
    else:
        lines.append("- github_ecosystem: [未启用]")
    return "\n".join(lines)


def format_external_evidence_md(
    bundle: dict,
    max_hits: int = 3,
    external_plan: ExternalPlan | dict[str, Any] | None = None,
) -> str:
    """Render external evidence for Phase 1 prompt (truncated hits + skipped line).

    若 external_plan 非空，prompt 头部附 3 源状态行（spec §2 + §5），避免 agent 把
    silent skip 误读为"查了"——D0/False → 显式「未启用」字样。
    """
    # 即使 bundle 为空，若 external_plan 给定，仍渲染 3 源状态行。
    if not bundle and external_plan is None:
        return "（无外部证据；禁止编造 url）"

    lines: list[str] = []
    if external_plan is not None:
        lines.append("**外部证据源状态：**")
        lines.append(render_3source_status(external_plan))
        lines.append("")  # 空行分隔 status 与 evidence detail

    if not bundle:
        return "\n".join(lines)

    paper = bundle.get("paper") or {}
    hits: list[dict[str, Any]] = list(paper.get("hits") or [])

    if hits:
        lines.append("**论文命中：**")
        for i, hit in enumerate(hits[:max_hits], start=1):
            title = hit.get("title") or "（无标题）"
            url = hit.get("url") or ""
            abstract = _truncate(str(hit.get("abstract") or ""), 200)
            lines.append(f"{i}. {title} — {url}")
            if abstract:
                lines.append(f"   摘要: {abstract}")
    else:
        lines.append("**论文命中：**（无 — 禁止编造论文 url）")

    code = bundle.get("code") or {}
    attestation = code.get("routine_attestation") or {}
    verdict = attestation.get("verdict") or "inconclusive"
    docs = attestation.get("docs") or []
    lines.append(f"**常规库/API 佐证：** 结论={verdict}；文档条数={len(docs)}")
    for doc in docs[:max_hits]:
        symbol = doc.get("symbol") or doc.get("module") or "?"
        excerpt = _truncate(str(doc.get("doc_excerpt") or doc.get("url") or ""), 120)
        lines.append(f"  - {symbol}: {excerpt}")

    meta = bundle.get("meta") or {}
    skipped = meta.get("skipped") or []
    if skipped:
        parts = [
            f"{s.get('provider', '?')}={s.get('reason', '')}" for s in skipped[:5]
        ]
        lines.append(f"**已跳过的数据源：** {', '.join(parts)}")

    if meta.get("error"):
        lines.append(f"**Phase 1.85 异常：** {meta['error']}")

    return "\n".join(lines) if lines else "（空 bundle；禁止编造 url）"