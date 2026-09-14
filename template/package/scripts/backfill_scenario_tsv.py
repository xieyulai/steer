#!/usr/bin/env python3
"""为 _runs/results.tsv 回填 scenario_id 列（dry-run / apply）。"""
from __future__ import annotations

import argparse
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PKG_ROOT = _SCRIPT_DIR.parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from experiment import migrate_legacy_keeper_if_needed  # noqa: E402
from lib.scenario_inventory import (  # noqa: E402
    SCENARIO_ID_COLUMN,
    focus_scenario_id,
    load_scenario_ids,
)

TSV_REL = "_runs/results.tsv"
MODEL_ARCH_COLUMNS = ("model_arch", "MODEL_ARCH")
VIDEO_SUBSTRINGS = ("reference_3dconv", "reference_plain", "flow_")


@dataclass
class BackfillRules:
    inventory: list[str]
    exact_map: dict[str, str] = field(default_factory=dict)
    prefix_map: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class BackfillReport:
    header: list[str]
    rows: list[dict[str, str]]
    resolved: list[tuple[str, str, str]] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    skipped_existing: list[str] = field(default_factory=list)
    inserted_column: bool = False
    applied: bool = False

    @property
    def unresolved_count(self) -> int:
        return len(self.unresolved)


def _read_tsv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
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


def _write_tsv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    lines = ["\t".join(header)]
    for row in rows:
        lines.append("\t".join(row.get(col, "") for col in header))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _ensure_scenario_column(header: list[str]) -> tuple[list[str], bool]:
    if SCENARIO_ID_COLUMN in header:
        return header, False
    if "experiment" not in header:
        return [*header, SCENARIO_ID_COLUMN], True
    idx = header.index("experiment") + 1
    return header[:idx] + [SCENARIO_ID_COLUMN] + header[idx:], True


def _load_map_file(path: Path) -> tuple[dict[str, str], list[tuple[str, str]]]:
    exact: dict[str, str] = {}
    prefixes: list[tuple[str, str]] = []
    if not path.is_file():
        raise FileNotFoundError(f"映射文件不存在: {path}")
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return exact, prefixes
    header = [c.strip().lower() for c in lines[0].split("\t")]
    key_col = None
    for candidate in ("experiment", "experiment_prefix"):
        if candidate in header:
            key_col = candidate
            break
    if key_col is None:
        raise ValueError("映射表须含 experiment 或 experiment_prefix 列")
    sid_idx = header.index("scenario_id") if "scenario_id" in header else None
    if sid_idx is None:
        raise ValueError("映射表须含 scenario_id 列")
    key_idx = header.index(key_col)
    for line in lines[1:]:
        if not line.strip():
            continue
        cells = line.split("\t")
        if len(cells) <= max(key_idx, sid_idx):
            continue
        key = cells[key_idx].strip()
        sid = cells[sid_idx].strip()
        if not key or not sid:
            continue
        if key_col == "experiment":
            exact[key] = sid
        else:
            prefixes.append((key, sid))
    prefixes.sort(key=lambda x: len(x[0]), reverse=True)
    return exact, prefixes


def _model_arch_value(row: dict[str, str]) -> str:
    for col in MODEL_ARCH_COLUMNS:
        val = (row.get(col) or "").strip()
        if val:
            return val
    return ""


def _match_map(experiment: str, rules: BackfillRules) -> str | None:
    if experiment in rules.exact_map:
        return rules.exact_map[experiment]
    for prefix, sid in rules.prefix_map:
        if experiment.startswith(prefix) or prefix in experiment:
            return sid
    return None


def _match_video(experiment: str, inventory: list[str]) -> str | None:
    inv_set = set(inventory)
    for substr in VIDEO_SUBSTRINGS:
        if substr not in experiment:
            continue
        if substr in inv_set:
            return substr
        if substr == "flow_":
            flow_ids = [
                sid for sid in inventory
                if sid.startswith("flow_") and sid != "flow_*" and sid in experiment
            ]
            if flow_ids:
                return max(flow_ids, key=len)
            if experiment.startswith("flow_") and experiment in inv_set:
                return experiment
    return None


def infer_scenario_id(
    row: dict[str, str],
    header: list[str],
    repo_root: Path,
    rules: BackfillRules,
) -> str | None:
    """单场景→default；BM→model_arch；VIDEO→experiment 前缀；PINN→map 文件。"""
    experiment = (row.get("experiment") or "").strip()
    existing = (row.get(SCENARIO_ID_COLUMN) or "").strip()
    inventory = rules.inventory
    inv_set = set(inventory)

    if existing:
        if existing in inv_set:
            return existing
        return None

    mapped = _match_map(experiment, rules)
    if mapped and mapped in inv_set:
        return mapped

    if len(inventory) == 1:
        return inventory[0]

    arch = _model_arch_value(row)
    if arch and arch in inv_set:
        return arch

    video_sid = _match_video(experiment, inventory)
    if video_sid:
        return video_sid

    return None


