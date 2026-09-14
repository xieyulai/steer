"""contract 门面测试：题面常量归位（METRIC_KEYS / AUXILIARY_KEYS）。

注：KEEP_THRESHOLD 常量与 Contract.keep_threshold property、PROTECTED_PATHS 与
Contract.protected_paths property 均已在 exploration-contract P0 撤回（零行为变更，
回退到 nn-config.yaml keep 段 / 文件级由 nn-doctor 直接守）。相关测试随之删除，
勿再加回（见 memory exploration-contract-p0-released-1.7.0）。

SCENARIO_ID 常量与 Contract.scenario_id property 已在 v1.39.2 退役；场景标识改由
init / 台账 scenario_id 列承担，contract 门面不再导出空壳占位。
"""
import sys
import pathlib

_ROOT = pathlib.Path(__file__).parent.parent
_PKG = _ROOT / "template/package"
sys.path.insert(0, str(_PKG / "scripts"))  # contract.__init__ → lib.metric_units
sys.path.insert(0, str(_PKG))

from contract.metrics import (
    AUXILIARY_KEYS,
    METRIC_KEYS,
)
from contract import Contract


def test_metric_keys_still_present():  # 回归：既有常量不动
    assert isinstance(METRIC_KEYS, dict)
    assert isinstance(AUXILIARY_KEYS, dict)


def test_contract_metric_keys_property():
    c = Contract()
    assert c.metric_keys is METRIC_KEYS
    assert c.auxiliary_keys is AUXILIARY_KEYS
