"""reflect Phase 1.85 — build external plan, execute providers, write saved/*.json."""
from __future__ import annotations

import dataclasses
import json
import sys
import traceback
from pathlib import Path
from typing import Any

from lib.external.catalog import append_catalog_overlay
from lib.external.config import load_external_config
from lib.external.evidence_refs import _FIND_CANDIDATES_FILENAME, _derive_url
from lib.external.executor import _paper_depth_rank, execute_plan
from lib.external.executable_advice import attach_executable_advice
from lib.external.format_prompt import render_3source_status
from lib.external.models import ExternalPlan, empty_bundle
from lib.external.router import RouterContext, build_external_plan
from lib.innovation_fingerprint import apply_novel_ceiling

# T4/ADR-6：寻找(find)阶段——评估(verify)的事双胞胎。
# 寻找候选部件封顶（与 evidence_refs 同口径，防 find_candidates.json 撑大）。
_FIND_CANDIDATES_CAP = 5
# 寻找触发深度集（撞墙后才有向外捞的意义；routine/derived 不触发）。
_FIND_DEPTH_SET = ("different", "novel")
# 注：_FIND_CANDIDATES_FILENAME 由 evidence_refs 单一持有（同模块还有 reader），
# 这里只 import 不重定义，防两处文件名漂移（code-review Duplicated Code 收口）。


def format_3source_status_lines(plan_dict: dict[str, Any] | None) -> str:
    """spec §2 + §5: 把 3 源状态行打包成 reflect prompt 注入块（spec: T6）。

    返回 markdown 文本块：
        **外部证据源状态：**
        - paper: ...
        - docs: ...
        - github: ...

    用于 reflect.py 在 ## 外部证据（已验证） 段之前塞入 prompt，让 agent 看到
    「docs_depth=D0 → docs: 未启用」这样的显式提示，避免 silent skip 误读。

    plan_dict 为 None / 空 dict 时返回空字符串，调用方无需判 None。
    """
    if not plan_dict:
        return ""
    try:
        body = render_3source_status(plan_dict)
    except Exception:
        # 单源字段缺失 → 不阻塞 reflect
        return ""
    return "**外部证据源状态：**\n" + body


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _infer_routine_mislabel(innovation_warnings: list[dict], fingerprint: dict | None = None) -> bool:
    if any(w.get("kind") == "routine_mislabel" for w in innovation_warnings):
        return True
    fp = fingerprint or {}
    agent = str(fp.get("agent_depth") or "").strip().lower()
    depth = str(fp.get("depth") or "").strip().lower()
    return agent == "routine" and depth in ("derived", "different", "novel")


def _infer_not_attested_extend(last_round: dict, tam_result, effective_depth: str) -> bool:
    depth = (effective_depth or last_round.get("innovation_depth") or "").strip().lower()
    if depth not in ("derived", "different", "novel"):
        return False
    tier_raw = (last_round.get("tier_this_round") or "B").strip().upper()
    letter = tier_raw[0] if tier_raw else "B"
    rollup = getattr(tam_result, "rollup", None) or {}
    status = (rollup.get(letter) or {}).get("status")
    return status == "not_attested"


