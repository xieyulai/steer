"""Reflect 证据包（REB）：Phase 0.5 确定性组装（模板级，不绑业务仓）。"""
from __future__ import annotations

import difflib
import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.run_ledger_summary import (
    _parse_contract_ast,
    _try_load_contract,
    agent_config,
    build_summary,
    format_brief,
    format_keeper_status,
    format_roadmap_status,
    load_keepers,
    metric_direction,
    metric_key,
    plateau_streak,
    roadmap_status,
    round_decision_status,
    tsv_rows,
)
from lib.train_dynamics import (  # noqa: E402
    TRAIN_DYNAMICS_JSON,
    TRAIN_DYNAMICS_MD,
    read_metrics_series_rows,
    summarize_series_tail,
)

_LOG_SIGNAL_RE = re.compile(
    r"(nan|oom|out of memory|cuda|early\s*stop|error|exception|failed|traceback)",
    re.I,
)
_SNAPSHOT_SKIP = frozenset({"__pycache__", "outputs", ".pyc"})


_GIT_SCOPE_PATHS = ("train.py", "workspace/")
_GIT_LOG_RE = re.compile(r"^([0-9a-f]{7,40})\|(.+)$")


@dataclass
class ReflectEvidenceConfig:
    recent: int = 3
    attested_failures: int = 3
    include_flagged: bool = True
    log_tail_lines: int = 200
    snapshot_diff: bool = True
    git_log: bool = True
    git_log_max: int = 12


@dataclass
class EvidenceGap:
    level: str  # gap | suggest
    kind: str  # metric | artifact | viz | tier | file
    id: str
    detail: str
    exp_dir: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class ReflectEvidenceBundle:
    schema_version: int = 1
    ts: str = ""
    ets: list[dict[str, str]] = field(default_factory=list)
    runs: list[dict[str, Any]] = field(default_factory=list)
    snapshot_diffs: list[dict[str, Any]] = field(default_factory=list)
    git_history: list[dict[str, Any]] = field(default_factory=list)
    tier_evidence: list[str] = field(default_factory=list)
    gaps: list[EvidenceGap] = field(default_factory=list)
    summary_brief: str = ""
    keeper_status: list[str] = field(default_factory=list)
    roadmap_block: str = ""
    audit_card_md: str = ""
    markdown: str = ""

    def gaps_dicts(self) -> list[dict[str, str]]:
        return [g.to_dict() for g in self.gaps]


def load_reflect_evidence_config(repo_root: Path) -> ReflectEvidenceConfig:
    cfg = ReflectEvidenceConfig()
    p = repo_root / "nn-config.yaml"
    if not p.is_file():
        return cfg
    try:
        import yaml

        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        ref = raw.get("reflect") if isinstance(raw.get("reflect"), dict) else {}
        cfg.recent = int(ref.get("evidence_recent", cfg.recent))
        cfg.attested_failures = int(
            ref.get("evidence_attested_failures", cfg.attested_failures)
        )
        cfg.include_flagged = bool(ref.get("evidence_include_flagged", cfg.include_flagged))
        cfg.log_tail_lines = int(ref.get("evidence_log_tail_lines", cfg.log_tail_lines))
        cfg.snapshot_diff = bool(ref.get("evidence_snapshot_diff", cfg.snapshot_diff))
        cfg.git_log = bool(ref.get("evidence_git_log", cfg.git_log))
        cfg.git_log_max = int(ref.get("evidence_git_log_max", cfg.git_log_max))
    except Exception:
        pass
    return cfg


def _focus_scenario_id(repo_root: Path) -> str:
    p = repo_root / "nn-config.yaml"
    if not p.is_file():
        return "default"
    try:
        import yaml

        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        sid = str((raw.get("agent") or {}).get("scenario_default") or "default").strip()
        return sid or "default"
    except Exception:
        return "default"


def _git_is_repo(repo_root: Path) -> bool:
    return (repo_root / ".git").exists()


def _run_git(repo_root: Path, *args: str, timeout: float = 30.0) -> str:
    if not _git_is_repo(repo_root):
        return ""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if proc.returncode != 0:
            return ""
        return proc.stdout.strip()
    except Exception:
        return ""


