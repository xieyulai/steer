"""prune-runs：regen 失败不得阻断删目录 / 写 jsonl。"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1]
_PKG = _SCRIPTS.parent
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

_SPEC = importlib.util.spec_from_file_location("_prune_runs", _SCRIPTS / "prune-runs.py")
assert _SPEC and _SPEC.loader
pr = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(pr)


def test_apply_prune_continues_when_regen_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo = tmp_path
    exp = repo / "_runs" / "exp" / "20260728_000000_1_s0of1_smoke_check"
    exp.mkdir(parents=True)
    (exp / "marker.txt").write_text("x", encoding="utf-8")

    tsv = repo / "_runs" / "results.tsv"
    tsv.parent.mkdir(parents=True, exist_ok=True)
    tsv.write_text(
        "experiment\texp_dir\n"
        f"smoke_check\t{exp}\n"
        "real_run\t_runs/exp/keep_me\n",
        encoding="utf-8",
    )
    jsonl = repo / "_runs" / "results.jsonl"
    jsonl.write_text(
        json.dumps({"experiment": "smoke_check", "exp_dir": str(exp)})
        + "\n"
        + json.dumps({"experiment": "real_run", "exp_dir": "_runs/exp/keep_me"})
        + "\n",
        encoding="utf-8",
    )
    (repo / "scripts").mkdir()
    (repo / "scripts" / "regen_results_tsv.py").write_text("# stub\n", encoding="utf-8")

    def _boom(*_a, **_k):
        raise pr.subprocess.CalledProcessError(1, "regen")

    monkeypatch.setattr(pr.subprocess, "run", _boom)

    keep = [{"experiment": "real_run", "exp_dir": "_runs/exp/keep_me"}]
    drop = [{"experiment": "smoke_check", "exp_dir": str(exp)}]
    pr.apply_prune(
        repo,
        keep_rows=keep,
        drop_rows=drop,
        exp_to_delete={exp.resolve()},
        ledger_only=False,
        tsv_rel="_runs/results.tsv",
        jsonl_rel="_runs/results.jsonl",
        drop_experiments=frozenset({"smoke_check"}),
        no_backup=True,
    )

    assert not exp.exists(), "regen 失败时仍应删除 junk exp 目录"
    body = tsv.read_text(encoding="utf-8")
    assert "smoke_check" not in body
    assert "real_run" in body
    jl = jsonl.read_text(encoding="utf-8")
    assert "smoke_check" not in jl
    assert "real_run" in jl


def test_parse_metrics_py_fallback(tmp_path: Path):
    from scripts.regen_results_tsv import _parse_metric_dicts_from_source

    (tmp_path / "contract").mkdir()
    (tmp_path / "contract" / "__init__.py").write_text(
        "class Contract:\n"
        "    @property\n"
        "    def metric_keys(self):\n"
        "        return METRIC_KEYS\n",
        encoding="utf-8",
    )
    (tmp_path / "contract" / "metrics.py").write_text(
        'METRIC_KEYS = {"test_loss": "min"}\n'
        'AUXILIARY_KEYS = {"aux": "max"}\n',
        encoding="utf-8",
    )
    parsed = _parse_metric_dicts_from_source(tmp_path)
    assert parsed is not None
    mk, ak, _ = parsed
    assert mk == {"test_loss": "min"}
    assert ak == {"aux": "max"}
