"""tests/test_init_watchlist.py — F1.5 init_watchlist.py 单元测试"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "template" / "package" / "scripts" / "init_watchlist.py"


def test_dry_run_outputs_recommended_keys(tmp_path):
    """无 nn-config.yaml + 有 profiles.yaml → dry-run 列出推荐"""
    # 1. mock profiles.yaml（init_watchlist 调 load_profiles_default）
    pkg = tmp_path / "template" / "package"
    pkg.mkdir(parents=True)
    (pkg / "profiles.yaml").write_text(
        "profiles:\n  supervised:\n    default_watchlist: [LR, BATCH_SIZE, EPOCHS, OPTIMIZER, WEIGHT_DECAY, MIXUP]\n"
    )
    # 2. mock 一个 _runs/exp_a/config.json（让 first_cfg_keys 有交集）
    cfg_dir = tmp_path / "_runs" / "exp_a"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.json").write_text(
        '{"LR": 0.001, "BATCH_SIZE": 32, "EPOCHS": 10, "OPTIMIZER": "adam", "WEIGHT_DECAY": 0.0001, "MIXUP": 0.2, "DROPOUT": 0.5}'
    )

    # 3. 跑脚本 dry-run
    result = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--repo-root", str(tmp_path),
         "--template-root", "template/package",
         "--profile", "supervised",
         "--dry-run"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"script failed: {result.stderr}"
    # default_watchlist 中至少 1 个 key 出现
    assert "LR" in result.stdout
    assert "BATCH_SIZE" in result.stdout


def test_dry_run_does_not_modify_files(tmp_path):
    """dry-run 模式下 nn-config.yaml 不应被创建/修改"""
    pkg = tmp_path / "template" / "package"
    pkg.mkdir(parents=True)
    (pkg / "profiles.yaml").write_text(
        "profiles:\n  supervised:\n    default_watchlist: [LR]\n"
    )
    result = subprocess.run(
        [sys.executable, str(SCRIPT),
         "--repo-root", str(tmp_path),
         "--template-root", "template/package",
         "--profile", "supervised",
         "--dry-run"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"script failed: {result.stderr}"
    assert not (tmp_path / "nn-config.yaml").exists(), "dry-run 不应创建 nn-config.yaml"