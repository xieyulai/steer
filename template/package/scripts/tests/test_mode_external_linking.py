"""spec §2:6 档 mode 联动 3 源 (paper + docs + github_impl + github_ecosystem)。

关键改进 (vs 当前 router):
- optimize 默认开 github_ecosystem (看 best practice)
- innovate+ 开 github_impl (看具体代码)
- aggressive 拉满 = 真"穷尽"

也覆盖:
- spec §5:ExternalEvidenceConfig.effective_mode 字段 + load_external_config 读 yaml
"""
from __future__ import annotations

from dataclasses import fields

from lib.external.config import ExternalEvidenceConfig, load_external_config
from lib.external.models import (
    MODE_TO_EXTERNAL,
    MODE_TO_EXTERNAL_AUTO_DEFAULT,
    mode_to_external,
)
from lib.external.router import build_external_plan, RouterContext


# === MODE_TO_EXTERNAL 表完整性 ===

def test_mode_to_external_table_careful():
    """careful:全关"""
    assert MODE_TO_EXTERNAL["careful"] == {
        "paper_depth": "P0", "docs_depth": "D0",
        "github_impl": False, "github_ecosystem": False,
    }


def test_mode_to_external_table_optimize():
    """optimize:只开 github_ecosystem"""
    assert MODE_TO_EXTERNAL["optimize"] == {
        "paper_depth": "P1", "docs_depth": "D1",
        "github_impl": False, "github_ecosystem": True,
    }


def test_mode_to_external_table_innovate():
    """innovate:双开 github"""
    assert MODE_TO_EXTERNAL["innovate"] == {
        "paper_depth": "P2", "docs_depth": "D2",
        "github_impl": True, "github_ecosystem": True,
    }


def test_mode_to_external_table_aggressive():
    """aggressive:拉满 P3/D3"""
    assert MODE_TO_EXTERNAL["aggressive"] == {
        "paper_depth": "P3", "docs_depth": "D3",
        "github_impl": True, "github_ecosystem": True,
    }


def test_mode_to_external_table_explore():
    """explore:跟 innovate 一样但 goal 不同"""
    assert MODE_TO_EXTERNAL["explore"] == {
        "paper_depth": "P2", "docs_depth": "D2",
        "github_impl": True, "github_ecosystem": True,
    }


def test_mode_to_external_auto_default_is_optimize():
    """auto 起步 optimize"""
    assert MODE_TO_EXTERNAL_AUTO_DEFAULT == "optimize"


def test_mode_to_external_lookup_invalid_falls_back_to_optimize():
    """未知 mode → optimize 兜底 (防 typo 静默走错档)"""
    assert mode_to_external("nonsense") == MODE_TO_EXTERNAL["optimize"]
    assert mode_to_external("") == MODE_TO_EXTERNAL["optimize"]
    assert mode_to_external("OPTIMIZE") == MODE_TO_EXTERNAL["optimize"]


# === build_external_plan 5 档 mode 联动 ===

def _ctx(effective_mode: str, exploration: str = "conservative", **kw) -> RouterContext:
    defaults = dict(
        tier="B",
        innovation_depth="novel",
        gate="run:R1",
        beat_best=False,
        routine_mislabel=False,
        not_attested_extend=False,
        reflect_skipped=False,
        plateau_active=False,
        config=ExternalEvidenceConfig(
            effective_mode=effective_mode, exploration=exploration
        ),
    )
    defaults.update(kw)
    return RouterContext(**defaults)


def test_build_plan_careful_no_3_sources():
    """careful mode → 3 源全关 (即使 tier=B novel — careful 强制覆盖)"""
    plan = build_external_plan(_ctx("careful"))
    assert plan.paper_depth == "P0"
    assert plan.docs_depth == "D0"
    assert plan.github_impl is False
    assert plan.github_ecosystem is False


def test_build_plan_optimize_github_ecosystem_only():
    """optimize mode → github_ecosystem=True (不开 impl)"""
    plan = build_external_plan(_ctx("optimize"))
    assert plan.paper_depth == "P1"
    assert plan.docs_depth == "D1"
    assert plan.github_impl is False
    assert plan.github_ecosystem is True