def _exp_git_commit_map(repo_root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in tsv_rows(repo_root):
        exp_d = str(row.get("exp_dir") or "").strip()
        commit = str(row.get("git_commit") or "").strip()
        if exp_d and commit:
            out[exp_d] = commit
    return out


def _resolve_run_git_commit(exp_dir: Path, tsv_map: dict[str, str]) -> str:
    exp_s = str(exp_dir.resolve())
    if exp_s in tsv_map:
        return tsv_map[exp_s]
    env = _load_json(exp_dir / "env_snapshot.json")
    if env and env.get("git_commit"):
        return str(env["git_commit"]).strip()
    results = _load_json(exp_dir / "results.json")
    if results and results.get("git_commit"):
        return str(results["git_commit"]).strip()
    return ""


def _parse_git_log_lines(raw: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for ln in raw.splitlines():
        m = _GIT_LOG_RE.match(ln.strip())
        if not m:
            continue
        entries.append({"hash": m.group(1), "subject": m.group(2).strip()})
    return entries


def _git_log_at_commit(repo_root: Path, commit: str, max_n: int) -> list[dict[str, str]]:
    fmt = r"%h|%s"
    raw = _run_git(
        repo_root,
        "log",
        f"-{max_n}",
        f"--format={fmt}",
        "--no-decorate",
        commit,
        "--",
        *_GIT_SCOPE_PATHS,
    )
    return _parse_git_log_lines(raw)


def _git_log_range(
    repo_root: Path,
    since: str,
    until: str,
    max_n: int,
) -> list[dict[str, str]]:
    fmt = r"%h|%s"
    raw = _run_git(
        repo_root,
        "log",
        f"-{max_n}",
        f"--format={fmt}",
        "--no-decorate",
        f"{since}..{until}",
        "--",
        *_GIT_SCOPE_PATHS,
    )
    return _parse_git_log_lines(raw)


def _git_diff_name_only(repo_root: Path, since: str, until: str) -> list[str]:
    raw = _run_git(
        repo_root,
        "diff",
        "--name-only",
        since,
        until,
        "--",
        *_GIT_SCOPE_PATHS,
    )
    if not raw:
        return []
    return [ln.strip() for ln in raw.splitlines() if ln.strip()]


def _attach_git_history(
    repo_root: Path,
    runs: list[dict[str, Any]],
    *,
    keeper_commit: str,
    max_n: int,
    tsv_map: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """为各 run 附加 git_commit / git_log；返回 bundle 级 git_history 与 tier 路径提示。"""
    git_history: list[dict[str, Any]] = []
    tier_paths: list[str] = []
    if not _git_is_repo(repo_root):
        return git_history, tier_paths
    tsv_map = tsv_map if tsv_map is not None else _exp_git_commit_map(repo_root)

    for run in runs:
        exp_dir = Path(run["exp_dir"])
        commit = _resolve_run_git_commit(exp_dir, tsv_map)
        if commit:
            run["git_commit"] = commit
        else:
            continue
        role = str(run.get("role") or "")
        if role == "keeper":
            log_entries = _git_log_at_commit(repo_root, commit, max_n)
            run["git_log"] = log_entries
            git_history.append(
                {
                    "role": role,
                    "exp_dir": run.get("rel_exp_dir", run["exp_dir"]),
                    "git_commit": commit,
                    "range": f"at {commit}",
                    "commits": log_entries,
                }
            )
            continue
        if keeper_commit and keeper_commit != commit:
            log_entries = _git_log_range(repo_root, keeper_commit, commit, max_n)
            changed = _git_diff_name_only(repo_root, keeper_commit, commit)
            run["git_log"] = log_entries
            run["git_changed_files"] = changed
            run["git_range"] = f"{keeper_commit}..{commit}"
            tier_paths.extend(changed)
            git_history.append(
                {
                    "role": role,
                    "exp_dir": run.get("rel_exp_dir", run["exp_dir"]),
                    "git_commit": commit,
                    "range": run["git_range"],
                    "commits": log_entries,
                    "changed_files": changed,
                }
            )
        elif keeper_commit == commit:
            run["git_log"] = []
            run["git_note"] = "same commit as keeper"
        else:
            log_entries = _git_log_at_commit(repo_root, commit, max_n)
            run["git_log"] = log_entries
            git_history.append(
                {
                    "role": role,
                    "exp_dir": run.get("rel_exp_dir", run["exp_dir"]),
                    "git_commit": commit,
                    "range": f"at {commit}",
                    "commits": log_entries,
                }
            )
    return git_history, tier_paths


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file() or path.stat().st_size < 2:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _contract_metric_keys(repo_root: Path) -> tuple[str, dict[str, str], dict[str, str], tuple[str, ...]]:
    c = _try_load_contract(repo_root)
    if c is not None:
        mk = getattr(c, "metric_key", metric_key(repo_root))
        mkeys = dict(getattr(c, "metric_keys", {}) or {})
        aux = dict(getattr(c, "auxiliary_keys", {}) or getattr(c, "aux_metrics", {}) or {})
        ledger = tuple(getattr(c, "ledger_context_keys", ()) or ())
        if not mkeys and mk:
            mkeys = {mk: metric_direction(repo_root)}
        return mk, mkeys, aux, ledger
    parsed = _parse_contract_ast(repo_root)
    mk = str(parsed.get("metric_key") or "val_accuracy")
    aux = dict(parsed.get("auxiliary_keys") or {})
    mkeys = {mk: str(parsed.get("metric_direction") or "maximize")}
    return mk, mkeys, aux, ()


def _load_profile_diagnostics(repo_root: Path) -> list[dict[str, Any]]:
    profile = "supervised"
    p = repo_root / "nn-config.yaml"
    if p.is_file():
        try:
            import yaml

            raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            profile = str(raw.get("profile") or profile)
        except Exception:
            pass
    profiles_path = repo_root / "profiles.yaml"
    if not profiles_path.is_file():
        return []
    try:
        import yaml

        data = yaml.safe_load(profiles_path.read_text(encoding="utf-8")) or {}
        block = (data.get("reflect_diagnostics") or {}).get(profile) or {}
        return list(block.get("suggest_when_plateau") or [])
    except Exception:
        return []


def _load_contract_manifest(repo_root: Path) -> list[dict[str, Any]]:
    c = _try_load_contract(repo_root)
    if c is None:
        return []
    fn = getattr(c, "reflect_diagnostic_manifest", None)
    if not callable(fn):
        return []
    try:
        out = fn()
        return list(out) if isinstance(out, list) else []
    except Exception:
        return []


def _snapshot_files(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not root.is_dir():
        return out
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        parts = rel.split("/")
        if any(part in _SNAPSHOT_SKIP or part.endswith(".pyc") for part in parts):
            continue
        if not (rel == "train.py" or rel.startswith("workspace/")):
            continue
        try:
            out[rel] = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
    return out


def _infer_tier_from_paths(paths: list[str]) -> list[str]:
    tiers: list[str] = []
    joined = " ".join(paths).lower()
    if re.search(r"workspace/.*(loss|reward|objective)", joined):
        tiers.append("C")
    if re.search(r"workspace/.*(model|pinn|backbone|arch|net)", joined) or "train.py" in paths:
        if re.search(r"workspace/", joined):
            tiers.append("B")
    if re.search(r"workspace/.*(data|colloc|sampler|curriculum)", joined):
        tiers.append("D")
    if paths == ["train.py"] or (len(paths) == 1 and paths[0] == "train.py"):
        tiers.append("A")
    return sorted(set(tiers))


def diff_code_snapshots(base: Path, target: Path) -> dict[str, Any]:
    base_files = _snapshot_files(base / "code_snapshot")
    tgt_files = _snapshot_files(target / "code_snapshot")
    changed: list[str] = []
    summaries: list[str] = []
    all_keys = sorted(set(base_files) | set(tgt_files))
    for key in all_keys:
        b = base_files.get(key)
        t = tgt_files.get(key)
        if b == t:
            continue
        changed.append(key)
        if b is None:
            summaries.append(f"+ {key} (new)")
        elif t is None:
            summaries.append(f"- {key} (removed)")
        else:
            diff = difflib.unified_diff(
                b.splitlines(keepends=True),
                t.splitlines(keepends=True),
                fromfile=f"keeper/{key}",
                tofile=f"target/{key}",
                n=1,
            )
            chunk = "".join(diff).strip()
            if len(chunk) > 400:
                chunk = chunk[:400] + "\n…"
            summaries.append(f"~ {key}:\n{chunk}")
    tiers = _infer_tier_from_paths(changed)
    return {
        "base": str(base),
        "target": str(target),
        "changed_files": changed,
        "summaries": summaries[:8],
        "tier_hints": tiers,
    }


def _find_log_path(repo_root: Path, exp_dir: Path, train_done: dict[str, Any] | None) -> Path | None:
    if train_done:
        lp = str(train_done.get("log_path") or "").strip()
        if lp:
            p = Path(lp)
            if p.is_file():
                return p
            p2 = repo_root / lp
            if p2.is_file():
                return p2
    logs = repo_root / "_runs" / "logs"
    if not logs.is_dir():
        return None
    stamp = exp_dir.name.split("_")[0] if exp_dir.name else ""
    candidates = sorted(logs.glob("*.log"), key=lambda x: x.stat().st_mtime, reverse=True)
    for c in candidates:
        if stamp and stamp in c.name:
            return c
    return candidates[0] if candidates else None


def _extract_log_signals(path: Path, tail_lines: int) -> list[str]:
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    tail = lines[-tail_lines:] if tail_lines > 0 else lines
    hits: list[str] = []
    for ln in tail:
        if _LOG_SIGNAL_RE.search(ln):
            s = ln.strip()
            if len(s) > 240:
                s = s[:240] + "…"
            hits.append(s)
    return hits[-12:]


def _load_train_dynamics_summary(exp_dir: Path) -> dict[str, Any] | None:
    p = exp_dir / TRAIN_DYNAMICS_JSON
    if not p.is_file() or p.stat().st_size < 2:
        return None
    try:
        dyn = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(dyn, dict):
        return None
    return {
        "n_points": dyn.get("n_points"),
        "primary": dyn.get("primary"),
        "plateau": dyn.get("plateau"),
        "train_loss": dyn.get("train_loss"),
        "train_val_gap": dyn.get("train_val_gap"),
        "anomalies": dyn.get("anomalies"),
        "stop": dyn.get("stop"),
    }


def _collect_run_evidence(
    repo_root: Path,
    exp_dir: Path,
    *,
    role: str,
    log_tail: int,
    required_metrics: dict[str, str],
    required_aux: dict[str, str],
) -> tuple[dict[str, Any], list[EvidenceGap]]:
    gaps: list[EvidenceGap] = []
    exp_s = str(exp_dir)
    rel = exp_dir.relative_to(repo_root).as_posix() if exp_dir.is_relative_to(repo_root) else exp_s
    run: dict[str, Any] = {
        "role": role,
        "exp_dir": exp_s,
        "rel_exp_dir": rel,
        "artifacts": {},
    }
    for name in (
        "config.json",
        "env_snapshot.json",
        "results.json",
        "keep_suggestion.json",
        "train_done.json",
        "train_status.json",
        TRAIN_DYNAMICS_JSON,
        TRAIN_DYNAMICS_MD,
        "metrics_series.tsv",
    ):
        p = exp_dir / name
        present = p.is_file() and p.stat().st_size > 1
        run["artifacts"][name] = present
        if not present and name in ("config.json", "results.json"):
            gaps.append(
                EvidenceGap(
                    level="gap",
                    kind="file",
                    id=name,
                    detail=f"缺少 {name}",
                    exp_dir=rel,
                )
            )
    exc = exp_dir / "train_exception.txt"
    run["artifacts"]["train_exception.txt"] = exc.is_file()
    if exc.is_file():
        try:
            run["train_exception"] = exc.read_text(encoding="utf-8", errors="replace")[:800]
        except Exception:
            pass

    results = _load_json(exp_dir / "results.json")
    if results:
        metrics = results.get("metrics") if isinstance(results.get("metrics"), dict) else {}
        run["metrics"] = metrics
        for key in {**required_metrics, **required_aux}:
            if key not in metrics:
                gaps.append(
                    EvidenceGap(
                        level="gap",
                        kind="metric",
                        id=key,
                        detail=f"results.json 缺 {key}",
                        exp_dir=rel,
                    )
                )
    config = _load_json(exp_dir / "config.json")
    if config:
        run["config_keys"] = sorted(config.keys())[:40]

    train_done = _load_json(exp_dir / "train_done.json")
    if train_done:
        run["train_done"] = {
            k: train_done.get(k)
            for k in (
                "stop_reason",
                "stopped_early",
                "last_completed_epoch",
                "epochs_configured",
                "training_loop_finished",
            )
            if k in train_done
        }

    dyn_summary = _load_train_dynamics_summary(exp_dir)
    series_rows = read_metrics_series_rows(exp_dir)
    if dyn_summary:
        run["train_dynamics"] = dyn_summary
        run["process_evidence_source"] = "train_dynamics"
    elif series_rows:
        run["process_evidence_source"] = "metrics_series"
    else:
        run["process_evidence_source"] = "log"

    if series_rows:
        run["metrics_series_tail"] = summarize_series_tail(series_rows, max_rows=5)
        run["metrics_series_n_rows"] = len(series_rows)
    elif dyn_summary is None:
        gaps.append(
            EvidenceGap(
                level="suggest",
                kind="artifact",
                id="metrics_series",
                detail="无 metrics_series.tsv / train_dynamics（过程分析将依赖 log）",
                exp_dir=rel,
            )
        )

    log_path = _find_log_path(repo_root, exp_dir, train_done)
    if log_path:
        run["log_path"] = str(log_path.relative_to(repo_root)) if log_path.is_relative_to(repo_root) else str(log_path)
        if run.get("process_evidence_source") == "log" or not dyn_summary:
            run["log_signals"] = _extract_log_signals(log_path, log_tail)
    snap = exp_dir / "code_snapshot"
    run["code_snapshot"] = snap.is_dir()
    if not snap.is_dir():
        gaps.append(
            EvidenceGap(
                level="gap",
                kind="artifact",
                id="code_snapshot",
                detail="缺少 code_snapshot/",
                exp_dir=rel,
            )
        )
    return run, gaps


def _build_ets(repo_root: Path, cfg: ReflectEvidenceConfig) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(role: str, exp_dir_s: str, experiment: str = "") -> None:
        if not exp_dir_s or exp_dir_s in seen:
            return
        p = Path(exp_dir_s)
        if not p.is_dir():
            return
        seen.add(exp_dir_s)
        entries.append({"role": role, "exp_dir": exp_dir_s, "experiment": experiment})

    focus = _focus_scenario_id(repo_root)
    keepers = load_keepers(repo_root)
    keeper_entry = keepers.get(focus) or {}
    keeper_dir = str(keeper_entry.get("keeper_exp_dir") or "").strip()
    if keeper_dir:
        add("code_baseline", keeper_dir, str(keeper_entry.get("experiment") or ""))

    try:
        from lib.ledger_anchor import metric_leader_row  # noqa: WPS433

        leader = metric_leader_row(repo_root, focus)
        if leader:
            add("metric_leader", leader.exp_dir, leader.experiment)
    except ImportError:
        pass

    data_rows = [
        r for r in tsv_rows(repo_root) if r.get("experiment") != "preflight_check"
    ]
    for row in data_rows[-cfg.recent :]:
        add("recent", str(row.get("exp_dir") or "").strip(), str(row.get("experiment") or ""))

    if cfg.include_flagged:
        status = round_decision_status(repo_root)
        if status == "DISCARD" and data_rows:
            last = data_rows[-1]
            add("flagged", str(last.get("exp_dir") or "").strip(), str(last.get("experiment") or ""))
        for row in data_rows[-cfg.recent :]:
            exp_d = str(row.get("exp_dir") or "").strip()
            if not exp_d:
                continue
            p = Path(exp_d)
            if (p / "train_exception.txt").is_file():
                add("flagged", exp_d, str(row.get("experiment") or ""))
            td = _load_json(p / "train_done.json")
            if td and str(td.get("stop_reason") or "").lower() in ("error", "failed", "exception"):
                add("flagged", exp_d, str(row.get("experiment") or ""))
        if keeper_dir and data_rows:
            mk = metric_key(repo_root)
            direction = metric_direction(repo_root)
            try:
                kv = float(keeper_entry.get("best_metric_value") or data_rows[-1].get(mk, "nan"))
            except ValueError:
                kv = None
            try:
                lv = float(data_rows[-1].get(mk, "nan"))
            except ValueError:
                lv = None
            if kv is not None and lv == lv:
                bad = (direction == "maximize" and lv < kv * 0.95) or (
                    direction == "minimize" and lv > kv * 1.05
                )
                if bad:
                    add("flagged", str(data_rows[-1].get("exp_dir") or "").strip(), str(data_rows[-1].get("experiment") or ""))

    return entries


def _glob_matches(repo_root: Path, pattern: str) -> list[str]:
    pat = pattern.strip()
    if not pat:
        return []
    hits: list[str] = []
    if pat.startswith("_runs/exp/"):
        for p in repo_root.glob(pat):
            if p.is_file():
                hits.append(p.relative_to(repo_root).as_posix())
    else:
        for p in repo_root.glob(pat):
            if p.is_file():
                hits.append(p.relative_to(repo_root).as_posix())
    return hits


def build_reflect_evidence(repo_root: Path) -> ReflectEvidenceBundle:
    root = repo_root.resolve()
    cfg = load_reflect_evidence_config(root)
    mk, mkeys, aux, _ledger = _contract_metric_keys(root)
    plateau_n, _interval = agent_config(root)
    ps = plateau_streak(root, plateau_n, mk)
    is_plateau = ps >= plateau_n

    bundle = ReflectEvidenceBundle(
        ts=datetime.now(timezone.utc).isoformat(),
    )
    bundle.summary_brief = format_brief(build_summary(root), repo_root=root)
    try:
        bundle.keeper_status = format_keeper_status(root)
    except Exception:
        bundle.keeper_status = []
    rs = roadmap_status(root)
    if rs.roadmap != "empty":
        bundle.roadmap_block = format_roadmap_status(rs)

    bundle.ets = _build_ets(root, cfg)
    all_gaps: list[EvidenceGap] = []

    for ent in bundle.ets:
        exp_dir = Path(ent["exp_dir"])
        run_ev, gaps = _collect_run_evidence(
            root,
            exp_dir,
            role=ent["role"],
            log_tail=cfg.log_tail_lines,
            required_metrics=mkeys,
            required_aux=aux,
        )
        bundle.runs.append(run_ev)
        all_gaps.extend(gaps)

    keeper_commit = ""
    tsv_git = _exp_git_commit_map(root)
    if cfg.git_log:
        for run in bundle.runs:
            if run.get("role") in ("keeper", "code_baseline") and run.get("exp_dir"):
                keeper_commit = _resolve_run_git_commit(Path(run["exp_dir"]), tsv_git)
                break
        git_hist, git_tier_paths = _attach_git_history(
            root,
            bundle.runs,
            keeper_commit=keeper_commit,
            max_n=cfg.git_log_max,
            tsv_map=tsv_git,
        )
        bundle.git_history = git_hist
        for t in _infer_tier_from_paths(git_tier_paths):
            if t not in bundle.tier_evidence:
                bundle.tier_evidence.append(t)

    keeper_path = next(
        (e["exp_dir"] for e in bundle.ets if e["role"] in ("keeper", "code_baseline")),
        "",
    )
    if cfg.snapshot_diff and keeper_path:
        base = Path(keeper_path)
        for ent in bundle.ets:
            if ent["role"] in ("keeper", "code_baseline"):
                continue
            target = Path(ent["exp_dir"])
            if not target.is_dir():
                continue
            diff = diff_code_snapshots(base, target)
            if diff["changed_files"]:
                bundle.snapshot_diffs.append(diff)
                for t in diff.get("tier_hints") or []:
                    if t not in bundle.tier_evidence:
                        bundle.tier_evidence.append(t)

    for item in _load_profile_diagnostics(root):
        if not is_plateau:
            continue
        kind = str(item.get("kind") or "viz")
        item_id = str(item.get("id") or "?")
        desc = str(item.get("desc") or item_id)
        glob_pat = str(item.get("glob") or "")
        matched = _glob_matches(root, glob_pat) if glob_pat else []
        if not matched:
            all_gaps.append(
                EvidenceGap(
                    level="suggest",
                    kind=kind,
                    id=item_id,
                    detail=f"plateau 建议具备：{desc}",
                )
            )

    for item in _load_contract_manifest(root):
        item_id = str(item.get("id") or "?")
        glob_pat = str(item.get("glob") or "")
        plateau_only = bool(item.get("plateau_only", True))
        if plateau_only and not is_plateau:
            continue
        matched = _glob_matches(root, glob_pat) if glob_pat else []
        if not matched:
            all_gaps.append(
                EvidenceGap(
                    level="suggest" if not item.get("required") else "gap",
                    kind=str(item.get("kind") or "artifact"),
                    id=item_id,
                    detail=f"manifest 未匹配 glob: {glob_pat or item_id}",
                )
            )

    # 去重 gaps
    seen_gap: set[tuple[str, str, str, str]] = set()
    deduped: list[EvidenceGap] = []
    for g in all_gaps:
        key = (g.level, g.kind, g.id, g.exp_dir)
        if key in seen_gap:
            continue
        seen_gap.add(key)
        deduped.append(g)
    bundle.gaps = deduped

    try:
        from lib.audit_core import format_audit_card_body, injection_for_scenario
        from lib.scenario_inventory import focus_scenario_id

        sid = (focus_scenario_id(root) or "").strip()
        inj = injection_for_scenario(root, sid) if sid else None
        if inj:
            bundle.audit_card_md = format_audit_card_body(root, inj)
    except Exception:
        bundle.audit_card_md = ""

    if is_plateau:
        recent_has_series = any(
            r.get("metrics_series_n_rows", 0) for r in bundle.runs if r.get("role") in ("recent", "flagged")
        )
        if not recent_has_series:
            bundle.gaps.append(
                EvidenceGap(
                    level="suggest",
                    kind="artifact",
                    id="metrics_series",
                    detail="plateau 且无 metrics_series — 建议接 record_* hook",
                )
            )

    bundle.markdown = format_evidence_markdown(bundle, max_chars=12000)
    return bundle


def enrich_reb_after_tam(
    repo_root: Path,
    bundle: ReflectEvidenceBundle,
    tam_result: Any,
    *,
    cfg: ReflectEvidenceConfig | None = None,
) -> ReflectEvidenceBundle:
    """Phase 0.5b：TAM 完成后补 attested_failure 进 ETS 并刷新 git/snapshot/md。"""
    root = repo_root.resolve()
    cfg = cfg or load_reflect_evidence_config(root)
    mk, mkeys, aux, _ledger = _contract_metric_keys(root)
    seen = {e["exp_dir"] for e in bundle.ets}
    existing_runs = {str(Path(r["exp_dir"]).resolve()) for r in bundle.runs if r.get("exp_dir")}
    candidates: list[dict[str, Any]] = []
    for row in tam_result.rows or []:
        verdict = str(row.get("verdict") or "")
        outcome = row.get("outcome") or {}
        if outcome.get("keep_decision") != "DISCARD":
            continue
        if verdict not in ("attested", "shallow", "false_claim"):
            continue
        exp_d = str(row.get("exp_dir") or "").strip()
        if not exp_d or exp_d in seen:
            continue
        candidates.append(row)
    added = 0
    for row in reversed(candidates):
        if added >= cfg.attested_failures:
            break
        exp_d = str(row.get("exp_dir") or "").strip()
        if not exp_d or exp_d in seen:
            continue
        seen.add(exp_d)
        bundle.ets.append(
            {
                "role": "attested_failure",
                "exp_dir": exp_d,
                "experiment": str(row.get("experiment") or "?"),
            }
        )
        run_ev, gaps = _collect_run_evidence(
            root,
            Path(exp_d),
            role="attested_failure",
            log_tail=cfg.log_tail_lines,
            required_metrics=mkeys,
            required_aux=aux,
        )
        bundle.runs.append(run_ev)
        bundle.gaps.extend(gaps)
        added += 1

    if added == 0:
        return bundle

    keeper_commit = ""
    tsv_git = _exp_git_commit_map(root)
    if cfg.git_log:
        for run in bundle.runs:
            if run.get("role") in ("keeper", "code_baseline") and run.get("exp_dir"):
                keeper_commit = _resolve_run_git_commit(Path(run["exp_dir"]), tsv_git)
                break
        git_hist, git_tier_paths = _attach_git_history(
            root,
            bundle.runs,
            keeper_commit=keeper_commit,
            max_n=cfg.git_log_max,
            tsv_map=tsv_git,
        )
        bundle.git_history = git_hist
        for t in _infer_tier_from_paths(git_tier_paths):
            if t not in bundle.tier_evidence:
                bundle.tier_evidence.append(t)

    keeper_path = next(
        (e["exp_dir"] for e in bundle.ets if e["role"] in ("keeper", "code_baseline")),
        "",
    )
    if cfg.snapshot_diff and keeper_path:
        base = Path(keeper_path)
        bundle.snapshot_diffs = []
        for ent in bundle.ets:
            if ent["role"] in ("keeper", "code_baseline"):
                continue
            target = Path(ent["exp_dir"])
            if not target.is_dir():
                continue
            diff = diff_code_snapshots(base, target)
            if diff["changed_files"]:
                bundle.snapshot_diffs.append(diff)
                for t in diff.get("tier_hints") or []:
                    if t not in bundle.tier_evidence:
                        bundle.tier_evidence.append(t)

    seen_gap: set[tuple[str, str, str, str]] = set()
    deduped: list[EvidenceGap] = []
    for g in bundle.gaps:
        key = (g.level, g.kind, g.id, g.exp_dir)
        if key in seen_gap:
            continue
        seen_gap.add(key)
        deduped.append(g)
    bundle.gaps = deduped
    bundle.markdown = format_evidence_markdown(bundle, max_chars=12000)
    return bundle


def format_evidence_markdown(bundle: ReflectEvidenceBundle, *, max_chars: int = 12000) -> str:
    lines = [
        "## Reflect 证据包（REB）",
        "",
        "### 台账摘要",
        bundle.summary_brief,
        "",
    ]
    if bundle.keeper_status:
        lines.append("### Keeper 状态")
        lines.extend(bundle.keeper_status[:20])
        lines.append("")
    if bundle.roadmap_block.strip():
        lines.append("### 路线图")
        lines.append(bundle.roadmap_block.strip())
        lines.append("")
    lines.append("### ETS 目标")
    for e in bundle.ets:
        lines.append(f"- [{e['role']}] {e.get('experiment') or '?'} → `{e['exp_dir']}`")
    lines.append("")
    for run in bundle.runs:
        lines.append(f"#### Run ({run['role']}) `{run.get('rel_exp_dir', run['exp_dir'])}`")
        arts = run.get("artifacts") or {}
        missing = [k for k, v in arts.items() if not v]
        lines.append(f"- artifacts ok: {', '.join(k for k, v in arts.items() if v) or '（无）'}")
        if missing:
            lines.append(f"- missing: {', '.join(missing)}")
        if run.get("metrics"):
            lines.append(f"- metrics: {run['metrics']}")
        if run.get("train_done"):
            lines.append(f"- train_done: {run['train_done']}")
        if run.get("train_dynamics"):
            lines.append(f"- train_dynamics: {run['train_dynamics']}")
        if run.get("metrics_series_tail"):
            lines.append(f"- metrics_series_tail (n={run.get('metrics_series_n_rows', '?')}):")
            for row in run["metrics_series_tail"]:
                step = row.get("step", "?")
                kind = row.get("step_kind", "")
                tl = row.get("train_loss", "")
                lines.append(f"  - step={step} kind={kind} train_loss={tl}")
        if run.get("process_evidence_source"):
            lines.append(f"- process_evidence_source: {run['process_evidence_source']}")
        if run.get("git_commit"):
            lines.append(f"- git_commit: `{run['git_commit']}`")
        if run.get("git_range"):
            lines.append(f"- git_range: `{run['git_range']}`")
        if run.get("git_changed_files"):
            lines.append(f"- git_changed: {run['git_changed_files'][:12]}")
        if run.get("git_log"):
            lines.append("- git_log (train.py/workspace):")
            for ent in run["git_log"][:8]:
                if isinstance(ent, dict):
                    lines.append(f"  - {ent.get('hash', '?')} {ent.get('subject', '')}")
                else:
                    lines.append(f"  - {ent}")
        elif run.get("git_note"):
            lines.append(f"- git: {run['git_note']}")
        if run.get("log_signals"):
            lines.append("- log_signals:")
            for s in run["log_signals"]:
                lines.append(f"  - {s}")
        lines.append("")
    if bundle.snapshot_diffs:
        lines.append("### Snapshot diff（vs code_baseline）")
        for d in bundle.snapshot_diffs[:5]:
            lines.append(
                f"- {Path(d['target']).name}: changed={d['changed_files']} tier_hints={d.get('tier_hints')}"
            )
            for s in d.get("summaries") or []:
                lines.append(f"  ```\n  {s}\n  ```")
        if bundle.tier_evidence:
            lines.append(f"- tier_evidence: {', '.join(bundle.tier_evidence)}")
        lines.append("")
    if bundle.git_history:
        lines.append("### Git 更新（code_baseline → run，train.py/workspace）")
        for gh in bundle.git_history[:6]:
            commits = gh.get("commits") or []
            commit_lines = [
                f"{c.get('hash', '?')} {c.get('subject', '')}"
                for c in commits[:6]
                if isinstance(c, dict)
            ]
            lines.append(
                f"- [{gh.get('role')}] `{gh.get('exp_dir')}` "
                f"commit={gh.get('git_commit')} range={gh.get('range')}"
            )
            for cl in commit_lines:
                lines.append(f"  - {cl}")
            changed = gh.get("changed_files") or []
            if changed:
                lines.append(f"  - files: {changed[:10]}")
        lines.append("")
    if bundle.gaps:
        lines.append("### 证据缺口")
        for g in bundle.gaps[:20]:
            lines.append(f"- [{g.level}:{g.kind}] {g.id}: {g.detail}" + (f" ({g.exp_dir})" if g.exp_dir else ""))
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[: max_chars - 20] + "\n\n…(truncated)"
    if bundle.audit_card_md:
        text = text + "\n\n## audit-card\n" + bundle.audit_card_md
    return text


def format_gaps_experience_block(gaps: list[EvidenceGap]) -> str:
    if not gaps:
        return ""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"## 证据缺口 {ts}", ""]
    for g in gaps[:15]:
        suffix = f" (`{g.exp_dir}`)" if g.exp_dir else ""
        lines.append(f"- **[{g.level}:{g.kind}]** `{g.id}` — {g.detail}{suffix}")
    return "\n".join(lines)


def write_reflect_evidence_artifacts(
    repo_root: Path,
    bundle: ReflectEvidenceBundle,
    *,
    reflect_id: str = "",
) -> None:
    saved = repo_root / "saved"
    saved.mkdir(exist_ok=True)
    evidence_path = saved / "reflect_evidence.json"
    payload = {
        "schema_version": bundle.schema_version,
        "ts": bundle.ts,
        "reflect_id": reflect_id,
        "ets": bundle.ets,
        "runs": bundle.runs,
        "snapshot_diffs": bundle.snapshot_diffs,
        "git_history": bundle.git_history,
        "tier_evidence": bundle.tier_evidence,
        "gaps": bundle.gaps_dicts(),
        "summary_brief": bundle.summary_brief,
    }
    evidence_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    gaps_path = saved / "reflect_evidence_gaps.json"
    gaps_payload = {
        "schema_version": 1,
        "reflect_id": reflect_id,
        "ts": bundle.ts,
        "gaps": bundle.gaps_dicts(),
    }
    gaps_path.write_text(json.dumps(gaps_payload, ensure_ascii=False, indent=2), encoding="utf-8")
