"""align_probe — 可解释对齐建议（旁路 detect，不膨胀 DetectionResult）。

BUILD 默认 object_type=data（避免脚手架 @register_* 污染）。
profile：路径/依赖启发式；可单测。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from init_workflow import Workflow, detect


@dataclass
class AlignSuggestion:
    workflow: str
    object_type_suggested: str
    profile_suggested: str
    framework_name_suggested: str | None
    pattern: str | None
    evidence: list[str] = field(default_factory=list)
    migrate_allowed: bool = True
    detect_object_type: str = ""
    detect_framework_kind: str | None = None
    detect_workflow: str = ""


_RL_DEPS = ("gymnasium", "gym==", "gym>", "envpool", "cleanrl")
_PHYSICAL_DEPS = ("neuralop", "neuraloperator", "deepxde")
_PHYSICAL_PATH = ("neuralop", "neuraloperator", "pinn", "darcy")
_RL_PATH = ("cleanrl", "/rl/", "reinforcement")
_FW_NAMES = ("mammoth", "lightning", "avalanche", "timm", "transformers")


def _read_text(path: Path, limit: int = 200_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except OSError:
        return ""


def _scan_root_for_profile(scan: Path) -> tuple[str, list[str]]:
    evidence: list[str] = []
    joined = str(scan).lower()
    for tok in _RL_PATH:
        if tok in joined:
            evidence.append(f"path:{tok}")
            return "rl", evidence
    for tok in _PHYSICAL_PATH:
        if tok in joined:
            evidence.append(f"path:{tok}")
            return "physical", evidence

    pyproject = scan / "pyproject.toml"
    reqs = list(scan.glob("requirements*.txt"))[:5]
    blob = _read_text(pyproject) if pyproject.is_file() else ""
    for r in reqs:
        blob += "\n" + _read_text(r)
    low = blob.lower()
    for dep in _RL_DEPS:
        if dep in low:
            evidence.append(f"dep:{dep}")
            return "rl", evidence
    for dep in _PHYSICAL_DEPS:
        if dep in low:
            evidence.append(f"dep:{dep}")
            return "physical", evidence

    # single-file RL algos
    for p in scan.rglob("ppo_*.py"):
        if ".git" in p.parts or "site-packages" in p.parts:
            continue
        evidence.append(f"file:{p.name}")
        return "rl", evidence

    evidence.append("default:supervised")
    return "supervised", evidence


def _suggest_framework_name(scan: Path, kind: str | None) -> str | None:
    if kind and kind != "unknown":
        return kind
    joined = str(scan).lower()
    for name in _FW_NAMES:
        if name in joined:
            return "mammoth" if name == "mammoth" else name.replace("transformers", "hf_trainer")
    pyproject = scan / "pyproject.toml"
    if pyproject.is_file():
        text = _read_text(pyproject).lower()
        m = re.search(r'name\s*=\s*["\']([^"\']+)["\']', text)
        if m:
            n = m.group(1).lower()
            for name in _FW_NAMES:
                if name in n:
                    return "mammoth" if name == "mammoth" else name
    return None


def probe(
    repo_root: Path | str,
    source_root: Path | str | None = None,
    force_workflow: str | None = None,
) -> AlignSuggestion:
    """Produce AlignSuggestion from detect() + heuristics."""
    repo_root = Path(repo_root)
    src = Path(source_root) if source_root else None
    result = detect(repo_root, src, force_workflow=force_workflow)
    evidence: list[str] = []

    migrate_allowed = True
    if result.workflow == Workflow.MIGRATE and src is not None:
        if result.object_type == "data":
            migrate_allowed = False
            evidence.append("source_has_no_training_py:reject_migrate")

    if result.workflow == Workflow.BUILD:
        ot = "data"
        evidence.append("build_default_object_type:data")
    else:
        ot = result.object_type

    scan = src if (result.workflow == Workflow.MIGRATE and src) else repo_root
    # For BUILD after scaffold, profile still supervised unless scan has signals
    # (empty/new target → supervised). Prefer source when migrate.
    profile, pe = _scan_root_for_profile(scan if scan.exists() else repo_root)
    evidence.extend(pe)

    fname = None
    if ot == "framework" or result.object_type == "framework":
        fname = _suggest_framework_name(scan if scan.exists() else repo_root, result.framework_kind)
        if fname:
            evidence.append(f"framework_name:{fname}")

    return AlignSuggestion(
        workflow=result.workflow.value,
        object_type_suggested=ot,
        profile_suggested=profile,
        framework_name_suggested=fname,
        pattern=result.pattern,
        evidence=evidence,
        migrate_allowed=migrate_allowed,
        detect_object_type=result.object_type,
        detect_framework_kind=result.framework_kind,
        detect_workflow=result.workflow.value,
    )


def suggestion_to_dict(s: AlignSuggestion) -> dict:
    return {
        "workflow": s.workflow,
        "object_type_suggested": s.object_type_suggested,
        "profile_suggested": s.profile_suggested,
        "framework_name_suggested": s.framework_name_suggested,
        "pattern": s.pattern,
        "evidence": list(s.evidence),
        "migrate_allowed": s.migrate_allowed,
        "detect_object_type": s.detect_object_type,
        "detect_framework_kind": s.detect_framework_kind,
        "detect_workflow": s.detect_workflow,
    }
