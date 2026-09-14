"""spec §4.2 + §5：auto 模式撞墙检测 + effective_mode 跟踪 + yaml 写盘升档。

5 显式 vs auto 区别：
- 5 显式：撞墙 → reflect 写建议，不动 yaml
- auto：撞墙 → 系统写 yaml 升档

升档链：optimize → innovate → aggressive（不含 explore，哲学冲突）
aggressive 撞墙 → 不退

yaml 写 exploration_mode="auto" + auto.effective_mode 记实际档（如 innovate）。
"""
from __future__ import annotations

from pathlib import Path

import yaml

from lib.nn_config import load_nn_config, save_nn_config


# 升档链：5 显式 → 升一档（不含 explore；aggressive 不退）
PROMOTE_CHAIN: dict[str, str] = {
    "optimize": "innovate",
    "innovate": "aggressive",
}

# R8 paradigm_mismatch 宽判决常量（§9.1）：连续 K 轮无创新 best ∧ 主指标走势平稳。
# K=6~8 取 7（宽松，早提醒）；ε=0.5pp（方向无关的 max-min spread）。
# 可经 nn-config 的 paradigm_mismatch.{k,eps} 覆盖（best-effort）。
PARADIGM_MISMATCH_K = 7
PARADIGM_MISMATCH_EPS = 0.005


def _ensure_auto_block(cfg: dict) -> dict:
    """确保 cfg.auto 段存在 + 有 defaults。"""
    auto = cfg.setdefault("auto", {})
    auto.setdefault("start_mode", "optimize")
    auto.setdefault("promote_threshold", 5)
    auto.setdefault("max_mode", "aggressive")
    auto.setdefault("effective_mode", auto["start_mode"])
    auto.setdefault("wall_hit_streak", 0)
    return auto


def check_and_promote_auto(repo_root: Path) -> dict:
    """spec §4.2 + §5：auto 撞墙 promote_threshold 轮 → 升 auto.effective_mode + 写 yaml。

    升档链：optimize → innovate → aggressive
    aggressive 撞墙 → 保持（不退）

    干净切（Task 5）：不再调 apply_mode / 不写 preset 段——bundle 由 resolve_exploration
    读时从 auto.effective_mode 动态派生。仅 bump effective_mode + reset streak + save。
    exploration_mode 保持 "auto" 不变。非 auto 配置 → no-op。

    读 raw yaml（不经 load_nn_config —— 后者做 preset expansion 会钉死段）。

    Returns: 写盘后的 cfg dict
    """
    # 读 raw yaml（避免 preset expansion 钉段）
    path = repo_root / "nn-config.yaml"
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}
    if not isinstance(cfg, dict):
        cfg = {}
    # 非 auto 模式 → no-op
    if not is_auto_mode(cfg):
        return cfg
    auto = _ensure_auto_block(cfg)

    streak = int(auto.get("wall_hit_streak", 0))
    threshold = int(auto.get("promote_threshold", 5))
    eff = str(auto.get("effective_mode", "optimize"))

    # 没撞墙 → 不升
    if streak < threshold:
        return cfg
    if eff not in PROMOTE_CHAIN:
        # aggressive / explore / unknown → 不退，保持当前档
        return cfg

    # 升档：仅 bump effective_mode + reset streak（bundle 读时派生，不写段）
    auto["effective_mode"] = PROMOTE_CHAIN[eff]
    auto["wall_hit_streak"] = 0

    save_nn_config(repo_root, cfg)
    return cfg


def _paradigm_mismatch_params(repo_root: Path) -> tuple[int, float]:
    """读 nn-config ``paradigm_mismatch.{k,eps}``（best-effort），失败用模块默认。

    与 auto 段解耦：R8 须在全模式（含显式档）生效，故配置不挂在 auto-only 段。
    """
    try:
        cfg = load_nn_config(repo_root) or {}
        pm = cfg.get("paradigm_mismatch") if isinstance(cfg, dict) else None
        if isinstance(pm, dict):
            k = int(pm.get("k", PARADIGM_MISMATCH_K))
            eps = float(pm.get("eps", PARADIGM_MISMATCH_EPS))
            return k, eps
    except Exception:
        pass
    return PARADIGM_MISMATCH_K, PARADIGM_MISMATCH_EPS