def _infer_beat_best(repo_root: Path, gate_label: str) -> bool:
    if gate_label == "skip:keep_new_best":
        return True
    rd_path = repo_root / "_runs" / "round_decision.json"
    if rd_path.is_file():
        try:
            rd = json.loads(rd_path.read_text(encoding="utf-8"))
            ks = rd.get("keep_suggestion") or rd.get("keep") or {}
            if isinstance(ks, dict):
                reason = str(ks.get("reason") or "").lower()
                if "new best" in reason or "beat best" in reason or "beat_best" in reason:
                    return True
        except Exception:
            pass
    try:
        from lib.run_ledger_summary import (  # noqa: WPS433
            metric_direction,
            metric_key,
            round_decision_status,
            tsv_rows,
        )

        status = round_decision_status(repo_root)
        rows = tsv_rows(repo_root)
        if status == "KEEP" and len(rows) >= 1:
            mk = metric_key(repo_root)
            direction = metric_direction(repo_root)
            try:
                last_v = float(rows[-1].get(mk, "nan"))
                prev = [
                    float(r.get(mk, "nan"))
                    for r in rows[:-1]
                    if r.get(mk)
                ]
                prev = [v for v in prev if v == v]
                if prev and last_v == last_v:
                    if direction == "minimize":
                        return last_v <= min(prev)
                    return last_v >= max(prev)
            except ValueError:
                pass
    except ImportError:
        pass
    try:
        from lib.ledger_anchor import metric_leader_row  # noqa: WPS433
        from lib.run_ledger_summary import metric_key, tsv_rows  # noqa: WPS433

        leader = metric_leader_row(repo_root)
        rows = tsv_rows(repo_root)
        if leader and rows:
            last_exp = rows[-1].get("experiment", "")
            if last_exp and last_exp == leader.experiment:
                return True
    except ImportError:
        pass
    return False


def _infer_plateau_active(repo_root: Path) -> bool:
    try:
        from lib.run_ledger_summary import agent_config, plateau_streak  # noqa: WPS433
        plateau_n, _interval = agent_config(repo_root)
        if plateau_n <= 0:
            return False
        return plateau_streak(repo_root, plateau_n) >= plateau_n
    except ImportError:
        return False


def _resolve_seek_plateau_rounds(repo_root: Path) -> int | None:
    """T5/ADR-8：寻找(find)触发的撞墙阈值，按 exploration_mode 走（≠ 全局
    agent.plateau_rounds——那是 verify/评估 的 deepen 阈值，find 不读）。
    careful=None（永不寻找）/ optimize=7 / innovate=5 / aggressive=1。
    解析失败/无 nn-config → None（永不寻找，安全默认）。
    """
    try:
        from lib.experiment_mode import resolve_exploration  # noqa: WPS433
        ext = resolve_exploration(repo_root).external or {}
        val = ext.get("seek_plateau_rounds")
        return int(val) if val is not None else None
    except Exception:
        return None


def _infer_seek_plateau_active(repo_root: Path) -> bool:
    """寻找自己的 plateau 判定：用 mode 的 seek 阈值比 plateau_streak。
    seek=None / <=0 → False（careful 永不寻找）。verify(评估) 不受此影响（仍用全局
    agent.plateau_rounds 经 _infer_plateau_active）。"""
    seek_n = _resolve_seek_plateau_rounds(repo_root)
    if not seek_n or seek_n <= 0:
        return False
    try:
        from lib.run_ledger_summary import plateau_streak  # noqa: WPS433
        return plateau_streak(repo_root, seek_n) >= seek_n
    except Exception:
        return False


def _resolve_task_domain(repo_root: Path) -> str:
    """Pre-condition guard: Task 3 must have created lib/external/task_domain.py.

    If Task 3 not yet done (this task is being implemented first in isolation),
    fall back to empty string — router will use catalog ID query as a degraded
    path. This unblocks Task 2 implementation/testing before Task 3 lands.
    """
    try:
        from lib.external.task_domain import resolve_task_domain  # noqa: WPS433
        return resolve_task_domain(repo_root)
    except ImportError:
        return ""


