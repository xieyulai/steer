"""三态 lock normalize：已结构化 / 人话模板 / 不可结构化。

调用方：append-init-qa-log.py 在 append_entry 前 normalize(--lock TEXT)。
返回 (normalized_text, warns)。
"""
from __future__ import annotations

import csv
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

from lib.lock_terminology import LOCK_FIELDS


# ── 模板 regex 编译（6 种）───────────────────────────────────────

# S1: "K=主 X 锁 Y" 或 "K=主 X 锁 Y" → T1.HARD=Y
_RE_S1_KV_LOCK = re.compile(
    r"^([A-Z]\d+)\s*=\s*主\s+\S+\s+锁\s+(.+?)$"
)

# S2: "K=v[; K2=v2]" 半结构化（已编码） → 原样落
# 判定：含 ";" 分隔且至少一个 K=v 在 LOCK_FIELDS 集内
_RE_S2_KV_CODED = re.compile(
    r"^([A-Z_][A-Z0-9_]*)\s*=\s*[^;]+"
)

# S3: "其余（a/b/c/d）允许 Agent 调" → "T1.ALLOWED=[a,b,c,d]"
_RE_S3_ALLOWED = re.compile(
    r"其余\s*[（(]([^\)）]+)[)）]\s*允许\s*Agent\s*调"
)

# S4: mammoth 风格 "agent.X=y; keep mammoth ..." → 部分识别（agent.X 不在 LOCK_FIELDS）
# 处理：识别 LOCK_FIELDS 内的 K=v；不在的保留
_RE_S4_KV_ITEM = re.compile(
    r"([A-Z_][A-Z0-9_]*)\s*=\s*([^;]+)"
)

# S5: "scenario: X; metrics: a/b/c" → "SCENARIO=X; METRICS=[a,b,c]"
_RE_S5_SCENARIO = re.compile(r"scenario\s*:\s*([a-zA-Z_][a-zA-Z0-9_-]*)")
_RE_S5_METRICS = re.compile(r"metrics\s*:\s*([a-zA-Z_][a-zA-Z0-9_/\-,]*)")

# S6: "K: v（备注）" 或 "K: v(remark)" → "K=v"
_RE_S6_NOTE_TAIL = re.compile(r"[（(]([^)）]*)[)）]\s*$")


def normalize_lock(text: str, slug: str = "") -> Tuple[str, List[str]]:
    """三态 normalize lock 文本。
    Returns: (normalized_text, warns)
      - normalized_text: 写盘的 lock 文本（已结构化/人话模板/不可结构化原样）
      - warns: 列表（仅不可结构化 / 部分字段未识别时填充）
    """
    text = (text or "").strip()
    if not text:
        return ("", [])
    warns: List[str] = []

    # ── 态 1：已是嵌套编码（T1.HARD=X; T1.TUNABLE=Y） ───────
    # 判定：存在 "." 子键 且 任一字段在 LOCK_FIELDS 集
    if re.search(r"\b[A-Z]\d+\.[A-Z_]+\s*=", text):
        return (text, [])

    # ── 态 2：人话模板识别 ──────────────────────────────────
    # S3："其余（a/b/c）允许 Agent 调" → T1.ALLOWED=[a,b,c]
    m_s3 = _RE_S3_ALLOWED.search(text)
    if m_s3:
        keys_text = m_s3.group(1)
        keys = [k.strip() for k in keys_text.split("/") if k.strip()]
        keys = [k.replace(" ", "_") for k in keys]
        return (f"{slug}.ALLOWED=[{','.join(keys)}]" if slug else f"ALLOWED=[{','.join(keys)}]", [])

    # S1："T1=主 X 锁 Y" → "T1.HARD=Y"
    m_s1 = _RE_S1_KV_LOCK.match(text)
    if m_s1:
        slug_name, hard = m_s1.group(1), m_s1.group(2).strip()
        return (f"{slug_name}.HARD={hard}", [])

    # S5："scenario: X; metrics: a/b/c"
    if _RE_S5_SCENARIO.search(text) or _RE_S5_METRICS.search(text):
        out_parts = []
        m_sc = _RE_S5_SCENARIO.search(text)
        if m_sc:
            out_parts.append(f"SCENARIO={m_sc.group(1)}")
        m_me = _RE_S5_METRICS.search(text)
        if m_me:
            metrics = [m.strip() for m in m_me.group(1).split("/") if m.strip()]
            out_parts.append(f"METRICS=[{','.join(metrics)}]")
        return ("; ".join(out_parts), [])

    # S6："K: v（note）" → "K=v"
    m_s6 = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*([^（(]+)", text)
    if m_s6:
        k_raw, v_raw = m_s6.group(1), m_s6.group(2).strip()
        k_up = k_raw.upper().replace(".", "_")
        # 仅 LOCK_FIELDS 集内或步骤前缀（E/T/D/G/O）大写转换
        if (k_up in LOCK_FIELDS) or (len(k_raw) <= 4 and k_raw[0].isupper()):
            # 剥离尾部括号注
            v_clean = _RE_S6_NOTE_TAIL.sub("", v_raw).strip()
            return (f"{k_up}={v_clean}", [])

    # S2 半结构化：含步骤前缀（O2=...）或 LOCK_FIELDS 字段 → 视为已编码，原样落
    # 步骤前缀：字母+数字（如 O2/T1/E6/G3/D4/P0 等 ≤4 字符大写）
    has_step_prefix = bool(re.match(r"^[A-Z]\d+\s*=", text))
    s2_parts = _RE_S4_KV_ITEM.findall(text)
    has_lock_field = any(
        (p[0].upper() in LOCK_FIELDS or p[0].upper().replace(".", "_") in LOCK_FIELDS)
        for p in s2_parts
    )
    if has_step_prefix or has_lock_field:
        if has_lock_field:
            # 大写化已识别的 key
            normalized_parts = []
            for k, v in s2_parts:
                k_up = k.upper().replace(".", "_")
                if k_up in LOCK_FIELDS:
                    v = _RE_S6_NOTE_TAIL.sub("", v).strip()
                    normalized_parts.append(f"{k_up}={v}")
                else:
                    normalized_parts.append(f"{k}={v}")
            return ("; ".join(normalized_parts), [])
        return (text, [])

    # ── 态 3：不可结构化 ─────────────────────────────────────
    warns.append("unrecognized_template")
    return (text, warns)


def write_warn_log(slug: str, text: str, reason: str, log_path: "str | Path") -> None:
    """append-only CSV：timestamp,slug,reason,excerpt。

    log_path 通常是 <repo>/.auto-nn/lock_normalize_warnings.log。
    parent dir 不存在自动 mkdir（事务宽限）。
    """
    p = Path(log_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    excerpt = (text[:60] + "…") if len(text) > 60 else text
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with p.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([timestamp, slug, reason, excerpt])


def emit_stderr_warning(slug: str, text: str, reason: str) -> None:
    """stderr 实时打印（人类可见，不落 .log 也能看到）。"""
    excerpt = (text[:60] + "…") if len(text) > 60 else text
    print(f"⚠ lock_normalize: slug={slug} reason={reason} text={excerpt}", file=sys.stderr, flush=True)