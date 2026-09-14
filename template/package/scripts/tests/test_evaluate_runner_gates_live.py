"""实弹：runner 出分门禁在夹具上真触发；LEARNER / 无配置不触发。

覆盖 evaluate_runner_baseline_tag_doctor + is_evaluate_runner_repo 别名。
"""
from __future__ import annotations

from pathlib import Path

import yaml

from lib.adapter_accept import (
    evaluate_runner_baseline_tag_doctor,
    is_adapter_repo,
    is_evaluate_runner_repo,
)


def _write_cfg(
    root: Path,
    metrics_shape: str | None,
    *,
    watchlist: list[str] | None = None,
) -> None:
    data: dict = {"profile": "default", "ledger": {"watchlist": watchlist or ["LR"]}}
    if metrics_shape is not None:
        data["workspace"] = {"metrics_shape": metrics_shape}
    (root / "nn-config.yaml").write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")


def test_runner_missing_baseline_tag_fails(tmp_path: Path):
    _write_cfg(tmp_path, "EVALUATE_RUNNER", watchlist=["LR"])
    (tmp_path / "_runs").mkdir()
    (tmp_path / "_runs" / "results.tsv").write_text("run_id\tLR\n1\t0.1\n", encoding="utf-8")

    assert is_evaluate_runner_repo(tmp_path) is True
    assert is_adapter_repo(tmp_path) is True  # 别名
    status, msg = evaluate_runner_baseline_tag_doctor(tmp_path)
    assert status == "FAIL"
    assert "baseline_tag" in msg


def test_runner_baseline_tag_complete_passes(tmp_path: Path):
    _write_cfg(tmp_path, "EVALUATE_RUNNER", watchlist=["LR", "baseline_tag"])
    (tmp_path / "_runs").mkdir()
    (tmp_path / "_runs" / "results.tsv").write_text(
        "run_id\tLR\tbaseline_tag\n1\t0.1\tnone\n", encoding="utf-8"
    )

    status, msg = evaluate_runner_baseline_tag_doctor(tmp_path)
    assert status == "PASS"
    assert "runner 出分" in msg


def test_learner_skips_baseline_tag_gate(tmp_path: Path):
    _write_cfg(tmp_path, "EVALUATE_LEARNER", watchlist=["LR"])
    (tmp_path / "_runs").mkdir()
    (tmp_path / "_runs" / "results.tsv").write_text("run_id\tLR\n1\t0.1\n", encoding="utf-8")

    assert is_evaluate_runner_repo(tmp_path) is False
    status, msg = evaluate_runner_baseline_tag_doctor(tmp_path)
    assert status is None
    assert msg == ""


def test_no_config_skips(tmp_path: Path):
    assert is_evaluate_runner_repo(tmp_path) is False
    status, msg = evaluate_runner_baseline_tag_doctor(tmp_path)
    assert status is None
    assert msg == ""
