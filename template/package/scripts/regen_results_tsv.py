#!/usr/bin/env python3
"""按当前 contract 重生成 _runs/results.tsv 表头，并从 exp_dir/results.json 回填指标列。"""
from __future__ import annotations

import argparse
import ast
import json
import math
import shutil
import sys
from pathlib import Path
from typing import Any


def _format_metric_cell(v: Any) -> str:
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return ""
        return f"{v:.6f}"
    if v is None:
        return ""
    return str(v)


def _dict_from_return_dict(node: ast.AST) -> dict[str, str]:
    if not isinstance(node, ast.Dict):
        return {}
    out: dict[str, str] = {}
    for k, v in zip(node.keys, node.values):
        if isinstance(k, ast.Constant) and isinstance(v, ast.Constant):
            if isinstance(k.value, str) and isinstance(v.value, str):
                out[k.value] = v.value
    return out


def _dict_from_module_assign(tree: ast.AST, name: str) -> dict[str, str]:
    """``NAME = {...}`` 或 ``NAME: dict[...] = {...}`` 模块级赋值。"""
    for node in tree.body:
        target = None
        value = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        if not isinstance(target, ast.Name) or target.id != name:
            continue
        return _dict_from_return_dict(value)
    return {}


def _parse_metric_dicts_from_metrics_py(
    repo_root: Path,
) -> tuple[dict[str, str], dict[str, str], tuple[str, ...]] | None:
    """扫 ``contract/metrics.py`` 的 METRIC_KEYS / AUXILIARY_KEYS（不 import，避 pyarrow）。"""
    path = repo_root / "contract" / "metrics.py"
    if not path.is_file():
        return None
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return None
    metric_keys = _dict_from_module_assign(tree, "METRIC_KEYS")
    if not metric_keys:
        return None
    auxiliary_keys = _dict_from_module_assign(tree, "AUXILIARY_KEYS")
    return metric_keys, auxiliary_keys, ()


def _parse_metric_dicts_from_source(
    repo_root: Path,
) -> tuple[dict[str, str], dict[str, str], tuple[str, ...]] | None:
    """不 import contract（避免 new-project 时尚未 poetry install / 缺业务依赖）。"""
    path = repo_root / "contract" / "__init__.py"
    if not path.is_file():
        return _parse_metric_dicts_from_metrics_py(repo_root)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return _parse_metric_dicts_from_metrics_py(repo_root)
    metric_keys: dict[str, str] = {}
    auxiliary_keys: dict[str, str] = {}
    ledger_context_keys: tuple[str, ...] = ()
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if item.name == "metric_keys":
                for sub in ast.walk(item):
                    if isinstance(sub, ast.Return) and sub.value is not None:
                        if isinstance(sub.value, ast.Dict):
                            metric_keys = _dict_from_return_dict(sub.value)
                        elif isinstance(sub.value, ast.Name) and sub.value.id == "METRIC_KEYS":
                            # return METRIC_KEYS → 改从 metrics.py 取
                            pass
            if item.name == "auxiliary_keys":
                for sub in ast.walk(item):
                    if isinstance(sub, ast.Return) and sub.value is not None:
                        if isinstance(sub.value, ast.Dict):
                            auxiliary_keys = _dict_from_return_dict(sub.value)
            if item.name == "ledger_context_keys":
                for sub in ast.walk(item):
                    if isinstance(sub, ast.Return) and sub.value is not None and isinstance(sub.value, (ast.Tuple, ast.List)):
                        vals: list[str] = []
                        for elt in sub.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                vals.append(elt.value)
                        ledger_context_keys = tuple(vals)
    if not metric_keys:
        fallback = _parse_metric_dicts_from_metrics_py(repo_root)
        if fallback is None:
            return None
        mk, ak, _ = fallback
        return mk, ak or auxiliary_keys, ledger_context_keys
    return metric_keys, auxiliary_keys, ledger_context_keys


def _default_tsv_columns_from_dicts(
    metric_keys: dict[str, str],
    auxiliary_keys: dict[str, str],
    ledger_context_keys: tuple[str, ...] = (),
) -> list[str]:
    metric_key = next(iter(metric_keys))
    all_keys = sorted((set(metric_keys.keys()) | set(auxiliary_keys.keys())) - {metric_key})
    ledger = list(ledger_context_keys)
    if "baseline_tag" not in ledger:
        ledger.append("baseline_tag")
    if "exploration_space" not in ledger:
        ledger.append("exploration_space")
    return [
        "experiment",
        "scenario_id",
        metric_key,
        *all_keys,
        *ledger,
        "elapsed_sec",
        "git_commit",
        "exp_dir",
        "description",
        "notes",
        "timestamp",
    ]