def backfill_tsv(
    repo_root: Path,
    *,
    apply: bool,
    map_file: Path | None,
    tsv_rel: str = TSV_REL,
) -> BackfillReport:
    """回填 scenario_id；unresolved>0 且 apply → 不写盘（由 main exit 1）。"""
    root = repo_root.resolve()
    tsv_path = root / tsv_rel
    header, rows = _read_tsv(tsv_path)
    if not header:
        raise FileNotFoundError(f"TSV 不存在或为空: {tsv_path}")

    inventory = load_scenario_ids(root)
    exact_map: dict[str, str] = {}
    prefix_map: list[tuple[str, str]] = []
    if map_file is not None:
        exact_map, prefix_map = _load_map_file(map_file.resolve())
    rules = BackfillRules(inventory=inventory, exact_map=exact_map, prefix_map=prefix_map)

    header, inserted = _ensure_scenario_column(header)
    report = BackfillReport(header=header, rows=[], inserted_column=inserted)

    for row in rows:
        new_row = dict(row)
        if SCENARIO_ID_COLUMN not in new_row:
            new_row[SCENARIO_ID_COLUMN] = ""
        existing = (new_row.get(SCENARIO_ID_COLUMN) or "").strip()
        sid = infer_scenario_id(new_row, header, root, rules)
        exp = (new_row.get("experiment") or "").strip()

        if sid:
            new_row[SCENARIO_ID_COLUMN] = sid
            if existing and existing == sid:
                report.skipped_existing.append(exp)
            else:
                report.resolved.append((exp, existing or "(空)", sid))
        else:
            report.unresolved.append(exp)
        report.rows.append(new_row)

    if apply:
        if report.unresolved_count > 0:
            return report
        if tsv_path.is_file():
            bak = tsv_path.with_suffix(tsv_path.suffix + ".bak")
            shutil.copy2(tsv_path, bak)
            print(f"已备份: {bak}", file=sys.stderr)
        _write_tsv(tsv_path, header, report.rows)
        print(f"已写入: {tsv_path}（{len(report.rows)} 行）", file=sys.stderr)
        focus_sid = focus_scenario_id(root)
        if migrate_legacy_keeper_if_needed(root, focus_sid):
            print(f"keeper 已迁移至 keepers.json（scenario_id={focus_sid}）", file=sys.stderr)
        report.applied = True

    return report


def _print_report(report: BackfillReport, *, apply: bool) -> None:
    mode = "apply" if apply else "dry-run"
    print(f"=== backfill scenario_id ({mode}) ===")
    if report.inserted_column:
        print(f"表头: 在 experiment 后插入 {SCENARIO_ID_COLUMN!r} 列")
    print(f"总行数: {len(report.rows)}")
    print(f"已推断: {len(report.resolved)}")
    print(f"未解析: {report.unresolved_count}")
    if report.resolved:
        print("\n推断映射:")
        for exp, old, new in report.resolved:
            print(f"  {exp!r}: {old} → {new!r}")
    if report.unresolved:
        print("\n未解析 experiment:")
        for exp in report.unresolved:
            print(f"  {exp!r}")
    if report.skipped_existing:
        print(f"\n已有有效 scenario_id（跳过）: {len(report.skipped_existing)} 行")

    # 人话小结（P2）：方便人审 dry-run
    sids = sorted({new for _, _, new in report.resolved if new})
    print("\n--- 人话小结 ---")
    print(
        f"将处理约 {len(report.resolved)} 行推断"
        f"（跳过已有 {len(report.skipped_existing)} 行；未解析 {report.unresolved_count} 行）。"
    )
    if sids:
        print(f"涉及场景 ID：{', '.join(sids[:12])}" + ("…" if len(sids) > 12 else ""))
    if not apply:
        if report.unresolved_count:
            print("建议：先补 --map 或修规则，再 --apply；未解析>0 时 apply 不会写盘。")
        else:
            print("建议：人审通过后执行 --apply 写回台账。")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", type=Path, default=Path.cwd(), help="项目根目录")
    ap.add_argument("--dry-run", action="store_true", help="仅打印报告（默认）")
    ap.add_argument("--apply", action="store_true", help="写回 TSV（unresolved>0 时 exit 1）")
    ap.add_argument(
        "--map",
        type=Path,
        default=None,
        dest="map_file",
        help="可选 TSV 映射：experiment 或 experiment_prefix → scenario_id",
    )
    args = ap.parse_args()

    apply = bool(args.apply)
    if not apply and not args.dry_run:
        apply = False

    try:
        report = backfill_tsv(
            args.repo_root,
            apply=apply,
            map_file=args.map_file,
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1

    _print_report(report, apply=apply)
    if apply and report.unresolved_count > 0:
        print(
            f"\n错误: 仍有 {report.unresolved_count} 行未解析，未写盘",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
