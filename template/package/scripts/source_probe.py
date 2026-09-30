# source_probe.py
"""migrate 源现状静态提取(D4.1):对源对齐题做「能机读的」静态提取。

宁缺毋假:提不出的键输出 null,notes 里标「需人工核对」。
用法:python3 source_probe.py --source-root <src>   # 输出 JSON
"""
from __future__ import annotations

import argparse
import ast
import json
import pathlib
import re
import sys

# 数据划分相关常量名须含这些关键词(SEED / TRAIN_RATIO / ...)
_CONST_KEYWORDS = ("SEED", "SPLIT", "RATIO", "FRACTION", "SHARE",
                   "TRAIN", "VAL", "TEST", "PERCENT")
_CONST_NAME = re.compile(r"^[A-Z][A-Z0-9_]+$")

# v1 边界:这 5 题静态提不出,一律 null + 需人工核对
MANUAL_SLUGS = ("I1-train-consumes", "I2-official-path", "T2-callchain",
                "E3-official-test", "E4-train-eval")


def _const_literals(path: pathlib.Path) -> dict[str, object]:
    """顶层 `NAME = 字面量` 常量(ast.literal_eval 可解析的才收)。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return {}
    out: dict[str, object] = {}
    for node in tree.body:  # 只看顶层
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
        for t in targets:
            if (isinstance(t, ast.Name) and _CONST_NAME.match(t.id)
                    and any(k in t.id for k in _CONST_KEYWORDS)):
                try:
                    out[t.id] = ast.literal_eval(node.value)  # type: ignore[arg-type]
                except (ValueError, SyntaxError):
                    pass  # 非字面量(表达式) → 不猜
    return out


def _list_const(path: pathlib.Path, names: tuple[str, ...]) -> list | None:
    text = path.read_text(encoding="utf-8")
    for name in names:
        m = re.search(rf"^{name}\s*[:=]\s*(\[.*?\])\s*$", text, re.MULTILINE | re.DOTALL)
        if m:
            try:
                v = ast.literal_eval(m.group(1))
                if isinstance(v, list):
                    return v
            except (ValueError, SyntaxError):
                continue
    return None


def probe(source_root: pathlib.Path) -> dict:
    src = pathlib.Path(source_root)
    data: dict = {"source_root": str(src)}
    notes: list[str] = []
    # D2:数据划分 ← contract/prepare_data.py 顶层常量
    pd_path = src / "contract" / "prepare_data.py"
    if pd_path.is_file():
        consts = _const_literals(pd_path)
        data["D2-data-split"] = {"constants": consts} if consts else None
        if not consts:
            notes.append("D2-data-split:prepare_data.py 无可机读常量,需人工核对")
    else:
        data["D2-data-split"] = None
        notes.append("D2-data-split:无 contract/prepare_data.py,需人工核对")
    # E1:主辅指标键 ← contract/metrics.py 的 METRIC_KEYS / AUXILIARY_KEYS
    m_path = src / "contract" / "metrics.py"
    if m_path.is_file():
        keys = _list_const(m_path, ("METRIC_KEYS", "PRIMARY_KEYS", "MAIN_KEYS"))
        aux = _list_const(m_path, ("AUXILIARY_KEYS", "AUX_KEYS"))
        data["E1-metrics"] = ({"metric_keys": keys, "auxiliary_keys": aux}
                              if keys is not None or aux is not None else None)
        if data["E1-metrics"] is None:
            notes.append("E1-metrics:metrics.py 无 METRIC_KEYS/AUXILIARY_KEYS,需人工核对")
    else:
        data["E1-metrics"] = None
        notes.append("E1-metrics:无 contract/metrics.py,需人工核对")
    for slug in MANUAL_SLUGS:
        data[slug] = None
        notes.append(f"{slug}:静态提不出,需人工核对")
    data["notes"] = notes
    return data


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="migrate 源现状静态提取(探针)")
    ap.add_argument("--source-root", type=pathlib.Path, required=True)
    args = ap.parse_args(argv)
    print(json.dumps(probe(args.source_root), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
