"""T-B: finalize_run 写 config.json 时确保 baseline_tag 字段存在、默认 none。

agent 在 plain 触发轮把 baseline_tag=plain 写进 cfg；finalize_run 兜底：
cfg 是 dict 且无 baseline_tag 时补 "none"，有则保留。本测试不跑训练，
stub 掉 finalize_run 的重尾方法（report_train_artifacts / save_checkpoint）。
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from experiment import ExperimentBase  # noqa: E402


class _FinalizeStub(ExperimentBase):
    """finalize_run 轻量执行：重尾方法 no-op。"""

    @property
    def metric_keys(self) -> dict[str, str]:
        return {}

    def report_train_artifacts(self, *args, **kwargs):  # noqa: D401
        return {}

    def save_checkpoint(self, *args, **kwargs):  # noqa: D401
        return None


@pytest.fixture()
def _skip_env(monkeypatch):
    monkeypatch.setenv("NN_SKIP_POST_EVAL", "1")
    monkeypatch.setenv("NN_SNAPSHOT_CODE", "0")


def _run_finalize(tmp_path: Path, cfg: dict) -> dict:
    inst = _FinalizeStub.__new__(_FinalizeStub)
    exp_dir = tmp_path / "exp001"
    exp_dir.mkdir()
    inst.finalize_run(
        repo_root=tmp_path,
        cfg=cfg,
        timer=types.SimpleNamespace(elapsed=0.0),
        best_state=None,
        exp_dir=exp_dir,
        experiment="t",
        precomputed_official_metrics={},  # 跳过 contract/ws/learner elif 分支
    )
    return json.loads((exp_dir / "config.json").read_text(encoding="utf-8"))


def test_finalize_sets_default_none(tmp_path, _skip_env):
    out = _run_finalize(tmp_path, {"LR": 0.001})
    assert out["baseline_tag"] == "none"


def test_finalize_preserves_existing_plain(tmp_path, _skip_env):
    out = _run_finalize(tmp_path, {"LR": 0.001, "baseline_tag": "plain"})
    assert out["baseline_tag"] == "plain"
