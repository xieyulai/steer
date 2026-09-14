"""
契约包 — Contract 门面。

实现分布：metrics.py · runtime.py · prepare_data.py · test.py
不可变：Agent 常规迭代中不得修改本目录。
"""
from __future__ import annotations

from typing import Any

from torch.utils.data import DataLoader

from contract import prepare_data as data_entry
from contract import test as terminal_test
from contract.metrics import AUXILIARY_KEYS, METRIC_KEYS
from contract.runtime import REPRO_ENV_KEYS
from lib.metric_units import _safe_metric as _metric_units_safe_metric  # Layer 1 复用 (v1.24.0)
from contract.scenario_capacity import (
    check_scenario_capacity as _check_scenario_capacity,
    list_capacity as _list_capacity,
)
from contract.scaling_laws import apply as _scaling_apply
from experiment import ExperimentBase, TimeGuard

# TimeGuard 定义在 experiment.py；模板 train.py 可直接 from experiment import TimeGuard。
# 迁后若 train.py 仍写 from contract import TimeGuard，须在门面 re-export（见 PROTOCOL §3.0）。

class Contract(ExperimentBase):

    @property
    def metric_keys(self) -> dict[str, str]:
        return METRIC_KEYS

    @property
    def auxiliary_keys(self) -> dict[str, str]:
        return AUXILIARY_KEYS

    @property
    def repro_env_keys(self) -> tuple[str, ...]:
        return REPRO_ENV_KEYS

    def prepare_data(self, cfg: dict) -> tuple[DataLoader, DataLoader]:
        return data_entry.prepare_data(self, cfg)

    def test(
        self,
        learner,
        ws,
        *,
        shared_context: dict,
        adapter_runner: Any | None = None,
    ) -> dict[str, float]:
        """官方评估门面。评 runner 时转发 adapter_runner 至 terminal_test.run。"""
        return terminal_test.run(
            learner,
            ws,
            shared_context=shared_context,
            adapter_runner=adapter_runner,
        )

    # ── v1.24.0 Layer 2 — None-safe + 缺值兜底 ─────────────────────
    @property
    def _safe_metric(self):
        """供业务仓 contract 子类一键获取 None-safe helper。

        业务仓可写 ``return self._safe_metric(metrics.get("val_accuracy"))``
        替代手动 ``or 0.0`` / ``float(metrics[k])`` None 崩溃补丁。
        """
        return _metric_units_safe_metric

    def default_metrics(self, shared_context: dict | None) -> dict[str, float] | None:
        """非训末官方主路径（ADR-11）。

        骨架保留供业务仓实验性覆盖；官方台账分须走 ``test(..., adapter_runner=)``
        + ``ws.adapter_runner``，不要把本方法接成第二条官方出分主路径。
        基类返回 None。
        """
        return None

    # ── M1 场景容量查询（reflect 集成用，业务仓零代码）────────
    def list_capacity(self, scenario_id: str) -> dict[str, Any]:
        """返回本场景的规模参数（bits / input_dim / num_classes / ...）。
        业务仓未填表时返回空 dict（reflect 优雅跳过 M1 段）。"""
        return _list_capacity(scenario_id)

    # ── P2 preflight gate（WARN，提示业务仓填表获 M1+M2 收益）──
    def check_scenario_capacity(self, scenario_id: str) -> list[str]:
        """返回 WARN 列表。空表或无匹配 → 1 条提示，提示业务仓填 SCENARIO_CAPACITY。

        业务仓可通过设置 SCENARIO_CAPACITY_OPT_OUT=True 关闭警告。
        """
        return _check_scenario_capacity(scenario_id)

    # ── M2 经验律推荐（reflect 集成用，业务仓零代码）──────────
    def list_scaling_recommendation(
        self,
        cap: dict[str, Any],
        history_best_cap: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """根据 cap + 历史 best cap 算推荐 cfg 值 + 跨场景 delta 提示。"""
        return _scaling_apply(cap, history_best_cap)


def create_contract(cfg: dict) -> ExperimentBase:
    return Contract()


def get_test_loader(batch_size: int = 256, num_workers: int = 2) -> DataLoader:
    """向后兼容：委托 contract.test.get_test_loader。"""
    return terminal_test.get_test_loader(Contract().data_dir, batch_size=batch_size, num_workers=num_workers)
