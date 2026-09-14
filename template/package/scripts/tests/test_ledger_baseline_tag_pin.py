"""ledger_context_keys 强制并入 baseline_tag。"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

PKG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PKG))

from experiment import ExperimentBase  # noqa: E402


def test_ledger_pins_baseline_tag_when_watchlist_omits(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "nn-config.yaml").write_text(
        yaml.safe_dump({"ledger": {"watchlist": ["LR", "EPOCHS"]}}),
        encoding="utf-8",
    )

    class C(ExperimentBase):
        @property
        def metric_keys(self):
            return {"acc": "maximize"}

    cols = C()._default_tsv_columns()
    assert "baseline_tag" in cols
    assert "exploration_space" in cols
    assert "LR" in cols
    assert "baseline_tag" in C().ledger_context_keys
    assert "exploration_space" in C().ledger_context_keys


def test_ledger_pins_when_no_watchlist(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # 无 nn-config → 空 watchlist → 仍有 baseline_tag / exploration_space

    class C(ExperimentBase):
        @property
        def metric_keys(self):
            return {"acc": "maximize"}

    assert "baseline_tag" in C().ledger_context_keys
    assert "exploration_space" in C().ledger_context_keys
    assert "baseline_tag" in C()._default_tsv_columns()
    assert "exploration_space" in C()._default_tsv_columns()
