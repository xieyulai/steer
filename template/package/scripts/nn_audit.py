#!/usr/bin/env python3
"""审查编排：选对象 → 判定 → 不入账复现/多种子/消融 → 写卡片。

不调用 finalize-round，不改 keepers.json / 成绩表表头。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import time
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lib.audit_attest import AttestResult, attest_candidate  # noqa: E402
from lib.audit_core import (  # noqa: E402
    AuditTarget,
    ablation_config,
    ablation_drop_exceeds,
    extra_seeds,
    load_index,
    pick_target,
    primary_from_results,
    repro_tolerance,
    resolve_fingerprint_baseline,
    write_index_entry,
)

ArmRunner = Callable[..., Path]


def train_env(base: dict | None = None) -> dict:
    """NN_SKIP_WRITE_KEEPER=1, NN_AUTO_FINALIZE_ROUND=0, 强制 NN_PARALLEL_TOTAL=1。"""
    env = dict(os.environ)
    if base:
        env.update({str(k): str(v) for k, v in base.items()})
    env["NN_SKIP_WRITE_KEEPER"] = "1"
    env["NN_AUTO_FINALIZE_ROUND"] = "0"
    env["NN_PARALLEL_TOTAL"] = "1"
    env["NN_SLOT"] = "0"
    return env


def build_train_argv(config_path: Path, experiment: str) -> list[str]:
    name = str(experiment)
    if not name.startswith("audit_"):
        name = "audit_" + name
    return [
        "poetry", "run", "python", "train.py",
        "--config", str(config_path),
        "--experiment", name,
        "--no-auto-finalize-round",
    ]


def _dump(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if is_dataclass(obj) and not isinstance(obj, type):
        obj = asdict(obj)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _load_json(path: Path) -> dict:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _rel(repo_root: Path, p: Path | str) -> str:
    root = Path(repo_root).resolve()
    path = Path(p)
    if not path.is_absolute():
        path = root / path
    try:
        return str(path.resolve().relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")


def _target_dir(repo_root: Path, target: AuditTarget) -> Path:
    p = Path(target.audited_exp_dir)
    if not p.is_absolute():
        p = Path(repo_root) / p
    return p.resolve()


def _near_best_abs(repo_root: Path) -> float:
    cfg_path = Path(repo_root) / "nn-config.yaml"
    if not cfg_path.is_file():
        return 0.0
    try:
        import yaml

        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        keep = (raw.get("keep") or {}) if isinstance(raw, dict) else {}
        return float(keep.get("near_best_abs") or 0.0)
    except Exception:
        return 0.0


def _primary_from_exp(exp_dir: Path, metric_key: str = "") -> float:
    data = _load_json(Path(exp_dir) / "results.json")
    try:
        return primary_from_results(data, metric_key)
    except ValueError as exc:
        raise ValueError(f"results.json 缺少主分: {exp_dir}") from exc


def _mean_std(vals: list[float]) -> tuple[float, float]:
    if not vals:
        return 0.0, 0.0
    mean = float(statistics.fmean(vals))
    std = float(statistics.stdev(vals)) if len(vals) >= 2 else 0.0
    return mean, std


def _is_ablate(arm: dict) -> bool:
    return "ablate" in str(arm.get("kind", "")).lower() or "ablate" in str(
        arm.get("experiment", "")
    ).lower()


def _safe_token(s: str) -> str:
    out = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(s)).strip("._")
    return out or "x"


def _with_seed(cfg: dict, seed: int) -> dict:
    out = deepcopy(cfg)
    out["SEED"] = int(seed)
    if "seed" in out:
        out["seed"] = int(seed)
    return out


def _search_claimed_depth(repo_root: Path) -> str:
    p = Path(repo_root) / "EXPERIENCE.md"
    if not p.is_file():
        return ""
    try:
        text = p.read_text(encoding="utf-8")
    except Exception:
        return ""
    m = re.search(r"innovation_depth:\s*(\w+)", text, re.I)
    return m.group(1).strip().lower() if m else ""


def _reference_multiseed(repo_root: Path, scenario_id: str) -> str:
    try:
        from lib.run_ledger_summary import tsv_rows

        n = 0
        for row in tsv_rows(Path(repo_root)):
            if str(row.get("scenario_id", "")).strip() != scenario_id:
                continue
            if str(row.get("baseline_tag", "")).strip().lower() == "reference":
                n += 1
        return "missing" if n < 2 else "present"
    except Exception:
        return "missing"


def _fetch_paper_verdict(repo_root: Path) -> str:
    """可选联网。任何失败 → inconclusive。测试不得走这条路径。"""
    try:
        from lib.external.config import load_external_config
        from lib.external.executor import execute_plan
        from lib.external.router import RouterContext, build_external_plan

        cfg = None
        try:
            cfg = load_external_config(Path(repo_root))
        except Exception:
            cfg = None
        ctx = RouterContext(
            tier="B",
            innovation_depth="different",
            gate="manual:audit",
            beat_best=False,
            routine_mislabel=False,
            not_attested_extend=False,
            reflect_skipped=False,
            config=cfg,
        )
        plan = build_external_plan(ctx)
        try:
            plan.paper_depth = "P3"
        except Exception:
            pass
        bundle = execute_plan(plan, dry_run=False, repo_root=Path(repo_root))
        verdict = (((bundle or {}).get("code") or {}).get("routine_attestation") or {}).get(
            "verdict"
        )
        return str(verdict) if verdict else "inconclusive"
    except Exception:
        return "inconclusive"


def _resolve_verdict(
    repo_root: Path,
    *,
    fetch_external: bool = False,
    paper_verdict: str | None = None,
    dry_run_external: bool = False,
) -> str:
    if paper_verdict is not None:
        return str(paper_verdict)
    if dry_run_external or not fetch_external:
        return "inconclusive"
    try:
        return _fetch_paper_verdict(repo_root)
    except Exception:
        return "inconclusive"


def _stderr_tail(text: str | None, *, limit: int = 2000) -> str:
    return (text or "")[-limit:]


def _maybe_write_arm_stderr(card_dir: Path | None, name: str, snippet: str) -> None:
    if card_dir is None or not snippet:
        return
    try:
        logp = Path(card_dir) / "logs" / f"{name}.stderr.txt"
        logp.parent.mkdir(parents=True, exist_ok=True)
        logp.write_text(snippet, encoding="utf-8")
    except OSError:
        pass


def run_arm(
    repo_root: Path,
    config_path: Path,
    experiment: str,
    *,
    runner: ArmRunner | None = None,
    card_dir: Path | None = None,
) -> Path:
    """跑一条审查臂，返回新 exp_dir。成功路径禁止 finalize-round。"""
    root = Path(repo_root).resolve()
    cfg_path = Path(config_path)
    name = str(experiment)
    if not name.startswith("audit_"):
        name = "audit_" + name
    if runner is not None:
        return Path(runner(root, cfg_path, name))
    argv = build_train_argv(cfg_path, name)
    env = train_env()
    t0 = time.time()
    proc = subprocess.run(
        argv, env=env, cwd=str(root), capture_output=True, text=True,
    )
    if proc.returncode != 0:
        stderr_tail = _stderr_tail(proc.stderr)
        _maybe_write_arm_stderr(card_dir, name, stderr_tail)
        raise RuntimeError(
            f"审查臂失败 experiment={name} rc={proc.returncode}\n{stderr_tail}"
        )
    blob = f"{proc.stderr or ''}\n{proc.stdout or ''}"
    m = re.search(r"exp_dir=(\S+)", blob)
    if m:
        p = Path(m.group(1).strip().strip("\"'"))
        if not p.is_absolute():
            p = root / p
        if p.is_dir():
            return p
    exp_root = root / "_runs" / "exp"
    if exp_root.is_dir():
        cands = [
            d for d in exp_root.iterdir()
            if d.is_dir()
            and (d.name == name or d.name.endswith("_" + name))
            and d.stat().st_mtime >= t0
        ]
        if cands:
            return max(cands, key=lambda d: d.stat().st_mtime)
    raise RuntimeError(
        f"审查臂未找到 exp_dir experiment={name} rc={proc.returncode}"
    )


def _make_card_dir(repo_root: Path, scenario_id: str) -> Path:
    sid = _safe_token(scenario_id)
    root = Path(repo_root).resolve() / "saved" / "audit"
    root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    path = root / f"{ts}_{sid}"
    if path.exists():
        for i in range(1, 1000):
            cand = root / f"{ts}_{sid}_{i}"
            if not cand.exists():
                path = cand
                break
    path.mkdir(parents=True, exist_ok=True)
    return path


def _full_scores(arms: list[dict]) -> list[float]:
    out: list[float] = []
    for a in arms:
        if _is_ablate(a):
            continue
        if a.get("primary") is None:
            continue
        try:
            out.append(float(a["primary"]))
        except (TypeError, ValueError):
            continue
    return out


def _ablate_scores(arms: list[dict]) -> list[float]:
    out: list[float] = []
    for a in arms:
        if not _is_ablate(a):
            continue
        if a.get("primary") is None:
            continue
        try:
            out.append(float(a["primary"]))
        except (TypeError, ValueError):
            continue
    return out


def _ablation_note(
    target: AuditTarget,
    attest: AttestResult,
    arms: list[dict],
    *,
    repro_ok: bool,
    ablation_ran: bool,
) -> str:
    if ablation_ran:
        full_vals = _full_scores(arms)
        ab_vals = _ablate_scores(arms)
        full_mean, full_std = _mean_std(full_vals)
        ab_mean, ab_std = _mean_std(ab_vals)
        if target.metric_direction == "minimize":
            drop = ab_mean - full_mean
        else:
            drop = full_mean - ab_mean
        gate = ablation_drop_exceeds(
            full_mean, full_std, len(full_vals),
            ab_mean, ab_std, len(ab_vals),
            target.metric_direction,
        )
        if gate is None:
            return f"均值差 {drop:.6g}；样本不足未判门槛"
        if gate:
            return f"下降超过门槛（均值差 {drop:.6g}）"
        return f"下降未过门槛（均值差 {drop:.6g}）"
    if not repro_ok:
        return "复现失败未做消融"
    if attest.ablation_skip_reason:
        return str(attest.ablation_skip_reason)
    return "未做消融"


def _render_card_md(
    target: AuditTarget,
    attest: AttestResult,
    *,
    repro_ok: bool,
    n_seeds: int,
    mean: float,
    std: float,
    ablation_ran: bool,
    note: str,
) -> str:
    repro_txt = "对上" if repro_ok else "没对上"
    keys = ",".join(attest.ablation_keys) if attest.ablation_keys else "无"
    ran = "是" if ablation_ran else "否"
    claimed = attest.search_claimed_depth or "（未记录）"
    if attest.attested_depth == "skipped":
        novelty_line = "新不新：对象是公开对照，已跳过新不新"
    else:
        novelty_line = f"新不新：搜索时声称 {claimed}；本次审查 {attest.attested_depth}"
    return (
        "# 审查卡片\n"
        f"审的是：场景 {target.scenario_id}，实验目录 {target.audited_exp_dir}\n"
        f"复现：{repro_txt}\n"
        f"多种子：n={n_seeds} 均值 {mean} 标准差 {std}\n"
        f"{novelty_line}\n"
        f"消融：计划 {keys}；已跑 {ran}；{note}\n"
        "人还没决定留下、搁置还是驳回。\n"
    )


def write_card(
    repo_root,
    target: AuditTarget,
    attest: AttestResult,
    arms: list[dict],
    *,
    status: str,
    card_dir: Path | None = None,
) -> Path:
    """写 card.md+json+attest.json+arms.json，并 write_index_entry。不改 keepers/TSV。"""
    root = Path(repo_root).resolve()
    if card_dir is None:
        card_dir = _make_card_dir(root, target.scenario_id)
    else:
        card_dir = Path(card_dir)
        card_dir.mkdir(parents=True, exist_ok=True)

    ablation_ran = any(_is_ablate(a) for a in arms)
    full_vals = _full_scores(arms)
    mean, std = _mean_std(full_vals)
    n_seeds = len(full_vals)

    if status == "repro_failed":
        repro_ok = False
    else:
        repro_ok = False
        for a in arms:
            if _is_ablate(a):
                continue
            kind = str(a.get("kind", ""))
            exp = str(a.get("experiment", ""))
            if kind == "repro" or exp.startswith("audit_repro"):
                try:
                    score = float(a["primary"])
                except (TypeError, ValueError, KeyError):
                    score = None
                if score is not None:
                    tol = repro_tolerance(target.original_primary, _near_best_abs(root))
                    repro_ok = abs(score - float(target.original_primary)) <= tol
                break
        else:
            if full_vals and status == "complete":
                tol = repro_tolerance(target.original_primary, _near_best_abs(root))
                repro_ok = abs(full_vals[0] - float(target.original_primary)) <= tol

    note = _ablation_note(
        target, attest, arms, repro_ok=repro_ok, ablation_ran=ablation_ran,
    )
    card = {
        "schema_version": 1,
        "scenario_id": target.scenario_id,
        "audited_exp_dir": target.audited_exp_dir,
        "config_sha256": target.config_sha256,
        "repro_ok": bool(repro_ok),
        "n_seeds": n_seeds,
        "primary_mean": mean,
        "primary_std": std,
        "attested_depth": attest.attested_depth,
        "search_claimed_depth": attest.search_claimed_depth,
        "ablation_planned": bool(attest.ablation_planned),
        "ablation_ran": bool(ablation_ran),
        "human_decision": "",
        "status": status,
        "reference_multiseed": _reference_multiseed(root, target.scenario_id),
        "ablation_note": note,
    }
    md = _render_card_md(
        target, attest,
        repro_ok=repro_ok, n_seeds=n_seeds, mean=mean, std=std,
        ablation_ran=ablation_ran, note=note,
    )
    (card_dir / "card.md").write_text(md, encoding="utf-8")
    _dump(card_dir / "card.json", card)
    _dump(card_dir / "attest.json", attest)
    _dump(card_dir / "arms.json", arms)
    write_index_entry(
        root,
        scenario_id=target.scenario_id,
        card_dir=str(card_dir),
        audited_exp_dir=target.audited_exp_dir,
        config_sha256=target.config_sha256,
    )
    return card_dir


def _target_baseline_tag(repo_root: Path, target: AuditTarget) -> str:
    tdir = _target_dir(repo_root, target)
    cfgp = tdir / "config.json"
    if cfgp.is_file():
        tag = str(_load_json(cfgp).get("baseline_tag") or "").strip().lower()
        if tag in ("plain", "reference", "none"):
            return tag
    from lib.run_ledger_summary import tsv_rows

    for row in tsv_rows(Path(repo_root)):
        exp = str(row.get("exp_dir") or "").strip()
        if not exp:
            continue
        if not _audit_paths_match_local(exp, target.audited_exp_dir):
            continue
        return str(row.get("baseline_tag") or "").strip().lower()
    return ""


def _audit_paths_match_local(a: str, b: str) -> bool:
    from lib.audit_core import _audit_paths_match

    return _audit_paths_match(a, b)


def _skipped_reference_attest(*, baseline_kind: str) -> AttestResult:
    return AttestResult(
        fp_depth="",
        attested_depth="skipped",
        search_claimed_depth="",
        paper_verdict="skipped",
        baseline_kind=baseline_kind or "plain",
        primary_keys_changed={},
        ablation_keys=[],
        ablation_planned=False,
        ablation_skip_reason="对象是公开对照，已跳过新不新",
        fingerprint={},
    )


def _load_baseline_cfg(repo_root: Path, scenario_id: str) -> dict:
    base_path, _kind = resolve_fingerprint_baseline(Path(repo_root), scenario_id)
    if base_path is None:
        return {}
    p = Path(base_path)
    if not p.is_absolute():
        p = Path(repo_root) / p
    cfgp = p / "config.json"
    if not cfgp.is_file():
        return {}
    return _load_json(cfgp)


def _arm_record(
    *,
    kind: str,
    experiment: str,
    seed: int,
    primary: float | None,
    exp_dir: Path | str,
    repo_root: Path,
    key: str = "",
) -> dict:
    rec: dict[str, Any] = {
        "kind": kind,
        "experiment": experiment,
        "seed": int(seed),
        "primary": primary,
        "exp_dir": _rel(repo_root, exp_dir),
    }
    if key:
        rec["key"] = key
    return rec


def pipeline(
    repo_root: Path,
    *,
    exp_dir: str | None = None,
    scenario_id: str | None = None,
    n_seeds: int = 5,
    skip_train: bool = False,
    fetch_external: bool = False,
    dry_run_external: bool = False,
    paper_verdict: str | None = None,
    runner: ArmRunner | None = None,
) -> Path:
    """固定顺序：pick → attest → repro → extra seeds → ablation → 写卡。"""
    root = Path(repo_root).resolve()
    target: AuditTarget | None = None
    attest: AttestResult | None = None
    card_dir: Path | None = None
    arms: list[dict] = []
    orig_cfg: dict = {}

    def _flush(status: str) -> Path:
        if target is None:
            raise RuntimeError("审查尚未选出对象，无法写卡")
        cd = card_dir or _make_card_dir(root, target.scenario_id)
        att = attest or AttestResult(
            fp_depth="",
            attested_depth="",
            search_claimed_depth="",
            paper_verdict="inconclusive",
            baseline_kind="none",
            primary_keys_changed={},
            ablation_keys=[],
            ablation_planned=False,
            ablation_skip_reason="",
            fingerprint={},
        )
        return write_card(root, target, att, arms, status=status, card_dir=cd)

    try:
        target = pick_target(root, exp_dir=exp_dir, scenario_id=scenario_id)
        card_dir = _make_card_dir(root, target.scenario_id)
        skip_novelty = _target_baseline_tag(root, target) == "reference"
        if skip_novelty:
            _, bk = resolve_fingerprint_baseline(
                root, target.scenario_id, exclude_exp_dir=target.audited_exp_dir,
            )
            attest = _skipped_reference_attest(baseline_kind=bk)
        else:
            verdict = _resolve_verdict(
                root,
                fetch_external=fetch_external,
                paper_verdict=paper_verdict,
                dry_run_external=dry_run_external,
            )
            claimed = _search_claimed_depth(root)
            attest = attest_candidate(
                root, target, search_claimed_depth=claimed, paper_verdict=verdict,
            )
        _dump(card_dir / "attest.json", attest)

        tdir = _target_dir(root, target)
        orig_cfg = _load_json(tdir / "config.json") if (tdir / "config.json").is_file() else {}

        if skip_train:
            arms.append(_arm_record(
                kind="repro",
                experiment="audit_repro_skip",
                seed=target.original_seed,
                primary=target.original_primary,
                exp_dir=target.audited_exp_dir,
                repo_root=root,
            ))
            return _flush("complete")

        cfg_dir = card_dir / "configs"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        short = (target.config_sha256 or "x")[:8]
        repro_name = f"audit_repro_{short}"
        repro_cfg = cfg_dir / f"{repro_name}.json"
        _dump(repro_cfg, orig_cfg)
        repro_ok = False
        repro_score: float | None = None
        repro_exp: Path | str = ""
        try:
            repro_exp = run_arm(
                root, repro_cfg, repro_name, runner=runner, card_dir=card_dir,
            )
            repro_score = _primary_from_exp(Path(repro_exp), target.metric_key)
            tol = repro_tolerance(target.original_primary, _near_best_abs(root))
            repro_ok = abs(float(repro_score) - float(target.original_primary)) <= tol
        except KeyboardInterrupt:
            raise
        except Exception:
            repro_ok = False
        arms.append(_arm_record(
            kind="repro",
            experiment=repro_name,
            seed=target.original_seed,
            primary=repro_score,
            exp_dir=repro_exp or tdir,
            repo_root=root,
        ))
        if not repro_ok:
            return _flush("repro_failed")

        try:
            seeds = extra_seeds(target.original_seed, int(n_seeds) if n_seeds else 5)
            for seed in seeds[1:]:
                seed_name = f"audit_seed_{seed}"
                seed_cfg_path = cfg_dir / f"{seed_name}.json"
                _dump(seed_cfg_path, _with_seed(orig_cfg, seed))
                seed_exp = run_arm(
                    root, seed_cfg_path, seed_name, runner=runner, card_dir=card_dir,
                )
                seed_score = _primary_from_exp(Path(seed_exp), target.metric_key)
                arms.append(_arm_record(
                    kind="seed",
                    experiment=seed_name,
                    seed=int(seed),
                    primary=seed_score,
                    exp_dir=seed_exp,
                    repo_root=root,
                ))

            if (
                attest.attested_depth == "novel"
                and repro_ok
                and attest.ablation_keys
            ):
                baseline_cfg = _load_baseline_cfg(root, target.scenario_id)
                for key in attest.ablation_keys:
                    ab_name = f"audit_ablate_{_safe_token(key)}"
                    ab_cfg = _with_seed(
                        ablation_config(orig_cfg, baseline_cfg, [key]),
                        target.original_seed,
                    )
                    ab_cfg_path = cfg_dir / f"{ab_name}.json"
                    _dump(ab_cfg_path, ab_cfg)
                    ab_exp = run_arm(
                        root, ab_cfg_path, ab_name, runner=runner, card_dir=card_dir,
                    )
                    ab_score = _primary_from_exp(Path(ab_exp), target.metric_key)
                    arms.append(_arm_record(
                        kind="ablate",
                        experiment=ab_name,
                        seed=target.original_seed,
                        primary=ab_score,
                        exp_dir=ab_exp,
                        repo_root=root,
                        key=str(key),
                    ))
        except Exception:
            _flush("partial")
            raise

        return _flush("complete")
    except KeyboardInterrupt:
        if target is not None:
            _flush("partial")
        raise


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--repo-root", default=".")
    p.add_argument("--exp-dir", default=None)
    p.add_argument("--scenario", default=None)


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="审查编排（不入账）")
    sub = p.add_subparsers(dest="cmd", required=True)

    pick = sub.add_parser("pick", help="选出审查对象")
    _add_common(pick)

    att = sub.add_parser("attest", help="判定新不新并写消融草稿")
    _add_common(att)
    att.add_argument("--dry-run-external", action="store_true", help="不访问外部文献（与 --fetch-external 同时出现时以此为准）")
    att.add_argument("--fetch-external", action="store_true", help="尝试拉文献；失败则 inconclusive")

    pipe = sub.add_parser("pipeline", help="完整审查管线")
    _add_common(pipe)
    pipe.add_argument("--n-seeds", type=int, default=5)
    pipe.add_argument("--skip-train", action="store_true")
    pipe.add_argument("--dry-run-external", action="store_true", help="不访问外部文献（与 --fetch-external 同时出现时以此为准）")
    pipe.add_argument("--fetch-external", action="store_true")

    show = sub.add_parser("show", help="打印最新审查卡片")
    show.add_argument("--repo-root", default=".")
    show.add_argument("--scenario", default=None)
    return p


def cmd_show(repo_root: Path, scenario_id: str | None) -> int:
    idx = load_index(repo_root)
    by = idx.get("by_scenario") or {}
    if not isinstance(by, dict) or not by:
        print("（无审查卡片）")
        return 0
    keys = [scenario_id] if scenario_id else list(by.keys())
    for sid in keys:
        entry = by.get(sid) if sid else None
        if not isinstance(entry, dict):
            print(f"（场景 {sid} 无卡片）")
            continue
        latest = entry.get("latest") or {}
        rel = str(latest.get("card_dir") or "").strip()
        if not rel:
            print(f"（场景 {sid} 无卡片）")
            continue
        md = Path(repo_root) / rel / "card.md"
        if md.is_file():
            text = md.read_text(encoding="utf-8")
            print(text, end="" if text.endswith("\n") else "\n")
        else:
            print(rel)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    root = Path(getattr(args, "repo_root", ".")).resolve()
    exp_dir = getattr(args, "exp_dir", None)
    scenario = getattr(args, "scenario", None)
    if args.cmd == "pick":
        t = pick_target(root, exp_dir=exp_dir, scenario_id=scenario)
        print(json.dumps(asdict(t), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "attest":
        t = pick_target(root, exp_dir=exp_dir, scenario_id=scenario)
        verdict = _resolve_verdict(
            root,
            fetch_external=bool(getattr(args, "fetch_external", False)),
            dry_run_external=bool(getattr(args, "dry_run_external", False)),
        )
        r = attest_candidate(
            root, t,
            search_claimed_depth=_search_claimed_depth(root),
            paper_verdict=verdict,
        )
        print(json.dumps(asdict(r), ensure_ascii=False, indent=2, default=str))
        return 0
    if args.cmd == "pipeline":
        card_dir = pipeline(
            root,
            exp_dir=exp_dir,
            scenario_id=scenario,
            n_seeds=int(getattr(args, "n_seeds", 5) or 5),
            skip_train=bool(getattr(args, "skip_train", False)),
            fetch_external=bool(getattr(args, "fetch_external", False)),
            dry_run_external=bool(getattr(args, "dry_run_external", False)),
        )
        print(f"card_dir={card_dir}")
        md = card_dir / "card.md"
        if md.is_file():
            print(md.read_text(encoding="utf-8"), end="")
        return 0
    if args.cmd == "show":
        return cmd_show(root, scenario)
    return 2


if __name__ == "__main__":
    sys.exit(main())
