"""Classify poetry/torch import failures for check-env / setup messaging.

Separates CUDA/cuDNN shared-library load errors from missing pip packages
so repair hints are not wrongly 「poetry install」.
Maps a few common ``.so`` names to nvidia pip wheels for setup best-effort install.
"""
from __future__ import annotations

import argparse
import re
import sys

_DYNAMIC_LIB_RE = re.compile(
    r"libcudnn|libcuda|libcusparselt|cusparselt|"
    r"cannot open shared object file|\.so\.\d+",
    re.IGNORECASE,
)

# 缺库片段（小写）→ pip 包名（cu12 系；cpu / 未知档不映射）
_SO_TO_PIP_CU12: dict[str, str] = {
    "libcusparselt": "nvidia-cusparselt-cu12",
    "cusparselt": "nvidia-cusparselt-cu12",
    "libcudnn": "nvidia-cudnn-cu12",
}

_SO_NAME_RE = re.compile(
    r"(libcusparselt|libcudnn|libcuda)(?:\.so[.\d]*)?",
    re.IGNORECASE,
)


def classify_torch_import_failure(output: str) -> str:
    """Return ``dynamic_lib`` or ``missing_pkg`` for failed import diagnostics."""
    text = output or ""
    if _DYNAMIC_LIB_RE.search(text):
        return "dynamic_lib"
    return "missing_pkg"


def extract_missing_so_names(output: str) -> list[str]:
    """从报错文本抽出缺库 basename（小写、去重、保序）。"""
    seen: set[str] = set()
    out: list[str] = []
    for m in _SO_NAME_RE.finditer(output or ""):
        name = m.group(1).lower()
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def pip_packages_for_dynamic_libs(
    output: str, *, cuda_wheel_tag: str | None = None
) -> list[str]:
    """缺库 → 可尝试的 nvidia pip 包（仅 cu12 系 wheel；未知/cpu → 空）。

    ``cuda_wheel_tag`` 如 ``cu124`` / ``cu121`` / ``cu118`` / ``cpu``。
    """
    tag = (cuda_wheel_tag or "").strip().lower()
    if not tag.startswith("cu12"):
        return []
    pkgs: list[str] = []
    seen: set[str] = set()
    for so in extract_missing_so_names(output):
        pkg = _SO_TO_PIP_CU12.get(so)
        if pkg and pkg not in seen:
            seen.add(pkg)
            pkgs.append(pkg)
    return pkgs


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Classify torch import failure output")
    p.add_argument(
        "--classify",
        action="store_true",
        help="Read failure text from stdin; print dynamic_lib|missing_pkg",
    )
    args = p.parse_args(argv)
    if not args.classify:
        p.error("use --classify and pipe failure text on stdin")
    kind = classify_torch_import_failure(sys.stdin.read())
    print(kind)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