def _build_router_context(
    repo_root: Path,
    *,
    gate_label: str,
    last_round: dict,
    tam_result,
    innovation_warnings: list[dict],
    fingerprint: dict | None = None,
    llm_query_fn=None,
) -> RouterContext:
    cfg = load_external_config(repo_root)
    fp = fingerprint or {}
    tier_raw = str(fp.get("primary_tier") or last_round.get("tier_this_round") or "B").strip().upper()
    tier = tier_raw[0] if tier_raw and tier_raw[0] in "ABCDE" else "B"
    agent_depth = str(last_round.get("innovation_depth") or fp.get("agent_depth") or "routine").strip().lower()
    fp_depth = str(fp.get("depth") or "").strip().lower()
    if fp.get("enabled", True) and fp and not fp.get("fallback") and fp_depth in ("routine", "derived", "different", "novel"):
        effective_depth = str(fp.get("effective_depth") or fp_depth).strip().lower()
    elif fp.get("enabled") and fp and fp.get("fallback") and agent_depth in ("routine", "derived", "different", "novel"):
        effective_depth = agent_depth
    else:
        effective_depth = agent_depth if agent_depth in ("routine", "derived", "different", "novel") else "routine"
    return RouterContext(
        tier=tier,
        innovation_depth=effective_depth,
        gate=gate_label,
        beat_best=_infer_beat_best(repo_root, gate_label),
        routine_mislabel=_infer_routine_mislabel(innovation_warnings, fp),
        not_attested_extend=_infer_not_attested_extend(last_round, tam_result, effective_depth),
        reflect_skipped=gate_label.startswith("skip:"),
        rationale=str(last_round.get("innovation_rationale") or ""),
        phase2_focus="",
        config=cfg,
        fingerprint=fp if fp else None,
        agent_depth=agent_depth,
        fingerprint_depth=fp_depth,
        plateau_active=_infer_plateau_active(repo_root),
        task_domain=_resolve_task_domain(repo_root),
        llm_query_fn=llm_query_fn,
    )


def _fallback_off_plan(gate_label: str) -> ExternalPlan:
    return ExternalPlan(
        schema_version=1,
        round_state={"gate": gate_label, "router_reason": "error_fallback"},
        paper_depth="P0",
        paper_hits_cap=3,
        docs_depth="D0",
        github_impl=False,
        github_ecosystem=False,
        budget_max_http=6,
        queries={},
    )


def _plan_all_off(plan_dict: dict[str, Any]) -> bool:
    return (
        plan_dict.get("paper_depth") == "P0"
        and plan_dict.get("docs_depth") == "D0"
        and not plan_dict.get("github_impl")
        and not plan_dict.get("github_ecosystem")
    )


def compute_external_attestation(
    bundle: dict[str, Any],
    plan_dict: dict[str, Any] | None = None,
) -> str:
    """Return supported | inconclusive | skipped for innovation_audit."""
    plan_dict = plan_dict or {}
    meta = bundle.get("meta") or {}
    skipped = meta.get("skipped") or []

    if any(
        s.get("provider") == "config"
        and "external_evidence_disabled" in str(s.get("reason") or "")
        for s in skipped
    ):
        return "skipped"

    gate = str((plan_dict.get("round_state") or bundle.get("round_state") or {}).get("gate") or "")
    if gate.startswith("skip:"):
        return "skipped"

    if meta.get("error"):
        return "inconclusive"

    if _plan_all_off(plan_dict):
        return "skipped"

    paper_hits = (bundle.get("paper") or {}).get("hits") or []
    attestation = (bundle.get("code") or {}).get("routine_attestation") or {}
    verdict = str(attestation.get("verdict") or "inconclusive").strip().lower()
    docs = attestation.get("docs") or []

    if len(paper_hits) >= 1 or verdict == "supported":
        return "supported"

    if not paper_hits and not docs and skipped and not meta.get("error"):
        wanted_paper = plan_dict.get("paper_depth", "P0") != "P0"
        wanted_docs = plan_dict.get("docs_depth", "D0") != "D0"
        wanted_github = bool(plan_dict.get("github_impl") or plan_dict.get("github_ecosystem"))
        if not wanted_paper and not wanted_docs and not wanted_github:
            return "skipped"
        if skipped and not paper_hits and not docs:
            return "skipped"

    return "inconclusive"


