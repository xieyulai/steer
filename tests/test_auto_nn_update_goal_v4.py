"""tests/test_auto_nn_update_goal_v4.py — auto-nn-update.sh inline Python v4 goal 对齐 (2026-07-07)"""
import re
import subprocess
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "template" / "package" / "scripts" / "auto-nn-update.sh"


def test_inline_python_uses_load_nn_config_not_raw_safe_load():
    """auto-nn-update.sh 不能再 raw yaml.safe_load nn-config.yaml"""
    text = SCRIPT.read_text(encoding="utf-8")
    # raw yaml.safe_load + 'nn-config.yaml' in auto-nn-update.sh → 应 0 命中
    # (注意:auto-nn-update.sh 可能含其他 yaml.safe_load,但读 nn-config.yaml 应 0 命中)
    raw_with_nncfg = re.findall(r"yaml\.safe_load[^\n]*\n[^\n]*nn-config\.yaml", text)
    assert len(raw_with_nncfg) == 0, (
        f"auto-nn-update.sh 仍 raw yaml.safe_load nn-config.yaml:\n{raw_with_nncfg}"
    )


def test_inline_python_uses_load_nn_config_function():
    """auto-nn-update.sh inline Python 应 import + 调 load_nn_config"""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "load_nn_config" in text, "auto-nn-update.sh inline Python 缺 load_nn_config 引用"


def test_inline_python_reads_goal_target_and_per_scenario():
    """v4 schema 字段:goal.target / goal.per_scenario"""
    text = SCRIPT.read_text(encoding="utf-8")
    # 至少含 goal.target 字段读
    assert "goal.get(\"target\")" in text or "goal.get('target')" in text, (
        "auto-nn-update.sh inline Python 未读 goal.target"
    )
    assert "goal.get(\"per_scenario\")" in text or "goal.get('per_scenario')" in text, (
        "auto-nn-update.sh inline Python 未读 goal.per_scenario"
    )


def test_inline_python_no_v3_agent_goal_value_residual():
    """v3 agent.goal_value / agent.scenario_goals 不再硬读"""
    text = SCRIPT.read_text(encoding="utf-8")
    # 找 auto-nn-update.sh 内出现的 agent.goal_value 或 agent.scenario_goals
    v3_residual = re.findall(r"agent\.(goal_value|scenario_goals)", text)
    # 若有 inline Python 显式读 v2 alias 是 allowed(compatibility);不算残留
    # 残留硬读:应该只有 load_nn_config back-fill 一处
    # 简化:若出现 ≥ 2 次, 可能有多处直接 dump; 1 次可能是 v2 兼容
    if len(v3_residual) > 1:
        pytest.fail(f"auto-nn-update.sh 多处硬读 v2 字段:\n{v3_residual}")