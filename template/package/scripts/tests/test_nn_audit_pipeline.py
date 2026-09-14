# template/package/scripts/tests/test_nn_audit_pipeline.py
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from lib.audit_attest import AttestResult
from lib.audit_core import AuditTarget, config_sha256
from nn_audit import (
    _resolve_verdict,
    build_train_argv,
    pipeline,
    run_arm,
    train_env,
    write_card,
)


def test_train_argv_no_finalize():
    argv = build_train_argv(Path("c.json"), "audit_repro_x")
    assert "--no-auto-finalize-round" in argv
    assert any(a.startswith("audit_") for a in argv)


def test_train_env_blocks_keeper_and_parallel():
    env = train_env({"NN_PARALLEL_TOTAL": "4"})
    assert env["NN_SKIP_WRITE_KEEPER"] in ("1", "true")
    assert env["NN_AUTO_FINALIZE_ROUND"] in ("0", "false")
    assert env.get("NN_PARALLEL_TOTAL", "1") == "1"


def _exp(root: Path, name: str, cfg: dict, primary: float | None = None) -> Path:
    d = root / "_runs" / "exp" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    if primary is not None:
        (d / "results.json").write_text(
            json.dumps({"primary_metric": {"test_acc": primary}}), encoding="utf-8",
        )
    return d


def _target(tmp_path: Path, keeper: Path, *, primary: float = 0.9) -> AuditTarget:
    cfg = json.loads((keeper / "config.json").read_text(encoding="utf-8"))
    return AuditTarget(
        scenario_id="seq",
        audited_exp_dir=keeper.relative_to(tmp_path).as_posix(),
        config_sha256=config_sha256(cfg),
        original_seed=1,
        original_primary=primary,
        metric_key="test_acc",
        metric_direction="maximize",
    )


def _attest(**kwargs) -> AttestResult:
    defaults = dict(
        fp_depth="different",
        attested_depth="novel",
        search_claimed_depth="routine",
        paper_verdict="supported",
        baseline_kind="plain",
        primary_keys_changed={"LOSS": {"from": "ce", "to": "poly"}},
        ablation_keys=["LOSS"],
        ablation_planned=True,
        ablation_skip_reason="",
        fingerprint={},
    )
    defaults.update(kwargs)
    return AttestResult(**defaults)


def _keepers(tmp_path: Path) -> Path:
    saved = tmp_path / "saved"
    saved.mkdir(exist_ok=True)
    p = saved / "keepers.json"
    p.write_text(
        json.dumps({"seq": {"scenario_id": "seq", "keeper_exp_dir": "_runs/exp/keeper"}}),
        encoding="utf-8",
    )
    return p


def test_write_card_leaves_ledger_untouched_and_empty_decision(tmp_path: Path):
    keeper = _exp(tmp_path, "keeper", {"LOSS": "poly", "SEED": 1}, 0.9)
    keepers_path = _keepers(tmp_path)
    keepers_bytes = keepers_path.read_bytes()
    tsv = tmp_path / "_runs" / "results.tsv"
    tsv.write_text(
        "experiment\tscenario_id\tbaseline_tag\texp_dir\n"
        "r\tseq\treference\t_runs/exp/ref\n",
        encoding="utf-8",
    )
    tsv_text = tsv.read_text(encoding="utf-8")
    n_rows = len([ln for ln in tsv_text.splitlines() if ln.strip()])

    arms = [{
        "kind": "repro",
        "experiment": "audit_repro_x",
        "seed": 1,
        "primary": 0.9,
        "exp_dir": keeper.relative_to(tmp_path).as_posix(),
    }]
    card_dir = write_card(
        tmp_path, _target(tmp_path, keeper), _attest(), arms, status="complete",
    )

    assert keepers_path.read_bytes() == keepers_bytes
    assert tsv.is_file()
    assert len([ln for ln in tsv.read_text(encoding="utf-8").splitlines() if ln.strip()]) == n_rows
    card = json.loads((card_dir / "card.json").read_text(encoding="utf-8"))
    required = [
        "schema_version", "scenario_id", "audited_exp_dir", "config_sha256",
        "repro_ok", "n_seeds", "primary_mean", "primary_std",
        "attested_depth", "search_claimed_depth", "ablation_planned",
        "ablation_ran", "human_decision", "status",
    ]
    for key in required:
        assert key in card
    assert card["schema_version"] == 1
    assert card["human_decision"] == ""
    assert card["reference_multiseed"] == "missing"
    assert (tmp_path / "saved" / "audit" / "index.json").is_file()
    md = (card_dir / "card.md").read_text(encoding="utf-8")
    assert "终审技能" not in md
    for phrase in (
        "# 审查卡片",
        "审的是：",
        "复现：",
        "多种子：",
        "新不新：",
        "消融：",
        "人还没决定留下、搁置还是驳回",
    ):
        assert phrase in md