def test_build_plan_innovate_github_both():
    """innovate mode → github 双开"""
    plan = build_external_plan(_ctx("innovate"))
    assert plan.paper_depth == "P2"
    assert plan.docs_depth == "D2"
    assert plan.github_impl is True
    assert plan.github_ecosystem is True


def test_build_plan_aggressive_full():
    """aggressive mode → P3/D3 + github 双开"""
    plan = build_external_plan(_ctx("aggressive"))
    assert plan.paper_depth == "P3"
    assert plan.docs_depth == "D3"
    assert plan.github_impl is True
    assert plan.github_ecosystem is True


def test_build_plan_explore_p2_d2():
    """explore mode → 跟 innovate 一样 3 源配置"""
    plan = build_external_plan(_ctx("explore"))
    assert plan.paper_depth == "P2"
    assert plan.docs_depth == "D2"
    assert plan.github_impl is True
    assert plan.github_ecosystem is True


def test_build_plan_default_optimize_when_no_config():
    """无 config → 兜底 optimize (mode 默认)"""
    ctx = RouterContext(
        tier="B", innovation_depth="novel", gate="run:R1",
        beat_best=False, routine_mislabel=False,
        not_attested_extend=False, reflect_skipped=False,
    )
    plan = build_external_plan(ctx)
    # ExternalEvidenceConfig() 默认 effective_mode="optimize"
    assert plan.paper_depth == "P1"
    assert plan.docs_depth == "D1"
    assert plan.round_state.get("effective_mode") == "optimize"


# === 向后兼容:旧 inductive/aggressive 联动保留 ===

def test_build_plan_inductive_lifts_paper_above_mode():
    """inductive 把 paper 抬到 P2(即使 optimize 默认 P1,inductive 必查论文)"""
    plan = build_external_plan(_ctx(
        "optimize",
        exploration="inductive",
        tier="A",
        innovation_depth="routine",
    ))
    # mode=optimize → P1,inductive lift → P2
    assert plan.paper_depth == "P2"


def test_build_plan_aggressive_deepens_to_p3():
    """aggressive 把 paper 拉到 P3"""
    plan = build_external_plan(_ctx(
        "optimize",
        exploration="aggressive",
    ))
    # mode=optimize → P1,aggressive lift → P2,然后 deepen P2→P3
    assert plan.paper_depth == "P3"


def test_build_plan_round_state_records_effective_mode():
    """round_state 记录 effective_mode(spec §5:auto 必备)"""
    plan = build_external_plan(_ctx("innovate"))
    assert plan.round_state.get("effective_mode") == "innovate"


# === spec §5:ExternalEvidenceConfig.effective_mode 字段 ===

def test_external_config_has_effective_mode():
    """ExternalEvidenceConfig 加 effective_mode 字段 (spec §5)"""
    field_names = {f.name for f in fields(ExternalEvidenceConfig)}
    assert "effective_mode" in field_names


def test_external_config_default_effective_mode_is_optimize():
    """effective_mode 默认 "optimize" (无 user 显式 = optimize 起步档)"""
    cfg = ExternalEvidenceConfig()
    assert cfg.effective_mode == "optimize"


def test_load_external_config_reads_effective_mode(tmp_path):
    """load_external_config 从 yaml 读 effective_mode(auto 段下)"""
    yaml_path = tmp_path / "nn-config.yaml"
    yaml_path.write_text("auto:\n  effective_mode: innovate\n")
    cfg = load_external_config(tmp_path)
    assert cfg.effective_mode == "innovate"


def test_load_external_config_invalid_effective_mode_keeps_default(tmp_path):
    """无效 effective_mode → 保留 default optimize (防 typo)"""
    yaml_path = tmp_path / "nn-config.yaml"
    yaml_path.write_text("auto:\n  effective_mode: nonsense\n")
    cfg = load_external_config(tmp_path)
    assert cfg.effective_mode == "optimize"


def test_load_external_config_auto_itself_not_an_effective_mode(tmp_path):
    """effective_mode 不能是 "auto" 自身(防止递归:auto.effective_mode = auto)"""
    yaml_path = tmp_path / "nn-config.yaml"
    yaml_path.write_text("auto:\n  effective_mode: auto\n")
    cfg = load_external_config(tmp_path)
    # 'auto' 不在白名单,保留默认 optimize
    assert cfg.effective_mode == "optimize"


