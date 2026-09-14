"""审查判定：指定两端指纹 + 强制 P3 天花板 + 消融策略草稿。

不发 HTTP；paper_verdict 由调用方注入（默认 inconclusive）。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lib.audit_core import AuditTarget, resolve_fingerprint_baseline
from lib.innovation_fingerprint import apply_novel_ceiling, build_innovation_fingerprint
from lib.reflect_evidence import ReflectEvidenceBundle

_NO_RULER_SKIP = "无尺子，深度非正式"


@dataclass
class AttestResult:
    fp_depth: str
    attested_depth: str
    search_claimed_depth: str
    paper_verdict: str
    baseline_kind: str  # reference|plain|none
    primary_keys_changed: dict
    ablation_keys: list[str]
    ablation_planned: bool
    ablation_skip_reason: str  # 空=将跑；否则如 not_pluggable / not_novel / 无尺子…
    fingerprint: dict


def _resolve_target_dir(repo_root: Path, target: AuditTarget) -> Path:
    root = Path(repo_root).resolve()
    p = Path(target.audited_exp_dir)
    if not p.is_absolute():
        p = root / p
    return p.resolve()


def _skip_reason(
    *,
    baseline_kind: str,
    attested_depth: str,
    ablation_keys: list[str],
    ablation_planned: bool,
) -> str:
    if ablation_planned:
        return ""
    if baseline_kind == "none":
        return _NO_RULER_SKIP
    if not ablation_keys:
        return "not_pluggable"
    if attested_depth != "novel":
        return "not_novel"
    return "no_baseline"


def attest_candidate(
    repo_root: Path,
    target: AuditTarget,
    *,
    search_claimed_depth: str = "",
    paper_verdict: str | None = None,
) -> AttestResult:
    """paper_verdict 默认 'inconclusive'。测试可注入 'supported'。

    本函数不发 HTTP；CLI pipeline 在 novel 需要背书时再调外部执行器，把 verdict 传入。
    """
    root = Path(repo_root).resolve()
    verdict = "inconclusive" if paper_verdict is None else str(paper_verdict)
    claimed = (search_claimed_depth or "").strip()

    baseline_path, baseline_kind = resolve_fingerprint_baseline(
        root, target.scenario_id, exclude_exp_dir=target.audited_exp_dir,
    )
    target_dir = _resolve_target_dir(root, target)
    empty = ReflectEvidenceBundle()

    if baseline_path is not None:
        fp = build_innovation_fingerprint(
            root,
            reb_bundle=empty,
            baseline_dir=baseline_path,
            candidate_dirs=[target_dir],
        )
        fp_depth = str(fp.depth or "")
        attested_depth = apply_novel_ceiling(fp_depth, verdict, "P3")
    else:
        # 无尺子：candidate vs 空 cfg（无 config.json → {}）草稿可点名键；深度非正式。
        empty_base = root / "_runs" / ".audit_empty_baseline"
        fp = build_innovation_fingerprint(
            root,
            reb_bundle=empty,
            baseline_dir=empty_base,
            candidate_dirs=[target_dir],
        )
        fp_depth = str(fp.depth or "")
        attested_depth = "inconclusive"

    primary: dict[str, Any] = dict(fp.primary_keys_changed or {})
    ablation_keys = list(primary.keys())
    ablation_planned = attested_depth == "novel" and bool(ablation_keys)
    skip = _skip_reason(
        baseline_kind=baseline_kind,
        attested_depth=attested_depth,
        ablation_keys=ablation_keys,
        ablation_planned=ablation_planned,
    )

    return AttestResult(
        fp_depth=fp_depth,
        attested_depth=attested_depth,
        search_claimed_depth=claimed,
        paper_verdict=verdict,
        baseline_kind=baseline_kind,
        primary_keys_changed=primary,
        ablation_keys=ablation_keys,
        ablation_planned=ablation_planned,
        ablation_skip_reason=skip,
        fingerprint=fp.to_dict(),
    )