def test_write_card_does_not_create_tsv(tmp_path: Path):
    keeper = _exp(tmp_path, "keeper", {"LOSS": "poly", "SEED": 1}, 0.9)
    keepers_path = _keepers(tmp_path)
    before = keepers_path.read_bytes()
    write_card(
        tmp_path, _target(tmp_path, keeper), _attest(),
        [{"kind": "repro", "experiment": "audit_repro_x", "seed": 1, "primary": 0.9,
          "exp_dir": "_runs/exp/keeper"}],
        status="complete",
    )
    assert keepers_path.read_bytes() == before
    assert not (tmp_path / "_runs" / "results.tsv").exists()
    assert not (tmp_path / "_runs" / "results.jsonl").exists()


def _setup_pipeline_repo(tmp_path: Path, *, primary: float = 0.9) -> Path:
    plain = _exp(tmp_path, "plain", {"LOSS": "ce", "SEED": 1})
    keeper = _exp(tmp_path, "keeper", {"LOSS": "poly", "SEED": 1}, primary)
    _keepers(tmp_path)
    tsv = tmp_path / "_runs" / "results.tsv"
    tsv.write_text(
        "experiment\tscenario_id\tbaseline_tag\texp_dir\n"
        f"p\tseq\tplain\t{plain.relative_to(tmp_path).as_posix()}\n"
        f"k\tseq\t\t{keeper.relative_to(tmp_path).as_posix()}\n",
        encoding="utf-8",
    )
    (tmp_path / "nn-config.yaml").write_text(
        "agent:\n  scenario_default: seq\nkeep:\n  near_best_abs: 0\n",
        encoding="utf-8",
    )
    return keeper


