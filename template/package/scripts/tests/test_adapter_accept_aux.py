"""adapter_accept 辅指标：声明键须有真值，0 合法，未声明不查。"""
from __future__ import annotations

import pytest

from lib.adapter_accept import require_declared_aux_metrics


def test_empty_declared_noop():
    require_declared_aux_metrics({}, [])
    require_declared_aux_metrics({"acc": 1.0}, [])


def test_missing_key_raises():
    with pytest.raises(ValueError, match="forgetting"):
        require_declared_aux_metrics({"acc": 0.9}, ["forgetting"])


def test_none_value_raises():
    with pytest.raises(ValueError, match="forgetting"):
        require_declared_aux_metrics({"forgetting": None}, ["forgetting"])


def test_zero_passes():
    require_declared_aux_metrics({"forgetting": 0.0}, ["forgetting"])
    require_declared_aux_metrics({"forgetting": 0}, ["forgetting"])


def test_non_numeric_raises():
    with pytest.raises(ValueError, match="forgetting"):
        require_declared_aux_metrics({"forgetting": "n/a"}, ["forgetting"])


def test_undeclared_keys_ignored():
    require_declared_aux_metrics({"acc": 0.5, "extra": None}, ["acc"])


def test_multiple_declared_all_required():
    with pytest.raises(ValueError, match="bwt"):
        require_declared_aux_metrics({"forgetting": 0.1}, ["forgetting", "bwt"])
