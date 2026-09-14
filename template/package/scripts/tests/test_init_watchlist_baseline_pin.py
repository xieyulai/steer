"""init_watchlist：系统键 baseline_tag 钉死。"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
SCRIPT = SCRIPTS / "init_watchlist.py"


def _load_mod():
    spec = importlib.util.spec_from_file_location("init_watchlist", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_pin_system_ledger_keys_appends_baseline_tag():
    mod = _load_mod()
    assert mod.pin_system_ledger_keys(["LR", "EPOCHS"]) == ["LR", "EPOCHS", "baseline_tag"]
    assert mod.pin_system_ledger_keys(["LR", "baseline_tag"]) == ["LR", "baseline_tag"]


def test_recommend_keeps_baseline_tag_after_cfg_intersect():
    """求交只命中超参时，仍 append baseline_tag（cifar 类漏列场景）。"""
    mod = _load_mod()
    default = ["LR", "BATCH_SIZE", "baseline_tag", "EPOCHS"]
    cfg_keys = {"LR", "BATCH_SIZE", "EPOCHS"}  # 无 baseline_tag
    rec = mod.recommend_watchlist(default, cfg_keys)
    assert "LR" in rec and "BATCH_SIZE" in rec
    assert "baseline_tag" in rec


def test_dry_run_stdout_includes_baseline_tag(tmp_path: Path):
    pkg = tmp_path / "template" / "package"
    pkg.mkdir(parents=True)
    (pkg / "profiles.yaml").write_text(
        "profiles:\n  supervised:\n    default_watchlist: [LR, BATCH_SIZE, baseline_tag]\n",
        encoding="utf-8",
    )
    cfg_dir = tmp_path / "_runs" / "exp" / "a"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.json").write_text('{"LR": 0.1, "BATCH_SIZE": 32}', encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(tmp_path),
            "--template-root",
            "template/package",
            "--profile",
            "supervised",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "baseline_tag" in result.stdout
