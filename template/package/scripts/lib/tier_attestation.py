"""Tier Attestation Matrix（TAM）：Phase 0.6 确定性 Tier 举证（false_claim + shallow/exhausted）。"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.reflect_evidence import ReflectEvidenceBundle, diff_code_snapshots
from lib.run_ledger_summary import (
    load_keepers,
    metric_direction,
    metric_key,
    tsv_rows,
)

_TIER_ORDER = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5}
_CLAIMED_RE = re.compile(r"Tier\s*([A-Ea-e])\b")
_LOG_BAD_RE = re.compile(r"(oom|out of memory|traceback|exception|failed)", re.I)
_AMBIENT_RE = re.compile(r"(^|/)train\.py$|/__init__\.py$")
_SUBSTANTIVE_TIERS = frozenset({"B", "C", "D", "E"})


@dataclass
class TierAttestationConfig:
    enabled: bool = True
    window: int = 12
    exhaust_min_attempts: int = 2


@dataclass
class TierAttestationResult:
    schema_version: int = 1
    ts: str = ""
    rows: list[dict[str, Any]] = field(default_factory=list)
    rollup: dict[str, dict[str, Any]] = field(default_factory=dict)
    tam_line: str = ""
    not_attested_tiers: list[str] = field(default_factory=list)
    false_claims: list[dict[str, str]] = field(default_factory=list)
    markdown: str = ""


def load_tier_attestation_config(repo_root: Path) -> TierAttestationConfig:
    cfg = TierAttestationConfig()
    p = repo_root / "nn-config.yaml"
    if not p.is_file():
        return cfg
    try:
        import yaml

        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        tam = raw.get("tier_attestation") if isinstance(raw.get("tier_attestation"), dict) else {}
        cfg.enabled = bool(tam.get("enabled", cfg.enabled))
        cfg.window = int(tam.get("window", cfg.window))
        cfg.exhaust_min_attempts = int(
            tam.get("exhaust_min_attempts", cfg.exhaust_min_attempts)
        )
    except Exception:
        pass
    return cfg


def parse_claimed_tiers(text: str) -> list[str]:
    if not text:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for m in _CLAIMED_RE.finditer(text):
        letter = m.group(1).upper()
        if letter in _TIER_ORDER and letter not in seen:
            seen.add(letter)
            out.append(letter)
    return out


_CONFIG_TIER_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^(MODEL_ARCH|BACKBONE|ARCH|ENCODER)$", re.I), "B"),
    (re.compile(r"^(LOSS|OBJECTIVE|REWARD|LABEL_SMOOTHING)$", re.I), "C"),
    (re.compile(r"^FOCAL_", re.I), "C"),
    (re.compile(r"^(AUGMENT|AUGMENTATION|MIXUP|MIX_MODE|CUTMIX|RANDAUG|DATA_SAMPLER|SAMPLER_)", re.I), "D"),
    (re.compile(r"^(LR|LEARNING_RATE|EPOCHS|NUM_EPOCHS|BATCH_SIZE|WD|WEIGHT_DECAY|SCHEDULER|WARMUP|EMA)", re.I), "A"),
)


def classify_config_key(key: str) -> str | None:
    for pat, tier in _CONFIG_TIER_RULES:
        if pat.search(key.strip()):
            return tier
    return None


def config_tiers_from_delta(
    keeper_cfg: dict[str, Any],
    run_cfg: dict[str, Any],
) -> tuple[set[str], list[str]]:
    """keeper vs run 的 config.json 键级 diff → (tiers, changed_keys)。"""
    tiers: set[str] = set()
    changed_keys: list[str] = []
    all_keys = sorted(set(keeper_cfg) | set(run_cfg))
    for key in all_keys:
        if keeper_cfg.get(key) == run_cfg.get(key):
            continue
        changed_keys.append(key)
        tier = classify_config_key(key)
        if tier:
            tiers.add(tier)
    return tiers, changed_keys


def _config_evidence_vs_keeper(
    keeper_dir: Path | None,
    exp_dir: Path,
) -> tuple[set[str], list[str]]:
    if keeper_dir is None or not keeper_dir.is_dir():
        return set(), []
    keeper_cfg = _load_json(keeper_dir / "config.json")
    run_cfg = _load_json(exp_dir / "config.json")
    if not keeper_cfg or not run_cfg:
        return set(), []
    return config_tiers_from_delta(keeper_cfg, run_cfg)


def _norm_path(path: str) -> str:
    return path.replace("\\", "/").lower()


def _is_ambient_path(path: str) -> bool:
    return bool(_AMBIENT_RE.search(_norm_path(path)))


def classify_path_tiers(path: str) -> set[str]:
    """单文件路径 → Tier 集合（不含 ambient 降权逻辑）。"""
    p = _norm_path(path)
    tiers: set[str] = set()
    if p.startswith("contract/") or p == "contract":
        return {"E"}
    if re.search(r"workspace/nn/objectives/", p):
        tiers.add("C")
    elif re.search(r"workspace/(nn/|models/)", p):
        tiers.add("B")
    if re.search(r"workspace/objectives/", p):
        tiers.add("C")
    if re.search(r"workspace/.*(data_process|data|colloc|sampler|curriculum)", p):
        tiers.add("D")
    if re.search(r"workspace/.*(loss|reward|objective)", p):
        tiers.add("C")
    if re.search(r"workspace/.*(model|pinn|backbone|arch)", p):
        tiers.add("B")
    if p == "train.py" or p.endswith("/train.py"):
        tiers.add("A")
    return tiers


_TRAIN_TIER_C_RE = re.compile(
    r"(register_objective|register_loss|\bloss\s*[=:]|focal|polyloss|bitempered|"
    r"label_smoothing|cross_entropy|nll_loss|softmax_cross)",
    re.I,
)
_TRAIN_TIER_A_RE = re.compile(
    r"(\blr\s*[=:]|learning_rate|\bepochs?\b|scheduler|warmup|\bema\b|weight_decay)",
    re.I,
)
_INIT_TIER_C_RE = re.compile(
    r"(register_objective|register_loss|bitempered|polyloss|focal_loss|\bloss\s*[=:])",
    re.I,
)
_INIT_TIER_B_RE = re.compile(r"(register_learner|@register_learner)", re.I)


def _diff_text_for_path(path: str, summaries: list[str]) -> str:
    """从 REB snapshot summary 块提取单文件 diff 文本。"""
    np = _norm_path(path)
    base = np.rsplit("/", 1)[-1]
    chunks: list[str] = []
    for s in summaries:
        sl = s.lower()
        head = s.split("\n", 1)[0].lower()
        if head.startswith(f"~ {np}:") or head.startswith(f"~ {base}:"):
            chunks.append(s)
        elif f"keeper/{np}" in sl or f"target/{np}" in sl:
            chunks.append(s)
        elif np in sl or (base in ("train.py", "__init__.py") and base in head):
            chunks.append(s)
    return "\n".join(chunks)


def tiers_from_train_diff(text: str) -> set[str]:
    if not text:
        return set()
    low = text.lower()
    tiers: set[str] = set()
    if _TRAIN_TIER_C_RE.search(low):
        tiers.add("C")
    elif _TRAIN_TIER_A_RE.search(low):
        tiers.add("A")
    return tiers


def tiers_from_init_diff(text: str) -> set[str]:
    if not text:
        return set()
    low = text.lower()
    tiers: set[str] = set()
    if _INIT_TIER_C_RE.search(low):
        tiers.add("C")
    if _INIT_TIER_B_RE.search(low):
        tiers.add("B")
    return tiers


def tiers_from_diff_summaries(
    summaries: list[str],
    *,
    changed_paths: list[str] | None = None,
) -> set[str]:
    """ambient 文件（train.py / __init__.py）diff 文本 → Tier 提示。"""
    if not summaries:
        return set()
    paths = changed_paths or []
    tiers: set[str] = set()
    for path in paths:
        np = _norm_path(path)
        text = _diff_text_for_path(path, summaries)
        if np == "train.py" or np.endswith("/train.py"):
            tiers.update(tiers_from_train_diff(text))
        elif np.endswith("__init__.py"):
            tiers.update(tiers_from_init_diff(text))
    if not paths:
        text = "\n".join(summaries).lower()
        tiers.update(tiers_from_train_diff(text))
        tiers.update(tiers_from_init_diff(text))
    return tiers


def resolve_evidence_primary(
    evidence_tiers: list[str],
    claimed: list[str] | None = None,
) -> str | None:
    if not evidence_tiers:
        return None
    claimed_deep = _deepest_claimed(claimed or [])
    if claimed_deep and claimed_deep in evidence_tiers:
        return claimed_deep
    substantive = [t for t in evidence_tiers if t in _SUBSTANTIVE_TIERS]
    pool = substantive or list(evidence_tiers)
    return max(pool, key=lambda t: _TIER_ORDER[t])


def evidence_tiers_from_paths(
    paths: list[str],
    *,
    config_tiers: set[str] | None = None,
    diff_summaries: list[str] | None = None,
    claimed: list[str] | None = None,
) -> tuple[list[str], str | None]:
    tiers: set[str] = set(config_tiers or ())
    if not paths and not tiers:
        return [], None
    has_init_change = any(_norm_path(p).endswith("__init__.py") for p in paths)
    has_train_change = any(_norm_path(p) == "train.py" or _norm_path(p).endswith("/train.py") for p in paths)
    for path in paths:
        tiers.update(classify_path_tiers(path))
    if (has_init_change or has_train_change) and diff_summaries:
        tiers.update(
            tiers_from_diff_summaries(diff_summaries, changed_paths=paths)
        )
    has_substantive = bool(tiers & _SUBSTANTIVE_TIERS)
    if has_substantive and "A" in tiers:
        tiers.discard("A")
    if not tiers and paths:
        if all(_is_ambient_path(p) for p in paths):
            if any(_norm_path(p) in ("train.py",) or _norm_path(p).endswith("/train.py") for p in paths):
                tiers.add("A")
        else:
            tiers.add("A")
    ordered = sorted(tiers, key=lambda t: _TIER_ORDER[t])
    primary = resolve_evidence_primary(ordered, claimed)
    return ordered, primary


def _deepest_claimed(claimed: list[str]) -> str | None:
    if not claimed:
        return None
    return max(claimed, key=lambda t: _TIER_ORDER.get(t, 0))


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file() or path.stat().st_size < 2:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _abs_exp(repo_root: Path, p: str | Path | None) -> Path | None:
    """v2.7.4: 状态文件里的 exp 路径(相对 repo_root 或绝对) → 绝对 Path。

    相对则 join repo_root(读侧运行时定位); 绝对原样; 空返回 None。
    """
    if p is None:
        return None
    ps = str(p).strip()
    if not ps:
        return None
    pp = Path(ps)
    return pp if pp.is_absolute() else (repo_root / pp)


def _keeper_metric(repo_root: Path, keeper_dir: Path, mk: str) -> float | None:
    keepers = load_keepers(repo_root)
    for entry in keepers.values():
        # v2.7.4: entry.keeper_exp_dir 存相对(新)/绝对(老); 两侧归一为绝对再比
        _ev = _abs_exp(repo_root, entry.get("keeper_exp_dir"))
        if _ev is not None and str(_ev) == str(keeper_dir):
            try:
                return float(entry.get("best_metric_value"))
            except (TypeError, ValueError):
                break
    res = _load_json(keeper_dir / "results.json")
    if res and isinstance(res.get("metrics"), dict):
        try:
            return float(res["metrics"].get(mk))
        except (TypeError, ValueError):
            pass
    return None


def _metric_improved(cur: float | None, best: float | None, direction: str) -> bool:
    if cur is None or best is None or cur != cur or best != best:
        return False
    if direction == "minimize":
        return cur < best - 1e-12
    return cur > best + 1e-12


def _process_block(exp_dir: Path, run_ev: dict[str, Any] | None) -> dict[str, Any]:
    run_ev = run_ev or {}
    arts = run_ev.get("artifacts") or {}
    exc = arts.get("train_exception.txt", False) or (exp_dir / "train_exception.txt").is_file()
    td = run_ev.get("train_done") or {}
    if not td:
        td_raw = _load_json(exp_dir / "train_done.json")
        if td_raw:
            td = {
                k: td_raw.get(k)
                for k in ("stop_reason", "training_loop_finished")
                if k in td_raw
            }
    finished = bool(td.get("training_loop_finished"))
    if not td and (exp_dir / "results.json").is_file():
        finished = True
    log_signals = run_ev.get("log_signals") or []
    bad_log = any(_LOG_BAD_RE.search(str(s)) for s in log_signals)
    minimal = not exc and finished and not bad_log
    return {
        "finished": finished,
        "stop_reason": td.get("stop_reason"),
        "log_signals": log_signals[:6],
        "minimal_train_ok": minimal,
    }


def _outcome_block(
    exp_dir: Path,
    *,
    mk: str,
    direction: str,
    keeper_metric: float | None,
    tsv_row: dict[str, str],
) -> dict[str, Any]:
    ks = _load_json(exp_dir / "keep_suggestion.json")
    keep_bool = bool(ks.get("keep_suggestion")) if ks else None
    decision = "KEEP" if keep_bool else ("DISCARD" if keep_bool is False else "")
    cur: float | None = None
    res = _load_json(exp_dir / "results.json")
    if res and isinstance(res.get("metrics"), dict):
        try:
            cur = float(res["metrics"].get(mk))
        except (TypeError, ValueError):
            pass
    if cur is None:
        try:
            cur = float(tsv_row.get(mk, "nan"))
        except ValueError:
            cur = None
    delta: float | None = None
    if cur is not None and keeper_metric is not None and cur == cur and keeper_metric == keeper_metric:
        delta = cur - keeper_metric
    improved = _metric_improved(cur, keeper_metric, direction)
    return {
        "keep_decision": decision,
        "primary_delta_vs_keeper": delta,
        "primary_improved": improved,
        "near_miss": bool(decision == "DISCARD" and not improved and ks),
    }


def _summaries_for_exp(bundle: ReflectEvidenceBundle, exp_dir: Path) -> list[str]:
    exp_s = str(exp_dir.resolve())
    out: list[str] = []
    for d in bundle.snapshot_diffs:
        if str(Path(d.get("target", "")).resolve()) == exp_s:
            out.extend(d.get("summaries") or [])
    return out


def _rollup_tiers_for_row(row: dict[str, Any]) -> list[str]:
    v = str(row.get("verdict") or "")
    if v == "false_claim":
        cd = _deepest_claimed(row.get("claimed_tiers") or [])
        return [cd] if cd else []
    tiers = list(row.get("evidence_tiers") or [])
    if tiers:
        return tiers
    ep = row.get("evidence_primary")
    return [ep] if ep else []


def _merge_changed_files(
    exp_dir: Path,
    keeper_dir: Path | None,
    bundle: ReflectEvidenceBundle,
    run_ev: dict[str, Any] | None,
) -> tuple[list[str], str]:
    changed: list[str] = []
    git_range = ""
    if run_ev:
        changed.extend(run_ev.get("git_changed_files") or [])
        git_range = str(run_ev.get("git_range") or "")
    exp_s = str(exp_dir.resolve())
    for d in bundle.snapshot_diffs:
        if str(Path(d.get("target", "")).resolve()) == exp_s:
            changed.extend(d.get("changed_files") or [])
    if keeper_dir and keeper_dir.is_dir() and not changed:
        diff = diff_code_snapshots(keeper_dir, exp_dir)
        changed.extend(diff.get("changed_files") or [])
    # 去重保序
    seen: set[str] = set()
    deduped: list[str] = []
    for c in changed:
        if c not in seen:
            seen.add(c)
            deduped.append(c)
    return deduped, git_range


def _base_verdict(
    *,
    evidence_primary: str | None,
    claimed: list[str],
    process: dict[str, Any],
) -> tuple[str, str]:
    if not process.get("minimal_train_ok"):
        return "broken_run", "train 未完成或 log/exception 异常"
    if not evidence_primary:
        return "unclaimed", "相对 keeper 无 train.py/workspace 变更"
    claimed_deep = _deepest_claimed(claimed)
    if claimed_deep and _TIER_ORDER.get(claimed_deep, 0) > _TIER_ORDER.get(evidence_primary, 0):
        return (
            "false_claim",
            f"claimed {claimed_deep} evidence {evidence_primary} ({','.join(claimed) or '-'})",
        )
    return "attested", f"evidence {evidence_primary}"


def _build_rollup(
    rows: list[dict[str, Any]],
    *,
    exhaust_min: int,
) -> dict[str, dict[str, Any]]:
    rollup: dict[str, dict[str, Any]] = {}
    for letter in "ABCDE":
        rollup[letter] = {
            "attested": 0,
            "false_claim": 0,
            "shallow": 0,
            "broken_run": 0,
            "unclaimed": 0,
            "status": "not_attested",
        }
    any_improve: dict[str, bool] = {k: False for k in _TIER_ORDER}
    false_tier: set[str] = set()

    for row in rows:
        if row.get("role") == "keeper":
            continue
        v = str(row.get("verdict") or "")
        if v == "false_claim":
            cd = _deepest_claimed(row.get("claimed_tiers") or [])
            if cd and cd in rollup:
                rollup[cd]["false_claim"] += 1
                false_tier.add(cd)
            continue
        for ep in _rollup_tiers_for_row(row):
            if ep in rollup and v in rollup[ep]:
                rollup[ep][v] += 1
                if v in ("attested", "shallow") and row.get("outcome", {}).get("primary_improved"):
                    any_improve[ep] = True

    for letter in "ABCDE":
        r = rollup[letter]
        att = int(r["attested"]) + int(r["shallow"])
        if r["false_claim"] > 0 or letter in false_tier:
            r["status"] = "false_claim"
        elif att >= exhaust_min and att > 0 and not any_improve.get(letter):
            r["status"] = "exhausted"
        elif r["shallow"] > 0:
            r["status"] = "shallow"
        elif r["attested"] > 0:
            r["status"] = "attested"
        elif r["broken_run"] > 0 or r["unclaimed"] > 0:
            r["status"] = "not_attested"
        else:
            r["status"] = "not_attested"
    return rollup


def _apply_shallow_pass(rows: list[dict[str, Any]], *, exhaust_min: int) -> None:
    counts: dict[str, int] = {k: 0 for k in _TIER_ORDER}
    improved: dict[str, bool] = {k: False for k in _TIER_ORDER}
    for row in rows:
        if row.get("role") == "keeper":
            continue
        base = row.get("_base_verdict")
        ep = row.get("evidence_primary")
        if base != "attested" or not ep:
            continue
        counts[ep] = counts.get(ep, 0) + 1
        if row.get("outcome", {}).get("primary_improved"):
            improved[ep] = True
        if counts[ep] >= exhaust_min and not improved.get(ep) and counts[ep] > exhaust_min:
            row["verdict"] = "shallow"
            row["verdict_detail"] = f"Tier {ep} 浅尝×{counts[ep]}，primary 未改善"


def _tam_summary_line(rollup: dict[str, dict[str, Any]]) -> str:
    parts: list[str] = []
    for letter in "ABCDE":
        r = rollup.get(letter) or {}
        st = r.get("status", "not_attested")
        bits = [st]
        if r.get("attested"):
            bits.append(f"att×{r['attested']}")
        if r.get("false_claim"):
            bits.append(f"false×{r['false_claim']}")
        if r.get("shallow"):
            bits.append(f"shallow×{r['shallow']}")
        parts.append(f"{letter}:{'/'.join(bits)}")
    attested = [f"Tier {k}" for k, v in rollup.items() if v.get("status") in ("attested", "exhausted", "shallow")]
    not_att = [f"Tier {k}" for k, v in rollup.items() if v.get("status") == "not_attested" and k in "BCDE"]
    false_list = [f"Tier {k}" for k, v in rollup.items() if v.get("status") == "false_claim" or v.get("false_claim")]
    line = "[TAM: " + " ".join(parts) + "]"
    if false_list:
        line += f" false_claim={','.join(false_list)}"
    if not_att:
        line += f" not_attested={','.join(not_att)}"
    return line


def build_tier_attestation(
    repo_root: Path,
    bundle: ReflectEvidenceBundle,
) -> TierAttestationResult:
    root = repo_root.resolve()
    cfg = load_tier_attestation_config(root)
    result = TierAttestationResult(ts=datetime.now(timezone.utc).isoformat())
    if not cfg.enabled:
        result.tam_line = "[TAM: disabled]"
        return result

    mk = metric_key(root)
    direction = metric_direction(root)
    data_rows = [r for r in tsv_rows(root) if r.get("experiment") != "preflight_check"]
    window_rows = data_rows[-cfg.window :] if cfg.window > 0 else data_rows

    keeper_dir_s = next(
        (e["exp_dir"] for e in bundle.ets if e.get("role") in ("keeper", "code_baseline")),
        "",
    )
    keeper_dir = Path(keeper_dir_s) if keeper_dir_s else None
    keeper_m = _keeper_metric(root, keeper_dir, mk) if keeper_dir else None

    run_by_exp = {str(Path(r["exp_dir"]).resolve()): r for r in bundle.runs if r.get("exp_dir")}
    ets_map = {e["exp_dir"]: e.get("role", "recent") for e in bundle.ets}

    seen_exp: set[str] = set()
    ordered_specs: list[tuple[dict[str, str], str]] = []
    for row in window_rows:
        exp_d = str(row.get("exp_dir") or "").strip()
        if not exp_d or exp_d in seen_exp:
            continue
        seen_exp.add(exp_d)
        ordered_specs.append((row, ets_map.get(exp_d, "window")))
    for ent in bundle.ets:
        exp_d = ent.get("exp_dir") or ""
        if exp_d and exp_d not in seen_exp:
            seen_exp.add(exp_d)
            ordered_specs.append(
                (
                    next((r for r in data_rows if r.get("exp_dir") == exp_d), {"experiment": ent.get("experiment", "?"), "exp_dir": exp_d, "description": ""}),
                    ent.get("role", "recent"),
                )
            )

    rows: list[dict[str, Any]] = []
    for tsv_row, role in ordered_specs:
        exp_d = str(tsv_row.get("exp_dir") or "").strip()
        if not exp_d:
            continue
        exp_dir = Path(exp_d)
        if role in ("keeper", "code_baseline"):
            continue
        run_ev = run_by_exp.get(str(exp_dir.resolve()))
        desc = str(tsv_row.get("description") or "")
        claimed = parse_claimed_tiers(desc)
        changed, git_range = _merge_changed_files(
            exp_dir,
            keeper_dir,
            bundle,
            run_ev,
        )
        summaries = _summaries_for_exp(bundle, exp_dir)
        cfg_tiers, cfg_keys = _config_evidence_vs_keeper(keeper_dir, exp_dir)
        ev_tiers, ev_primary = evidence_tiers_from_paths(
            changed,
            config_tiers=cfg_tiers,
            diff_summaries=summaries,
            claimed=claimed,
        )
        process = _process_block(exp_dir, run_ev)
        outcome = _outcome_block(
            exp_dir,
            mk=mk,
            direction=direction,
            keeper_metric=keeper_m,
            tsv_row=tsv_row,
        )
        base_v, base_detail = _base_verdict(
            evidence_primary=ev_primary,
            claimed=claimed,
            process=process,
        )
        row: dict[str, Any] = {
            "exp_dir": exp_d,
            "experiment": str(tsv_row.get("experiment") or "?"),
            "role": role,
            "claimed_tiers": claimed,
            "evidence_tiers": ev_tiers,
            "evidence_primary": ev_primary,
            "evidence_config_keys": cfg_keys,
            "changed_files": changed,
            "git_range": git_range,
            "process": process,
            "outcome": outcome,
            "_base_verdict": base_v,
            "verdict": base_v,
            "verdict_detail": base_detail,
        }
        rows.append(row)

    _apply_shallow_pass(rows, exhaust_min=cfg.exhaust_min_attempts)
    rollup = _build_rollup(rows, exhaust_min=cfg.exhaust_min_attempts)
    for row in rows:
        row.pop("_base_verdict", None)

    result.rows = rows
    result.rollup = rollup
    result.tam_line = _tam_summary_line(rollup)
    result.not_attested_tiers = [
        f"Tier {k}" for k in "ABCDE" if rollup.get(k, {}).get("status") == "not_attested"
    ]
    result.false_claims = [
        {
            "exp_dir": r["exp_dir"],
            "experiment": r["experiment"],
            "detail": r.get("verdict_detail", ""),
        }
        for r in rows
        if r.get("verdict") == "false_claim"
    ]
    result.markdown = format_tier_attestation_markdown(result)
    return result


def format_tier_attestation_markdown(result: TierAttestationResult, *, max_chars: int = 8000) -> str:
    lines = ["## Tier Attestation Matrix（TAM）", "", result.tam_line, ""]
    for letter in "ABCDE":
        r = result.rollup.get(letter) or {}
        lines.append(
            f"- **Tier {letter}**: status={r.get('status')} attested={r.get('attested')} "
            f"false_claim={r.get('false_claim')} shallow={r.get('shallow')}"
        )
    lines.append("")
    for row in result.rows[:15]:
        lines.append(
            f"### `{row.get('experiment')}` ({row.get('role')}) verdict={row.get('verdict')}"
        )
        lines.append(
            f"- claimed={row.get('claimed_tiers')} evidence={row.get('evidence_primary')} "
            f"files={row.get('changed_files')[:8]}"
        )
        cfg_keys = row.get("evidence_config_keys") or []
        if cfg_keys:
            lines.append(f"- configΔ: {cfg_keys[:12]}")
        lines.append(f"- {row.get('verdict_detail')}")
        out = row.get("outcome") or {}
        if out.get("keep_decision"):
            lines.append(f"- outcome: {out.get('keep_decision')} delta={out.get('primary_delta_vs_keeper')}")
        lines.append("")
    text = "\n".join(lines)
    if len(text) > max_chars:
        return text[: max_chars - 20] + "\n…(truncated)"
    return text


def format_tam_experience_block(result: TierAttestationResult) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"## Tier 举证摘要 {ts}", "", result.tam_line, ""]
    if result.false_claims:
        lines.append("**false_claim:**")
        for fc in result.false_claims[:8]:
            lines.append(f"- `{fc.get('experiment')}`: {fc.get('detail')}")
        lines.append("")
    if result.not_attested_tiers:
        lines.append(f"**未举证档:** {', '.join(result.not_attested_tiers)}")
    return "\n".join(lines)


_NARRATIVE_TRIED_RE = re.compile(r"已深|浅尝|已试|穷尽|饱和", re.I)


def parse_experience_tier_status_column(experience_md: str) -> dict[str, str]:
    """从 EXPERIENCE `## Tier 状态` 表解析每档「状态」列。"""
    from lib.experience_compress import parse_tier_status_table

    table = parse_tier_status_table(experience_md)
    if not table:
        return {}
    out: dict[str, str] = {}
    for letter in "ABCDE":
        m = re.search(rf"^\|\s*{letter}\s*\|([^|]+)\|", table, re.MULTILINE)
        if m:
            out[letter] = m.group(1).strip()
    return out


def experience_tam_conflicts(
    experience_md: str,
    rollup: dict[str, dict[str, Any]],
) -> list[str]:
    """EXPERIENCE Tier 表叙事 vs TAM rollup 不一致 → 人话警告列表。"""
    conflicts: list[str] = []
    for letter, narrative in parse_experience_tier_status_column(experience_md).items():
        tam_st = str((rollup.get(letter) or {}).get("status") or "not_attested")
        if _NARRATIVE_TRIED_RE.search(narrative) and tam_st == "not_attested":
            conflicts.append(
                f"Tier {letter} 经验文档写「{narrative}」，但举证矩阵仍为未举证（TAM={tam_st}）"
            )
    return conflicts


def format_experience_tam_warnings(conflicts: list[str]) -> str:
    if not conflicts:
        return ""
    lines = [
        "**TAM↔EXPERIENCE 冲突（举证矩阵为准，请更正 `## Tier 状态` 二维矩阵）:**",
    ]
    lines.extend(f"- {c}" for c in conflicts[:8])
    return "\n".join(lines)


def exhausted_tier_labels(rollup: dict[str, dict[str, Any]]) -> list[str]:
    return [
        f"Tier {letter}"
        for letter in "ABCDE"
        if (rollup.get(letter) or {}).get("status") == "exhausted"
    ]


def _merge_row_into_tam_json(repo_root: Path, row: dict[str, Any], *, window: int) -> None:
    """将单条 TAM 行 upsert 进 ``saved/tier_attestation.json``（保留最近 window 条）。"""
    saved = repo_root / "saved"
    saved.mkdir(exist_ok=True)
    path = saved / "tier_attestation.json"
    payload: dict[str, Any]
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            payload = raw if isinstance(raw, dict) else {}
        except Exception:
            payload = {}
    else:
        payload = {}

    rows = payload.get("rows")
    if not isinstance(rows, list):
        rows = []
    exp_s = str(row.get("exp_dir") or "")
    rows = [
        r for r in rows
        if isinstance(r, dict) and str(r.get("exp_dir") or "") != exp_s
    ]
    rows.append(row)
    if window > 0 and len(rows) > window:
        rows = rows[-window:]

    payload["schema_version"] = int(payload.get("schema_version") or 1)
    payload["ts"] = datetime.now(timezone.utc).isoformat()
    payload["rows"] = rows
    if not str(payload.get("tam_line") or "").strip():
        payload["tam_line"] = "[TAM: finalize_upsert]"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def upsert_finalize_tam_row(
    repo_root: Path,
    exp_dir: Path,
    *,
    description: str = "",
    experiment: str = "",
) -> bool:
    """训末 finalize 前写单条 TAM 行，供同轮 ``explore_attested_for_exp`` / ``should_keep`` 读取。

    仅探索期（``effective_objective=explore`` 且迁移未阻断）且 TAM 启用时执行；失败不抛异常。
    reflect 轮末仍会 ``build_tier_attestation`` 全量覆盖。
    """
    root = repo_root.resolve()
    cfg = load_tier_attestation_config(root)
    if not cfg.enabled:
        return False
    try:
        from lib.explore_objective import effective_objective  # noqa: WPS433

        obj = effective_objective(root)
        if obj.mode != "explore" or obj.migration_blocked:
            return False
    except ImportError:
        return False

    exp_dir = exp_dir.resolve()
    if not (exp_dir / "results.json").is_file():
        return False

    mk = metric_key(root)
    direction = metric_direction(root)

    keeper_dir: Path | None = None
    try:
        from lib.ledger_anchor import code_baseline_entry, focus_scenario_id  # noqa: WPS433

        baseline = code_baseline_entry(root, focus_scenario_id(root))
        if baseline and baseline.keeper_exp_dir:
            keeper_dir = _abs_exp(root, baseline.keeper_exp_dir)
    except ImportError:
        pass

    keeper_m = _keeper_metric(root, keeper_dir, mk) if keeper_dir else None

    changed: list[str] = []
    git_range = ""
    if keeper_dir and keeper_dir.is_dir():
        diff = diff_code_snapshots(keeper_dir, exp_dir)
        changed = list(diff.get("changed_files") or [])
        git_range = str(diff.get("git_range") or "")

    claimed = parse_claimed_tiers(description)
    cfg_tiers, cfg_keys = (
        _config_evidence_vs_keeper(keeper_dir, exp_dir) if keeper_dir else (set(), [])
    )
    ev_tiers, ev_primary = evidence_tiers_from_paths(
        changed,
        config_tiers=cfg_tiers,
        diff_summaries=[],
        claimed=claimed,
    )
    process = _process_block(exp_dir, None)
    tsv_row: dict[str, str] = {
        "description": description,
        "experiment": experiment or "?",
    }
    res = _load_json(exp_dir / "results.json")
    if res and isinstance(res.get("metrics"), dict):
        raw_m = res["metrics"].get(mk)
        if raw_m is not None:
            tsv_row[mk] = str(raw_m)

    outcome = _outcome_block(
        exp_dir,
        mk=mk,
        direction=direction,
        keeper_metric=keeper_m,
        tsv_row=tsv_row,
    )
    base_v, base_detail = _base_verdict(
        evidence_primary=ev_primary,
        claimed=claimed,
        process=process,
    )
    row: dict[str, Any] = {
        "exp_dir": str(exp_dir),
        "experiment": experiment or exp_dir.name,
        "role": "finalize",
        "claimed_tiers": claimed,
        "evidence_tiers": ev_tiers,
        "evidence_primary": ev_primary,
        "evidence_config_keys": cfg_keys,
        "changed_files": changed,
        "git_range": git_range,
        "process": process,
        "outcome": outcome,
        "verdict": base_v,
        "verdict_detail": base_detail,
    }
    _merge_row_into_tam_json(root, row, window=cfg.window)
    return True


def write_tier_attestation_artifacts(repo_root: Path, result: TierAttestationResult) -> None:
    saved = repo_root / "saved"
    saved.mkdir(exist_ok=True)
    payload = {
        "schema_version": result.schema_version,
        "ts": result.ts,
        "tam_line": result.tam_line,
        "rollup": result.rollup,
        "rows": result.rows,
        "not_attested_tiers": result.not_attested_tiers,
        "false_claims": result.false_claims,
    }
    (saved / "tier_attestation.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (saved / "tier_attestation.md").write_text(result.markdown, encoding="utf-8")