def format_external_experience_summary(
    bundle: dict[str, Any],
    attestation: str,
) -> str:
    """One-line plain-language summary for EXPERIENCE [反思] block."""
    meta = bundle.get("meta") or {}
    skipped = meta.get("skipped") or []
    hits_count = len((bundle.get("paper") or {}).get("hits") or [])
    verdict = str(
        ((bundle.get("code") or {}).get("routine_attestation") or {}).get("verdict") or ""
    ).strip().lower()

    if attestation == "skipped":
        notes: list[str] = []
        for s in skipped[:4]:
            prov = str(s.get("provider") or "")
            reason = str(s.get("reason") or "")
            if prov == "config" or "disabled" in reason:
                notes.append("外部检索已关闭")
            elif "serper" in prov.lower() or "serper" in reason.lower():
                notes.append("文献搜索服务未配置")
            elif gate := reason:
                if gate.startswith("skip:") or "gate" in reason.lower():
                    notes.append("本轮未触发外部检索")
        if not notes:
            return "外部证据：本轮未做外部检索"
        deduped = list(dict.fromkeys(notes))
        return f"外部证据：本轮未做外部检索（{'；'.join(deduped)}）"

    parts: list[str] = []
    if hits_count:
        parts.append(f"查到 {hits_count} 篇相关论文")
    if verdict == "supported":
        parts.append("框架文档用法有印证")
    if attestation == "inconclusive" and not parts:
        parts.append("已检索但暂无明确佐证")

    for s in skipped[:4]:
        prov = str(s.get("provider") or "")
        reason = str(s.get("reason") or "")
        if "serper" in prov.lower() or "serper" in reason.lower():
            parts.append("文献搜索服务未配置已跳过")
            break

    if not parts:
        return "外部证据：已检索但未找到可用条目"
    return "外部证据：" + "；".join(parts)


