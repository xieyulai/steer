#!/usr/bin/env python3
"""scan_no_fallback.py — 扫描吞错的 except 块（no-fallback 门禁）

用法：
  python scripts/scan_no_fallback.py [ROOT]

原则（no-fallback）：勿隐藏错误，错误须上抛（raise）或显式记录（print/log）。
``try/except`` 仅用于类型解析或可选特性守卫，且必须 ``raise`` 或 ``log`` ——
**禁止** 静默 ``pass`` / ``return None`` / ``return {}`` / ``return False`` /
``continue`` 来吞下失败。

扫描范围：experiment.py + workspace/**/*.py + contract/**/*.py（确定性排序）。

判定（AST）：
  对每个 ``except`` 处理器，检查其 body 第一条"实质语句"（跳过 docstring）：
    - 命中 raise / print / log / warn / sys.exit → 视为显式处理，**不 WARN**。
    - 命中 pass / return / continue / break → **WARN**（吞错）。
    - 其它（赋值、再调用等）→ 不 WARN（保守，可能合理也可能不合理，留给人审）。
  ``except ...: pass`` / ``return None`` / ``return {}`` / ``return False`` /
  ``continue`` 一律 WARN（无论 except 类型是否具体）。

输出：``[WARN] file:line: <snippet>`` + 一行修复提示（"勿隐藏错误，上抛或显式处理"）。
**始终 exit 0**（WARN 不阻断 —— 合法 optional 场景也会被命中，避免误伤）。
末尾打印汇总计数。
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

FIX_HINT = "勿隐藏错误，上抛（raise）或显式处理（print/log）；可选特性须加注释 # optional: …"


def _scan_files(root: Path) -> list[Path]:
    """experiment.py + workspace/**/*.py + contract/**/*.py，确定性排序。"""
    files: list[Path] = []
    exp = root / "experiment.py"
    if exp.is_file():
        files.append(exp)
    files.extend(sorted((root / "workspace").rglob("*.py")))
    files.extend(sorted((root / "contract").rglob("*.py")))
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in files:
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        unique.append(p)
    return unique


def _type_name(node: ast.expr | None) -> str:
    """渲染 except 类型（如 ``except (OSError, json.JSONDecodeError)``）。"""
    if node is None:
        return "bare except"
    if isinstance(node, ast.Name):
        return f"except {node.id}"
    if isinstance(node, ast.Attribute):
        base = _type_name_base(node.value)
        return f"except {base}.{node.attr}" if base else f"except {node.attr}"
    if isinstance(node, ast.Tuple):
        parts = [_type_name(e).removeprefix("except ") for e in node.elts]
        return f"except ({', '.join(parts)})"
    return "except <expr>"


def _type_name_base(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        b = _type_name_base(node.value)
        return f"{b}.{node.attr}" if b else node.attr
    return ast.unparse(node) if hasattr(ast, "unparse") else "<expr>"


def _is_explicit_handler(body: list[ast.stmt]) -> bool:
    """except 块是否显式处理（raise / print / log / warn / sys.exit）。

    只看第一条实质语句（跳过 docstring）。显式 → 不 WARN。
    """
    if not body:
        return False
    stmt = body[0]
    # 跳过模块/函数 docstring（Expr + Constant str）
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
        if len(body) > 1:
            stmt = body[1]
        else:
            return False
    # raise ...（含 bare raise / raise ... from ...）
    if isinstance(stmt, ast.Raise):
        return True
    # sys.exit(...) / exit(...)
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        call = stmt.value
        fname = _call_name(call.func)
        if fname in ("exit", "sys.exit", "os._exit") or fname.endswith(".exit"):
            return True
        if fname in ("print",) or fname.endswith(".print"):
            return True
        # logger.info/.warning/.error/.warn/.exception/.critical/.log 等
        if _looks_like_log(fname):
            return True
        # warnings.warn(...)
        if fname in ("warn", "warnings.warn") or fname.endswith(".warn"):
            return True
        # logging.xxx(...) 直接调用
        if fname.startswith("logging."):
            return True
    return False


def _call_name(node: ast.expr) -> str:
    """提取调用名（如 ``logger.error`` → ``logger.error``；``print`` → ``print``）。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _looks_like_log(fname: str) -> bool:
    """常见 logger 方法名（logger.error / log.warning / self._log.info 等）。"""
    log_methods = (
        ".debug", ".info", ".warning", ".warn", ".error",
        ".exception", ".critical", ".log",
    )
    for m in log_methods:
        if fname.endswith(m):
            return True
    return False


