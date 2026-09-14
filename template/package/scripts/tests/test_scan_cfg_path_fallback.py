"""scan_cfg_path_fallback — 禁 env/绝对路径写入全大写 cfg 键。"""
from __future__ import annotations

import sys
from pathlib import Path

_PKG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PKG / "scripts"))

from lib.scan_cfg_path_fallback import find_cfg_path_fallback_violations  # noqa: E402


def _write(repo: Path, rel: str, content: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_no_train_or_workspace_returns_empty(tmp_path: Path) -> None:
    assert find_cfg_path_fallback_violations(tmp_path) == []


def test_env_get_assigned_to_caps_cfg_key(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "train.py",
        """
import os
cfg = {}
cfg["MAMMOTH_ROOT"] = os.environ.get("MAMMOTH_ROOT", "/mnt/x/default")
""",
    )
    v = find_cfg_path_fallback_violations(tmp_path)
    assert len(v) == 1
    assert "MAMMOTH_ROOT" in v[0]
    assert "os.environ" in v[0]


def test_os_environ_subscript_assigned_to_caps_cfg_key(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "workspace/foo.py",
        """
import os
cfg = {}
cfg["DATA_ROOT"] = os.environ["DATA_ROOT"]
""",
    )
    v = find_cfg_path_fallback_violations(tmp_path)
    assert len(v) == 1
    assert "DATA_ROOT" in v[0]


def test_caps_name_subscript_with_env_fallback(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "train.py",
        """
import os
KEY = "MAMMOTH_ROOT"
cfg = {}
cfg[KEY] = os.environ.get("MAMMOTH_ROOT")
""",
    )
    v = find_cfg_path_fallback_violations(tmp_path)
    assert len(v) == 1
    assert "KEY" in v[0]
    assert "os.environ" in v[0]


def test_abs_path_literal_assigned_to_caps_cfg_key(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "train.py",
        """
cfg = {}
cfg["MAMMOTH_ROOT"] = "/mnt/shared/vendor/mammoth"
""",
    )
    v = find_cfg_path_fallback_violations(tmp_path)
    assert len(v) == 1
    assert "绝对路径" in v[0]


def test_home_and_users_abs_paths(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "workspace/paths.py",
        """
cfg = {}
cfg["VENDOR_ROOT"] = "/home/user/vendor"
cfg["MAC_ROOT"] = "/Users/dev/project"
""",
    )
    v = find_cfg_path_fallback_violations(tmp_path)
    assert len(v) == 2


def test_clean_strong_read_passes(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "train.py",
        """
def run(cfg):
    root = cfg["MAMMOTH_ROOT"]
    return root
""",
    )
    assert find_cfg_path_fallback_violations(tmp_path) == []


def test_relative_path_literal_not_violation(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "train.py",
        """
cfg = {}
cfg["REL_ROOT"] = "relative/path"
""",
    )
    assert find_cfg_path_fallback_violations(tmp_path) == []


def test_lowercase_cfg_key_not_violation(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "train.py",
        """
import os
cfg = {}
cfg["mammoth_root"] = os.environ.get("MAMMOTH_ROOT")
""",
    )
    assert find_cfg_path_fallback_violations(tmp_path) == []


def test_module_constant_for_path_passes(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "train.py",
        """
MAMMOTH_ROOT_DEFAULT = "/mnt/shared/vendor/mammoth"

def run(cfg):
    return cfg["MAMMOTH_ROOT"]
""",
    )
    assert find_cfg_path_fallback_violations(tmp_path) == []


def test_skips_pycache(tmp_path: Path) -> None:
    cache = tmp_path / "workspace" / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "bad.cpython-311.pyc").write_bytes(b"\x00")
    _write(
        tmp_path,
        "workspace/ok.py",
        "def run(cfg):\n    return cfg['MAMMOTH_ROOT']\n",
    )
    assert find_cfg_path_fallback_violations(tmp_path) == []


def test_template_package_is_clean() -> None:
    assert find_cfg_path_fallback_violations(_PKG) == []
