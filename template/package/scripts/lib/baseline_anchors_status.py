"""基线尺子（plain / reference）状态体检 — 供 analyse / check 共用。"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BaselineAnchorsStatus:
    has_plain: bool
    has_reference_number: bool
    has_reference_run: bool
    plain_value: float | None = None
    reference_value: float | None = None
    plain_tag_rows: int = 0
    reference_tag_rows: int = 0
    none_tag_rows: int = 0
    baseline_tag_col: bool = False
    intent_start_runs: str | None = None
    recommendations: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def has_reference(self) -> bool:
        return self.has_reference_number or self.has_reference_run

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _plain_anchor_value(root: Path) -> float | None:
    p = root / "saved" / "plain_anchor.json"
    if p.is_file():
        try:
            d = json.loads(_read_text(p))
            v = d.get("plain_anchor_value")
            if isinstance(v, (int, float)):
                return float(v)
        except Exception:
            pass
    exp = root / "EXPERIENCE.md"
    if not exp.is_file():
        return None
    text = _read_text(exp)
    m = re.search(r"^## Tier 状态.*?\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        return None
    for line in m.group(1).splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 6:
            continue
        mm = re.search(
            r"plain_anchor_value\s*=\s*([\-+]?\d+(?:\.\d+)?(?:[eE][\-+]?\d+)?)",
            cells[-1],
        )
        if mm:
            try:
                return float(mm.group(1))
            except ValueError:
                return None
    return None


def _reference_anchor_value(root: Path) -> float | None:
    p = root / "saved" / "reference_anchor.json"
    if p.is_file():
        try:
            d = json.loads(_read_text(p))
            v = d.get("reference_anchor_value")
            if isinstance(v, (int, float)):
                return float(v)
        except Exception:
            pass
    exp = root / "EXPERIENCE.md"
    if not exp.is_file():
        return None
    text = _read_text(exp)
    m = re.search(r"^## 基线锚点.*?\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not m:
        return None
    mm = re.search(
        r"reference_anchor_value\s*[:：=]\s*([\-+]?\d+(?:\.\d+)?(?:[eE][\-+]?\d+)?)",
        m.group(1),
    )
    if not mm:
        return None
    try:
        return float(mm.group(1))
    except ValueError:
        return None


def _tsv_baseline_tag_counts(root: Path) -> tuple[bool, int, int, int]:
    """返回 (有 baseline_tag 列, plain 行数, reference 行数, none/其它行数)。"""
    tsv = root / "_runs" / "results.tsv"
    if not tsv.is_file():
        return False, 0, 0, 0
    lines = _read_text(tsv).splitlines()
    if len(lines) < 1:
        return False, 0, 0, 0
    headers = [h.strip() for h in lines[0].split("\t")]
    if "baseline_tag" not in headers:
        return False, 0, 0, 0
    i = headers.index("baseline_tag")
    plain_n = ref_n = other_n = 0
    for row in lines[1:]:
        if not row.strip():
            continue
        cells = row.split("\t")
        tag = cells[i].strip().lower() if i < len(cells) else ""
        if tag == "plain":
            plain_n += 1
        elif tag == "reference":
            ref_n += 1
        else:
            other_n += 1
    return True, plain_n, ref_n, other_n


def has_plain_baseline_tag(
    repo_root: Path | str, scenario_id: str | None = None
) -> bool:
    return _has_baseline_tag(repo_root, "plain", scenario_id=scenario_id)


def has_reference_baseline_tag(
    repo_root: Path | str, scenario_id: str | None = None
) -> bool:
    return _has_baseline_tag(repo_root, "reference", scenario_id=scenario_id)


def _has_baseline_tag(
    repo_root: Path | str,
    want: str,
    scenario_id: str | None = None,
) -> bool:
    root = Path(repo_root).resolve()
    tsv = root / "_runs" / "results.tsv"
    if not tsv.is_file():
        return False
    try:
        lines = _read_text(tsv).splitlines()
    except OSError:
        return False
    if len(lines) < 2:
        return False
    headers = [h.strip() for h in lines[0].split("\t")]
    if "baseline_tag" not in headers:
        return False
    ti = headers.index("baseline_tag")
    si = headers.index("scenario_id") if "scenario_id" in headers else None
    want_l = want.strip().lower()
    for row in lines[1:]:
        if not row.strip():
            continue
        cells = row.split("\t")
        if ti >= len(cells):
            continue
        if cells[ti].strip().lower() != want_l:
            continue
        if scenario_id is not None and si is not None:
            if si >= len(cells) or cells[si].strip() != scenario_id:
                continue
        return True
    return False


def _load_intent(root: Path) -> dict[str, Any] | None:
    p = root / "saved" / "baseline_start_intent.json"
    if not p.is_file():
        return None
    try:
        d = json.loads(_read_text(p))
        return d if isinstance(d, dict) else None
    except Exception:
        return None


def assess_baseline_anchors(repo_root: Path | str) -> BaselineAnchorsStatus:
    """体检当前仓 plain / reference 尺子是否已立；缺则给推荐句。"""
    root = Path(repo_root).resolve()
    plain_v = _plain_anchor_value(root)
    ref_v = _reference_anchor_value(root)
    has_col, plain_n, ref_n, other_n = _tsv_baseline_tag_counts(root)
    intent = _load_intent(root)
    intent_sr = None
    if intent:
        intent_sr = str(intent.get("start_runs") or "") or None

    has_plain = plain_v is not None or plain_n > 0
    has_ref_num = ref_v is not None
    has_ref_run = ref_n > 0
    missing: list[str] = []
    recs: list[str] = []

    if not has_plain:
        missing.append("plain")
        recs.append(
            "还没立朴素下界：请用 /auto-nn-plain "
            "（在契约内容易落地的最傻方法上跑一轮并贴 plain）。"
        )
    if not (has_ref_num or has_ref_run):
        missing.append("reference")
        try:
            from lib.baseline_stamp import (
                REFERENCE_AUTO_AFTER_ROUNDS,
                completed_experiment_rounds,
            )

            n_rounds = completed_experiment_rounds(root)
            auto_after = int(REFERENCE_AUTO_AFTER_ROUNDS)
        except Exception:
            n_rounds = 0
            auto_after = 10
        if n_rounds >= auto_after:
            recs.append(
                f"已满 {REFERENCE_AUTO_AFTER_ROUNDS} 轮仍无公开对照："
                "本轮必做 /auto-nn-reference（自动多轮则跟注入段走，可中点代用自动贴）。"
            )
        else:
            recs.append(
                "还没立公开对照（研究题可以没有）：需要时用 /auto-nn-reference。"
            )
        try:
            from lib.source_calibration import (
                resolve_source_repo,
                source_cal_skip_why,
            )

            if resolve_source_repo(root) is not None and not source_cal_skip_why(root):
                check_p = root / "saved" / "source_cal_check.json"
                passed = False
                if check_p.is_file():
                    try:
                        chk = json.loads(_read_text(check_p))
                        passed = isinstance(chk, dict) and chk.get("verdict") == "pass"
                    except Exception:
                        passed = False
                if not passed:
                    recs.append(
                        "找得到原仓库：先本机跑原仓入口写出校准分，再立公开对照；对不上禁止贴尺。"
                    )
        except Exception:
            pass
    if plain_n > 1:
        recs.append("朴素下界贴了不止一行：请用 /auto-nn-plain 确认留哪一把。")
    if ref_n > 1:
        recs.append("公开对照贴了不止一行：请用 /auto-nn-reference 确认留哪一把。")
    if has_col is False and (root / "_runs" / "results.tsv").is_file():
        recs.append(
            "台账无 `baseline_tag` 列：无法区分尺子轮与普通轮；"
            "建议 `nn-config.yaml` 的 `ledger.watchlist` 含 baseline_tag 后 "
            "`python3 scripts/regen_results_tsv.py --repo-root .`（台账同步，非 /auto-nn-modify）。"
        )
    if intent_sr and "plain" in intent_sr.lower() and not has_plain:
        recs.append(
            f"init 意图 start_runs={intent_sr!r} 要求先建朴素下界，但当前仍无锚——"
            "请用 /auto-nn-plain。"
        )
    if intent_sr and "reference" in intent_sr.lower() and not (has_ref_num or has_ref_run):
        recs.append(
            f"init 意图 start_runs={intent_sr!r} 要求公开对照，但当前仍无对照——"
            "请用 /auto-nn-reference。"
        )
    if not missing and not recs:
        recs.append("plain / reference 尺子已立（或已有对照信号）；后续 fancy 请对照靶子段归因。")

    return BaselineAnchorsStatus(
        has_plain=has_plain,
        has_reference_number=has_ref_num,
        has_reference_run=has_ref_run,
        plain_value=plain_v,
        reference_value=ref_v,
        plain_tag_rows=plain_n,
        reference_tag_rows=ref_n,
        none_tag_rows=other_n,
        baseline_tag_col=has_col,
        intent_start_runs=intent_sr,
        recommendations=recs,
        missing=missing,
    )


def format_baseline_anchors_markdown(status: BaselineAnchorsStatus) -> str:
    """analyse 报告用的 markdown 小节（人话为主，可含字段名一次）。"""
    def _f(v: float | None) -> str:
        return f"{v:.4f}" if v is not None else "未标定"

    lines = [
        "## 基线尺子 (baseline anchors)",
        f"- plain（下界）: {'有' if status.has_plain else '**缺**'} "
        f"（锚值={_f(status.plain_value)}；台账 plain 行={status.plain_tag_rows}）",
        f"- reference（上界/对照）: {'有' if status.has_reference else '**缺**'} "
        f"（发表分={_f(status.reference_value)}；台账 reference 行={status.reference_tag_rows}）",
        f"- baseline_tag 列: {'有' if status.baseline_tag_col else '无'}"
        + (
            f"；none/其它行={status.none_tag_rows}"
            if status.baseline_tag_col
            else ""
        ),
    ]
    if status.intent_start_runs:
        lines.append(f"- init 起步意图: start_runs={status.intent_start_runs}")
    if status.missing:
        lines.append("- 缺口: " + "、".join(status.missing))
    lines.append("- 建议:")
    for r in status.recommendations:
        lines.append(f"  - {r}")
    return "\n".join(lines) + "\n"
