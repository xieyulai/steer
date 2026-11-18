"""nn_audit pipeline 种子/消融编排回归测试（P0/P1/P2 扩展，2026-11-18）。

覆盖：
- 默认行为不变（多种子 = extra_seeds[1:]，消融每键 1 种子、无后缀名）
- ablation_n_seeds > 1：每键多种子、首个无后缀、其余 _s<seed>
- ablation_keys_override：显式清单绕过新不新自动选键
- seeds_override：显式种子列表去重基准种子、顺序保持
- write_card 落 runs.tsv（机器可读行清单，不入成绩表）
- CLI 新参数解析
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from template.package.scripts import nn_audit
from template.package.scripts.lib.audit_attest import AttestResult
from template.package.scripts.lib.audit_core import AuditTarget, extra_seeds


def _mk_target(orig_seed: int = 2) -> AuditTarget:
    return AuditTarget(
        scenario_id="demo",
        audited_exp_dir="_runs/exp/demo_orig",
        config_sha256="deadbeef" * 8,
        original_seed=orig_seed,
        original_primary=0.5,
        metric_key="sgcs",
        metric_direction="maximize",
    )


def _mk_attest(depth: str = "novel", keys: list[str] | None = None) -> AttestResult:
    return AttestResult(
        fp_depth="composition",
        attested_depth=depth,
        search_claimed_depth="composition",
        paper_verdict=depth,
        baseline_kind="none",
        primary_keys_changed={},
        ablation_keys=list(keys or []),
        ablation_planned=bool(keys),
        ablation_skip_reason="",
        fingerprint={},
    )


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """打桩 pipeline 外部依赖；返回 (repo_root, arms 收集器)。"""
    root = tmp_path
    (root / "_runs" / "exp" / "demo_orig").mkdir(parents=True)
    calls: list[dict] = []

    def fake_run_arm(repo_root, config_path, experiment, *, runner=None, card_dir=None):
        cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
        exp_dir = root / "_runs" / "exp" / str(experiment)
        exp_dir.mkdir(parents=True, exist_ok=True)
        calls.append({"experiment": str(experiment), "seed": cfg.get("SEED")})
        return exp_dir

    monkeypatch.setattr(nn_audit, "pick_target", lambda *a, **k: _mk_target())
    monkeypatch.setattr(nn_audit, "_target_baseline_tag", lambda *a, **k: "")
    monkeypatch.setattr(nn_audit, "attest_candidate",
                        lambda *a, **k: _mk_attest(keys=["FOO", "BAR"]))
    monkeypatch.setattr(nn_audit, "run_arm", fake_run_arm)
    monkeypatch.setattr(nn_audit, "_primary_from_exp", lambda *a, **k: 0.5)
    monkeypatch.setattr(nn_audit, "resolve_fingerprint_baseline", lambda *a, **k: (None, "plain"))
    monkeypatch.setattr(nn_audit, "write_index_entry", lambda *a, **k: None)
    return SimpleNamespace(root=root, calls=calls)


def _run(env, **kw) -> Path:
    return nn_audit.pipeline(env.root, exp_dir="_runs/exp/demo_orig", **kw)


def test_default_behavior_unchanged(env):
    """默认：种子行 = extra_seeds(orig, n)[1:]；消融每键 1 行、原名无后缀。"""
    card = _run(env, n_seeds=3)
    names = [c["experiment"] for c in env.calls]
    seeds = extra_seeds(2, 3)
    assert names == [
        "audit_repro_deadbeef",
        f"audit_seed_{seeds[1]}",
        f"audit_seed_{seeds[2]}",
        "audit_ablate_FOO",
        "audit_ablate_BAR",
    ]
    ab = [c for c in env.calls if c["experiment"].startswith("audit_ablate")]
    assert all(c["seed"] == 2 for c in ab)
    assert (card / "runs.tsv").is_file()


def test_ablation_n_seeds_extends_per_key(env):
    """ablation_n_seeds=3：每键 3 行；首个无后缀（原种子），其余 _s<seed>。"""
    _run(env, n_seeds=2, ablation_n_seeds=3)
    ab = [c for c in env.calls if c["experiment"].startswith("audit_ablate")]
    want = extra_seeds(2, 3)
    assert [(c["experiment"], c["seed"]) for c in ab] == [
        ("audit_ablate_FOO", want[0]),
        ("audit_ablate_FOO_s%d" % want[1], want[1]),
        ("audit_ablate_FOO_s%d" % want[2], want[2]),
        ("audit_ablate_BAR", want[0]),
        ("audit_ablate_BAR_s%d" % want[1], want[1]),
        ("audit_ablate_BAR_s%d" % want[2], want[2]),
    ]


def test_ablation_keys_override_bypasses_novelty(env, monkeypatch):
    """显式 keys：attested_depth 非 novel 也跑（人指定 = 明确意图）。"""
    monkeypatch.setattr(nn_audit, "attest_candidate",
                        lambda *a, **k: _mk_attest(depth="known", keys=[]))
    _run(env, n_seeds=2, ablation_keys_override=["BAZ"])
    ab = [c["experiment"] for c in env.calls if c["experiment"].startswith("audit_ablate")]
    assert ab == ["audit_ablate_BAZ"]


def test_seeds_override_dedups_orig_keeps_order(env):
    """显式种子列表：基准种子去重、其余按给定顺序。"""
    _run(env, n_seeds=2, seeds_override=[7, 5, 2, 9])
    seed_rows = [c for c in env.calls if c["experiment"].startswith("audit_seed_")]
    assert [c["seed"] for c in seed_rows] == [7, 5, 9]


def test_runs_tsv_schema(env):
    """runs.tsv：8 列头、行数 = arms+1、metric/direction 来自 target。"""
    card = _run(env, n_seeds=2, ablation_n_seeds=2)
    lines = (card / "runs.tsv").read_text(encoding="utf-8").strip().split("\n")
    assert lines[0].split("\t") == [
        "kind", "experiment", "seed", "key", "primary",
        "metric", "metric_direction", "exp_dir",
    ]
    assert len(lines) == 1 + len(env.calls)
    row = lines[1].split("\t")
    assert row[0] == "repro" and row[5] == "sgcs" and row[6] == "maximize"
    ab_row = [ln.split("\t") for ln in lines[1:] if ln.startswith("ablate\t")]
    assert ab_row and ab_row[0][3] == "FOO"


def test_cli_new_args():
    """CLI：--seeds / --ablation-keys / --ablation-seeds 解析。"""
    p = nn_audit.build_arg_parser()
    a = p.parse_args(["pipeline", "--seeds", "7,5,9",
                      "--ablation-keys", "A,B", "--ablation-seeds", "10"])
    assert a.seeds == "7,5,9"
    assert a.ablation_keys == "A,B"
    assert a.ablation_seeds == 10
