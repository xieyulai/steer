"""migrate_fingerprint_history.py — 老 depth 词 → RDDN（一次性）。

RDDN（T2 migrate+contract）：深度轴收口 routine/derived/different + dormant novel
背书槽。旧词 ``extend→derived``、旧 formal-``novel→different`` 已退役（代码无 producer）。
本脚本把**已落盘**的 ``saved/innovation_fingerprint.json`` 里残留的旧 depth 词改写为
RDDN，让升级后的运行代码（router/external/reflect 读 depth 字段）不再撞到旧词。

为什么只迁这一个文件：``write_fingerprint_artifact`` 单文件覆盖写（无 history/append
机制），故 saved/innovation_fingerprint.json 就是全部历史。

- 旧 ``extend→derived``、旧 ``novel→different``（T2 时 novel 无 producer，凡存盘的
  novel 都是旧 formal-novel = different）
- 重算 ``depth_rank`` 跟齐当前 schema（避免老 rank 漂移）
- 同时改写 ``summary_line`` 内嵌的 depth 词（grep 审计不漏）
- 幂等：已是 RDDN 词原样透传，跑两次 = 跑一次
- 无 saved 文件 → no-op（新仓 / 还没跑过 fingerprint 的常见情形）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

# 自举 path：governance-sync.sh 直接 `python3 .../migrate_fingerprint_history.py` 调用，
# 无 PYTHONPATH=scripts。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 旧词 → RDDN。routine/ambiguous/derived/different 透传不动。
# （与 lib.innovation_fingerprint._DEPTH_RANK 保持一致；本地硬编码以免跨模块耦合私有名）
_DEPTH_REMAP = {
    "extend": "derived",   # 旧 extend（部件重排）→ derived
    "novel": "different",  # 旧 formal-novel（形式创新）→ different；novel 背书槽在 T2 无 producer
}

# 改写 depth_rank 跟齐当前 schema（源：lib.innovation_fingerprint._DEPTH_RANK）
_DEPTH_RANK = {
    "ambiguous": 0, "routine": 1, "derived": 2, "different": 3, "novel": 3,
}

# summary_line 内嵌 depth 词按词边界替换（summary 是受控格式，词边界安全）。
_SUMMARY_WORD_RE = re.compile(r"\b(extend|novel)\b")

# 需改写的结构化 depth 字段。
_DEPTH_FIELDS = ("depth", "agent_depth", "effective_depth")


def _remap_value(v: object) -> tuple[object, bool]:
    """单值改写：str 且命中旧词 → (新词, True)；否则 (原值, False)。"""
    if isinstance(v, str) and v in _DEPTH_REMAP:
        return _DEPTH_REMAP[v], True
    return v, False


def migrate(repo_root: Path, *, write: bool, backup: bool = True) -> dict:
    """返回 ``{changed, fields, summary_line_changed, wrote}``。

    - 文件不存在 → ``{changed: False, wrote: False}``（no-op）
    - JSON 损坏/非 dict → ValueError（fail-loud，不静默吞）
    - 命中旧词 → 改写 depth 三字段 + 重算 depth_rank + 改写 summary_line
    - backup=True + write=True + 实际改写 + 备份不存在 → 建 .deprecated.bak 一次
    """
    fp = Path(repo_root) / "saved" / "innovation_fingerprint.json"
    if not fp.is_file():
        return {"changed": False, "fields": [], "summary_line_changed": False, "wrote": False}

    try:
        raw: dict = json.loads(fp.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{fp} 不是合法 JSON（{e}）；手工核对后再迁") from e
    if not isinstance(raw, dict):
        raise ValueError(f"{fp} 顶层不是 dict（{type(raw).__name__}）；手工核对后再迁")

    changed_fields: list[str] = []
    for k in _DEPTH_FIELDS:
        if k in raw:
            new_v, changed = _remap_value(raw[k])
            if changed:
                raw[k] = new_v
                changed_fields.append(f"{k}: {raw[k]}")

    # depth 变了 → depth_rank 跟齐当前 schema（仅在 depth 是已知词时重算）
    if changed_fields and isinstance(raw.get("depth"), str) and raw["depth"] in _DEPTH_RANK:
        raw["depth_rank"] = _DEPTH_RANK[raw["depth"]]

    summary_line_changed = False
    sl = raw.get("summary_line")
    if isinstance(sl, str) and _SUMMARY_WORD_RE.search(sl):
        raw["summary_line"] = _SUMMARY_WORD_RE.sub(
            lambda m: _DEPTH_REMAP[m.group(1)], sl)
        summary_line_changed = True

    changed = bool(changed_fields) or summary_line_changed
    wrote = False
    if changed and write:
        bak = fp.with_suffix(fp.suffix + ".deprecated.bak")
        if backup and not bak.exists():
            shutil.copy2(fp, bak)
        fp.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        wrote = True

    return {
        "changed": changed,
        "fields": changed_fields,
        "summary_line_changed": summary_line_changed,
        "wrote": wrote,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="migrate saved/innovation_fingerprint.json 旧 depth 词 → RDDN（extend→derived, novel→different）")
    ap.add_argument("repo_root", type=Path, nargs="?", default=Path("."),
                    help="业务仓根（默认当前目录）")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="写盘（默认 dry-run）")
    mode.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    args = ap.parse_args(argv)
    try:
        r = migrate(args.repo_root, write=args.write, backup=not args.no_backup)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    if not r["changed"]:
        print("no-op: 已是 RDDN 词或无 saved/innovation_fingerprint.json")
        return 0
    fields = ", ".join(r["fields"]) or "(none)"
    print(f"changed={r['changed']} fields=[{fields}] "
          f"summary_line_changed={r['summary_line_changed']} wrote={r['wrote']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
