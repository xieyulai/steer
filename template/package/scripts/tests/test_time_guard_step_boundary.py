"""训练墙钟：满预算才停 + optimizer.step 入口边界（spec 20260906_0847）。"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
import torch
import torch.nn as nn

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from experiment import (  # noqa: E402
    TimeBudgetStop,
    TimeGuard,
    guard_optimizer_steps,
)


def test_should_stop_at_full_budget_not_80_percent():
    t = TimeGuard(budget=100)
    t._start = time.time() - 80.0
    assert t.should_stop() is False
    t._start = time.time() - 100.0
    assert t.should_stop() is True


def test_should_stop_budget_zero_never():
    t = TimeGuard(budget=0)
    t._start = time.time() - 10_000.0
    assert t.should_stop() is False


def test_time_budget_stop_not_caught_as_exception():
    caught_as_exception = False
    try:
        raise TimeBudgetStop()
    except Exception:
        caught_as_exception = True
    except TimeBudgetStop:
        caught_as_exception = False
    assert caught_as_exception is False


def test_guard_optimizer_steps_raises_after_budget():
    param = nn.Parameter(torch.zeros(2, 2))
    opt = torch.optim.Adam([param], lr=1e-3)
    timer = TimeGuard(budget=1)
    timer._start = time.time() - 1.0
    n = 0
    with pytest.raises(TimeBudgetStop):
        with guard_optimizer_steps(timer):
            for _ in range(50):
                opt.zero_grad()
                (param ** 2).sum().backward()
                opt.step()
                n += 1
    assert n == 0  # 入口即停，一次 step 都未开始


def test_guard_optimizer_steps_restores_after_exit():
    param = nn.Parameter(torch.zeros(2, 2))
    opt = torch.optim.SGD([param], lr=0.1)
    timer = TimeGuard(budget=1)
    timer._start = time.time() - 1.0
    with pytest.raises(TimeBudgetStop):
        with guard_optimizer_steps(timer):
            opt.step()
    opt.zero_grad()
    (param ** 2).sum().backward()
    opt.step()  # 拆包后不再抛


def test_partial_epoch_does_not_update_best_or_completed():
    """与 train.py 单层判断相同：半截轮不写 last_completed、不更新 best_state。"""
    last_completed = 0
    best_state = None
    stop_reason = "epochs_complete"
    timer = TimeGuard(budget=1)
    # epoch 1 在预算内完整；epoch 2 开始前把秒表拨过点，长 step 循环触发 TimeBudgetStop

    def train_step_epoch1():
        return {"ok": True}

    def train_step_epoch2_long():
        param = nn.Parameter(torch.ones(2))
        opt = torch.optim.Adam([param], lr=1e-3)
        for _ in range(20):
            opt.zero_grad()
            (param ** 2).sum().backward()
            opt.step()
        return {"ok": True}

    with guard_optimizer_steps(timer):
        for epoch in (1, 2):
            if timer.should_stop():
                stop_reason = "time_budget"
                break
            try:
                if epoch == 1:
                    train_step_epoch1()
                else:
                    timer._start = time.time() - 1.0
                    train_step_epoch2_long()
            except TimeBudgetStop:
                stop_reason = "time_budget"
                break
            best_state = {"epoch": epoch}
            last_completed = epoch

    assert stop_reason == "time_budget"
    assert last_completed == 1
    assert best_state == {"epoch": 1}


def test_train_py_wires_boundary_stop():
    src = (Path(__file__).resolve().parents[2] / "train.py").read_text(encoding="utf-8")
    assert "guard_optimizer_steps(timer)" in src
    assert "except TimeBudgetStop:" in src
