from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lib.nn_config import save_nn_config


def _resolve_keep_delta(keep_cfg: dict, *, default: float = 0.005) -> float:
    """spec §0.1：解析 keep.* 的 delta 字段优先级。

    优先级：primary_delta_rel（新）→ primary_delta（老）→ default
    类型守卫：必须是数字（含 int / float），且**不是** bool（防 YAML true/false 污染）。

    Args:
        keep_cfg: 已读出的 keep 段 dict；非 dict 时走 default。
        default: 兜底 delta（相对值）。

    Returns:
        解析后的 float delta。
    """
    if not isinstance(keep_cfg, dict):
        return default
    for key in ("primary_delta_rel", "primary_delta"):
        v = keep_cfg.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
    return default


def _resolve_keep_threshold(
    best: float,
    default_delta: float,
    *,
    cfg_path: Path | None = None,
) -> float:
    """spec §0.1：相对阈值（``best × (1 + delta)``），不是 ``best + delta``。

    60% + 0.01 = 60.6%（不是 61%）。

    字段优先级：``primary_delta_rel``（新）→ ``primary_delta``（老，向后兼容）→
    ``default_delta``（入参）。

    Args:
        best: 历史最佳值。
        default_delta: yaml 未配时的回退 delta（相对值）。
        cfg_path: ``nn-config.yaml`` 路径。``None`` 或不存在 → 走 default_delta。

    Returns:
        ``best × (1 + delta)``。下游 ``_primary_improved`` 再与 best 比对。
    """
    delta = default_delta
    if cfg_path is not None and cfg_path.is_file():
        import yaml

        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        keep = cfg.get("keep") or {}
        delta = _resolve_keep_delta(keep, default=default_delta)
    return best * (1.0 + delta)


def apply_mode(repo_root: Path, mode: str, *, start_mode: str | None = None) -> dict:
    """spec §5 干净切：写 exploration_mode 单旋钮（bundle 由 resolve_exploration 读时派生）。

    6 显式档（careful/optimize/innovate/aggressive/explore）：
    - 仅写 ``cfg["exploration_mode"] = mode``
    - **不**写 keep/reflect/goal/early_stop/external/experiment/exploration 段
      （bundle 在读时由 resolve_exploration/load_nn_config 从 preset 派生，
       钉死会造成后续换档时 stale override）

    auto 档（spec §4.2）：
    - 调 lib.auto_mode.initialize_auto(repo_root, start_mode)
    - 写 auto 段 + exploration_mode="auto"

    Returns: 写盘后的 cfg dict
    """
    m = (mode or "").strip().lower()

    # auto 分支（spec §4.2）：撞墙自动升档
    if m == "auto":
        from lib.auto_mode import initialize_auto

        return initialize_auto(repo_root, start_mode=start_mode)

    if m not in _VANILLA_MODES:
        raise ValueError(
            f"invalid mode: {mode!r} (valid 5 显式档：careful/optimize/innovate/aggressive/explore; 'auto' 也支持)"
        )

    import yaml

    # 读 raw yaml（不经 load_nn_config —— 后者做 preset expansion 会钉死段，
    # 造成后续换档时 stale override）。仅写 exploration_mode 单旋钮。
    p = repo_root / "nn-config.yaml"
    cfg = yaml.safe_load(p.read_text(encoding="utf-8")) if p.is_file() else {}
    if not isinstance(cfg, dict):
        cfg = {}
    cfg["exploration_mode"] = m
    save_nn_config(repo_root, cfg)
    return cfg


def set_experiment_mode(repo_root: Path, mode: str, *, start_mode: str | None = None) -> dict:
    """6 档统一入口（SKILL.md mode-setter / manage_goal.py mode 子命令真路径）。

    - auto → initialize_auto（懒导入防 auto_mode↔experiment_mode 环）
    - 其余 5 显式档 → apply_mode（仅写 exploration_mode + save）

    Returns: 写盘后的 cfg dict
    """
    m = (mode or "").strip().lower()

    if m == "auto":
        from lib.auto_mode import initialize_auto  # 懒导入防环

        return initialize_auto(repo_root, start_mode=start_mode)

    if m not in _VANILLA_MODES:
        raise ValueError(
            f"invalid mode: {mode!r} (valid: careful/optimize/innovate/aggressive/explore/auto)"
        )

    return apply_mode(repo_root, m)


@dataclass
class ExplorationResolution:
    mode: str                       # 用户旋钮原值（含 auto）
    resolved_mode: str              # 实际生效档（auto 时 = effective_mode）
    is_auto: bool
    skip_goal_stop: bool
    innovate_prompt_boost: bool
    tier_start: str
    keep: dict
    reflect: dict
    goal: dict
    external: dict
    early_stop: dict


_VANILLA_MODES = ("careful", "optimize", "innovate", "aggressive", "explore")


def resolve_exploration(repo_root: Path) -> ExplorationResolution:
    """exploration_mode → 完整 bundle + 运行时旗标（spec §5）。

    自包含解析（读 raw yaml，不经 load_nn_config —— 后者做 preset expansion，
    会烤错 section）。集中读时解析器：exploration_mode → bundle + flags。
    缺 exploration_mode → KeyError（no-fallback）。
    """
    import yaml
    from lib.presets import default_for_mode, _deep_merge

    path = Path(repo_root) / "nn-config.yaml"
    raw: dict = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}
    if not isinstance(raw, dict):
        raw = {}

    mode = raw["exploration_mode"]                       # 必填，缺失 KeyError
    if not isinstance(mode, str):
        raise KeyError("exploration_mode must be a string")
    mode = mode.strip().lower()

    if mode == "auto":
        auto = raw.get("auto") or {}
        eff = str(auto.get("effective_mode", "optimize")).strip().lower()
        resolved_mode = eff if eff in _VANILLA_MODES else "optimize"
        is_auto = True
    else:
        resolved_mode = mode if mode in _VANILLA_MODES else "optimize"
        is_auto = False

    bundle = default_for_mode(resolved_mode)
    # 用户叶子覆盖（presence-check）：yaml 显式段 deep-merge 胜出（spec §6）
    for sec in ("keep", "reflect", "external", "early_stop", "goal"):
        user = raw.get(sec)
        if isinstance(user, dict) and isinstance(bundle.get(sec), dict):
            bundle[sec] = _deep_merge(bundle[sec], user)

    return ExplorationResolution(
        mode=mode,
        resolved_mode=resolved_mode,
        is_auto=is_auto,
        skip_goal_stop=(resolved_mode == "explore"),
        innovate_prompt_boost=(resolved_mode in ("innovate", "aggressive")),
        tier_start=bundle["tier_start"],
        keep=bundle["keep"],
        reflect=bundle["reflect"],
        goal=bundle["goal"],
        external=bundle["external"],
        early_stop=bundle["early_stop"],
    )
