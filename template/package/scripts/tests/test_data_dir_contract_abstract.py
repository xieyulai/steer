"""T-A3: experiment.ExperimentBase.data_dir 不再硬编码 data/example-cls。

L4 fashionmnist-raw debug 暴露的低危 bug：
data_dir property 的 fallback 硬编码模板仓的 data/example-cls，
业务仓 smoke-check 时找不到 data dir 默认指向模板路径。

修复（spec T-A3）：
- 优先级：subclass override > NN_DATA_DIR env > ./data fallback
- 不再硬编码 data/example-cls（避免模板/业务仓混淆）
- 业务仓可继承 ExperimentBase 后 override data_dir 返回 ./data 或绝对路径
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from experiment import ExperimentBase


class _BaseExperiment(ExperimentBase):
    """最小实验子类，不 override data_dir。"""

    @property
    def metric_keys(self) -> dict[str, str]:
        return {"acc": "max"}


class _DataDirOverrideExperiment(ExperimentBase):
    """override data_dir 模拟业务仓 contract。"""

    @property
    def metric_keys(self) -> dict[str, str]:
        return {"acc": "max"}

    @property
    def data_dir(self) -> str:
        return "/custom/path/to/data"


# === A3: 优先级测试 ===

def test_data_dir_env_var_wins(monkeypatch, tmp_path):
    """A3 spec: NN_DATA_DIR env 优先级最高。"""
    monkeypatch.setenv("NN_DATA_DIR", str(tmp_path / "env_data"))
    inst = _BaseExperiment.__new__(_BaseExperiment)
    assert inst.data_dir == str(tmp_path / "env_data")


def test_data_dir_subclass_override_wins_over_env(monkeypatch, tmp_path):
    """A3 spec: subclass override 优先级 > env var。

    业务仓通常 override data_dir（spec T-A3 推荐），env 仅为兜底。
    """
    monkeypatch.setenv("NN_DATA_DIR", str(tmp_path / "env_data"))
    inst = _DataDirOverrideExperiment.__new__(_DataDirOverrideExperiment)
    # override 胜出
    assert inst.data_dir == "/custom/path/to/data"


def test_data_dir_fallback_to_relative_data(monkeypatch):
    """A3 spec: 无 env、无 override 时 fallback 到 ./data（不再硬编码 example-cls）。"""
    monkeypatch.delenv("NN_DATA_DIR", raising=False)
    inst = _BaseExperiment.__new__(_BaseExperiment)
    # fallback 不应是模板仓的 data/example-cls
    assert inst.data_dir == "./data"
    assert "example-cls" not in inst.data_dir
    assert "template/package" not in inst.data_dir


def test_data_dir_does_not_hardcode_example_cls(monkeypatch):
    """A3 spec regression: 绝不返回 data/example-cls 路径。"""
    monkeypatch.delenv("NN_DATA_DIR", raising=False)
    inst = _BaseExperiment.__new__(_BaseExperiment)
    result = inst.data_dir
    # 不能是模板仓的绝对路径
    assert not result.endswith("data/example-cls"), (
        f"data_dir 仍硬编码 data/example-cls: {result}"
    )
