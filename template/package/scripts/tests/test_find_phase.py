"""T4/ADR-6：reflect cycle「寻找」(find) 阶段——评估(verify)的事双胞胎。

触发 = plateau ∧ depth ∈ {different, novel}（比 verify 的 _should_deepen_plateau 宽——
后者还要 not_attested_extend）。共用 router+executor channel，强制 P3+ 取全文，
捞候选改进部件 → saved/find_candidates.json（反馈边数据；catalog 落盘在 T8）。

ADR-6：寻找 = 撞墙驱动 + 深度门控。先评估（验证当前方法有无文献背书）→ 再寻找
（向外捞可借力的候选部件）。P3+ 全文 + github_ecosystem。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.external import reflect_hook
from lib.external.evidence_refs import collect_round_evidence
from lib.external.models import ExternalPlan
from lib.external.reflect_hook import (
    _extract_find_candidates,
    _force_find_plan,
    run_find_phase,
    should_run_find_phase,
)


# ── AC5：触发条件三测 ──────────────────────────────────────────────────────
def test_trigger_plateau_and_different():
    """①plateau + different → 触发寻找。"""
    assert should_run_find_phase(plateau_active=True, depth="different") is True


def test_trigger_plateau_and_novel():
    assert should_run_find_phase(plateau_active=True, depth="novel") is True


def test_no_trigger_without_plateau():
    """②非 plateau → 不触发（即使 different）。"""
    assert should_run_find_phase(plateau_active=False, depth="different") is False


def test_no_trigger_routine_or_derived():
    """③depth=routine/derived → 不触发（即使 plateau）。"""
    assert should_run_find_phase(plateau_active=True, depth="routine") is False
    assert should_run_find_phase(plateau_active=True, depth="derived") is False
    assert should_run_find_phase(plateau_active=True, depth="") is False
    assert should_run_find_phase(plateau_active=True, depth=None) is False


# ── 候选部件抽取（纯函数）──────────────────────────────────────────────────
def test_extract_candidates_from_full_bundle():
    """喂 paper hits + method_excerpt + ecosystem → 抽出候选部件。"""
    bundle = {
        "paper": {
            "hits": [
                {"title": "CoordAtt", "arxiv_id": "2103.1", "url": "http://a/1", "abstract": "x"},
                {"title": "SENet", "arxiv_id": "1709.1", "url": "http://a/2", "abstract": "y"},
            ],
            "method_excerpt": "We propose coordinate attention gating.",
            "impl_hints": ["use AdamW", "add coord conv"],
        },
        "code": {
            "routine_attestation": {
                "github_ecosystem": [
                    {"name": "coord-att-lib", "url": "http://g/1", "description": "impl"},
                ],
            },
        },
    }
    out = _extract_find_candidates(bundle, depth="different", reflect_id="r1")
    assert out["triggered"] is True
    assert out["depth"] == "different"
    assert out["reflect_id"] == "r1"
    assert out["paper_candidates"][0]["title"] == "CoordAtt"
    assert "coordinate attention" in out["method_excerpt"]
    assert "use AdamW" in out["impl_hints"]
    assert out["ecosystem_candidates"][0]["name"] == "coord-att-lib"


def test_extract_empty_bundle_no_candidates():
    """空 bundle → triggered 仍 True（已执行），但候选列表空。"""
    out = _extract_find_candidates({}, depth="different", reflect_id="r1")
    assert out["triggered"] is True
    assert out["paper_candidates"] == []
    assert out["method_excerpt"] == ""
    assert out["ecosystem_candidates"] == []
    assert out["code_candidates"] == []


# ── T9/ADR-9：linked_code → code_candidates（寻找反馈边）──────────────────────
def test_extract_candidates_includes_linked_code():
    """T9：bundle['paper']['linked_code'] → code_candidates 喂寻找反馈边。"""
    bundle = {
        "paper": {
            "hits": [],
            "linked_code": [
                {"repo": "owner/repo", "path": "README.md",
                 "url": "https://raw/owner/repo/README.md",
                 "content_excerpt": "impl notes", "bytes": 10},
            ],
        },
        "code": {"routine_attestation": {}},
    }
    out = _extract_find_candidates(bundle, depth="different", reflect_id="r1")
    assert out["code_candidates"][0]["repo"] == "owner/repo"
    assert out["code_candidates"][0]["path"] == "README.md"
    assert "impl notes" in out["code_candidates"][0]["excerpt"]


# ── _force_find_plan：强制 P3+ 全文 + github_ecosystem ─────────────────────
def test_force_find_plan_upgrades_p2_to_p3():
    """P2 plan（无 plateau deepen，无 not_attested_extend）→ 强制升 P3+ + 开 ecosystem。"""
    from lib.external.config import load_external_config
    from lib.external.router import RouterContext

    cfg = load_external_config(Path("/nonexistent-external-config"))  # default enabled=True
    ctx = RouterContext(
        tier="B",
        innovation_depth="different",
        gate="run:R2:plateau>=2",
        beat_best=False,
        routine_mislabel=False,
        not_attested_extend=False,
        reflect_skipped=False,
        rationale="",
        phase2_focus="",
        config=cfg,
        agent_depth="different",
        fingerprint_depth="different",
        plateau_active=True,
        task_domain="",
    )
    plan = _force_find_plan(ctx)
    assert plan.paper_depth in ("P3", "P4", "P5")
    assert plan.github_ecosystem is True


# ── run_find_phase 编排 ────────────────────────────────────────────────────
def _stub_plan(ctx):
    return ExternalPlan(
        schema_version=1,
        round_state={"round": 1},
        paper_depth="P2",  # 故意低于 P3，验证 _force_find_plan 升档
        paper_hits_cap=5,
        docs_depth="D2",
        github_impl=False,
        github_ecosystem=False,
        budget_max_http=10,
        queries={"paper": "attention network", "docs_symbols": []},
    )


def _fake_find_bundle(*args, **kwargs):
    return {
        "paper": {
            "hits": [{"title": "FooNet", "arxiv_id": "1", "url": "u", "abstract": "a"}],
            "method_excerpt": "We propose FooNet.",
            "impl_hints": ["hint1"],
        },
        "code": {"routine_attestation": {"github_ecosystem": []}},
    }


def test_run_find_phase_no_trigger_no_file(tmp_path, monkeypatch):
    """非 plateau → 不触发，不写 find_candidates.json，triggered=False。"""
    monkeypatch.setattr(reflect_hook, "_infer_seek_plateau_active", lambda root: False)
    out = run_find_phase(
        tmp_path,
        gate_label="skip:keep_new_best",
        last_round={"innovation_depth": "different"},
        tam_result=None,
        innovation_warnings=[],
        reflect_id="r1",
        fingerprint={"depth": "different", "enabled": True},
    )
    assert out["triggered"] is False
    assert out["paper_candidates"] == []
    assert not (tmp_path / "saved" / "find_candidates.json").is_file()


def test_run_find_phase_no_trigger_clears_stale(tmp_path, monkeypatch):
    """非触发轮清掉上一轮触发的残留 find_candidates.json（防陈旧候选泄漏下轮）。"""
    saved = tmp_path / "saved"
    saved.mkdir(parents=True)
    # 上一轮触发的残留
    (saved / "find_candidates.json").write_text(
        json.dumps({"triggered": True, "depth": "different",
                    "paper_candidates": [{"title": "StaleNet"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(reflect_hook, "_infer_seek_plateau_active", lambda root: False)
    out = run_find_phase(
        tmp_path,
        gate_label="skip:keep_new_best",
        last_round={"innovation_depth": "routine"},  # depth 降回 routine → 不触发
        tam_result=None,
        innovation_warnings=[],
        reflect_id="r2",
        fingerprint={"depth": "routine", "enabled": True},
    )
    assert out["triggered"] is False
    # 残留被清：反馈边只喂「下一轮」，陈旧候选不泄漏
    assert not (saved / "find_candidates.json").is_file()



def test_run_find_phase_triggered_writes_candidates(tmp_path, monkeypatch):
    """plateau + different → 触发：执行 forced-P3+ plan，写 find_candidates.json。"""
    monkeypatch.setattr(reflect_hook, "_infer_seek_plateau_active", lambda root: True)
    monkeypatch.setattr(reflect_hook, "build_external_plan", _stub_plan)
    monkeypatch.setattr(reflect_hook, "execute_plan", _fake_find_bundle)
    out = run_find_phase(
        tmp_path,
        gate_label="run:R2:plateau>=2",
        last_round={"innovation_depth": "different"},
        tam_result=None,
        innovation_warnings=[],
        reflect_id="r7",
        fingerprint={"depth": "different", "enabled": True},
    )
    assert out["triggered"] is True
    assert out["depth"] == "different"
    fc = tmp_path / "saved" / "find_candidates.json"
    assert fc.is_file()
    data = json.loads(fc.read_text(encoding="utf-8"))
    assert data["paper_candidates"][0]["title"] == "FooNet"


def test_run_find_phase_never_raises(tmp_path, monkeypatch):
    """find 非致命（与 verify 同模式）：执行炸了不抛，写空候选。"""
    monkeypatch.setattr(reflect_hook, "_infer_seek_plateau_active", lambda root: True)
    monkeypatch.setattr(reflect_hook, "build_external_plan", _stub_plan)

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(reflect_hook, "execute_plan", boom)
    out = run_find_phase(
        tmp_path,
        gate_label="run:R2:plateau>=2",
        last_round={"innovation_depth": "different"},
        tam_result=None,
        innovation_warnings=[],
        reflect_id="r7",
        fingerprint={"depth": "different", "enabled": True},
    )
    # 非致命：返回空候选（triggered False 表示未成功产出），不抛
    assert out.get("paper_candidates", []) == []
    assert out.get("triggered") is False


# ── AC4：find_candidates → collect_round_evidence → 下轮 run context 注入 ─
def test_collect_round_evidence_includes_find_candidates(tmp_path):
    """find_candidates.json → collect_round_evidence 带回 find_candidates 字段（注入下轮）。"""
    saved = tmp_path / "saved"
    saved.mkdir()
    (saved / "find_candidates.json").write_text(
        json.dumps(
            {
                "triggered": True,
                "depth": "different",
                "paper_candidates": [{"title": "FooNet", "url": "u"}],
            }
        ),
        encoding="utf-8",
    )
    ev = collect_round_evidence(saved)
    assert "find_candidates" in ev
    assert ev["find_candidates"]["triggered"] is True
    assert ev["find_candidates"]["paper_candidates"][0]["title"] == "FooNet"


def test_collect_round_evidence_no_find_candidates_is_empty(tmp_path):
    """无 find_candidates.json → find_candidates 字段为空（不崩）。"""
    saved = tmp_path / "saved"
    saved.mkdir()
    ev = collect_round_evidence(saved)
    assert ev["find_candidates"] == {}


# ── T5/ADR-8：寻找(find) eagerness 按 mode 走 + paper_depth 双语义锁 ──────────
def _write_mode_config(repo_root: Path, mode: str) -> Path:
    """写最小 nn-config.yaml：只含 exploration_mode（resolve_exploration 单键即可解析）。"""
    (repo_root / "nn-config.yaml").write_text(
        f"exploration_mode: {mode}\n", encoding="utf-8"
    )
    return repo_root


def test_resolve_seek_threshold_per_mode(tmp_path):
    """AC①：mode bundle 决定寻找阈值——aggressive=1 / innovate=5 / optimize=7 / careful=None。"""
    assert reflect_hook._resolve_seek_plateau_rounds(_write_mode_config(tmp_path, "aggressive")) == 1
    assert reflect_hook._resolve_seek_plateau_rounds(_write_mode_config(tmp_path, "innovate")) == 5
    assert reflect_hook._resolve_seek_plateau_rounds(_write_mode_config(tmp_path, "optimize")) == 7
    # careful 永不寻找（阈值 None）
    assert reflect_hook._resolve_seek_plateau_rounds(_write_mode_config(tmp_path, "careful")) is None


def test_resolve_seek_threshold_no_config_returns_none(tmp_path):
    """无 nn-config → None（安全默认：永不寻找；解析失败不抛）。"""
    assert reflect_hook._resolve_seek_plateau_rounds(tmp_path) is None


def test_infer_seek_plateau_active_careful_never(tmp_path, monkeypatch):
    """AC②：careful 永不寻找——seek=None，即便撞墙连环也不触发。"""
    _write_mode_config(tmp_path, "careful")
    # 故意把 plateau_streak 抬很高，careful 仍不触发（seek=None 直接短路）
    monkeypatch.setattr("lib.run_ledger_summary.plateau_streak", lambda root, n, mk=None: 999)
    assert reflect_hook._infer_seek_plateau_active(tmp_path) is False


def test_infer_seek_plateau_active_aggressive_one_round(tmp_path, monkeypatch):
    """AC①：aggressive seek=1——撞 1 轮即触发；streak=0 不触发。"""
    _write_mode_config(tmp_path, "aggressive")
    monkeypatch.setattr("lib.run_ledger_summary.plateau_streak", lambda root, n, mk=None: 1)
    assert reflect_hook._infer_seek_plateau_active(tmp_path) is True
    monkeypatch.setattr("lib.run_ledger_summary.plateau_streak", lambda root, n, mk=None: 0)
    assert reflect_hook._infer_seek_plateau_active(tmp_path) is False


def test_infer_seek_plateau_active_optimize_needs_seven(tmp_path, monkeypatch):
    """AC①补充：optimize seek=7（≠ aggressive=1）——streak=6 不触发，streak=7 才触发。
    证明 mode 调的是 find 阈值，不是全局 agent.plateau_rounds。"""
    _write_mode_config(tmp_path, "optimize")
    monkeypatch.setattr("lib.run_ledger_summary.plateau_streak", lambda root, n, mk=None: 6)
    assert reflect_hook._infer_seek_plateau_active(tmp_path) is False
    monkeypatch.setattr("lib.run_ledger_summary.plateau_streak", lambda root, n, mk=None: 7)
    assert reflect_hook._infer_seek_plateau_active(tmp_path) is True


# ── AC③④ + paper_depth 双语义锁（ADR-7）────────────────────────────────────
def test_paper_depth_dual_semantics_guard():
    """AC③④：paper_depth 兼检索强度 + 深度天花板——apply_novel_ceiling 耦锁。
    AC③ innovate=P2 → different（天花板到 different，不升 novel）；
    AC④ aggressive=P3 + supported → novel（P3 门控放行升档）。"""
    from lib.innovation_fingerprint import apply_novel_ceiling

    # AC③：P0/P2 + supported → 留 different（innovate 档天花板卡死在 different）
    assert apply_novel_ceiling("different", "supported", "P0") == "different"
    assert apply_novel_ceiling("different", "supported", "P2") == "different"
    # 弱信号（inconclusive）即便 P3 也留 different
    assert apply_novel_ceiling("different", "inconclusive", "P3") == "different"
    # AC④：P3+ 且 supported → 升 novel
    assert apply_novel_ceiling("different", "supported", "P3") == "novel"
    assert apply_novel_ceiling("different", "supported", "P5") == "novel"
    # routine/derived 透传（novel 只从 different 升，不抬 routine）
    assert apply_novel_ceiling("routine", "supported", "P3") == "routine"
    assert apply_novel_ceiling("derived", "supported", "P3") == "derived"


def test_mode_paper_depth_ladder_monotonic():
    """双语义耦合：paper_depth（检索强度）随 mode 单调升档，同时即深度天花板升档。
    careful P0 < optimize P1 < innovate P2 < aggressive P3。"""
    from lib.presets import default_for_mode

    rank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4, "P5": 5}
    ladder = {
        m: rank[default_for_mode(m)["external"]["paper_depth"]]
        for m in ("careful", "optimize", "innovate", "aggressive")
    }
    assert ladder["careful"] < ladder["optimize"] < ladder["innovate"] < ladder["aggressive"]


def test_mode_seek_eagerness_tracks_paper_depth():
    """ADR-8：寻找 eagerness 随 paper_depth 单调收紧——aggressive 最急(1) < innovate(5) < optimize(7)，
    careful=None 永不找。eagerness 与 paper_depth 阶梯同向（更深的检索强度 = 更早寻找）。"""
    from lib.presets import default_for_mode

    def seek(m):
        return default_for_mode(m)["external"]["seek_plateau_rounds"]

    assert seek("careful") is None
    # 越激进，撞墙阈值越小（越早触发寻找）
    assert seek("aggressive") < seek("innovate") < seek("optimize")