def _classify_body(body: list[ast.stmt]) -> str | None:
    """返回吞错语句类型，否则 None（不 WARN）。

    返回 'pass' / 'return' / 'continue' / 'break' 之一。
    """
    if not body:
        return None
    stmt = body[0]
    # 跳过 docstring
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str):
        if len(body) > 1:
            stmt = body[1]
        else:
            return None
    if isinstance(stmt, ast.Raise):
        return None  # 显式上抛
    if isinstance(stmt, ast.Pass):
        return "pass"
    if isinstance(stmt, ast.Return):
        return "return"
    if isinstance(stmt, ast.Continue):
        return "continue"
    if isinstance(stmt, ast.Break):
        return "break"
    # 显式 print/log/warn 调用 → 不 WARN
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        if _is_explicit_handler(body):
            return None
    return None  # 其它（赋值、再调用）保守不 WARN


def _snippet(text: str, lineno: int) -> str:
    lines = text.splitlines()
    if 1 <= lineno <= len(lines):
        return lines[lineno - 1].strip()
    return ""


_OPTIONAL_MARKERS = ("# optional:", "# optional ", "# noqa: no-fallback", "# optional-feature")


def _has_optional_marker(text: str, node: ast.ExceptHandler, body: list[ast.stmt]) -> bool:
    """except 行或吞错语句行带 ``# optional:`` / ``# noqa: no-fallback`` → 抑制。

    鼓励显式声明意图（optional 特性 / 可选缓存），保留运行时无噪。
    """
    lines = text.splitlines()
    check_lines: list[int] = []
    if node.lineno and 1 <= node.lineno <= len(lines):
        check_lines.append(node.lineno)
    if body and body[0].lineno and 1 <= body[0].lineno <= len(lines):
        check_lines.append(body[0].lineno)
    for ln in check_lines:
        comment = lines[ln - 1]
        low = comment.lower()
        if any(m in low for m in _OPTIONAL_MARKERS):
            return True
    return False


def scan(root: Path) -> int:
    warns = 0
    for p in _scan_files(root):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text, filename=str(p))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            body = node.body or []
            kind = _classify_body(body)
            if kind is None:
                continue
            # 注释抑制：except 行或吞错语句行带 ``# optional:`` / ``# noqa: no-fallback``
            # 视为已显式声明意图（optional 特性 / 可选缓存），不 WARN。
            if _has_optional_marker(text, node, body):
                continue
            snippet = _snippet(text, node.lineno)
            # 标注 except 类型描述
            etype = _type_name(node.type)
            print(
                f"[WARN] {p}:{node.lineno}: 吞错 except（{etype}）→ {kind}：{snippet}"
            )
            print(f"        → {FIX_HINT}")
            warns += 1
    if warns:
        print(f"\n[scan_no_fallback] WARN: {warns} 个吞错 except（请上抛或显式处理；可选特性加 # optional）")
    else:
        print(f"\n[scan_no_fallback] OK: 0 吞错 except")
    return 0  # 始终 0（WARN 不阻断）


def main() -> None:
    p = argparse.ArgumentParser(description="扫描吞错 except（no-fallback 原则）")
    p.add_argument("root", nargs="?", default=".", help="项目根目录")
    args = p.parse_args()
    sys.exit(scan(Path(args.root).resolve()))


if __name__ == "__main__":
    main()
