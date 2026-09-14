#!/usr/bin/env python3
"""信息权限（INFO_PERM）扫描库 — 不依赖 torch。

读 ``contract/runtime.py::INFO_PERM``（必须是字面量）：

  IP0 登记表非字面量 / 值域错
  IP4 受限交卷路径未被 run() 调用或平凡   IP5 交卷开关函数不是单条 return True/False
  运行时：工作区 / train.py 真打开只评路径或真调用只评函数（栈无读者）→ FAIL
  源码字面量 IP1–IP3 仅清单，不拦预检 / 体检

另提供 ``check_train_batch_keys``（首 batch 键白名单）与 ``collect_guard_bypasses``（旁路留痕）。
消费方：experiment.py（G-信息权限 / finalize_run）、nn-doctor、verify、info_perm_gate、单测。

CLI：``python3 scripts/lib/info_perm.py [repo_root]`` → exit 0 合同静态无违规；1 为 IP0/IP4/IP5。

不在范围（诚实声明）：拷成别名再读、把数组贴进源码、C 扩展 I/O、工作区自己重建测试集。
"""
from __future__ import annotations

import ast
import builtins
import fnmatch
import importlib
import inspect
import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

OFFICIAL_PATHS = ("full_model", "restricted", "eval_mode_locked")
DEFAULT_READERS = ("contract/test.py",)
DEFAULT_SWITCH = "_official_path_enabled"
_ALLOWED_KEYS = frozenset({
    "enforce", "official_path", "official_path_impl", "official_path_switch",
    "eval_only_assets", "eval_only_readers", "train_batch_keys", "strict_no_train_files",
})
_FALSY = ("0", "false", "no", "off")

# IP3：终结调用名 → 允许的属性链前缀（"" = 裸名，如 from scipy.io import loadmat）
_DATA_READ_CALLS: dict[str, frozenset[str]] = {
    "load": frozenset({"np", "numpy"}),
    "loadtxt": frozenset({"np", "numpy"}),
    "genfromtxt": frozenset({"np", "numpy"}),
    "loadmat": frozenset({"", "sio", "io", "scipy.io"}),
    "File": frozenset({"h5py"}),
    "read_csv": frozenset({"pd", "pandas"}),
    "read_parquet": frozenset({"pd", "pandas"}),
    "read_hdf": frozenset({"pd", "pandas"}),
    "open_dataset": frozenset({"xr", "xarray"}),
    "open_dataarray": frozenset({"xr", "xarray"}),
}


class InfoPermError(ValueError):
    """INFO_PERM 登记表本身不合法（IP0）。"""


@dataclass(frozen=True)
class InfoPerm:
    enforce: bool
    official_path: str
    official_path_impl: str | None
    official_path_switch: str
    eval_only_assets: tuple[str, ...]
    eval_only_readers: tuple[str, ...]
    train_batch_keys: tuple[str, ...] | None
    strict_no_train_files: bool


@dataclass(frozen=True)
class Violation:
    rule: str
    path: str
    line: int
    detail: str
    fix: str


# ── 登记表 ────────────────────────────────────────────────────────

