#!/usr/bin/env python3
"""view_runs.py — 选行选列查看 _runs/results.tsv（std lib only）

用法：
  python scripts/view_runs.py --root .                              # 全部
  python scripts/view_runs.py --root . --last 5                     # 最近 5 行
  python scripts/view_runs.py --root . --cols experiment,scenario_id,test_rmse_avg,LR,EPOCHS,git_commit
  python scripts/view_runs.py --root . --where scenario_id=12week_price_pred --last 10
  python scripts/view_runs.py --root . --where LR<0.005 --where EPOCHS>=30
  python scripts/view_runs.py --root . --scenario "*_1pct"          # scenario_id glob
  python scripts/view_runs.py --root . --best-by test_val_acc1 --best-direction higher --cols scenario_id,test_val_acc1
  python scripts/view_runs.py --root . --show-cols                  # 列出所有列名 + 序号
  python scripts/view_runs.py --root . --format tsv | clip         # pipe 给其他工具
  python scripts/view_runs.py --root . --no-header --format csv     # 数据行
  python scripts/view_runs.py --root . --baseline-summary           # plain/reference 尺子计数
  python scripts/view_runs.py --root . --baseline-tags plain,reference --last 20

where 操作符：=（字符串相等）、~（正则）、< > <= >=（数值比较，无法转 float 时退化为字符串）。
--scenario 用 fnmatch glob；--best-by / --best-direction 须同时给；elapsed_sec 列在 table 模式自动转 m/h。
--baseline-tags：按 baseline_tag 列 OR 过滤；有该列时默认把 baseline_tag 插到 --cols 前列。
--baseline-summary：打印尺子体检（可与表一并输出）。
table 模式：baseline_tag 的 none/空 显示为 "-"（tsv/csv 仍原样，不改盘）。
"""
from __future__ import annotations

import argparse
import csv
import fnmatch
import re
import sys
from pathlib import Path

# 超长 cell 截断宽度
MAX_CELL = 40


def _fmt_elapsed(s: str) -> str:
    """elapsed_sec 列智能显示：转秒后按 1m/1h 缩写。"""
    try:
        f = float(s)
    except (ValueError, TypeError):
        return s or ""
    if f < 3600:
        return f"{f/60:.1f}m"
    return f"{f/3600:.1f}h"