def _mock_runner(
    score_for: dict[str, float],
    *,
    raise_on: int | None = None,
    error_on: int | None = None,
):
    state = {"n": 0, "experiments": []}

    def runner(repo_root, config_path, experiment):
        state["n"] += 1
        state["experiments"].append(experiment)
        if raise_on is not None and state["n"] >= raise_on:
            raise KeyboardInterrupt
        if error_on is not None and state["n"] >= error_on:
            raise RuntimeError("seed arm boom")
        d = Path(repo_root) / "_runs" / "exp" / str(experiment)
        d.mkdir(parents=True, exist_ok=True)
        cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
        (d / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
        if "ablate" in str(experiment):
            score = score_for.get("ablate", 0.5)
        elif "seed" in str(experiment):
            score = score_for.get("seed", 0.9)
        else:
            score = score_for.get("repro", 0.9)
        (d / "results.json").write_text(
            json.dumps({"primary_metric": {"test_acc": score}}), encoding="utf-8",
        )
        return d

    runner.state = state  # type: ignore[attr-defined]
    return runner


def _arm_blob(card_dir: Path) -> list:
    raw = json.loads((card_dir / "arms.json").read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return raw
    return list(raw.get("arms") or [])


def test_pipeline_repro_fail_skips_ablation(tmp_path: Path):
    _setup_pipeline_repo(tmp_path)
    runner = _mock_runner({"repro": 0.1, "ablate": 0.1, "seed": 0.1})
    card_dir = pipeline(
        tmp_path, runner=runner, n_seeds=5, paper_verdict="supported",
    )
    card = json.loads((card_dir / "card.json").read_text(encoding="utf-8"))
    assert card["status"] == "repro_failed"
    assert card["repro_ok"] is False
    assert card["ablation_ran"] is False
    assert card["human_decision"] == ""
    arms = _arm_blob(card_dir)
    assert not any("ablate" in str(a).lower() for a in arms)
    assert not any("ablate" in str(e) for e in runner.state["experiments"])
    keepers = json.loads((tmp_path / "saved" / "keepers.json").read_text(encoding="utf-8"))
    assert keepers["seq"]["keeper_exp_dir"] == "_runs/exp/keeper"


def test_pipeline_reference_skips_novelty(tmp_path: Path):
    plain = _exp(tmp_path, "plain", {"LOSS": "ce", "SEED": 1, "baseline_tag": "plain"}, 0.4)
    ref = _exp(tmp_path, "ref", {"LOSS": "poly", "SEED": 1, "baseline_tag": "reference"}, 0.7)
    _keepers(tmp_path)
    tsv = tmp_path / "_runs" / "results.tsv"
    tsv.write_text(
        "experiment\tscenario_id\tbaseline_tag\texp_dir\n"
        f"p\tseq\tplain\t{plain.relative_to(tmp_path).as_posix()}\n"
        f"r\tseq\treference\t{ref.relative_to(tmp_path).as_posix()}\n",
        encoding="utf-8",
    )
    tsv_n = len([ln for ln in tsv.read_text(encoding="utf-8").splitlines() if ln.strip()])
    (tmp_path / "nn-config.yaml").write_text(
        "agent:\n  scenario_default: seq\nkeep:\n  near_best_abs: 0\n",
        encoding="utf-8",
    )

    def boom(*_a, **_k):
        raise AssertionError("skip_train 不得调用 runner")

    card_dir = pipeline(
        tmp_path,
        exp_dir=str(ref.relative_to(tmp_path)),
        skip_train=True,
        runner=boom,
        fetch_external=True,
        paper_verdict="supported",
    )
    card = json.loads((card_dir / "card.json").read_text(encoding="utf-8"))
    md = (card_dir / "card.md").read_text(encoding="utf-8")
    assert card["attested_depth"] == "skipped"
    assert card["ablation_ran"] is False
    assert card["ablation_planned"] is False
    assert "已跳过新不新" in md
    tsv_n2 = len([ln for ln in tsv.read_text(encoding="utf-8").splitlines() if ln.strip()])
    assert tsv_n2 == tsv_n


def test_pipeline_skip_train_writes_card_without_runner(tmp_path: Path):
    _setup_pipeline_repo(tmp_path)

    def boom(*_a, **_k):
        raise AssertionError("skip_train 不得调用 runner / train")

    card_dir = pipeline(tmp_path, skip_train=True, runner=boom, paper_verdict="supported")
    assert (card_dir / "card.json").is_file()
    assert (card_dir / "attest.json").is_file()
    card = json.loads((card_dir / "card.json").read_text(encoding="utf-8"))
    assert card["human_decision"] == ""
    assert (tmp_path / "saved" / "audit" / "index.json").is_file()
    assert not (tmp_path / "_runs" / "results.jsonl").exists()


def test_pipeline_keyboardinterrupt_writes_partial(tmp_path: Path):
    _setup_pipeline_repo(tmp_path)
    runner = _mock_runner({"repro": 0.9, "seed": 0.9}, raise_on=2)
    with pytest.raises(KeyboardInterrupt):
        pipeline(tmp_path, runner=runner, n_seeds=5, paper_verdict="supported")
    cards = list((tmp_path / "saved" / "audit").glob("*/card.json"))
    assert cards
    card = json.loads(cards[0].read_text(encoding="utf-8"))
    assert card["status"] == "partial"
    assert card["human_decision"] == ""


def test_pipeline_later_arm_failure_writes_partial(tmp_path: Path):
    """复现成功后第二臂失败：写 partial 卡，arms.json 保留已完成臂。"""
    _setup_pipeline_repo(tmp_path)
    runner = _mock_runner({"repro": 0.9, "seed": 0.9}, error_on=2)
    with pytest.raises(RuntimeError, match="seed arm boom"):
        pipeline(tmp_path, runner=runner, n_seeds=5, paper_verdict="supported")
    cards = list((tmp_path / "saved" / "audit").glob("*/card.json"))
    assert cards
    card_dir = cards[0].parent
    card = json.loads(cards[0].read_text(encoding="utf-8"))
    assert card["status"] == "partial"
    arms = _arm_blob(card_dir)
    completed = [a for a in arms if a.get("primary") is not None]
    assert completed
    assert any(str(a.get("kind", "")).lower() == "repro" for a in completed)
    assert not any("seed" in str(a.get("kind", "")).lower() for a in completed)


def test_pipeline_novel_repro_ok_runs_one_ablation_arm(tmp_path: Path):
    _setup_pipeline_repo(tmp_path)
    runner = _mock_runner({"repro": 0.9, "seed": 0.9, "ablate": 0.8})
    card_dir = pipeline(
        tmp_path, runner=runner, n_seeds=2, paper_verdict="supported",
    )
    card = json.loads((card_dir / "card.json").read_text(encoding="utf-8"))
    assert card["repro_ok"] is True
    assert card["ablation_ran"] is True
    assert card["status"] == "complete"
    assert card["human_decision"] == ""
    arms = _arm_blob(card_dir)
    ablate = [
        a for a in arms
        if "ablate" in str(a.get("kind", "")).lower()
        or "ablate" in str(a.get("experiment", "")).lower()
    ]
    assert len(ablate) == 1
    assert int(ablate[0].get("seed", -1)) == 1
    md = (card_dir / "card.md").read_text(encoding="utf-8")
    assert "样本不足未判门槛" in md
    assert "终审技能" not in md
    # n_seeds=2 → n_f=2 + n_a=1 < 4
    called = runner.state["experiments"]
    assert sum("ablate" in str(e) for e in called) == 1
    assert not any("finalize" in str(e) for e in called)


def test_failed_arm_does_not_reuse_previous_audit_score(tmp_path, monkeypatch):
    """失败臂（非零 rc、无新目录）不得把上一臂 audit_* 的分数当成本臂结果。"""
    prev = _exp(tmp_path, "audit_repro_prev", {"LOSS": "poly", "SEED": 1}, 0.99)
    cfg = tmp_path / "cfg.json"
    cfg.write_text("{}", encoding="utf-8")

    class FakeProc:
        returncode = 1
        stdout = ""
        stderr = "train failed"

    monkeypatch.setattr("nn_audit.subprocess.run", lambda *_a, **_k: FakeProc())

    with pytest.raises(RuntimeError):
        run_arm(tmp_path, cfg, "audit_seed_7")

    _setup_pipeline_repo(tmp_path, primary=0.9)
    card_dir = pipeline(tmp_path, n_seeds=2, paper_verdict="supported")
    card = json.loads((card_dir / "card.json").read_text(encoding="utf-8"))
    assert card["status"] == "repro_failed"
    arms = _arm_blob(card_dir)
    repro = [a for a in arms if str(a.get("kind", "")).lower() == "repro"]
    assert repro
    assert repro[0].get("primary") != 0.99
    assert "audit_repro_prev" not in str(repro[0].get("exp_dir", ""))
    assert Path(repro[0]["exp_dir"]).name != prev.name


def test_run_arm_mtime_fallback_matches_current_experiment_only(tmp_path, monkeypatch):
    """成功但无 exp_dir= 时，只认当前实验名且 mtime>=t0，不认任意含 audit_ 的目录。"""
    other = _exp(tmp_path, "audit_repro_other", {"SEED": 1}, 0.11)
    mine = _exp(tmp_path, "audit_seed_7", {"SEED": 7}, 0.77)
    tagged = _exp(tmp_path, "20260101_pid_audit_seed_9", {"SEED": 9}, 0.55)
    old = time.time() - 120
    for d in (other, mine, tagged):
        os.utime(d, (old, old))

    def fake_run(argv, *_a, **_k):
        exp_name = next((str(a) for a in argv if str(a).startswith("audit_")), "")
        exp_root = tmp_path / "_runs" / "exp"
        now = time.time()
        for d in exp_root.iterdir():
            if d.is_dir() and (d.name == exp_name or d.name.endswith("_" + exp_name)):
                os.utime(d, (now, now))

        class FakeProc:
            returncode = 0
            stdout = ""
            stderr = ""

        return FakeProc()

    monkeypatch.setattr("nn_audit.subprocess.run", fake_run)
    cfg = tmp_path / "c.json"
    cfg.write_text("{}", encoding="utf-8")

    got = run_arm(tmp_path, cfg, "audit_seed_7")
    assert Path(got).resolve() == mine.resolve()

    got2 = run_arm(tmp_path, cfg, "audit_seed_9")
    assert Path(got2).resolve() == tagged.resolve()


def test_run_arm_mtime_fallback_ignores_stale_dirs(tmp_path, monkeypatch):
    stale = _exp(tmp_path, "audit_seed_7", {"SEED": 7}, 0.77)
    os.utime(stale, (time.time() - 120, time.time() - 120))

    class FakeProc:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr("nn_audit.subprocess.run", lambda *_a, **_k: FakeProc())
    cfg = tmp_path / "c.json"
    cfg.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="未找到 exp_dir"):
        run_arm(tmp_path, cfg, "audit_seed_7")


def test_run_arm_failed_includes_stderr_tail(tmp_path, monkeypatch):
    class FakeProc:
        returncode = 1
        stdout = ""
        stderr = ("boom-line\n" * 400) + "TAIL_MARK"

    monkeypatch.setattr("nn_audit.subprocess.run", lambda *_a, **_k: FakeProc())
    cfg = tmp_path / "c.json"
    cfg.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError) as ei:
        run_arm(tmp_path, cfg, "audit_seed_7")
    msg = str(ei.value)
    assert "rc=1" in msg
    assert "TAIL_MARK" in msg
    assert len(msg) < 4000


def test_dry_run_external_never_fetches(tmp_path, monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("dry-run 不得联网")

    monkeypatch.setattr("nn_audit._fetch_paper_verdict", boom)
    v = _resolve_verdict(tmp_path, fetch_external=True, dry_run_external=True)
    assert v == "inconclusive"
