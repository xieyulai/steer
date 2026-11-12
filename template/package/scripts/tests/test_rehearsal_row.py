"""正式成绩计算跳过 exploration_space=E-rehearsal 的预演行。"""
from __future__ import annotations

import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PKG))
sys.path.insert(0, str(PKG / "scripts"))

from experiment import _LEDGER_OVERLAY_KEYS, _history_best_metric  # noqa: E402
from lib.exploration_stamp import is_trained_row  # noqa: E402
from lib.rehearsal_row import is_rehearsal_row  # noqa: E402
from lib.run_ledger_summary import (  # noqa: E402
    _best_row_for_scenario,
    _plateau_streak_for_scenario,
    best_tsv_row,
)

_TSV_HEADER = (
    "experiment\tscenario_id\tsgcs\trehearsal_score\texploration_space\telapsed_sec"
)


def _write_tsv(root: Path, lines: list[str]) -> None:
    runs = root / "_runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "results.tsv").write_text(
        _TSV_HEADER + "\n" + "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def test_is_rehearsal_row_matches_cell():
    assert is_rehearsal_row({"exploration_space": "E-rehearsal"}) is True
    assert is_rehearsal_row({"exploration_space": "  E-rehearsal  "}) is True
    assert is_rehearsal_row({"exploration_space": "A-routine"}) is False
    assert is_rehearsal_row({}) is False


def test_best_row_skips_rehearsal_even_if_score_higher(tmp_path: Path):
    """同场景正式 0.80；预演主指标空、rehearsal_score=0.90；另有恶意填了 0.99 的预演行。"""
    _write_tsv(
        tmp_path,
        [
            "formal\tdefault\t0.80\t\tA-routine\t10",
            "reh\tdefault\t\t0.90\tE-rehearsal\t100",
            "reh_evil\tdefault\t0.99\t0.99\tE-rehearsal\t100",
        ],
    )
    row = _best_row_for_scenario(tmp_path, "default", "sgcs", "maximize")
    assert row is not None
    assert row["experiment"] == "formal"


def test_best_tsv_row_skips_rehearsal_across_scenarios(tmp_path: Path):
    """跨场景兜底也不认预演行，哪怕主指标被填成更高的数。"""
    _write_tsv(
        tmp_path,
        [
            "formal\tdefault\t0.80\t\tA-routine\t10",
            "reh_other\tother\t0.99\t0.99\tE-rehearsal\t100",
        ],
    )
    row = best_tsv_row(tmp_path, "sgcs", "maximize")
    assert row is not None
    assert row["experiment"] == "formal"


def test_is_trained_row_rejects_rehearsal():
    assert is_trained_row(
        {"exploration_space": "E-rehearsal", "elapsed_sec": "100", "sgcs": ""},
        metric_key="sgcs",
    ) is False


def test_plateau_streak_filters_rehearsal_before_window(tmp_path: Path):
    """窗口里夹预演空主指标时，连续段按去掉该行后的正式读数算，空格不当断档。

    plateau_n=5 → 切片宽 8。9 行里第 8 行是预演：若不先过滤，切片会挤掉更早的
    正式最高分，撞墙 streak 变成 0；先过滤则最高分仍在窗口内。
    """
    plateau_n = 5
    lines = ["exp_best\tdefault\t0.90\t\tA-routine\t10"]
    for i in range(6):
        lines.append(f"exp_{i}\tdefault\t0.70\t\tA-routine\t10")
    lines.append("reh\tdefault\t\t0.90\tE-rehearsal\t100")
    lines.append("exp_tail\tdefault\t0.70\t\tA-routine\t10")
    _write_tsv(tmp_path, lines)

    streak = _plateau_streak_for_scenario(tmp_path, "default", plateau_n, mk="sgcs")
    assert streak == 7


def test_history_best_metric_skips_rehearsal_even_if_primary_filled():
    history = [
        {"experiment": "formal", "sgcs": "0.80", "exploration_space": "A-routine"},
        {
            "experiment": "reh",
            "sgcs": "",
            "rehearsal_score": "0.90",
            "exploration_space": "E-rehearsal",
        },
    ]
    assert _history_best_metric(history, "sgcs", "maximize") == 0.80

    history.append(
        {
            "experiment": "reh_evil",
            "sgcs": "0.99",
            "rehearsal_score": "0.99",
            "exploration_space": "E-rehearsal",
        }
    )
    assert _history_best_metric(history, "sgcs", "maximize") == 0.80


def test_ledger_overlay_includes_rehearsal_score():
    assert "rehearsal_score" in _LEDGER_OVERLAY_KEYS
