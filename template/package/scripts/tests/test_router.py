"""router.py 单测：tier+depth+gate+beat_best 决策矩阵。"""
from __future__ import annotations
import dataclasses

from lib.external.config import ExternalEvidenceConfig
from lib.external.router import RouterContext, build_external_plan


def _ctx(**kw) -> RouterContext:
    defaults = dict(
        tier="B",
        innovation_depth="novel",
        gate="R5:normal",
        beat_best=False,
        routine_mislabel=False,
        not_attested_extend=False,
        reflect_skipped=False,
        plateau_active=False,
    )
    defaults.update(kw)
    return RouterContext(**defaults)


def test_tier_exhaust_kw_with_beat_best_runs_external():
    """gate=R5:tier_exhaust_kw + beat_best=True 仍需外部检索（不能 beat_best 短路）。"""
    plan = build_external_plan(_ctx(
        gate="R5:tier_exhaust_kw",
        beat_best=True,
    ))
    assert plan.paper_depth != "P0"
    assert "tier_exhaust" not in plan.round_state.get("router_reason", "")


def test_not_attested_extend_runs_external():
    """未举证 extend/novel tier 表示 TAM 缺证据，外部文献可补——不应 beat_best 短路。"""
    plan = build_external_plan(_ctx(
        gate="R5:normal",
        beat_best=True,
        not_attested_extend=True,
    ))
    assert plan.paper_depth != "P0"


def test_beat_best_alone_still_off_plan():
    """regression：beat_best 单独 + 正常 gate + 未未举证的 tier → 仍 _off_plan(P0)。"""
    plan = build_external_plan(_ctx(
        gate="R5:normal",
        beat_best=True,
        not_attested_extend=False,
    ))
    assert plan.paper_depth == "P0"
    assert plan.round_state.get("router_reason") == "beat_best"


def test_plateau_active_still_runs_with_deepen():
    """regression：plateau gate 仍触发外部检索 (paper 不退到 P0)。
    deepen 仅在 not_attested_extend 时才升到 P3。
    spec §2 加 mode 联动后:optimize 默认 P1,plateau 不带 not_attested_extend → 保持 P1。
    """
    plan = build_external_plan(_ctx(
        gate="R3:plateau",
        plateau_active=True,
        innovation_depth="novel",
        not_attested_extend=False,
    ))
    # spec §2:optimize 默认 P1;not_attested_extend=False 不触发 deepen → P1
    assert plan.paper_depth == "P1"
    assert plan.paper_depth != "P0"  # regression:仍触发外部检索


def test_matrix_b_novel_yields_mode_optimize_defaults():
    """(B, novel) 默认 effective_mode=optimize → spec §2 P1/D1/False/True。
    matrix 仍提供 tier×depth 推理,但 mode 表覆盖 emission(spec §2 是 canonical)。
    """
    plan = build_external_plan(_ctx(
        tier="B",
        innovation_depth="novel",
        gate="R5:manual:reflect",
    ))
    assert plan.paper_depth == "P1"
    assert plan.docs_depth == "D1"
    assert plan.github_impl is False
    assert plan.github_ecosystem is True


def test_exploration_inductive_bypasses_beat_best():
    # (B, novel, beat_best=True, inductive) → must NOT short-circuit → matrix (B,novel)=P2
    ctx = RouterContext(
        tier="B", innovation_depth="novel", gate="R5:normal",
        beat_best=True, routine_mislabel=False, not_attested_extend=False,
        reflect_skipped=False, plateau_active=False,
        config=ExternalEvidenceConfig(exploration="inductive"),
    )
    plan = build_external_plan(ctx)
    assert plan.paper_depth == "P2"
    assert plan.round_state.get("router_reason") != "beat_best"


def test_exploration_aggressive_bypasses_and_deepens_to_p3():
    # (B, novel, beat_best=True, aggressive) → bypass + P2→P3
    ctx = RouterContext(
        tier="B", innovation_depth="novel", gate="R5:normal",
        beat_best=True, routine_mislabel=False, not_attested_extend=False,
        reflect_skipped=False, plateau_active=False,
        config=ExternalEvidenceConfig(exploration="aggressive"),
    )
    plan = build_external_plan(ctx)
    assert plan.paper_depth == "P3"


