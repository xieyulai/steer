# template/package/scripts/tests/test_audit_attest.py
import json
from pathlib import Path

from lib.audit_attest import attest_candidate
from lib.audit_core import AuditTarget, config_sha256


def _exp(root: Path, name: str, cfg: dict) -> Path:
    d = root / "_runs" / "exp" / name
    d.mkdir(parents=True)
    (d / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    return d


def _setup_plain_vs_keeper(tmp_path: Path) -> AuditTarget:
    """plain LOSS=ce 作尺子；keeper LOSS=poly（catalog 未知 → different）。"""
    plain = _exp(tmp_path, "plain", {"LOSS": "ce", "SEED": 1})
    keeper = _exp(tmp_path, "keeper", {"LOSS": "poly", "SEED": 1})
    (keeper / "results.json").write_text(
        json.dumps({"primary_metric": {"test_acc": 0.9}}), encoding="utf-8",
    )
    tsv = tmp_path / "_runs" / "results.tsv"
    tsv.write_text(
        "experiment\tscenario_id\tbaseline_tag\texp_dir\n"
        f"p\tseq\tplain\t{plain.relative_to(tmp_path).as_posix()}\n"
        f"k\tseq\t\t{keeper.relative_to(tmp_path).as_posix()}\n",
        encoding="utf-8",
    )
    (tmp_path / "nn-config.yaml").write_text(
        "agent:\n  scenario_default: seq\n", encoding="utf-8",
    )
    cfg = json.loads((keeper / "config.json").read_text(encoding="utf-8"))
    return AuditTarget(
        scenario_id="seq",
        audited_exp_dir=keeper.relative_to(tmp_path).as_posix(),
        config_sha256=config_sha256(cfg),
        original_seed=1,
        original_primary=0.9,
        metric_key="test_acc",
        metric_direction="maximize",
    )


def test_attest_supported_yields_novel_and_loss_keys(tmp_path: Path):
    target = _setup_plain_vs_keeper(tmp_path)
    r = attest_candidate(tmp_path, target, paper_verdict="supported")
    assert r.attested_depth == "novel"
    assert r.ablation_keys == ["LOSS"]
    assert r.ablation_planned is True
    assert r.ablation_skip_reason == ""
    assert r.baseline_kind == "plain"
    assert r.paper_verdict == "supported"
    assert "LOSS" in r.primary_keys_changed


def test_attest_inconclusive_not_novel_no_ablation(tmp_path: Path):
    target = _setup_plain_vs_keeper(tmp_path)
    r = attest_candidate(tmp_path, target, paper_verdict="inconclusive")
    assert r.attested_depth != "novel"
    assert r.ablation_planned is False
    assert "LOSS" in r.ablation_keys
    assert r.paper_verdict == "inconclusive"
