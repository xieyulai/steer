"""nn_baseline CLI：stamp 后 status 能看见尺子。"""
from __future__ import annotations

import json
from pathlib import Path

from nn_baseline import main


def _exp(root: Path, name: str, primary: float) -> None:
    d = root / "_runs" / "exp" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.json").write_text(
        json.dumps({"SEED": 1, "SCENARIO_ID": "seq", "baseline_tag": "none"}),
        encoding="utf-8",
    )
    (d / "results.json").write_text(
        json.dumps({"metrics": {"test_acc": primary}}), encoding="utf-8",
    )


def test_stamp_then_status(tmp_path: Path, capsys):
    _exp(tmp_path, "p1", 0.3)
    (tmp_path / "_runs").mkdir(exist_ok=True)
    (tmp_path / "_runs" / "results.tsv").write_text(
        "experiment\tscenario_id\tbaseline_tag\texp_dir\ttest_acc\n"
        "p1\tseq\tnone\t_runs/exp/p1\t0.3\n",
        encoding="utf-8",
    )
    rc = main(["stamp", "--repo-root", str(tmp_path), "--tag", "plain", "--exp-dir", "_runs/exp/p1"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    rc2 = main(["stamp", "--repo-root", str(tmp_path), "--tag", "plain", "--exp-dir", "_runs/exp/p1"])
    # 同一行再贴同一尺：existing 不含自己 → 幂等成功
    assert rc2 == 0
    capsys.readouterr()
    rc3 = main(["status", "--repo-root", str(tmp_path), "--scenario", "seq"])
    assert rc3 == 0
    st = json.loads(capsys.readouterr().out)
    assert st["has_plain"] is True
    assert any("/auto-nn-reference" in r for r in st["recommendations"])


def test_check_source_cal_over_tolerance_exit_2(tmp_path: Path, capsys):
    src = tmp_path / "upstream"
    src.mkdir()
    nn = tmp_path / ".auto-nn"
    nn.mkdir()
    (nn / "migration-source").write_text(str(src) + "\n", encoding="utf-8")
    saved = tmp_path / "saved"
    saved.mkdir()
    (saved / "source_calibration.json").write_text(
        json.dumps({"schema_version": 1, "source_cal_value": 0.95}), encoding="utf-8"
    )
    _exp(tmp_path, "dla", 0.87)
    (tmp_path / "_runs" / "results.tsv").write_text(
        "experiment\tscenario_id\tbaseline_tag\texp_dir\ttest_acc\n"
        "dla\tseq\tnone\t_runs/exp/dla\t0.87\n",
        encoding="utf-8",
    )
    (tmp_path / "nn-config.yaml").write_text("goal:\n  metric: test_acc\n", encoding="utf-8")
    rc = main(
        [
            "check-source-cal",
            "--repo-root",
            str(tmp_path),
            "--exp-dir",
            "_runs/exp/dla",
        ]
    )
    assert rc == 2
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert out["check"]["verdict"] == "fail"
