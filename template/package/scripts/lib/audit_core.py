"""审查核心纯函数：选对象、容差、种子、消融臂、门槛。

不训练、不写卡片/index（卡片与 index 见后续任务）。
"""
from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


INDEX_REL = "saved/audit/index.json"


@dataclass
class AuditTarget:
    scenario_id: str
    audited_exp_dir: str  # repo 相对路径
    config_sha256: str
    original_seed: int
    original_primary: float
    metric_key: str
    metric_direction: str  # "maximize" | "minimize"


def config_sha256(cfg: dict) -> str:
    raw = json.dumps(cfg, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def repro_tolerance(original_primary: float, near_best_abs: float) -> float:
    if near_best_abs > 0:
        return float(near_best_abs)
    return max(abs(float(original_primary)) * 0.01, 1e-4)


def extra_seeds(original_seed: int, n_total: int = 5) -> list[int]:
    """含原种子，长度 n_total；其余 (seed+i) % 2**32。"""
    seed = int(original_seed) % (2**32)
    out = [seed]
    for i in range(1, max(1, int(n_total))):
        if len(out) >= n_total:
            break
        out.append((seed + i) % (2**32))
    return out[:n_total]


def ablation_config(full_cfg: dict, baseline_cfg: dict, keys: list[str]) -> dict:
    out = deepcopy(full_cfg)
    for k in keys:
        if k in baseline_cfg:
            out[k] = deepcopy(baseline_cfg[k])
    return out


def pooled_std(s_f: float, n_f: int, s_a: float, n_a: int) -> float:
    """合并标准差：s_p = sqrt(((n_f-1)s_f^2+(n_a-1)s_a^2)/(n_f+n_a-2))。"""
    denom = n_f + n_a - 2
    if denom <= 0:
        return 0.0
    numer = (n_f - 1) * float(s_f) ** 2 + (n_a - 1) * float(s_a) ** 2
    return math.sqrt(numer / denom)


def ablation_drop_exceeds(
    full_mean: float,
    full_std: float,
    n_f: int,
    ab_mean: float,
    ab_std: float,
    n_a: int,
    direction: str,
) -> bool | None:
    """n_f+n_a < 4 → None（不做门槛）。下降 > 2 s_p 为 True。"""
    if n_f + n_a < 4:
        return None
    sp = pooled_std(full_std, n_f, ab_std, n_a)
    if direction == "minimize":
        drop = float(ab_mean) - float(full_mean)
    else:
        drop = float(full_mean) - float(ab_mean)
    return drop > 2.0 * sp


def _focus_scenario(repo_root: Path) -> str:
    try:
        from lib.ledger_anchor import focus_scenario_id

        sid = (focus_scenario_id(repo_root) or "").strip()
        if sid:
            return sid
    except Exception:
        pass
    try:
        from lib.scenario_inventory import focus_scenario_id as _focus

        sid = (_focus(repo_root) or "").strip()
        if sid:
            return sid
    except Exception:
        pass
    return "default"


def _metric_meta(repo_root: Path, primary: dict[str, Any] | None) -> tuple[str, str]:
    """能从 contract/nn-config 读则用；否则 test_acc / maximize。"""
    try:
        from lib.run_ledger_summary import metric_direction as _md
        from lib.run_ledger_summary import metric_key as _mk

        mk = str(_mk(repo_root) or "").strip()
        md = str(_md(repo_root) or "").strip()
        if mk and md in ("maximize", "minimize"):
            # 无 contract 时 AST 默认 val_accuracy；优先用 results 里的主分键
            if not (repo_root / "contract" / "__init__.py").is_file():
                if isinstance(primary, dict) and primary:
                    return str(next(iter(primary))), md or "maximize"
                return "test_acc", md or "maximize"
            return mk, md
    except Exception:
        pass
    if isinstance(primary, dict) and primary:
        return str(next(iter(primary))), "maximize"
    return "test_acc", "maximize"


def _metrics_map(results: dict[str, Any]) -> dict[str, Any]:
    pm = results.get("primary_metric")
    if isinstance(pm, dict) and pm:
        return pm
    m = results.get("metrics")
    if isinstance(m, dict) and m:
        return m
    return {}


def primary_from_results(results: dict[str, Any], metric_key: str = "") -> float:
    """读主分：优先 primary_metric，否则 metrics（CSI 成绩文件常见只有后者）。"""
    md = _metrics_map(results)
    if metric_key and metric_key in md:
        return float(md[metric_key])
    for k in ("sgcs", "test_acc", "val_accuracy"):
        if k in md:
            return float(md[k])
    if md:
        return float(next(iter(md.values())))
    pm = results.get("primary_metric")
    if isinstance(pm, (int, float)):
        return float(pm)
    raise ValueError("results.json 缺少 primary_metric / metrics")


def _original_primary(results: dict[str, Any], metric_key: str = "") -> float:
    return primary_from_results(results, metric_key)


def _rel_exp_dir(repo_root: Path, exp_dir: str | Path) -> str:
    root = repo_root.resolve()
    p = Path(exp_dir)
    if not p.is_absolute():
        p = root / p
    p = p.resolve()
    try:
        return str(p.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(exp_dir).replace("\\", "/")


def _load_target_from_exp(
    repo_root: Path,
    *,
    scenario_id: str,
    exp_dir: str,
) -> AuditTarget:
    root = repo_root.resolve()
    rel = _rel_exp_dir(root, exp_dir)
    exp_path = root / rel
    cfg_path = exp_path / "config.json"
    res_path = exp_path / "results.json"
    if not cfg_path.is_file():
        raise FileNotFoundError(f"缺少 config.json: {rel}")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict):
        raise ValueError(f"config.json 非 dict: {rel}")
    if not res_path.is_file():
        raise FileNotFoundError(f"缺少 results.json: {rel}")
    raw = json.loads(res_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"results.json 非 dict: {rel}")
    results = raw
    primary_dict = _metrics_map(results)
    mk, md = _metric_meta(root, primary_dict if primary_dict else None)
    original_primary = _original_primary(results, mk)
    seed_raw = cfg.get("SEED", cfg.get("seed", 0))
    return AuditTarget(
        scenario_id=scenario_id,
        audited_exp_dir=rel,
        config_sha256=config_sha256(cfg),
        original_seed=int(seed_raw) % (2**32),
        original_primary=float(original_primary),
        metric_key=mk,
        metric_direction=md,
    )


def pick_target(
    repo_root: Path,
    *,
    exp_dir: str | None = None,
    scenario_id: str | None = None,
) -> AuditTarget:
    """无 exp_dir：keepers.json 主场景；无 keeper 则该场景 TSV 最优行。"""
    root = Path(repo_root).resolve()
    sid = (scenario_id or _focus_scenario(root)).strip() or "default"

    if exp_dir:
        return _load_target_from_exp(root, scenario_id=sid, exp_dir=exp_dir)

    from lib.run_ledger_summary import (
        _best_row_for_scenario,
        load_keepers,
        metric_direction,
        metric_key,
    )

    keepers = load_keepers(root)
    entry = keepers.get(sid) or {}
    keeper_dir = str(entry.get("keeper_exp_dir") or "").strip()
    if keeper_dir:
        return _load_target_from_exp(root, scenario_id=sid, exp_dir=keeper_dir)

    try:
        mk = metric_key(root)
        md = metric_direction(root)
    except Exception:
        mk, md = "test_acc", "maximize"
    best = _best_row_for_scenario(root, sid, mk, md)
    if not best:
        raise ValueError(f"场景 {sid} 无 keeper 且成绩表无可用最优行")
    best_dir = str(best.get("exp_dir") or "").strip()
    if not best_dir:
        raise ValueError(f"场景 {sid} 最优行缺少 exp_dir")
    return _load_target_from_exp(root, scenario_id=sid, exp_dir=best_dir)


def resolve_fingerprint_baseline(
    repo_root: Path,
    scenario_id: str,
    *,
    exclude_exp_dir: str | None = None,
) -> tuple[Path | None, str]:
    """返回 (目录, 'reference'|'plain'|'none')。不用 keepers.json。"""
    from lib.run_ledger_summary import tsv_rows

    root = Path(repo_root).resolve()
    sid = (scenario_id or "").strip()
    ref_path: Path | None = None
    plain_path: Path | None = None
    for row in tsv_rows(root):
        if str(row.get("scenario_id", "")).strip() != sid:
            continue
        if row.get("experiment") == "preflight_check":
            continue
        tag = str(row.get("baseline_tag", "")).strip().lower()
        exp = str(row.get("exp_dir") or "").strip()
        if not exp:
            continue
        if exclude_exp_dir and _audit_paths_match(exp, exclude_exp_dir):
            continue
        p = root / exp if not Path(exp).is_absolute() else Path(exp)
        if tag == "reference" and ref_path is None:
            ref_path = p
        elif tag == "plain" and plain_path is None:
            plain_path = p
    if ref_path is not None:
        return ref_path, "reference"
    if plain_path is not None:
        return plain_path, "plain"
    return None, "none"


def _norm_audit_path(p: str) -> str:
    return Path(p).as_posix().rstrip("/")


def _audit_paths_match(a: str, b: str) -> bool:
    na = _norm_audit_path(a)
    nb = _norm_audit_path(b)
    if na == nb:
        return True
    return na.endswith("/" + nb) or nb.endswith("/" + na) or na.endswith(nb) or nb.endswith(na)


def _to_repo_rel_posix(repo_root: Path, p: str) -> str:
    root = repo_root.resolve()
    path = Path(p)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return _norm_audit_path(str(p))


def _empty_index() -> dict[str, Any]:
    return {"schema_version": 1, "by_scenario": {}}


def load_index(repo_root: Path) -> dict:
    root = Path(repo_root).resolve()
    path = root / INDEX_REL
    if not path.is_file():
        return _empty_index()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _empty_index()
    if not isinstance(data, dict):
        return _empty_index()
    if "by_scenario" not in data or not isinstance(data.get("by_scenario"), dict):
        data = dict(data)
        data["by_scenario"] = {}
    if "schema_version" not in data:
        data = dict(data)
        data["schema_version"] = 1
    return data


def write_index_entry(
    repo_root: Path,
    *,
    scenario_id: str,
    card_dir: str,
    audited_exp_dir: str,
    config_sha256: str,
) -> dict:
    root = Path(repo_root).resolve()
    sid = (scenario_id or "").strip()
    if not sid:
        raise ValueError("scenario_id 不能为空")

    data = load_index(root)
    by_scenario = data.setdefault("by_scenario", {})
    entry = by_scenario.setdefault(sid, {"latest": None, "history": []})
    if not isinstance(entry, dict):
        entry = {"latest": None, "history": []}
        by_scenario[sid] = entry
    history = entry.setdefault("history", [])
    if not isinstance(history, list):
        history = []
        entry["history"] = history

    latest = entry.get("latest")
    if isinstance(latest, dict):
        history.append(latest)

    rel_card_dir = _to_repo_rel_posix(root, card_dir)
    rel_audited = _to_repo_rel_posix(root, audited_exp_dir)
    new_latest = {
        "card_dir": rel_card_dir,
        "audited_exp_dir": rel_audited,
        "config_sha256": str(config_sha256),
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    entry["latest"] = new_latest

    index_path = root / INDEX_REL
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return data


def injection_for_scenario(repo_root: Path, scenario_id: str) -> dict | None:
    root = Path(repo_root).resolve()
    sid = (scenario_id or "").strip()
    if not sid:
        return None

    data = load_index(root)
    by_scenario = data.get("by_scenario") or {}
    if not isinstance(by_scenario, dict):
        return None
    entry = by_scenario.get(sid)
    if not isinstance(entry, dict):
        return None
    latest = entry.get("latest")
    if not isinstance(latest, dict):
        return None

    card_dir = str(latest.get("card_dir") or "").strip()
    audited_exp_dir = str(latest.get("audited_exp_dir") or "").strip()
    if not card_dir or not audited_exp_dir:
        return None

    from lib.run_ledger_summary import load_keepers

    keepers = load_keepers(root)
    keeper_entry = keepers.get(sid) or {}
    keeper_dir = str(keeper_entry.get("keeper_exp_dir") or "").strip()

    status = "current" if keeper_dir and _audit_paths_match(keeper_dir, audited_exp_dir) else "superseded"
    card_json_rel = f"{card_dir.rstrip('/')}/card.json"
    inj = {
        "status": status,
        "card_dir": card_dir,
        "audited_exp_dir": audited_exp_dir,
        "one_liner": "",
        "card_json_rel": card_json_rel,
    }
    inj["one_liner"] = compose_audit_one_liner(root, inj)
    return inj


def compose_audit_one_liner(repo_root: Path, inj: dict) -> str:
    """card.md 前 8 行，否则 card.json 拼一句。已有 one_liner 则原样返回。"""
    existing = str(inj.get("one_liner") or "").strip()
    if existing:
        return existing
    root = Path(repo_root)
    card_dir = str(inj.get("card_dir") or "").strip()
    md_path = (root / card_dir / "card.md") if card_dir else None
    if md_path is not None and md_path.is_file():
        lines = md_path.read_text(encoding="utf-8", errors="replace").splitlines()[:8]
        joined = " ".join(ln.strip() for ln in lines if ln.strip())
        return joined[:240]
    json_rel = str(inj.get("card_json_rel") or "").strip()
    jp = (root / json_rel) if json_rel else None
    if jp is None or not jp.is_file():
        return ""
    try:
        data = json.loads(jp.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not isinstance(data, dict):
        return ""
    parts: list[str] = []
    if "repro_ok" in data:
        parts.append("复现对上" if data["repro_ok"] else "复现没对上")
    n_seeds = data.get("n_seeds")
    if n_seeds:
        parts.append(f"多种子n={n_seeds}")
    depth = data.get("attested_depth")
    if depth:
        parts.append(f"新不新={depth}")
    if data.get("ablation_ran"):
        parts.append("已做消融")
    return "；".join(parts)


def format_audit_card_body(repo_root: Path, inj: dict) -> str:
    """注入正文（无标题）。前科 one_liner 加「上一套：」，避免旧 novel 写成当前结论。"""
    status = str(inj.get("status") or "")
    one = compose_audit_one_liner(repo_root, inj)
    if status == "current":
        label = "当前这套已审查"
    else:
        label = "上一套已审查"
        if one and not one.startswith("上一套："):
            one = f"上一套：{one}"
    lines = [label]
    if one:
        lines.append(one)
    return "\n".join(lines)
