"""GPU 三档快照：exclusive / shareable / busy，供 auto-run 与 Run Context 注入。"""
from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from lib.home_gpus import HomeGpusError, allowed_gpus, detect_local_gpus, read_home_gpus
from lib.nn_config import load_nn_config

DEFAULT_GPU_AGENT: dict[str, float | int | bool] = {
    "gpu_mem_reserve_gb": 2.0,
    "gpu_estimated_mem_gb": 4.0,
    "gpu_exclusive_mem_ratio": 0.25,
    "gpu_exclusive_util_max": 10,
    "gpu_shareable_mem_ratio": 0.70,
    "gpu_shareable_util_max": 50,
    "gpu_busy_mem_ratio": 0.85,
    "gpu_busy_util_min": 80,
    "gpu_colocate_on_single": True,
}


@dataclass
class GpuRow:
    index: int
    mem_used_mb: int
    mem_total_mb: int
    util_pct: int
    mem_ratio: float
    headroom_gb: float
    tier: str  # exclusive | shareable | busy | unknown

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_nn_config(repo_root: Path) -> dict[str, Any]:
    p = repo_root / "nn-config.yaml"
    if not p.is_file():
        return {}
    try:
        import yaml

        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def load_gpu_agent_config(repo_root: Path) -> dict[str, float | int | bool]:
    """读顶层 ``gpu`` 段，返回 classify_gpu 用的扁平键（gpu_* 前缀，非 yaml 双写）。"""
    raw = load_nn_config(repo_root)
    gpu = raw.get("gpu") if isinstance(raw.get("gpu"), dict) else {}
    out: dict[str, float | int | bool] = dict(DEFAULT_GPU_AGENT)
    # DEFAULT_GPU_AGENT keys are agent-era names; map from top-level gpu.*
    _GPU_FLAT_TO_TOP = {
        "gpu_mem_reserve_gb": "mem_reserve_gb",
        "gpu_estimated_mem_gb": "estimated_mem_gb",
        "gpu_exclusive_mem_ratio": "exclusive_mem_ratio",
        "gpu_exclusive_util_max": "exclusive_util_max",
        "gpu_shareable_mem_ratio": "shareable_mem_ratio",
        "gpu_shareable_util_max": "shareable_util_max",
        "gpu_busy_mem_ratio": "busy_mem_ratio",
        "gpu_busy_util_min": "busy_util_min",
        "gpu_colocate_on_single": "colocate_on_single",
    }
    for flat, top_key in _GPU_FLAT_TO_TOP.items():
        if top_key in gpu and gpu[top_key] is not None:
            out[flat] = gpu[top_key]
    return out


def resolve_whitelist(repo_root: Path) -> list[int]:
    """项目名单 ∩ 家目录授权 ∩ 本机。无 ``~/.gpus`` 时与旧行为一致（cfg 空 = 本机全部）。"""
    cfg = _read_nn_config(repo_root)
    cfg_raw = cfg.get("gpus", [])
    cfg_ids: list[int] | None
    if cfg_raw is None or (isinstance(cfg_raw, list) and len(cfg_raw) == 0):
        cfg_ids = None
    elif isinstance(cfg_raw, list):
        cfg_ids = [int(x) for x in cfg_raw]
    else:
        cfg_ids = []

    local = detect_local_gpus()
    home = None
    try:
        home = read_home_gpus()
    except HomeGpusError:
        return []

    if not local and home is None:
        try:
            import torch

            n = int(torch.cuda.device_count())
            local = set(range(n)) if n > 0 else set()
        except Exception:
            local = set()

    try:
        allowed = allowed_gpus(local=local)
    except HomeGpusError:
        return []

    # 有 ~/.gpus：开训活闸以家目录为准，不让项目里过期的 gpus: 再挡住
    if home is not None:
        return sorted(allowed)
    if cfg_ids is None:
        return sorted(allowed)
    return sorted(set(cfg_ids) & allowed) if allowed else list(cfg_ids)


def query_nvidia_smi() -> list[tuple[int, int, int, int]] | None:
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=index,memory.used,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            stderr=subprocess.DEVNULL,
            timeout=15,
        ).decode()
    except Exception:
        return None
    rows: list[tuple[int, int, int, int]] = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        try:
            rows.append((int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])))
        except ValueError:
            continue
    return rows


