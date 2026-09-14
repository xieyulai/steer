"""governance-sync 写戳前 stamp 自检：顺序 + dest 缺文件可检出。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_PKG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PKG / "scripts"))

from lib.governance_sync_manifest import missing_stamp_required  # noqa: E402


def test_governance_sync_stamp_check_before_version_write() -> None:
    text = (_PKG / "scripts" / "governance-sync.sh").read_text(encoding="utf-8")
    i_stamp = text.find("missing_stamp_required")
    i_ver = text.find('nn_state_write version')
    assert i_stamp > 0 and i_ver > 0
    assert i_stamp < i_ver


def test_dest_missing_classify_detected_against_template_manifest(
    tmp_path: Path,
) -> None:
    """模拟半套：dest 无 classify，清单仍读模板包 → missing 非空。"""
    (tmp_path / "scripts" / "lib").mkdir(parents=True)
    missing = missing_stamp_required(tmp_path, manifest_root=_PKG)
    assert "scripts/lib/check_env_import_classify.py" in missing
