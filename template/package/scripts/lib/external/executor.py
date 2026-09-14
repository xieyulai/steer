"""Execute ExternalPlan → evidence bundle (P0: arxiv + openalex, local docs)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from lib.external.arxiv import search_arxiv
from lib.external.config import resolve_serper_key
from lib.external.docs_local import inspect_symbol
from lib.external.docs_registry import resolve_docs
from lib.external.docs_serper import search_site
from lib.external.github_ecosystem import search_library_repos
from lib.external.github_impl import fetch_repo_code, search_repos
from lib.external.merge import merge_paper_hits
from lib.external.models import ExternalPlan, ToolResult, empty_bundle
from lib.external.openalex import search_openalex
from lib.external.pdf import fetch_arxiv_excerpt
from lib.external.query import _QueryContext, build_docs_symbols
from lib.external.scholar import search_scholar

_DOCS_DEPTH_RANK = {"D0": 0, "D1": 1, "D2": 2, "D3": 3}
_PAPER_DEPTH_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4, "P5": 5}


def _docs_depth_rank(depth: str) -> int:
    return _DOCS_DEPTH_RANK.get(str(depth or "D0"), 0)


def _paper_depth_rank(depth: str) -> int:
    return _PAPER_DEPTH_RANK.get(str(depth or "P0"), 0)


# ── T3/ADR-9+：seed_repos 前馈（universal framework/task theme → GitHub repo）──
# 数据在 scripts/data/seed_repos.json（v=1, schemas 详见 JSON）。
# 命中逻辑：fingerprint.MODEL_ARCH + fingerprint.task_domain + rationale 三路
# 文本 lowercased 后,token 命中 → 累计 full_name；先 frameworks 后 task_themes；
# 去重；5 项封顶（cap=5，JSON 可列更多）。文件缺失/JSON 错 → safe fallback 空。
_SEED_REPOS_PATH = Path(__file__).resolve().parents[2] / "data" / "seed_repos.json"
_SEED_REPOS_CACHE: dict | None = None
_SEED_REPOS_CAP = 5


def _load_seed_repos() -> dict:
    """读 + 缓存 seed_repos.json。失败/缺失 → 空 schema（frameworks/task_themes={}）。"""
    global _SEED_REPOS_CACHE
    if _SEED_REPOS_CACHE is not None:
        return _SEED_REPOS_CACHE
    empty = {"frameworks": {}, "task_themes": {}}
    if not _SEED_REPOS_PATH.exists():
        _SEED_REPOS_CACHE = empty
        return _SEED_REPOS_CACHE
    try:
        data = json.loads(_SEED_REPOS_PATH.read_text(encoding="utf-8"))
    except Exception:
        _SEED_REPOS_CACHE = empty
        return _SEED_REPOS_CACHE
    if not isinstance(data, dict):
        _SEED_REPOS_CACHE = empty
        return _SEED_REPOS_CACHE
    _SEED_REPOS_CACHE = {
        "frameworks": data.get("frameworks") or {},
        "task_themes": data.get("task_themes") or {},
    }
    return _SEED_REPOS_CACHE


def _seed_repos_lookup(ctx) -> list[str]:
    """启发式：ctx.fingerprint + ctx.rationale 三路文本 → 命中 token → repo full_name 列表。

    顺序：frameworks 先于 task_themes（保持稳定命中序）。
    去重：full_name 全局 set；5 项封顶。
    容错：ctx=None/{}、fingerprint 非 dict、文件缺失/JSON 错 → 返回 []，不抛。
    """
    ctx = ctx or {}
    fp = ctx.get("fingerprint") if isinstance(ctx, dict) else None
    if not isinstance(fp, dict):
        fp = {}
    text_parts = [
        str(fp.get("MODEL_ARCH") or ""),
        str(fp.get("task_domain") or ""),
        str(ctx.get("rationale") or "") if isinstance(ctx, dict) else "",
    ]
    text = " ".join(text_parts).lower()
    if not text.strip():
        return []
    repos = _load_seed_repos()
    out: list[str] = []
    seen: set[str] = set()
    for src_key in ("frameworks", "task_themes"):
        bucket = repos.get(src_key) or {}
        if not isinstance(bucket, dict):
            continue
        for tok, full_names in bucket.items():
            if not isinstance(tok, str) or tok not in text:
                continue
            if not isinstance(full_names, list):
                continue
            for fn in full_names:
                if not isinstance(fn, str) or "/" not in fn:
                    continue
                if fn in seen:
                    continue
                seen.add(fn)
                out.append(fn)
                if len(out) >= _SEED_REPOS_CAP:
                    return out
    return out


# ── T3/ADR-2：routine_attestation.verdict 改 LLM-judged（全文证据）─────────
# 旧糙判定 supported if docs_hits 换成：喂 method_excerpt（PDF 全文，P3+ 才有）
# + docs 摘要 + paper 摘要给 LLM，判文献是否真背书本轮库/API 用法。
# llm_query_fn=None（无 LLM / 测试）→ 回退 crude（docs 命中即 supported），不劣化。
def _build_attestation_prompt(
    *,
    docs_hits: list[dict[str, Any]],
    paper_hits: list[dict[str, Any]],
    method_excerpt: str | None,
) -> str:
    """构造文献背书判定 prompt：喂全文方法段 + docs 摘要 + paper 摘要。"""
    parts: list[str] = []
    if method_excerpt:
        parts.append("【论文方法段（arXiv 全文）】\n" + str(method_excerpt).strip())
    if paper_hits:
        abs_lines: list[str] = []
        for h in paper_hits[:5]:
            title = str(h.get("title") or "").strip()
            abstract = str(h.get("abstract") or "").strip()
            if abstract:
                abs_lines.append(f"- {title}: {abstract[:400]}")
        if abs_lines:
            parts.append("【论文摘要】\n" + "\n".join(abs_lines))
    if docs_hits:
        doc_lines: list[str] = []
        for d in docs_hits[:5]:
            sym = str(d.get("symbol") or "").strip()
            exc = str(d.get("doc_excerpt") or "").strip()
            if exc:
                doc_lines.append(f"- {sym}: {exc[:300]}")
        if doc_lines:
            parts.append("【框架文档用法】\n" + "\n".join(doc_lines))

    evidence = "\n\n".join(parts) if parts else "（本轮无可用外部证据）"
    return (
        "你是「文献背书」判官。下面是本轮实验用到常规库/API 的外部证据"
        "（论文全文方法段、论文摘要、框架文档）。请判断：这些文献是否"
        "**明确佐证（supported）**本轮的库/API 用法（即用法有出处、有先例、有原理支撑）？\n\n"
        f"{evidence}\n\n"
        "判断标准：\n"
        "- supported：证据中能找到对本轮用法的明确出处/先例/原理支撑；\n"
        "- inconclusive：证据不足、模棱两可或无法佐证（含弱信号、间接相关）。\n\n"
        "只回答一行，以 `结论:` 开头，后接 supported 或 inconclusive。"
    )


def _parse_attestation_verdict(raw: str) -> str:
    """解析 LLM 背书判定输出 → supported/inconclusive；无法解析 → inconclusive。

    否定词优先（inconclusive / unsupported / not support），避免「不支持」误判。
    """
    s = str(raw or "").strip().lower()
    if "inconclusive" in s or "unsupported" in s or "not support" in s:
        return "inconclusive"
    if "supported" in s or "supports" in s:
        return "supported"
    return "inconclusive"


def _judge_attestation_verdict(
    llm_query_fn,
    *,
    docs_hits: list[dict[str, Any]],
    paper_hits: list[dict[str, Any]],
    method_excerpt: str | None,
) -> str:
    """T3/ADR-2：LLM 判 routine_attestation verdict（全文证据）。

    - llm_query_fn=None → 回退 crude（docs 命中即 supported），保持 v1 行为不劣化；
    - LLM 可用 → 喂全文方法段 + docs + paper 摘要给 LLM 判；
    - 任何 LLM 失败静默回退 crude（外部证据非致命，与 query.py 同模式）。
    """
    crude = "supported" if docs_hits else "inconclusive"
    if llm_query_fn is None:
        return crude
    try:
        prompt = _build_attestation_prompt(
            docs_hits=docs_hits, paper_hits=paper_hits, method_excerpt=method_excerpt,
        )
        return _parse_attestation_verdict(llm_query_fn(prompt))
    except Exception as exc:
        # LLM 挂掉：回退 crude，但留痕（外部证据非致命，降级须可观测，
        # 与 reflect_hook 非致命外部错同模式 print→stderr）。
        print(
            f"[executor] attestation LLM down, crude fallback ({type(exc).__name__}: {exc})",
            file=sys.stderr,
        )
        return crude


def _parse_docs_symbols(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(s).strip() for s in raw if str(s).strip()]
    return [s.strip() for s in str(raw).split(",") if s.strip()]


def _early_stop_paper(hits: list[dict[str, Any]]) -> bool:
    if len(hits) < 3:
        return False
    top = hits[0]
    return bool(top.get("arxiv_id")) and bool(str(top.get("abstract") or "").strip())


def _record_tool_skip(tr: ToolResult, skipped: list[dict[str, str]]) -> None:
    reason = tr.skip_reason or tr.error or "skipped"
    skipped.append({"provider": tr.provider, "reason": str(reason)})


def _run_paper_no_serper(
    plan: ExternalPlan,
    *,
    http_used: int,
    skipped: list[dict[str, str]],
    repo_root: Path | None = None,
) -> tuple[list[dict[str, Any]], int, str | None, list[dict[str, Any]], str | None, str | None, str | None, list[str]]:
    budget = plan.budget_max_http
    hit_lists: list[list[dict[str, Any]]] = []
    paper_query = str(plan.queries.get("paper") or "").strip()
    if not paper_query:
        return [], http_used, None, [], None, None, None, []

    if http_used < budget:
        try:
            arxiv_hits = search_arxiv(paper_query, max_results=5)
            http_used += 1
            hit_lists.append(arxiv_hits)
        except Exception as exc:
            skipped.append({"provider": "arxiv", "reason": str(exc)})
    else:
        skipped.append({"provider": "arxiv", "reason": "budget_exceeded"})

    merged = merge_paper_hits(hit_lists, cap=plan.paper_hits_cap) if hit_lists else []
    if _early_stop_paper(merged):
        excerpt, impl, http_used, pdf_path, pdf_aid, method_excerpt, impl_hints = _finish_paper_extras(
            plan,
            merged,
            http_used=http_used,
            skipped=skipped,
            budget=budget,
            repo_root=repo_root,
        )
        return merged, http_used, excerpt, impl, pdf_path, pdf_aid, method_excerpt, impl_hints

    if http_used < budget:
        try:
            openalex_hits = search_openalex(paper_query, max_results=5)
            http_used += 1
            hit_lists.append(openalex_hits)
        except Exception as exc:
            skipped.append({"provider": "openalex", "reason": str(exc)})
    else:
        skipped.append({"provider": "openalex", "reason": "budget_exceeded"})

    merged = merge_paper_hits(hit_lists, cap=plan.paper_hits_cap) if hit_lists else []
    excerpt, impl, http_used, pdf_path, pdf_aid, method_excerpt, impl_hints = _finish_paper_extras(
        plan,
        merged,
        http_used=http_used,
        skipped=skipped,
        budget=budget,
        repo_root=repo_root,
    )
    return merged, http_used, excerpt, impl, pdf_path, pdf_aid, method_excerpt, impl_hints


def _run_paper_scholar_only(
    plan: ExternalPlan,
    *,
    http_used: int,
    skipped: list[dict[str, str]],
    repo_root: Path | None = None,
) -> tuple[list[dict[str, Any]], int, str | None, list[dict[str, Any]], str | None, str | None, str | None, list[str]]:
    """有 serper key：Scholar + arXiv 双源（Ticket 01/#01 修复）。

    设计：
    - primary = scholar（Google Scholar via serper）
    - 补调 arxiv：scholar 命中不带 arxiv_id，需 arxiv 注入 arxiv_id 才能触发
      PDF 全文下载（_finish_paper_extras 取 merged[0].arxiv_id）；merge 的
      truncate_hits 自动把带 arxiv_id 的命中浮顶 → 前列带 arxiv_id
    - 不级联 openalex（保持克制；arxiv 已足够补 arxiv_id）
    """
    budget = plan.budget_max_http
    hit_lists: list[list[dict[str, Any]]] = []
    paper_query = str(plan.queries.get("paper") or "").strip()
    if not paper_query:
        return [], http_used, None, [], None, None, None, []

    if http_used < budget:
        tr = search_scholar(paper_query, max_results=5)
        if tr.status == "ok":
            hit_lists.append(tr.hits)
            http_used += tr.http_calls
        elif tr.status == "skipped":
            _record_tool_skip(tr, skipped)
        else:
            _record_tool_skip(tr, skipped)
            http_used += tr.http_calls
    else:
        skipped.append({"provider": "scholar", "reason": "budget_exceeded"})

    # Ticket 01 (#01): scholar 命中不带 arxiv_id → 补调 arxiv 注入 arxiv_id。
    if http_used < budget:
        try:
            arxiv_hits = search_arxiv(paper_query, max_results=5)
            http_used += 1
            hit_lists.append(arxiv_hits)
        except Exception as exc:
            skipped.append({"provider": "arxiv", "reason": str(exc)})
    else:
        skipped.append({"provider": "arxiv", "reason": "budget_exceeded"})

    merged = merge_paper_hits(hit_lists, cap=plan.paper_hits_cap) if hit_lists else []
    excerpt, impl, http_used, pdf_path, pdf_aid, method_excerpt, impl_hints = _finish_paper_extras(
        plan,
        merged,
        http_used=http_used,
        skipped=skipped,
        budget=budget,
        repo_root=repo_root,
    )
    return merged, http_used, excerpt, impl, pdf_path, pdf_aid, method_excerpt, impl_hints



def _finish_paper_extras(
    plan: ExternalPlan,
    merged: list[dict[str, Any]],
    *,
    http_used: int,
    skipped: list[dict[str, str]],
    budget: int,
    repo_root: Path | None = None,
) -> tuple[str | None, list[dict[str, Any]], int, str | None, str | None, str | None, list[str]]:
    excerpt: str | None = None
    impl_candidates: list[dict[str, Any]] = []
    pdf_local_path: str | None = None
    pdf_arxiv_id: str | None = None
    method_excerpt: str | None = None  # Ticket 01 (#02): PDF 全文抽取的方法段
    impl_hints: list[str] = []          # Ticket 01 (#02): 方法段内的实现信号句

    if _paper_depth_rank(plan.paper_depth) >= 3 and merged:
        top_aid = str(merged[0].get("arxiv_id") or "").strip()
        if top_aid and http_used < budget:
            persist_dir = None
            if repo_root is not None:
                persist_dir = repo_root / "saved" / "external_evidence" / "pdfs"
            tr = fetch_arxiv_excerpt(
                top_aid,
                persist_dir=persist_dir,
                repo_root=repo_root,
            )
            if tr.status == "ok" and tr.excerpt:
                excerpt = tr.excerpt
                method_excerpt = tr.method_excerpt
                impl_hints = tr.impl_hints
                pdf_local_path = tr.local_path
                pdf_arxiv_id = top_aid
                http_used += tr.http_calls
            elif tr.status == "skipped":
                _record_tool_skip(tr, skipped)
            else:
                _record_tool_skip(tr, skipped)
                http_used += tr.http_calls
        elif top_aid:
            skipped.append({"provider": "pdf", "reason": "budget_exceeded"})

    if plan.github_impl and merged:
        impl_query = str(merged[0].get("title") or plan.queries.get("paper") or "").strip()
        if impl_query and http_used < budget:
            tr = search_repos(impl_query, max_results=3)
            if tr.status == "ok":
                impl_candidates = tr.hits
                http_used += tr.http_calls
            elif tr.status == "skipped":
                _record_tool_skip(tr, skipped)
            else:
                _record_tool_skip(tr, skipped)
                http_used += tr.http_calls
        elif impl_query:
            skipped.append({"provider": "github_impl", "reason": "budget_exceeded"})

    return excerpt, impl_candidates, http_used, pdf_local_path, pdf_arxiv_id, method_excerpt, impl_hints


def _run_docs(
    plan: ExternalPlan,
    *,
    skipped: list[dict[str, str]],
    http_used: int,
    ctx: _QueryContext | None = None,
) -> tuple[list[dict[str, str]], int]:
    depth = _docs_depth_rank(plan.docs_depth)
    if depth < 1:
        return [], http_used

    # C1: caller 没填 docs_symbols 且 ctx 非空 → 走 build_docs_symbols 启发式推断；
    # 仍空则沿用原行为（下面 symbols 为空 → silent skip）。
    if not plan.queries.get("docs_symbols") and ctx is not None:
        inferred = build_docs_symbols(ctx) or []
        if inferred:
            plan.queries["docs_symbols"] = inferred

    symbols = _parse_docs_symbols(plan.queries.get("docs_symbols"))
    if not symbols:
        return [], http_used

    docs: list[dict[str, str]] = []

    for symbol in symbols:
        try:
            docs.append(inspect_symbol(symbol))
        except Exception as exc:
            skipped.append({"provider": "docs_local", "reason": f"{symbol}: {exc}"})

    if depth >= 2:
        try:
            docs.extend(resolve_docs(symbols))
        except Exception as exc:
            skipped.append({"provider": "docs_registry", "reason": str(exc)})

    if depth >= 3:
        budget = plan.budget_max_http
        if resolve_serper_key() is None:
            skipped.append({"provider": "serper_site", "reason": "no_serper_key"})
        else:
            for symbol in symbols:
                if http_used >= budget:
                    skipped.append({"provider": "serper_site", "reason": "budget_exceeded"})
                    break
                tr = search_site(symbol, site="pytorch.org/docs")
                if tr.status == "ok":
                    docs.extend(tr.hits)  # type: ignore[arg-type]
                    http_used += tr.http_calls
                elif tr.status == "skipped":
                    _record_tool_skip(tr, skipped)
                else:
                    _record_tool_skip(tr, skipped)
                    http_used += tr.http_calls

    return docs, http_used


def _run_github_ecosystem(
    plan: ExternalPlan,
    *,
    http_used: int,
    skipped: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], int]:
    if not plan.github_ecosystem:
        return [], http_used

    lib_query = str(plan.queries.get("paper") or "").strip()
    if not lib_query:
        return [], http_used

    if http_used >= plan.budget_max_http:
        skipped.append({"provider": "github_ecosystem", "reason": "budget_exceeded"})
        return [], http_used

    # B2: query 改写 — 多路候选查询去重搜索
    try:
        from lib.external.query_refiner import rewrite_for_awesome
        ctx = getattr(plan, "context", None) or {}
        refined_queries = rewrite_for_awesome(lib_query, ctx=ctx)
    except Exception:
        refined_queries = [lib_query]

    seen_full_names: set[str] = set()
    aggregated_hits: list[dict[str, Any]] = []
    local_http = 0

    for q in refined_queries[:5]:
        if http_used + local_http >= plan.budget_max_http:
            skipped.append({"provider": "github_ecosystem", "reason": "budget_exceeded"})
            break
        tr = search_library_repos(q)
        local_http += tr.http_calls
        if tr.status == "ok":
            for hit in tr.hits:
                full_name = hit.get("full_name") if isinstance(hit, dict) else None
                if full_name and full_name in seen_full_names:
                    continue
                if full_name:
                    seen_full_names.add(full_name)
                aggregated_hits.append(hit)
        else:
            _record_tool_skip(tr, skipped)

    if aggregated_hits:
        http_used += local_http
        return aggregated_hits[:5], http_used
    http_used += local_http
    return [], http_used


def _run_github_code(
    plan: ExternalPlan,
    bundle: dict[str, Any],
    *,
    http_used: int,
    skipped: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], int]:
    """T9/ADR-9：P3+ 抓代码喂寻找（aggressive / 寻找 forced-P3 启用，默认关）。

    github 检索从 metadata 扩到 raw 代码内容：取 impl_candidates 的 top repo，拉
    README + 少量源码片段 → bundle['paper']['linked_code']（寻找反馈边数据）。
    仅 P3+ 启用（AC2「默认关」：非 P3+ 短路返回 []，既有检索行为不变）；无 top
    repo（github_impl=F / 搜空）或预算耗尽 → 不抓。非致命（与 _run_github_ecosystem
    同模式：skipped/error 不抛）。
    """
    if _paper_depth_rank(plan.paper_depth) < 3:
        return [], http_used
    candidates = ((bundle.get("paper") or {}).get("impl_candidates") or [])
    # B1/ADR-9+：seed_repos 前馈（fingerprint.MODEL_ARCH + task_domain + rationale）
    # 命中 → 注入 full_name；不覆盖原候选（去重保原序，seed_repos 追加尾部）。
    seed_ctx = getattr(plan, "context", None) or {}
    seed_repos = _seed_repos_lookup(seed_ctx)
    if seed_repos:
        existing = {
            c.get("full_name")
            for c in candidates
            if isinstance(c, dict) and c.get("full_name")
        }
        for fn in seed_repos:
            if fn not in existing:
                candidates.append({"full_name": fn, "source": "seed_repos"})
                existing.add(fn)
    top = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
    repo = str(top.get("full_name") or "").strip()
    if not repo:
        return [], http_used
    if http_used >= plan.budget_max_http:
        skipped.append({"provider": "github_code", "reason": "budget_exceeded"})
        return [], http_used
    tr = fetch_repo_code(repo)
    if tr.status == "ok":
        http_used += tr.http_calls
        return tr.hits, http_used
    _record_tool_skip(tr, skipped)
    http_used += tr.http_calls
    return [], http_used


def execute_plan(
    plan: ExternalPlan,
    *,
    dry_run: bool = False,
    has_serper: bool | None = None,
    repo_root: Path | None = None,
    llm_query_fn=None,
) -> dict[str, Any]:
    # P1-7: bundle['plan'] 由 empty_bundle 内填（single chokepoint，
    # reflect_hook disabled/except 两路径也走 empty_bundle，自动覆盖）。
    if dry_run or plan.all_off():
        return empty_bundle(plan=plan)

    if has_serper is None:
        has_serper = resolve_serper_key() is not None

    bundle = empty_bundle(plan=plan)
    skipped: list[dict[str, str]] = []
    http_used = 0

    if plan.paper_depth != "P0":
        if has_serper:
            (
                paper_hits,
                http_used,
                excerpt,
                impl_candidates,
                pdf_local_path,
                pdf_arxiv_id,
                method_excerpt,
                impl_hints,
            ) = _run_paper_scholar_only(
                plan, http_used=http_used, skipped=skipped, repo_root=repo_root
            )
        else:
            (
                paper_hits,
                http_used,
                excerpt,
                impl_candidates,
                pdf_local_path,
                pdf_arxiv_id,
                method_excerpt,
                impl_hints,
            ) = _run_paper_no_serper(
                plan, http_used=http_used, skipped=skipped, repo_root=repo_root
            )
        bundle["paper"]["hits"] = paper_hits
        bundle["paper"]["excerpt"] = excerpt
        bundle["paper"]["impl_candidates"] = impl_candidates
        bundle["paper"]["pdf_local_path"] = pdf_local_path
        bundle["paper"]["pdf_arxiv_id"] = pdf_arxiv_id
        # Ticket 01 (#02): PDF 方法段 + 实现要点落进 bundle（喂入层外部证据包）。
        bundle["paper"]["method_excerpt"] = method_excerpt
        bundle["paper"]["impl_hints"] = impl_hints

    docs_hits, http_used = _run_docs(plan, skipped=skipped, http_used=http_used)
    ecosystem_hits, http_used = _run_github_ecosystem(
        plan, http_used=http_used, skipped=skipped
    )
    # T9/ADR-9：P3+ 抓代码喂寻找（取 top impl_candidate 的 raw 代码内容 → linked_code）。
    linked_code, http_used = _run_github_code(
        plan, bundle, http_used=http_used, skipped=skipped
    )
    bundle["paper"]["linked_code"] = linked_code

    attestation = bundle["code"]["routine_attestation"]
    attestation["docs"] = docs_hits
    attestation["github_ecosystem"] = ecosystem_hits
    # T3/ADR-2：verdict 走 LLM-judged（喂 method_excerpt 全文 + docs + paper）。
    attestation["verdict"] = _judge_attestation_verdict(
        llm_query_fn,
        docs_hits=docs_hits,
        paper_hits=bundle["paper"]["hits"],
        method_excerpt=bundle["paper"]["method_excerpt"],
    )

    bundle["meta"]["http_calls_used"] = http_used
    bundle["meta"]["skipped"] = skipped

    # D1: 写盘 saved/external_evidence_health.json — health 状态报告
    try:
        from lib.external.evidence_health import write_evidence_health
        round_no = int(getattr(plan, "round_no", 0) or 0)
        saved_dir = getattr(plan, "saved_dir", None) or "saved"
        write_evidence_health(bundle, round_no=round_no, saved_dir=saved_dir)
    except Exception:
        # 落盘失败不阻断 executor 主体返回 — health 是观察位
        pass

    return bundle
