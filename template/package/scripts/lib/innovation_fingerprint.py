"""创新指纹（Phase 0.75）：keeper vs run config + REB diff → routine/derived/different。"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml  # type: ignore

from lib.nn_config import load_nn_config
from lib.reflect_evidence import ReflectEvidenceBundle
from lib.external.catalog import load_innovation_overlay

# RDDN (T2 migrate+contract)：深度轴收口到 routine/derived/different + dormant novel 背书槽。
# routine(1) < derived(2) < different(3)==novel(3)。旧 extend→derived、旧 formal-novel→different
# 已退役（无 producer）；novel 留作 attestation 背书槽（与 different 同档，T3 激活升 rank 4）。
_DEPTH_RANK = {
    "ambiguous": 0,
    "routine": 1,
    "derived": 2,        # routine 部件重排（旧 extend 退役→derived）
    "different": 3,      # 形式创新（旧 formal-novel 退役→different）
    "novel": 3,          # dormant 背书槽；与 different 同档，T3 升 rank 4
}
_VALID_DEPTHS = frozenset(_DEPTH_RANK)
_CATALOG_PATH = Path(__file__).resolve().parent / "innovation_catalog.yaml"
_REGISTER_RE = re.compile(
    r"@register_(objective|learner|activation)\s*\(\s*['\"]([^'\"]+)['\"]",
    re.I,
)
_SUBSTANTIVE_TRAIN_RE = re.compile(
    r"(curriculum|custom\s+loss|multi[_-]?term|state\s*machine)",
    re.I,
)


@dataclass
class InnovationFingerprintConfig:
    enabled: bool = True
    authoritative: bool = True


@dataclass
class InnovationFingerprintResult:
    schema_version: int = 1
    ts: str = ""
    depth: str = "ambiguous"
    depth_rank: int = 0
    primary_tier: str = "B"
    agent_depth: str = ""
    effective_depth: str = "routine"
    slots_changed: list[str] = field(default_factory=list)
    primary_keys_changed: dict[str, list[Any]] = field(default_factory=dict)
    scalar_keys_changed: list[str] = field(default_factory=list)
    catalog_hits: list[dict[str, Any]] = field(default_factory=list)
    diff_signals: list[str] = field(default_factory=list)
    # T6/ADR-4：catalog 命中 docs_symbols 的命名空间扫描快照（可复现审计；source=local
    # 表示可 import 标准件，not_importable 表示非标准件技法）。落盘入 innovation_audit.json。
    symbol_introspection: list[dict[str, Any]] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    summary_line: str = ""
    fallback: bool = False
    enabled: bool = True
    baseline_exp_dir: str = ""
    candidate_exp_dirs: list[str] = field(default_factory=list)
    pairing_source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_fingerprint_config(repo_root: str | Path = ".") -> InnovationFingerprintConfig:
    cfg = InnovationFingerprintConfig()
    p = Path(repo_root) / "nn-config.yaml"
    if not p.is_file():
        return cfg
    try:
        raw = load_nn_config(Path(repo_root))
        innov = raw.get("innovation") if isinstance(raw.get("innovation"), dict) else {}
        if "fingerprint_enabled" in innov:
            cfg.enabled = bool(innov["fingerprint_enabled"])
        if "fingerprint_authoritative" in innov:
            cfg.authoritative = bool(innov["fingerprint_authoritative"])
    except Exception:
        pass
    return cfg


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _merge_framework_binding_registration(
    catalog: dict[str, Any], repo_root: Path
) -> dict[str, Any]:
    """合并 ``contract/framework_binding.yaml`` 的 ``innovation`` 注册段（框架键第二真源）。

    框架仓的第三方键（如 ``MAMMOTH_MODEL``）属立项期人审事实：登记在 contract
    （governance-sync 不覆盖、运行期 agent 禁改），与种子同权参与硬判定——既不用
    模板发版，也不破 AC3（contract 不是运行期可写区）。键/表名冲突时种子优先
    （模板通用语义不可被仓内改写）。注册段缺失 = 非 framework 仓，no-op；
    注册段畸形 = ValueError 上抛（静默当未注册会把格子悄悄翻转，比崩更糟）。
    """
    from lib.framework_binding import load_framework_binding

    doc = load_framework_binding(repo_root)
    if doc is None:
        return catalog
    innov = doc.get("innovation")
    if innov is None:
        return catalog
    if not isinstance(innov, dict):
        raise ValueError("contract/framework_binding.yaml innovation 段须为 mapping")

    pks = innov.get("primary_keys") or {}
    tables = innov.get("tables") or {}
    if not isinstance(pks, dict) or not isinstance(tables, dict):
        raise ValueError("innovation.primary_keys / innovation.tables 须为 mapping")

    out = dict(catalog)
    merged_pks = dict(out.get("primary_keys") or {})
    for key, spec in pks.items():
        if not isinstance(spec, dict) or not str(spec.get("table") or "").strip():
            raise ValueError(f"innovation.primary_keys.{key} 缺 table")
        tier = str(spec.get("tier") or "").strip().upper()
        if len(tier) != 1 or tier not in "ABCDE":
            raise ValueError(f"innovation.primary_keys.{key} tier 须为 A-E")
        if key not in merged_pks:  # 种子优先，不覆盖模板通用键
            merged_pks[key] = spec
    out["primary_keys"] = merged_pks

    for name, table in tables.items():
        if not isinstance(table, dict) or not table:
            raise ValueError(f"innovation.tables.{name} 须为非空 mapping")
        for k, entry in table.items():
            if not isinstance(entry, dict) or not str(entry.get("change") or "").strip():
                raise ValueError(f"innovation.tables.{name}.{k} 缺 change")
        if name not in catalog:  # 种子表优先
            out[name] = table
    return out


def load_innovation_catalog(repo_root: Path | None = None) -> dict[str, Any]:
    """读种子 catalog（硬、确定性、随模板发版）+ contract 框架键注册段（硬、立项期人审）。
    只硬信这两处——确定性 depth 判定器不得被运行期 overlay 污染（T8/ADR-3 AC3）。
    workspace/innovation_catalog.local.yaml（软、运行期、可回滚）改由
    lib.external.catalog.load_innovation_overlay 单独读，软提示路径消费。
    repo_root=None 时纯种子（不合并 contract，供单测隔离）。
    """
    if not _CATALOG_PATH.is_file():
        return {}
    try:
        data = yaml.safe_load(_CATALOG_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    data = data if isinstance(data, dict) else {}
    if repo_root is None:
        return data
    return _merge_framework_binding_registration(data, Path(repo_root))


def _normalize_exp_dir(repo_root: Path, raw: str) -> Path | None:
    text = (raw or "").strip()
    if not text:
        return None
    p = Path(text)
    if not p.is_absolute():
        p = (repo_root / p).resolve()
    else:
        p = p.resolve()
    if p.is_dir():
        return p
    return None


def _load_round_decision(repo_root: Path) -> dict[str, Any]:
    rd = repo_root / "_runs"
    for name in ("round_decision.json", "evaluation_result.json"):
        p = rd / name
        if not p.is_file() or p.stat().st_size == 0:
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            continue
    return {}


def _candidate_dirs_from_round_decision(repo_root: Path) -> list[Path]:
    data = _load_round_decision(repo_root)
    fin = data.get("finalize_round")
    if isinstance(fin, dict):
        raw_dirs = fin.get("candidate_exp_dirs")
        if isinstance(raw_dirs, list):
            out: list[Path] = []
            for d in raw_dirs:
                norm = _normalize_exp_dir(repo_root, str(d))
                if norm is not None:
                    out.append(norm)
            if out:
                return out
        slots = fin.get("slots")
        if isinstance(slots, list):
            out = []
            for slot in slots:
                if not isinstance(slot, dict):
                    continue
                norm = _normalize_exp_dir(repo_root, str(slot.get("exp_dir") or ""))
                if norm is not None:
                    out.append(norm)
            if out:
                return out
    ev = data.get("evaluated_exp_dir")
    if ev:
        norm = _normalize_exp_dir(repo_root, str(ev))
        if norm is not None:
            return [norm]
    return []


def _resolve_baseline_dir(
    repo_root: Path,
    reb_bundle: ReflectEvidenceBundle,
) -> tuple[Path | None, str]:
    try:
        from lib.ledger_anchor import code_baseline_entry, focus_scenario_id  # noqa: WPS433

        baseline = code_baseline_entry(repo_root, focus_scenario_id(repo_root))
        if baseline and baseline.keeper_exp_dir:
            p = _normalize_exp_dir(repo_root, baseline.keeper_exp_dir)
            if p is not None:
                return p, "code_baseline"
    except ImportError:
        pass
    for ent in reb_bundle.ets:
        if ent.get("role") == "code_baseline" and ent.get("exp_dir"):
            p = _normalize_exp_dir(repo_root, str(ent["exp_dir"]))
            if p is not None:
                return p, "reb_code_baseline"
    for ent in reb_bundle.ets:
        if ent.get("role") == "keeper" and ent.get("exp_dir"):
            p = _normalize_exp_dir(repo_root, str(ent["exp_dir"]))
            if p is not None:
                return p, "reb_keeper"
    return None, ""


def _resolve_candidates_from_reb(
    repo_root: Path,
    reb_bundle: ReflectEvidenceBundle,
) -> list[Path]:
    out: list[Path] = []
    for ent in reversed(reb_bundle.ets):
        role = ent.get("role") or ""
        exp_d = ent.get("exp_dir") or ""
        if exp_d and role not in ("keeper", "code_baseline"):
            p = _normalize_exp_dir(repo_root, str(exp_d))
            if p is not None:
                out.append(p)
                break
    if not out and reb_bundle.ets:
        exp_d = str(reb_bundle.ets[-1].get("exp_dir") or "")
        p = _normalize_exp_dir(repo_root, exp_d)
        if p is not None:
            out.append(p)
    return out


def _resolve_round_experiments(
    repo_root: Path,
    reb_bundle: ReflectEvidenceBundle,
) -> tuple[Path | None, list[Path], str]:
    baseline_dir, baseline_src = _resolve_baseline_dir(repo_root, reb_bundle)
    candidates = _candidate_dirs_from_round_decision(repo_root)
    pairing = ""
    if candidates:
        pairing = "round_decision"
    else:
        candidates = _resolve_candidates_from_reb(repo_root, reb_bundle)
        if candidates:
            pairing = "reb_fallback"
    if baseline_dir and candidates:
        pairing = f"{pairing}+{baseline_src}" if pairing else baseline_src
    elif baseline_src and not pairing:
        pairing = baseline_src
    return baseline_dir, candidates, pairing


def _ignore_config_keys(catalog: dict[str, Any]) -> frozenset[str]:
    raw = catalog.get("ignore_config_keys") or []
    return frozenset(str(k) for k in raw)


def _config_delta(
    keeper_cfg: dict[str, Any],
    run_cfg: dict[str, Any],
    *,
    ignore_keys: frozenset[str] | None = None,
) -> tuple[list[str], dict[str, list[Any]]]:
    ignore = ignore_keys or frozenset()
    changed: list[str] = []
    primary_changed: dict[str, list[Any]] = {}
    for key in sorted(set(keeper_cfg) | set(run_cfg)):
        if key in ignore:
            continue
        if keeper_cfg.get(key) == run_cfg.get(key):
            continue
        changed.append(key)
        primary_changed[key] = [keeper_cfg.get(key), run_cfg.get(key)]
    return changed, primary_changed


def _is_positive(val: Any) -> bool:
    try:
        return float(val) > 0
    except (TypeError, ValueError):
        return bool(val)


def _lookup_catalog_entry(
    catalog: dict[str, Any],
    config_key: str,
    run_val: Any,
) -> tuple[str, str, dict[str, Any]] | None:
    primary = catalog.get("primary_keys") or {}
    meta = primary.get(config_key)
    if not meta:
        return None
    table = str(meta.get("table") or "")
    strategy_key = meta.get("strategy_key")
    if strategy_key:
        entry = (catalog.get(table) or {}).get(str(strategy_key))
        if entry and (config_key.endswith("_ALPHA") and _is_positive(run_val)):
            return table, str(strategy_key), entry
        return None
    if config_key == "D_NOVEL_MODE":
        key = str(run_val or "").lower().strip()
        entry = (catalog.get(table) or {}).get(key)
        if entry:
            return table, key, entry
        return None
    key = str(run_val or "").lower().strip()
    entry = (catalog.get(table) or {}).get(key)
    if entry:
        return table, key, entry
    return None


def _catalog_hit_dict(table: str, key: str, entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "table": table,
        "key": key,
        "change": str(entry.get("change") or ""),
        "paper_query": str(entry.get("paper_query") or ""),
        "docs_symbols": list(entry.get("docs_symbols") or []),
    }


def _depth_from_change(change: str) -> str:
    c = (change or "").strip().lower()
    if c == "drop_in":
        return "derived"          # 旧 extend→derived
    if c == "recombine":          # T7：routine 部件重排 → derived（catalog 声明）
        # 非全 routine 部件由下方 compute_fingerprint_from_configs 的 T7 校验块升 different
        # （依赖 T6 introspection 认 routine 部件）；此处先乐观标 derived，事后块再纠偏。
        return "derived"
    if c == "substantive":
        return "different"        # 旧 formal-novel→different
    if c == "baseline":
        return "routine"
    return "different"            # 默认回落 different（不再回落 novel）


def _max_depth(*depths: str) -> str:
    best = "ambiguous"
    best_rank = -1
    for d in depths:
        dl = (d or "ambiguous").strip().lower()
        if dl not in _DEPTH_RANK:
            dl = "ambiguous"
        if _DEPTH_RANK[dl] > best_rank:
            best_rank = _DEPTH_RANK[dl]
            best = dl
    return best


# paper_depth 阶梯（ADR-7）：novel 仅 P3+ 可达——innovate=P2 不行，aggressive=P3 行。
# 与 executor._PAPER_DEPTH_RANK 同义；此处独立持有避免 fingerprint 依赖 external 包。
_PAPER_DEPTH_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4, "P5": 5}


def apply_novel_ceiling(fp_depth: str, attestation_verdict: str, paper_depth: str) -> str:
    """T3 / ADR-2：different 是默认天花板；novel = different ⊕ (文献背书 supported ∧ P3+)。

    fingerprint 结构层定 different（形式创新）后，是否升 novel 由外部背书决定：
    - routine / derived / novel 透传——novel 只从 different 升，不会把 routine 抬成 novel；
    - different + supported + paper_depth≥P3 → novel（背书独占）；
    - different + inconclusive/skipped/弱信号 → 留 different（off-whitelist 即 different）。

    P3+ 门控与 ADR-7 阶梯对齐（MODE_TO_EXTERNAL：innovate=P2 / aggressive=P3）。
    """
    depth = (fp_depth or "").strip().lower()
    if depth != "different":
        return depth
    verdict = (attestation_verdict or "").strip().lower()
    if verdict == "supported" and _PAPER_DEPTH_RANK.get(str(paper_depth or "P0"), 0) >= 3:
        return "novel"
    return "different"


def _exp_dir_matches(target: str, run_s: str) -> bool:
    if not target or not run_s:
        return False
    if target == run_s:
        return True
    return run_s.endswith(target) or target.endswith(run_s)


def _has_primary_key_delta(
    baseline_cfg: dict[str, Any],
    run_cfg: dict[str, Any],
    catalog: dict[str, Any],
) -> bool:
    ignore_keys = _ignore_config_keys(catalog)
    _, primary_changed = _config_delta(
        baseline_cfg, run_cfg, ignore_keys=ignore_keys,
    )
    primary_keys = set((catalog.get("primary_keys") or {}).keys())
    return any(k in primary_keys for k in primary_changed)


def _register_matches_unchanged_primary(
    kind: str,
    name: str,
    keeper_cfg: dict[str, Any],
    run_cfg: dict[str, Any],
) -> bool:
    key_map = {"objective": "LOSS", "learner": "MODEL_ARCH", "activation": "ACTIVATION"}
    cfg_key = key_map.get(kind)
    if not cfg_key:
        return False
    keeper_val = str(keeper_cfg.get(cfg_key) or "").lower().strip()
    run_val = str(run_cfg.get(cfg_key) or "").lower().strip()
    return bool(keeper_val and keeper_val == run_val == name.lower().strip())


def _introspect_catalog_symbols(
    catalog_hits: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    """T6/ADR-4：扫描 catalog 命中条目的 docs_symbols（命名空间扫描）。

    可 import（标准件，如 CrossEntropyLoss = torch.nn）→ source="local" 快照；
    不可 import（非标准件技法）→ source="not_importable"。返回
    (snapshots, importable_set, all_symbols)：importable_set = 成功 import 的
    符号集合；all_symbols = docs_symbols 去空白去重后的全集（与 scan_symbols
    看到的名字口径一致）。depth 判定层据此判「全标准件重用」→ 封顶 derived。

    非致命：scan_symbols 拿不到（如 torch 缺失）→ 返 ([], set(), all_symbols)，
    不封顶、不抛。懒 import 便于单测 monkeypatch（lib.external.docs_local.scan_symbols）。
    """
    symbols: list[str] = []
    seen: set[str] = set()
    for hit in catalog_hits:
        for sym in (hit.get("docs_symbols") or []):
            s = str(sym).strip()
            if s and s not in seen:
                seen.add(s)
                symbols.append(s)
    if not symbols:
        return [], set(), seen
    try:  # optional: torch 不可用 → 不封顶（safe default），不阻断 fingerprint
        from lib.external.docs_local import scan_symbols
        snapshots = scan_symbols(symbols)
    except Exception:
        return [], set(), seen
    importable = {str(s.get("symbol")) for s in snapshots if s.get("source") == "local"}
    return snapshots, importable, seen


def _collect_diff_signals(
    bundle: ReflectEvidenceBundle,
    run_dirs: list[Path],
    catalog: dict[str, Any],
    *,
    keeper_cfg: dict[str, Any] | None = None,
    run_cfgs: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[str], str]:
    signals: list[str] = []
    depth = "routine"
    if not run_dirs:
        return signals, depth

    keeper_cfg = keeper_cfg or {}
    run_cfgs = run_cfgs or {}

    run_paths = {str(d.resolve()) for d in run_dirs}
    summaries: list[str] = []
    for diff in bundle.snapshot_diffs or []:
        target = str(diff.get("target") or "")
        if not target:
            continue
        if not any(_exp_dir_matches(target, run_s) for run_s in run_paths):
            continue
        summaries.extend(diff.get("summaries") or [])

    text = "\n".join(summaries)
    for m in _REGISTER_RE.finditer(text):
        kind, name = m.group(1).lower(), m.group(2).lower()
        run_cfg = {}
        for run_s, cfg in run_cfgs.items():
            if any(_exp_dir_matches(run_s, rp) for rp in run_paths):
                run_cfg = cfg
                break
        if _register_matches_unchanged_primary(kind, name, keeper_cfg, run_cfg):
            continue
        table = {"objective": "objectives", "learner": "learners", "activation": "activations"}.get(
            kind, ""
        )
        entry = (catalog.get(table) or {}).get(name) if table else None
        signals.append(f"new_register:{kind}:{name}")
        if entry and str(entry.get("change")) == "drop_in":
            depth = _max_depth(depth, "derived")
        else:
            depth = _max_depth(depth, "different")

    if _SUBSTANTIVE_TRAIN_RE.search(text):
        signals.append("substantive_train_diff")
        depth = _max_depth(depth, "different")

    return signals, depth


def compute_fingerprint_from_configs(
    keeper_cfg: dict[str, Any],
    run_cfg: dict[str, Any],
    catalog: dict[str, Any],
    *,
    agent_depth: str = "",
    diff_depth: str = "routine",
    diff_signals: list[str] | None = None,
    primary_tier_fallback: str = "B",
    overlay: dict[str, Any] | None = None,
) -> InnovationFingerprintResult:
    scalar_keys = set(catalog.get("scalar_keys") or [])
    primary_keys = set((catalog.get("primary_keys") or {}).keys())
    ignore_keys = _ignore_config_keys(catalog)

    changed_keys, primary_changed = _config_delta(
        keeper_cfg, run_cfg, ignore_keys=ignore_keys,
    )
    scalar_changed = [k for k in changed_keys if k in scalar_keys]
    primary_changed_keys = {k: v for k, v in primary_changed.items() if k in primary_keys}

    reasons: list[str] = []
    catalog_hits: list[dict[str, Any]] = []
    slots: set[str] = set()
    config_depth = "ambiguous"

    if not keeper_cfg or not run_cfg:
        reasons.append("no_config")
        config_depth = "ambiguous"
    elif not changed_keys:
        config_depth = "routine"
        reasons.append("identical")
    elif not primary_changed_keys and all(k in scalar_keys for k in changed_keys):
        config_depth = "routine"
        reasons.append("scalar_only")
    else:
        for pk in primary_changed_keys:
            meta = (catalog.get("primary_keys") or {}).get(pk) or {}
            tier = str(meta.get("tier") or primary_tier_fallback)
            slots.add(tier)
        if len(slots) > 1:
            config_depth = "different"
            reasons.append("multi_slot")
        elif primary_changed_keys:
            pk = next(iter(primary_changed_keys))
            run_val = primary_changed_keys[pk][1]
            hit = _lookup_catalog_entry(catalog, pk, run_val)
            if hit:
                table, key, entry = hit
                catalog_hits.append(_catalog_hit_dict(table, key, entry))
                config_depth = _depth_from_change(str(entry.get("change")))
                reasons.append(f"single_slot_{entry.get('change', 'unknown')}")
            else:
                config_depth = "different"
                reasons.append("unknown_key")
        elif changed_keys:
            config_depth = "routine"
            reasons.append("non_primary_only")

    depth = _max_depth(config_depth, diff_depth)
    if diff_signals:
        reasons.extend(diff_signals)

    # T6/ADR-4 标准件检测：catalog 命中 docs_symbols 全可 import（标准件重用，
    # 如换一个仍走 CrossEntropyLoss 的 loss 变体）→ 封顶 derived（非 different/novel）。
    # 命中条目无 docs_symbols（非 import 技法，走 T8 catalog）或多槽改动不触发封顶。
    # all_symbols 与 scan_symbols 口径一致（去空白去重），避免带尾空格的符号名漏判封顶。
    snapshots, importable, all_symbols = _introspect_catalog_symbols(catalog_hits)
    if all_symbols and importable and all_symbols <= importable:
        if _DEPTH_RANK.get(depth, 0) > _DEPTH_RANK["derived"]:
            depth = "derived"
            reasons.append("importable_standard_parts")

    # T7/ADR-4：routine 部件重排检测。catalog 标 change=recombine 的命中条目，
    # docs_symbols 经上面 T6 introspection 确认全可 import（routine 标准件）→ 新组合
    # 属 derived（非 routine 无变化、非 different 形式创新），reason routine_recombination。
    # recombine 但部件非全 routine → 非真·routine 重排，升 different（detection 依赖
    # introspection 认 routine 部件——认不出 routine 时不给 derived），reason recombine_non_routine。
    for hit in catalog_hits:
        if str(hit.get("change") or "").strip().lower() != "recombine":
            continue
        hit_syms = {str(s).strip() for s in (hit.get("docs_symbols") or []) if str(s).strip()}
        if hit_syms and hit_syms <= importable:
            if _DEPTH_RANK.get(depth, 0) > _DEPTH_RANK["derived"]:
                depth = "derived"
            if "routine_recombination" not in reasons:
                reasons.append("routine_recombination")
        else:
            depth = _max_depth(depth, "different")
            if "recombine_non_routine" not in reasons:
                reasons.append("recombine_non_routine")

    # T8/ADR-3 overlay 软提示：runtime overlay（T4 反馈边喂）命中 config delta 解析到的
    # (table, key) → 追加软 reason overlay_hint:<key>，**不动 depth**（AC3：确定性判定器
    # 只硬信种子，overlay 当参考、不污染硬判定）。覆盖两类命中：种子命中（catalog_hits）
    # 与 unknown_key（种子无条目、overlay 有 → 软标注「实为已知技法」，depth 仍按硬判）。
    # find_discoveries 表非技法、不在 primary_keys，故不触软提示（原始论文留作可回滚痕迹）。
    if overlay:
        resolved: list[tuple[str, str]] = [
            (str(h.get("table") or ""), str(h.get("key") or "")) for h in catalog_hits
        ]
        if "unknown_key" in reasons:
            for pk, vals in primary_changed_keys.items():
                meta = (catalog.get("primary_keys") or {}).get(pk) or {}
                tbl = str(meta.get("table") or "")
                kv = str(vals[1] or "").lower().strip()
                if tbl and kv:
                    resolved.append((tbl, kv))
        for tbl, kv in resolved:
            if not kv:
                continue
            ov_tbl = overlay.get(tbl)
            if isinstance(ov_tbl, dict) and kv in ov_tbl:
                tag = f"overlay_hint:{kv}"
                if tag not in reasons:
                    reasons.append(tag)

    agent = (agent_depth or "").strip().lower()
    effective = depth
    if depth == "ambiguous" and agent in _VALID_DEPTHS:
        effective = agent

    tier = primary_tier_fallback
    if slots:
        tier = sorted(slots)[0]
    elif catalog_hits:
        for pk in primary_changed_keys:
            pk_meta = (catalog.get("primary_keys") or {}).get(pk)
            if pk_meta:
                tier = str(pk_meta.get("tier") or tier)
                break

    warn = ""
    if agent and agent in _VALID_DEPTHS and agent != depth and depth != "ambiguous":
        warn = " WARN"

    pk_summary = ""
    if primary_changed_keys:
        pk, vals = next(iter(primary_changed_keys.items()))
        pk_summary = f" | {pk} {vals[0]}→{vals[1]}"

    summary = f"[Fingerprint: Tier {tier} {depth}{pk_summary}"
    if agent:
        summary += f" | agent={agent}{warn}"
    summary += f"; effective={effective}]"

    return InnovationFingerprintResult(
        ts=datetime.now(timezone.utc).isoformat(),
        depth=depth,
        depth_rank=_DEPTH_RANK.get(depth, 0),
        primary_tier=tier.upper()[:1] if tier else "B",
        agent_depth=agent,
        effective_depth=effective,
        slots_changed=sorted(slots),
        primary_keys_changed=primary_changed_keys,
        scalar_keys_changed=scalar_changed,
        catalog_hits=catalog_hits,
        diff_signals=list(diff_signals or []),
        symbol_introspection=snapshots,
        reasons=reasons,
        summary_line=summary,
        fallback=False,
        enabled=True,
    )


def _primary_signature(primary_keys_changed: dict[str, list[Any]]) -> tuple[tuple[str, Any, Any], ...]:
    return tuple(sorted((k, v[0], v[1]) for k, v in primary_keys_changed.items()))


def _merge_fingerprint_results(
    results: list[InnovationFingerprintResult],
    *,
    agent_depth: str = "",
    primary_tier_fallback: str = "B",
) -> InnovationFingerprintResult:
    if not results:
        return InnovationFingerprintResult(
            ts=datetime.now(timezone.utc).isoformat(),
            depth="ambiguous",
            agent_depth=(agent_depth or "").strip().lower(),
            effective_depth="ambiguous",
            reasons=["no_candidates"],
            summary_line="[Fingerprint: no candidates]",
            fallback=True,
        )
    if len(results) == 1:
        return results[0]

    depth = _max_depth(*(r.depth for r in results))
    reasons: list[str] = []
    slots: set[str] = set()
    scalar: set[str] = set()
    catalog_hits: list[dict[str, Any]] = []
    diff_signals: list[str] = []
    symbol_snaps: list[dict[str, Any]] = []
    primary_sigs = {_primary_signature(r.primary_keys_changed) for r in results}

    for r in results:
        reasons.extend(r.reasons)
        slots.update(r.slots_changed)
        scalar.update(r.scalar_keys_changed)
        catalog_hits.extend(r.catalog_hits)
        diff_signals.extend(r.diff_signals)
        symbol_snaps.extend(r.symbol_introspection)

    if len(primary_sigs) > 1:
        depth = _max_depth(depth, "different")
        reasons.append("multi_candidate_primary_mismatch")

    primary_keys_changed = results[0].primary_keys_changed
    tier = results[0].primary_tier or primary_tier_fallback
    if slots:
        tier = sorted(slots)[0].upper()[:1]

    agent = (agent_depth or results[0].agent_depth or "").strip().lower()
    effective = depth
    if depth == "ambiguous" and agent in _VALID_DEPTHS:
        effective = agent

    warn = ""
    if agent and agent in _VALID_DEPTHS and agent != depth and depth != "ambiguous":
        warn = " WARN"

    pk_summary = ""
    if primary_keys_changed:
        pk, vals = next(iter(primary_keys_changed.items()))
        pk_summary = f" | {pk} {vals[0]}→{vals[1]}"

    summary = f"[Fingerprint: Tier {tier} {depth}{pk_summary}"
    if agent:
        summary += f" | agent={agent}{warn}"
    summary += f"; effective={effective}]"

    seen_reasons: list[str] = []
    for reason in reasons:
        if reason not in seen_reasons:
            seen_reasons.append(reason)

    seen_hits: list[dict[str, Any]] = []
    hit_keys: set[str] = set()
    for hit in catalog_hits:
        key = f"{hit.get('table')}:{hit.get('key')}"
        if key in hit_keys:
            continue
        hit_keys.add(key)
        seen_hits.append(hit)

    # T6：合并多候选的符号扫描快照，按 symbol 去重（首个胜出，保留 source 信息）。
    seen_snaps: list[dict[str, Any]] = []
    snap_syms: set[str] = set()
    for snap in symbol_snaps:
        sym = str(snap.get("symbol") or "")
        if sym and sym not in snap_syms:
            snap_syms.add(sym)
            seen_snaps.append(snap)

    return InnovationFingerprintResult(
        ts=datetime.now(timezone.utc).isoformat(),
        depth=depth,
        depth_rank=_DEPTH_RANK.get(depth, 0),
        primary_tier=tier,
        agent_depth=agent,
        effective_depth=effective,
        slots_changed=sorted(slots),
        primary_keys_changed=primary_keys_changed,
        scalar_keys_changed=sorted(scalar),
        catalog_hits=seen_hits,
        diff_signals=list(dict.fromkeys(diff_signals)),
        symbol_introspection=seen_snaps,
        reasons=seen_reasons,
        summary_line=summary,
        fallback=False,
        enabled=True,
    )


def build_innovation_fingerprint(
    repo_root: Path,
    *,
    reb_bundle: ReflectEvidenceBundle,
    agent_depth: str = "",
    tier_fallback: str = "B",
    baseline_dir: Path | None = None,
    candidate_dirs: list[Path] | None = None,
) -> InnovationFingerprintResult:
    cfg = load_fingerprint_config(repo_root)
    if not cfg.enabled:
        agent = (agent_depth or "routine").strip().lower()
        if agent not in _VALID_DEPTHS:
            agent = "routine"
        return InnovationFingerprintResult(
            ts=datetime.now(timezone.utc).isoformat(),
            depth=agent,
            depth_rank=_DEPTH_RANK.get(agent, 1),
            primary_tier=(tier_fallback or "B").upper()[:1],
            agent_depth=agent,
            effective_depth=agent,
            summary_line="[Fingerprint: disabled]",
            fallback=True,
            enabled=False,
        )

    catalog = load_innovation_catalog(repo_root)
    overlay = load_innovation_overlay(repo_root)
    if (baseline_dir is None) ^ (candidate_dirs is None):
        raise ValueError("baseline_dir 与 candidate_dirs 必须同时给或同时省略")
    if baseline_dir is not None:
        pairing_source = "explicit"
        candidate_dirs = list(candidate_dirs)
    else:
        baseline_dir, candidate_dirs, pairing_source = _resolve_round_experiments(
            repo_root, reb_bundle,
        )
    baseline_cfg = _load_json(baseline_dir / "config.json") if baseline_dir else {}

    per_candidate: list[InnovationFingerprintResult] = []
    merged_diff_signals: list[str] = []
    merged_diff_depth = "routine"
    run_cfgs = {
        str(run_dir.resolve()): _load_json(run_dir / "config.json")
        for run_dir in candidate_dirs
    }
    primary_delta = any(
        _has_primary_key_delta(baseline_cfg, run_cfg, catalog)
        for run_cfg in run_cfgs.values()
    )
    if primary_delta:
        diff_signals, diff_depth = _collect_diff_signals(
            reb_bundle,
            candidate_dirs,
            catalog,
            keeper_cfg=baseline_cfg,
            run_cfgs=run_cfgs,
        )
        merged_diff_signals = diff_signals
        merged_diff_depth = diff_depth

    for run_dir in candidate_dirs:
        run_cfg = run_cfgs[str(run_dir.resolve())]
        per_candidate.append(
            compute_fingerprint_from_configs(
                baseline_cfg,
                run_cfg,
                catalog,
                agent_depth=agent_depth,
                diff_depth=merged_diff_depth,
                diff_signals=merged_diff_signals,
                primary_tier_fallback=tier_fallback,
                overlay=overlay,
            )
        )

    result = _merge_fingerprint_results(
        per_candidate,
        agent_depth=agent_depth,
        primary_tier_fallback=tier_fallback,
    )
    result.baseline_exp_dir = str(baseline_dir.resolve()) if baseline_dir else ""
    result.candidate_exp_dirs = [str(d.resolve()) for d in candidate_dirs]
    result.pairing_source = pairing_source

    agent = (agent_depth or "").strip().lower()
    if result.depth == "ambiguous":
        result.fallback = True
        if agent in _VALID_DEPTHS:
            result.effective_depth = agent
        else:
            result.effective_depth = "routine"
    elif not cfg.authoritative and agent in _VALID_DEPTHS:
        result.effective_depth = agent
    else:
        result.effective_depth = result.depth

    # T6/AC③：扫描快照落 saved/innovation_audit.json（可复现审计，非致命）。
    # 懒 import 避免模块加载期耦合；record_symbol_introspection 自身写失败也不抛。
    if result.symbol_introspection:
        try:
            from lib.innovation_audit import record_symbol_introspection
            record_symbol_introspection(repo_root, result.symbol_introspection)
        except Exception:
            pass

    return result


def write_fingerprint_artifact(repo_root: Path, result: InnovationFingerprintResult) -> Path:
    out = Path(repo_root) / "saved" / "innovation_fingerprint.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return out
