"""stamp-required ≡ manifest group train_runtime。"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

_PKG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PKG / "scripts"))

from lib.governance_sync_manifest import (  # noqa: E402
    list_stamp_required_relpaths,
    missing_stamp_required,
)


def test_list_stamp_required_includes_classify_and_adapter() -> None:
    paths = list_stamp_required_relpaths(_PKG)
    assert "scripts/lib/check_env_import_classify.py" in paths
    assert "scripts/lib/adapter_accept.py" in paths
    assert "scripts/lib/framework_binding.py" in paths
    assert "scripts/lib/auto_mode.py" in paths
    assert "scripts/lib/contract_test_signature.py" in paths
    assert "scripts/lib/governance_sync_manifest.yaml" in paths
    assert "scripts/lib/info_perm.py" in paths
    assert "scripts/lib/home_gpus.py" in paths


def test_missing_stamp_required_reports_absent_file(tmp_path: Path) -> None:
    lib = tmp_path / "scripts" / "lib"
    lib.mkdir(parents=True)
    shutil.copy(
        _PKG / "scripts" / "lib" / "governance_sync_manifest.yaml",
        lib / "governance_sync_manifest.yaml",
    )
    # 故意不创建 train_runtime 文件
    missing = missing_stamp_required(tmp_path)
    assert "scripts/lib/check_env_import_classify.py" in missing
    assert "scripts/lib/adapter_accept.py" in missing


def test_missing_stamp_required_empty_when_files_present() -> None:
    assert missing_stamp_required(_PKG) == []


def test_missing_stamp_required_manifest_root_vs_check_root(tmp_path: Path) -> None:
    """sync 写戳前：清单读模板包，文件查业务仓。"""
    missing = missing_stamp_required(tmp_path, manifest_root=_PKG)
    assert "scripts/lib/check_env_import_classify.py" in missing
