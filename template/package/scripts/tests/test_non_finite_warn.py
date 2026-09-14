"""B3: record_train_epoch 每调用一次做轻量 nan/inf 实时检查（WARN，不阻断）。

背景：训练中 loss 变 NaN 不会报警、不会停训，NaN 被静默吞成空格进 series；
只有训末 train_dynamics 扫字面量才标记 non_finite。本测试锁定修复后行为：
record_train_epoch 拿到 train_metrics 后、写盘前，对标量值做一次 non-finite
检查，命中即 WARN（不阻断写盘 / 不阻断训练）。非标量值跳过。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from experiment import ExperimentBase  # noqa: E402


class _Stub(ExperimentBase):
    """最小子类：record_metrics 空操作（不写盘），只测检查逻辑。"""

    def record_metrics(self, *args, **kwargs):  # noqa: D401
        pass  # optional: 测试不落盘


def test_nan_train_loss_warns(capsys):
    base = _Stub()
    base._warn_non_finite_metrics({"train_loss": float("nan")}, epoch=3)
    err = capsys.readouterr().err
    assert "WARNING" in err
    assert "non-finite" in err
    assert "train_loss" in err
    assert "epoch 3" in err


def test_inf_value_warns(capsys):
    base = _Stub()
    base._warn_non_finite_metrics({"train_loss": float("inf")}, epoch=1)
    err = capsys.readouterr().err
    assert "WARNING" in err and "train_loss" in err


def test_finite_no_warn(capsys):
    base = _Stub()
    base._warn_non_finite_metrics({"train_loss": 0.5, "acc": 0.9}, epoch=1)
    assert capsys.readouterr().err == ""


def test_non_scalar_skipped(capsys):
    """非标量（str/dict）→ float() 失败跳过，不抛、不 WARN。"""
    base = _Stub()
    base._warn_non_finite_metrics(
        {"train_loss": 0.5, "note": "x", "comp": {"a": 1}}, epoch=1
    )
    assert capsys.readouterr().err == ""


def test_record_train_epoch_triggers_check(tmp_path, capsys):
    """接线：record_train_epoch 传入 nan train_loss → 触发 WARN（不阻断）。"""
    base = _Stub()
    base.record_train_epoch(str(tmp_path), 5, {"train_loss": float("nan")}, optimizer=None)
    err = capsys.readouterr().err
    assert "WARNING" in err and "non-finite" in err and "epoch 5" in err
