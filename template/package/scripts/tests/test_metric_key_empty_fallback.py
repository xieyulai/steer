"""T-A1: experiment.ExperimentBase.metric_key 在 metric_keys 为空 dict 时返回 None。

L4 fashionmnist-raw debug 暴露的真实 bug：
greenfield init 项目跑 regen_results_tsv.py 时 `metric_key` property
  return next(iter(self.metric_keys))  # 空 dict 抛 StopIteration
导致下游 _default_tsv_columns 崩溃（set 减法求 metric_key 时）。

修复：metric_key property 在 metric_keys 为空时返回 None 而非 StopIteration。
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from experiment import ExperimentBase


class _EmptyContract(ExperimentBase):
    """最小实验子类，metric_keys 显式返回空 dict 模拟 greenfield。"""

    @property
    def metric_keys(self) -> dict[str, str]:
        return {}


class _NormalContract(ExperimentBase):
    """常规子类，metric_keys 有一个指标。"""

    @property
    def metric_keys(self) -> dict[str, str]:
        return {"accuracy": "max"}


# === A1: 空 dict 不再抛 StopIteration ===

def test_metric_key_empty_returns_none():
    """A1 spec: metric_keys 为空时返回 None，不抛 StopIteration。"""
    inst = _EmptyContract.__new__(_EmptyContract)
    # 显式调用 property 两次
    assert inst.metric_key is None


def test_metric_key_empty_does_not_raise_stopiteration():
    """A1 spec: 显式 verify 不抛 StopIteration。"""
    inst = _EmptyContract.__new__(_EmptyContract)
    try:
        result = inst.metric_key
    except StopIteration:
        pytest.fail("metric_key 在空 dict 时不应抛 StopIteration（应返回 None）")
    assert result is None


# === A1 regression: 非空时仍返回第一个 key ===

def test_metric_key_non_empty_returns_first_key():
    """A1 regression: 非空时返回第一个 key（保持原行为）。"""
    inst = _NormalContract.__new__(_NormalContract)
    assert inst.metric_key == "accuracy"


def test_metric_key_multiple_keys_returns_first():
    """A1 regression: 多 key 时返回第一个（dict 顺序保留）。"""
    class _MultiContract(ExperimentBase):
        @property
        def metric_keys(self) -> dict[str, str]:
            return {"primary": "max", "secondary": "min"}
    inst = _MultiContract.__new__(_MultiContract)
    assert inst.metric_key == "primary"


# === A1 caller: _default_tsv_columns 也能 handle None ===

def test_default_tsv_columns_empty_returns_no_none():
    """A1 caller: _default_tsv_columns 在空 metric_keys 时不返回 None。"""
    inst = _EmptyContract.__new__(_EmptyContract)
    cols = inst._default_tsv_columns()
    # 主列占位应为 ""（不写 None 触发下游 str 失败）
    assert None not in cols
    # SCENARIO_ID_COLUMN 位置 = index 1
    assert cols[1]  # 不为空


def test_default_tsv_columns_normal_keeps_metric_key_col():
    """A1 caller regression: 非空时主列 = 第一个 metric key。"""
    inst = _NormalContract.__new__(_NormalContract)
    cols = inst._default_tsv_columns()
    # "accuracy" 在主列位置（index 2 = experiment 之后、scenario 之后）
    assert "accuracy" in cols
