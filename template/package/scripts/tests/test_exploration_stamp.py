from __future__ import annotations

import json
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PKG / "scripts"))

from lib.exploration_stamp import (  # noqa: E402
    compute_stamp,
    is_trained_row,
    is_untrained,
    prev_trained_exp_dir,
)


def test_untrained_short_clock():
    assert is_untrained(elapsed_sec=0.2, smoke=False) is True
    assert is_untrained(elapsed_sec=10.0, smoke=True) is True
    assert is_untrained(elapsed_sec=10.0, smoke=False) is False


def test_is_trained_row_untrained_flag_false():
    """墙钟够长但 untrained=1 → 不能当对照行。"""
    assert is_trained_row(
        {"elapsed_sec": "10", "untrained": "1"},
        metric_key="acc",
    ) is False
    assert is_trained_row(
        {"elapsed_sec": "10", "untrained": "0"},
        metric_key="acc",
    ) is True
    # 旧行无 untrained 列：仍只靠 elapsed
    assert is_trained_row(
        {"elapsed_sec": "10"},
        metric_key="acc",
    ) is True


def test_prev_trained_skips_untrained_middle(tmp_path: Path):
    """中间 smoke/untrained 行被跳过，选更早的正式行。"""
    d0 = tmp_path / "_runs" / "exp" / "e0"
    d1 = tmp_path / "_runs" / "exp" / "e1"
    d2 = tmp_path / "_runs" / "exp" / "e2"
    for d in (d0, d1, d2):
        d.mkdir(parents=True)
    tsv = tmp_path / "_runs" / "results.tsv"
    tsv.write_text(
        "experiment\tscenario_id\tacc\telapsed_sec\texp_dir\tuntrained\n"
        f"e0\ts\t0.5\t10\t{d0}\t0\n"
        f"e1\ts\t0.1\t10\t{d1}\t1\n"
        f"e2\ts\t0.6\t12\t{d2}\t0\n",
        encoding="utf-8",
    )
    prev = prev_trained_exp_dir(
        tmp_path, scenario_id="s", before_exp_dir=d2, metric_key="acc"
    )
    assert prev == d0.resolve()


