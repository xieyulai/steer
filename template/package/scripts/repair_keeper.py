#!/usr/bin/env python3
"""修复 saved/keepers.json 指针的"滞后"与"路径硬编码死链"。

keeper 应该是 **TSV 主指标最优 run 的指针**。两类问题导致它滞后:

1. **指针不指 TSV 最优**：all_primary 在 Pareto 前沿下结构性不可达
   (primary + auxiliary 必须同时最优), keeper 永远停在最后一次
   "双过"的旧 run。
2. **路径写绝对**:keeper_exp_dir / best_model_path 是绝对路径,
   业务仓 cp 到 sandbox 后这些路径立即变成死链。

修法 (v2.5.7):
1. 备份 saved/keepers.json → saved/keepers.json.bak.<ts>
2. 对每个 scenario_id:
   - 用 ``metric_key(repo_root)`` + ``metric_direction`` 取主指标
   - 从 _runs/results.tsv 找该 scenario 的主指标最优 run
   - 比当前 pointer.experiment,不一致则重写
   - keeper_exp_dir / best_model_path 改相对 ``_runs/exp/...`` (不再 resolve 绝对)
3. **自检**:所有 pointer 必须 == TSV 主指标最优 + path 必须存在 + 路径相对
4. 默认 ``--dry-run``; ``--apply`` 才写盘
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib.run_ledger_summary import metric_direction, metric_key  # noqa: E402


def _read_keeper_path(repo_root: Path) -> Path:
    return repo_root / "saved" / "keepers.json"


def _read_tsv(repo_root: Path) -> list[dict[str, str]]:
    tsv = repo_root / "_runs" / "results.tsv"
    if not tsv.is_file():
        return []
    with tsv.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def _best_run(
    rows: list[dict[str, str]],
    scenario_id: str,
    metric_col: str,
    direction: str,
) -> dict[str, str] | None:
    """从 TSV rows 找该 scenario 的主指标最优行。maximize 取 max, minimize 取 min。"""
    cands: list[tuple[float, dict[str, str]]] = []
    for r in rows:
        if r.get("scenario_id", "").strip() != scenario_id:
            continue
        v = r.get(metric_col, "").strip()
        if not v:
            continue
        try:
            fv = float(v)
        except ValueError:
            continue
        cands.append((fv, r))
    if not cands:
        return None
    if direction == "minimize":
        cands.sort(key=lambda x: x[0])
    else:
        cands.sort(key=lambda x: -x[0])
    return cands[0][1]


def _is_abs(p: str) -> bool:
    return p.startswith("/") or (len(p) >= 2 and p[1] == ":")


def _to_repo_rel(repo_root: Path, p: str) -> str:
    """绝对路径转 repo_root 相对;若已在 repo_root 内,返回相对 _runs/exp/... 等。
    若不在 repo_root 内,保留原绝对路径(标 warn 让用户知情)。
    """
    if not _is_abs(p):
        return p
    pp = Path(p).resolve()
    try:
        return str(pp.relative_to(repo_root.resolve()))
    except ValueError:
        return p  # 保留绝对,标 warn


def repair(repo_root: Path, apply: bool = False) -> int:
    keeper_path = _read_keeper_path(repo_root)
    if not keeper_path.is_file():
        print("[repair-keeper] 无 saved/keepers.json,跳过 (无 keeper 可修)")
        return 0

    try:
        data = json.loads(keeper_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[repair-keeper] FAIL: keepers.json 损坏: {exc}")
        return 1
    if not isinstance(data, dict):
        print("[repair-keeper] FAIL: keepers.json 顶层不是 dict")
        return 1

    mk = metric_key(repo_root)
    direction = metric_direction(repo_root)
    rows = _read_tsv(repo_root)

    print(f"[repair-keeper] 主指标={mk!r} 方向={direction!r}  业务仓={repo_root}")
    print(f"[repair-keeper] keepers.json 共 {len(data)} 个 scenario")

    actions: list[str] = []
    new_data: dict = {}
    checks: list[tuple[str, str, str]] = []  # (sid, status, msg)

    for sid, ptr in data.items():
        if not isinstance(ptr, dict):
            new_data[sid] = ptr
            checks.append((sid, "skip", "非 dict,跳过"))
            continue

        best = _best_run(rows, sid, mk, direction)
        best_exp = (best or {}).get("experiment", "").strip()
        cur_exp = (ptr.get("experiment") or "").strip()
        cur_kdir = (ptr.get("keeper_exp_dir") or "").strip()
        cur_bm = (ptr.get("best_model_path") or "").strip()

        # 1. 路径相对化
        new_kdir = _to_repo_rel(repo_root, cur_kdir) if cur_kdir else cur_kdir
        new_bm = _to_repo_rel(repo_root, cur_bm) if cur_bm else cur_bm
        if cur_kdir and _is_abs(cur_kdir):
            actions.append(f"{sid}: 路径绝对→相对 ({cur_kdir} → {new_kdir})")
        if cur_bm and _is_abs(cur_bm):
            actions.append(f"{sid}: best_model_path 绝对→相对")

        # 2. 指针指 TSV 最优（experiment + keeper_exp_dir 一起改）
        best_dir = (best or {}).get("exp_dir", "").strip()
        if best_exp and best_exp != cur_exp:
            actions.append(
                f"{sid}: pointer.experiment '{cur_exp}' → '{best_exp}' (TSV 主指标最优)"
            )
            if best_dir:
                new_kdir = _to_repo_rel(repo_root, best_dir)
                new_bm = f"{new_kdir.rstrip('/')}/best_model.pt"
                actions.append(f"{sid}: keeper_exp_dir → {new_kdir}")
        elif best_dir and _to_repo_rel(repo_root, best_dir) != new_kdir:
            new_kdir = _to_repo_rel(repo_root, best_dir)
            new_bm = f"{new_kdir.rstrip('/')}/best_model.pt"
            actions.append(f"{sid}: keeper_exp_dir → {new_kdir} (对齐 TSV exp_dir)")
        elif best_exp and best_exp == cur_exp:
            checks.append((sid, "ok", f"pointer 已对齐 TSV 最优 ({best_exp})"))
        elif not best_exp:
            checks.append((sid, "warn", f"TSV 无 {sid} 主指标数据,保留原指针"))

        # 3. 指针路径在 repo_root 内
        exp_dir = new_kdir or cur_kdir
        if exp_dir:
            ep = (repo_root / exp_dir).resolve() if not _is_abs(exp_dir) else Path(exp_dir)
            if ep.exists():
                checks.append((sid, "ok", f"exp dir 存在 ({exp_dir})"))
            else:
                checks.append((sid, "fail", f"exp dir 不存在 ({exp_dir})"))

        # 组装新指针
        new_ptr = dict(ptr)
        new_ptr["keeper_exp_dir"] = new_kdir
        new_ptr["best_model_path"] = new_bm
        if best_exp:
            new_ptr["experiment"] = best_exp
        new_ptr["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        new_data[sid] = new_ptr

    if not actions:
        print("[repair-keeper] 无需修复 (路径已相对 + 指针已对齐 TSV 最优)")
        for sid, status, msg in checks:
            print(f"  [{status}] {sid}: {msg}")
        return 0

    print(f"[repair-keeper] 待修复 ({len(actions)} 项):")
    for a in actions:
        print(f"  - {a}")

    if not apply:
        print("[repair-keeper] --dry-run: 加 --apply 写盘 (会先备份)")
        return 0

    # 备份 + 写回
    bak = keeper_path.with_suffix(
        f".json.bak.{dt.datetime.now():%Y%m%d-%H%M%S}"
    )
    shutil.copy2(keeper_path, bak)
    keeper_path.write_text(
        json.dumps(new_data, indent=2, ensure_ascii=False, sort_keys=False),
        encoding="utf-8",
    )
    print(f"[repair-keeper] ✅ 已写回 (备份 {bak.name})")

    # 自检: 重读一遍确认
    re_read = json.loads(keeper_path.read_text(encoding="utf-8"))
    rows2 = _read_tsv(repo_root)
    fail_count = 0
    for sid, ptr in re_read.items():
        if not isinstance(ptr, dict):
            continue
        cur_exp = (ptr.get("experiment") or "").strip()
        best = _best_run(rows2, sid, mk, direction)
        best_exp = (best or {}).get("experiment", "").strip()
        if best_exp and cur_exp != best_exp:
            print(f"  [fail] {sid}: 写后仍未对齐 ({cur_exp} vs {best_exp})")
            fail_count += 1
        # path 相对检查
        cur_kdir = (ptr.get("keeper_exp_dir") or "")
        if cur_kdir and _is_abs(cur_kdir):
            print(f"  [fail] {sid}: 写后路径仍是绝对 ({cur_kdir})")
            fail_count += 1
    if fail_count:
        print(f"[repair-keeper] 自检 FAIL: {fail_count} 项;请检查 TSV 是否完整")
        return 2
    print("[repair-keeper] 自检 PASS: 所有 pointer == TSV 主指标最优 + 路径相对")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--repo-root", type=Path, default=Path.cwd(),
                   help="业务仓根 (默认 cwd)")
    p.add_argument("--apply", action="store_true",
                   help="写盘 (默认 dry-run; 会先备份 saved/keepers.json.bak.<ts>)")
    p.add_argument("--check", action="store_true",
                   help="只读检查 (供 nn-doctor 调用; 输出 PASS/WARN/FAIL + 退出码)")
    args = p.parse_args()

    if args.check:
        return check_only(args.repo_root.resolve())

    return repair(args.repo_root.resolve(), apply=args.apply)


def check_only(repo_root: Path) -> int:
    """只读检查（供 nn-doctor 调用）: 输出 PASS/WARN/FAIL + 退出码。

    - PASS (0): keepers.json 不存在 / 无 staleness / 无绝对路径
    - WARN (1): pointer 与 TSV 主指标最优不一致 或 路径绝对
    - FAIL (2): exp dir 不存在 (死链)
    """
    keeper_path = _read_keeper_path(repo_root)
    if not keeper_path.is_file():
        print("PASS: 无 saved/keepers.json (无 keeper 可检)")
        return 0
    try:
        data = json.loads(keeper_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"FAIL: keepers.json 损坏: {exc}")
        return 2
    if not isinstance(data, dict):
        print("FAIL: keepers.json 顶层不是 dict")
        return 2

    mk = metric_key(repo_root)
    direction = metric_direction(repo_root)
    rows = _read_tsv(repo_root)

    issues: list[str] = []
    for sid, ptr in data.items():
        if not isinstance(ptr, dict):
            continue
        cur_exp = (ptr.get("experiment") or "").strip()
        cur_kdir = (ptr.get("keeper_exp_dir") or "").strip()
        best = _best_run(rows, sid, mk, direction)
        best_exp = (best or {}).get("experiment", "").strip()
        # pointer staleness
        if best_exp and cur_exp != best_exp:
            issues.append(f"{sid}: pointer '{cur_exp}' ≠ TSV 最优 '{best_exp}'")
        # 绝对路径
        if cur_kdir and _is_abs(cur_kdir):
            issues.append(f"{sid}: keeper_exp_dir 是绝对路径 (cp 后变死链)")
        # exp dir 不存在
        if cur_kdir:
            ep = (repo_root / cur_kdir).resolve() if not _is_abs(cur_kdir) else Path(cur_kdir)
            if not ep.exists():
                issues.append(f"{sid}: exp dir 不存在 ({cur_kdir})")

    if not issues:
        print("PASS: keeper 指针 == TSV 主指标最优 + 路径相对")
        return 0
    print(f"WARN: {len(issues)} 项需修 (跑 scripts/repair_keeper.py --apply):")
    for it in issues:
        print(f"  - {it}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())