def _read_ast(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return None


def _str_tuple(v: Any, key: str) -> tuple[str, ...]:
    if isinstance(v, (list, tuple)) and all(isinstance(x, str) for x in v):
        return tuple(v)
    raise InfoPermError(f"INFO_PERM[{key!r}] 须为字符串 tuple/list，得到 {type(v).__name__}")


def load_info_perm(repo_root: str | os.PathLike) -> InfoPerm | None:
    """读 ``contract/runtime.py`` 的 ``INFO_PERM``；未登记 → None；非字面量 / 值域错 → InfoPermError。"""
    rt = Path(repo_root) / "contract" / "runtime.py"
    tree = _read_ast(rt)
    if tree is None:
        return None
    node: ast.expr | None = None
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "INFO_PERM" for t in stmt.targets
        ):
            node = stmt.value
    if node is None:
        return None
    try:
        raw = ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError) as exc:
        raise InfoPermError(
            "INFO_PERM 必须是字面量 dict（不得读 os.environ / 调函数）；对照两臂请拷两份合同"
        ) from exc
    if not isinstance(raw, dict):
        raise InfoPermError("INFO_PERM 必须是 dict")
    unknown = set(raw) - _ALLOWED_KEYS
    if unknown:
        raise InfoPermError(f"INFO_PERM 未知键 {sorted(unknown)}；允许 {sorted(_ALLOWED_KEYS)}")
    enforce = raw.get("enforce", True)
    if not isinstance(enforce, bool):
        raise InfoPermError("INFO_PERM['enforce'] 须为 bool")
    op = raw.get("official_path", "full_model")
    if op not in OFFICIAL_PATHS:
        raise InfoPermError(f"INFO_PERM['official_path'] 须为 {OFFICIAL_PATHS} 之一，得到 {op!r}")
    impl = raw.get("official_path_impl")
    if impl is not None and not (isinstance(impl, str) and impl.strip()):
        raise InfoPermError("INFO_PERM['official_path_impl'] 须为非空 str 或 None")
    if op != "full_model" and impl is None:
        raise InfoPermError(
            f"official_path={op!r} 时 official_path_impl 不得为 None（run() 必须调用的函数名）"
        )
    switch = raw.get("official_path_switch", DEFAULT_SWITCH)
    if not (isinstance(switch, str) and switch.strip()):
        raise InfoPermError("INFO_PERM['official_path_switch'] 须为非空 str")
    keys = raw.get("train_batch_keys")
    strict = raw.get("strict_no_train_files", False)
    if not isinstance(strict, bool):
        raise InfoPermError("INFO_PERM['strict_no_train_files'] 须为 bool")
    return InfoPerm(
        enforce=enforce,
        official_path=op,
        official_path_impl=impl,
        official_path_switch=switch,
        eval_only_assets=_str_tuple(raw.get("eval_only_assets", ()), "eval_only_assets"),
        eval_only_readers=_str_tuple(raw.get("eval_only_readers", DEFAULT_READERS), "eval_only_readers"),
        train_batch_keys=None if keys is None else _str_tuple(keys, "train_batch_keys"),
        strict_no_train_files=strict,
    )


# ── AST 工具 ──────────────────────────────────────────────────────

def is_callable_asset(asset: str) -> bool:
    """以 ``contract.`` 开头且不含 ``/`` ``*`` 的条目视为点名读取函数，其余按路径 glob。"""
    return asset.startswith("contract.") and "/" not in asset and "*" not in asset


def _asset_matches(literal: str, glob: str) -> bool:
    """fnmatch 无 globstar：``**/`` 视为「零或多层目录」，另允许任意前缀（绝对路径 / Path 拼接）。"""
    s = literal.replace("\\", "/")
    variants = {glob, glob.replace("**/", ""), glob.replace("/**", "")}
    for g in variants:
        if fnmatch.fnmatchcase(s, g) or fnmatch.fnmatchcase(s, "*/" + g):
            return True
    base = glob.rsplit("/", 1)[-1]
    if not base:
        return False
    if any(c in base for c in "*?["):
        # 裸文件名字面量（Path(DATA_DIR) / "x.mat" 这类拼接）只比基名
        return "/" not in s and fnmatch.fnmatchcase(s, base)
    return s.endswith(base)


def _scan_targets(repo_root: Path, readers: tuple[str, ...]) -> list[Path]:
    out: list[Path] = []
    tp = repo_root / "train.py"
    if tp.is_file():
        out.append(tp)
    ws = repo_root / "workspace"
    if ws.is_dir():
        out.extend(sorted(p for p in ws.rglob("*.py") if "__pycache__" not in p.parts))
    rd = {r.strip("/").replace("\\", "/") for r in readers}
    return [p for p in out if p.relative_to(repo_root).as_posix() not in rd]