def _load_contract(repo_root: Path) -> Any:
    sys.path.insert(0, str(repo_root.resolve()))
    try:
        from contract import create_contract  # noqa: WPS433

        return create_contract({})
    except Exception as exc:
        parsed = _parse_metric_dicts_from_source(repo_root)
        if parsed is None:
            raise exc from None
        metric_keys, auxiliary_keys, ledger_context_keys = parsed

        class _ContractStub:
            def __init__(self) -> None:
                self.metric_keys = metric_keys
                self.auxiliary_keys = auxiliary_keys
                self.ledger_context_keys = ledger_context_keys
                self.metric_key = next(iter(metric_keys))

            def _default_tsv_columns(self) -> list[str]:
                return _default_tsv_columns_from_dicts(
                    self.metric_keys, self.auxiliary_keys, self.ledger_context_keys,
                )

        return _ContractStub()


def _config_from_exp_dir(exp_dir: str) -> dict[str, Any]:
    if not exp_dir.strip():
        return {}
    p = Path(exp_dir) / "config.json"
    if not p.is_file():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _metrics_from_exp_dir(exp_dir: str) -> dict[str, Any]:
    if not exp_dir.strip():
        return {}
    p = Path(exp_dir) / "results.json"
    if not p.is_file():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    metrics = data.get("metrics", data)
    return metrics if isinstance(metrics, dict) else {}


def _read_tsv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    if not path.is_file() or path.stat().st_size == 0:
        return [], []
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return [], []
    header = lines[0].split("\t")
    rows: list[dict[str, str]] = []
    for line in lines[1:]:
        if not line.strip():
            continue
        cells = line.split("\t")
        row = {header[i]: cells[i] if i < len(cells) else "" for i in range(len(header))}
        rows.append(row)
    return header, rows


def _metric_keys_for_contract(contract: Any) -> tuple[str, ...]:
    keys = set(contract.metric_keys.keys()) | set(contract.auxiliary_keys.keys())
    return tuple(sorted(keys))


def _build_notes_overflow(metrics: dict[str, Any], contract: Any) -> str:
    known = (
        set(contract.metric_keys.keys())
        | set(contract.auxiliary_keys.keys())
        | set(getattr(contract, "ledger_context_keys", ()))
    )
    parts: list[str] = []
    for k in sorted(metrics.keys()):
        if k in known:
            continue
        v = metrics[k]
        if not isinstance(v, (int, float)):
            continue
        cell = _format_metric_cell(v)
        if cell:
            parts.append(f"{k}={cell}")
    return "; ".join(parts)


def _exp_dir_matches_experiment(exp_dir: str, experiment: str) -> bool:
    """目录名等于 experiment，或为模板槽位 ``…_s*of*_<experiment>``。"""
    name = Path(exp_dir).name
    if name == experiment:
        return True
    suffix = f"_{experiment}"
    return name.endswith(suffix)


def _should_backfill_metrics(old: dict[str, str]) -> bool:
    """对正式实验行从 ``exp_dir/results.json`` 回填；preflight 等跳过。"""
    exp = (old.get("experiment") or "").strip()
    if exp == "preflight_check":
        return False
    exp_dir = (old.get("exp_dir") or "").strip()
    if exp_dir and (Path(exp_dir) / "results.json").is_file():
        return True
    desc = old.get("description", "")
    if "finalize_round" in desc:
        return True
    if exp_dir and exp and _exp_dir_matches_experiment(exp_dir, exp):
        return True
    return False


def _build_row(
    header: list[str],
    old: dict[str, str],
    contract: Any,
) -> dict[str, str]:
    meta_cols = ("experiment", "elapsed_sec", "git_commit", "exp_dir", "description", "notes", "timestamp")
    cfg = _config_from_exp_dir(old.get("exp_dir", "")) if _should_backfill_metrics(old) else {}
    metrics = _metrics_from_exp_dir(old.get("exp_dir", "")) if _should_backfill_metrics(old) else {}
    # 旧表头 val_accuracy 等占位列：若 results.json 无数据则留空
    for legacy in ("val_accuracy", "val_loss", "val_top2_accuracy"):
        if legacy in old and old[legacy].strip() and legacy not in metrics:
            try:
                metrics[legacy] = float(old[legacy])
            except ValueError:
                pass

    row: dict[str, str] = {}
    for col in header:
        if col == "notes":
            if old.get("notes", "").strip():
                row[col] = old.get(col, "")
            elif metrics:
                row[col] = _build_notes_overflow(metrics, contract)
            else:
                row[col] = ""
        elif col in meta_cols:
            row[col] = old.get(col, "")
        elif col in contract.metric_keys or col in contract.auxiliary_keys:
            cell = _format_metric_cell(metrics.get(col))
            if not cell and (old.get(col) or "").strip():
                row[col] = old.get(col, "")
            else:
                row[col] = cell
        elif col in getattr(contract, "ledger_context_keys", ()):
            try:
                from experiment import resolve_cfg_for_ledger_key  # noqa: WPS433
            except ImportError:
                resolve_cfg_for_ledger_key = None  # type: ignore[misc, assignment]
            if resolve_cfg_for_ledger_key is not None:
                val = resolve_cfg_for_ledger_key(cfg, col)
            else:
                val = cfg.get(col)
            if val is not None:
                row[col] = _format_metric_cell(val)
            else:
                row[col] = old.get(col, "")
        else:
            row[col] = old.get(col, "")
    return row


