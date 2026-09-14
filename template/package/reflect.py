#!/usr/bin/env python3
"""
Tier-ladder 反思轮：Phase 0 压缩 + Phase 1～3 分析 / 检索 / 成文。

用法（项目根目录）：
    poetry run python reflect.py [--agent claude|cursor] [--max-tokens N]

每轮实验结束后自动调用（`auto-nn-run.sh` 里嵌入），也可单独运行：
    poetry run python reflect.py --agent claude
    poetry run python reflect.py --agent cursor

Phase 0.5 — **Reflect 证据包（REB）**：…  
Phase 0.6 — **Tier Attestation Matrix（TAM）**：… `saved/tier_attestation.json`；**禁止**用 description 计 Tier；pending 须含 `[TAM: …]`。
Phase 0.75 — **创新指纹（innovation_fingerprint）**：keeper vs run config + REB diff → routine/extend/novel；写 `saved/innovation_fingerprint.json`；**Phase 1.85 检索权威**。
Phase 0.7 — **创新审计（innovation_audit）**：Agent 声明 vs 指纹对比 WARN；写入 `saved/innovation_audit.json` 并注入 Phase1。

Phase 0 — **大模型压缩**（**仅**当 ``EXPERIENCE.md`` 字符数 **>** ``--experience-raw-max``（默认 24000）时触发；**不**因 ``PROTOCOL.md`` 变长而触发——PROTOCOL 为只读契约，压缩逻辑不以其长度为准）。**写回瘦身** EXPERIENCE 用 ``scripts/compress-experience.py``（PROTOCOL §7.5.2），与本 Phase0 临时 digest 不同。
    **不**因 ``_runs/results.jsonl`` 行数变多而单独触发；jsonl 仅作 Phase0 输入尾部、并在 Phase1 用 ``--jsonl-rollup-at`` 附趋势提示。
    **必须保留**：禁忌、数据/评估口径、当前最佳、阈值提议、EXPERIENCE `## Tier 状态`（二维矩阵）要点（语义见 PROTOCOL §7.5.1 与 §7.5.1a）、keep/discard 与契约边界等（见 Phase0 提示词）。
    **不得**臆造数值；不确定处写「见 _runs/results.tsv / _runs/exp/*/results.json」。
    **失败**时回退为**规则摘要**；**未触发**则无 Phase0、无规则摘要块（Phase1 仍有用 ledger / evaluation / [反思]）；
    ``--skip-phase0`` 触发后仅规则摘要；``--no-compress`` 关闭一切摘要与 rollup。

Phase 1 — 分析信号：**_runs/results.jsonl** 趋势、**_runs/round_decision.json**（兼容旧名 evaluation_result）、Phase0/规则 **context**、**[反思]** 摘录。
Phase 2 — 外部知识：references/ + 模型知识，产出 JSON。
Phase 3 — **确定性紧凑成文**：合并原「详细分析」要点为短列表，**不**再调用大模型；长摘要写入 **references/auto/**，并更新 **references/REFLECT_INDEX.md** pending；完整 findings 在 **saved/reflect_latest.json**。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

from experiment import load_repo_round_decision, resolve_repo_round_decision_path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

# 确保能 import scripts/lib 下的模块（与 reflect 其他 lib 导入方式一致）
_scripts_dir = _ROOT / "scripts"
if str(_scripts_dir) not in sys.path:
    sys.path.insert(0, str(_scripts_dir))

# 创新维审计（Phase 0.7）
try:
    from lib.innovation_audit import run_innovation_audit, format_innovation_line
except Exception:
    run_innovation_audit = None
    format_innovation_line = None

# Query validation (Task 3；Task 4-5 会用到)
from lib.external.query_validator import (  # noqa: E402
    ValidationVerdict,
    validate_query_alignment,
)
from lib.external.query_refiner import format_validation_feedback  # noqa: E402

try:
    from contract import create_contract
    _c = create_contract({})
    METRIC_KEY = _c.metric_key
    METRIC_DIRECTION = _c.metric_direction
except Exception:
    # torch not available in system python; read directly from contract/__init__.py
    import re as _re
    _contract_file = _ROOT / "contract" / "__init__.py"
    _txt = _contract_file.read_text()
    _mk = _re.search(r'metric_key.*return\s*["\']([^"\']+)["\']', _txt, _re.M)
    _md = _re.search(r'metric_direction.*return\s*["\']([^"\']+)["\']', _txt, _re.M)
    METRIC_KEY = _mk.group(1) if _mk else "?"
    METRIC_DIRECTION = _md.group(1) if _md else "maximize"

# _runs/results.jsonl 防护：避免超长行/超大文件/异常数据拖垮反思流程
_JSONL_MAX_LINE_BYTES = 2 * 1024 * 1024
_JSONL_MAX_LINES = 100_000
_DESC_MAX_CHARS = 8_000
_EXPERIMENT_MAX_CHARS = 512
_EVAL_RESULT_MAX_CHARS = 6_000

# 超长时的确定性摘要（不调用 LLM）
_EXPERIENCE_RAW_MAX_DEFAULT = 24_000
_EXPERIENCE_DIGEST_CHARS_DEFAULT = 10_000
_PROTOCOL_DIGEST_CHARS_DEFAULT = 6_000
_LAST_REFLECT_CHARS_DEFAULT = 4_000
_JSONL_ROLLUP_AT_DEFAULT = 48
_TIER_STATS_ROWS_DEFAULT = 30

# Phase 0：输入截断防护（防止单次 prompt 过大）
_PHASE0_EXPERIENCE_IN_MAX = 48_000
_PHASE0_PROTOCOL_IN_MAX = 32_000
_PHASE0_JSONL_TAIL_ROWS = 72
_PHASE0_OUT_CHARS_DEFAULT = 12_000
_PHASE0_MAX_TOKENS_DEFAULT = 4096

# EXPERIENCE 中与 PROTOCOL/台账硬约束相关的二级标题关键词（标题行须含其一整词）
_EXPERIENCE_PRIORITY_TITLE_KEYS: tuple[str, ...] = (
    "禁忌",
    "当前最佳",
    "KEEP_THRESHOLD",
    "阈值",
    "数据与训练",
    "课题约束",
    "Tier Ladder",
    "值得探索",
    "工程备注",
    "台账状态",
)


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def _load_jsonl_records(p: Path) -> list[dict]:
    """读取 ``_runs/results.jsonl``（或调用方传入的等价路径）：每行一个 JSON 对象；IO/编码/超长行/损坏 JSON 均跳过并告警。"""
    if not p.is_file():
        return []
    out: list[dict] = []
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, start=1):
                if i > _JSONL_MAX_LINES:
                    print(
                        f"[reflect] WARNING: {p} 已超过最大行数 {_JSONL_MAX_LINES}，截断读取。",
                        file=sys.stderr,
                    )
                    break
                nbytes = len(line.encode("utf-8", errors="replace"))
                if nbytes > _JSONL_MAX_LINE_BYTES:
                    print(
                        f"[reflect] WARNING: {p}:{i} 行过长 ({nbytes} bytes)，已跳过。",
                        file=sys.stderr,
                    )
                    continue
                s = line.strip()
                if not s:
                    continue
                try:
                    rec = json.loads(s)
                except json.JSONDecodeError as ex:
                    print(f"[reflect] WARNING: {p}:{i} JSON 跳过: {ex}", file=sys.stderr)
                    continue
                if isinstance(rec, dict):
                    out.append(rec)
                else:
                    print(
                        f"[reflect] WARNING: {p}:{i} 非 object，已跳过（{type(rec).__name__}）。",
                        file=sys.stderr,
                    )
    except OSError as ex:
        print(f"[reflect] WARNING: 无法读取 {p}: {ex}", file=sys.stderr)
        return []
    except MemoryError:
        print(f"[reflect] WARNING: 读取 {p} 时内存不足，已中止加载。", file=sys.stderr)
        return out
    return out


def _safe_metric_cell(raw: object) -> str:
    """主指标单元格 → Phase 1 展示用字符串。"""
    if raw is None:
        return "?"
    if isinstance(raw, str):
        t = raw.strip()
        return t if t else "?"
    if isinstance(raw, bool):
        return "true" if raw else "false"
    if isinstance(raw, (int, float)):
        try:
            x = float(raw)
        except (TypeError, ValueError, OverflowError):
            return "?"
        if math.isnan(x) or math.isinf(x):
            return "?"
        return f"{x:.6f}"
    return str(raw)[:256]


def _clamp_str(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def _format_evaluation_for_phase1(evaluation: dict | None) -> str:
    """将 ``_runs/round_decision.json`` 压成 Phase 1 可嵌入的文本。"""
    if not evaluation:
        return (
            "（无：未找到 _runs/round_decision.json 或为空；"
            "请以 _runs/results.jsonl 与反思摘录为准；"
            "单槽训末由 finalize_round 写入；多槽须在全部 train 结束后执行 python -m contract finalize-round …。）"
        )
    try:
        s = json.dumps(evaluation, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        s = str(evaluation)
    return _clamp_str(s, _EVAL_RESULT_MAX_CHARS)


def _rows_from_jsonl_records(
    records: list[dict],
    metric_key: str,
    *,
    extra_metric_keys: tuple[str, ...] = (),
) -> list[dict[str, str]]:
    """转为 Phase 1 使用的行字典；单条记录异常不影响其它行（对齐 TSV/jsonl schema v2）。"""
    rows: list[dict[str, str]] = []
    for idx, rec in enumerate(records):
        try:
            if not isinstance(rec, dict):
                continue
            m = rec.get("metrics")
            m = m if isinstance(m, dict) else {}
            raw = m.get(metric_key)
            cell = _safe_metric_cell(raw)
            exp = str(rec.get("experiment") or "?").strip() or "?"
            exp = _clamp_str(exp, _EXPERIMENT_MAX_CHARS)
            desc = str(rec.get("description") or "")
            desc = _clamp_str(desc, _DESC_MAX_CHARS)
            row: dict[str, str] = {
                "experiment": exp,
                metric_key: cell,
                "description": desc,
            }
            sid = rec.get("scenario_id")
            if not sid and isinstance(rec.get("scenario_context"), dict):
                sid = rec["scenario_context"].get("scenario_id")
            if sid:
                row["scenario_id"] = _clamp_str(str(sid), 128)
            if rec.get("exp_dir"):
                row["exp_dir"] = _clamp_str(str(rec["exp_dir"]), 512)
            if rec.get("git_commit"):
                row["git_commit"] = _clamp_str(str(rec["git_commit"]), 64)
            for k in extra_metric_keys:
                if k == metric_key or k not in m:
                    continue
                row[k] = _safe_metric_cell(m.get(k))
            lc = rec.get("ledger_context")
            if isinstance(lc, dict) and lc:
                try:
                    row["ledger_context"] = _clamp_str(
                        json.dumps(lc, ensure_ascii=False, default=str),
                        1200,
                    )
                except (TypeError, ValueError):
                    pass
            rows.append(row)
        except Exception as ex:
            print(f"[reflect] WARNING: jsonl 第 {idx + 1} 条展平失败，已跳过: {ex}", file=sys.stderr)
    return rows


def _load_json(p: Path) -> dict | None:
    if p.is_file():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return None


def _load_train_dynamics(exp_dir: Path) -> dict | None:
    """读 <exp_dir>/train_dynamics.json，提取 loss 细节摘要；缺失/损坏 → None。

    仿 _load_json 的单文件 json 读，但加容错（IO / JSON 损坏 → None，reflect 不因
    某个 exp 无 dynamics 阻断）。只读现成 json，不重算——finalize_train_dynamics 训末
    已写盘（scripts/lib/train_dynamics.py:321）。摘要字段照 train_dynamics.json 顶层
    结构（schema_version=1）：anomalies(list) / train_loss.trend / train_val_gap.trend /
    plateau.detected / stop.reason。
    """
    p = Path(exp_dir) / "train_dynamics.json"
    if not p.is_file():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return {
        "anomalies": d.get("anomalies") or [],
        "train_loss": (d.get("train_loss") or {}).get("trend"),
        "train_val_gap": (d.get("train_val_gap") or {}).get("trend"),
        "plateau": (d.get("plateau") or {}).get("detected"),
        "stop_reason": (d.get("stop") or {}).get("reason"),
    }


def _load_text(p: Path, limit: int | None = None) -> str:
    if not p.is_file():
        return ""
    text = open(p, encoding="utf-8").read()
    return text[:limit] if limit else text


def _split_markdown_h2_sections(md: str) -> list[tuple[str, str]]:
    """按二级标题 ``## `` 切分（不含 ``###``）。首段 title 为空表示文首 preamble。"""
    lines = md.splitlines()
    sections: list[tuple[str, str]] = []
    title = ""
    buf: list[str] = []
    for ln in lines:
        if ln.startswith("## ") and not ln.startswith("###"):
            body = "\n".join(buf).strip()
            sections.append((title, body))
            title = ln[3:].strip()
            buf = []
        else:
            buf.append(ln)
    sections.append((title, "\n".join(buf).strip()))
    return sections


