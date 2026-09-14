"""synthesis 综合推理：跨证据 → 下一步建议（带「为什么不照搬」硬约束）。
"""
from __future__ import annotations

import json
import re
from typing import Any

_VALID_CODE_AREAS = frozenset({"workspace/model", "workspace/loss", "workspace/data", "contract"})


def _bundle_paper_urls(external_bundle: dict | None) -> set[str]:
    """从 external_bundle 抽出 paper.hits 所有 url（供 evidence_refs 清洗）。"""
    if not external_bundle:
        return set()
    paper = external_bundle.get("paper") or {}
    hits = paper.get("hits") or []
    out: set[str] = set()
    for h in hits:
        if not isinstance(h, dict):
            continue
        u = (h.get("url") or h.get("link") or "").strip()
        if u:
            out.add(u)
    return out


def _letters_from_tam_list(tam_not_attested: list[str] | None) -> set[str]:
    out: set[str] = set()
    for t in tam_not_attested or []:
        mm = re.search(r"Tier\s*([A-E])", str(t), re.I)
        if mm:
            out.add(mm.group(1).upper())
        else:
            tl = str(t).strip()[:1].upper()
            if tl in "ABCDE":
                out.add(tl)
    return out


def _tier_letter_from_field(tier_raw: str) -> str:
    m = re.search(r"Tier\s*([A-E])", tier_raw, re.I)
    if m:
        return m.group(1).upper()
    letter = tier_raw.strip()[:1].upper()
    return letter if letter in "ABCDE" else ""


def _format_findings(findings: list[dict], *, selectable_letters: set[str] | None = None) -> str:
    if not findings:
        return "  （无）"
    lines = []
    for f in findings[:5]:
        t = f.get("tier", "?")
        letter = _tier_letter_from_field(str(t))
        ca = f.get("code_area", "?")
        s = str(f.get("summary", "?"))[:120]
        w = str(f.get("why", ""))[:80]
        tag = ""
        if selectable_letters is not None and letter and letter not in selectable_letters:
            tag = " [参考-only，不可作 synthesis.tier]"
        lines.append(f"  - [{t}/{ca}] {s}{tag}  why={w}")
    return "\n".join(lines)


def _format_hits(hits: list[dict]) -> str:
    if not hits:
        return "  （无）"
    lines = []
    for h in hits[:10]:
        u = (h.get("url") or h.get("link") or "?").strip()
        t = str(h.get("title") or "?")[:80]
        lines.append(f"  - {u}  ({t})")
    return "\n".join(lines)


def _format_method_excerpt(paper: dict) -> str:
    """A1: 渲染 PDF 全文方法段。空 → 返回 ''。

    method_excerpt 优先（更精）→ cap=1500；fallback excerpt → cap=2500。
    都空 → 整段不渲染（返回 ''）。
    """
    method_excerpt = (paper.get("method_excerpt") or "").strip()
    excerpt = (paper.get("excerpt") or "").strip()
    if method_excerpt:
        body = method_excerpt
        cap = 1500
    elif excerpt:
        body = excerpt
        cap = 2500
    else:
        return ""
    truncated = False
    if len(body) > cap:
        body = body[:cap]
        truncated = True
    out = "<paper_method_excerpt>\n"
    out += "[PDF FULL-TEXT EXCERPT — read carefully, not a hint]\n"
    out += body
    if truncated:
        out += "\n[TRUNCATED]"
    out += "\n</paper_method_excerpt>"
    return out


def _tier_json_example(tam_not_attested: list[str] | None) -> str:
    letters = sorted(_letters_from_tam_list(tam_not_attested))
    if len(letters) == 1:
        return letters[0]
    if letters:
        return "|".join(letters)
    return "?"


def _format_pending_skeleton_queue(current_round: int) -> str:
    """A2: 渲染 saved/skeleton_queue.json 中 pending_fill 段。"""
    if current_round <= 0:
        return ""
    try:
        from pathlib import Path
        import json as _json
        import os as _os
        saved_dir = Path(_os.environ.get("NN_SAVED_DIR", "saved"))
        qpath = saved_dir / "skeleton_queue.json"
        if not qpath.exists():
            return ""
        if _os.environ.get("NN_SKELETON_QUEUE_ENABLED") == "0":
            return ""
        queue = _json.loads(qpath.read_text())
    except Exception:
        return ""

    items = [x for x in queue.get("items", []) if x.get("status") == "pending_fill"]
    if not items:
        return ""

    lines = ["<pending_skeleton_queue>"]
    for item in items:
        deadline = item.get("deadline_round", 0)
        reg = item.get("registry", "?")
        name = item.get("registry_name") or item.get("class_name", "?")
        ref = item.get("paper_ref", "?")
        created = item.get("round", "?")
        if current_round > deadline:
            tag = f"[OVERDUE] {name} ({reg}) — {ref} — created R{created}, deadline R{deadline} (missed by {current_round - deadline} round, fill NOW)"
        elif deadline - current_round == 1:
            tag = f"[DUE NEXT ROUND] {name} ({reg}) — {ref} — created R{created}, deadline R{deadline}"
        else:
            tag = f"[PENDING] {name} ({reg}) — {ref} — created R{created}, deadline R{deadline}"
        lines.append(tag)
    lines.append("</pending_skeleton_queue>")
    return "\n".join(lines)


