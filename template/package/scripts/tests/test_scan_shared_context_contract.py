"""scan_shared_context_contract：禁止袋内 contract。"""
from __future__ import annotations

import sys
from pathlib import Path

_PKG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PKG / "scripts"))

from lib.scan_shared_context_contract import find_shared_context_contract_violations  # noqa: E402


def test_clean_repo(tmp_path: Path) -> None:
    (tmp_path / "train.py").write_text(
        "shared_context = {'device': None, 'cfg': {}}\n",
        encoding="utf-8",
    )
    (tmp_path / "contract").mkdir()
    (tmp_path / "contract" / "test.py").write_text(
        "def run(learner, ws, *, shared_context):\n"
        "    cfg = shared_context['cfg']\n"
        "    return {}\n",
        encoding="utf-8",
    )
    assert find_shared_context_contract_violations(tmp_path) == []


def test_get_contract_fails(tmp_path: Path) -> None:
    (tmp_path / "contract").mkdir()
    (tmp_path / "contract" / "test.py").write_text(
        "def run(learner, ws, *, shared_context):\n"
        "    c = shared_context.get('contract')\n"
        "    return {}\n",
        encoding="utf-8",
    )
    v = find_shared_context_contract_violations(tmp_path)
    assert v and "get('contract')" in v[0]


def test_subscript_assign_fails(tmp_path: Path) -> None:
    (tmp_path / "train.py").write_text(
        "shared_context = {}\n"
        "shared_context['contract'] = object()\n",
        encoding="utf-8",
    )
    v = find_shared_context_contract_violations(tmp_path)
    assert v and "['contract']" in v[0]


def test_template_package_clean() -> None:
    """模板 package 根（含演示 contract）应无违规。"""
    assert (_PKG / "train.py").is_file()
    assert find_shared_context_contract_violations(_PKG) == []
