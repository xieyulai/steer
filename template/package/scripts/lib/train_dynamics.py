"""训中过程分析：metrics_series.tsv 写入与 train_dynamics 规则引擎。"""
from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

METRICS_SERIES_BASENAME = "metrics_series.tsv"
TRAIN_DYNAMICS_JSON = "train_dynamics.json"
TRAIN_DYNAMICS_MD = "train_dynamics.md"

_PREFIX_COLS = ("step", "step_kind", "phase", "recorded_at")


def metrics_series_path(exp_dir: Path) -> Path:
    return Path(exp_dir).resolve() / METRICS_SERIES_BASENAME


def _read_tsv_header(path: Path) -> list[str] | None:
    if not path.is_file() or path.stat().st_size == 0:
        return None
    with path.open(encoding="utf-8", newline="") as f:
        row = next(csv.reader(f, delimiter="\t"), None)
    return list(row) if row else None


def _read_tsv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        if reader.fieldnames is None:
            return []
        return [dict(r) for r in reader]


def _format_cell(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return ""
        return f"{val:.6g}"
    if isinstance(val, (int, bool)):
        return str(val)
    return str(val).strip()


def _merge_header(existing: list[str] | None, keys: set[str]) -> list[str]:
    metric_cols = sorted(k for k in keys if k not in _PREFIX_COLS)
    if existing:
        extra = sorted(set(metric_cols) - set(existing))
        return list(existing) + extra
    return list(_PREFIX_COLS) + metric_cols


def _rewrite_tsv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(header)
        for row in rows:
            w.writerow([row.get(c, "") for c in header])


def append_metrics_row(
    exp_dir: Path,
    *,
    step: int,
    step_kind: str,
    phase: str,
    metrics: dict[str, Any],
) -> Path:
    """Append one row to ``metrics_series.tsv``; extend header if new keys appear."""
    exp_dir = Path(exp_dir).resolve()
    path = metrics_series_path(exp_dir)
    exp_dir.mkdir(parents=True, exist_ok=True)

    row_keys = {k for k, v in metrics.items() if _format_cell(v)}
    header = _read_tsv_header(path)
    new_header = _merge_header(header, row_keys)

    row_map: dict[str, str] = {
        "step": str(int(step)),
        "step_kind": str(step_kind).strip(),
        "phase": str(phase).strip(),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    for k, v in metrics.items():
        row_map[k] = _format_cell(v)

    if header is None:
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f, delimiter="\t", lineterminator="\n")
            w.writerow(new_header)
            w.writerow([row_map.get(c, "") for c in new_header])
        return path

    if new_header != header:
        old_rows = _read_tsv_rows(path)
        _rewrite_tsv(path, new_header, old_rows)
        header = new_header

    with path.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow([row_map.get(c, "") for c in header])
    return path


def _parse_float(cell: str) -> float | None:
    s = (cell or "").strip()
    if not s:
        return None
    try:
        v = float(s)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except ValueError:
        return None


def _strict_improved(current: float, best: float, direction: str) -> bool:
    if direction == "maximize":
        return current > best
    return current < best


def _rows_with_kind(rows: list[dict[str, str]], kind: str) -> list[dict[str, str]]:
    return [r for r in rows if str(r.get("step_kind", "")).strip() == kind]


def _eval_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    eval_k = _rows_with_kind(rows, "epoch_eval")
    if eval_k:
        return eval_k
    return _rows_with_kind(rows, "eval_checkpoint")


def _train_loss_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for r in rows:
        if _parse_float(r.get("train_loss", "")) is not None:
            out.append(r)
    return out


def _trend(vals: list[float]) -> str:
    if len(vals) < 2:
        return "flat"
    n = max(1, len(vals) // 3)
    first = sum(vals[:n]) / n
    last = sum(vals[-n:]) / n
    if abs(last - first) <= 1e-12 * max(abs(first), 1.0):
        return "flat"
    return "decreasing" if last < first else "increasing"


def compute_train_dynamics(
    rows: list[dict[str, str]],
    *,
    metric_key: str,
    direction: str,
    train_done: dict[str, Any] | None,
    plateau_window: int = 5,
    profile: str = "supervised",
) -> dict[str, Any]:
    """Deterministic summary from metrics_series rows."""
    eval_rows = _eval_rows(rows)
    loss_rows = _train_loss_rows(rows)
    steps = [_parse_float(r.get("step", "")) for r in rows]
    steps_f = [s for s in steps if s is not None]

    primary_vals: list[tuple[int, float]] = []
    for r in eval_rows:
        st = _parse_float(r.get("step", ""))
        v = _parse_float(r.get(metric_key, ""))
        if st is not None and v is not None:
            primary_vals.append((int(st), v))

    primary_block: dict[str, Any] = {
        "first": None,
        "last": None,
        "best": None,
        "best_at_step": None,
        "improved_over_first": None,
    }
    if primary_vals:
        primary_block["first"] = primary_vals[0][1]
        primary_block["last"] = primary_vals[-1][1]
        if direction == "maximize":
            best_pair = max(primary_vals, key=lambda x: x[1])
        else:
            best_pair = min(primary_vals, key=lambda x: x[1])
        primary_block["best"] = best_pair[1]
        primary_block["best_at_step"] = best_pair[0]
        primary_block["improved_over_first"] = _strict_improved(
            primary_vals[-1][1], primary_vals[0][1], direction
        )

    plateau = {"detected": False, "since_step": None, "window": plateau_window, "rule": "no_strict_improve_for_n_evals"}
    if len(primary_vals) >= plateau_window + 1:
        best_so_far: float | None = None
        since: int | None = None
        for st, v in primary_vals:
            if best_so_far is None:
                best_so_far = v
                since = st
                continue
            if _strict_improved(v, best_so_far, direction):
                best_so_far = v
                since = st
        if since is not None and primary_vals[-1][0] - since >= 0:
            tail = primary_vals[-(plateau_window + 1):]
            if len(tail) >= plateau_window + 1 and all(
                not _strict_improved(tail[i][1], tail[i - 1][1], direction) for i in range(1, len(tail))
            ):
                plateau["detected"] = True
                plateau["since_step"] = since

    loss_vals = [_parse_float(r.get("train_loss", "")) for r in loss_rows]
    loss_vals = [v for v in loss_vals if v is not None]
    train_loss_block: dict[str, Any] = {"trend": "n/a", "first": None, "last": None}
    if loss_vals:
        train_loss_block = {
            "first": loss_vals[0],
            "last": loss_vals[-1],
            "trend": _trend(loss_vals),
        }

    gap_block: dict[str, Any] = {"available": False}
    gaps: list[float] = []
    for r in eval_rows:
        tl = _parse_float(r.get("train_loss", ""))
        ev = _parse_float(r.get(metric_key, ""))
        if tl is not None and ev is not None:
            gaps.append(abs(tl - ev))
    if gaps:
        gap_block = {
            "available": True,
            "first_gap": gaps[0],
            "last_gap": gaps[-1],
            "trend": _trend(gaps) if len(gaps) >= 2 else "stable",
        }

    anomalies: list[str] = []
    for r in rows:
        st = r.get("step", "?")
        for k, v in r.items():
            if k in _PREFIX_COLS:
                continue
            raw = (v or "").strip().lower()
            if raw in ("nan", "inf", "-inf"):
                anomalies.append(f"non_finite:{k}@step{st}")

    if loss_vals and primary_vals and len(loss_vals) >= 3 and len(primary_vals) >= 2:
        loss_tail = loss_vals[-max(1, len(loss_vals) // 5):]
        pri_tail = [p[1] for p in primary_vals[-max(1, len(primary_vals) // 5):]]
        if _trend(loss_tail) == "increasing" and _trend(pri_tail) in ("flat", "decreasing" if direction == "maximize" else "increasing"):
            anomalies.append("loss_divergence")

    stop_block: dict[str, Any] = {}
    if train_done:
        stop_block = {
            "reason": train_done.get("stop_reason"),
            "last_completed_step": train_done.get("last_completed_epoch") or train_done.get("last_completed_step"),
            "configured_steps": train_done.get("epochs_configured"),
            "stopped_early": train_done.get("stopped_early"),
        }

    return {
        "schema_version": 1,
        "profile": profile,
        "metric_key": metric_key,
        "direction": direction,
        "n_points": len(rows),
        "step_range": [int(min(steps_f)), int(max(steps_f))] if steps_f else [],
        "primary": primary_block,
        "plateau": plateau,
        "train_loss": train_loss_block,
        "train_val_gap": gap_block,
        "anomalies": anomalies,
        "stop": stop_block,
        "metric_roles": {
            "train_loss": "train_proxy",
            metric_key: "eval_proxy",
            "official": "results.json",
        },
        "series_path": METRICS_SERIES_BASENAME,
    }


def format_train_dynamics_md(dynamics: dict[str, Any]) -> str:
    p = dynamics.get("primary") or {}
    pl = dynamics.get("plateau") or {}
    tl = dynamics.get("train_loss") or {}
    gap = dynamics.get("train_val_gap") or {}
    stop = dynamics.get("stop") or {}
    lines = [
        "# Train dynamics",
        "",
        f"| field | value |",
        f"|-------|-------|",
        f"| n_points | {dynamics.get('n_points', 0)} |",
        f"| metric | {dynamics.get('metric_key')} ({dynamics.get('direction')}) |",
        f"| primary first/last/best | {p.get('first')} / {p.get('last')} / {p.get('best')} @ step {p.get('best_at_step')} |",
        f"| train_loss trend | {tl.get('trend')} ({tl.get('first')} → {tl.get('last')}) |",
        f"| plateau | {pl.get('detected')} since={pl.get('since_step')} |",
        f"| train_val_gap | {gap.get('trend') if gap.get('available') else 'n/a'} |",
        f"| stop | {stop.get('reason')} @ {stop.get('last_completed_step')} |",
    ]
    anom = dynamics.get("anomalies") or []
    if anom:
        lines.append(f"| anomalies | {', '.join(anom)} |")
    lines.append("")
    return "\n".join(lines)


def write_train_dynamics(exp_dir: Path, dynamics: dict[str, Any]) -> tuple[Path, Path]:
    exp_dir = Path(exp_dir).resolve()
    jp = exp_dir / TRAIN_DYNAMICS_JSON
    mp = exp_dir / TRAIN_DYNAMICS_MD
    jp.write_text(json.dumps(dynamics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    mp.write_text(format_train_dynamics_md(dynamics), encoding="utf-8")
    return jp, mp


def load_train_done(exp_dir: Path) -> dict[str, Any] | None:
    p = Path(exp_dir) / "train_done.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def finalize_train_dynamics(
    exp_dir: Path,
    contract: Any,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Read series (or adapt monitor.csv), compute and write dynamics. Never raises."""
    exp_dir = Path(exp_dir).resolve()
    series_path = metrics_series_path(exp_dir)
    rows: list[dict[str, str]] = _read_tsv_rows(series_path)

    if not rows:
        adapted = adapt_monitor_csv_to_series(exp_dir)
        if adapted:
            rows = _read_tsv_rows(series_path)

    plateau_window = 5
    profile = "supervised"
    if repo_root is not None:
        try:
            import yaml

            cfg_path = Path(repo_root) / "nn-config.yaml"
            if cfg_path.is_file():
                raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
                agent = raw.get("agent") or {}
                plateau_window = int(agent.get("train_dynamics_plateau_window", 5))
                profile = str(raw.get("profile") or "supervised")
        except Exception:
            pass

    train_done = load_train_done(exp_dir)
    mk = str(getattr(contract, "metric_key", "") or "")
    direction = str(getattr(contract, "metric_direction", "maximize") or "maximize")

    dynamics = compute_train_dynamics(
        rows,
        metric_key=mk,
        direction=direction,
        train_done=train_done,
        plateau_window=max(2, plateau_window),
        profile=profile,
    )
    dynamics["exp_dir"] = str(exp_dir)
    write_train_dynamics(exp_dir, dynamics)
    return dynamics


def adapt_monitor_csv_to_series(exp_dir: Path) -> bool:
    """RL v1: map ``training_monitor/monitor.csv`` → metrics_series.tsv."""
    exp_dir = Path(exp_dir).resolve()
    if metrics_series_path(exp_dir).is_file():
        return False
    mon = exp_dir / "training_monitor" / "monitor.csv"
    if not mon.is_file():
        mon = exp_dir / "monitor.csv"
    if not mon.is_file():
        return False
    try:
        with mon.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return False
            for i, row in enumerate(reader):
                metrics: dict[str, Any] = {}
                if "r" in row:
                    metrics["episode_return"] = row["r"]
                if "l" in row:
                    metrics["episode_length"] = row["l"]
                if "perf_score" in row:
                    metrics["perf_score"] = row["perf_score"]
                append_metrics_row(
                    exp_dir,
                    step=i + 1,
                    step_kind="eval_checkpoint",
                    phase="training",
                    metrics=metrics,
                )
        return True
    except OSError:
        return False


def read_metrics_series_rows(exp_dir: Path) -> list[dict[str, str]]:
    """Read all rows from ``exp_dir/metrics_series.tsv``."""
    return _read_tsv_rows(metrics_series_path(exp_dir))


def summarize_series_tail(rows: list[dict[str, str]], *, max_rows: int = 5) -> list[dict[str, str]]:
    if not rows:
        return []
    return rows[-max_rows:]