def build_synthesis_prompt(
    *,
    phase1: dict,
    phase2: dict,
    external_bundle: dict | None,
    tam_not_attested: list[str] | None,
    fingerprint: dict | None,
    capacity_card: dict | None = None,
    scaling_recommendation: dict | None = None,
    hardcoded_context: str = "",
    exhaustion_metric: dict | None = None,
    current_round: int = 0,
) -> str:
    """构造 synthesis prompt：含五类锚文本（key_insight / findings / paper hits / TAM / fingerprint）
    + 4 类反射上下文（M1 容量 / M2 经验律 / M3 硬编码 / M4 穷尽度）。

    新增 4 个 keyword-only 入参全部 default None/空，向后兼容：
    - 未传 → 不出对应段（旧调用方不受影响）
    - 传了空 dict/空串 → 同样不出段
    """
    p1 = phase1 or {}
    p2 = phase2 or {}
    key_insight = p1.get("key_insight") or "（无）"
    wall = bool(p1.get("wall_crash"))
    streak_tier = p1.get("streak_tier") or "?"
    streak_count = p1.get("streak_count") or 0

    findings = p2.get("findings") or []
    fp = fingerprint or {}
    fp_line = f"routine/derived/different = {fp.get('innovation', '?')}" if fp else "（无创新指纹）"

    paper = (external_bundle or {}).get("paper") or {}
    hits = paper.get("hits") or []
    tam_list = list(tam_not_attested or [])
    selectable = _letters_from_tam_list(tam_list)
    tier_example = _tier_json_example(tam_list)

    # ── 4 类反射上下文段（按需渲染）────────────────────
    refl_lines: list[str] = []
    # M1 场景容量卡
    if capacity_card and any(v is not None for v in capacity_card.values()):
        m1_lines = [f"- {k}: {v}" for k, v in capacity_card.items() if v is not None]
        refl_lines.append("## M1 场景容量卡\n" + "\n".join(m1_lines))
    # M2 经验律推荐
    if scaling_recommendation:
        m2_lines = []
        for k, v in scaling_recommendation.items():
            if k.startswith("delta_"):
                m2_lines.append(f"- 跨场景 delta: {k} = {v}")
            else:
                m2_lines.append(f"- 建议 {k} = {v}")
        if m2_lines:
            refl_lines.append("## M2 经验律推荐\n" + "\n".join(m2_lines))
    # M3 硬编码可见性
    if hardcoded_context and hardcoded_context.strip():
        refl_lines.append("## M3 workspace 硬编码可见性\n" + hardcoded_context.strip())
    # M4 同场景穷尽度
    if exhaustion_metric and (
        exhaustion_metric.get("diversity")
        or exhaustion_metric.get("leader")
        or exhaustion_metric.get("tam_reconcile")
    ):
        m4_lines = []
        d = exhaustion_metric.get("diversity") or {}
        if d:
            m4_lines.append(
                f"- 台账窗口: {d.get('window', 0)} 条，"
                f"exhaustion_score = {exhaustion_metric.get('exhaustion_score', 0):.2f}, "
                f"suggestion = `{exhaustion_metric.get('suggestion', 'continue_exploration')}`"
            )
        ld = exhaustion_metric.get("leader") or {}
        if ld:
            m4_lines.append(
                f"- Leader gap = {ld.get('gap', 0):.4f}, "
                f"confidence = {ld.get('confidence', '?')}"
            )
        tr = exhaustion_metric.get("tam_reconcile") or {}
        if tr:
            m4_lines.append(
                f"- TAM action = {tr.get('action', '?')}, "
                f"tier {tr.get('tier', '?')} "
                f"({tr.get('tam_before', '?')} → {tr.get('tam_after', '?')})"
            )
        if m4_lines:
            refl_lines.append("## M4 同场景穷尽度\n" + "\n".join(m4_lines))

    refl_block = ""
    if refl_lines:
        refl_block = (
            "\n## 反射上下文（4 类，由 reflect.py Phase 0.5 注入）\n"
            + "\n\n".join(refl_lines)
            + "\n"
        )

    return (
        "You are the synthesis phase of a reflect round.\n"
        "Cross-reference 外部证据 + 历史信号 + TAM + 创新指纹 + 4 类反射上下文 → 推导下一步建议。\n"
        "\n"
        "## 硬约束（违反任一 → parse 判失败 → synthesis=None → 回退现有建议）\n"
        "1. adaptation 必填且非空（三要素：差异 + 为什么不照搬 + 改造点）。空/复述论文 → 失败。\n"
        "2. reasoning_chain ≥ 2 步。少于 2 步 → 失败。\n"
        "3. evidence_refs url 必须在下方「合法 url 池」内；不在则清空该项（禁止编造）。\n"
        "4. tier 必须落在 not_attested_tiers 内（与 JSON 示例一致）。\n"
        f"   not_attested_tiers = {tam_list}\n"
        "5. 标注 [参考-only] 的 Phase2 finding 不可作为 synthesis.tier。\n"
        "\n"
        "## 输入\n"
        f"- key_insight: {key_insight}\n"
        f"- 撞墙: {wall} (Tier {streak_tier} × {streak_count})\n"
        f"- 创新指纹: {fp_line}\n"
        f"- Phase2 findings ({len(findings)} 条):\n"
        f"{_format_findings(findings, selectable_letters=selectable)}\n"
        f"- 合法 url 池（evidence_refs 必须从下列 url 中选；不在则清空该项）:\n"
        f"{_format_hits(hits)}\n"
        f"{_format_method_excerpt(paper)}\n"
        f"{refl_block}\n"
        f"{_format_pending_skeleton_queue(current_round)}\n"
        "## 产出（裸 JSON，无 markdown fence）\n"
        "{\n"
        '  "next_step": "一句话具体下一步",\n'
        '  "code_area": "workspace/model|workspace/loss|workspace/data|contract",\n'
        f'  "tier": "{tier_example}",\n'
        '  "single_diff_var": "本轮单一差分变量",\n'
        '  "reasoning_chain": ["证据+历史 → 推论1", "推论1 + 撞墙 → 推论2", "..."],\n'
        '  "adaptation": "差异 + 为什么不照搬 + 改造点（≥30 字符）",\n'
        '  "evidence_refs": ["url from 合法 url 池"]\n'
        "}\n"
    )


