"""训末探索空间打格：相对同场景上一有效训练行（非 keeper TAM）。

规则（与探索空间 stamp 设计 §4 对齐）：

- ``smoke`` 或 ``elapsed_sec < 1`` → 未开训，``cell=""``。
- 有效训练：``elapsed_sec >= 1`` 且非 smoke；主指标缺失或非有限仍算有效。
- 上一有效行：同 ``scenario_id``、TSV 已有行、``is_trained_row``、``exp_dir`` 不是当前。
- 档：``config_tiers_from_delta`` + ``evidence_tiers_from_paths(diff_code_snapshots)``；
  有 B/C/D 则丢掉顺带 A；``contract/`` 路径不加入格子（E 不进 cell）。
- 深：``compute_fingerprint_from_configs``；训末把 ``novel`` 压成 ``different``。
- 配置与快照均无 Δ → 继承上一格；无上一行 → ``A-routine``（``first_in_scenario``）。
- ``primary_tier`` 若为 E 或空 → 用证据档最深的 A–D，否则 ``A``。

正式训完若算出空 cell，由调用方 raise；本模块对 untrained 返回空 cell。
禁止 git 考古。
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lib.innovation_fingerprint import (
    compute_fingerprint_from_configs,
    load_innovation_catalog,
)
from lib.reflect_evidence import diff_code_snapshots
from lib.tier_attestation import (
    classify_path_tiers,
    config_tiers_from_delta,
    evidence_tiers_from_paths,
)
from sync_exploration_ledger import cell_from_fingerprint

UNTRAINED_ELAPSED_SEC = 1.0

_TIER_ORDER = {"A": 1, "B": 2, "C": 3, "D": 4}
_ABCD = frozenset("ABCD")


@dataclass
class StampResult:
    cell: str
    untrained: bool
    reasons: list[str]


def is_untrained(*, elapsed_sec: float, smoke: bool) -> bool:
    return bool(smoke) or float(elapsed_sec) < UNTRAINED_ELAPSED_SEC


def is_trained_row(
    row: dict[str, str],
    *,
    metric_key: str,
    smoke: bool = False,
) -> bool:
    """TSV 行是否可作为「上一有效训练」对照。

    ``metric_key`` 保留给调用方对齐主指标列；缺失/非有限主指标仍算有效。
    ``untrained`` 列为 1/true/yes 时不当对照（smoke 墙钟常 ≥1s）。
    旧表无该列时列空，仍只靠 elapsed / smoke 列（与历史行为一致）。
    """
    del metric_key  # 主指标不参与有效性门禁（评测打 0 / 缺失仍保留）
    if smoke:
        return False
    raw_untrained = str(row.get("untrained") or "").strip().lower()
    if raw_untrained in {"1", "true", "yes", "y"}:
        return False
    raw_smoke = str(row.get("smoke") or row.get("NN_SMOKE") or "").strip().lower()
    if raw_smoke in {"1", "true", "yes", "y"}:
        return False
    try:
        elapsed = float(row.get("elapsed_sec") or 0)
    except (TypeError, ValueError):
        elapsed = 0.0
    if not math.isfinite(elapsed) or elapsed < UNTRAINED_ELAPSED_SEC:
        return False
    return True


def _resolve_exp_dir(repo_root: Path, raw: str) -> Path | None:
    text = (raw or "").strip()
    if not text:
        return None
    p = Path(text)
    if not p.is_absolute():
        p = (repo_root / p).resolve()
    else:
        p = p.resolve()
    return p


def _read_tsv_rows(repo_root: Path) -> list[dict[str, str]]:
    p = repo_root / "_runs" / "results.tsv"
    if not p.is_file():
        return []
    lines = [ln for ln in p.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    if len(lines) < 2:
        return []
    hdr = lines[0].split("\t")
    rows: list[dict[str, str]] = []
    for ln in lines[1:]:
        cells = ln.split("\t")
        if len(cells) < len(hdr):
            cells.extend([""] * (len(hdr) - len(cells)))
        rows.append(dict(zip(hdr, cells[: len(hdr)])))
    return rows


def prev_trained_exp_dir(
    repo_root: Path,
    *,
    scenario_id: str,
    before_exp_dir: Path,
    metric_key: str,
) -> Path | None:
    """同场景 TSV 中、当前 ``exp_dir`` 之前最近一条有效训练行的目录。"""
    before = Path(before_exp_dir).resolve()
    last: Path | None = None
    for row in _read_tsv_rows(repo_root):
        if (row.get("scenario_id") or "").strip() != str(scenario_id).strip():
            continue
        if not is_trained_row(row, metric_key=metric_key):
            continue
        ed = _resolve_exp_dir(repo_root, row.get("exp_dir") or "")
        if ed is None or ed == before:
            continue
        last = ed
    return last


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _prev_cell(
    repo_root: Path,
    *,
    scenario_id: str,
    prev_dir: Path,
) -> str:
    target = Path(prev_dir).resolve()
    for row in _read_tsv_rows(repo_root):
        if (row.get("scenario_id") or "").strip() != str(scenario_id).strip():
            continue
        ed = _resolve_exp_dir(repo_root, row.get("exp_dir") or "")
        if ed is None or ed != target:
            continue
        return str(row.get("exploration_space") or "").strip()
    return ""


def _paths_for_cell(changed_files: list[str]) -> list[str]:
    """丢掉 contract/（E）路径，不进成绩表格子。"""
    out: list[str] = []
    for path in changed_files:
        tiers = classify_path_tiers(path)
        if "E" in tiers:
            continue
        out.append(path)
    return out


def _deepest_abcd(tiers: list[str]) -> str:
    pool = [t for t in tiers if t in _ABCD]
    if not pool:
        return "A"
    return max(pool, key=lambda t: _TIER_ORDER[t])


def compute_stamp(
    repo_root: Path,
    exp_dir: Path,
    *,
    elapsed_sec: float,
    smoke: bool,
    scenario_id: str,
    metric_key: str,
    metrics: dict,
) -> StampResult:
    del metrics  # 打格不依赖本轮分；调用方仍传入以对齐 finalize 签名
    if is_untrained(elapsed_sec=elapsed_sec, smoke=smoke):
        return StampResult(cell="", untrained=True, reasons=["untrained"])

    root = Path(repo_root)
    cur = Path(exp_dir).resolve()
    reasons: list[str] = []

    prev = prev_trained_exp_dir(
        root,
        scenario_id=scenario_id,
        before_exp_dir=cur,
        metric_key=metric_key,
    )
    if prev is None:
        reasons.append("first_in_scenario")
        return StampResult(cell="A-routine", untrained=False, reasons=reasons)

    keeper_cfg = _load_json(prev / "config.json")
    run_cfg = _load_json(cur / "config.json")
    if not keeper_cfg:
        reasons.append("no_prev_config")
    if not run_cfg:
        reasons.append("no_config")

    snap = diff_code_snapshots(prev, cur)
    changed_files = list(snap.get("changed_files") or [])
    summaries = list(snap.get("summaries") or [])

    config_tiers, changed_keys = config_tiers_from_delta(keeper_cfg, run_cfg)
    configs_identical = keeper_cfg == run_cfg
    paths_for_cell = _paths_for_cell(changed_files)

    if configs_identical and not paths_for_cell:
        inherited = _prev_cell(root, scenario_id=scenario_id, prev_dir=prev)
        if inherited:
            reasons.append("inherit_prev")
            return StampResult(cell=inherited, untrained=False, reasons=reasons)
        reasons.append("inherit_prev_missing_cell")
        return StampResult(cell="A-routine", untrained=False, reasons=reasons)

    config_tiers_ad = {t for t in config_tiers if t in _ABCD}
    ev_tiers, ev_primary = evidence_tiers_from_paths(
        paths_for_cell,
        config_tiers=config_tiers_ad,
        diff_summaries=summaries,
    )
    primary = str(ev_primary or "").strip().upper()[:1]
    if primary not in _ABCD:
        primary = _deepest_abcd(list(ev_tiers))
        reasons.append("primary_fallback_abcd")

    catalog = load_innovation_catalog(root)
    if not catalog:
        catalog = load_innovation_catalog(None)
    if not catalog:
        reasons.append("no_catalog")

    fp = compute_fingerprint_from_configs(
        keeper_cfg,
        run_cfg,
        catalog or {},
        primary_tier_fallback=primary,
    )
    reasons.extend(list(fp.reasons or []))

    depth = str(fp.depth or "")
    effective = str(fp.effective_depth or depth)
    if effective == "novel":
        effective = "different"
        reasons.append("clamp_novel_to_different")
    if depth == "novel":
        depth = "different"

    fp_payload: dict[str, Any] = {
        "primary_tier": primary,
        "depth": depth,
        "effective_depth": effective,
    }
    cell = cell_from_fingerprint(fp_payload)
    if not cell:
        # 无 Δ 已在上方 inherit；此处多为 depth 空 / 拒 E —— 正式训完不得空格
        if not changed_keys and not paths_for_cell:
            inherited = _prev_cell(root, scenario_id=scenario_id, prev_dir=prev)
            if inherited:
                reasons.append("inherit_prev_empty_cell")
                return StampResult(cell=inherited, untrained=False, reasons=reasons)
        reasons.append("fallback_a_routine")
        cell = "A-routine"

    return StampResult(cell=cell, untrained=False, reasons=reasons)