def test_exploration_conservative_still_short_circuits_on_beat_best():
    # regression: conservative + beat_best + normal gate → P0 (existing behavior preserved)
    ctx = RouterContext(
        tier="B", innovation_depth="novel", gate="R5:normal",
        beat_best=True, routine_mislabel=False, not_attested_extend=False,
        reflect_skipped=False, plateau_active=False,
        config=ExternalEvidenceConfig(exploration="conservative"),
    )
    plan = build_external_plan(ctx)
    assert plan.paper_depth == "P0"
    assert plan.round_state.get("router_reason") == "beat_best"


def test_exploration_balanced_uses_existing_bypass():
    # balanced + beat_best + tier_exhaust gate → bypass (fix 4 path) → plan 仍跑 (paper != P0)
    ctx = RouterContext(
        tier="B", innovation_depth="novel", gate="R5:tier_exhaust_kw",
        beat_best=True, routine_mislabel=False, not_attested_extend=False,
        reflect_skipped=False, plateau_active=False,
        config=ExternalEvidenceConfig(exploration="balanced"),
    )
    plan = build_external_plan(ctx)
    assert plan.paper_depth != "P0"  # bypass 仍跑,paper 走 mode optimize = P1
    assert plan.round_state.get("router_reason") != "beat_best"


def test_exploration_aggressive_routine_lifts_p0_to_p3():
    # 沙箱 demo 抓到的 bug：(B, routine, aggressive, beat_best) matrix 给 P0；
    # aggressive 必须抬到 P3（floor P0→P2 + deepen P2→P3），否则 routine 档不查论文。
    ctx = RouterContext(
        tier="B", innovation_depth="routine", gate="R5:normal",
        beat_best=True, routine_mislabel=False, not_attested_extend=False,
        reflect_skipped=False, plateau_active=False,
        config=ExternalEvidenceConfig(exploration="aggressive"),
    )
    plan = build_external_plan(ctx)
    assert plan.paper_depth == "P3"


def test_exploration_inductive_routine_lifts_p0_to_p2():
    # (A, routine, inductive, beat_best) matrix 给 P0；inductive 抬到 P2（必查论文，但不拉满 P3）
    ctx = RouterContext(
        tier="A", innovation_depth="routine", gate="R5:normal",
        beat_best=True, routine_mislabel=False, not_attested_extend=False,
        reflect_skipped=False, plateau_active=False,
        config=ExternalEvidenceConfig(exploration="inductive"),
    )
    plan = build_external_plan(ctx)
    assert plan.paper_depth == "P2"


# ── RDDN migrate (T2)：_DEPTH_MATRIX 升 5×4=20；extend 退役、derived 镜像旧 extend ──
def test_depth_matrix_is_5x4_20():
    """contract：A-E × routine/derived/different/novel = 20 条；无 extend key。"""
    from lib.external.router import _DEPTH_MATRIX

    tiers = {k[0] for k in _DEPTH_MATRIX}
    depths = {k[1] for k in _DEPTH_MATRIX}
    assert tiers == {"A", "B", "C", "D", "E"}
    assert depths == {"routine", "derived", "different", "novel"}
    assert "extend" not in depths
    assert len(_DEPTH_MATRIX) == 20


def test_router_tolerates_different_depth():
    """contract：different 合法，normal gate 下不被 beat_best 短路、不崩。"""
    plan = build_external_plan(_ctx(innovation_depth="different"))
    assert plan.paper_depth != "P0"


def test_router_tolerates_derived_depth():
    plan = build_external_plan(_ctx(innovation_depth="derived"))
    assert plan.paper_depth != "P0"


def test_router_different_mirrors_novel_on_plateau_deepen():
    """(B, different, plateau, not_attested) 与 (B, novel, ...) 同档 → 同 paper_depth。"""
    novel = build_external_plan(_ctx(
        gate="R5:plateau", innovation_depth="novel", not_attested_extend=True,
    ))
    diff = build_external_plan(_ctx(
        gate="R5:plateau", innovation_depth="different", not_attested_extend=True,
    ))
    assert diff.paper_depth == novel.paper_depth
    assert diff.paper_depth != "P0"


def test_router_derived_does_not_plateau_deepen():
    """ADR-6：derived（旧 extend）不再触发 plateau-deepen——只有 different/novel 找。
    derived+plateau+not_attested 与 routine+plateau+not_attested 同 paper_depth（都不 deepen）。
    """
    derived = build_external_plan(_ctx(
        gate="R5:plateau", innovation_depth="derived", not_attested_extend=True,
    ))
    routine = build_external_plan(_ctx(
        gate="R5:plateau", innovation_depth="routine", not_attested_extend=True,
    ))
    assert derived.paper_depth == routine.paper_depth
