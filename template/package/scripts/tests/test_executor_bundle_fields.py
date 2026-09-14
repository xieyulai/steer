"""P1-7: bundle 落盘 plan 字段非 None（paper_depth/docs_depth/github_ecosystem/paper_hits_cap）。

csi 实测：reflect.py 落盘 saved/external_evidence/{reflect_id}.json 时，
bundle 里 paper_depth=None / github_ecosystem=None，但 plan 对象本身有值。
修法：empty_bundle 内填 bundle['plan']（single chokepoint，execute_plan 主路径/dry_run
+ reflect_hook disabled/except 4 路径全覆盖）。

ExternalPlan 真实字段（lib/external/models.py）：
  schema_version / round_state / paper_depth / paper_hits_cap / docs_depth /
  github_impl / github_ecosystem / budget_max_http / queries
（spec 假设的 tier / innovation_depth / gate 不是 ExternalPlan 字段，故不测）。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.external.models import ExternalPlan, empty_bundle
from lib.external.executor import execute_plan


def _make_plan(*, paper_depth="P3", docs_depth="D2", github_ecosystem=True,
               github_impl=False, paper_hits_cap=5) -> ExternalPlan:
    return ExternalPlan(
        schema_version=1,
        round_state={"round": 1},
        paper_depth=paper_depth,
        paper_hits_cap=paper_hits_cap,
        docs_depth=docs_depth,
        github_impl=github_impl,
        github_ecosystem=github_ecosystem,
        budget_max_http=10,
        queries={},
    )


def test_bundle_has_plan_fields_when_off():
    """all_off（dry_run）时 bundle 仍含 plan 字段。"""
    plan = _make_plan(paper_depth="P0", docs_depth="D0",
                      github_impl=False, github_ecosystem=False)
    bundle = execute_plan(plan, dry_run=True)
    plan_section = bundle.get("plan") or {}
    assert plan_section.get("paper_depth") == "P0", \
        f"FAIL paper_depth={plan_section.get('paper_depth')}"
    assert plan_section.get("docs_depth") == "D0"
    assert plan_section.get("github_ecosystem") is False
    assert plan_section.get("paper_hits_cap") is not None


def test_bundle_has_plan_fields_when_active():
    """非 dry_run、非 all_off 主路径 bundle 也含 plan 字段。"""
    plan = _make_plan(paper_depth="P3", docs_depth="D2",
                      github_ecosystem=True, github_impl=False, paper_hits_cap=5)
    # has_serper=False 避免真实 http；paper_depth=P3 会走 _run_paper_no_serper
    # 但 search_arxiv 可能真实调用 — 用 all_off 之外的安全路径：
    # 改 budget_max_http=0 让所有 provider 进 budget_exceeded，0 http 调用
    plan.budget_max_http = 0
    bundle = execute_plan(plan, dry_run=False, has_serper=False)
    plan_section = bundle.get("plan") or {}
    assert plan_section.get("paper_depth") == "P3", \
        f"FAIL paper_depth={plan_section.get('paper_depth')}"
    assert plan_section.get("docs_depth") == "D2"
    assert plan_section.get("github_ecosystem") is True
    assert plan_section.get("paper_hits_cap") == 5


def test_bundle_plan_section_full_fields():
    """plan 字段含全部 ExternalPlan 关键属性（不丢 github_impl / budget_max_http）。"""
    plan = _make_plan()
    bundle = execute_plan(plan, dry_run=True)
    plan_section = bundle.get("plan") or {}
    assert plan_section.get("github_impl") is False
    assert plan_section.get("budget_max_http") == 10


def test_empty_bundle_has_plan_section():
    """empty_bundle 直接测：reflect_hook disabled/except 路径也带 plan 字段。

    reflect_hook.run_external_evidence_phase 的 cfg.enabled=False 与 except 兜底
    两路径都直接调 empty_bundle(...)，不经 execute_plan。empty_bundle 必须自带
    bundle['plan']，否则 saved/external_evidence/{reflect_id}.json 仍丢 plan 字段。
    本测试覆盖 I-1（disabled/except 路径）。
    """
    plan = _make_plan()
    # 普通 empty_bundle（disabled 路径）
    bundle = empty_bundle(plan=plan, reflect_id="r99")
    plan_section = bundle.get("plan") or {}
    assert plan_section.get("paper_depth") == "P3", \
        f"FAIL paper_depth={plan_section.get('paper_depth')}"
    assert plan_section.get("docs_depth") == "D2"
    assert plan_section.get("github_ecosystem") is True
    assert plan_section.get("github_impl") is False
    assert plan_section.get("paper_hits_cap") == 5
    assert plan_section.get("budget_max_http") == 10
    assert plan_section.get("queries") == {}
    # 带 error 的 empty_bundle（except 兜底路径）
    bundle_err = empty_bundle(plan=plan, reflect_id="r99", error="boom")
    assert bundle_err.get("meta", {}).get("error") == "boom"
    assert bundle_err["plan"]["paper_depth"] == "P3"