def _docstring_ids(tree: ast.Module) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def _string_literals(tree: ast.Module) -> list[tuple[str, int]]:
    skip = _docstring_ids(tree)
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
            out.append((node.value, int(getattr(node, "lineno", 0) or 0)))
    return out


def _dotted(node: ast.AST) -> str | None:
    parts: list[str] = []
    cur = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        return ".".join(reversed(parts))
    return None


def _callable_refs(tree: ast.Module, dotted_callable: str) -> list[tuple[int, str]]:
    """工作区文件对 ``contract.<mod>.<func>`` 的引用：直接 import，或经模块别名的属性链。"""
    mod, func = dotted_callable.rsplit(".", 1)
    parent, _, last = mod.rpartition(".")
    hits: list[tuple[int, str]] = []
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == mod:
                for a in node.names:
                    if a.name == func:
                        hits.append((node.lineno, f"from {mod} import {func}"))
            if node.module == parent:
                for a in node.names:
                    if a.name == last:
                        aliases.add(a.asname or a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name == mod:
                    aliases.add(a.asname or a.name)
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            d = _dotted(node)
            if d and any(d == f"{al}.{func}" for al in aliases):
                hits.append((node.lineno, d))
    return hits


def _open_mode_is_binary_read(call: ast.Call) -> bool:
    mode: Any = None
    if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant):
        mode = call.args[1].value
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            mode = kw.value.value
    return isinstance(mode, str) and "b" in mode and not any(c in mode for c in "wax+")


def _data_read_calls(tree: ast.Module) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        d = _dotted(node.func)
        if d is None:
            continue
        prefix, _, name = d.rpartition(".")
        allowed = _DATA_READ_CALLS.get(name)
        if allowed is not None and prefix in allowed:
            hits.append((node.lineno, d))
        elif d == "open" and _open_mode_is_binary_read(node):
            hits.append((node.lineno, "open(..., 'rb')"))
    return hits