def _row_experiment(row: dict[str, str]) -> str:
    return (row.get("experiment") or "").strip()


def regen_tsv(
    repo_root: Path,
    tsv_rel: str = "_runs/results.tsv",
    *,
    backup: bool = True,
    drop_experiments: frozenset[str] = frozenset(),
) -> Path:
    repo_root = repo_root.resolve()
    tsv_path = repo_root / tsv_rel
    contract = _load_contract(repo_root)
    header = contract._default_tsv_columns()
    metric_keys = _metric_keys_for_contract(contract)

    old_header, old_rows = _read_tsv_rows(tsv_path)

    if backup and tsv_path.is_file() and tsv_path.stat().st_size > 0:
        bak = tsv_path.with_suffix(tsv_path.suffix + ".bak")
        shutil.copy2(tsv_path, bak)
        print(f"已备份: {bak}", file=sys.stderr)

    out_lines = ["\t".join(header)]
    filled = 0
    skipped = 0
    for old in old_rows:
        if drop_experiments and _row_experiment(old) in drop_experiments:
            skipped += 1
            continue
        new_row = _build_row(header, old, contract)
        if any(new_row.get(k) for k in metric_keys):
            filled += 1
        out_lines.append("\t".join(new_row.get(col, "") for col in header))

    tsv_path.parent.mkdir(parents=True, exist_ok=True)
    tsv_path.write_text("\n".join(out_lines) + ("\n" if out_lines else ""), encoding="utf-8")
    msg = f"已写入 {tsv_path}：{len(old_rows) - skipped} 行"
    if skipped:
        msg += f"（跳过 {skipped} 行: {', '.join(sorted(drop_experiments))}）"
    msg += f"，{filled} 行含指标（表头 {len(header)} 列）"
    print(msg, file=sys.stderr)
    return tsv_path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", type=Path, default=Path("."), help="项目根目录")
    ap.add_argument("--tsv", default="_runs/results.tsv", help="相对 repo-root 的 TSV 路径")
    ap.add_argument("--header-only", action="store_true", help="仅打印表头（供 new-project.sh 使用）")
    ap.add_argument("--no-backup", action="store_true", help="不备份原 TSV")
    ap.add_argument(
        "--drop-experiment",
        action="append",
        default=[],
        metavar="NAME",
        help="重生时丢弃 experiment 列等于 NAME 的行（可重复，如 preflight_check）",
    )
    ap.add_argument(
        "--sync-jsonl",
        action="store_true",
        help="成功重生并校验通过后，同步 _runs/results.jsonl（与 sync_ledger.py --apply 一致）",
    )
    args = ap.parse_args()

    repo_root = args.repo_root.resolve()
    if args.header_only:
        contract = _load_contract(repo_root)
        print("\t".join(contract._default_tsv_columns()))
        return 0

    drop_set = frozenset(x.strip() for x in args.drop_experiment if x.strip())
    regen_tsv(repo_root, args.tsv, backup=not args.no_backup, drop_experiments=drop_set)

    contract = _load_contract(repo_root)
    tsv_path = repo_root / args.tsv
    header = tsv_path.read_text(encoding="utf-8").splitlines()[0].split("\t")
    required = set(contract.metric_keys) | set(contract.auxiliary_keys)
    missing = required - set(header)
    if missing:
        print(f"错误: 表头缺列 {missing}", file=sys.stderr)
        return 1
    if contract.metric_key not in header:
        print(f"错误: 表头缺少主指标列 {contract.metric_key!r}", file=sys.stderr)
        return 1
    print("校验通过: 表头与 contract 一致", file=sys.stderr)
    print(
        "注意: 本次 regen 仅重写 TSV；若需对齐 results.jsonl 请使用参数 --sync-jsonl。",
        file=sys.stderr,
    )
    if args.sync_jsonl:
        from sync_ledger import sync_ledger  # noqa: WPS433

        sync_ledger(repo_root, tsv_rel=args.tsv, dry_run=False, backup_jsonl=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