def classify_gpu(
    *,
    mem_used_mb: int,
    mem_total_mb: int,
    util_pct: int,
    cfg: dict[str, float | int | bool],
) -> tuple[str, float]:
    if mem_total_mb <= 0:
        return "unknown", 0.0
    mem_ratio = mem_used_mb / mem_total_mb
    headroom_gb = max(0.0, (mem_total_mb - mem_used_mb) / 1024.0)
    est = float(cfg.get("gpu_estimated_mem_gb", 4.0))
    reserve = float(cfg.get("gpu_mem_reserve_gb", 2.0))
    busy_mem = float(cfg.get("gpu_busy_mem_ratio", 0.85))
    busy_util = int(cfg.get("gpu_busy_util_min", 80))
    ex_mem = float(cfg.get("gpu_exclusive_mem_ratio", 0.25))
    ex_util = int(cfg.get("gpu_exclusive_util_max", 10))
    sh_mem = float(cfg.get("gpu_shareable_mem_ratio", 0.70))
    sh_util = int(cfg.get("gpu_shareable_util_max", 50))

    if util_pct >= busy_util or mem_ratio >= busy_mem:
        return "busy", headroom_gb
    if mem_ratio <= ex_mem and util_pct <= ex_util:
        return "exclusive", headroom_gb
    if mem_ratio <= sh_mem and util_pct <= sh_util and headroom_gb >= est + reserve:
        return "shareable", headroom_gb
    return "busy", headroom_gb


def build_gpu_rows(
    whitelist: list[int],
    smi_rows: list[tuple[int, int, int, int]] | None,
    cfg: dict[str, float | int | bool],
) -> list[GpuRow]:
    if not whitelist:
        return []
    if smi_rows is None:
        return [
            GpuRow(
                index=i,
                mem_used_mb=0,
                mem_total_mb=0,
                util_pct=0,
                mem_ratio=0.0,
                headroom_gb=0.0,
                tier="unknown",
            )
            for i in whitelist
        ]
    by_idx = {idx: (used, total, util) for idx, used, total, util in smi_rows}
    out: list[GpuRow] = []
    for idx in sorted(whitelist):
        used, total, util = by_idx.get(idx, (0, 0, 0))
        tier, headroom = classify_gpu(
            mem_used_mb=used,
            mem_total_mb=total,
            util_pct=util,
            cfg=cfg,
        )
        mem_ratio = (used / total) if total > 0 else 0.0
        out.append(
            GpuRow(
                index=idx,
                mem_used_mb=used,
                mem_total_mb=total,
                util_pct=util,
                mem_ratio=round(mem_ratio, 4),
                headroom_gb=round(headroom, 2),
                tier=tier,
            )
        )
    return out


def usable_gpu_indices(gpus: list[GpuRow]) -> list[int]:
    return [g.index for g in gpus if g.tier in ("exclusive", "shareable")]


def free_csv(snapshot: dict[str, Any]) -> str:
    gpus = snapshot.get("gpus") or []
    ids = [str(g["index"]) for g in gpus if g.get("tier") in ("exclusive", "shareable")]
    return ",".join(ids)


def assign_slots(snapshot: dict[str, Any], n_slots: int) -> list[int | None]:
    """为 n 个并行槽建议 GPU 索引；None 表示该槽无法安全分配。"""
    if n_slots <= 0:
        return []
    cfg = snapshot.get("config") or {}
    est = float(cfg.get("gpu_estimated_mem_gb", 4.0))
    reserve = float(cfg.get("gpu_mem_reserve_gb", 2.0))
    colocate = bool(cfg.get("gpu_colocate_on_single", True))
    whitelist = snapshot.get("whitelist") or []
    gpus_raw = snapshot.get("gpus") or []
    usable = [g for g in gpus_raw if g.get("tier") in ("exclusive", "shareable")]
    if not usable:
        return [None] * n_slots

    allocated: dict[int, float] = {int(g["index"]): 0.0 for g in usable}

    def remaining(g: dict[str, Any]) -> float:
        idx = int(g["index"])
        return float(g.get("headroom_gb") or 0.0) - allocated[idx] - reserve

    def pick_slot_gpu(prefer_unused_exclusive: bool) -> int | None:
        if prefer_unused_exclusive:
            for g in sorted(usable, key=lambda x: int(x["index"])):
                if g.get("tier") == "exclusive" and allocated[int(g["index"])] == 0.0:
                    if remaining(g) >= est:
                        return int(g["index"])
        candidates = [g for g in usable if remaining(g) >= est]
        if candidates:
            best = max(candidates, key=lambda g: remaining(g))
            return int(best["index"])
        if colocate and len(whitelist) == 1 and len(usable) == 1:
            g = usable[0]
            if remaining(g) >= est:
                return int(g["index"])
        return None

    slots: list[int | None] = []
    for i in range(n_slots):
        idx = pick_slot_gpu(prefer_unused_exclusive=(i < len(usable)))
        if idx is None:
            slots.append(None)
        else:
            allocated[idx] += est
            slots.append(idx)
    return slots