def _module_func(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    for stmt in tree.body:
        if isinstance(stmt, ast.FunctionDef) and stmt.name == name:
            return stmt
    return None


def _body_without_docstring(func: ast.FunctionDef) -> list[ast.stmt]:
    body = list(func.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    return body


def _is_trivial(func: ast.FunctionDef) -> bool:
    body = _body_without_docstring(func)
    if not body:
        return True
    for stmt in body:
        if isinstance(stmt, (ast.Pass, ast.Raise)):
            continue
        if isinstance(stmt, ast.Return) and (stmt.value is None or isinstance(stmt.value, ast.Constant)):
            continue
        return False
    return True


def _calls_name(func: ast.FunctionDef, name: str) -> bool:
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            d = _dotted(node.func)
            if d and (d == name or d.endswith("." + name)):
                return True
    return False


def _is_literal_bool_switch(func: ast.FunctionDef) -> bool:
    body = _body_without_docstring(func)
    return (
        len(body) == 1
        and isinstance(body[0], ast.Return)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, bool)
    )


# ── 源码清单（IP1–IP3，不拦预检）──────────────────────────────────

def inventory_eval_only_literals(repo_root: str | os.PathLike) -> list[Violation]:
    """工作区 / train.py 里出现的只评字面量、点名函数、严格档读取调用。未调用不算犯规。"""
    root = Path(repo_root).resolve()
    perm = load_info_perm(root)
    if perm is None or not perm.enforce:
        return []
    out: list[Violation] = []
    globs = [a for a in perm.eval_only_assets if not is_callable_asset(a)]
    callables = [a for a in perm.eval_only_assets if is_callable_asset(a)]
    for path in _scan_targets(root, perm.eval_only_readers):
        tree = _read_ast(path)
        if tree is None:
            continue
        rel = path.relative_to(root).as_posix()
        for lit, line in _string_literals(tree):
            for g in globs:
                if _asset_matches(lit, g):
                    out.append(Violation(
                        "IP1", rel, line,
                        f"字面量 {lit!r} 匹配只评资产 {g!r}（预留不算犯规；训练真打开才拦）",
                        "默认不要走这条路径；开治理下训练真打开只评材料会失败",
                    ))
                    break
        for c in callables:
            for line, what in _callable_refs(tree, c):
                out.append(Violation(
                    "IP2", rel, line,
                    f"引用只评读取函数 {what}（预留不算犯规；训练真调用才拦）",
                    f"默认不要调用 {c}；开治理下训练真调用会失败",
                ))
        if perm.strict_no_train_files:
            for line, what in _data_read_calls(tree):
                out.append(Violation(
                    "IP3", rel, line,
                    f"严格档下出现数据读取 {what}（预留不算犯规；训练真执行才拦）",
                    "默认不要读数据文件；开治理下训练真读会失败",
                ))
    return out


# ── 合同静态（IP4 / IP5）；IP1–IP3 不在此 FAIL ─────────────────────

def check_info_perm(repo_root: str | os.PathLike) -> list[Violation]:
    """合同静态：IP4/IP5。未登记或 ``enforce=False`` → ``[]``；IP0 → raise InfoPermError。"""
    root = Path(repo_root).resolve()
    perm = load_info_perm(root)
    if perm is None or not perm.enforce:
        return []
    out: list[Violation] = []
    ttree = _read_ast(root / "contract" / "test.py")
    if ttree is not None:
        if perm.official_path != "full_model":
            impl = perm.official_path_impl or ""
            run = _module_func(ttree, "run")
            f = _module_func(ttree, impl)
            if f is None or _is_trivial(f):
                out.append(Violation(
                    "IP4", "contract/test.py", int(getattr(f, "lineno", 0) or 0),
                    f"official_path={perm.official_path!r} 但 {impl}() 缺失或函数体平凡",
                    f"在 contract/test.py 实现 {impl}()（受限交卷手续）；失败返回 None，不回退整网",
                ))
            elif run is None or not _calls_name(run, impl):
                out.append(Violation(
                    "IP4", "contract/test.py", int(getattr(run, "lineno", 0) or 0),
                    f"official_path={perm.official_path!r} 但 run() 未调用 {impl}()",
                    f"官方分只能从 {impl}() 出；run() 循环内改为调用它",
                ))
        sw = _module_func(ttree, perm.official_path_switch)
        if sw is not None and not _is_literal_bool_switch(sw):
            out.append(Violation(
                "IP5", "contract/test.py", sw.lineno,
                f"{perm.official_path_switch}() 不是单条 return True/False（疑似读 env）",
                "开关写死字面量；对照两臂拷两份合同，不用环境变量切换",
            ))
    return out


# ── 运行时：真打开 / 真调用才拦 ──────────────────────────────────

_DATA_SUFFIXES = frozenset({".mat", ".npy", ".npz", ".h5", ".hdf5", ".csv", ".parquet", ".bin"})
_tls = threading.local()
_guards: list[tuple[Path, InfoPerm]] = []
_io_patched = False
_orig: dict[str, Any] = {}
_callable_orig: list[tuple[Any, str, Any]] = []

_RUNTIME_FAIL = (
    "[G-信息权限] 训练真用了只评材料（只评文件或只评读取函数；"
    "官方打分走合同测试可以）。本守门无环境变量开关；改 enforce = 改合同。"
)


def _coerce_path(file: Any) -> Path | None:
    if file is None or isinstance(file, int):
        return None
    if isinstance(file, (bytes, bytearray)):
        try:
            file = os.fsdecode(file)
        except (TypeError, ValueError, UnicodeDecodeError):
            return None
    try:
        return Path(file)
    except (TypeError, ValueError):
        return None


def _path_matches_eval(path: Path, glob: str, repo_root: Path) -> bool:
    raw = str(path).replace("\\", "/")
    name = path.name
    rel_s = raw
    try:
        rel_s = path.resolve().relative_to(repo_root).as_posix()
    except (ValueError, OSError):
        try:
            rel_s = path.relative_to(repo_root).as_posix()
        except (ValueError, OSError):
            pass
    return (
        _asset_matches(rel_s, glob)
        or _asset_matches(raw, glob)
        or _asset_matches(name, glob)
    )


def _is_data_open(kind: str, path: Path, repo_root: Path, mode: str | None) -> bool:
    if kind in ("loadmat", "numpy.load", "numpy.loadtxt", "numpy.genfromtxt", "h5py.File"):
        return True
    if kind in ("open", "Path.open"):
        if path.suffix.lower() in _DATA_SUFFIXES:
            return True
        try:
            rel = path.resolve().relative_to(repo_root)
            return rel.parts[:1] == ("data",)
        except (ValueError, OSError):
            return False
    return False


def _stack_decision(repo_root: Path, readers: tuple[str, ...]) -> str:
    repo_root = repo_root.resolve()
    readers_n = {r.strip("/").replace("\\", "/") for r in readers}
    this_file = Path(__file__).resolve()
    has_reader = False
    has_train = False
    for fr in inspect.stack()[1:]:
        fn = Path(fr.filename).resolve()
        if fn == this_file:
            continue
        try:
            rel = fn.relative_to(repo_root).as_posix()
        except ValueError:
            continue
        if rel in readers_n:
            has_reader = True
        elif rel == "train.py" or rel.startswith("workspace/"):
            has_train = True
    if has_reader:
        return "allow"
    if has_train:
        return "block"
    return "neutral"


def _maybe_block_path(file: Any, *, kind: str, mode: str | None = None) -> None:
    if getattr(_tls, "in_guard", False) or not _guards:
        return
    _tls.in_guard = True
    try:
        path = _coerce_path(file)
        if path is None:
            return
        for root, perm in _guards:
            if _stack_decision(root, perm.eval_only_readers) != "block":
                continue
            globs = [a for a in perm.eval_only_assets if not is_callable_asset(a)]
            if any(_path_matches_eval(path, g, root) for g in globs):
                raise RuntimeError(_RUNTIME_FAIL)
            if perm.strict_no_train_files and _is_data_open(kind, path, root, mode):
                raise RuntimeError(_RUNTIME_FAIL)
    finally:
        _tls.in_guard = False


def _maybe_block_callable(root: Path, dotted: str) -> None:
    if getattr(_tls, "in_guard", False) or not _guards:
        return
    _tls.in_guard = True
    try:
        for g_root, perm in _guards:
            if g_root != root:
                continue
            if dotted not in perm.eval_only_assets:
                continue
            if _stack_decision(root, perm.eval_only_readers) == "block":
                raise RuntimeError(_RUNTIME_FAIL)
    finally:
        _tls.in_guard = False


def _patched_open(file, *args, **kwargs):
    mode = args[0] if args else kwargs.get("mode", "r")
    _maybe_block_path(file, kind="open", mode=mode if isinstance(mode, str) else None)
    return _orig["open"](file, *args, **kwargs)


def _patched_path_open(self, *args, **kwargs):
    mode = args[0] if args else kwargs.get("mode", "r")
    _maybe_block_path(self, kind="Path.open", mode=mode if isinstance(mode, str) else None)
    return _orig["Path.open"](self, *args, **kwargs)


def _ensure_io_patches() -> None:
    global _io_patched
    if _io_patched:
        return
    _orig["open"] = builtins.open
    builtins.open = _patched_open  # type: ignore[assignment]
    _orig["Path.open"] = Path.open
    Path.open = _patched_path_open  # type: ignore[method-assign,assignment]
    try:
        import numpy as np  # noqa: WPS433

        _orig["numpy.load"] = np.load
        _orig["numpy.loadtxt"] = np.loadtxt
        _orig["numpy.genfromtxt"] = np.genfromtxt

        def _pload(file, *a, **k):
            _maybe_block_path(file, kind="numpy.load")
            return _orig["numpy.load"](file, *a, **k)

        def _ploadtxt(file, *a, **k):
            _maybe_block_path(file, kind="numpy.loadtxt")
            return _orig["numpy.loadtxt"](file, *a, **k)

        def _pgen(file, *a, **k):
            _maybe_block_path(file, kind="numpy.genfromtxt")
            return _orig["numpy.genfromtxt"](file, *a, **k)

        np.load = _pload  # type: ignore[assignment]
        np.loadtxt = _ploadtxt  # type: ignore[assignment]
        np.genfromtxt = _pgen  # type: ignore[assignment]
    except ImportError:
        pass
    try:
        import scipy.io as sio  # noqa: WPS433

        _orig["scipy.io.loadmat"] = sio.loadmat

        def _ploadmat(file, *a, **k):
            _maybe_block_path(file, kind="loadmat")
            return _orig["scipy.io.loadmat"](file, *a, **k)

        sio.loadmat = _ploadmat  # type: ignore[assignment]
    except ImportError:
        pass
    try:
        import h5py  # noqa: WPS433

        _orig["h5py.File"] = h5py.File

        def _ph5(name, *a, **k):
            _maybe_block_path(name, kind="h5py.File")
            return _orig["h5py.File"](name, *a, **k)

        h5py.File = _ph5  # type: ignore[assignment]
    except ImportError:
        pass
    _io_patched = True


def _restore_io_patches() -> None:
    global _io_patched
    if not _io_patched:
        return
    builtins.open = _orig["open"]
    Path.open = _orig["Path.open"]
    try:
        import numpy as np  # noqa: WPS433

        if "numpy.load" in _orig:
            np.load = _orig["numpy.load"]
            np.loadtxt = _orig["numpy.loadtxt"]
            np.genfromtxt = _orig["numpy.genfromtxt"]
    except ImportError:
        pass
    try:
        import scipy.io as sio  # noqa: WPS433

        if "scipy.io.loadmat" in _orig:
            sio.loadmat = _orig["scipy.io.loadmat"]
    except ImportError:
        pass
    try:
        import h5py  # noqa: WPS433

        if "h5py.File" in _orig:
            h5py.File = _orig["h5py.File"]
    except ImportError:
        pass
    _orig.clear()
    _io_patched = False


def _wrap_callables_for(root: Path, perm: InfoPerm) -> None:
    root_s = str(root)
    if root_s not in sys.path:
        sys.path.insert(0, root_s)
    for asset in perm.eval_only_assets:
        if not is_callable_asset(asset):
            continue
        parts = asset.split(".")
        if len(parts) < 2:
            continue
        mod_name, func_name = ".".join(parts[:-1]), parts[-1]
        try:
            mod = importlib.import_module(mod_name)
        except ImportError:
            continue
        fn = getattr(mod, func_name, None)
        if not callable(fn) or getattr(fn, "_info_perm_wrapped", False):
            continue

        def _wrapper(*args, _fn=fn, _root=root, _dotted=asset, **kwargs):
            _maybe_block_callable(_root, _dotted)
            return _fn(*args, **kwargs)

        _wrapper._info_perm_wrapped = True  # type: ignore[attr-defined]
        setattr(mod, func_name, _wrapper)
        _callable_orig.append((mod, func_name, fn))


def _unwrap_callables() -> None:
    while _callable_orig:
        mod, name, fn = _callable_orig.pop()
        setattr(mod, name, fn)


def install_eval_only_runtime_guard(repo_root: str | os.PathLike) -> None:
    """预检通过后安装：工作区真打开只评材料才抛错。``enforce=False`` / 未登记 / 空名单且非严格档 → 空转。"""
    root = Path(repo_root).resolve()
    perm = load_info_perm(root)
    if perm is None or not perm.enforce:
        return
    if not perm.eval_only_assets and not perm.strict_no_train_files:
        return
    if any(g[0] == root for g in _guards):
        return
    _guards.append((root, perm))
    _ensure_io_patches()
    _wrap_callables_for(root, perm)


def uninstall_eval_only_runtime_guard(repo_root: str | os.PathLike | None = None) -> None:
    """单测用。``repo_root=None`` 卸掉全部挂钩。"""
    global _guards
    if repo_root is None:
        _guards = []
        _unwrap_callables()
        _restore_io_patches()
        return
    root = Path(repo_root).resolve()
    _guards = [g for g in _guards if g[0] != root]
    if not _guards:
        _unwrap_callables()
        _restore_io_patches()


# ── 动态：首 batch 键 / 旁路留痕 ──────────────────────────────────

def check_train_batch_keys(batch: Any, keys: tuple[str, ...] | list[str] | None) -> list[str]:
    """训练首 batch 对白名单：dict 多键 / tuple 多项即越权；``keys=None`` 不校；未知结构跳过。"""
    if keys is None or batch is None:
        return []
    allowed = tuple(str(k) for k in keys)
    if isinstance(batch, Mapping):
        extra = sorted(str(k) for k in batch.keys() if str(k) not in allowed)
        return [f"训练 batch 多出键 {extra}（白名单 {list(allowed)}）"] if extra else []
    if isinstance(batch, (tuple, list)):
        if len(batch) > len(allowed):
            return [f"训练 batch 有 {len(batch)} 项，白名单只允许 {len(allowed)} 项 {list(allowed)}"]
        return []
    return []


def collect_guard_bypasses(environ: Mapping[str, str] | None = None) -> list[str]:
    """``NN_PREFLIGHT`` / ``NN_GUARD`` / ``NN_GUARD_*`` 取 0/false/no/off 的项 → ``["K=v", …]``（排序）。"""
    env = os.environ if environ is None else environ
    out: list[str] = []
    for k in sorted(env):
        if k == "NN_PREFLIGHT" or k == "NN_GUARD" or k.startswith("NN_GUARD_"):
            if str(env[k]).strip().lower() in _FALSY:
                out.append(f"{k}={env[k]}")
    return out


def format_violations(vs: list[Violation], *, header: str = "[Pre-flight G-信息权限]") -> str:
    lines = [f"{header} {len(vs)} 处违规（合同 contract/runtime.py INFO_PERM 登记的信息权限）："]
    for v in vs:
        lines.append(f"  - {v.rule} {v.path}:{v.line} {v.detail}")
        lines.append(f"      修复：{v.fix}")
    lines.append(
        "  说明：本守门无 NN_GUARD_* 开关；enforce 只由 INFO_PERM 决定（改它 = 改合同，须 NN_RELAUNCH=1）"
    )
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else ".").resolve()
    try:
        vs = check_info_perm(root)
    except InfoPermError as exc:
        print(f"[G-信息权限] IP0 {exc}")
        return 1
    if vs:
        print(format_violations(vs, header="[G-信息权限]"))
        return 1
    perm = load_info_perm(root)
    if perm is None:
        print("[G-信息权限] 未登记（contract/runtime.py 无 INFO_PERM）：空转")
    elif not perm.enforce:
        print("[G-信息权限] enforce=False：空转（对照关臂）")
    else:
        inv = inventory_eval_only_literals(root)
        print("[G-信息权限] OK：合同静态通过；只评材料真打开才拦")
        if inv:
            print(f"[G-信息权限] 清单 {len(inv)} 条预留（未调用不算犯规）")
            for v in inv[:12]:
                print(f"  - {v.rule} {v.path}:{v.line} {v.detail}")
            if len(inv) > 12:
                print(f"  - … 另 {len(inv) - 12} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
