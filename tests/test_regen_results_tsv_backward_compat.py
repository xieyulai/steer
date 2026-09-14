"""tests/test_regen_results_tsv_backward_compat.py — Legacy Contract override path.

After v3 ledger-watchlist migration (1.2.0):
- experiment.py reads YAML first, falls back to Contract override
- regen_results_tsv.py stays contract-only (backward compat — legacy business repos)

This test guards the legacy path: if Contract.ledger_context_keys is set, _build_row must
produce columns for those keys; if empty, must not explode.
"""
import sys
import pathlib
from types import SimpleNamespace

import pytest

# regen_results_tsv.py lives in template/package/scripts/
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "template" / "package" / "scripts"))


def _make_contract(ledger_keys: tuple[str, ...] = ()) -> SimpleNamespace:
    """最小 Contract mock — 只含 regen_results_tsv 读得到的字段"""
    return SimpleNamespace(
        metric_keys={"val_accuracy": "max", "val_loss": "min"},
        auxiliary_keys={},
        ledger_context_keys=ledger_keys,
    )


def test_legacy_contract_override_yields_columns():
    """老业务仓：Contract.ledger_context_keys 设了 → _build_row 输出对应列"""
    from regen_results_tsv import _build_row
    contract = _make_contract(ledger_keys=("LR", "BATCH_SIZE"))
    header = ["experiment", "val_accuracy", "LR", "BATCH_SIZE", "notes"]
    old = {
        "experiment": "exp_test",
        "val_accuracy": "0.85",
        "description": "finalize_round",
        "exp_dir": "",  # empty → 不触发 _should_backfill_metrics 的文件检查
        "notes": "",
    }
    row = _build_row(header, old, contract)
    # LR / BATCH_SIZE 列必须存在（即使值空）
    assert "LR" in row
    assert "BATCH_SIZE" in row
    # legacy path 不读 YAML；列存在即视为 PASS


def test_empty_contract_ledger_no_explosion():
    """Contract.ledger_context_keys 空 → _build_row 不抛异常"""
    from regen_results_tsv import _build_row
    contract = _make_contract(ledger_keys=())
    header = ["experiment", "val_accuracy", "notes"]
    old = {
        "experiment": "exp_test",
        "val_accuracy": "0.85",
        "description": "",
        "notes": "",
    }
    row = _build_row(header, old, contract)
    # 不应抛异常；row 至少有 experiment + val_accuracy
    assert row["experiment"] == "exp_test"
    assert "val_accuracy" in row


def test_legacy_metric_column_populated_from_old():
    """老 Contract metric_keys 列从 old 取值（无 results.json 回填时）"""
    from regen_results_tsv import _build_row
    # 这里不测 disjoint；只测 _build_row 不会因 mock overlap crash
    contract = SimpleNamespace(
        metric_keys={"val_acc": "max"},
        auxiliary_keys={},
        ledger_context_keys=(),
    )
    header = ["experiment", "val_acc", "notes"]
    old = {
        "experiment": "exp_test",
        "val_acc": "0.85",
        "description": "",
        "notes": "",
    }
    row = _build_row(header, old, contract)
    # val_acc 列必须存在；值可能从 metrics 或 old 取（空 exp_dir → metrics={}, 走 old 路径）
    assert "val_acc" in row
    assert row["val_acc"] == "0.85"