def build_snapshot(
    repo_root: Path,
    *,
    smi_rows: list[tuple[int, int, int, int]] | None = None,
) -> dict[str, Any]:
    root = repo_root.resolve()
    cfg = load_gpu_agent_config(root)
    whitelist = resolve_whitelist(root)
    if smi_rows is None:
        smi_rows = query_nvidia_smi()
    gpus = build_gpu_rows(whitelist, smi_rows, cfg)
    smi_ok = smi_rows is not None
    snapshot: dict[str, Any] = {
        "schema_version": 1,
        "smi_ok": smi_ok,
        "whitelist": whitelist,
        "config": {
            "mem_reserve_gb": cfg["gpu_mem_reserve_gb"],
            "estimated_mem_gb": cfg["gpu_estimated_mem_gb"],
            "colocate_on_single": cfg["gpu_colocate_on_single"],
        },
        "gpus": [g.to_dict() for g in gpus],
        "usable_count": len(usable_gpu_indices(gpus)),
        "free_gpus": free_csv({"gpus": [g.to_dict() for g in gpus]}) or "unknown",
    }
    if not smi_ok:
        snapshot["free_gpus"] = "unknown"
    return snapshot


def format_gpu_table_lines(snapshot: dict[str, Any]) -> list[str]:
    gpus = snapshot.get("gpus") or []
    if not gpus:
        return ["gpu_snapshot: (no whitelist GPUs)"]
    tier_zh = {
        "exclusive": "独占（近空）",
        "shareable": "可共享（可同卡插队）",
        "busy": "繁忙（勿加任务）",
        "unknown": "未知（无法探测）",
    }
    lines = [
        "gpu 快照（tier=档位；headroom=剩余显存 GB；est=单槽预估占用）:",
    ]
    est = float((snapshot.get("config") or {}).get("estimated_mem_gb", 4.0))
    for g in gpus:
        tier = str(g.get("tier") or "unknown")
        label = tier_zh.get(tier, tier)
        mem_pct = round(float(g.get("mem_ratio") or 0.0) * 100, 1)
        lines.append(
            f"  GPU {g['index']}: tier={tier}({label}) "
            f"mem={mem_pct}% util={g.get('util_pct')}% "
            f"headroom={g.get('headroom_gb')}GB"
        )
    lines.append(f"  单槽预估显存≈{est}GB；usable_gpus={snapshot.get('usable_count', 0)}")
    return lines


def format_slot_assignment_lines(snapshot: dict[str, Any], n_slots: int) -> list[str]:
    if n_slots <= 1:
        return []
    slots = assign_slots(snapshot, n_slots)
    if not any(s is not None for s in slots):
        return [f"slot 建议: {n_slots} 槽但当前无可用 GPU（全 busy/unknown）→ 降并行或等待"]
    parts = []
    for i, gpu in enumerate(slots):
        if gpu is None:
            parts.append(f"slot{i}=?")
        else:
            parts.append(f"slot{i}→GPU{gpu}")
    uniq = sorted({g for g in slots if g is not None})
    if len(uniq) == 1 and n_slots > 1:
        hint = f"同卡 {n_slots} 槽（CUDA_VISIBLE_DEVICES={uniq[0]}，各 NN_SLOT 不同）"
    else:
        hint = "；".join(
            f"slot{i} CUDA_VISIBLE_DEVICES={gpu}" for i, gpu in enumerate(slots) if gpu is not None
        )
    return [f"slot 建议（{', '.join(parts)}）: {hint}"]
