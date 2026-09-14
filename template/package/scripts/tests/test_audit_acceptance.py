# template/package/scripts/tests/test_audit_acceptance.py
"""规格验收：不入账、活指针当前/上一套、反思 pending 仍在。无 GPU。"""
from __future__ import annotations

import json
from pathlib import Path

from lib.audit_core import injection_for_scenario
from nn_audit import pipeline

PRIMARY = 0.9
SCENARIO = "seq"


def _write_exp(root: Path, name: str, cfg: dict, primary: float | None = None) -> Path:
    d = root / "_runs" / "exp" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    if primary is not None:
        (d / "results.json").write_text(
            json.dumps({"primary_metric": {"test_acc": primary}}),
            encoding="utf-8",
        )
    return d


def _setup_acceptance_repo(tmp_path: Path) -> Path:
    """keepers + plain 尺子。TSV 只给尺子用；审查不得增行。"""
    plain = _write_exp(tmp_path, "plain", {"LOSS": "ce", "SEED": 1})
    keeper = _write_exp(tmp_path, "keeper", {"LOSS": "poly", "SEED": 1}, PRIMARY)
    saved = tmp_path / "saved"
    saved.mkdir(exist_ok=True)
    keepers_path = saved / "keepers.json"
    keepers_path.write_text(
        json.dumps({
            SCENARIO: {
                "scenario_id": SCENARIO,
                "keeper_exp_dir": "_runs/exp/keeper",
            }
        }),
        encoding="utf-8",
    )
    tsv = tmp_path / "_runs" / "results.tsv"
    tsv.write_text(
        "experiment\tscenario_id\tbaseline_tag\texp_dir\n"
        f"p\t{SCENARIO}\tplain\t{plain.relative_to(tmp_path).as_posix()}\n"
        f"k\t{SCENARIO}\t\t{keeper.relative_to(tmp_path).as_posix()}\n",
        encoding="utf-8",
    )
    (tmp_path / "nn-config.yaml").write_text(
        "agent:\n  scenario_default: seq\nkeep:\n  near_best_abs: 0\n",
        encoding="utf-8",
    )
    return keepers_path


def _fake_arm_runner(original_primary: float):
    """写假 audit_* / results.json，主分与原记录相同；不调 train.py。"""

    def runner(repo_root, config_path, experiment):
        d = Path(repo_root) / "_runs" / "exp" / str(experiment)
        d.mkdir(parents=True, exist_ok=True)
        src = Path(config_path)
        if src.is_file():
            (d / "config.json").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            (d / "config.json").write_text("{}", encoding="utf-8")
        (d / "results.json").write_text(
            json.dumps({"primary_metric": {"test_acc": original_primary}}),
            encoding="utf-8",
        )
        return d

    return runner


def _tsv_state(root: Path) -> tuple[bool, int]:
    tsv = root / "_runs" / "results.tsv"
    if not tsv.is_file():
        return False, 0
    n = len([ln for ln in tsv.read_text(encoding="utf-8").splitlines() if ln.strip()])
    return True, n


def test_audit_acceptance_no_ledger_and_live_pointer(tmp_path: Path):
    keepers_path = _setup_acceptance_repo(tmp_path)
    keepers_bytes = keepers_path.read_bytes()
    tsv_existed, tsv_rows = _tsv_state(tmp_path)

    card_dir = pipeline(
        tmp_path,
        skip_train=False,
        runner=_fake_arm_runner(PRIMARY),
        paper_verdict="supported",
    )

    existed_after, rows_after = _tsv_state(tmp_path)
    if not tsv_existed:
        assert not existed_after
    else:
        assert rows_after == tsv_rows
    assert keepers_path.read_bytes() == keepers_bytes

    assert (tmp_path / "saved" / "audit" / "index.json").is_file()

    cards = list((tmp_path / "saved" / "audit").glob("*/card.json"))
    assert cards
    for card_path in cards:
        card = json.loads(card_path.read_text(encoding="utf-8"))
        assert card.get("human_decision") == ""

    raw_arms = json.loads((card_dir / "arms.json").read_text(encoding="utf-8"))
    arms = raw_arms if isinstance(raw_arms, list) else list(raw_arms.get("arms") or [])
    repros = [
        a for a in arms
        if a.get("kind") == "repro"
        and str(a.get("experiment", "")).startswith("audit_repro_")
        and "skip" not in str(a.get("experiment", "")).lower()
    ]
    assert repros, "repro arm must actually run (not skip_train)"

    inj = injection_for_scenario(tmp_path, SCENARIO)
    assert inj is not None
    assert inj["status"] == "current"

    keepers_path.write_text(
        json.dumps({
            SCENARIO: {
                "scenario_id": SCENARIO,
                "keeper_exp_dir": "_runs/exp/other",
            }
        }),
        encoding="utf-8",
    )
    inj2 = injection_for_scenario(tmp_path, SCENARIO)
    assert inj2 is not None
    assert inj2["status"] == "superseded"


def test_reflect_py_still_writes_pending():
    text = (Path(__file__).resolve().parents[2] / "reflect.py").read_text(encoding="utf-8")
    assert "REFLECT_INDEX" in text
    assert "pending" in text.lower()
