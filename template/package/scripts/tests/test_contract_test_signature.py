"""contract_test_signature — always FAIL / conditional WARN / 模板 PASS."""
from __future__ import annotations

import sys
from pathlib import Path

_PKG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_PKG / "scripts"))

from lib.contract_test_signature import analyze_contract_test_signature  # noqa: E402


_ALWAYS_FACADE = '''\
from typing import Any
from contract import test as terminal_test

class Contract:
    def test(self, learner, ws, *, shared_context: dict, adapter_runner: Any | None = None):
        return terminal_test.run(
            learner, ws, shared_context=shared_context, adapter_runner=adapter_runner,
        )
'''

_CONDITIONAL_FACADE = '''\
from typing import Any
from contract import test as terminal_test

class Contract:
    def test(self, learner, ws, *, shared_context: dict, adapter_runner: Any | None = None):
        if adapter_runner is None:
            return terminal_test.run(learner, ws, shared_context=shared_context)
        return terminal_test.run(
            learner, ws, shared_context=shared_context, adapter_runner=adapter_runner,
        )
'''

_RUN_NO_KW = '''\
def run(learner, ws, *, shared_context: dict) -> dict:
    return {}
'''

_RUN_WITH_KW = '''\
from typing import Callable, Any
def run(learner, ws, *, shared_context: dict, adapter_runner: Callable | None = None) -> dict:
    return {}
'''


def _write_repo(root: Path, *, init: str, run: str) -> None:
    c = root / "contract"
    c.mkdir(parents=True)
    (c / "__init__.py").write_text(init, encoding="utf-8")
    (c / "test.py").write_text(run, encoding="utf-8")


def test_skip_without_test_py(tmp_path: Path) -> None:
    r = analyze_contract_test_signature(tmp_path)
    assert r.doctor_status == "SKIP"


def test_always_facade_missing_kw_fail(tmp_path: Path) -> None:
    _write_repo(tmp_path, init=_ALWAYS_FACADE, run=_RUN_NO_KW)
    r = analyze_contract_test_signature(tmp_path)
    assert r.facade_mode == "always"
    assert r.doctor_status == "FAIL"
    assert r.run_accepts_adapter_runner is False


def test_conditional_facade_missing_kw_warn(tmp_path: Path) -> None:
    _write_repo(tmp_path, init=_CONDITIONAL_FACADE, run=_RUN_NO_KW)
    r = analyze_contract_test_signature(tmp_path)
    assert r.facade_mode == "conditional"
    assert r.doctor_status == "WARN"


def test_run_with_kw_pass_even_if_always(tmp_path: Path) -> None:
    _write_repo(tmp_path, init=_ALWAYS_FACADE, run=_RUN_WITH_KW)
    r = analyze_contract_test_signature(tmp_path)
    assert r.doctor_status == "PASS"


def test_template_package_pass() -> None:
    r = analyze_contract_test_signature(_PKG)
    assert r.run_accepts_adapter_runner is True
    assert r.doctor_status == "PASS"
    assert r.facade_mode == "always"