def _experience_priority_digest(
    md: str,
    budget: int,
    raw_trigger: int,
) -> tuple[str, bool]:
    """
    EXPERIENCE.md 超长时生成摘要：保留禁忌/最佳/阈值/Tier/数据口径等，省略逐轮长文。
    返回 (digest 文本, 是否发生了压缩)。
    """
    if len(md) <= raw_trigger:
        return "", False
    notice = (
        "## (reflect — EXPERIENCE 压缩摘要)\n\n"
        "规则（对齐 PROTOCOL §1.1 / 台账）：保留禁忌、当前最佳、KEEP_THRESHOLD 提议、"
        "数据与训练入口、课题约束、Tier Ladder、值得探索、工程备注、台账状态等固定区块；"
        "省略中间迭代长篇，完整正文仍以仓库 **EXPERIENCE.md** 为准。\n\n"
        "---\n\n"
    )
    chunks: list[str] = []
    used = len(notice)
    preamble_cap = min(2500, max(800, budget // 5))
    block_cap = max(1200, budget // 4)

    for sec_title, body in _split_markdown_h2_sections(md):
        if sec_title == "":
            if body.strip():
                seg = _clamp_str(body.strip(), preamble_cap) + "\n\n---\n\n"
                if used + len(seg) <= budget:
                    chunks.append(seg)
                    used += len(seg)
            continue
        if any(k in sec_title for k in _EXPERIENCE_PRIORITY_TITLE_KEYS):
            block = f"## {sec_title}\n{body}\n\n"
            if len(block) > block_cap:
                block = f"## {sec_title}\n{_clamp_str(body, block_cap)}\n\n"
            if used + len(block) > budget:
                remain = budget - used - 20
                if remain > 200:
                    block = f"## {sec_title}\n{_clamp_str(body, remain)}\n\n"
                else:
                    break
            if used + len(block) > budget:
                break
            chunks.append(block)
            used += len(block)

    digest = notice + "".join(chunks)
    digest = _clamp_str(digest.strip(), budget)
    return digest, True


def _protocol_head_digest(proto: str, budget: int) -> str:
    """规则回退时附带 PROTOCOL 首部节选（固定 budget）；不因 PROTOCOL 全文长度触发压缩。"""
    if not proto.strip() or budget <= 0:
        return ""
    head = _clamp_str(proto.strip(), budget)
    return (
        "## (reflect — PROTOCOL.md 摘录)\n\n"
        "以下仅为首部节选；**keep/discard、契约修改边界、指标口径** 等以完整 **PROTOCOL.md** 为准。\n\n"
        "---\n\n"
        + head
    )


def _parse_row_metric(val: object) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        x = float(val)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    s = str(val).strip().upper()
    if s in ("?", "DISCARD", "N/A", "NA", ""):
        return None
    try:
        x = float(s)
        if math.isnan(x) or math.isinf(x):
            return None
        return x
    except ValueError:
        return None


def _jsonl_ledger_rollup_line(
    rows: list[dict[str, str]],
    metric_key: str,
    metric_direction: str,
    threshold: int,
) -> str:
    """行数过多时给出历史可解析最优的扫描提示（不替代 evaluation_result）。"""
    if len(rows) <= threshold:
        return ""
    scored: list[tuple[float, str]] = []
    for r in rows:
        x = _parse_row_metric(r.get(metric_key))
        if x is None:
            continue
        scored.append((x, str(r.get("experiment") or "?")))
    if not scored:
        return (
            f"  (jsonl 共 {len(rows)} 条可展平记录；主指标几乎无法解析为数值；"
            "请以 _runs/round_decision.json 与 _runs/exp/*/results.json 为准。)"
        )
    if metric_direction.strip().lower() == "maximize":
        best = max(scored, key=lambda t: t[0])
    else:
        best = min(scored, key=lambda t: t[0])
    return (
        f"  (jsonl 共 {len(rows)} 条；本提示仅列出历史中主指标可解析的**粗略**最优 "
        f"{best[1]}={best[0]:.6f}；Phase1 的「最近一条」趋势仍以文末为准。)"
    )


def _ledger_compact_for_phase0(
    rows: list[dict[str, str]],
    metric_key: str,
    tail_rows: int,
    desc_cap: int = 220,
) -> str:
    """Phase 0 输入：jsonl 展平尾部若干行，制表分隔。"""
    if not rows:
        return "(无 jsonl 行)"
    if tail_rows <= 0:
        tail_rows = min(_PHASE0_JSONL_TAIL_ROWS, len(rows))
    n = min(tail_rows, len(rows))
    tail = rows[-n:]
    lines = []
    for r in tail:
        d = (r.get("description") or "").replace("\t   ", " ").replace("\n", " ")
        d = _clamp_str(d, desc_cap)
        lines.append(
            f"{r.get('experiment', '?')}\t{r.get(metric_key, '?')}\t{d}"
        )
    return "\n".join(lines)


def _dynamics_compact_for_phase0(
    rows: list[dict[str, str]],
    repo_root: Path,
    tail_rows: int,
) -> str:
    """Phase 0 输入：尾部若干 exp 的 train_dynamics loss 细节摘要（per exp 一行）。

    与 _ledger_compact_for_phase0 同口径取 tail（rows[-n:]）；无 exp_dir / 无
    train_dynamics.json 的 exp 跳过；全无 → ''（_phase0_prompt 据此整段省略）。
    渲染规则：有 anomaly 必报（强信号）；无 anomaly 报 train_loss/gap/plateau/stop
    （每个字段非空才显，省 token）。exp_dir 相对路径按 repo_root 解析。
    """
    if not rows:
        return ""
    if tail_rows <= 0:
        tail_rows = min(_PHASE0_JSONL_TAIL_ROWS, len(rows))
    n = min(tail_rows, len(rows))
    tail = rows[-n:]
    lines = []
    for r in tail:
        raw = r.get("exp_dir")
        if not raw:
            continue
        p = Path(raw)
        exp_dir = p if p.is_absolute() else repo_root / p
        dyn = _load_train_dynamics(exp_dir)
        if dyn is None:
            continue
        parts: list[str] = []
        if dyn["anomalies"]:
            parts.append(f"anomalies=[{','.join(dyn['anomalies'])}]")
        if dyn["train_loss"]:
            parts.append(f"train_loss={dyn['train_loss']}")
        if dyn["train_val_gap"]:
            parts.append(f"gap={dyn['train_val_gap']}")
        if dyn["plateau"]:
            parts.append("plateau=True")
        if dyn["stop_reason"]:
            parts.append(f"stop={dyn['stop_reason']}")
        if not parts:
            continue
        lines.append(f"- {r.get('experiment', '?')}: {' · '.join(parts)}")
    return "\n".join(lines)


def _phase0_prompt(
    *,
    experience_body: str,
    protocol_body: str,
    jsonl_compact: str,
    dynamics_compact: str = "",
    metric_key: str,
    metric_direction: str,
    out_max_chars: int,
) -> str:
    dynamics_section = ""
    if dynamics_compact:
        dynamics_section = (
            "---\n"
            "### 训练过程 loss 细节 (train_dynamics, per exp — anomaly 优先看)\n"
            f"{dynamics_compact}\n"
        )
    return textwrap.dedent(f"""\
    You are **Phase 0** of the reflection pipeline: compress noisy project text into ONE Markdown briefing for **Phase 1** (downstream JSON analysis). Do NOT write any file. Output **only** Markdown.

    ## Mandatory preservation (do NOT omit or contradict)
    - **禁忌 / forbidden** items and train vs eval data rules (e.g. which .mat / paths).
    - **当前最佳** experiment name(s) and stated **{metric_key}** values if present (copy from source; never invent).
    - **KEEP_THRESHOLD / 阈值提议** and keep/discard semantics **as described in PROTOCOL** (summarize, do not invent numbers).
    - **Tier Ladder** (#tier-ladder) — directions and status bullets.
    - Contract boundaries: what must NOT be changed in **contract/** during normal iteration.

    ## Compression rules
    - **EXPERIENCE** iterative logs: compress to a **short bullet timeline**; unknown numbers → say 「见 _runs/results.tsv / _runs/exp」.
    - **PROTOCOL**: keep only what Phase1 needs (metrics, keep flow, agent constraints); drop boilerplate.
    - **jsonl tail**: synthesize trend, stalls, disasters, and best run **only from given lines**; do not extrapolate fake metrics.
    - Prefer concise **Chinese** when the source is Chinese.
    - Hard cap ~**{out_max_chars}** characters for your entire answer.

    ## Required output structure (exact headings)
    ## EXPERIENCE 要点
    ## PROTOCOL 要点
    ## _runs/results.jsonl 脉络

    ---
    ### EXPERIENCE.md (may be truncated)
    {experience_body}

    ---
    ### PROTOCOL.md (may be truncated)
    {protocol_body}

    ---
    ### _runs/results.jsonl / ledger tail (compact, tab-separated: experiment \\t metric \\t description)
    {jsonl_compact}
    {dynamics_section}
    metric_key={metric_key}  metric_direction={metric_direction}
    """)


def _last_reflect_section(exp_path: Path, max_chars: int = 4000) -> str:
    """提取 EXPERIENCE.md 最近一条 [反思] 条目，按字符上限截断。"""
    text = _load_text(exp_path)
    if not text:
        return ""
    lines = text.splitlines()
    out: list[str] = []
    in_reflect = False
    for ln in lines:
        if "## [反思]" in ln or "## [reflection]" in ln.lower():
            in_reflect = True
            out = [ln]
        elif in_reflect:
            if ln.startswith("## ") and "## [反思]" not in ln:
                break
            out.append(ln)
    joined = "\n".join(out)
    return _clamp_str(joined, max_chars) if joined else ""


def _last_experience_log_block(after: str) -> str:
    """取 experience-log 内最近一条实验记录块（## [Round N] > ### > blockquote）。"""
    round_pat = re.compile(r"^## \[Round \d+\]", re.M)
    round_matches = list(round_pat.finditer(after))
    if round_matches:
        start = round_matches[-1].start()
        tail = after[start:]
        nxt = re.search(r"\n## (?!\[Round \d+\])", tail[1:])
        if nxt:
            return tail[: nxt.start() + 1].strip()
        return tail.strip()

    legacy_blocks = re.split(r"\n(?=### )", after.strip())
    if legacy_blocks and legacy_blocks[-1].startswith("### "):
        return legacy_blocks[-1]

    bq_pat = re.compile(r"^> 本轮新增", re.M)
    bq_matches = list(bq_pat.finditer(after))
    if bq_matches:
        start = bq_matches[-1].start()
        lines: list[str] = []
        for line in after[start:].splitlines():
            if lines and not line.startswith(">") and line.strip():
                break
            lines.append(line)
        return "\n".join(lines)

    return after.strip()


def _parse_innovation_fields(block: str) -> dict:
    """从单条实验记录块解析 tier / innovation 字段（兼容 markdown ** 与 blockquote）。"""
    info: dict = {}

    m = re.search(
        r"^\s*(?:>+\s*)?(?:-\s*)?(?:\*\*)?tier_this_round(?:\*\*)?\s*:\s*([^\n]+)",
        block,
        re.I | re.M,
    )
    if m:
        tier_m = re.search(r"([A-Ea-e])", m.group(1))
        if tier_m:
            info["tier_this_round"] = tier_m.group(1).upper()

    m = re.search(
        r"^\s*(?:>+\s*)?(?:-\s*)?(?:\*\*)?innovation_depth(?:\*\*)?\s*:\s*([^\n]+)",
        block,
        re.I | re.M,
    )
    if m:
        depth_m = re.match(r"(routine|extend|novel)", m.group(1).strip().lower())
        if depth_m:
            info["innovation_depth"] = depth_m.group(1)

    m = re.search(
        r"^\s*(?:>+\s*)?(?:-\s*)?(?:\*\*)?innovation_rationale(?:\*\*)?\s*:\s*(.+)",
        block,
        re.I | re.M | re.S,
    )
    if m:
        raw_lines: list[str] = []
        for i, line in enumerate(m.group(1).splitlines()):
            if i > 0 and re.match(r"^\s*(?:>+\s*)?(?:-\s*)?\*\*", line):
                break
            raw_lines.append(line)
        rationale = "\n".join(raw_lines).strip()
        rationale = re.sub(r"^>\s?", "", rationale, flags=re.M).strip()
        if rationale:
            info["innovation_rationale"] = rationale

    return info


def _extract_last_round_innovation(exp_path: Path) -> dict:
    """从 EXPERIENCE.md 最近一条实验记录中提取 tier/innovation 字段，供 Phase 0.7 / 1.85。"""
    text = _load_text(exp_path)
    if not text:
        return {}
    marker = "<!-- experience-log-start -->"
    if marker not in text:
        return {}
    after = text.split(marker, 1)[1]
    if "<!-- experience-log-end -->" in after:
        after = after.split("<!-- experience-log-end -->", 1)[0]
    last = _last_experience_log_block(after)
    if not last:
        return {}
    return _parse_innovation_fields(last)


def _resolve_reflect_gate(root: Path, args, num_rows: int) -> str:
    """Resolve reflect gate label: CLI override > auto (--run) > manual hand-run."""
    override = (getattr(args, "reflect_gate", None) or "").strip()
    if override:
        return override
    run_arg = getattr(args, "run", None)
    if run_arg is None:
        return "manual:reflect_invoked"
    from lib.run_ledger_summary import agent_config, reflect_gate_decision  # noqa: WPS433

    plateau_n, interval = agent_config(root)
    return reflect_gate_decision(root, run=int(run_arg), interval=interval, plateau_n=plateau_n)


def _claude_invoke_cmd(*extra: str) -> list[str]:
    """claude -p 或 cc-switch 包装（ccg/ccm/ccx）；读 NN_AGENT_CLAUDE_CMD / NN_CC_SWITCH_HOME。"""
    from lib.agent_cli import claude_invoke_argv  # noqa: WPS433

    frontend = os.environ.get("NN_AGENT_CLAUDE_CMD", "claude").strip()
    if frontend == "claude":
        return claude_invoke_argv(*extra)
    if frontend in ("ccg", "ccm", "ccx"):
        tail = ["-p", "--dangerously-skip-permissions", *extra]
        prov = {"ccg": "zhipu-glm", "ccm": "minimax", "ccx": "xiaomi"}[frontend]
        return ["cc-switch", "start", "claude", prov, "--", "claude", *tail]
    raise RuntimeError(f"invalid NN_AGENT_CLAUDE_CMD: {frontend!r}")


_AGENT_CALL_TIMEOUT_DEFAULT = 600  # 秒；Phase 1 是大 prompt 分析，300s 偶发超时
# Phase 1.85 查询生成 LLM 调用：只要 3-6 词查询，输出极短，max_tokens 小（省）
_QUERY_GEN_MAX_TOKENS = 64


def _agent_call_timeout() -> int:
    """单次 agent 调用超时（秒）；NN_AGENT_CALL_TIMEOUT 覆盖。"""
    raw = os.environ.get("NN_AGENT_CALL_TIMEOUT")
    if raw:
        try:
            val = int(raw)
            if val > 0:
                return val
        except ValueError:
            pass
    return _AGENT_CALL_TIMEOUT_DEFAULT


def _call_agent(prompt: str, agent: str, max_tokens: int) -> str:
    """调用 claude -p 或 agent -p，返回 stdout。

    超时容错：单次达 timeout 不立刻失败、重试 1 次（覆盖瞬时慢/排队）；
    两次都超时则抛 TimeoutExpired，由调用方 except 降级到 fallback defaults。
    非超时错误（非零 exit）立刻抛、不重试。
    """
    prompt_bytes = prompt.encode()
    env = os.environ.copy()
    home_override = os.environ.get("NN_CC_SWITCH_HOME")
    if home_override:
        env["HOME"] = home_override

    if agent == "cursor":
        cmd = ["agent", "-p", "--trust", "--yolo", "--approve-mcps",
               "--workspace", str(_ROOT)]
    else:  # claude
        cmd = _claude_invoke_cmd()

    timeout = _agent_call_timeout()
    for attempt in (1, 2):
        try:
            proc = subprocess.run(
                cmd, input=prompt_bytes, env=env,
                capture_output=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            print(f"[reflect] _call_agent attempt {attempt}/2 timed out ({timeout}s)",
                  file=sys.stderr)
            continue
        if proc.returncode != 0:
            err = proc.stderr.decode(errors="replace")
            raise RuntimeError(f"agent call failed (exit {proc.returncode}): {err[:300]}")
        return proc.stdout.decode(errors="replace")

    raise subprocess.TimeoutExpired(cmd, timeout)


# ---------------------------------------------------------------------------
# Phase prompts
# ---------------------------------------------------------------------------

def _apply_phase1_anchors(phase1: dict, repo_root: Path) -> None:
    """脚本回填 metric_leader / code_baseline（TSV 为准，覆盖 LLM 偏离）。"""
    try:
        from lib.ledger_anchor import code_baseline_entry, metric_leader_row  # noqa: WPS433
    except ImportError:
        return
    leader = metric_leader_row(repo_root)
    baseline = code_baseline_entry(repo_root)
    if leader:
        phase1["best_exp"] = leader.experiment
        phase1["best_metric"] = str(leader.metric_value)
        phase1["metric_leader_exp"] = leader.experiment
        phase1["metric_leader_metric"] = str(leader.metric_value)
    if baseline:
        exp_label = baseline.experiment or Path(baseline.keeper_exp_dir).name
        phase1["code_baseline_exp"] = exp_label
        phase1["code_baseline_dir"] = baseline.keeper_exp_dir


_F1_HINT_MAX = 3  # 写到 query 段时只列前 N 个 scenario 避免 prompt 膨胀


def _format_context_section(
    *,
    f1_scenarios: list[str],
    profile: str,
    metric_key: str,
    tier: str,
    innovation_depth: str,
    tam_status: str,
) -> str:
    """注入项目现状到 Phase 1 prompt（设计为接在 query 规则之前）。

    注：当前 `_phase1_prompt` 未调用此 helper；Task 4 会负责 wiring。
    """
    f1_full = f1_scenarios or ["(无 F1 manifest)"]
    f1_top = f1_full[:_F1_HINT_MAX]
    lines = [
        "## 项目现状（写 query 前必看）",
        f"- profile: {profile or '(unknown)'}",
        f"- F1 scenario_ids: {f1_full}",
        f"- contract.metric_key: {metric_key or '(unknown)'}",
        "",
        "### 当前阶段（你站在哪）",
        f"- Tier: {tier or '(unknown)'}",
        f"- innovation_depth: {innovation_depth or '(unknown)'}",
        f"- TAM 状态: {tam_status or '(unknown)'}",
        "",
        "### 你的 query 要能搜到对项目有用的论文",
        f"  - 至少 1 个 F1 scenario_id token：{f1_top}",
        f"  - 包含 metric_key：{metric_key or '(any)'}",
        "  - 不用 'method/approach/analysis/study' 等通用词",
        "  - 不与 F1 无任何 token 重叠",
    ]
    return "\n".join(lines)


def _format_query_rules_section() -> str:
    """注入 query 写作规则到 Phase 1 prompt（设计为接在 Context 之后）。

    注：当前 `_phase1_prompt` 未调用此 helper；Task 4 会负责 wiring。
    DO/DON'T/示例与 query_validator 常量同源；改 validator 常量时 prompt 自动同步。
    """
    from lib.external.query_validator import (  # noqa: PLC0415
        _GENERIC_QUERY_WORDS,
        _QUERY_MAX_LEN,
    )
    generic_joined = "/".join(sorted(_GENERIC_QUERY_WORDS))
    return (
        "## Query 写作规则（你的 paper_query 字段必须满足）\n"
        "**DO**:\n"
        "  - 至少 1 个 F1 scenario_id 的 token（如 fmnist / kerr）\n"
        "  - 用具体方法/算法名（EMA sampler 优于 sampling method）\n"
        "  - 包含 contract.metric_key 名（test accuracy 优于 performance）\n"
        f"  - 总长 ≤ {_QUERY_MAX_LEN} 字符\n"
        "\n"
        "**DON'T**:\n"
        f"  - 用 {generic_joined}（太泛）\n"
        "  - 跨领域关键词（physical-constraint 在 image 任务中是冲突）\n"
        "  - 与 F1 scenario_id 无任何 token 重叠\n"
        "\n"
        "**示例（好）**: `fashion-mnist EMA-confidence sampler test accuracy`\n"
        "**示例（差）**: `physical-constraint operator-learning improvement`\n"
    )


def _extract_paper_query(llm_response: dict | str) -> str:
    """从 LLM 响应中提取 paper_query 字符串。

    兼容 dict（取 paper_query 字段；fallback "query"）+ str（直接返回）+ 其他（空串）。
    实际生产路径：paper_query 由 lib/external/query.py:build_paper_query 构造
    （deterministic, from fingerprint）；本 helper 主要为 LLM-driven fallback 路径保留。
    """
    if isinstance(llm_response, str):
        return llm_response.strip()
    if isinstance(llm_response, dict):
        v = llm_response.get("paper_query") or llm_response.get("query") or ""
        return str(v).strip()
    return ""


def _generate_validated_query(
    *,
    call_agent_fn,
    initial_prompt: str,
    f1_scenarios: list[str],
    metric_key: str = "",
    max_retries: int = 1,
) -> tuple[str, ValidationVerdict, list[ValidationVerdict]]:
    """生成 paper_query；失败时 re-prompt（最多 max_retries 次）。

    Returns:
        (final_paper_query, final_verdict, all_verdicts)
    """
    if max_retries < 0:
        # 防御：负值 → 当 0 处理；返空 verdict
        return "", ValidationVerdict(ok=False, errors=("max_retries < 0",)), []

    all_verdicts: list[ValidationVerdict] = []
    prompt = initial_prompt
    last_query = ""
    last_verdict: ValidationVerdict | None = None

    for _ in range(max_retries + 1):
        response = call_agent_fn(prompt)
        paper_query = _extract_paper_query(response)
        verdict = validate_query_alignment(
            paper_query,
            f1_scenarios=f1_scenarios,
            metric_key=metric_key,
        )
        all_verdicts.append(verdict)
        last_query = paper_query
        last_verdict = verdict
        if verdict.ok:
            return paper_query, verdict, all_verdicts
        # fail → 追加 feedback 到 prompt 末尾
        feedback = format_validation_feedback(verdict, f1_scenarios=f1_scenarios)
        prompt = prompt + "\n\n" + feedback

    # 全部 fail（max_retries+1 次都失败）
    assert last_verdict is not None  # type narrowing（max_retries >= 0 已保证）
    return last_query, last_verdict, all_verdicts


_QUERY_VALIDATION_INDEX_MAX_Q_LEN = 60
_QUERY_VALIDATION_SECTION_HEADER = "## 历史 query validation"
_QUERY_VALIDATION_TABLE_HEADER = (
    "| round | ok | errors | warnings | retries | query |\n"
    "| --- | --- | --- | --- | --- | --- |"
)


def _write_query_validation_to_index(
    repo_root: Path,
    verdicts: list[ValidationVerdict],
    paper_query: str,
    round_id: str,
) -> None:
    """把 query validation 结果写到 REFLECT_INDEX.md 的 ## 历史 query validation 段。

    行为：
    - 写失败时静默（不阻断 reflect 主流程；与现有 INDEX 写策略一致）
    - 无 INDEX 文件 → 直接返
    - 无 ## 历史 query validation 段 → append 新段
    - 有段 → 在表头后插入新行
    - query 截断到 _QUERY_VALIDATION_INDEX_MAX_Q_LEN
    - query 中 | 转义为 \\|（防 markdown 表格破坏）
    """
    index_path = repo_root / "references" / "REFLECT_INDEX.md"
    if not index_path.is_file():
        return  # 无 INDEX → 静默
    try:
        text = index_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(
            f"[reflect] WARNING: failed to read REFLECT_INDEX.md for query validation: {exc}",
            file=sys.stderr,
        )
        return

    # 决定 status
    final_ok = verdicts and verdicts[-1].ok
    all_errors: list[str] = []
    for v in verdicts:
        all_errors.extend(v.errors)
    all_warnings: list[str] = []
    for v in verdicts:
        all_warnings.extend(v.warnings)
    status_mark = "✓" if final_ok else "✗"
    err_count = len(all_errors)
    warn_count = len(all_warnings)
    retry_count = max(0, len(verdicts) - 1)

    # 截短 query + 转义 |（防表格破坏）
    q_short = paper_query.replace("\n", " ").replace("|", "\\|")
    if len(q_short) > _QUERY_VALIDATION_INDEX_MAX_Q_LEN:
        q_short = q_short[:_QUERY_VALIDATION_INDEX_MAX_Q_LEN] + "…"

    new_row = (
        f"| {round_id} | {status_mark} | {err_count} | {warn_count} | {retry_count} | "
        f"`{q_short}` |"
    )
    # 错误/警告明细以引用行跟在表行后（不破坏表格列数）
    detail_lines: list[str] = []
    if all_errors:
        detail_lines.append(f"> {round_id} errors: " + "; ".join(all_errors))
    if all_warnings:
        detail_lines.append(f"> {round_id} warnings: " + "; ".join(all_warnings))
    new_block = new_row + ("\n" + "\n".join(detail_lines) + "\n" if detail_lines else "\n")

    if _QUERY_VALIDATION_SECTION_HEADER in text:
        # 段已存在：在表头后插入
        lines = text.splitlines()
        header_idx = lines.index(_QUERY_VALIDATION_SECTION_HEADER)
        insert_idx = header_idx + 1
        if insert_idx < len(lines) and lines[insert_idx].strip() == "":
            insert_idx += 1
        if insert_idx < len(lines) and lines[insert_idx].startswith("| round"):
            insert_idx += 2  # 跳表头和分隔行
        # 插入整块（新行 + 可能的 detail 行）
        block_lines = new_block.rstrip("\n").splitlines()
        for offset, bl in enumerate(block_lines):
            lines.insert(insert_idx + offset, bl)
        new_text = "\n".join(lines)
    else:
        # 段不存在：append
        new_text = text.rstrip() + f"\n\n{_QUERY_VALIDATION_SECTION_HEADER}\n\n{_QUERY_VALIDATION_TABLE_HEADER}\n{new_block}"

    try:
        index_path.write_text(new_text, encoding="utf-8")
    except OSError as exc:
        print(
            f"[reflect] WARNING: failed to write query validation row to REFLECT_INDEX.md: {exc}",
            file=sys.stderr,
        )


def _build_hardcoded_context(repo_root: Path) -> str:
    """扫描 workspace 硬编码函数签名默认值，返回 context 摘要（config-only 合规检查）。

    每轮都扫——config-only 是硬性要求，不依赖 exploration.mode。
    返回空串表示无硬编码或扫描失败。
    """
    try:
        from analyze_hardcoded_params import analyze_workspace
        hardcoded = analyze_workspace(repo_root, train_env_covered=set())
        if not hardcoded:
            return ""

        # 按值域分组统计（通用启发式，不绑具体参数名）
        float_params = {}   # 0 < val < 1 → 训练动态/正则化
        int_large = {}      # val >= 16 → 模型容量/量化
        int_small = {}      # 2 <= val < 16 → 架构细节
        other = {}
        for name, val in hardcoded.items():
            try:
                v = float(val)
                if 0 < v < 1:
                    float_params[name] = val
                elif v >= 16 and v == int(v):
                    int_large[name] = val
                elif 2 <= v < 16 and v == int(v):
                    int_small[name] = val
                else:
                    other[name] = val
            except (ValueError, TypeError):
                other[name] = val

        # 输出摘要（不猜瓶颈，让 agent 根据项目上下文自己判断）
        parts = [
            f"\n\n## 未配置化的硬编码参数（config-only 违规，共 {len(hardcoded)} 个）",
        ]
        if float_params:
            examples = ", ".join(f"{k}={v}" for k, v in sorted(float_params.items())[:5])
            parts.append(f"- 浮点 0-1（训练动态/正则化）: {len(float_params)} 个，如 {examples}")
        if int_large:
            examples = ", ".join(f"{k}={v}" for k, v in sorted(int_large.items())[:5])
            parts.append(f"- 整数 ≥16（模型容量/量化）: {len(int_large)} 个，如 {examples}")
        if int_small:
            examples = ", ".join(f"{k}={v}" for k, v in sorted(int_small.items())[:5])
            parts.append(f"- 整数 2-15（架构细节）: {len(int_small)} 个，如 {examples}")
        if other:
            parts.append(f"- 其他: {len(other)} 个")
        parts.append(
            "哪些参数是当前瓶颈，取决于项目上下文（模型结构、任务、当前 sgcs）。"
            "结合 EXPERIENCE.md Tier 状态和 round_decision.json 判断优先提取哪个。"
        )

        return "\n".join(parts)
    except Exception:
        return ""


def _build_capacity_context(
    repo_root: Path,
    scenario_id: str = "",
    history_best_cap: dict | None = None,
) -> str:
    """M1+M2 反射上下文：场景容量卡 + 经验律推荐。

    业务仓零代码工作：
    - contract.scenario_capacity.SCENARIO_CAPACITY 空表时
      list_capacity 返回全 None → 此函数返回空串 → Phase 1 prompt 不增段
    - 业务仓填了表 → 容量卡渲染到 context_digest
    - 经验律用模板内置 4 条通用律（业务仓可 SCALING_LAW_OVERRIDE 覆盖）

    返回空串 = 业务仓未填表，零成本跳过 M1+M2 段。
    """
    try:
        from contract import create_contract
        from contract.scenario_capacity import SCENARIO_CAPACITY

        contract = create_contract({})

        # 1) M1 容量卡
        sid = scenario_id or _detect_scenario_id(repo_root)
        cap = contract.list_capacity(sid)
        if all(v is None for v in cap.values()):
            return ""  # 业务仓没填表，跳过整段

        # 2) M2 经验律推荐
        rec = contract.list_scaling_recommendation(cap, history_best_cap)

        # 3) 渲染
        parts = [f"\n\n## 场景容量与架构推荐（M1+M2，scenario_id={sid!r}）"]
        # 容量卡
        cap_lines = []
        for k, v in cap.items():
            if v is not None:
                cap_lines.append(f"- {k}: {v}")
        if cap_lines:
            parts.append("\n".join(cap_lines))
        # 经验律推荐
        if rec:
            rec_lines = ["\n### 经验律推荐 cfg 值（基于场景规模）"]
            for k, v in rec.items():
                if k.startswith("delta_"):
                    rec_lines.append(f"- 跨场景 delta: {k} = {v}")
                else:
                    rec_lines.append(f"- 建议 {k} = {v}")
            parts.append("\n".join(rec_lines))
            parts.append(
                "\n**判断建议**：以上是经验律推论，agent 应结合项目上下文（模型结构、"
                "当前 sgcs、EXPERIENCE.md Tier 状态）决定是否采纳。"
                "如 cap 与当前 cfg 差 >2×，通常意味着架构容量欠配或过配，"
                "优先尝试 cfg-only 调整而非动 workspace/ 源码。"
            )
        return "\n".join(parts)
    except Exception:
        return ""


# M4 整合层用：把 dict-shaped fingerprint 包装成 compute_diversity 期望的
# duck-type 对象（attribute access 而不是 dict access）。
class _DictFP:
    __slots__ = ("primary_keys_changed", "primary_tier")

    def __init__(self, primary_keys_changed: dict, primary_tier: str) -> None:
        self.primary_keys_changed = primary_keys_changed
        self.primary_tier = primary_tier


def _detect_scenario_id(repo_root: Path) -> str:
    """从 _runs/results.tsv 读最近一条 scenario_id（兜底）。"""
    try:
        tsv = repo_root / "_runs" / "results.tsv"
        if not tsv.exists():
            return ""
        with tsv.open("r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) < 2:
            return ""
        # 假设 header 含 scenario_id
        header = lines[0].rstrip("\n").split("\t")
        try:
            idx = header.index("scenario_id")
        except ValueError:
            return ""
        # 取最后一条非空
        for line in reversed(lines[1:]):
            cells = line.rstrip("\n").split("\t")
            if idx < len(cells) and cells[idx].strip():
                return cells[idx].strip()
    except Exception:
        pass
    return ""


# M4 整合入口：3 个子模块 → 1 个统一 dict
def compute_exhaustion_metric(
    repo_root: Path,
    *,
    leader_config_path: Path | None = None,
    current_config_path: Path | None = None,
    leader_metric: float | None = None,
    current_metric: float | None = None,
) -> dict:
    """M4 同场景穷尽度统一入口。

    包 3 个 task #146-157 子模块：
    - fingerprint_diversity: 算台账多样性（重复度、降档建议）
    - leader_attribution: 算当前 cfg vs leader cfg gap
    - tam_reconcile: 算 TAM tier 冲突 / 升档建议

    每个子模块失败优雅降级（缺数据返回空 dict 子段），
    让 reflect 在 PLATEAU 或新业务仓零场景时仍能调。

    返回 dict 结构（每个子段可能 {} 或省略）：
        {
            "diversity": {...},        # fingerprint_diversity.DiversityReport.to_dict()
            "leader": {...},            # LeaderAttribution.to_dict() 或 {}
            "tam_reconcile": {...},    # TamReconcileResult.__dict__ 子集
            "exhaustion_score": 0-1,    # 综合分数（基于 diversity）
            "suggestion": "continue_exploration" | "downshift_tier" | "try_new_chain"
        }
    """
    out: dict = {
        "diversity": {},
        "leader": {},
        "tam_reconcile": {},
        "exhaustion_score": 0.0,
        "suggestion": "continue_exploration",
        "notes": [],
    }
    try:
        # 1) diversity：从 saved/experiment_journal.json 读最近 fingerprints
        try:
            from lib.fingerprint_diversity import compute_diversity
            journal_path = repo_root / "saved" / "experiment_journal.json"
            fps_raw = []
            if journal_path.is_file():
                import json
                j = json.loads(journal_path.read_text(encoding="utf-8"))
                # 兼容 dict 或 list 形态
                if isinstance(j, list):
                    fps_raw = j
                elif isinstance(j, dict):
                    fps_raw = j.get("fingerprints") or j.get("records") or []
            # 封装成 duck-type 对象（compute_diversity 期望 .primary_keys_changed 和 .primary_tier）
            # 业务仓 journal 字段约定：每条 {swap: str, tier: str}
            # 我们把 swap 包成 primary_keys_changed={some_key: [swap_val]}
            # 注意：_extract_swap 取 first key 的 first val，所以 multi-key 不能简单
            # 共享 key — 我们用 swap 字符串本身 hash 成 key 名（保唯一）
            fps = []
            for fp in fps_raw:
                if isinstance(fp, dict):
                    swap = fp.get("swap", "") or ""
                    tier = fp.get("tier", "") or ""
                    if not swap:
                        continue
                    # 用 swap 字符串作 key（保证多 swap 时 key 唯一）
                    fps.append(_DictFP(primary_keys_changed={swap: [swap]},
                                       primary_tier=tier))
                else:
                    fps.append(fp)  # 已经是 dataclass 形态
            report = compute_diversity(fps)
            out["diversity"] = {
                "window": report.window,
                "primary_swap_repeat_pct": report.primary_swap_repeat_pct,
                "tier_repeat_pct": report.tier_repeat_pct,
                "dominant_swap": report.dominant_swap,
                "downshift_recommended": report.downshift_recommended,
                "downshift_target_tier": report.downshift_target_tier,
                "n_unique_swaps": report.n_unique_swaps,
                "n_unique_tiers": report.n_unique_tiers,
            }
            # 综合分数：0.0 = 极度多样，1.0 = 完全饱和
            n = max(report.window, 1)
            out["exhaustion_score"] = round(
                0.5 * report.primary_swap_repeat_pct + 0.5 * report.tier_repeat_pct, 3
            )
            if report.downshift_recommended:
                out["suggestion"] = f"downshift_to_tier_{report.downshift_target_tier}"
            elif out["exhaustion_score"] >= 0.7:
                out["suggestion"] = "try_new_chain"
        except Exception as e:
            out["notes"].append(f"diversity_skip: {e}")

        # 2) leader_attribution：需 4 个参数（leader_cfg / current_cfg / 2 个 metric）
        if (
            leader_config_path is not None
            and current_config_path is not None
            and leader_metric is not None
            and current_metric is not None
        ):
            try:
                from lib.leader_attribution import compute_leader_attribution
                attr = compute_leader_attribution(
                    leader_config_path,
                    current_config_path,
                    leader_metric,
                    current_metric,
                )
                out["leader"] = attr.to_dict()
            except Exception as e:
                out["notes"].append(f"leader_skip: {e}")

        # 3) tam_reconcile：需要 EXPERIENCE.md + saved/tier_attestation.json
        try:
            from lib.tam_reconcile import reconcile_tam_with_experience
            exp_md = repo_root / "EXPERIENCE.md"
            if exp_md.is_file():
                tam_result = reconcile_tam_with_experience(repo_root, exp_md)
                out["tam_reconcile"] = {
                    "action": tam_result.action,
                    "tier": tam_result.tier,
                    "tam_before": tam_result.tam_before,
                    "tam_after": tam_result.tam_after,
                    "conflict_reason": tam_result.conflict_reason,
                }
        except Exception as e:
            out["notes"].append(f"tam_skip: {e}")

    except Exception as e:
        out["notes"].append(f"compute_exhaustion_metric_top_level: {e}")
    return out


def _build_exhaustion_context(repo_root: Path) -> str:
    """M4 反射上下文：穷尽度报告。

    调用 compute_exhaustion_metric 整合层，渲染成 markdown 段。
    业务仓零代码：saved/experiment_journal.json 存在即工作；
    缺数据时返回空串，零成本。
    """
    try:
        metric = compute_exhaustion_metric(repo_root)
        # 没数据就不渲染
        if not metric.get("diversity") and not metric.get("leader") and not metric.get("tam_reconcile"):
            return ""

        parts = ["\n\n## 场景穷尽度（M4 — 同场景参数空间饱和度）"]
        if metric.get("diversity"):
            d = metric["diversity"]
            parts.append(
                f"- 台账窗口: {d['window']} 条，dominant_swap = {d['dominant_swap']!r}"
            )
            parts.append(
                f"- primary_swap 重复度: {d['primary_swap_repeat_pct']:.0%}，"
                f"tier 重复度: {d['tier_repeat_pct']:.0%}"
            )
            parts.append(
                f"- 唯一 swap 数: {d['n_unique_swaps']}，唯一 tier 数: {d['n_unique_tiers']}"
            )
            parts.append(
                f"- **exhaustion_score**: {metric['exhaustion_score']:.2f} "
                f"(0=多样，1=饱和)"
            )
            parts.append(
                f"- **suggestion**: `{metric['suggestion']}`"
            )
            if d.get("downshift_recommended"):
                parts.append(
                    f"- ⚠ 建议降档到 tier {d['downshift_target_tier']}（饱和信号）"
                )
        if metric.get("leader"):
            ld = metric["leader"]
            parts.append(
                f"\n### Leader 对齐（vs 历史 leader cfg）\n"
                f"- leader metric = {ld['leader_metric_value']:.4f}, "
                f"current = {ld['current_metric_value']:.4f}, gap = {ld['gap']:.4f}\n"
                f"- confidence: {ld['confidence']}, missing: {ld['missing_in_current']}"
            )
        if metric.get("tam_reconcile"):
            tr = metric["tam_reconcile"]
            parts.append(
                f"\n### TAM 对账\n"
                f"- action = {tr['action']}, tier = {tr['tier']}, "
                f"tam_before/after = {tr['tam_before']} → {tr['tam_after']}"
            )
            if tr.get("conflict_reason") and tr["conflict_reason"] != "EXPERIENCE.md not found":
                parts.append(f"- 冲突: {tr['conflict_reason']}")
        if metric.get("notes"):
            parts.append(
                f"\n### 跳过项\n" + "\n".join(f"- {n}" for n in metric["notes"])
            )
        parts.append(
            "\n**判断建议**：exhaustion_score ≥ 0.7 时本场景参数空间接近饱和，"
            "应优先尝试：① 换 chain / 改 workspace/ 架构；② 跨场景迁移；"
            "而非继续调 cfg 超参。"
        )
        return "\n".join(parts)
    except Exception:
        return ""


def _phase1_prompt(
    metric_key: str,
    rows: list[dict[str, str]],
    last_reflect: str,
    *,
    ledger_hint: str,
    eval_summary: str,
    context_digest: str,
    ledger_rollup: str,
    evidence_md: str = "",
    tam_md: str = "",
    anchor_lines: list[str] | None = None,
    metric_leader_exp: str = "?",
    metric_leader_metric: str = "?",
    code_baseline_exp: str = "",
    innovation_line: str = "",
    fingerprint_line: str = "",
    external_md: str = "",
    e_feedback_md: str = "",
) -> str:
    recent = rows[-8:] if rows else []
    trend = "\n".join(
        f"  {r.get('experiment', '?')}: {metric_key}={r.get(metric_key, '?')}"
        + (f" git={r.get('git_commit')}" if r.get("git_commit") else "")
        for r in recent
    ) or "  (无数据)"
    if ledger_rollup:
        trend = trend + "\n" + ledger_rollup

    tam = tam_md.strip() or (
        "（无 TAM：不得声称 A–D 已试/穷尽；tried_tiers 须留空或写「见 TAM」）"
    )

    innov = innovation_line.strip() or "(无审计结果或上一轮未产生)"
    fp_line = fingerprint_line.strip() or "(无创新指纹或未启用)"
    innov_block = (
        f"- **创新指纹（Phase 0.75，外部检索权威）**：{fp_line}\n"
        f"- **创新维度审计（Phase 0.7）**：{innov}\n"
        "  Agent 填 EXPERIENCE 标签；检索深度以指纹 effective_depth 为准；depth_mismatch 须 WARN。"
    )

    anchors_block = "\n".join(f"  {ln}" for ln in (anchor_lines or [])) or "  (无)"
    baseline_note = (
        f"code_baseline (diff/git 基线，非 SOTA 叙事主语): {code_baseline_exp or '(无)'}"
    )

    ctx = context_digest.strip() or (
        "（未触发超长压缩：无 Phase0/规则摘要；请依赖 evaluation、ledger 趋势与下文 [反思]，"
        "并与仓库内 EXPERIENCE.md / PROTOCOL.md 常识对齐。）"
    )
    reb = evidence_md.strip() or "（无 REB：Phase 0.5 未产出证据包；不得断言 Tier B/C/D 已试或训练 OOM/NaN。）"
    ext = external_md.strip() or "（无 external evidence；禁止编造 url）"
    e_fb = e_feedback_md.strip() or (
        "（尚无人决议。三选一留下/搁置/驳回之后都不得改题面。）"
    )

    return textwrap.dedent(f"""\
You are Phase 1 of a Tier-ladder reflection round.
Read and integrate: (1) experiment ledger ({ledger_hint}; summary below),
(2) **`_runs/round_decision.json`** snapshot below — official post-train eval for the latest **aggregated** round
(prefer ``keep_suggestion``, ``reason``, ``primary_metric`` over inferring from ledger alone),
(3) **Phase 0 / 规则压缩上下文**（EXPERIENCE+PROTOCOL+jsonl 脉络摘要；不得与之下游臆造禁忌或契约）,
(4) **Reflect 证据包（REB, Phase 0.5）** — exp 产物、日志信号、code_snapshot diff；**硬约束**：
   - 无 code_snapshot diff → 不得写「已试 Tier B/C/D」
   - 无 L2 日志信号 → 不得写「训练未收敛 / OOM / NaN」
   - gaps 非空 → 须在 key_insight 或 phase2_focus 中标注 fix-gap | defer | proceed
(5) **Tier Attestation Matrix（TAM, Phase 0.6）** — **权威** Tier 举证；**硬约束**：
   - `tried_tiers` / `not_tried_tiers` **必须与 TAM 一致**（禁止用 description 推断）
   - 存在 `false_claim` → 必须在 key_insight 列出；禁止写该档「已试/已穷尽」
   - 存在 `not_attested` Tier B/C/D → 禁止写「梯子 A–D 已试完」
   - `shallow` / `exhausted` 仅指档内刷参穷尽，不等于升档完成
(6) **创新指纹与审计（Phase 0.75 / 0.7）**：
{innov_block}
   - 外部证据深度以 **指纹 effective_depth** 为准，非 Agent 散文。
   - 仅当 EXPERIENCE 二维矩阵中**具体格子**（如 B-routine）标「已穷尽」时，才考虑同档下一深度或升更深字母档的 routine。
   - 当 A-D 档都穷尽时，检查 context 中"未配置化的硬编码参数"，考虑提取为 cfg（A档第一次：改代码把硬编码变成 cfg["X"]）
   - 搜到新架构/loss/增强时，考虑注册它（B/C/D档创造：@register_learner / @register_objective + 设 cfg 键）
(7) **外部证据（Phase 1.85，仅已验证条目）** — **硬约束**：
   - 论文 url 只能引用本节列出的 hits；routine 结论只认 routine_attestation。
{ext}
(8) **认知锚** — **硬约束**：
   - `best_exp` / `best_metric` **必须指 metric_leader**（同 focus scenario 的 TSV 主指标最优），**不得**指 code_baseline，除非二者为同一 run
   - code_baseline 仅用于解释 git/snapshot diff；禁止写「当前最佳实验 = code_baseline」当 metric_leader 为不同 run
   - 撞墙/证伪须引用 ≥1 条 attested_failure 或 TAM 中 DISCARD 且 attested/shallow/false_claim 的 run（若 REB 中存在）
(9) **改题人决议** — **硬约束**：
   - 留下 / 搁置 / 驳回 **都不得**改 contract / 题面 / 指标 / 官方测试。
   - 已驳回的类似主张：e_proposed / e_why_abcd / e_ask 必须空串。
   - 已留下的：只可当建议，禁止再填三键催改，禁止当已落地。
   - 已搁置的：不当禁令；若仍主张改题，可以再填三键。
{e_fb}
(10) **最近一条 [反思] 全文/摘录**（可能与摘要重叠，以不矛盾为准）。
Output ONLY a JSON object to stdout, nothing else.

Context:
- ledger: {ledger_hint}
- metric_key: {metric_key}
- cognitive anchors (metric_leader = ledger SOTA; code_baseline = keeper diff base):
{anchors_block}
- {baseline_note}
- `_runs/round_decision.json` (use this explicitly when judging keep vs plateau):
{eval_summary}
- compressed project context (Phase 0 LLM preferred; else rule-based; ambiguity → full files win):
{ctx}
- Reflect evidence bundle (REB; cite exp_dir / tier_evidence when claiming Tier changes):
{reb}
- Tier attestation matrix (TAM; authoritative for attested/not_attested/false_claim):
{tam}
- Innovation audit (Phase 0.7):
{innov}
- 外部证据（Phase 1.85；仅可引用下列 url/hits）：
{ext}
- recent results (last 8):
{trend}
- metric_leader (authoritative for best_exp/best_metric): {metric_leader_exp} = {metric_leader_metric}
- last reflection block:
{last_reflect or "(无)"}
- 改题人决议:
{e_fb}

Produce this EXACT JSON to stdout (write ONLY the JSON):

{{
  "wall_crash": true or false,
  "wall_crash_detail": "连续 N 轮同一 Tier 失败且主指标未改善，或'无明确信号'",
  "streak_tier": "Tier A/B/C/D/E or null",
  "streak_count": N,
  "tried_tiers": ["Tier A", "Tier B", ...],
  "not_tried_tiers": ["Tier B", "Tier C", "Tier D"],
  "best_exp": "{metric_leader_exp}",
  "best_metric": "{metric_leader_metric}",
  "key_insight": "1-2 sentences: why the best experiment worked or why recent ones failed",
  "task_reflection": {{
    "current_goal": "从 HUMAN_GUIDANCE.md / goal / EXPERIENCE 提炼的当前实验目标（一句话）",
    "main_blockers": ["阻碍进展的 1-3 个关键问题，聚焦初级但关键的：config-only 违规（硬编码参数）、数据管道瓶颈、训练不收敛、资源限制等"],
    "potential_risks": ["下一轮可能遇到的 1-2 个风险：过拟合、plateau、数据泄露、硬编码参数未提取等"]
  }},
  "phase2_focus": "Specific question for backbone/operator (Tier B), objective (Tier C), or data pipeline (Tier D); not Tier E unless contract metric/test changes",
  "e_proposed": "若主张改题面（指标/官方测试/场景/KEEP/问题陈述）填具体改什么；否则空串",
  "e_why_abcd": "若主张改题：为何 A–D 解不开（具体）；否则空串",
  "e_ask": "若主张改题：请求人开闸或走改能力；否则空串"
}}

改题规则：只有当你明确主张修改 contract/题面 时才填 e_proposed / e_why_abcd / e_ask（三条齐全）；
否则三个键一律留空字符串。禁止用散文「Tier E」代替这三键；成绩表格子仍只谈 A–D。
人已驳回的类似主张必须空串；人已留下的只复述建议、不得再催改；搁置可再提。""")


def _phase2_prompt(phase1: dict, *, task_domain: str = "") -> str:
    focus = phase1.get("phase2_focus",
                        "physical-constraint or operator-learning improvement for extrapolation")
    not_tried = phase1.get("not_tried_tiers", [])
    domain = (task_domain or "the current experiment task").strip()
    return textwrap.dedent(f"""\
You are Phase 2 of a reflection round. Two knowledge sources are available:

1. LOCAL REFERENCES: Check `references/manual/` then `references/auto/` under the project root.
   Read any .md or .txt files there — they may already contain relevant papers
   or techniques. If a finding is already in references/, note it instead of
   duplicating.

2. TRAINED KNOWLEDGE: Draw on your trained knowledge (up to early 2025) to
   supplement or extend the local references.

Produce this EXACT JSON to stdout (write ONLY the JSON):

{{
  "search_queries": [
    "{focus}",
    "{focus} {domain} 2024",
    "{domain} deep learning benchmark"
  ],
  "findings": [
    {{
      "url": "https://arxiv.org/abs/... (real URL or empty string if unknown)",
      "summary": "one sentence describing the method and why it's relevant",
      "relevance": "high/medium/low",
      "tier": "Tier A|B|C|D only; Tier E ONLY if proposing contract/metric/test/KEEP change",
      "code_area": "workspace/model | workspace/loss | workspace/data | contract (rare)",
      "source": "local or trained_knowledge",
      "why": "why this is relevant to {domain}"
    }}
  ],
  "references_to_add": [
    {{
      "title": "Paper title or technique name",
      "url": "https://... (real URL or empty)",
      "summary": "2-3 sentences describing the key insight and how to apply it",
      "tier": "Tier A|B|C|D only; Tier E ONLY if proposing contract/metric/test/KEEP change",
      "code_area": "workspace/model | workspace/loss | workspace/data | contract (rare)"
    }}
  ]
}}

IMPORTANT:
- Do NOT label Koopman, FNO, DeepONet, or neural-operator backbone papers as Tier E — use Tier B.
- Soft physics in loss (small lambda PDE residual) → Tier C; backbone swap → Tier B (note B+C combo may need split rounds).
- Tier E requires an explicit contract-level change (metric_key, test set, scenario KEEP pool).
- Output ONLY the JSON.
- Check `references/` first; if a relevant entry already exists, use it and
  add it to findings (source="local") rather than duplicating.
- If you discover new papers/techniques not in references/, add them to
  "references_to_add" — these will be appended to references/ after Phase 3.
- If you cannot recall a real URL, use an empty string for "url" — do NOT fabricate.
- P0-1 (LLM 污染传播)：禁止在任何 phase 凭空给出 paper title — paper title 仅可来自
  (a) `references/manual/` / `references/auto/` 中已有条目，或
  (b) Phase 1.85 注入的 `bundle.paper.hits`（已验证论文）。
  若 `bundle.paper.hits` 为空且 references 中无命中条目 → `references_to_add: []`，
  `findings` 仅写技术名称 + 方向，不写论文标题、不写 URL。
- At least 3 findings required; if truly none found, set findings to [].
- Output ONLY the JSON, with NO markdown code fences (no ```json or ```).""")


def _collapse_ws(s: str) -> str:
    return " ".join(str(s or "").split())


def _parse_json_lenient(s: str):
    """容错解析 LLM JSON：跳过前导文本，raw_decode 取首个完整对象/数组，
    忽略尾部多余数据（LLM 常在 JSON 后追加解释 → 'Extra data' 错）。失败返回 None。"""
    s = (s or "").strip()
    start = -1
    for i, ch in enumerate(s):
        if ch in "{[":
            start = i
            break
    if start < 0:
        return None
    try:
        obj, _end = json.JSONDecoder().raw_decode(s[start:])
        return obj
    except json.JSONDecodeError:
        return None


def _resolve_path_under_root(repo_root: Path, raw: object) -> Path | None:
    text = str(raw or "").strip()
    if not text:
        return None
    p = Path(text)
    if not p.is_absolute():
        p = (repo_root / p).resolve()
    else:
        p = p.resolve()
    return p if p.is_dir() else None


def _current_exp_dir_for_e_feedback(
    repo_root: Path,
    fingerprint: dict | None,
    round_decision: dict | None,
) -> Path | None:
    candidates: list[object] = []
    if isinstance(fingerprint, dict):
        candidates.extend(fingerprint.get("candidate_exp_dirs") or [])
    if isinstance(round_decision, dict):
        ev = round_decision.get("evaluated_exp_dir")
        if ev:
            candidates.append(ev)
        candidates.extend(round_decision.get("candidate_exp_dirs") or [])
    for raw in reversed(candidates):
        p = _resolve_path_under_root(repo_root, raw)
        if p is not None:
            return p
    return None


def _scenario_id_for_exp(exp_dir: Path) -> str:
    cfg = exp_dir / "config.json"
    if not cfg.is_file():
        return ""
    try:
        data = json.loads(cfg.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("scenario_id") or "").strip()


def _maybe_record_executed_e_feedback(
    repo_root: Path,
    *,
    fingerprint: dict | None,
    round_decision: dict | None,
    metric_key: str,
    round_hint: int | None,
) -> None:
    """Phase 0.75 后：开闸 + contract diff → executed（不改 TSV 格子）。"""
    from lib.e_feedback_store import try_append_executed_on_relaunch
    from lib.exploration_stamp import prev_trained_exp_dir

    cur = _current_exp_dir_for_e_feedback(repo_root, fingerprint, round_decision)
    if cur is None:
        return
    sid = _scenario_id_for_exp(cur)
    prev = None
    if sid:
        prev = prev_trained_exp_dir(
            repo_root,
            scenario_id=sid,
            before_exp_dir=cur,
            metric_key=metric_key,
        )
    rec = try_append_executed_on_relaunch(
        repo_root,
        relaunch_env=os.environ.get("NN_RELAUNCH"),
        prev_exp_dir=prev,
        cur_exp_dir=cur,
        experiment=cur.name,
        round_hint=round_hint,
    )
    if rec and "skipped" not in rec:
        print(f"[reflect] e_feedback executed: {rec.get('id')}", file=sys.stderr)


def _maybe_record_shout_e_feedback(
    repo_root: Path,
    phase1: dict,
    *,
    fingerprint: dict | None,
    round_decision: dict | None,
    round_hint: int | None,
) -> None:
    """Phase 1 JSON 三条齐全 → shout；禁止扫 Tier E 散文。"""
    from lib.e_feedback_store import try_append_shout_from_reflect

    cur = _current_exp_dir_for_e_feedback(repo_root, fingerprint, round_decision)
    experiment = cur.name if cur is not None else str(phase1.get("best_exp") or "reflect")
    quote = str(phase1.get("key_insight") or phase1.get("wall_crash_detail") or "")
    rec = try_append_shout_from_reflect(
        repo_root,
        phase1,
        experiment=experiment,
        round_hint=round_hint,
        quote=quote,
    )
    skipped = rec.get("skipped")
    if skipped == "incomplete":
        return
    if skipped in ("rejected", "adopted"):
        print(
            f"[reflect] e_feedback shout skipped: {skipped} id={rec.get('id')}",
            file=sys.stderr,
        )
        return
    print(f"[reflect] e_feedback shout: {rec.get('id')}", file=sys.stderr)


def _truncate_text(s: str, max_chars: int) -> str:
    s = _collapse_ws(s)
    if max_chars <= 0:
        return ""
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 1].rstrip() + "…"


def _phase3_markdown_compact(
    metric_key: str,
    phase1: dict,
    phase2: dict,
    *,
    tam_line: str = "",
    tam_not_attested: list[str] | None = None,
    innovation_line: str = "",
    external_summary_line: str = "",
    synthesis: dict | None = None,
) -> str:
    """合并原「详细分析」为短块：无 ``### 详细分析``；长文仅 ``references/``。"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    not_tried = tam_not_attested if tam_not_attested is not None else (phase1.get("not_tried_tiers") or [])
    not_tried_joined = ", ".join(str(x) for x in not_tried) if not_tried else "（无）"
    tam_suffix = f"\n- **TAM**: {tam_line}" if tam_line.strip() else ""
    innov_suffix = f"\n- **Innovation**: {innovation_line}" if innovation_line.strip() else ""
    external_suffix = (
        f"\n- {external_summary_line.strip()}" if external_summary_line.strip() else ""
    )
    leader_exp = phase1.get("metric_leader_exp") or phase1.get("best_exp") or "?"
    leader_metric = phase1.get("metric_leader_metric") or phase1.get("best_metric") or "?"
    baseline_exp = str(phase1.get("code_baseline_exp") or "").strip()
    ledger_lines = [
        f"- **台账最优**: `{leader_exp}` · `{metric_key}={leader_metric}` · 未尝试 Tier：`{not_tried_joined}`",
    ]
    if baseline_exp and baseline_exp != leader_exp:
        ledger_lines.append(
            f"- **代码基线**: `{baseline_exp}` · （git/diff 基准，见 keepers.json）"
        )
    ledger_block = "\n".join(ledger_lines)

    wall = bool(phase1.get("wall_crash"))
    streak = int(phase1.get("streak_count") or 0)
    raw_tier = phase1.get("streak_tier")
    streak_tier_s = (
        "?"
        if raw_tier in (None, "", "null")
        else str(raw_tier)
    )

    wall_line = f"{'有' if wall else '无'}（{streak_tier_s} × {streak} 轮连续无改善）"
    wd = _truncate_text(str(phase1.get("wall_crash_detail") or ""), 160)
    if wall and wd and wd not in ("无明确信号", "无"):
        wall_line = f"{wall_line}；{wd}"

    ki = _truncate_text(str(phase1.get("key_insight") or ""), 360)
    if not ki:
        ki = "（Phase1 未给出 key_insight）"

    # task_reflection 渲染
    task_ref = phase1.get("task_reflection") or {}
    task_ref_lines: list[str] = []
    if task_ref:
        goal = str(task_ref.get("current_goal") or "").strip()
        blockers = task_ref.get("main_blockers") or []
        risks = task_ref.get("potential_risks") or []
        if goal:
            task_ref_lines.append(f"  - 目标：{goal}")
        if blockers:
            task_ref_lines.append(f"  - 阻塞：{'; '.join(str(b) for b in blockers[:3])}")
        if risks:
            task_ref_lines.append(f"  - 风险：{'; '.join(str(r) for r in risks[:2])}")
    task_reflection_block = "\n".join(task_ref_lines) if task_ref_lines else ""

    p2f = _truncate_text(str(phase1.get("phase2_focus") or ""), 300)
    dir_bits: list[str] = []
    if p2f:
        dir_bits.append(f"检索焦点：{p2f}")
    dir_bits.append(f"未尝试 Tier：{not_tried_joined}")
    dir_bits.append("建议下一轮择一方向做最小对照，与当前 SOTA 仅保留单一差分")
    direction = _truncate_text("；".join(dir_bits), 420)

    findings = phase2.get("findings") or []
    flines: list[str] = []
    for f in findings[:3]:
        summ = _truncate_text(str(f.get("summary") or ""), 100)
        if not summ:
            continue
        tier = f.get("tier") or "?"
        url = str(f.get("url") or "").strip()
        tail = f" — {url}" if url else ""
        flines.append(f"  - [{tier}] {summ}{tail}")
    findings_block = "\n".join(flines) if flines else "  - （无）"

    refs = phase2.get("references_to_add") or []
    rlines: list[str] = []
    for r in refs[:5]:
        title = str(r.get("title") or "?").strip()
        url = str(r.get("url") or "").strip()
        # P0-1 (LLM 污染传播)：title+URL 必须配对，禁孤标题渲染（防 LLM 捏造）
        if not url or not title or title == "?":
            continue
        rlines.append(f"  - **{title}** — {url}")
    refs_block = "\n".join(rlines) if rlines else "  - （本轮无新条目；详文见 `references/auto/`）"

    # synthesis 渲染：synthesis=None 时为空串 → 与现有产物逐字节一致
    synthesis_section = ""
    if synthesis:
        chain = synthesis.get("reasoning_chain") or []
        chain_lines = "\n".join(f"    - 步骤{i+1}: {c}" for i, c in enumerate(chain))
        refs = synthesis.get("evidence_refs") or []
        refs_str = "; ".join(refs) if refs else "（无外部 url 引用；纯历史推导）"
        synthesis_section = (
            f"- **综合推理**（synthesis；证据+历史交叉推导）:\n"
            f"  - 下一步：`{synthesis.get('next_step', '?')}` · "
            f"`{synthesis.get('code_area', '?')}` · "
            f"{synthesis.get('tier', '?')} · 单一差分 `{synthesis.get('single_diff_var', '?')}`\n"
            f"  - 推理链：\n{chain_lines}\n"
            f"  - 为什么不照搬：{synthesis.get('adaptation', '?')}\n"
            f"  - 证据：{refs_str}\n"
        )

    return (
        f"## [反思] {ts} (自动反思轮)\n\n"
        f"- **撞墙信号**: {wall_line}\n"
        f"{ledger_block}\n"
        f"- **简要洞察**: {ki}\n"
        f"- **任务反思**:\n{task_reflection_block}\n"
        f"- **方向与下轮**: {direction}\n"
        f"{synthesis_section}"  # NEW; 空串时与现有逐字节一致
        f"{tam_suffix}{innov_suffix}{external_suffix}\n"
        f"- **外部线索**（Phase2 截断，最多 3 条；完整列表见 `saved/reflect_latest.json`）:\n"
        f"{findings_block}\n"
        f"- **references/auto/**（长摘要 `*_auto_reflected.md`；速查见 `references/REFLECT_INDEX.md`）:\n"
        f"{refs_block}\n"
    )


def _references_auto_dir() -> Path:
    d = _ROOT / "references" / "auto"
    d.mkdir(parents=True, exist_ok=True)
    (_ROOT / "references" / "manual").mkdir(parents=True, exist_ok=True)
    return d


def _compute_direction_base(synthesis: dict | None, phase1: dict) -> str:
    """compute direction_full 源头：synthesis.next_step（有效时）或 _next_round_one_liner(phase1)。

    防御性：synthesis.next_step 为空/纯空白 → 回退 one-liner（parse_synthesis 不强制 next_step 非空）。
    """
    if synthesis:
        step = str(synthesis.get("next_step") or "").strip()
        if step:
            return step
    return _next_round_one_liner(phase1)


_EXHAUST_CELL_MARKERS = ("已穷尽", "饱和", "exhausted", "失败", "证伪", "DISCARD")
_OPEN_CELL_MARKERS = ("未试", "浅尝", "attested", "进行中", "?")


def _nn_relaunch_is_set() -> bool:
    return bool(os.environ.get("NN_RELAUNCH", "").strip())


def _merge_external_hits_into_phase2(
    phase2: dict,
    external_bundle: dict,
    *,
    cap: int = 5,
) -> dict:
    from lib.external.merge import dedupe_key  # noqa: WPS433

    findings = list(phase2.get("findings") or [])
    seen: set[str] = set()
    for f in findings:
        url = str(f.get("url") or "").strip()
        if url:
            seen.add(url)
        key = dedupe_key(f)
        if key:
            seen.add(key)
    added = 0
    for hit in (external_bundle.get("paper") or {}).get("hits") or []:
        if added >= cap:
            break
        url = str(hit.get("url") or "").strip()
        if not url:
            continue
        if url in seen:
            continue
        key = dedupe_key(hit)
        if key and key in seen:
            continue
        seen.add(url)
        if key:
            seen.add(key)
        findings.append({
            "url": url,
            "summary": str(hit.get("abstract") or hit.get("title") or "")[:240],
            "relevance": "medium",
            "tier": "Tier A",
            "code_area": "workspace/data",
            "source": "external_api",
            "why": "Phase 1.85 HTTP retrieval",
        })
        added += 1
    return {**phase2, "findings": findings}


def _open_tier_cells_hint(repo_root: Path, *, max_cells: int = 3) -> str:
    """从 EXPERIENCE Tier 二维表摘「未穷尽」格子，供 auto-run defer E 后 fallback。"""
    exp = repo_root / "EXPERIENCE.md"
    if not exp.is_file():
        return "读 EXPERIENCE ## Tier 状态 未穷尽格子"
    try:
        from lib.experience_compress import parse_tier_status_table, _parse_tier_matrix  # noqa: WPS433
    except ImportError:
        return "读 EXPERIENCE ## Tier 状态"
    table = parse_tier_status_table(exp.read_text(encoding="utf-8", errors="replace"))
    mat = _parse_tier_matrix(table)
    if not mat:
        return "读 EXPERIENCE ## Tier 状态"
    short = {"routine": "r", "extend": "e", "novel": "n"}
    hits: list[str] = []
    for letter in "ABCD":
        depths = mat.get(letter) or {}
        for depth in ("routine", "extend", "novel"):
            val = str(depths.get(depth) or "").strip()
            if not val or val in ("—", "-"):
                continue
            if any(m in val for m in _EXHAUST_CELL_MARKERS):
                continue
            if val in _OPEN_CELL_MARKERS or any(m in val for m in _OPEN_CELL_MARKERS):
                hits.append(f"Tier {letter}-{short[depth]}")
            elif letter == "D" and depth == "extend" and len(val) < 40:
                hits.append(f"Tier {letter}-{short[depth]}={val[:20]}")
        if len(hits) >= max_cells:
            break
    if hits:
        return "优先 " + "、".join(hits[:max_cells])
    return "按 EXPERIENCE 子轴清单继续 OVAT（A–D）；E 须 NN_RELAUNCH"


def _tam_not_attested_has_tier_e(tam_not_attested: list[str] | None) -> bool:
    for t in tam_not_attested or []:
        if re.search(r"Tier\s*E\b", str(t), re.I):
            return True
        if str(t).strip().upper() in ("E", "TIER E"):
            return True
    return False


def _apply_dual_audience_direction(
    direction: str,
    *,
    tam_not_attested: list[str] | None,
) -> str:
    """pending 双读者：E 建议给人；NN_RELAUNCH 未设时给 auto-run 机器 fallback。"""
    base = str(direction or "").strip()
    if not base:
        return base
    if not _tam_not_attested_has_tier_e(tam_not_attested):
        return base
    if _nn_relaunch_is_set():
        return base
    hint = _open_tier_cells_hint(_ROOT)
    human = base if "NN_RELAUNCH" in base else f"（人审 E）{base}"
    machine = f"[AUTO-RUN: defer Tier E（NN_RELAUNCH 未设）→ 继续 A–D：{hint}]"
    return f"{human} {machine}"


def _save_synthesis_raw(raw: str, reason: str) -> None:
    agent_dir = _ROOT / "_runs" / "agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = agent_dir / f"{ts}_synthesis-raw.txt"
    try:
        path.write_text(f"reason={reason}\n\n{raw}", encoding="utf-8")
        print(f"[reflect] synthesis raw saved: {path}", file=sys.stderr)
    except OSError as ex:
        print(f"[reflect] synthesis raw save failed (non-fatal): {ex}", file=sys.stderr)


def _run_synthesis_phase(
    *,
    phase1: dict,
    phase2: dict,
    external_bundle: dict | None,
    tam_not_attested: list[str] | None,
    fingerprint: dict | None,
    call_agent_fn,
    max_tokens: int,
    capacity_card: dict | None = None,
    scaling_recommendation: dict | None = None,
    hardcoded_context: str = "",
    exhaustion_metric: dict | None = None,
) -> dict | None:
    """synthesis 综合推理：build prompt → call agent → parse。任一异常 → None（non-fatal）。

    新增 4 个 keyword-only 入参（M1+M2+M3+M4 反射上下文）默认 None/空，
    向后兼容：未传 → 不出对应段（旧调用方不受影响）。
    """
    try:
        from lib.external.synthesis import (  # noqa: WPS433
            build_synthesis_prompt,
            diagnose_synthesis_parse,
            parse_synthesis,
        )
    except Exception as ex:
        print(f"[reflect] synthesis import failed (non-fatal): {ex}", file=sys.stderr)
        return None
    try:
        prompt = build_synthesis_prompt(
            phase1=phase1, phase2=phase2, external_bundle=external_bundle,
            tam_not_attested=tam_not_attested, fingerprint=fingerprint,
            capacity_card=capacity_card, scaling_recommendation=scaling_recommendation,
            hardcoded_context=hardcoded_context, exhaustion_metric=exhaustion_metric,
        )
        raw = call_agent_fn(prompt)
        result = parse_synthesis(
            raw, external_bundle=external_bundle, tam_not_attested=tam_not_attested,
        )
        if result is None:
            reason = diagnose_synthesis_parse(
                raw, external_bundle=external_bundle, tam_not_attested=tam_not_attested,
            ) or "parse_failed"
            print(f"[reflect] synthesis rejected (non-fatal): {reason}", file=sys.stderr)
            _save_synthesis_raw(raw, reason)
        else:
            step = str(result.get("next_step") or "")[:60]
            print(f"[reflect] synthesis ok: next_step={step!r}", file=sys.stderr)
        return result
    except Exception as ex:
        print(f"[reflect] synthesis failed (non-fatal): {ex}", file=sys.stderr)
        return None


def _suggest_tier_from_phase1(phase1: dict) -> str:
    raw = phase1.get("streak_tier")
    if raw not in (None, "", "null", "?"):
        return str(raw).replace("Tier ", "").strip()[:1] or "?"
    not_tried = phase1.get("not_tried_tiers") or []
    if not_tried:
        t0 = str(not_tried[0])
        m = re.search(r"Tier\s*([A-E])", t0, re.I)
        if m:
            return m.group(1).upper()
    return "?"


def _next_round_one_liner(phase1: dict) -> str:
    p2f = _collapse_ws(str(phase1.get("phase2_focus") or ""))
    not_tried = phase1.get("not_tried_tiers") or []
    nt = ", ".join(str(x) for x in not_tried[:2]) if not_tried else ""
    bits: list[str] = []
    if p2f:
        bits.append(p2f)
    if nt:
        bits.append(f"优先 {nt}")
    bits.append("与当前 best 仅保留单一差分")
    return _truncate_text("；".join(bits), 120)


def _wall_short_from_phase1(phase1: dict) -> str:
    wall = bool(phase1.get("wall_crash"))
    streak = int(phase1.get("streak_count") or 0)
    raw_tier = phase1.get("streak_tier")
    tier_s = "?" if raw_tier in (None, "", "null") else str(raw_tier)
    if wall:
        return _truncate_text(f"plateau@{tier_s}×{streak}", 48)
    return "无明确撞墙"


_INDEX_NEXT_ROUND_MAX = 400


def _truncate_index_next_round(text: str, max_chars: int = _INDEX_NEXT_ROUND_MAX) -> str:
    """INDEX pending 下轮建议单元格长度门禁（TAM 超长时截断 + 见详文）。"""
    t = text.strip()
    if len(t) <= max_chars:
        return t
    suffix = "…见详文"
    return t[: max_chars - len(suffix)] + suffix


def _update_reflect_index(
    *,
    reflect_id: str,
    ts_display: str,
    wall_short: str,
    next_round: str,
    tier_letter: str,
    detail_rel: str,
) -> None:
    """覆盖 REFLECT_INDEX pending（至多 1 条）；未消费旧 pending 先归档。"""
    scripts = _ROOT / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from lib.reflect_index import default_index_template, set_pending_row

    index_path = _ROOT / "references" / "REFLECT_INDEX.md"
    if not index_path.is_file():
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(default_index_template(), encoding="utf-8")
    text = index_path.read_text(encoding="utf-8")
    text = set_pending_row(
        text,
        reflect_id=reflect_id,
        ts_display=ts_display,
        wall_short=wall_short,
        next_round=next_round,
        tier_letter=tier_letter,
        detail_rel=detail_rel,
    )
    index_path.write_text(text, encoding="utf-8")
    print(f"[reflect] Updated {index_path} pending → {reflect_id}", file=sys.stderr)
    try:
        from lib.experiment_journal import write_reflect_pending_snapshot  # noqa: WPS433

        write_reflect_pending_snapshot(
            _ROOT,
            reflect_id=reflect_id,
            suggest_one_liner=next_round[:200],
            tier_hint=tier_letter,
        )
    except ImportError:
        pass


def _warn_exhausted_tier_in_suggestion(
    suggestion: str,
    rollup: dict[str, dict[str, Any]],
) -> str:
    """下轮建议提及 TAM 已穷尽档 → stderr WARN。"""
    for letter in "ABCDE":
        if (rollup.get(letter) or {}).get("status") != "exhausted":
            continue
        if re.search(rf"Tier\s*{letter}\b", suggestion, re.I):
            print(
                f"[reflect] WARN: 下轮建议提及已穷尽 Tier {letter}（TAM exhausted），请改方向",
                file=sys.stderr,
            )
    return suggestion


# fork 触发（spec §11 ①）：轻量手段关键词——evidence 必须点名至少一个，防 agent 偷懒直接标 source_block
_LIGHTWEIGHT_MARKERS = (
    "register", "registry", "adapter",
    "monkey-patch", "monkey patch", "monkeypatch",
    "slim", "注册制",
)


def verify_source_block_exhaustion(round_decision):
    """独立核验 source_block 真假撞墙（spec §11 ①）。

    防 agent 偷懒直接标 source_block：evidence 必须点名至少一种轻量手段
    （register/adapter/monkey-patch/slim）且达最小长度，否则判「证据不足」。
    返回 (confirmed: bool, reason: str)。

    v1 为 evidence-quality 门（核 evidence 文本），不做 workspace/log forensic
    复读——reflect 已有 REB（saved/reflect_evidence.json 含 code_snapshot diff +
    log 信号），REB 交叉核验留作 future hardening（hook 点即本函数：可加读 REB
    校验 code_snapshot 非空 / log 含失败信号）。
    """
    if not isinstance(round_decision, dict):
        return (False, "no round_decision")
    sb = round_decision.get("source_block")
    if not isinstance(sb, dict) or not sb.get("blocked"):
        return (False, "no source_block")
    evidence = str(sb.get("evidence", ""))
    tried = [m for m in _LIGHTWEIGHT_MARKERS if m in evidence.lower()]
    if not tried:
        return (False, "evidence 未点名任何轻量手段（agent 偷懒？）")
    if len(evidence) < 20:
        return (False, "evidence 过短，未说明穷尽过程")
    cell = str(sb.get("cell", "")).strip()
    return (True, f"confirmed: evidence 点名 {tried}" + (f"；cell={cell}" if cell else ""))


def _fork_upgrade_advice(round_decision):
    """source_block 经核验确认真撞墙 → 产 register→fork 升级建议（spec §4 步 4）。

    reflect 只判定 + 产建议，不改 manual。返回建议字符串；未确认返回 ""。
    """
    confirmed, reason = verify_source_block_exhaustion(round_decision)
    if not confirmed:
        return ""
    sb = round_decision.get("source_block") or {}
    cell = str(sb.get("cell", "")).strip() or "该格"
    return (
        f"[升级建议] {cell} 应从 register 升 fork：轻量手段（register/adapter/monkey-patch）"
        f"穷尽仍改不动（{reason}）。fork 写法见 references/manual/abcde-manual.md framework 档 fork 兜底格；"
        f"下轮 step0b 读本建议后，把该 cell 从 register 改为 fork（cell 级、单向）。"
    )


def _warn_pending_human_conflict(next_round: str) -> str:
    """若 pending 与 HUMAN NOTE 禁止项冲突 → stderr WARN，并在 pending 首句标注。"""
    scripts = _ROOT / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    try:
        from lib.explore_objective import pending_conflicts_with_human_note  # noqa: WPS433
    except ImportError:
        return next_round
    if not pending_conflicts_with_human_note(_ROOT, next_round):
        return next_round
    print(
        "[reflect] WARN: pending 下轮建议与 HUMAN NOTE 禁止项可能冲突，请人审",
        file=sys.stderr,
    )
    if next_round.startswith("与 HUMAN NOTE 冲突"):
        return next_round
    return _truncate_index_next_round(f"与 HUMAN NOTE 冲突，人审 — {next_round}")


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Tier-ladder 反思轮执行器")
    parser.add_argument(
        "--agent", choices=["claude", "cursor"], default="claude",
        help="使用哪个 CLI（默认 claude）"
    )
    parser.add_argument(
        "--max-tokens", type=int, default=2048,
        help="Phase1/Phase2 的 Claude/Agent 输出上限（默认 2048）；Phase3 为确定性成文，不使用本参数"
    )
    parser.add_argument(
        "--skip-phase2", action="store_true",
        help="跳过 phase2（联网搜索）；用于调试"
    )
    parser.add_argument(
        "--skip-synthesis", action="store_true",
        help="跳过 synthesis 综合推理；失败/跳过时下轮建议回退现有 _next_round_one_liner",
    )
    parser.add_argument(
        "--skip-phase0",
        action="store_true",
        help="跳过 Phase0 大模型压缩；EXPERIENCE 超长时仅用规则摘要（h2 保留 + PROTOCOL 首部节选）",
    )
    parser.add_argument(
        "--phase0-max-tokens", type=int, default=_PHASE0_MAX_TOKENS_DEFAULT,
        help="Phase0 大模型输出 token 上限（默认 %(default)s）",
    )
    parser.add_argument(
        "--phase0-out-chars", type=int, default=_PHASE0_OUT_CHARS_DEFAULT,
        help="Phase0 产出注入 Phase1 前的最大字符数（默认 %(default)s）",
    )
    parser.add_argument(
        "--no-compress",
        action="store_true",
        help="关闭全部压缩（无 Phase0、无规则摘要、无 jsonl rollup；仍截断 evaluation JSON）",
    )
    parser.add_argument(
        "--experience-raw-max", type=int, default=_EXPERIENCE_RAW_MAX_DEFAULT,
        help="EXPERIENCE.md 超过该字符数则触发 Phase0/规则摘要；不因 jsonl 行数（默认 %(default)s）",
    )
    parser.add_argument(
        "--experience-digest-chars", type=int, default=_EXPERIENCE_DIGEST_CHARS_DEFAULT,
        help="EXPERIENCE 摘要最大字符数（默认 %(default)s）",
    )
    parser.add_argument(
        "--protocol-digest-chars", type=int, default=_PROTOCOL_DIGEST_CHARS_DEFAULT,
        help="规则回退时 PROTOCOL 首部节选最大字符数（不触发 Phase0，默认 %(default)s）",
    )
    parser.add_argument(
        "--last-reflect-chars", type=int, default=_LAST_REFLECT_CHARS_DEFAULT,
        help="最近 [反思] 块注入 Phase1 的最大字符数（默认 %(default)s）",
    )
    parser.add_argument(
        "--jsonl-rollup-at", type=int, default=_JSONL_ROLLUP_AT_DEFAULT,
        help="jsonl 展平行数超过此时仅在 Phase1 附加 rollup 提示（不触发 Phase0，默认 %(default)s）",
    )
    parser.add_argument(
        "--tier-stats-rows", type=int, default=_TIER_STATS_ROWS_DEFAULT,
        help="Tier 标签统计所用的最近 N 行 description（默认 %(default)s）",
    )
    parser.add_argument(
        "--external-dry-run",
        action="store_true",
        help="Phase 1.85 只写 plan，不 HTTP",
    )
    parser.add_argument(
        "--reflect-gate",
        default="",
        help="覆盖 gate 标签（测试/auto-run 对齐）",
    )
    parser.add_argument(
        "--run",
        type=int,
        default=None,
        help="auto-run 轮次号；未指定时 gate 用手跑默认 manual:reflect_invoked",
    )
    args = parser.parse_args()

    scripts_dir = _ROOT / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from lib.reflect_runtime_check import run_check as _reflect_runtime_run_check

    _rt_ok, _rt_failures = _reflect_runtime_run_check(_ROOT)
    if not _rt_ok:
        for msg in _rt_failures:
            print(f"[reflect] FAIL: {msg}", file=sys.stderr)
        print(
            "[reflect] 治理缺失：请 bash scripts/auto-nn-update.sh --pull-template；"
            "不写 REFLECT_INDEX pending",
            file=sys.stderr,
        )
        sys.exit(2)

    runs_dir = _ROOT / "_runs"
    jsonl_path = runs_dir / "results.jsonl"
    eval_path = resolve_repo_round_decision_path(runs_dir)
    exp_path = _ROOT / "EXPERIENCE.md"
    proto_path = _ROOT / "PROTOCOL.md"
    saved_dir = _ROOT / "saved"
    saved_dir.mkdir(exist_ok=True)

    from lib.reflect_evidence import (
        build_reflect_evidence,
        enrich_reb_after_tam,
        format_gaps_experience_block,
        write_reflect_evidence_artifacts,
    )
    from lib.ledger_anchor import (
        anchors_dict,
        code_baseline_entry,
        format_leader_baseline_lines,
        metric_leader_row,
    )
    from lib.tier_attestation import (
        build_tier_attestation,
        experience_tam_conflicts,
        exhausted_tier_labels,
        format_experience_tam_warnings,
        format_tam_experience_block,
        write_tier_attestation_artifacts,
    )

    extra_metric_keys: tuple[str, ...] = ()
    try:
        from contract import create_contract

        _rc = create_contract({})
        mk_set = set(getattr(_rc, "metric_keys", {}) or {})
        mk_set.update(getattr(_rc, "auxiliary_keys", {}) or getattr(_rc, "aux_metrics", {}) or {})
        if METRIC_KEY:
            mk_set.add(METRIC_KEY)
        extra_metric_keys = tuple(sorted(mk_set))
    except Exception:
        pass

    records = _load_jsonl_records(jsonl_path)
    rows = _rows_from_jsonl_records(records, METRIC_KEY, extra_metric_keys=extra_metric_keys)
    if not rows:
        print(
            f"[reflect] WARNING: {jsonl_path} 无有效记录（缺文件、全损坏或展平均失败）；"
            "Phase 1 将按空台账继续（单槽训末由 finalize_round 写 jsonl；多槽须在全部 train 结束后执行 "
            "python -m contract finalize-round …）。",
            file=sys.stderr,
        )
    ledger_src = str(jsonl_path.relative_to(_ROOT)) if jsonl_path.is_relative_to(_ROOT) else str(jsonl_path)
    round_decision = load_repo_round_decision(runs_dir)
    eval_summary = _format_evaluation_for_phase1(round_decision)

    exp_full = _load_text(exp_path)
    proto_full = _load_text(proto_path) if proto_path.is_file() else ""
    # Phase0 / 规则摘要：仅当 EXPERIENCE 超长触发；PROTOCOL 长度不触发（只读契约）
    phase0_trigger = len(exp_full) > args.experience_raw_max
    jsonl_rollup_trigger = len(rows) > args.jsonl_rollup_at

    experience_digest, exp_compressed = "", False
    protocol_digest = ""
    ledger_rollup = ""
    context_digest = ""
    phase0_used = False
    phase0_failed = False

    if not args.no_compress:
        ledger_rollup = _jsonl_ledger_rollup_line(
            rows,
            METRIC_KEY,
            METRIC_DIRECTION,
            args.jsonl_rollup_at,
        )
        if phase0_trigger:
            if not args.skip_phase0:
                phase0_used = True
                tail_n = min(_PHASE0_JSONL_TAIL_ROWS, len(rows)) if rows else 0
                jsonl_compact = _ledger_compact_for_phase0(
                    rows, METRIC_KEY, tail_n if tail_n > 0 else 0
                )
                dynamics_compact = _dynamics_compact_for_phase0(rows, _ROOT, tail_n)
                exp_in = _clamp_str(exp_full, _PHASE0_EXPERIENCE_IN_MAX)
                proto_in = _clamp_str(proto_full, _PHASE0_PROTOCOL_IN_MAX)
                p0 = _phase0_prompt(
                    experience_body=exp_in,
                    protocol_body=proto_in,
                    jsonl_compact=jsonl_compact,
                    dynamics_compact=dynamics_compact,
                    metric_key=METRIC_KEY,
                    metric_direction=METRIC_DIRECTION,
                    out_max_chars=args.phase0_out_chars,
                )
                try:
                    print("[reflect] === Phase 0: LLM context compress ===", file=sys.stderr)
                    raw0 = _call_agent(p0, args.agent, args.phase0_max_tokens)
                    context_digest = _clamp_str(raw0.strip(), args.phase0_out_chars)
                    if not context_digest.strip():
                        phase0_failed = True
                except Exception as ex:
                    phase0_failed = True
                    context_digest = ""
                    print(f"[reflect] Phase 0 failed: {ex}", file=sys.stderr)

            if not context_digest.strip():
                experience_digest, exp_compressed = _experience_priority_digest(
                    exp_full,
                    args.experience_digest_chars,
                    args.experience_raw_max,
                )
                protocol_digest = _protocol_head_digest(
                    proto_full,
                    args.protocol_digest_chars,
                )
                chunks = [c for c in (experience_digest, protocol_digest) if c.strip()]
                context_digest = "\n\n".join(chunks).strip()
                tag = ""
                if phase0_used and phase0_failed:
                    tag = "## (Phase 0 大模型失败 — 规则摘要回退)\n\n"
                elif args.skip_phase0 and context_digest:
                    tag = "## (未使用 Phase0 — 规则摘要)\n\n"
                context_digest = (tag + context_digest).strip()

    # config-only 合规：每轮扫描 workspace 硬编码（不依赖 exploration.mode）
    # 提到 context 最前面——LLM 注意力在开头最强
    _hardcoded_ctx = _build_hardcoded_context(_ROOT)
    if _hardcoded_ctx:
        context_digest = _hardcoded_ctx + "\n\n" + (context_digest or "")

    # M1+M2 反射上下文：场景容量 + 经验律（业务仓零代码自动接入）
    # 紧跟 M3 硬编码扫描后——LLM 看到"未暴露的 cfg"和"推荐 cfg"成对出现
    _capacity_ctx = _build_capacity_context(_ROOT)
    if _capacity_ctx:
        context_digest = _capacity_ctx + "\n\n" + (context_digest or "")

    # P2 preflight gate: 提醒业务仓填 SCENARIO_CAPACITY 表（默认 WARN）
    try:
        from contract import create_contract  # noqa: WPS433
        _contract_for_gate = create_contract({})
        if hasattr(_contract_for_gate, "check_scenario_capacity"):
            _sid_for_gate = _detect_scenario_id(_ROOT)
            for _warn in _contract_for_gate.check_scenario_capacity(_sid_for_gate):
                print(f"[reflect] {_warn}", file=sys.stderr)
    except Exception as _gate_ex:
        print(f"[reflect] P2 gate skipped (non-fatal): {_gate_ex}", file=sys.stderr)

    # M4 反射上下文：同场景穷尽度（整合 task #146-157 3 子模块）
    # 紧跟 M1+M2 后——LLM 看到"推荐 cfg"+"穷尽度"成对出现
    _exhaustion_ctx = _build_exhaustion_context(_ROOT)
    if _exhaustion_ctx:
        context_digest = _exhaustion_ctx + "\n\n" + (context_digest or "")

    last_reflect = _last_reflect_section(exp_path, args.last_reflect_chars)

    print("[reflect] === Phase 0.5: reflect evidence bundle (REB) ===", file=sys.stderr)
    reb_bundle = build_reflect_evidence(_ROOT)
    evidence_md = reb_bundle.markdown
    (saved_dir / "reflect_evidence.md").write_text(evidence_md, encoding="utf-8")
    print(
        f"[reflect] REB: ets={len(reb_bundle.ets)} runs={len(reb_bundle.runs)} "
        f"gaps={len(reb_bundle.gaps)} tier_evidence={reb_bundle.tier_evidence}",
        file=sys.stderr,
    )

    print("[reflect] === Phase 0.6: tier attestation matrix (TAM) ===", file=sys.stderr)
    tam_result = build_tier_attestation(_ROOT, reb_bundle)
    tam_md = tam_result.markdown
    write_tier_attestation_artifacts(_ROOT, tam_result)
    reb_bundle = enrich_reb_after_tam(_ROOT, reb_bundle, tam_result)
    evidence_md = reb_bundle.markdown
    (saved_dir / "reflect_evidence.md").write_text(evidence_md, encoding="utf-8")
    print(
        f"[reflect] REB after TAM enrich: ets={len(reb_bundle.ets)} runs={len(reb_bundle.runs)}",
        file=sys.stderr,
    )
    print(
        f"[reflect] TAM: rows={len(tam_result.rows)} false_claims={len(tam_result.false_claims)} "
        f"line={tam_result.tam_line[:120]}",
        file=sys.stderr,
    )

    last_round = _extract_last_round_innovation(exp_path)
    tier_fb = (last_round.get("tier_this_round") or "B").strip().upper()[:1]

    # Phase 0.75 — 创新指纹
    fingerprint_dict: dict = {}
    fingerprint_line = ""
    print("[reflect] === Phase 0.75: innovation fingerprint ===", file=sys.stderr)
    try:
        from lib.innovation_fingerprint import (  # noqa: WPS433
            build_innovation_fingerprint,
            write_fingerprint_artifact,
        )

        fp_result = build_innovation_fingerprint(
            _ROOT,
            reb_bundle=reb_bundle,
            agent_depth=str(last_round.get("innovation_depth") or ""),
            tier_fallback=tier_fb or "B",
        )
        fingerprint_dict = fp_result.to_dict()
        write_fingerprint_artifact(_ROOT, fp_result)
        fingerprint_line = fp_result.summary_line or ""
        print(f"[reflect] Fingerprint: {fingerprint_line}", file=sys.stderr)
    except Exception as ex:
        print(f"[reflect] innovation fingerprint skipped (non-fatal): {ex}", file=sys.stderr)
        fingerprint_line = "[Fingerprint: error]"

    # 追加 fingerprint 到 history（diversity check 读此文件）
    if fingerprint_dict:  # 跳过 fingerprint compute 失败的轮（不污染 history）
        try:
            _fp_hist_path = _ROOT / "saved" / "fingerprint_history.jsonl"
            _fp_hist_path.parent.mkdir(parents=True, exist_ok=True)
            with _fp_hist_path.open("a", encoding="utf-8") as _fh:
                _fh.write(json.dumps(fingerprint_dict, ensure_ascii=False) + "\n")
        except Exception as _hist_err:
            print(f"[reflect] WARN fingerprint_history append: {_hist_err}", file=sys.stderr)

    # Phase 0.5+ — Fingerprint 跨轮多样性检测（防原地打转）
    # 读过去 N 轮 fingerprint summary_line（从 saved/fingerprint_history.jsonl）
    try:
        from lib.fingerprint_diversity import (
            DiversityReport,
            compute_diversity,
            DEFAULT_WINDOW,
        )
        _fp_hist_path = _ROOT / "saved" / "fingerprint_history.jsonl"
        _fp_history: list = []
        if _fp_hist_path.is_file():
            for _line in _fp_hist_path.read_text(encoding="utf-8", errors="replace").splitlines():
                _line = _line.strip()
                if not _line:
                    continue
                try:
                    _fp_history.append(json.loads(_line))
                except Exception:
                    pass
        # 取最后 N 个
        _fp_history = _fp_history[-DEFAULT_WINDOW:] if DEFAULT_WINDOW > 0 else _fp_history
        _diversity: DiversityReport = compute_diversity(_fp_history, window=DEFAULT_WINDOW)
        # 写 saved/diversity.json（供 analyse / INDEX 读）
        _diversity_path = _ROOT / "saved" / "diversity.json"
        _diversity_path.parent.mkdir(parents=True, exist_ok=True)
        _diversity_path.write_text(
            json.dumps(_diversity.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # 注入 Phase 1 context
        if _diversity.downshift_recommended:
            print(
                f"[reflect] fingerprint_diversity: downshift=Yes "
                f"swap_repeat={_diversity.primary_swap_repeat_pct:.0%} "
                f"tier_repeat={_diversity.tier_repeat_pct:.0%} "
                f"dominant={_diversity.dominant_swap} → target_tier={_diversity.downshift_target_tier}",
                file=sys.stderr,
            )
    except Exception as _div_err:
        # fail-loud 但不阻塞 reflect
        print(f"[reflect] WARN fingerprint_diversity: {_div_err}", file=sys.stderr)

    # Phase 0.7 — 创新维度审计（routine / extend / novel）
    print("[reflect] === Phase 0.7: innovation audit ===", file=sys.stderr)
    innovation_line = ""
    innovation_warnings: list[dict] = []
    if run_innovation_audit is not None:
        try:
            recent = [last_round] if last_round else None
            innov_res = run_innovation_audit(
                _ROOT,
                recent_rounds=recent,
                fingerprint=fingerprint_dict or None,
            )
            innovation_line = innov_res.summary_line or ""
            innovation_warnings = [
                {"kind": w.kind, "message": w.message} for w in innov_res.warnings
            ]
            audit_payload = innov_res.to_dict()
            (saved_dir / "innovation_audit.json").write_text(
                json.dumps(audit_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"[reflect] Innovation: {innovation_line}", file=sys.stderr)
            for w in innovation_warnings:
                print(f"[reflect] WARN innovation_audit: {w['kind']} — {w['message']}", file=sys.stderr)
        except Exception as ex:
            print(f"[reflect] innovation audit skipped (non-fatal): {ex}", file=sys.stderr)
    else:
        print("[reflect] innovation_audit module not available", file=sys.stderr)

    reflect_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    reflect_id_pre = f"R{reflect_ts}"

    # Phase 1.85 — external evidence (plan + optional HTTP)
    print("[reflect] === Phase 1.85: external evidence ===", file=sys.stderr)
    external_md = ""
    external_bundle: dict = {}
    external_plan_dict: dict = {}
    external_attestation = "skipped"
    external_summary_line = ""
    try:
        from lib.external.format_prompt import format_external_evidence_md  # noqa: WPS433
        from lib.external.reflect_hook import (  # noqa: WPS433
            format_external_experience_summary,
            run_external_evidence_phase,
        )

        external_bundle, external_plan_dict, external_attestation = run_external_evidence_phase(
            _ROOT,
            gate_label=_resolve_reflect_gate(_ROOT, args, len(rows)),
            last_round=last_round,
            tam_result=tam_result,
            innovation_warnings=innovation_warnings,
            reflect_id=reflect_id_pre,
            fingerprint=fingerprint_dict or None,
            dry_run=bool(args.external_dry_run),
            llm_query_fn=lambda p: _call_agent(p, args.agent, _QUERY_GEN_MAX_TOKENS),
        )
        external_md = format_external_evidence_md(external_bundle)
        external_summary_line = format_external_experience_summary(
            external_bundle, external_attestation
        )
        paper_hits = (external_bundle.get("paper") or {}).get("hits") or []
        print(
            f"[reflect] external: gate={external_plan_dict.get('round_state', {}).get('gate', '?')} "
            f"paper_depth={external_plan_dict.get('paper_depth')} hits={len(paper_hits)} "
            f"plateau_active={external_plan_dict.get('round_state', {}).get('plateau_active', False)} "
            f"attestation={external_attestation}",
            file=sys.stderr,
        )
    except Exception as ex:
        print(f"[reflect] external_evidence failed (non-fatal): {ex}", file=sys.stderr)
        external_md = "（Phase 1.85 失败；禁止编造 url）"

    # 台账 exploration_space（优先 attested_depth 以区分 different/novel）
    # 默认 sync 仅升格已有 *-different → *-novel，不填空格。
    try:
        import subprocess

        _sync = _ROOT / "scripts" / "sync_exploration_ledger.py"
        if _sync.is_file():
            subprocess.run(
                [sys.executable, str(_sync), "--repo-root", str(_ROOT)],
                cwd=str(_ROOT),
                check=False,
            )
    except Exception as _sync_exc:
        print(f"[reflect] WARN sync_exploration_ledger: {_sync_exc}", file=sys.stderr)

    # 改题落地：NN_RELAUNCH + contract/ 相对上一有效轮有 diff → executed（格子仍 A–D）
    try:
        _maybe_record_executed_e_feedback(
            _ROOT,
            fingerprint=fingerprint_dict or None,
            round_decision=round_decision,
            metric_key=METRIC_KEY,
            round_hint=len(rows) if rows else None,
        )
    except Exception as _ef_ex:
        print(f"[reflect] WARN e_feedback executed: {_ef_ex}", file=sys.stderr)

    # Phase 1.86 — find stage（T4/ADR-6：评估的事双胞胎）
    # 撞墙 ∧ depth∈{different,novel} 触发 → 强制 P3+ 全文捞可借力的候选部件 →
    # saved/find_candidates.json，经 collect_round_evidence 注入下轮 run context。
    # 反馈边数据；catalog 落盘在 T8。非致命（与 Phase 1.85 同模式）。
    find_candidates: dict = {}
    try:
        from lib.external.reflect_hook import run_find_phase  # noqa: WPS433
        find_candidates = run_find_phase(
            _ROOT,
            gate_label=_resolve_reflect_gate(_ROOT, args, len(rows)),
            last_round=last_round,
            tam_result=tam_result,
            innovation_warnings=innovation_warnings,
            reflect_id=reflect_id_pre,
            fingerprint=fingerprint_dict or None,
            dry_run=bool(args.external_dry_run),
            llm_query_fn=lambda p: _call_agent(p, args.agent, _QUERY_GEN_MAX_TOKENS),
        )
    except Exception as ex:
        print(f"[reflect] find_stage failed (non-fatal): {ex}", file=sys.stderr)
        find_candidates = {}

    leader = metric_leader_row(_ROOT)
    baseline = code_baseline_entry(_ROOT)
    anchor_lines = format_leader_baseline_lines(_ROOT)
    ml_exp = leader.experiment if leader else "?"
    ml_metric = str(leader.metric_value) if leader else "?"
    cb_exp = (baseline.experiment if baseline else "") or ""

    print(f"[reflect] agent={args.agent} max_tokens={args.max_tokens}", file=sys.stderr)
    print(f"[reflect] ledger: {ledger_src} — {len(rows)} rows", file=sys.stderr)
    if round_decision:
        print(f"[reflect] _runs/round_decision.json: present ({eval_path})", file=sys.stderr)
    else:
        print(
            f"[reflect] _runs/round_decision.json: missing or empty ({eval_path or runs_dir / 'round_decision.json'})",
            file=sys.stderr,
        )
    if args.no_compress:
        print("[reflect] compression: off (--no-compress)", file=sys.stderr)
    else:
        print(
            f"[reflect] phase0_trigger={phase0_trigger} jsonl_rollup={jsonl_rollup_trigger} "
            f"phase0_used={phase0_used} phase0_failed={phase0_failed} "
            f"context_chars={len(context_digest)}",
            file=sys.stderr,
        )
    if ledger_rollup:
        print("[reflect] jsonl rollup hint appended to Phase1 trend", file=sys.stderr)

    # Phase 1+ — Leader vs current 差距归因（撞墙时给具体 actionable 建议）
    try:
        from lib.leader_attribution import (
            LeaderAttribution, compute_leader_attribution,
        )
        _round = round_decision or {}
        _keeper_path = _ROOT / "saved" / "keeper.json"
        if not _keeper_path.is_file():
            _keeper_path = _ROOT / "saved" / "keepers.json"
        _current_config_path = _round.get("evaluated_exp_dir", "")
        if _current_config_path:
            _cur_cfg = Path(_current_config_path) / "configs" / "config.json"
        else:
            _cur_cfg = _ROOT / "_runs" / "configs" / "exp.json"
        _leader_cfg = _keeper_path.parent / "keeper_config.json"
        if _keeper_path.is_file():
            try:
                _keeper_data = json.loads(_keeper_path.read_text(encoding="utf-8"))
                _keeper_exp_dir = (_keeper_data.get("default") or {}).get("exp_dir", "")
                if not _keeper_exp_dir and isinstance(_keeper_data, list):
                    _keeper_exp_dir = _keeper_data[0].get("exp_dir", "")
                _leader_cfg = Path(_keeper_exp_dir) / "configs" / "config.json" if _keeper_exp_dir else _leader_cfg
                _leader_metric = (_keeper_data.get("default") or {}).get("test_acc", 0.0)
            except Exception:
                _leader_metric = 0.0
        else:
            _leader_metric = 0.0
        if _leader_cfg.is_file() and _cur_cfg.is_file():
            _attr = compute_leader_attribution(
                leader_config_path=_leader_cfg,
                current_config_path=_cur_cfg,
                leader_metric=_leader_metric,
                current_metric=_round.get("primary_metric", {}).get("value", 0.0),
            )
            _attr_path = _ROOT / "saved" / "leader_attribution.json"
            _attr_path.parent.mkdir(parents=True, exist_ok=True)
            _attr_path.write_text(
                json.dumps(_attr.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            if _attr.missing_in_current and _attr.gap > 0:
                print(
                    f"[reflect] leader_attribution: missing={_attr.missing_in_current} "
                    f"gap={_attr.gap:.4f} confidence={_attr.confidence}",
                    file=sys.stderr,
                )
    except Exception as _attr_err:
        print(f"[reflect] WARN leader_attribution: {_attr_err}", file=sys.stderr)

    # Phase 1：分析信号
    print("[reflect] === Phase 1: analyzing signals ===", file=sys.stderr)
    try:
        from lib.e_feedback_store import format_shout_resolution_hint  # noqa: WPS433

        e_feedback_md = format_shout_resolution_hint(_ROOT)
    except Exception as _efh:
        e_feedback_md = ""
        print(f"[reflect] WARN e_feedback hint: {_efh}", file=sys.stderr)
    p1_prompt = _phase1_prompt(
        METRIC_KEY,
        rows,
        last_reflect,
        ledger_hint=ledger_src,
        eval_summary=eval_summary,
        context_digest=context_digest,
        ledger_rollup=ledger_rollup,
        evidence_md=evidence_md,
        tam_md=tam_md,
        anchor_lines=anchor_lines,
        metric_leader_exp=ml_exp,
        metric_leader_metric=ml_metric,
        code_baseline_exp=cb_exp,
        innovation_line=innovation_line,
        fingerprint_line=fingerprint_line,
        external_md=external_md,
        e_feedback_md=e_feedback_md,
    )

    phase1 = {}
    raw1 = ""
    try:
        raw1 = _call_agent(p1_prompt, args.agent, args.max_tokens)
        # 提取 JSON 块（Claude 有时裹在 markdown 里）
        m = re.search(r'\{[^{}]*"wall_crash"[^{}]*\}', raw1, re.DOTALL)
        json_str = m.group(0) if m else raw1
        # 容错：LLM 常在 JSON 后追加解释 → raw_decode 取首对象（修 "Extra data"）
        phase1 = _parse_json_lenient(json_str)
        if phase1 is None:
            phase1 = _parse_json_lenient(raw1)
        if not isinstance(phase1, dict):
            raise ValueError("no JSON object found in Phase 1 output")
        if tam_result.not_attested_tiers:
            phase1["not_tried_tiers"] = list(tam_result.not_attested_tiers)
        if tam_result.rollup:
            attested = [
                f"Tier {k}"
                for k, v in tam_result.rollup.items()
                if v.get("status") in ("attested", "exhausted", "shallow")
            ]
            if attested:
                phase1["tried_tiers"] = attested
        _apply_phase1_anchors(phase1, _ROOT)
        print(f"[reflect] Phase 1: wall_crash={phase1.get('wall_crash')}", file=sys.stderr)
        print(f"[reflect] Phase 1: not_tried={phase1.get('not_tried_tiers')}", file=sys.stderr)
    except Exception as ex:
        print(f"[reflect] Phase 1 parse failed: {ex}", file=sys.stderr)
        print("[reflect] raw (first 200):", (raw1[:200] if raw1 else "(empty)"), file=sys.stderr)
        # fallback
        phase1 = {
            "wall_crash": False,
            "streak_count": 0,
            "streak_tier": "unknown",
            "not_tried_tiers": tam_result.not_attested_tiers or ["Tier B", "Tier C", "Tier D"],
            "tried_tiers": [
                f"Tier {k}"
                for k, v in (tam_result.rollup or {}).items()
                if v.get("status") in ("attested", "exhausted", "shallow")
            ],
            "key_insight": "（Phase 1 分析失败）",
            "phase2_focus": "physical-constraint / operator-learning improvement",
        }
        _apply_phase1_anchors(phase1, _ROOT)

    # 改题主张：Phase 1 结构化三键齐全 → shout（禁止扫 Tier E 散文）
    try:
        _maybe_record_shout_e_feedback(
            _ROOT,
            phase1 if isinstance(phase1, dict) else {},
            fingerprint=fingerprint_dict or None,
            round_decision=round_decision,
            round_hint=int(phase1.get("streak_count") or 0) or (len(rows) if rows else None),
        )
    except Exception as _sh_ex:
        print(f"[reflect] WARN e_feedback shout: {_sh_ex}", file=sys.stderr)

    # Phase 2：知识召回（含 references/ 读取）
    phase2 = {"findings": [], "references_to_add": []}
    if not args.skip_phase2:
        print("[reflect] === Phase 2: knowledge search ===", file=sys.stderr)
        from lib.external.task_domain import resolve_task_domain  # noqa: WPS433
        _task_domain = resolve_task_domain(_ROOT)
        p2_prompt = _phase2_prompt(phase1, task_domain=_task_domain)
        try:
            raw2 = _call_agent(p2_prompt, args.agent, args.max_tokens)
            # 尝试完整解析裸 JSON（Phase 2 被要求无 markdown fence）
            phase2 = {"findings": [], "references_to_add": []}
            raw2_stripped = raw2.strip()
            if raw2_stripped.startswith("```"):
                raw2_stripped = raw2_stripped.split("```")[1]
                if raw2_stripped.startswith("json"):
                    raw2_stripped = raw2_stripped[4:]
            # 容错：raw_decode 取首对象/数组（修 "Extra data"；LLM JSON 后常追加解释）
            parsed = _parse_json_lenient(raw2_stripped)
            if isinstance(parsed, dict):
                phase2 = {
                    "findings": parsed.get("findings", []),
                    "references_to_add": parsed.get("references_to_add", []),
                }
            elif isinstance(parsed, list):
                # fallback: LLM 直接吐了 findings 数组
                phase2["findings"] = parsed
            else:
                # fallback: 找 findings 数组
                m = re.search(r'\[[\s\S]*?"findings"[\s\S]*?\]', raw2, re.DOTALL)
                if m:
                    arr = _parse_json_lenient(m.group(0))
                    if isinstance(arr, list):
                        phase2["findings"] = arr
            print(f"[reflect] Phase 2: {len(phase2.get('findings', []))} findings, "
                  f"{len(phase2.get('references_to_add', []))} refs_to_add", file=sys.stderr)
        except Exception as ex:
            print(f"[reflect] Phase 2 failed (non-fatal): {ex}", file=sys.stderr)
    else:
        print("[reflect] === Phase 2: skipped (--skip-phase2) ===", file=sys.stderr)

    # P1-4 defensive: normalize findings / references_to_add to list-of-dicts.
    # LLM 偶发返回 ["裸字符串"] 或裸字符串（经 line 2540/2546 fallback 进入），
    # 下游 sanitize / merge / Phase3 / refs-auto 均假设 dict 元素并 .get() → 崩溃（csi reflect.py:2812）。
    # 在任何 consumer 之前统一规整：dict 原样保留，str 包成最小 dict，非 list 强制成 []。
    for _fk in ("findings", "references_to_add"):
        _fv = phase2.get(_fk)
        if isinstance(_fv, list):
            phase2[_fk] = [
                f if isinstance(f, dict)
                else {"summary": str(f), "tier": "?", "url": "", "source": "llm_string"}
                for f in _fv
            ]
        elif isinstance(_fv, dict):
            phase2[_fk] = [_fv]
        elif _fv is None:
            phase2[_fk] = []
        else:
            phase2[_fk] = [{"summary": str(_fv), "tier": "?", "url": "", "source": "llm_string"}]

    # Phase 1.85 API hits 合流进 phase2 findings（spec §R5）
    try:
        phase2 = _merge_external_hits_into_phase2(phase2, external_bundle, cap=5)
        print(
            f"[reflect] Phase 2 merge: {sum(1 for f in phase2.get('findings', []) if f.get('source') == 'external_api')} external_api findings",
            file=sys.stderr,
        )
    except Exception as ex:
        print(f"[reflect] Phase 2 merge failed (non-fatal): {ex}", file=sys.stderr)

    # Phase 2.6 — trained_knowledge arXiv title 错配降级（spec §R7）
    try:
        from lib.external.arxiv import fetch_arxiv_title_by_id  # noqa: WPS433
        from lib.external.phase2_sanitize import sanitize_phase2_findings  # noqa: WPS433

        phase2, _n_mismatch = sanitize_phase2_findings(
            phase2,
            title_fetcher=fetch_arxiv_title_by_id,
            max_checks=6,
        )
        if _n_mismatch:
            print(
                f"[reflect] Phase 2.6: sanitized {_n_mismatch} arXiv title mismatches",
                file=sys.stderr,
            )
    except Exception as ex:
        print(f"[reflect] Phase 2.6 sanitize failed (non-fatal): {ex}", file=sys.stderr)

    # Phase 2.5 — references_to_add url 必须来自当轮 external_bundle
    try:
        from lib.external.validate_urls import (  # noqa: WPS433
            bundle_empty_for_refs,
            filter_references_to_add,
        )

        if bundle_empty_for_refs(external_bundle):
            if phase2.get("references_to_add"):
                print(
                    "[reflect] WARN external_url_not_in_bundle: empty bundle — clearing references_to_add",
                    file=sys.stderr,
                )
            phase2["references_to_add"] = []
        else:
            refs_raw = phase2.get("references_to_add") or []
            phase2["references_to_add"] = filter_references_to_add(refs_raw, external_bundle)
            print(
                f"[reflect] Phase 2.5: {len(phase2.get('references_to_add', []))} refs after url validation",
                file=sys.stderr,
            )
    except Exception as ex:
        print(f"[reflect] Phase 2.5 url validation failed (non-fatal): {ex}", file=sys.stderr)

    # synthesis 综合推理：跨证据 → 下一步建议（Task 4；详见 spec §5）
    synthesis: dict | None = None
    if args.skip_synthesis:
        print("[reflect] === synthesis: skipped (--skip-synthesis) ===", file=sys.stderr)
    else:
        print("[reflect] === synthesis: cross-referencing evidence + history ===", file=sys.stderr)
        # 4 类反射上下文（M1-M4）— 算结构化 dict 给 synthesis 5→9 入参
        # 容错：业务仓 contract 可能没有 list_capacity / list_scaling_recommendation
        # （老 init 的项目，governance-sync 不改 contract/）
        _cap = {}
        _scaling = {}
        try:
            from contract import create_contract  # noqa: WPS433
            _contract = create_contract({})
            if hasattr(_contract, "list_capacity"):
                _sid = _detect_scenario_id(_ROOT)
                _cap = _contract.list_capacity(_sid) if _sid else {}
                if hasattr(_contract, "list_scaling_recommendation"):
                    _history_best_cap = None
                    _scaling = _contract.list_scaling_recommendation(_cap, _history_best_cap) if _cap else {}
        except Exception as ex:
            print(f"[reflect] M1+M2 contract query skipped (non-fatal): {ex}", file=sys.stderr)
        _exh = compute_exhaustion_metric(_ROOT)  # dict 形态
        synthesis = _run_synthesis_phase(
            phase1=phase1, phase2=phase2, external_bundle=external_bundle,
            tam_not_attested=tam_result.not_attested_tiers,
            fingerprint=fingerprint_dict or None,
            call_agent_fn=lambda p: _call_agent(p, args.agent, args.max_tokens),
            max_tokens=args.max_tokens,
            capacity_card=_cap if any(v is not None for v in _cap.values()) else None,
            scaling_recommendation=_scaling if _scaling else None,
            hardcoded_context=_build_hardcoded_context(_ROOT),
            exhaustion_metric=_exh if (
                _exh.get("diversity") or _exh.get("leader") or _exh.get("tam_reconcile")
            ) else None,
        )

    # Phase 3 前 — EXPERIENCE ↔ TAM 一致性 reconcile
    try:
        from lib.tam_reconcile import reconcile_tam_with_experience
        _recon = reconcile_tam_with_experience(
            repo_root=_ROOT,
            experience_md_path=_ROOT / "EXPERIENCE.md",
        )
        if _recon.action == "promote":
            _tam_p = _ROOT / "saved" / "tier_attestation.json"
            _tam_d = {}
            if _tam_p.is_file():
                try:
                    _tam_d = json.loads(_tam_p.read_text(encoding="utf-8"))
                except Exception:
                    _tam_d = {}
            _tam_d.setdefault(_recon.tier, {"status": "not_attested", "evidence": []})
            _tam_d[_recon.tier]["status"] = "attested"
            _tam_d[_recon.tier]["evidence"] = _tam_d[_recon.tier].get("evidence", []) + [
                f"promoted by tam_reconcile {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
            ]
            _tam_p.parent.mkdir(parents=True, exist_ok=True)
            _tam_p.write_text(json.dumps(_tam_d, ensure_ascii=False, indent=2), encoding="utf-8")
            if (_ROOT / "EXPERIENCE.md").is_file():
                _md = (_ROOT / "EXPERIENCE.md").read_text(encoding="utf-8")
                if _recon.tier_attested_marker not in _md:
                    _md = _md.rstrip() + f"\n\n{_recon.tier_attested_marker}\n"
                    (_ROOT / "EXPERIENCE.md").write_text(_md, encoding="utf-8")
            print(
                f"[reflect] tam_reconcile: action=promote tier={_recon.tier} "
                f"({_recon.tam_before}→{_recon.tam_after}) evidence={_recon.evidence_count}",
                file=sys.stderr,
            )
        elif _recon.action == "conflict":
            print(
                f"[reflect] WARN tam_reconcile: {_recon.conflict_reason}（不 promote，FAIL-LOUD）",
                file=sys.stderr,
            )
        (_ROOT / "saved").mkdir(parents=True, exist_ok=True)
        (_ROOT / "saved" / "tam_reconcile.json").write_text(
            json.dumps(_recon.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as _recon_err:
        print(f"[reflect] WARN tam_reconcile: {_recon_err}", file=sys.stderr)

    # Phase 3：确定性紧凑 Markdown（不调用大模型）
    print("[reflect] === Phase 3: compact markdown (no agent) ===", file=sys.stderr)
    final_block = ""
    try:
        final_block = _phase3_markdown_compact(
            METRIC_KEY,
            phase1,
            phase2,
            tam_line=tam_result.tam_line,
            tam_not_attested=tam_result.not_attested_tiers,
            innovation_line=innovation_line,
            external_summary_line=external_summary_line,
            synthesis=synthesis,
        )
    except Exception as ex:
        print(f"[reflect] Phase 3 failed: {ex}", file=sys.stderr)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        final_block = (
            f"## [反思] {ts} (自动反思轮 — 成文失败)\n\n"
            f"- **撞墙信号**: {phase1.get('wall_crash_detail', '?')}\n"
            f"- **台账**: 见 `saved/reflect_latest.json`\n"
            f"- **备注**: Phase3 紧凑成文异常，请人工补写；`root_analysis` 见该 JSON 的 phase1。\n"
        )

    gaps_block = format_gaps_experience_block(reb_bundle.gaps)
    tam_block = format_tam_experience_block(tam_result)
    tam_conflicts = experience_tam_conflicts(exp_full, tam_result.rollup)
    for msg in tam_conflicts:
        print(f"[reflect] WARN experience_tam: {msg}", file=sys.stderr)
    tam_warn_block = format_experience_tam_warnings(tam_conflicts)

    # 追加到 EXPERIENCE.md
    with open(exp_path, "a", encoding="utf-8") as f:
        f.write("\n\n")
        f.write(final_block)
        if tam_block.strip():
            f.write("\n\n")
            f.write(tam_block)
        if tam_warn_block.strip():
            f.write("\n\n")
            f.write(tam_warn_block)
        if gaps_block.strip():
            f.write("\n\n")
            f.write(gaps_block)

    print("[reflect] Appended to EXPERIENCE.md. Preview:", file=sys.stderr)
    print(final_block[:500], file=sys.stderr)

    # 长文写入 references/auto/；更新 REFLECT_INDEX pending
    refs_to_add = phase2.get("references_to_add", [])
    ts_refs = reflect_ts
    refs_dir = _references_auto_dir()
    refs_file = refs_dir / f"{ts_refs}_auto_reflected.md"
    ki_full = _collapse_ws(str(phase1.get("key_insight") or ""))
    direction_full = _compute_direction_base(synthesis, phase1)  # synthesis 成功 → 用综合建议；否则回退 one-liner
    direction_full = _apply_dual_audience_direction(
        direction_full, tam_not_attested=tam_result.not_attested_tiers,
    )
    if tam_result.tam_line:
        direction_full = f"{direction_full} {tam_result.tam_line}"
    if innovation_line:
        direction_full = f"{direction_full} {innovation_line}"
    direction_full = _warn_exhausted_tier_in_suggestion(direction_full, tam_result.rollup)
    exhausted = exhausted_tier_labels(tam_result.rollup)
    if exhausted:
        print(f"[reflect] TAM exhausted: {', '.join(exhausted)}", file=sys.stderr)
    direction_full = _warn_pending_human_conflict(direction_full)
    # fork 触发（spec §4 步4）：source_block 核验确认 → 追加 register→fork 升级建议
    fork_advice = _fork_upgrade_advice(round_decision)
    if fork_advice:
        direction_full = (direction_full + " " + fork_advice) if direction_full else fork_advice
    # Ticket 05 §11：可执行建议（论文→注册项→骨架）进 direction_full（复用 1.17.0 通道，
    # reflect_hook 已把 advice+骨架挂 external_bundle.paper.executable_advice）。无 advice → 跳过。
    from lib.external.executable_advice import executable_advice_block  # noqa: WPS433
    advice_block = executable_advice_block(external_bundle)
    if advice_block:
        direction_full = (direction_full + " " + advice_block) if direction_full else advice_block
    reflect_quality = "ok"
    _ki = str(phase1.get("key_insight") or "")
    if phase0_failed or "Phase 1 分析失败" in _ki or not _ki.strip():
        reflect_quality = "low"
    index_next_round = _truncate_index_next_round(direction_full)
    if reflect_quality == "low":
        index_next_round = _truncate_index_next_round(
            f"{index_next_round} [quality:low — 须结合 exp 目录验证，勿盲跟]"
        )
    try:
        from lib.external.reflect_hook import format_3source_status_lines  # noqa: WPS433
        from lib.external.validate_urls import (  # noqa: WPS433
            format_external_plan_summary,
            render_verified_external_lines,
        )

        external_plan_line = format_external_plan_summary(external_bundle, external_plan_dict)
        # spec T6: 3 源状态行（paper/docs/github 关时显式 "未启用"，防 silent skip）
        external_3source_block = format_3source_status_lines(external_plan_dict)
        verified_lines = render_verified_external_lines(external_bundle, refs_to_add)
    except Exception as ex:
        print(f"[reflect] external verified section skipped (non-fatal): {ex}", file=sys.stderr)
        external_plan_line = ""
        external_3source_block = ""
        verified_lines = []

    ref_lines = [
        f"# Auto-reflected @ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        f"**撞墙**: {_wall_short_from_phase1(phase1)}",
        f"**下轮建议**: {direction_full}",
        "",
        "## 简要洞察",
        ki_full or "（无）",
        "",
    ]
    if external_plan_line:
        ref_lines.append(external_plan_line)
        ref_lines.append("")
    if external_3source_block:
        # spec T6: 显式 "未启用" 提示，避免 agent 把 silent skip 误读为"查了"
        ref_lines.append(external_3source_block)
        ref_lines.append("")
    ref_lines.append("## 外部证据（已验证）")
    ref_lines.append("")
    ref_lines.extend(verified_lines if verified_lines else ["（本轮无已验证外部条目）", ""])
    if refs_to_add:
        ref_lines.append("## 外部文献条目")
        ref_lines.append("")
        for r in refs_to_add:
            ref_lines.extend([
                f"### {r.get('title', '?')}",
                f"**Tier**: {r.get('tier', '?')}  |  **URL**: {r.get('url', 'n/a')}",
                "",
                str(r.get("summary") or ""),
                "",
            ])
    else:
        findings = phase2.get("findings") or []
        if findings:
            ref_lines.append("## Phase2 线索（截断）")
            ref_lines.append("")
            for f in findings[:5]:
                ref_lines.append(
                    f"- [{f.get('tier', '?')}] {_truncate_text(str(f.get('summary') or ''), 200)}"
                )
            ref_lines.append("")
    refs_file.write_text("\n".join(ref_lines), encoding="utf-8")
    print(f"[reflect] Wrote {refs_file}", file=sys.stderr)

    reflect_id = reflect_id_pre
    detail_rel = f"references/auto/{ts_refs}_auto_reflected.md"
    write_reflect_evidence_artifacts(_ROOT, reb_bundle, reflect_id=reflect_id)
    _tier_index = _suggest_tier_from_phase1(phase1)
    if reflect_quality == "low":
        _tier_index = f"{_tier_index} [quality:low]"
    _update_reflect_index(
        reflect_id=reflect_id,
        ts_display=datetime.now().strftime("%Y-%m-%d %H:%M"),
        wall_short=_wall_short_from_phase1(phase1),
        next_round=index_next_round,
        tier_letter=_tier_index,
        detail_rel=detail_rel,
    )

    # 保存状态供后续轮次参考
    state = {
        "phase1": phase1,
        "phase2": phase2,
        "synthesis": synthesis,
        "reflect_id": reflect_id,
        "reb": {
            "ets_count": len(reb_bundle.ets),
            "gaps_count": len(reb_bundle.gaps),
            "tier_evidence": reb_bundle.tier_evidence,
            "evidence_path": "saved/reflect_evidence.json",
            "gaps_path": "saved/reflect_evidence_gaps.json",
        },
        "tam": {
            "tam_line": tam_result.tam_line,
            "false_claims": len(tam_result.false_claims),
            "path": "saved/tier_attestation.json",
        },
        "anchors": anchors_dict(_ROOT),
        "timestamp": datetime.now().isoformat(),
        "quality": reflect_quality,
        "compression": {
            "no_compress": bool(args.no_compress),
            "phase0_trigger": phase0_trigger,
            "jsonl_rollup_trigger": jsonl_rollup_trigger,
            "phase0_used": phase0_used,
            "phase0_failed": phase0_failed,
            "skip_phase0": bool(args.skip_phase0),
            "context_chars": len(context_digest),
            "experience_chars_full": len(exp_full),
            "experience_rule_digest_chars": len(experience_digest),
            "experience_rule_compressed": exp_compressed,
            "protocol_rule_digest_chars": len(protocol_digest),
            "last_reflect_chars": len(last_reflect),
            "jsonl_rows": len(rows),
            "ledger_rollup": bool(ledger_rollup),
        },
        "external": {
            "reflect_id": reflect_id,
            "hits_count": len((external_bundle.get("paper") or {}).get("hits") or []),
            "skipped": (external_bundle.get("meta") or {}).get("skipped") or [],
            "path": "saved/evidence_bundle.json",
        },
    }
    archive_dir = saved_dir / "external_evidence"
    archive_dir.mkdir(parents=True, exist_ok=True)
    if external_bundle:
        (archive_dir / f"{reflect_id}.json").write_text(
            json.dumps(external_bundle, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(
            f"[reflect] Archived external bundle to saved/external_evidence/{reflect_id}.json",
            file=sys.stderr,
        )

    with open(saved_dir / "reflect_latest.json", "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

    print("[reflect] State saved to saved/reflect_latest.json", file=sys.stderr)
    print("[reflect] Done.", file=sys.stderr)


if __name__ == "__main__":
    main()
