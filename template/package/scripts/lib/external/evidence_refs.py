"""Ticket 04: 外部证据包 → round_decision 的 evidence_refs / paper_hint。

主体闭环切面（spec §4）：summarize_evidence 把外部证据包的关键命中压成
{evidence_refs, paper_hint}，供 finalize_round 落盘 round_decision.json、
build-run-context 注入下轮 step 1（**字段注入**，非 direction_full 文本注入——
两条注入通道语义不同，见 spec §4 / ticket 04 Notes）。

- evidence_refs: 本轮 bundle 关键命中（标题+URL+可追溯 arxiv_id），封顶 _EVIDENCE_REFS_CAP。
- paper_hint: 喂给下轮 agent 的方法摘要短文（首篇标题 + method_excerpt + impl_hints）。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# evidence_refs 封顶：防 round_decision.json 被海量命中撑大（spec §5 测）。
_EVIDENCE_REFS_CAP = 5
# impl_hints 拼进 paper_hint 时的字符上限（防 prompt 注入过长）。
_IMPL_HINTS_MAX_CHARS = 300

# reflect_hook 落盘的本轮外部证据包（单文件，每轮 reflect 覆写）。
_BUNDLE_FILENAME = "evidence_bundle.json"
# T4/ADR-6：寻找阶段落盘的候选部件（每轮触发才写；不触发/失败则无此文件）。
_FIND_CANDIDATES_FILENAME = "find_candidates.json"


def _derive_url(hit: dict[str, Any]) -> str:
    """hit 的 URL：优先 url 字段；缺则从 arxiv_id 兜底构造 abs 链接。"""
    url = str(hit.get("url") or "").strip()
    if url:
        return url
    aid = str(hit.get("arxiv_id") or "").strip()
    if aid:
        return f"https://arxiv.org/abs/{aid}"
    return ""


def summarize_evidence(bundle: dict[str, Any]) -> dict[str, Any]:
    """外部证据包 dict → {evidence_refs, paper_hint}。

    纯函数（无 IO）：调用方传 saved/evidence_bundle.json 的解析结果。

    空 bundle / 无命中 → {evidence_refs: [], paper_hint: ""}（AC #4 空包不崩）。
    """
    paper = (bundle.get("paper") or {}) if isinstance(bundle, dict) else {}
    raw_hits = paper.get("hits") or []

    refs: list[dict[str, str]] = []
    for hit in raw_hits[:_EVIDENCE_REFS_CAP]:
        if not isinstance(hit, dict):
            continue
        title = str(hit.get("title") or "").strip()
        if not title:
            continue
        ref: dict[str, str] = {"title": title, "url": _derive_url(hit)}
        aid = str(hit.get("arxiv_id") or "").strip()
        if aid:
            ref["arxiv_id"] = aid  # 可追溯（story #16）：回查 bundle
        refs.append(ref)

    method_excerpt = str(paper.get("method_excerpt") or "").strip()
    impl_hints = paper.get("impl_hints") or []

    parts: list[str] = []
    if refs:
        parts.append(refs[0]["title"])
    if method_excerpt:
        parts.append(method_excerpt)
    hint_str = " ".join(parts)

    hints_joined = "; ".join(str(h) for h in impl_hints if str(h).strip())
    if hints_joined:
        hints_joined = hints_joined[:_IMPL_HINTS_MAX_CHARS]
        hint_str = f"{hint_str} [hints: {hints_joined}]" if hint_str else f"[hints: {hints_joined}]"

    return {"evidence_refs": refs, "paper_hint": hint_str}


def _read_bundle_json(saved_dir: Path) -> dict[str, Any]:
    """读 saved/evidence_bundle.json → dict；缺失/损坏 → {}（spec §5 不崩）。

    非 no-fallback 违规：本函数契约即「无可用 bundle 返回空」，是 round_decision
    落盘的文档化降级，非静默吞错——调用方据此写空 evidence_refs。
    """
    bundle_path = saved_dir / _BUNDLE_FILENAME
    if not bundle_path.is_file():
        return {}
    try:
        data = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # corrupt JSON / 读失败 → 当作无 bundle（round_decision 必须落盘）
        return {}
    return data if isinstance(data, dict) else {}


def _read_find_candidates(saved_dir: Path) -> dict[str, Any]:
    """读 saved/find_candidates.json → dict；缺失/损坏 → {}（T4/ADR-6）。

    寻找阶段仅在 plateau ∧ depth∈{different,novel} 时触发写盘；其余轮无此文件 → {}。
    同 _read_bundle_json 的文档化降级契约：返回空表示「本轮无寻找反馈」，非吞错。
    """
    find_path = saved_dir / _FIND_CANDIDATES_FILENAME
    if not find_path.is_file():
        return {}
    try:
        data = json.loads(find_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def collect_round_evidence(saved_dir: Path | str) -> dict[str, Any]:
    """读本轮 saved/ 外部证据 → {evidence_refs, paper_hint, find_candidates}。

    调用方：experiment.finalize_round（落盘 round_decision.json 前合并进 ev）。

    优先级（spec §4 AC #3「注入优先读 library，若有」）：
      1. library（saved/external_evidence/library.jsonl）—— **ticket 03 hook**：
         当前 library 未建，分支空过，走 bundle。ticket 03 落地时在此插库优先读。
      2. bundle（saved/evidence_bundle.json）—— 当前真源。
      3. find_candidates（saved/find_candidates.json）—— **T4/ADR-6**：寻找阶段
         撞墙后捞的可借力候选部件，注入下轮 run context（反馈边数据；
         catalog 落盘在 T8）。无则 {}。
    两者皆无 → {evidence_refs: [], paper_hint: "", find_candidates: {}}（AC #4 空包不崩）。
    永不返回 None：调用方可直接 ev.update(collect_round_evidence(...))。
    """
    saved = Path(saved_dir)
    # [ticket 03 hook] library-first：saved/external_evidence/library.jsonl 若存在
    # 且非空 → 优先读（去重后的精炼库）。当前未建，落到 bundle。
    bundle = _read_bundle_json(saved)
    out = summarize_evidence(bundle)
    out["find_candidates"] = _read_find_candidates(saved)
    return out