def update_innovation_audit_external(
    repo_root: Path,
    attestation: str,
    *,
    attested_depth: str | None = None,
) -> None:
    """Merge external_attestation (+attested_depth) into saved/innovation_audit.json (non-fatal)."""
    audit_path = repo_root / "saved" / "innovation_audit.json"
    data: dict[str, Any] = {}
    if audit_path.is_file():
        try:
            data = json.loads(audit_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["external_attestation"] = attestation
    # T3/ADR-2：attested_depth（different 默认天花板，novel 背书独占）。
    if attested_depth is not None:
        data["attested_depth"] = attested_depth
    _write_json(audit_path, data)


def compute_attested_depth(
    fingerprint: dict | None,
    bundle: dict[str, Any],
    plan_dict: dict[str, Any],
) -> str | None:
    """T3/ADR-2：derive attested innovation depth from fingerprint + LLM verdict。

    different 是默认天花板；novel = different ⊕ (文献背书 supported ∧ P3+)。
    用 bundle 的 raw verdict（LLM-judged，喂全文），**不用** compute_external_attestation
    的宽口径（后者 paper_hits≥1 即 supported，会让「找到论文但未被背书」误升 novel）。
    无 fingerprint → None（novel 是 fingerprint different 的背书 overlay，
    无 different 无 overlay；空_bundle skip 路径 verdict 默认 inconclusive → different）。
    """
    fp = fingerprint or {}
    fp_depth = str(fp.get("depth") or "").strip().lower()
    if fp_depth not in ("routine", "derived", "different", "novel"):
        return None
    raw_verdict = str(
        ((bundle.get("code") or {}).get("routine_attestation") or {}).get("verdict")
        or "inconclusive"
    ).strip().lower()
    paper_depth = str(plan_dict.get("paper_depth") or "P0")
    return apply_novel_ceiling(fp_depth, raw_verdict, paper_depth)


def run_external_evidence_phase(
    repo_root: Path,
    *,
    gate_label: str,
    last_round: dict,
    tam_result,  # tier attestation result object with not_attested_tiers, rollup
    innovation_warnings: list[dict],
    reflect_id: str,
    fingerprint: dict | None = None,
    dry_run: bool = False,
    llm_query_fn=None,
) -> tuple[dict, dict, str]:
    """Build plan, optionally execute providers, write saved/*.json. Never raises.

    Returns (bundle, plan_dict, external_attestation).
    """
    saved_dir = repo_root / "saved"
    plan_path = saved_dir / "external_plan.json"
    bundle_path = saved_dir / "evidence_bundle.json"
    plan_dict: dict[str, Any] = {}
    plan: ExternalPlan | None = None

    try:
        ctx = _build_router_context(
            repo_root,
            gate_label=gate_label,
            last_round=last_round or {},
            tam_result=tam_result,
            innovation_warnings=innovation_warnings,
            fingerprint=fingerprint,
            llm_query_fn=llm_query_fn,
        )
        plan = build_external_plan(ctx)
        plan_dict = plan.to_dict()
        _write_json(plan_path, plan_dict)

        cfg = ctx.config or load_external_config(repo_root)
        if not cfg.enabled:
            bundle = empty_bundle(plan=plan, reflect_id=reflect_id)
            bundle["meta"]["skipped"].append(
                {"provider": "config", "reason": "external_evidence_disabled"}
            )
            _write_json(bundle_path, bundle)
            attestation = compute_external_attestation(bundle, plan_dict)
            update_innovation_audit_external(
                repo_root,
                attestation,
                attested_depth=compute_attested_depth(fingerprint, bundle, plan_dict),
            )
            return bundle, plan_dict, attestation

        bundle = execute_plan(
            plan, dry_run=dry_run, repo_root=repo_root, llm_query_fn=llm_query_fn
        )
        bundle["reflect_id"] = reflect_id
        # Ticket 05 §11：paper.method → 可执行建议 + 骨架，挂 bundle.paper.executable_advice
        # （reflect.py 读 bundle 拼 [实现建议] 块进 direction_full）。disabled/error 路径
        # 走 empty_bundle，executable_advice 已为 None，无需 attach。
        attach_executable_advice(bundle)
        _write_json(bundle_path, bundle)
        attestation = compute_external_attestation(bundle, plan_dict)
        update_innovation_audit_external(
            repo_root,
            attestation,
            attested_depth=compute_attested_depth(fingerprint, bundle, plan_dict),
        )
        return bundle, plan_dict, attestation
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        fallback = plan or _fallback_off_plan(gate_label)
        if not plan_dict:
            try:
                plan_dict = fallback.to_dict()
                _write_json(plan_path, plan_dict)
            except Exception:
                plan_dict = {"schema_version": 1, "error": err}
        bundle = empty_bundle(plan=fallback, reflect_id=reflect_id, error=err)
        try:
            _write_json(bundle_path, bundle)
        except Exception:
            pass
        print(
            f"[reflect_hook] external evidence error (non-fatal): {err}\n{traceback.format_exc()}",
            file=sys.stderr,
        )
        attestation = compute_external_attestation(bundle, plan_dict if plan_dict else {})
        try:
            update_innovation_audit_external(
                repo_root,
                attestation,
                attested_depth=compute_attested_depth(
                    fingerprint, bundle, plan_dict if plan_dict else {}
                ),
            )
        except Exception:
            pass
        return bundle, plan_dict, attestation


# ── T4/ADR-6：reflect cycle「寻找」(find) 阶段（评估 verify 的事双胞胎）──────
def should_run_find_phase(plateau_active: bool, depth: str | None) -> bool:
    """寻找触发 = plateau ∧ depth ∈ {different, novel}。

    比 verify 的 _should_deepen_plateau 宽——后者还要 not_attested_extend 前提；
    寻找是撞墙后向外捞可借力的候选部件，不要求「未背书的 extend」。
    routine/derived 不触发（撞墙在已知范式内，无向外捞的必要）。
    """
    if not plateau_active:
        return False
    return str(depth or "").strip().lower() in _FIND_DEPTH_SET


def _extract_find_candidates(
    bundle: dict[str, Any], *, depth: str, reflect_id: str,
) -> dict[str, Any]:
    """从执行后的 bundle 抽「可借力的候选部件」→ 反馈边数据（注入下轮）。

    纯函数（无 IO）：paper hits → 论文候选（title/url/arxiv_id）；
    method_excerpt/impl_hints → 方法段；routine_attestation.github_ecosystem
    → 生态库候选。空 bundle → 空候选（triggered 仍 True：已执行，只是没捞到）。
    """
    paper = (bundle.get("paper") or {}) if isinstance(bundle, dict) else {}
    attestation = (
        ((bundle.get("code") or {}).get("routine_attestation") or {})
        if isinstance(bundle, dict)
        else {}
    )

    paper_candidates: list[dict[str, str]] = []
    for hit in (paper.get("hits") or [])[:_FIND_CANDIDATES_CAP]:
        if not isinstance(hit, dict):
            continue
        title = str(hit.get("title") or "").strip()
        if not title:
            continue
        cand: dict[str, str] = {"title": title, "url": _derive_url(hit)}
        aid = str(hit.get("arxiv_id") or "").strip()
        if aid:
            cand["arxiv_id"] = aid
        paper_candidates.append(cand)

    ecosystem_candidates: list[dict[str, str]] = []
    for eco in (attestation.get("github_ecosystem") or [])[:_FIND_CANDIDATES_CAP]:
        if not isinstance(eco, dict):
            continue
        name = str(eco.get("name") or "").strip()
        if not name:
            continue
        ecosystem_candidates.append({
            "name": name,
            "url": str(eco.get("url") or "").strip(),
            "description": str(eco.get("description") or "").strip(),
        })

    # T9/ADR-9：linked_code raw 片段 → code_candidates（寻找反馈边：不止 metadata，
    # 把 top impl_candidate 的实际代码内容喂给下轮作借力素材）。
    code_candidates: list[dict[str, str]] = []
    for lc in (paper.get("linked_code") or [])[:_FIND_CANDIDATES_CAP]:
        if not isinstance(lc, dict):
            continue
        repo = str(lc.get("repo") or "").strip()
        path = str(lc.get("path") or "").strip()
        if not repo and not path:
            continue
        code_candidates.append({
            "repo": repo,
            "path": path,
            "url": str(lc.get("url") or "").strip(),
            "excerpt": str(lc.get("content_excerpt") or "").strip(),
        })

    return {
        "triggered": True,
        "depth": depth,
        "reflect_id": reflect_id,
        "paper_candidates": paper_candidates,
        "method_excerpt": str(paper.get("method_excerpt") or "").strip(),
        "impl_hints": list(paper.get("impl_hints") or []),
        "ecosystem_candidates": ecosystem_candidates,
        "code_candidates": code_candidates,
    }


def _force_find_plan(ctx: RouterContext) -> ExternalPlan:
    """强制 P3+ 全文 + github_ecosystem，保证寻找拿到 arXiv 全文方法段（ADR-6）。

    verify 可能因 _should_deepen_plateau 不满足（无 not_attested_extend）停在 P2、
    没取全文；寻找用自己的 forced plan 兜底 P3+。PDF 走缓存（pdf.py 复用已有
    {aid}.pdf），第二次取 http_calls=0，故寻找的二次执行廉价（plateau 稀有）。
    """
    plan = build_external_plan(ctx)
    if _paper_depth_rank(plan.paper_depth) < 3:
        plan = dataclasses.replace(plan, paper_depth="P3")
    if not plan.github_ecosystem:
        plan = dataclasses.replace(plan, github_ecosystem=True)
    return plan


def _empty_find_candidates() -> dict[str, Any]:
    """寻找未触发/失败时的空返回形状（与成功返回同 schema，triggered=False）。"""
    return {
        "triggered": False,
        "depth": "",
        "reflect_id": "",
        "paper_candidates": [],
        "method_excerpt": "",
        "impl_hints": [],
        "ecosystem_candidates": [],
        "code_candidates": [],
    }


def run_find_phase(
    repo_root: Path,
    *,
    gate_label: str,
    last_round: dict,
    tam_result,
    innovation_warnings: list[dict],
    reflect_id: str,
    fingerprint: dict | None = None,
    dry_run: bool = False,
    llm_query_fn=None,
) -> dict[str, Any]:
    """T4/ADR-6：reflect cycle「寻找」阶段。Never raises.

    触发 = plateau ∧ depth ∈ {different, novel}（见 should_run_find_phase）。
    触发 → 强制 P3+ 全文 + github_ecosystem 执行 plan → 抽候选部件 → 写
    saved/find_candidates.json（反馈边数据，注入下轮 run context；catalog 落盘
    在 T8，本 ticket 只产反馈边数据）。不触发/失败 → 返回空候选、不写文件。
    """
    find_path = repo_root / "saved" / _FIND_CANDIDATES_FILENAME
    try:
        ctx = _build_router_context(
            repo_root,
            gate_label=gate_label,
            last_round=last_round or {},
            tam_result=tam_result,
            innovation_warnings=innovation_warnings,
            fingerprint=fingerprint,
            llm_query_fn=llm_query_fn,
        )
        # ⚠️ 刻意不用 ctx.plateau_active（那是 verify/评估 的全局 agent.plateau_rounds 判定）；
        # find 的触发阈值按 mode 走（seek_plateau_rounds，ADR-8）—— 别「简化」回 ctx.plateau_active。
        if not should_run_find_phase(_infer_seek_plateau_active(repo_root), ctx.innovation_depth):
            # 非触发：清掉上一轮触发的残留，防陈旧候选泄漏进下轮。反馈边只喂「下一轮」，
            # 不触发说明本 reflect 不再向外捞 → 上一轮的候选已过期，删之（paper_hint 靠
            # round_decision.json 每轮整体覆写天然无陈旧；find_candidates.json 需显式清）。
            try:
                find_path.unlink(missing_ok=True)
            except OSError:
                pass
            return _empty_find_candidates()
        plan = _force_find_plan(ctx)
        bundle = execute_plan(
            plan, dry_run=dry_run, repo_root=repo_root, llm_query_fn=llm_query_fn,
        )
        candidates = _extract_find_candidates(
            bundle, depth=ctx.innovation_depth, reflect_id=reflect_id,
        )
        _write_json(find_path, candidates)
        # T8/ADR-3 反馈边落盘：本轮 find 候选作为软 overlay 记录（find_discoveries 表，
        # key=reflect_id，source=reflect_id 可回滚）。原始论文/生态候选非「已知技法」，
        # 不进技法表、不触 soft-hint（soft-hint 只看 primary_keys 表）、不碰 depth；
        # 留作可回滚的 find 痕迹 + 供后续 curation（T9+ 把论文 → 技法条目）。非致命。
        try:
            append_catalog_overlay(
                repo_root,
                source=reflect_id,
                table="find_discoveries",
                key=reflect_id,
                entry={
                    "depth": ctx.innovation_depth,
                    "paper_candidates": candidates.get("paper_candidates") or [],
                    "ecosystem_candidates": candidates.get("ecosystem_candidates") or [],
                    "code_candidates": candidates.get("code_candidates") or [],
                },
            )
        except Exception:
            pass
        print(
            f"[reflect_hook] find phase triggered (depth={ctx.innovation_depth}): "
            f"{len(candidates['paper_candidates'])} paper / "
            f"{len(candidates['ecosystem_candidates'])} ecosystem / "
            f"{len(candidates['code_candidates'])} code candidates",
            file=sys.stderr,
        )
        return candidates
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        print(
            f"[reflect_hook] find phase error (non-fatal): {err}\n{traceback.format_exc()}",
            file=sys.stderr,
        )
        return _empty_find_candidates()
