"""scenario_contract_guard — contract 不得持有 SCENARIO_ID。"""
from __future__ import annotations

import sys
from pathlib import Path

_PKG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PKG / "scripts"))

from lib.scenario_contract_guard import find_scenario_id_in_contract  # noqa: E402


def _write_contract(repo: Path, rel: str, content: str) -> None:
    path = repo / "contract" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_no_contract_dir_returns_empty(tmp_path: Path) -> None:
    assert find_scenario_id_in_contract(tmp_path) == []


def test_clean_contract_no_violations(tmp_path: Path) -> None:
    _write_contract(tmp_path, "metrics.py", "METRIC_KEYS: dict[str, str] = {}\n")
    assert find_scenario_id_in_contract(tmp_path) == []


def test_module_level_scenario_id_non_empty(tmp_path: Path) -> None:
    _write_contract(tmp_path, "metrics.py", 'SCENARIO_ID = "bench_a"\n')
    v = find_scenario_id_in_contract(tmp_path)
    assert len(v) == 1
    assert "SCENARIO_ID" in v[0]


def test_module_level_scenario_id_empty_string(tmp_path: Path) -> None:
    _write_contract(tmp_path, "metrics.py", 'SCENARIO_ID: str = ""\n')
    v = find_scenario_id_in_contract(tmp_path)
    assert len(v) == 1


def test_property_scenario_id_returning_constant(tmp_path: Path) -> None:
    _write_contract(
        tmp_path,
        "__init__.py",
        """
class Contract:
    @property
    def scenario_id(self):
        return SCENARIO_ID
""",
    )
    v = find_scenario_id_in_contract(tmp_path)
    assert len(v) == 1
    assert "scenario_id property" in v[0]


def test_property_scenario_id_returning_attribute(tmp_path: Path) -> None:
    _write_contract(
        tmp_path,
        "__init__.py",
        """
class Contract:
    @property
    def scenario_id(self):
        return metrics.SCENARIO_ID
""",
    )
    v = find_scenario_id_in_contract(tmp_path)
    assert len(v) == 1


def test_property_scenario_id_other_return_not_violation(tmp_path: Path) -> None:
    _write_contract(
        tmp_path,
        "__init__.py",
        """
class Contract:
    @property
    def scenario_id(self):
        return self._sid
""",
    )
    assert find_scenario_id_in_contract(tmp_path) == []


def test_skips_pycache(tmp_path: Path) -> None:
    cache = tmp_path / "contract" / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "metrics.cpython-311.pyc").write_bytes(b"\x00")
    _write_contract(tmp_path, "metrics.py", "METRIC_KEYS = {}\n")
    assert find_scenario_id_in_contract(tmp_path) == []


def test_template_package_contract_is_clean() -> None:
    root = _PKG
    assert find_scenario_id_in_contract(root) == []
