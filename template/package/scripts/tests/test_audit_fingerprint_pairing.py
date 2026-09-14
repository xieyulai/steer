from pathlib import Path
import json
from lib.innovation_fingerprint import build_innovation_fingerprint
from lib.reflect_evidence import ReflectEvidenceBundle


def _exp(root: Path, name: str, cfg: dict) -> Path:
    d = root / "_runs" / "exp" / name
    d.mkdir(parents=True)
    (d / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    return d


def test_explicit_pairing_ignores_reb(tmp_path: Path):
    base = _exp(tmp_path, "plain", {"LOSS": "ce", "SEED": 1})
    cand = _exp(tmp_path, "keeper", {"LOSS": "polyloss", "SEED": 1})
    empty = ReflectEvidenceBundle()
    fp = build_innovation_fingerprint(
        tmp_path,
        reb_bundle=empty,
        baseline_dir=base,
        candidate_dirs=[cand],
    )
    assert fp.pairing_source == "explicit"
    assert Path(fp.baseline_exp_dir).resolve() == base.resolve()
    assert Path(fp.candidate_exp_dirs[0]).resolve() == cand.resolve()
    assert "LOSS" in fp.primary_keys_changed


def test_explicit_requires_both_or_neither(tmp_path: Path):
    d = _exp(tmp_path, "x", {"SEED": 1})
    empty = ReflectEvidenceBundle()
    try:
        build_innovation_fingerprint(
            tmp_path, reb_bundle=empty, baseline_dir=d,
        )
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
