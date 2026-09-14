"""T8/ADR-3：innovation catalog overlay（运行期软层）。

种子（scripts/lib/innovation_catalog.yaml）= 硬、随模板发版、确定性，驱动 depth；
overlay（workspace/innovation_catalog.local.yaml）= 运行期累积、软、可回滚，
由 reflect「寻找」反馈边喂（04）。overlay 当参考、不污染 deterministic depth 硬判定
（AC3：确定性判定器只硬信种子）。overlay 条目按 source（reflect_id）打标，可按 source 回滚。

两类条目共享一个 overlay 文件：
- 技法条目（objectives/activations/…）：命中 (table,key) → compute_fingerprint_from_configs
  追加软 reason overlay_hint:<key>（depth 不动）。
- find_discoveries：T4 反馈边原始候选（论文/生态库），非技法、不触 soft-hint、不碰 depth，
  留作可回滚的 find 痕迹 + 供后续 curation（T9+ 把论文 → 技法条目）。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore

_OVERLAY_PATH = Path("workspace") / "innovation_catalog.local.yaml"


def _overlay_file(repo_root: str | Path) -> Path:
    return Path(repo_root) / _OVERLAY_PATH


def load_innovation_overlay(repo_root: str | Path = ".") -> dict[str, Any]:
    """读 overlay（软层）。缺/空/坏 → {}（非致命，永不抛）。

    与 load_innovation_catalog（硬种子）分离：确定性 depth 判定只读种子，overlay 仅由
    compute_fingerprint_from_configs 的软提示路径消费。
    """
    p = _overlay_file(repo_root)
    if not p.is_file():
        return {}
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def append_catalog_overlay(
    repo_root: str | Path,
    *,
    source: str,
    table: str,
    key: str,
    entry: dict[str, Any],
) -> None:
    """追加一条 overlay 条目（tag source），落盘 workspace/innovation_catalog.local.yaml。

    overlay 是软层：本函数只落盘，不影响 depth（depth 由 compute_fingerprint_from_configs
    只读种子判）。source 用于回滚（按 reflect_id 批量清）。非致命：IO 炸不抛。
    """
    if not table or not key:
        return
    data = load_innovation_overlay(repo_root)
    tbl = data.get(table)
    if not isinstance(tbl, dict):
        tbl = {}
        data[table] = tbl
    rec = dict(entry or {})
    rec["source"] = str(source)
    tbl[str(key)] = rec
    p = _overlay_file(repo_root)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8",
        )
    except Exception:
        pass


def rollback_catalog_overlay(repo_root: str | Path, source: str) -> int:
    """按 source 回滚 overlay 条目（删所有 source 匹配的条目，跨表）。返回删除条数。

    回滚到空 → overlay 文件删除（恢复无 overlay 初态，AC4③「恢复」）。非致命。
    """
    src = str(source)
    if not src:
        return 0
    data = load_innovation_overlay(repo_root)
    removed = 0
    for table, tbl in list(data.items()):
        if not isinstance(tbl, dict):
            continue
        for key, rec in list(tbl.items()):
            if isinstance(rec, dict) and str(rec.get("source") or "") == src:
                del tbl[key]
                removed += 1
        if not tbl:
            del data[table]
    if not removed:
        return 0
    p = _overlay_file(repo_root)
    try:
        if data:
            p.write_text(
                yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8",
            )
        elif p.is_file():
            p.unlink(missing_ok=True)
    except Exception:
        pass
    return removed
