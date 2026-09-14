"""TDD: check_env_import_classify — dynamic lib vs missing pkg."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(LIB))

from check_env_import_classify import (  # noqa: E402
    classify_torch_import_failure,
    extract_missing_so_names,
    pip_packages_for_dynamic_libs,
)


def test_cudnn_so_is_dynamic_lib():
    out = (
        "ImportError: libcudnn.so.9: cannot open shared object file: "
        "No such file or directory"
    )
    assert classify_torch_import_failure(out) == "dynamic_lib"


def test_libcuda_is_dynamic_lib():
    assert classify_torch_import_failure("error: libcuda.so.1: cannot open") == "dynamic_lib"


def test_cusparselt_is_dynamic_lib():
    out = "ImportError: libcusparseLt.so.0: cannot open shared object file"
    assert classify_torch_import_failure(out) == "dynamic_lib"
    assert extract_missing_so_names(out) == ["libcusparselt"]
    assert pip_packages_for_dynamic_libs(out, cuda_wheel_tag="cu124") == [
        "nvidia-cusparselt-cu12"
    ]
    assert pip_packages_for_dynamic_libs(out, cuda_wheel_tag="cpu") == []


def test_module_not_found_is_missing_pkg():
    assert (
        classify_torch_import_failure("ModuleNotFoundError: No module named 'yaml'")
        == "missing_pkg"
    )


def test_empty_is_missing_pkg():
    assert classify_torch_import_failure("") == "missing_pkg"


def test_cli_classify_stdin():
    script = LIB / "check_env_import_classify.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--classify"],
        input="ImportError: libcudnn.so.9: cannot open shared object file\n",
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "dynamic_lib"
