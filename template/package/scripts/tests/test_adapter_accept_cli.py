"""adapter_accept CLI helpers：空串省略、0 保留、argv 空值硬闸。"""
from __future__ import annotations

import pytest

from lib.adapter_accept import (
    append_cfg_cli,
    assert_cli_argv_no_empty_values,
    is_empty_cli_value,
)


def test_is_empty():
    assert is_empty_cli_value(None) and is_empty_cli_value("") and is_empty_cli_value("  ")
    assert not is_empty_cli_value(0) and not is_empty_cli_value("0") and not is_empty_cli_value(False)


def test_append_skips_empty_keeps_zero():
    args: list[str] = []
    append_cfg_cli(
        args,
        {"ALPHA": "", "BETA": "  ", "LR": 0.1, "SEED": 0},
        {"ALPHA": "alpha", "BETA": "beta", "LR": "lr", "SEED": "seed"},
    )
    assert args == ["--lr", "0.1", "--seed", "0"]


def test_append_skips_missing_keys():
    args: list[str] = []
    append_cfg_cli(args, {"LR": 0.01}, {"LR": "lr", "MISSING": "missing"})
    assert args == ["--lr", "0.01"]


def test_assert_rejects_empty_flag_value():
    with pytest.raises(ValueError, match="empty"):
        assert_cli_argv_no_empty_values(["python", "main.py", "--alpha", ""])
