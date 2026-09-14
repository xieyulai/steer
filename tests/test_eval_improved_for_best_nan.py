"""eval_improved_for_best NaN 防御回归测试 (AE-1)。

背景：F1 E4 设计上 `workspace.evaluate` 写 `test_accuracy=math.nan`
（训内 evaluate 不算 test）。在 NaN 比较下，Python `current > NaN` 永远 False
→ `eval_improved_for_best` 在 `best_epoch > 0` 后永远 False → KEEP 不触发
→ 3-4 轮结果作废 + A-e 探针事实上不可用（fashionmnist-raw 40 轮反思 L4 bug 1+3）。
"""
import math

import pytest

from template.package.experiment import eval_improved_for_best


def test_first_eval_always_improved():
    """best_epoch <= 0 → 视为 improved（与训内 best_state 更新一致）。"""
    assert eval_improved_for_best(0.5, 0.5, "maximize", best_epoch=0) is True
    assert eval_improved_for_best(0.5, math.nan, "maximize", best_epoch=0) is True


def test_normal_strict_improvement_maximize():
    """maximize + 真改进 → True；持平 → False；恶化 → False。"""
    assert eval_improved_for_best(0.91, 0.90, "maximize", best_epoch=10) is True
    assert eval_improved_for_best(0.90, 0.90, "maximize", best_epoch=10) is False
    assert eval_improved_for_best(0.89, 0.90, "maximize", best_epoch=10) is False


def test_normal_strict_improvement_minimize():
    """minimize 方向对称。"""
    assert eval_improved_for_best(0.09, 0.10, "minimize", best_epoch=10) is True
    assert eval_improved_for_best(0.10, 0.10, "minimize", best_epoch=10) is False
    assert eval_improved_for_best(0.11, 0.10, "minimize", best_epoch=10) is False


def test_nan_best_returns_false():
    """【核心修复】best 是 NaN（workspace.evaluate 写）→ 沿用旧 best，不假装改进。

    OLD 行为：`current > NaN` 永远 False → eval 永远返回 False → KEEP 不触发。
    NEW 行为：检测 best 是 NaN → return False（沿用，不假装改进）。
    """
    assert eval_improved_for_best(0.95, math.nan, "maximize", best_epoch=10) is False
    assert eval_improved_for_best(0.0, math.nan, "minimize", best_epoch=10) is False


def test_nan_current_returns_false():
    """current 是 NaN（当前评估无效）→ 不更新 best。"""
    assert eval_improved_for_best(math.nan, 0.90, "maximize", best_epoch=10) is False
    assert eval_improved_for_best(math.nan, 0.10, "minimize", best_epoch=10) is False


def test_inf_best_returns_false():
    """inf 也视为无效 best。"""
    assert eval_improved_for_best(0.95, math.inf, "maximize", best_epoch=10) is False
    assert eval_improved_for_best(0.95, -math.inf, "minimize", best_epoch=10) is False


def test_inf_current_returns_false():
    """current inf 也视为无效评估。"""
    assert eval_improved_for_best(math.inf, 0.90, "maximize", best_epoch=10) is False


def test_nan_first_eval_still_improved():
    """best_epoch=0 优先级高于 NaN 检查（首 eval 总是视为 improved）。"""
    assert eval_improved_for_best(math.nan, math.nan, "maximize", best_epoch=0) is True