def check_paradigm_mismatch(repo_root: Path) -> bool:
    """R8 软判决（§9.1）：连续 K 轮「未创新 best」∧ 主指标近 K 轮走势平稳 → 范式撞墙。

    结果导向，只读 ``_runs/results.tsv``（**全模式可用**——不依赖 auto-only 的
    ``wall_hit_streak``，因范式撞墙在任何显式/auto 档都可能发生）：
    - 条件① ``plateau_streak >= K``：近 K 轮无一轮创窗口 best（≈ KEEP=0 连续 K 轮）。
    - 条件② 近 K 轮主指标 ``max - min < ε``：走势平稳（ε=0.5pp，方向无关）。
    两条件 AND，缺一不触发（R8 原则：宁可漏报，不误报）。

    **永不 raise**——调用方（finalize_round / reflect_gate）已在 try 内，本函数再自守：
    IO/解析异常 → 返回 False，决策照常。R8 是软警告，误判代价仅一次多余 reflect。
    """
    try:
        from lib.run_ledger_summary import (  # noqa: WPS433
            metric_key,
            plateau_streak,
            tsv_rows,
        )

        k, eps = _paradigm_mismatch_params(repo_root)
        rows = tsv_rows(repo_root)
        if len(rows) < k:
            return False  # 历史不足 K 轮，无法判决
        # 条件①：近 K 轮无一轮创窗口 best（沿用既有 plateau 判定，与 R2 同源）
        if plateau_streak(repo_root, k) < k:
            return False
        # 条件②：近 K 轮主指标 max-min < ε（走势平稳；declining 时 spread 大 → 不触发）
        mk = metric_key(repo_root)
        vals = []
        for r in rows[-k:]:
            try:
                vals.append(float(r.get(mk, "nan")))
            except ValueError:
                vals.append(float("nan"))
        vals = [v for v in vals if v == v]  # 去 nan（metric_key 列缺失/非数值）
        if len(vals) < 2:
            return False
        if max(vals) - min(vals) >= eps:
            return False
        return True
    except Exception:
        return False  # 软判决：任何异常都不触发（决策照常）


def initialize_auto(repo_root: Path, start_mode: str | None = None) -> dict:
    """初始化 auto 模式：写 auto 段 + exploration_mode="auto"。

    如果 start_mode 是 careful/optimize/innovate/aggressive/explore 之一，用作 start_mode
    如果 start_mode 是 None 或 auto，使用 default optimize

    读 raw yaml（不经 load_nn_config —— 后者做 preset expansion 会钉死段）。
    """
    path = repo_root / "nn-config.yaml"
    cfg = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}
    if not isinstance(cfg, dict):
        cfg = {}
    auto = _ensure_auto_block(cfg)

    if start_mode in ("careful", "optimize", "innovate", "aggressive", "explore"):
        auto["start_mode"] = start_mode
        auto["effective_mode"] = start_mode
    else:
        # auto / None / unknown → 用 default optimize
        start_mode = auto["start_mode"]
        auto["effective_mode"] = start_mode

    cfg["exploration_mode"] = "auto"  # 单旋钮记 auto（resolve_exploration 读 auto.effective_mode 派生 bundle）
    save_nn_config(repo_root, cfg)
    return cfg


def is_auto_mode(cfg: dict) -> bool:
    """判断 cfg 是否在 auto 模式（exploration_mode="auto"，或已初始化 auto 段）。

    运行时判定：initialize_auto 写 exploration_mode="auto" + auto 段（effective_mode
    为实际起步档）。两者任一命中即算 auto 模式。
    """
    if not isinstance(cfg, dict):
        return False
    if str(cfg.get("exploration_mode", "")).strip().lower() == "auto":
        return True
    return isinstance(cfg.get("auto"), dict)