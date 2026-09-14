"""Analyze contract.test.run vs Contract.test facade for adapter_runner kw."""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SignatureReport:
    run_accepts_adapter_runner: bool
    facade_mode: str  # always | conditional | unknown
    doctor_status: str  # PASS | FAIL | WARN | SKIP
    message: str


_FIX = (
    "补齐 contract/test.py::run(..., adapter_runner=None)；"
    "门面与模板 contract/__init__.py 对齐（总是转发）；"
    "不要用 conditional 门面长期绕过"
)


def _run_accepts_adapter_runner(tree: ast.AST) -> bool:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "run":
            for a in node.args.kwonlyargs:
                if a.arg == "adapter_runner":
                    return True
            for a in node.args.args:
                if a.arg == "adapter_runner":
                    return True
            if node.args.kwarg is not None:
                return True
            return False
    return False


def _call_has_adapter_runner_kw(call: ast.Call) -> bool:
    return any(
        isinstance(kw, ast.keyword) and kw.arg == "adapter_runner" for kw in call.keywords
    )


def _is_run_call(call: ast.Call) -> bool:
    func = call.func
    if isinstance(func, ast.Name) and func.id == "run":
        return True
    if isinstance(func, ast.Attribute) and func.attr == "run":
        return True
    return False


def _facade_mode_from_test_method(func: ast.FunctionDef) -> str:
    """Classify how test() forwards adapter_runner to run().

    - always: 所有 run 调用都带 adapter_runner=
    - conditional: 同时存在带/不带 adapter_runner= 的 run 调用（典型：is None 分支不传）
    - unknown: 无 run 调用或无法归类
    """
    with_kw = False
    without_kw = False
    for node in ast.walk(func):
        if isinstance(node, ast.Call) and _is_run_call(node):
            if _call_has_adapter_runner_kw(node):
                with_kw = True
            else:
                without_kw = True
    if with_kw and without_kw:
        return "conditional"
    if with_kw:
        return "always"
    return "unknown"


def _facade_mode(init_path: Path) -> str:
    if not init_path.is_file():
        return "unknown"
    try:
        tree = ast.parse(init_path.read_text(encoding="utf-8"), filename=str(init_path))
    except SyntaxError:
        return "unknown"
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "test":
                    return _facade_mode_from_test_method(item)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "test":
            return _facade_mode_from_test_method(node)
    return "unknown"


def analyze_contract_test_signature(repo_root: Path) -> SignatureReport:
    repo_root = Path(repo_root)
    test_py = repo_root / "contract" / "test.py"
    if not test_py.is_file():
        return SignatureReport(
            run_accepts_adapter_runner=False,
            facade_mode="unknown",
            doctor_status="SKIP",
            message="无 contract/test.py",
        )
    try:
        tree = ast.parse(test_py.read_text(encoding="utf-8"), filename=str(test_py))
    except SyntaxError as exc:
        return SignatureReport(
            run_accepts_adapter_runner=False,
            facade_mode="unknown",
            doctor_status="WARN",
            message=f"contract/test.py 无法解析: {exc}",
        )

    accepts = _run_accepts_adapter_runner(tree)
    mode = _facade_mode(repo_root / "contract" / "__init__.py")

    if accepts:
        return SignatureReport(
            run_accepts_adapter_runner=True,
            facade_mode=mode,
            doctor_status="PASS",
            message="run 接受 adapter_runner",
        )
    if mode == "always":
        return SignatureReport(
            run_accepts_adapter_runner=False,
            facade_mode=mode,
            doctor_status="FAIL",
            message=f"门面总转发 adapter_runner 但 run 不接参 — {_FIX}",
        )
    return SignatureReport(
        run_accepts_adapter_runner=False,
        facade_mode=mode,
        doctor_status="WARN",
        message=f"run 不接受 adapter_runner（facade={mode}）— {_FIX}",
    )