def _write_run(root: Path, name: str, cfg: dict, elapsed: float = 10.0) -> Path:
    d = root / "_runs" / "exp" / name
    d.mkdir(parents=True)
    (d / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    snap = d / "code_snapshot"
    snap.mkdir()
    (snap / "train.py").write_text("# a\n", encoding="utf-8")
    (d / "results.json").write_text(
        json.dumps({"metrics": {"acc": 0.5}, "elapsed_sec": elapsed, "experiment": name}),
        encoding="utf-8",
    )
    return d


def test_stamp_scalar_lr_is_a_routine(tmp_path: Path):
    prev = _write_run(tmp_path, "p0", {"LR": 0.1, "scenario_id": "s"})
    cur = _write_run(tmp_path, "p1", {"LR": 0.2, "scenario_id": "s"})
    tsv = tmp_path / "_runs" / "results.tsv"
    tsv.write_text(
        "experiment\tscenario_id\tacc\telapsed_sec\texp_dir\texploration_space\n"
        f"p0\ts\t0.5\t10\t{prev}\tA-routine\n",
        encoding="utf-8",
    )
    r = compute_stamp(
        tmp_path, cur, elapsed_sec=10.0, smoke=False, scenario_id="s", metric_key="acc", metrics={"acc": 0.6},
    )
    assert r.untrained is False
    assert r.cell == "A-routine"


def test_stamp_untrained_empty_cell(tmp_path: Path):
    cur = _write_run(tmp_path, "x", {"LR": 0.1}, elapsed=0.0)
    r = compute_stamp(
        tmp_path, cur, elapsed_sec=0.4, smoke=False, scenario_id="s", metric_key="acc", metrics={},
    )
    assert r.untrained is True
    assert r.cell == ""


def test_stamp_contract_only_inherits_prev_cell(tmp_path: Path, monkeypatch):
    cfg = {"LR": 0.1, "scenario_id": "s"}
    prev = _write_run(tmp_path, "p0", cfg)
    cur = _write_run(tmp_path, "p1", cfg)

    def _fake_diff(base, target):
        del base, target
        return {
            "changed_files": ["contract/foo.yaml"],
            "summaries": ["+ contract/foo.yaml (new)"],
        }

    monkeypatch.setattr("lib.exploration_stamp.diff_code_snapshots", _fake_diff)

    tsv = tmp_path / "_runs" / "results.tsv"
    tsv.write_text(
        "experiment\tscenario_id\tacc\telapsed_sec\texp_dir\texploration_space\n"
        f"p0\ts\t0.5\t10\t{prev}\tB-different\n",
        encoding="utf-8",
    )
    r = compute_stamp(
        tmp_path, cur, elapsed_sec=10.0, smoke=False, scenario_id="s", metric_key="acc", metrics={"acc": 0.6},
    )
    assert r.untrained is False
    assert r.cell == "B-different"
    assert "inherit_prev" in r.reasons


def _stamp_after(tmp_path: Path, prev_cfg: dict, cur_cfg: dict, *, prev_cell="A-routine"):
    prev = _write_run(tmp_path, "p0", prev_cfg)
    cur = _write_run(tmp_path, "p1", cur_cfg)
    tsv = tmp_path / "_runs" / "results.tsv"
    sid = str(prev_cfg.get("scenario_id") or "s")
    tsv.write_text(
        "experiment\tscenario_id\tacc\telapsed_sec\texp_dir\texploration_space\n"
        f"p0\t{sid}\t0.5\t10\t{prev}\t{prev_cell}\n",
        encoding="utf-8",
    )
    return compute_stamp(
        tmp_path,
        cur,
        elapsed_sec=10.0,
        smoke=False,
        scenario_id=sid,
        metric_key="acc",
        metrics={"acc": 0.0},  # 评测打零仍须打格
    )


def test_stamp_model_arch_catalog_drop_in_is_b_derived(tmp_path: Path):
    r = _stamp_after(
        tmp_path,
        {"LR": 0.1, "MODEL_ARCH": "cnn", "scenario_id": "s"},
        {"LR": 0.1, "MODEL_ARCH": "resnet_cnn", "scenario_id": "s"},
    )
    assert r.untrained is False
    assert r.cell == "B-derived"


def test_stamp_loss_catalog_drop_in_is_c_derived(tmp_path: Path):
    r = _stamp_after(
        tmp_path,
        {"LR": 0.1, "LOSS": "ce", "scenario_id": "s"},
        {"LR": 0.1, "LOSS": "focal", "scenario_id": "s"},
    )
    assert r.untrained is False
    assert r.cell == "C-derived"


def test_stamp_mixup_catalog_drop_in_is_d_derived(tmp_path: Path):
    r = _stamp_after(
        tmp_path,
        {"LR": 0.1, "MIXUP_ALPHA": 0.0, "scenario_id": "s"},
        {"LR": 0.1, "MIXUP_ALPHA": 0.2, "scenario_id": "s"},
    )
    assert r.untrained is False
    assert r.cell == "D-derived"


def test_stamp_unknown_arch_is_b_different(tmp_path: Path):
    r = _stamp_after(
        tmp_path,
        {"LR": 0.1, "MODEL_ARCH": "cnn", "scenario_id": "s"},
        {"LR": 0.1, "MODEL_ARCH": "brand_new_unregistered_net", "scenario_id": "s"},
    )
    assert r.untrained is False
    assert r.cell == "B-different"


def test_stamp_bcd_drops_incidental_lr(tmp_path: Path):
    """同时改学习率与模型 → 格子是模型档，不记成只调学习率。"""
    r = _stamp_after(
        tmp_path,
        {"LR": 0.1, "MODEL_ARCH": "cnn", "scenario_id": "s"},
        {"LR": 0.01, "MODEL_ARCH": "resnet_cnn", "scenario_id": "s"},
    )
    assert r.cell.startswith("B-")
    assert not r.cell.startswith("A-")


def test_stamp_first_in_scenario_is_a_routine(tmp_path: Path):
    """现状：场景首行固定 A-routine（规格 §4.3 要比朴素尺/默认 config，尚未兑现）。"""
    cur = _write_run(tmp_path, "p1", {"LR": 0.1, "MODEL_ARCH": "resnet_cnn", "scenario_id": "s"})
    r = compute_stamp(
        tmp_path, cur, elapsed_sec=10.0, smoke=False, scenario_id="s", metric_key="acc", metrics={"acc": 0.5},
    )
    assert r.untrained is False
    assert r.cell == "A-routine"
    assert "first_in_scenario" in r.reasons


def test_stamp_other_scenario_is_not_prev(tmp_path: Path):
    """对照只认同场景，别的场景的正式行不能当上一把。"""
    other = _write_run(tmp_path, "o0", {"LR": 0.1, "MODEL_ARCH": "cnn", "scenario_id": "other"})
    cur = _write_run(tmp_path, "p1", {"LR": 0.2, "MODEL_ARCH": "cnn", "scenario_id": "s"})
    tsv = tmp_path / "_runs" / "results.tsv"
    tsv.write_text(
        "experiment\tscenario_id\tacc\telapsed_sec\texp_dir\texploration_space\n"
        f"o0\tother\t0.5\t10\t{other}\tB-derived\n",
        encoding="utf-8",
    )
    r = compute_stamp(
        tmp_path, cur, elapsed_sec=10.0, smoke=False, scenario_id="s", metric_key="acc", metrics={"acc": 0.6},
    )
    assert r.cell == "A-routine"
    assert "first_in_scenario" in r.reasons


def test_stamp_workspace_model_path_is_b(tmp_path: Path, monkeypatch):
    cfg = {"LR": 0.1, "MODEL_ARCH": "cnn", "scenario_id": "s"}
    prev = _write_run(tmp_path, "p0", cfg)
    cur = _write_run(tmp_path, "p1", cfg)

    def _fake_diff(base, target):
        del base, target
        return {
            "changed_files": ["workspace/models/net.py"],
            "summaries": ["+ workspace/models/net.py"],
        }

    monkeypatch.setattr("lib.exploration_stamp.diff_code_snapshots", _fake_diff)
    tsv = tmp_path / "_runs" / "results.tsv"
    tsv.write_text(
        "experiment\tscenario_id\tacc\telapsed_sec\texp_dir\texploration_space\n"
        f"p0\ts\t0.5\t10\t{prev}\tA-routine\n",
        encoding="utf-8",
    )
    r = compute_stamp(
        tmp_path, cur, elapsed_sec=10.0, smoke=False, scenario_id="s", metric_key="acc", metrics={"acc": 0.6},
    )
    assert r.untrained is False
    assert r.cell.startswith("B-")


def test_stamp_clamps_novel_to_different(tmp_path: Path, monkeypatch):
    class _Fp:
        depth = "novel"
        effective_depth = "novel"
        reasons = ["mock_novel"]

    monkeypatch.setattr(
        "lib.exploration_stamp.compute_fingerprint_from_configs",
        lambda *a, **k: _Fp(),
    )
    r = _stamp_after(
        tmp_path,
        {"LR": 0.1, "MODEL_ARCH": "cnn", "scenario_id": "s"},
        {"LR": 0.1, "MODEL_ARCH": "resnet_cnn", "scenario_id": "s"},
    )
    assert r.cell == "B-different"
    assert "clamp_novel_to_different" in r.reasons
