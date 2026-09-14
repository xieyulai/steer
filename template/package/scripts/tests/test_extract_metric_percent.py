"""P1-6: _extract_metric_percent 通用抽最后一个 'X%' 或 '[label]: X%'。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_mammoth_class_il_format():
    """mammoth: 'Accuracy for N task(s): [Class-IL]: 85.94 %' → 0.8594"""
    from experiment import ExperimentBase
    text = "Accuracy for 5 task(s): [Class-IL]: 85.94 %"
    assert ExperimentBase._extract_metric_percent(text, label="Class-IL") == 0.8594


def test_standard_accuracy_format():
    """标准: 'accuracy: 0.85' → 0.85"""
    from experiment import ExperimentBase
    assert ExperimentBase._extract_metric_percent("final accuracy: 0.85") == 0.85


def test_last_percent_wins():
    """多行取最后一个 X%"""
    from experiment import ExperimentBase
    text = "epoch 1: 70.0 %\nepoch 2: 85.94 %"
    assert ExperimentBase._extract_metric_percent(text) == 0.8594


def test_no_match_returns_default():
    """无匹配 → default（None）"""
    from experiment import ExperimentBase
    assert ExperimentBase._extract_metric_percent("no metric here") is None
    assert ExperimentBase._extract_metric_percent("no metric", default=0.0) == 0.0