def _extract_json_text(raw: str) -> tuple[str | None, str | None]:
    """从 LLM 输出提取 JSON 文本；失败返回 (None, reason)。"""
    if not raw or not raw.strip():
        return None, "empty_raw"
    s = raw.strip()
    if s.startswith("```"):
        parts = s.split("```")
        if len(parts) < 2:
            return None, "markdown_fence_empty"
        s = parts[1]
        if s.startswith("json"):
            s = s[4:]
        s = s.strip()
    if not (s.startswith("{") and s.endswith("}")):
        m = re.search(r"\{[\s\S]*\}", s)
        if not m:
            return None, "no_json_object"
        s = m.group(0)
    return s, None


def diagnose_synthesis_parse(
    raw: str,
    *,
    external_bundle: dict | None,
    tam_not_attested: list[str] | None,
) -> str | None:
    """解析诊断：通过返回 None，失败返回可读 reason（供 reflect stderr / 落盘）。"""
    s, err = _extract_json_text(raw)
    if err:
        return err
    assert s is not None
    try:
        obj = json.loads(s)
    except json.JSONDecodeError as ex:
        return f"json_decode: {ex}"

    if not isinstance(obj, dict):
        return "not_dict"

    required = {"next_step", "code_area", "tier", "single_diff_var",
                "reasoning_chain", "adaptation", "evidence_refs"}
    missing = required - set(obj.keys())
    if missing:
        return f"missing_fields: {sorted(missing)}"

    adapt = str(obj.get("adaptation") or "").strip()
    if not adapt:
        return "adaptation_empty"
    if len(adapt) < 30:
        return f"adaptation_too_short: len={len(adapt)}"

    chain = obj.get("reasoning_chain")
    if not isinstance(chain, list):
        return f"reasoning_chain_not_list: {type(chain).__name__}"
    if len(chain) < 2:
        return f"reasoning_chain_too_short: len={len(chain)}"

    tier_raw = str(obj.get("tier") or "").strip()
    tier_letter = _tier_letter_from_field(tier_raw)
    if not tier_letter:
        return f"invalid_tier: {tier_raw!r}"

    valid_letters = _letters_from_tam_list(tam_not_attested)
    if not valid_letters:
        return "tam_not_attested_empty"
    if tier_letter not in valid_letters:
        return f"tier_not_in_not_attested: got={tier_letter} valid={sorted(valid_letters)}"

    ca = str(obj.get("code_area") or "").strip()
    if ca not in _VALID_CODE_AREAS:
        return f"invalid_code_area: {ca!r}"
    if not str(obj.get("next_step") or "").strip():
        return "next_step_empty"
    if not str(obj.get("single_diff_var") or "").strip():
        return "single_diff_var_empty"
    return None


def parse_synthesis(
    raw: str,
    *,
    external_bundle: dict | None,
    tam_not_attested: list[str] | None,
) -> dict[str, Any] | None:
    """解析 LLM 响应，应用 4 条硬约束；任一 fail → None。"""
    reason = diagnose_synthesis_parse(
        raw, external_bundle=external_bundle, tam_not_attested=tam_not_attested,
    )
    if reason:
        return None

    s, _ = _extract_json_text(raw)
    assert s is not None
    obj = json.loads(s)

    bundle_urls = _bundle_paper_urls(external_bundle)
    raw_refs = obj.get("evidence_refs")
    if not isinstance(raw_refs, list):
        raw_refs = []
    cleaned = [str(r).strip() for r in raw_refs
               if isinstance(r, str) and str(r).strip() in bundle_urls]
    obj["evidence_refs"] = cleaned

    tier_letter = _tier_letter_from_field(str(obj.get("tier") or ""))
    obj["tier"] = f"Tier {tier_letter}"
    return obj
