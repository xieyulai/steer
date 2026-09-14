"""modify-config --from-template 默认 baseline_tag=none。"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

MOD = Path(__file__).resolve().parent.parent / "modify-config.py"


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(MOD), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_from_template_strips_plain_unless_explicit(tmp_path: Path):
    src = tmp_path / "base.json"
    src.write_text(json.dumps({"LR": 0.1, "baseline_tag": "plain"}), encoding="utf-8")
    out = tmp_path / "new.json"
    r = _run(
        [str(out), "--from-template", str(src), "--set", "EPOCHS=10"],
        tmp_path,
    )
    assert r.returncode == 0, r.stderr
    cfg = json.loads(out.read_text(encoding="utf-8"))
    assert cfg["baseline_tag"] == "none"
    assert cfg["EPOCHS"] == 10


def test_from_template_keeps_explicit_baseline_tag(tmp_path: Path):
    src = tmp_path / "base.json"
    src.write_text(json.dumps({"LR": 0.1, "baseline_tag": "none"}), encoding="utf-8")
    out = tmp_path / "new.json"
    r = _run(
        [
            str(out),
            "--from-template",
            str(src),
            "--set",
            "baseline_tag=plain",
        ],
        tmp_path,
    )
    assert r.returncode == 0, r.stderr
    cfg = json.loads(out.read_text(encoding="utf-8"))
    assert cfg["baseline_tag"] == "plain"


def test_inplace_set_does_not_force_none(tmp_path: Path):
    cfg_path = tmp_path / "exp.json"
    cfg_path.write_text(
        json.dumps({"LR": 0.1, "baseline_tag": "plain"}), encoding="utf-8"
    )
    r = _run([str(cfg_path), "--set", "LR=0.2"], tmp_path)
    assert r.returncode == 0, r.stderr
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert cfg["baseline_tag"] == "plain"
    assert cfg["LR"] == 0.2