# === spec §2 + §5: render_3source_status 显式"未启用"提示 (T6) ===

def test_format_prompt_renders_3source_status_careful():
    """careful mode: 3 源全关 → 每源都显式"未启用"字样（不是 silent skip）。"""
    from lib.external.format_prompt import render_3source_status
    from lib.external.models import ExternalPlan

    plan_careful = ExternalPlan(
        schema_version=1,
        round_state={},
        paper_depth="P0", paper_hits_cap=0,
        docs_depth="D0",
        github_impl=False, github_ecosystem=False,
        budget_max_http=6,
    )
    status = render_3source_status(plan_careful)
    assert "- paper: [未启用]" in status
    assert "- docs: [未启用]" in status
    assert "- github_impl: [未启用]" in status
    assert "- github_ecosystem: [未启用]" in status


def test_format_prompt_renders_3source_status_aggressive():
    """aggressive: 3 源全开 → 每源都显式"已启用"+ 深度参数。"""
    from lib.external.format_prompt import render_3source_status
    from lib.external.models import ExternalPlan

    plan_aggr = ExternalPlan(
        schema_version=1,
        round_state={},
        paper_depth="P3", paper_hits_cap=5,
        docs_depth="D3",
        github_impl=True, github_ecosystem=True,
        budget_max_http=6,
    )
    status = render_3source_status(plan_aggr)
    assert "paper: depth=P3" in status
    assert "docs: depth=D3" in status
    assert "- github_impl: 已启用" in status
    assert "- github_ecosystem: 已启用" in status


def test_format_prompt_renders_3source_status_optimize():
    """optimize: 只开 github_ecosystem（impl=False） → github 行只有 ecosystem。"""
    from lib.external.format_prompt import render_3source_status
    from lib.external.models import ExternalPlan

    plan_opt = ExternalPlan(
        schema_version=1,
        round_state={},
        paper_depth="P1", paper_hits_cap=3,
        docs_depth="D1",
        github_impl=False, github_ecosystem=True,
        budget_max_http=6,
    )
    status = render_3source_status(plan_opt)
    assert "paper: depth=P1" in status
    assert "docs: depth=D1" in status
    assert "- github_impl: [未启用]" in status
    assert "- github_ecosystem: 已启用" in status


# === reflect_hook.format_3source_status_lines 包装层 (T6) ===

def test_reflect_hook_format_3source_status_lines_wraps_block():
    """reflect_hook.format_3source_status_lines 返回 markdown 块（包含 header + 3 行）。"""
    from lib.external.reflect_hook import format_3source_status_lines

    plan_dict = {
        "schema_version": 1,
        "round_state": {},
        "paper_depth": "P0", "paper_hits_cap": 0,
        "docs_depth": "D0",
        "github_impl": False, "github_ecosystem": False,
        "budget_max_http": 6,
    }
    block = format_3source_status_lines(plan_dict)
    assert "**外部证据源状态：**" in block
    assert "- paper: [未启用]" in block
    assert "- docs: [未启用]" in block
    assert "- github_impl: [未启用]" in block
    assert "- github_ecosystem: [未启用]" in block


def test_reflect_hook_format_3source_status_lines_none_returns_empty():
    """plan_dict None / 空 dict → 返回空字符串（调用方无需判 None）。"""
    from lib.external.reflect_hook import format_3source_status_lines

    assert format_3source_status_lines(None) == ""
    assert format_3source_status_lines({}) == ""


def test_format_prompt_paper_hits_cap_zero_unavailable():
    """paper_depth != P0 但 paper_hits_cap=0 → 仍标未启用（防 silent skip）。"""
    from lib.external.format_prompt import render_3source_status
    from lib.external.models import ExternalPlan

    plan = ExternalPlan(
        schema_version=1,
        round_state={},
        paper_depth="P3", paper_hits_cap=0,  # 拉满 depth 但 0 hits
        docs_depth="D0",
        github_impl=False, github_ecosystem=False,
        budget_max_http=6,
    )
    status = render_3source_status(plan)
    assert "- paper: [未启用]" in status
    assert "hits_cap=0" in status  # 显式说原因
