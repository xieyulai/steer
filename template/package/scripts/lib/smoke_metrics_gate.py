"""smoke 实质指标闸：round_decision 主分 finite；拒绝 _error+全 0 失败兜底。"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file() or path.stat().st_size <= 0:
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def _decision_path(repo_root: Path) -> Path | None:
    runs = Path(repo_root) / "_runs"
    for name in ("round_decision.json", "evaluation_result.json"):
        p = runs / name
        if p.is_file() and p.stat().st_size > 0:
            return p
    return None


def _keeper_results_metrics(decision: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    """从 keeper / evaluated exp 的 results.json 取 metrics（含可能的 _error 字符串）。"""
    fr = decision.get("finalize_round")
    candidates: list[Path] = []
    if isinstance(fr, dict):
        kep = fr.get("keeper_exp_dir")
        if kep:
            candidates.append(Path(str(kep)))
    ev = decision.get("evaluated_exp_dir")
    if ev:
        candidates.append(Path(str(ev)))
    for exp in candidates:
        if not exp.is_absolute():
            exp = Path(repo_root) / exp
        payload = _load_json(exp / "results.json")
        if not payload:
            continue
        metrics = payload.get("metrics")
        if isinstance(metrics, dict):
            return metrics
    return {}


def evaluate_smoke_metrics(repo_root: Path | str) -> tuple[bool, str]:
    """返回 (ok, message)。ok=False 时 message 供 smoke-check die。"""
    root = Path(repo_root).resolve()
    path = _decision_path(root)
    if path is None:
        return False, "缺少非空 _runs/round_decision.json（或旧名 evaluation_result.json）"

    decision = _load_json(path)
    if decision is None:
        return False, f"{path.name} 无法解析为 JSON object"

    pm = decision.get("primary_metric")
    if not isinstance(pm, dict):
        return False, f"{path.name} 缺少 primary_metric 对象"

    key = str(pm.get("key") or "").strip() or "(unknown)"
    raw_val = pm.get("value")
    if raw_val is None:
        return False, f"primary_metric.value 缺失（key={key}）"
    if isinstance(raw_val, bool):
        return False, f"primary_metric.value 类型非法 bool（key={key}）"
    if not isinstance(raw_val, (int, float)):
        return False, f"primary_metric.value 非数值（key={key}, type={type(raw_val).__name__}）"

    val = float(raw_val)
    if not math.isfinite(val):
        return False, f"primary_metric 非有限值（key={key}, value={val!r}）"

    metrics = _keeper_results_metrics(decision, root)
    err = metrics.get("_error")
    if err is not None and str(err).strip() != "":
        # 失败兜底：带 _error 且主分为 0 → 拒绝（合法真 0 无 _error 仍过）
        if val == 0.0:
            return (
                False,
                f"疑似失败兜底：results.json metrics._error={err!r} 且主分 {key}=0",
            )

    return True, f"primary_metric ok key={key} value={val}"


def main() -> int:
    import sys

    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    ok, msg = evaluate_smoke_metrics(root)
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
