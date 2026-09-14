"""B2: _train_metrics_for_series 自动纳入未声明的 loss 分量 + 首次 WARN。

背景：子类 loss_log_keys 默认空元组；agent 在 train_step 新增 loss 分量（如 cls_loss）
忘声明时，旧逻辑静默丢弃，曲线缺失。本测试锁定修复后行为：疑似 loss 分量自动纳入，
首次发现 WARN 一次，非标量跳过不阻断。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from experiment import ExperimentBase  # noqa: E402


class _Stub(ExperimentBase):
    """最小子类：只 override loss_log_keys。"""

    @property
    def loss_log_keys(self) -> tuple[str, ...]:
        return ("reg_loss",)  # 声明了 reg_loss，没声明 cls_loss


def test_undeclared_loss_key_autocaptured():
    """key 名含 loss 但未声明 → 自动纳入。"""
    base = _Stub()
    row = base._train_metrics_for_series(
        {"train_loss": 0.5, "reg_loss": 0.1, "cls_loss": 0.3, "acc": 0.9},
        optimizer=None,
    )
    assert "train_loss" in row
    assert row["reg_loss"] == 0.1          # 已声明 → 正常纳入
    assert row["cls_loss"] == 0.3          # 未声明但含 loss → 自动纳入（B2 修复）
    assert "acc" not in row                # 非 loss → 不纳入


def test_non_loss_key_not_captured():
    """不含 loss 的 key（grad_norm/throughput）→ 不纳入。"""
    base = _Stub()
    row = base._train_metrics_for_series(
        {"train_loss": 0.5, "grad_norm": 1.2, "throughput": 100},
        optimizer=None,
    )
    assert "grad_norm" not in row
    assert "throughput" not in row


def test_warn_once_per_key(capsys):
    """同一未声明 loss key 只 WARN 一次。"""
    base = _Stub()
    base._train_metrics_for_series({"train_loss": 0.5, "cls_loss": 0.3}, optimizer=None)
    err1 = capsys.readouterr().err
    assert "cls_loss" in err1 and "WARNING" in err1
    # 第二次同 key 不再 WARN
    base._train_metrics_for_series({"train_loss": 0.4, "cls_loss": 0.2}, optimizer=None)
    err2 = capsys.readouterr().err
    assert "cls_loss" not in err2


def test_non_scalar_loss_skipped():
    """非标量 loss 分量（dict）→ float() 失败 → 跳过，不阻断。"""
    base = _Stub()
    row = base._train_metrics_for_series(
        {"train_loss": 0.5, "loss_components": {"a": 1}},
        optimizer=None,
    )
    assert "loss_components" not in row
    assert row["train_loss"] == 0.5        # 其它正常纳入不受影响
