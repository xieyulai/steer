"""Local API doc inspection via importlib + inspect (no HTTP)."""
from __future__ import annotations

import importlib
import inspect
from typing import Any

_DOC_EXCERPT_MAX = 480

# Short names from innovation_catalog docs_symbols → import path（命名空间表，AC②）。
# 表里列出的 = 已知标准件（catalog 显式登记的 docs_symbols）。未列出但形如
# torch.nn.<Name> 的仍由 _resolve_import_path 兜底解析；表的作用是显式登记 + 为
# 非 torch.nn.<Name> 的标准件（将来如有）留映射位。改 catalog docs_symbols 时同步维护此表。
_SYMBOL_IMPORTS: dict[str, str] = {
    # objectives
    "CrossEntropyLoss": "torch.nn.CrossEntropyLoss",
    "MSELoss": "torch.nn.MSELoss",
    "BCEWithLogitsLoss": "torch.nn.BCEWithLogitsLoss",
    "NLLLoss": "torch.nn.NLLLoss",
    "L1Loss": "torch.nn.L1Loss",
    "SmoothL1Loss": "torch.nn.SmoothL1Loss",
    # activations
    "ReLU": "torch.nn.ReLU",
    "SiLU": "torch.nn.SiLU",
}


def _resolve_import_path(name: str) -> str:
    stripped = name.strip()
    if not stripped:
        raise ValueError("symbol name must be non-empty")
    if "." in stripped:
        return stripped
    if stripped in _SYMBOL_IMPORTS:
        return _SYMBOL_IMPORTS[stripped]
    return f"torch.nn.{stripped}"


def _import_object(import_path: str) -> tuple[str, Any]:
    module_path, _, attr = import_path.rpartition(".")
    if not module_path or not attr:
        raise ImportError(f"cannot resolve import path: {import_path}")
    module = importlib.import_module(module_path)
    obj = getattr(module, attr)
    return module_path, obj


def _doc_excerpt(doc: str | None) -> str:
    if not doc:
        return ""
    text = inspect.cleandoc(doc)
    if len(text) <= _DOC_EXCERPT_MAX:
        return text
    return text[: _DOC_EXCERPT_MAX - 1].rstrip() + "…"


def inspect_symbol(name: str) -> dict[str, str]:
    import_path = _resolve_import_path(name)
    module_path, obj = _import_object(import_path)
    doc = inspect.getdoc(obj)
    symbol = import_path.rpartition(".")[2] or name.strip()
    return {
        "symbol": symbol,
        "module": module_path,
        "doc_excerpt": _doc_excerpt(doc),
        "source": "local",
    }


def scan_symbols(names: list[str]) -> list[dict[str, str]]:
    """逐符号容错扫描（T6/ADR-4）。

    可 import（标准件）→ inspect_symbol 快照（source="local"）；不可 import
    （非标准件技法，如自定义 loss / mixup）→ source="not_importable" 记 error。
    单个符号炸不影响整批——整批扫描不抛。depth 判定层据此决定是否封顶 derived。
    """
    out: list[dict[str, str]] = []
    for name in names:
        stripped = name.strip() if isinstance(name, str) else ""
        if not stripped:
            continue
        try:
            out.append(inspect_symbol(stripped))
        except Exception as exc:  # importlib/AttributeError 等皆视作不可 import（非致命）
            out.append({
                "symbol": stripped,
                "module": "",
                "doc_excerpt": "",
                "source": "not_importable",
                "error": f"{type(exc).__name__}: {exc}",
            })
    return out
