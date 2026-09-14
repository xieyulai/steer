"""要求1（R8 软警告）：范式撞墙宽判决 + 三接线点单测。

覆盖（对照记录 doc §7 Phase 3 R6 + §9 R8 设计）：
- check_paradigm_mismatch 宽判决：K 轮 / flat / 条件①② AND / 不足轮 / 异常不 raise / nn-config 覆盖
- R1 接线：reflect_gate_decision 命中 → "run:R8:paradigm_mismatch"
- R3 接线：experiment.py finalize_round 源码含 check_paradigm_mismatch + paradigm_fit=MISMATCH

设计：check_paradigm_mismatch 懒 import metric_key/plateau_streak/tsv_rows（run_ledger_summary），
故 monkeypatch 模块属性即可隔离 contract 依赖；tsv_rows 走真文件（验 eps 计算）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from lib import auto_mode
from lib import run_ledger_summary as rls
from lib.auto_mode import (
    PARADIGM_MISMATCH_EPS,
    PARADIGM_MISMATCH_K,
    check_paradigm_mismatch,
)
from lib.nn_config import save_nn_config


METRIC = "val_accuracy"


def _write_tsv(repo_root: Path, vals: list[float], metric_col: str = METRIC) -> None:
    """写 _runs/results.tsv：experiment\t<metric>\ttimestamp，每值一行。"""
    runs = repo_root / "_runs"
    runs.mkdir(parents=True, exist_ok=True)
    lines = [f"experiment\t{metric_col}\ttimestamp"]
    for i, v in enumerate(vals):
        lines.append(f"r{i}\t{v}\t2026-07-13T00:00:{i:02d}")
    (runs / "results.tsv").write_text("\n".join(lines) + "\n", encoding="utf-8")


@pytest.fixture
def stub_mp(monkeypatch):
    """桩 metric_key + plateau_streak（隔离 contract）；tsv_rows 走真文件。

    check_paradigm_mismatch 内 `from lib.run_ledger_summary import metric_key, plateau_streak`
    在调用时绑定模块属性 → monkeypatch 模块属性即生效。
    """

    def _apply(metric_col: str = METRIC, plateau_return: int = PARADIGM_MISMATCH_K):
        monkeypatch.setattr(rls, "metric_key", lambda root: metric_col)
        monkeypatch.setattr(rls, "plateau_streak", lambda root, n: plateau_return)

    return _apply


# === 常量默认（§9.1：K=6~8 取 7；ε=0.5pp）===

def test_constants_defaults():
    assert PARADIGM_MISMATCH_K == 7
    assert PARADIGM_MISMATCH_EPS == 0.005


# === 宽判决：不足轮 → False ===

def test_insufficient_rounds_returns_false(tmp_path):
    """历史 < K 轮 → 无法判决 → False（早退，不触 plateau/metric）。"""
    _write_tsv(tmp_path, [0.85, 0.85, 0.85])  # 3 < 7
    assert check_paradigm_mismatch(tmp_path) is False


def test_no_tsv_returns_false(tmp_path):
    """无 results.tsv → tsv_rows=[] → False。"""
    assert check_paradigm_mismatch(tmp_path) is False


# === 宽判决：flat + 无新 best → True（撞墙）===

def test_flat_no_new_best_returns_true(tmp_path, stub_mp):
    """连续 K 轮主指标走势平稳（spread<ε）∧ plateau>=K → 范式撞墙 → True。"""
    flat = [0.8500, 0.8501, 0.8502, 0.8499, 0.8500, 0.8501, 0.8502]  # spread≈0.0003
    _write_tsv(tmp_path, flat)
    stub_mp(plateau_return=PARADIGM_MISMATCH_K)
    assert check_paradigm_mismatch(tmp_path) is True


def test_flat_more_than_k_rounds_returns_true(tmp_path, stub_mp):
    """K+ 轮 flat 撞墙同样触发（tail 取末 K 轮）。"""
    _write_tsv(tmp_path, [0.85] * 10)
    stub_mp(plateau_return=PARADIGM_MISMATCH_K + 1)
    assert check_paradigm_mismatch(tmp_path) is True


# === 宽判决：条件① 不满足（仍在创新 best）→ False ===

def test_still_improving_returns_false(tmp_path, stub_mp):
    """plateau_streak < K（近 K 轮仍有创新 best）→ 条件①失败 → False。"""
    _write_tsv(tmp_path, [0.85] * PARADIGM_MISMATCH_K)
    stub_mp(plateau_return=PARADIGM_MISMATCH_K - 1)  # 6 < 7
    assert check_paradigm_mismatch(tmp_path) is False


# === 宽判决：条件② 不满足（spread>=ε，declining/波动）→ False ===

def test_large_spread_returns_false(tmp_path, stub_mp):
    """近 K 轮 max-min >= ε（走势非平稳，如 declining）→ 条件②失败 → False。"""
    declining = [0.80, 0.81, 0.82, 0.83, 0.84, 0.85, 0.86]  # spread 0.06
    _write_tsv(tmp_path, declining)
    stub_mp(plateau_return=PARADIGM_MISMATCH_K)
    assert check_paradigm_mismatch(tmp_path) is False


def test_borderline_spread_at_eps_returns_false(tmp_path, stub_mp):
    """spread 恰 >= ε → 不触发（边界保守：宁可漏报）。"""
    # 0.850 与 0.855 → spread=0.005 == ε → `>= eps` True → False
    vals = [0.850, 0.850, 0.850, 0.850, 0.855, 0.855, 0.855]
    _write_tsv(tmp_path, vals)
    stub_mp(plateau_return=PARADIGM_MISMATCH_K)
    assert check_paradigm_mismatch(tmp_path) is False


# === 不出错保证（R8 原则）：异常不 raise ===

def test_metric_key_exception_does_not_raise(tmp_path, monkeypatch, stub_mp):
    """metric_key 内部异常 → 被 outer try 吞 → 返回 False（不 raise）。"""

    def _boom(_root):  # 明确抛异常（替代 generator-throw 易碎 idiom）
        raise ValueError("boom")

    _write_tsv(tmp_path, [0.85] * PARADIGM_MISMATCH_K)
    stub_mp()  # plateau 正常（条件①已过，进到 mk=metric_key(...) 抛）
    monkeypatch.setattr(rls, "metric_key", _boom)
    assert check_paradigm_mismatch(tmp_path) is False


# === nn-config 覆盖（K/ε 可配）===

def test_nn_config_k_override(tmp_path, stub_mp):
    """nn-config paradigm_mismatch.k=3 → 3 轮 flat 即触发（宽松早提醒）。"""
    save_nn_config(tmp_path, {"paradigm_mismatch": {"k": 3, "eps": 0.005}})
    _write_tsv(tmp_path, [0.85, 0.85, 0.85])  # 3 轮 == 覆盖后的 k
    stub_mp(plateau_return=3)
    assert check_paradigm_mismatch(tmp_path) is True


def test_nn_config_eps_override_widens(tmp_path, stub_mp):
    """eps 调大 → 默认阈值判「非平稳」的 spread 被纳入「平稳」→ 触发。"""
    save_nn_config(tmp_path, {"paradigm_mismatch": {"k": 7, "eps": 0.07}})
    vals = [0.80, 0.81, 0.82, 0.83, 0.84, 0.85, 0.86]  # spread 0.06
    _write_tsv(tmp_path, vals)
    stub_mp(plateau_return=PARADIGM_MISMATCH_K)
    # 默认 eps=0.005 → spread 0.06 判非平稳（False）；覆盖 eps=0.07 → 0.06<0.07 判平稳 → True
    assert check_paradigm_mismatch(tmp_path) is True


# === R1 接线：reflect_gate_decision 命中 R8 ===

def test_reflect_gate_returns_r8_on_mismatch(tmp_path, monkeypatch):
    """check_paradigm_mismatch=True → reflect_gate 返回 run:R8:paradigm_mismatch。"""
    monkeypatch.setattr(rls, "agent_reflect_flags", lambda root: (False, False))  # 非 skip/force
    monkeypatch.setattr(auto_mode, "check_paradigm_mismatch", lambda root: True)
    decision = rls.reflect_gate_decision(tmp_path, run=1, interval=1, plateau_n=3)
    assert decision == "run:R8:paradigm_mismatch"


def test_reflect_gate_no_r8_when_not_mismatch(tmp_path, monkeypatch):
    """check_paradigm_mismatch=False → 不返回 R8（落到后续 R1-R7/skip）。"""
    monkeypatch.setattr(rls, "agent_reflect_flags", lambda root: (False, False))
    monkeypatch.setattr(auto_mode, "check_paradigm_mismatch", lambda root: False)
    decision = rls.reflect_gate_decision(tmp_path, run=1, interval=1, plateau_n=3)
    assert not decision.startswith("run:R8")


def test_reflect_gate_skip_still_wins_over_r8(tmp_path, monkeypatch):
    """要求1 软警告不破 skip：reflect_skip=True → skip:* 优先于 R8。"""
    monkeypatch.setattr(rls, "agent_reflect_flags", lambda root: (False, True))  # skip
    monkeypatch.setattr(auto_mode, "check_paradigm_mismatch", lambda root: True)
    decision = rls.reflect_gate_decision(tmp_path, run=1, interval=1, plateau_n=3)
    assert decision == "skip:reflect_skip"


# === R3 接线：finalize_round 源码含 R8 串接（防半接线回归）===

def test_finalize_round_wired_to_paradigm_mismatch():
    """experiment.py 须含 check_paradigm_mismatch 调用 + paradigm_fit=MISMATCH 写盘。"""
    src = Path(__file__).resolve().parents[2].joinpath("experiment.py").read_text(encoding="utf-8")
    assert "check_paradigm_mismatch" in src
    assert 'paradigm_fit' in src and 'MISMATCH' in src


def test_reflect_gate_source_has_r8_branch():
    """run_ledger_summary.py 须含 R8 分支（防回归）。"""
    src = Path(__file__).resolve().parents[1].joinpath("lib", "run_ledger_summary.py").read_text(encoding="utf-8")
    assert "run:R8:paradigm_mismatch" in src
