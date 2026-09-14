"""smoke_metrics_gate：finite 主分 + 拒绝 _error 全 0 兜底。"""
from __future__ import annotations

import json
from pathlib import Path

from lib.smoke_metrics_gate import evaluate_smoke_metrics


def _write(repo: Path, decision: dict, *, results_metrics: dict | None = None) -> None:
    runs = repo / "_runs"
    runs.mkdir(parents=True)
    exp = runs / "exp" / "e1"
    exp.mkdir(parents=True)
    decision = dict(decision)
    decision.setdefault(
        "finalize_round",
        {"keeper_exp_dir": str(exp), "candidate_exp_dirs": [str(exp)]},
    )
    decision.setdefault("evaluated_exp_dir", str(exp))
    (runs / "round_decision.json").write_text(
        json.dumps(decision, ensure_ascii=False), encoding="utf-8"
    )
    if results_metrics is not None:
        (exp / "results.json").write_text(
            json.dumps({"metrics": results_metrics}, ensure_ascii=False),
            encoding="utf-8",
        )


def test_ok_finite(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {"primary_metric": {"key": "val_accuracy", "value": 0.5, "direction": "maximize"}},
        results_metrics={"val_accuracy": 0.5},
    )
    ok, msg = evaluate_smoke_metrics(tmp_path)
    assert ok, msg


def test_ok_legitimate_zero(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {"primary_metric": {"key": "score", "value": 0.0, "direction": "maximize"}},
        results_metrics={"score": 0.0},
    )
    ok, msg = evaluate_smoke_metrics(tmp_path)
    assert ok, msg


def test_fail_nan(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {"primary_metric": {"key": "m", "value": float("nan"), "direction": "maximize"}},
    )
    ok, msg = evaluate_smoke_metrics(tmp_path)
    assert not ok
    assert "非有限" in msg


def test_fail_inf(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {"primary_metric": {"key": "m", "value": float("inf"), "direction": "maximize"}},
    )
    ok, msg = evaluate_smoke_metrics(tmp_path)
    assert not ok


def test_fail_missing_primary(tmp_path: Path) -> None:
    runs = tmp_path / "_runs"
    runs.mkdir(parents=True)
    (runs / "round_decision.json").write_text("{}", encoding="utf-8")
    ok, msg = evaluate_smoke_metrics(tmp_path)
    assert not ok
    assert "primary_metric" in msg


def test_fail_error_and_zero(tmp_path: Path) -> None:
    _write(
        tmp_path,
        {"primary_metric": {"key": "eval_episodic_return", "value": 0.0, "direction": "maximize"}},
        results_metrics={"eval_episodic_return": 0.0, "_error": "boom"},
    )
    ok, msg = evaluate_smoke_metrics(tmp_path)
    assert not ok
    assert "_error" in msg


def test_ok_error_but_nonzero(tmp_path: Path) -> None:
    """带 _error 但主分非 0：不按「全 0 兜底」杀（罕见；仍要求 finite）。"""
    _write(
        tmp_path,
        {"primary_metric": {"key": "r", "value": 1.0, "direction": "maximize"}},
        results_metrics={"r": 1.0, "_error": "partial"},
    )
    ok, msg = evaluate_smoke_metrics(tmp_path)
    assert ok, msg