def _read_tsv(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(encoding="utf-8", errors="replace") as f:
        rows = list(csv.reader(f, delimiter="\t"))
    if not rows:
        return [], []
    return rows[0], rows[1:]


def _resolve_col(col: str, header: list[str]) -> int:
    if col.isdigit():
        i = int(col)
        if 0 <= i < len(header):
            return i
        sys.exit(f"[view_runs] 列号越界: {col}（表头有 {len(header)} 列）")
    if col in header:
        return header.index(col)
    # 模糊匹配（先前缀，再子串）
    matches = [i for i, h in enumerate(header) if h.startswith(col)]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        sys.exit(f"[view_runs] 列名 '{col}' 模糊匹配到 {len(matches)} 列：{[header[m] for m in matches]}")
    matches = [i for i, h in enumerate(header) if col in h]
    if len(matches) == 1:
        return matches[0]
    sys.exit(f"[view_runs] 未知列: {col}（用 --show-cols 查列名）")


def _parse_where(expr: str, header: list[str]) -> tuple[int, str, str]:
    m = re.match(r"^(\S+?)(=|~|<=|>=|<|>)(.*)$", expr)
    if not m:
        sys.exit(f"[view_runs] 非法 --where: {expr}（格式 col=val / col~regex / col<num）")
    col, op, val = m.group(1), m.group(2), m.group(3)
    return _resolve_col(col, header), op, val


def _row_match(row: list[str], wheres: list[tuple[int, str, str]]) -> bool:
    for ci, op, val in wheres:
        cell = row[ci] if ci < len(row) else ""
        if op == "=":
            if cell != val:
                return False
            continue
        if op == "~":
            if not re.search(val, cell):
                return False
            continue
        # 数值
        try:
            cn, vn = float(cell), float(val)
        except ValueError:
            return False
        if op == "<"  and not (cn <  vn): return False
        if op == ">"  and not (cn >  vn): return False
        if op == "<=" and not (cn <= vn): return False
        if op == ">=" and not (cn >= vn): return False
    return True


def _trunc(s: str, fmt: str | None = None) -> str:
    if fmt == "elapsed":
        s = _fmt_elapsed(s)
    elif fmt == "baseline_tag":
        # 给人看：普通轮显示为 "-"；盘内仍可是 none（tsv/csv 原样）
        raw = (s or "").strip()
        if raw == "" or raw.lower() == "none":
            s = "-"
        else:
            s = raw
    s = s.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    if len(s) > MAX_CELL:
        return s[: MAX_CELL - 1] + "…"
    return s


def _emit_table(headers: list[str], body: list[list[str]], col_idx: list[int]) -> None:
    fmts = []
    for i in col_idx:
        if headers[i] == "elapsed_sec":
            fmts.append("elapsed")
        elif headers[i] == "baseline_tag":
            fmts.append("baseline_tag")
        else:
            fmts.append(None)
    cols = [[_trunc(headers[i], fmts[j]) for j, i in enumerate(col_idx)]]
    for row in body:
        cols.append([_trunc(row[i] if i < len(row) else "", fmts[j]) for j, i in enumerate(col_idx)])
    widths = [max(len(c) for c in col) for col in zip(*cols)]
    # header
    print("  ".join(c.ljust(w) for c, w in zip(cols[0], widths)))
    print("  ".join("-" * w for w in widths))
    for r in cols[1:]:
        print("  ".join(c.ljust(w) for c, w in zip(r, widths)))


def _emit_tsv(headers: list[str], body: list[list[str]], col_idx: list[int], with_header: bool) -> None:
    out = sys.stdout
    if with_header:
        out.write("\t".join(headers[i] for i in col_idx) + "\n")
    for row in body:
        out.write("\t".join((row[i] if i < len(row) else "") for i in col_idx) + "\n")


def _emit_csv(headers: list[str], body: list[list[str]], col_idx: list[int], with_header: bool) -> None:
    w = csv.writer(sys.stdout)
    if with_header:
        w.writerow([headers[i] for i in col_idx])
    for row in body:
        w.writerow([(row[i] if i < len(row) else "") for i in col_idx])


def main() -> int:
    p = argparse.ArgumentParser(
        description="选行选列查看 _runs/results.tsv",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--root", default=".", help="业务仓根（含 _runs/results.tsv）；默认 .")
    p.add_argument("--cols", help="逗号分隔的列名或列号（省略=全列）")
    p.add_argument("--where", action="append", default=[], help="行过滤（可多次：and 关系）")
    p.add_argument("--scenario", help="scenario_id 列 glob 过滤（如 *_1pct、sample_*）")
    p.add_argument("--best-by", help="按此列分组，每组保留最优行（须同时给 --best-direction）")
    p.add_argument("--best-direction", choices=["higher", "lower"], help="--best-by 的方向（higher=越大越好）")
    p.add_argument("--last", type=int, help="只看最后 N 行")
    p.add_argument("--no-header", action="store_true", help="不打印表头（管道友好）")
    p.add_argument("--format", choices=["table", "tsv", "csv"], default="table", help="输出格式")
    p.add_argument("--show-cols", action="store_true", help="列出所有列名 + 序号，不打印行")
    p.add_argument(
        "--baseline-tags",
        help="按 baseline_tag 列 OR 过滤，逗号分隔（如 plain,reference）；缺列则报错",
    )
    p.add_argument(
        "--baseline-summary",
        action="store_true",
        help="先打印 plain/reference 尺子体检（stdout）；可与表一起用",
    )
    p.add_argument(
        "--ensure-baseline-col",
        action="store_true",
        help="若存在 baseline_tag 列且 --cols 未包含，则自动插到列首（默认：给了 --baseline-tags 时也开）",
    )
    args = p.parse_args()

    if (args.best_by is None) != (args.best_direction is None):
        sys.exit("[view_runs] --best-by 与 --best-direction 须同时给")

    tsv_path = Path(args.root) / "_runs" / "results.tsv"
    if not tsv_path.is_file():
        sys.exit(f"[view_runs] 找不到 {tsv_path}")

    header, body = _read_tsv(tsv_path)
    if not header:
        return 0

    if args.show_cols:
        for i, h in enumerate(header):
            print(f"{i:2d}  {h}")
        return 0

    if args.baseline_summary:
        _SCRIPT_DIR = Path(__file__).resolve().parent
        if str(_SCRIPT_DIR) not in sys.path:
            sys.path.insert(0, str(_SCRIPT_DIR))
        from lib.baseline_anchors_status import assess_baseline_anchors

        st = assess_baseline_anchors(Path(args.root).resolve())
        print(
            f"[baseline] plain={'yes' if st.has_plain else 'NO'} "
            f"reference={'yes' if st.has_reference else 'NO'} "
            f"tag_col={'yes' if st.baseline_tag_col else 'NO'} "
            f"rows(plain/ref/other)={st.plain_tag_rows}/{st.reference_tag_rows}/{st.none_tag_rows}"
        )
        if st.missing:
            print(f"[baseline] missing={','.join(st.missing)}")
            for r in st.recommendations[:3]:
                print(f"[baseline] tip: {r}")

    if args.baseline_tags:
        try:
            bi = header.index("baseline_tag")
        except ValueError:
            sys.exit("[view_runs] --baseline-tags 需要 baseline_tag 列（见 --show-cols）")
        want = {t.strip().lower() for t in args.baseline_tags.split(",") if t.strip()}
        if not want:
            sys.exit("[view_runs] --baseline-tags 为空")
        body = [
            r
            for r in body
            if (r[bi].strip().lower() if bi < len(r) else "") in want
        ]

    ensure_bl = args.ensure_baseline_col or bool(args.baseline_tags)
    if args.cols:
        col_names = [c.strip() for c in args.cols.split(",") if c.strip()]
        if ensure_bl and "baseline_tag" in header and "baseline_tag" not in col_names:
            col_names = ["baseline_tag"] + col_names
        col_idx = [_resolve_col(c, header) for c in col_names]
    else:
        col_idx = list(range(len(header)))
        if ensure_bl and "baseline_tag" in header:
            bi = header.index("baseline_tag")
            if bi not in col_idx[:1]:
                col_idx = [bi] + [i for i in col_idx if i != bi]

    wheres = [_parse_where(w, header) for w in args.where]
    body = [r for r in body if _row_match(r, wheres)]

    if args.scenario:
        try:
            si = header.index("scenario_id")
        except ValueError:
            sys.exit("[view_runs] --scenario 需要 scenario_id 列")
        body = [r for r in body if fnmatch.fnmatch(r[si] if si < len(r) else "", args.scenario)]

    if args.best_by:
        try:
            gi = header.index(args.best_by)
        except ValueError:
            sys.exit(f"[view_runs] --best-by 列不存在: {args.best_by}")
        try:
            gi_grp = header.index("scenario_id")
        except ValueError:
            sys.exit("[view_runs] --best-by 需要 scenario_id 列做分组")
        best: dict[str, list[str]] = {}
        for r in body:
            key = r[gi_grp] if gi_grp < len(r) else ""
            try:
                v = float(r[gi]) if gi < len(r) else None
            except ValueError:
                v = None
            if v is None:
                continue
            cur = best.get(key)
            if cur is None:
                best[key] = r
            else:
                try:
                    cur_v = float(cur[gi])
                except (ValueError, IndexError):
                    best[key] = r
                    continue
                better = v > cur_v if args.best_direction == "higher" else v < cur_v
                if better:
                    best[key] = r
        body = sorted(best.values(), key=lambda r: r[gi_grp] if gi_grp < len(r) else "")

    if args.last is not None:
        body = body[-args.last:]

    with_header = not args.no_header
    if args.format == "table":
        _emit_table(header, body, col_idx)
    elif args.format == "tsv":
        _emit_tsv(header, body, col_idx, with_header)
    elif args.format == "csv":
        _emit_csv(header, body, col_idx, with_header)

    # 末尾给一行小计（不污染管道：写到 stderr）
    print(f"[view_runs] {len(body)} rows × {len(col_idx)} cols", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
