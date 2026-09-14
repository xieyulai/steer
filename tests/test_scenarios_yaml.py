# tests/test_scenarios_yaml.py
"""WP0.3: scenarios/<workflow>.yaml 3 文件落地 + decision_tree 自查清单。

锁以下不变量(spec v3.2 §3.4 / §4 WP0.3 / PR1 重命名 4-scenario → 3-workflow):
1. 3 个 workflow yaml 全部存在(build/update + overlay 同步)
2. 每个 yaml 必备字段:scenario_id / decision_tree / freedom_levels
3. decision_tree 每条都是 {when, do[list]} 结构(撞墙后 agent 可解析)
4. freedom_levels.E.locked == true(全场景 E 档锁定不变)
"""
from __future__ import annotations

import pathlib
import sys

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCEN_DIR = ROOT / "template" / "package" / "scenarios"
EXPECTED = {"build", "migrate", "update"}


def _load_scenario(name: str) -> dict:
    p = SCEN_DIR / f"{name}.yaml"
    assert p.is_file(), f"缺场景定义: {p}"
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def test_all_three_workflows_exist():
    """3 个 workflow yaml 必须全部存在(build/migrate/update)。"""
    found = {p.stem for p in SCEN_DIR.glob("*.yaml")}
    assert EXPECTED <= found, f"缺场景: {EXPECTED - found}"


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_scenario_required_keys(name):
    """每 yaml 必备字段:scenario_id / decision_tree / freedom_levels。"""
    sc = _load_scenario(name)
    assert sc.get("scenario_id") == name, f"scenario_id 不匹配: {sc.get('scenario_id')}"
    assert isinstance(sc.get("decision_tree"), list), "decision_tree 必须是 list"
    assert isinstance(sc.get("freedom_levels"), dict), "freedom_levels 必须是 dict"


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_scenario_e_locked(name):
    """全场景 E 档必须锁定(不变)。"""
    sc = _load_scenario(name)
    e = sc["freedom_levels"].get("E")
    assert e and e.get("locked") is True, f"{name}: E 档必须 locked=True"


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_scenario_decision_tree_structure(name):
    """decision_tree 每条: {when: str, do: list[str]}。"""
    sc = _load_scenario(name)
    dt = sc["decision_tree"]
    assert len(dt) >= 3, f"{name}: decision_tree 至少 3 条自查项,实际 {len(dt)}"
    for i, step in enumerate(dt):
        assert isinstance(step.get("when"), str) and step["when"], (
            f"{name}[{i}]: 缺 'when' 字符串"
        )
        dos = step.get("do")
        assert isinstance(dos, list) and dos, f"{name}[{i}]: 'do' 必须是 non-empty list"
        for action in dos:
            assert isinstance(action, str) and action, f"{name}[{i}]: 'do' 项必须非空 str"


def test_build_pattern_is_register_learner():
    """build 走全仓统一 register_learner 入口;无 source_root。"""
    sc = _load_scenario("build")
    assert sc.get("framework_pattern") == "register_learner"
    assert sc["recognition"].get("has_source_root") is False


def test_migrate_workspace_wrapper_branch():
    """migrate 走 patterns: 二级分流;workspace_wrapper 路径严守「无状态 + 保护 _backend_」。"""
    sc = _load_scenario("migrate")
    # recognition: source_root 与 repo 不同目录
    assert sc["recognition"].get("has_source_root") is True
    assert sc["recognition"].get("same_dir_as_repo") is False
    # patterns.workspace_wrapper.when 提 contract/ 触发条件
    assert "contract/" in sc["patterns"]["workspace_wrapper"]["when"]
    # wrapper_contract.invariant: workspace_wrapper 必须无状态
    assert "无状态" in sc["wrapper_contract"]["invariant"]
    # protected_paths 锁 _backend_/ 不可改(wrapper 路径不碰外部代码)
    assert "_backend_" in str(sc.get("protected_paths", []))


def test_update_preserves_artifacts():
    """update 同仓二次 init:保留 E 档口径(数据集/指标/seed 二 init 不允许改)。"""
    sc = _load_scenario("update")
    # recognition: 同仓
    assert sc["recognition"].get("same_dir_as_repo") is True
    # E 档仍 locked (与首 init 一致)
    assert sc["freedom_levels"]["E"].get("locked") is True
    # note 显式声明二次 init 不允许改 E 档
    assert "不允许改" in sc["freedom_levels"]["E"].get("note", "")


# init_workflow.resolve_workflow + --workflow（取代已删 init_scenarios）
@pytest.fixture(scope="module")
def init_workflow_mod():
    pkg_root = str(ROOT / "template" / "package" / "scripts")
    if pkg_root not in sys.path:
        sys.path.insert(0, pkg_root)
    import init_workflow as mod  # noqa: WPS433

    return mod


def test_resolve_workflow_no_override_auto_classify(init_workflow_mod, tmp_path):
    """无 override 时走 classify()。"""
    wf = init_workflow_mod
    assert wf.resolve_workflow(tmp_path, None) == wf.Workflow.BUILD
    src = tmp_path / "src"
    src.mkdir()
    assert wf.resolve_workflow(tmp_path, src) == wf.Workflow.MIGRATE


def test_resolve_workflow_override_takes_priority(init_workflow_mod, tmp_path):
    """--force-workflow / override 跳过自动分类。"""
    wf = init_workflow_mod
    assert wf.resolve_workflow(tmp_path, None, override="migrate") == wf.Workflow.MIGRATE
    assert wf.resolve_workflow(tmp_path, None, override="update") == wf.Workflow.UPDATE


def test_resolve_workflow_invalid_override_raises(init_workflow_mod, tmp_path):
    wf = init_workflow_mod
    with pytest.raises(ValueError, match="未知"):
        wf.resolve_workflow(tmp_path, None, override="totally-bogus")


def test_init_workflow_cli_parses(tmp_path):
    """CLI: --workflow 选项被识别。"""
    import subprocess

    cli = ROOT / "template" / "package" / "scripts" / "init_workflow.py"
    r = subprocess.run(
        ["python3", str(cli), "--repo-root", str(tmp_path), "--workflow", "build"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    assert r.stdout.strip() == "build"