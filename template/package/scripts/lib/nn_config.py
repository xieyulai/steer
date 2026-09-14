"""nn-config.yaml：顶层 block 唯一权威（无 agent.* 迁移别名双写）。

历史：曾将 ~59 个 `agent.*` 键迁到顶层 block，并用 load 回填 / save forward
保留双写。现已切断：LOAD 不回填；SAVE 先 forward 再 pop 迁移别名。
`AGENT_TO_TOP_KEYS` 仅作迁移表（migrate_agent_keys / save 一次性搬迁）。

`plateau_rounds` 与 scenario_* 故意排除，永久留在 agent。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .migrate_goal_schema import migrate_goal

# agent 旧键 → (顶层 block, 新键)。59 项；plateau_rounds 不在其中。
# 留 agent 的键：plateau_rounds（experiment-physics 维度）、scenario_active/axis/
# default/policy（场景配置，set-scenario-policy 专管）。
AGENT_TO_TOP_KEYS: dict[str, tuple[str, str]] = {
    # reflect:
    "reflect_interval": ("reflect", "interval"),
    "reflect_force": ("reflect", "force"),
    "reflect_skip": ("reflect", "skip"),
    "reflect_evidence_recent": ("reflect", "evidence_recent"),
    "reflect_evidence_attested_failures": ("reflect", "evidence_attested_failures"),
    "reflect_evidence_include_flagged": ("reflect", "evidence_include_flagged"),
    "reflect_evidence_log_tail_lines": ("reflect", "evidence_log_tail_lines"),
    "reflect_evidence_snapshot_diff": ("reflect", "evidence_snapshot_diff"),
    "reflect_evidence_git_log": ("reflect", "evidence_git_log"),
    "reflect_evidence_git_log_max": ("reflect", "evidence_git_log_max"),
    # goal:（v4 字段名；与 migrate_goal_schema.AGENT_FIELD_MAP 对齐）
    "goal_value": ("goal", "target"),
    "goal_metric": ("goal", "metric"),
    "goal_op": ("goal", "op"),
    "goal_stop_mode": ("goal", "policy"),
    "scenario_goals": ("goal", "per_scenario"),
    # exploration:
    "objective_mode": ("exploration", "objective_mode"),
    # external:
    "external_evidence_enabled": ("external", "enabled"),
    "external_task_domain": ("external", "task_domain"),
    "external_max_http_per_reflect": ("external", "max_http_per_reflect"),
    "external_paper_hits_default": ("external", "paper_hits_default"),
    "external_paper_hits_deepen": ("external", "paper_hits_deepen"),
    "external_pdf_enabled": ("external", "pdf_enabled"),
    "external_serper_key_env": ("external", "serper_key_env"),
    # innovation:
    "innovation_audit_enabled": ("innovation", "audit_enabled"),
    "innovation_fingerprint_enabled": ("innovation", "fingerprint_enabled"),
    "innovation_fingerprint_authoritative": ("innovation", "fingerprint_authoritative"),
    # tier_attestation（TAM）:
    "tier_attestation_enabled": ("tier_attestation", "enabled"),
    "tier_attestation_window": ("tier_attestation", "window"),
    "tier_exhaust_min_attempts": ("tier_attestation", "exhaust_min_attempts"),
    # gpu:
    "gpu_mem_reserve_gb": ("gpu", "mem_reserve_gb"),
    "gpu_estimated_mem_gb": ("gpu", "estimated_mem_gb"),
    "gpu_exclusive_mem_ratio": ("gpu", "exclusive_mem_ratio"),
    "gpu_exclusive_util_max": ("gpu", "exclusive_util_max"),
    "gpu_shareable_mem_ratio": ("gpu", "shareable_mem_ratio"),
    "gpu_shareable_util_max": ("gpu", "shareable_util_max"),
    "gpu_busy_mem_ratio": ("gpu", "busy_mem_ratio"),
    "gpu_busy_util_min": ("gpu", "busy_util_min"),
    "gpu_colocate_on_single": ("gpu", "colocate_on_single"),
    # training:
    "train_poll_interval_sec": ("training", "train_poll_interval_sec"),
    # context:
    "run_context_injection": ("context", "injection"),
    "run_context_journal_max_entries": ("context", "journal_max_entries"),
    "run_context_recent_rows": ("context", "recent_rows"),
    "language": ("context", "language"),
    # analyse:
    "analyse_recent_rows": ("analyse", "recent_rows"),
    "analyse_aux_max": ("analyse", "aux_max"),
    "analyse_flat_pct": ("analyse", "flat_pct"),
    "analyse_noise_std_hint": ("analyse", "noise_std_hint"),
    # compress:
    "experience_auto_compress": ("compress", "experience_auto_compress"),
    "experience_compress_preset": ("compress", "experience_compress_preset"),
    "experience_compress_keep_n": ("compress", "experience_compress_keep_n"),
    "experience_compress_keep_reflects": ("compress", "experience_compress_keep_reflects"),
    "experience_compress_tier_cell_max": ("compress", "experience_compress_tier_cell_max"),
    "experience_compress_scenario_cell_max": ("compress", "experience_compress_scenario_cell_max"),
    "experience_compress_reflect_hist_summary_max": ("compress", "experience_compress_reflect_hist_summary_max"),
    "experience_compress_min_lines": ("compress", "experience_compress_min_lines"),
    "experience_compress_min_archivable": ("compress", "experience_compress_min_archivable"),
    "experience_compress_cooldown_rounds": ("compress", "experience_compress_cooldown_rounds"),
    # safety:
    "human_guidance_gate_fail_fast": ("safety", "human_guidance_gate_fail_fast"),
    "skill_activity_log": ("safety", "skill_activity_log"),
}

__all__ = [
    "AGENT_TO_TOP_KEYS",
    "forward_and_pop_agent_aliases",
    "load_nn_config",
    "save_nn_config",
    "load_nn_config_legacy_keys",
]


# ---------------------------------------------------------------------------
# v4 schema helper for auto-nn-run.sh (T-A5 fix)
# ---------------------------------------------------------------------------
# 旧 auto-nn-run.sh 用 python heredoc 解析 v3 schema 字段路径（agent.exploration /
# keep.improve_mode / keep.mode / keep.primary_delta），v4 schema 字段全部解析为空 → log 显示
# `keep=? mode=? primary_delta=?` + `exploration=conservative`（fallback 默认）。
# 改用 load_nn_config()（v4-aware + preset expansion）输出以下 15 行（顺序对齐原 heredoc），
# 让 auto-nn-run.sh 的 CFG_* 变量能正确读 v4 schema 字段。
# 返回：15 行纯字符串（每行一个字段，空值 = ""），auto-nn-run.sh 用 `IFS=$'\n' read -r` 拆。
_LEGACY_KEYS_ORDER = (
    "profile",                          # _vals[0]
    "time_budget",                      # _vals[1]
    "gpus",                             # _vals[2]
    "max_parallel",                     # _vals[3]
    "keep.improve_mode",                # _vals[4]
    "keep.mode",                        # _vals[5]
    "keep.primary_delta",               # _vals[6]  (v3; v4 用 primary_delta_rel 但 _vals[6] 兼容老字段名)
    "keep.near_best_abs",               # _vals[7]
    "exploration_mode",                 # _vals[8]  (单旋钮 6 档)
    "agent.plateau_rounds",             # _vals[9]
    "reflect.interval",                 # _vals[10] (v4 顶层 block)
    "training.train_poll_interval_sec", # _vals[11] (v4 顶层 block)
    "agent.scenario_policy",            # _vals[12]
    "agent.scenario_default",           # _vals[13]
    "agent.scenario_active",            # _vals[14]
)


def load_nn_config_legacy_keys(repo_root) -> str:
    """读 nn-config.yaml (v4 schema) 并按 _LEGACY_KEYS_ORDER 输出 15 行（每行一个字段）。

    spec T-A5: 替代 auto-nn-run.sh 的 python heredoc v3 schema 字段路径解析。
    兼容 v4 顶层 block（load_nn_config 不再回填 agent 迁移别名）。
    空值字段输出空字符串 ""（不让 auto-nn-run.sh 看到 `?`）。
    """
    from pathlib import Path as _Path
    cfg = load_nn_config(_Path(repo_root)) or {}
    keep = cfg.get("keep", {}) or {}
    agent = cfg.get("agent", {}) or {}
    external = cfg.get("external", {}) or {}
    training = cfg.get("training", {}) or {}
    reflection = cfg.get("reflect", {})

    def _g(d, *path, default=""):
        v = d
        for k in path:
            if not isinstance(v, dict) or k not in v:
                return default
            v = v[k]
        if isinstance(v, list):
            return ",".join(map(str, v))
        return "" if v is None else str(v)

    gpus = cfg.get("gpus", "")
    if isinstance(gpus, list):
        gpus = ",".join(map(str, gpus))

    exploration_val = str(cfg.get("exploration_mode", "") or "")

    vals = [
        str(cfg.get("profile", "")),
        str(cfg.get("time_budget", "")),
        str(gpus),
        str(cfg.get("max_parallel", "")),
        str(keep.get("improve_mode", "any_primary")),  # v3 fallback;v4 不需要
        str(keep.get("mode", "relative")),            # v3 fallback;v4 不需要
        str(keep.get("primary_delta_rel", keep.get("primary_delta", ""))),  # v4 优先
        str(keep.get("near_best_abs", "")),
        str(exploration_val),
        str(agent.get("plateau_rounds", "")),
        str(reflection.get("interval", "")),         # v4 顶层 block
        str(training.get("train_poll_interval_sec", "")),  # v4 顶层 block
        str(agent.get("scenario_policy", "")),
        str(agent.get("scenario_default", "")),
        str(agent.get("scenario_active", "")),
    ]
    return "\n".join(vals)


def _deep_merge_preset(yaml_cfg: dict, preset: dict) -> dict:
    """Recursive merge:preset 提供 missing 字段默认值;yaml 显式写的不动。

    - preset 是基底;遍历 yaml 显式写到的 key。
    - 若 yaml[k] 与 merged[k] 都是 dict → 递归合并。
    - 否则 yaml 显式值直接覆盖。
    """
    merged = dict(preset)
    for k, v in yaml_cfg.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = _deep_merge_preset(v, merged[k])
        else:
            merged[k] = v
    return merged


# 顶层骨架旋钮（人面板），无论值 == 不 == preset 默认都保留——让人能看到/改的 yaml 骨架
_KEEP_TOP_KEYS: frozenset[str] = frozenset({
    "profile", "gpus", "max_parallel", "device",
    "time_budget", "seed", "deterministic", "checkpoint",
    "exploration_mode", "early_stop",
})


def _strip_preset_defaults(raw: dict[str, Any], mode: str) -> dict[str, Any]:
    """save_nn_config 的反向剥离: 写盘前删除"值 == preset 默认"的段。

    用途: load_nn_config 读时会把 preset 默认段塞进返回 dict；save 若直接 yaml.dump
    整个 dict,那些"运行时默认段"就会被落盘到磁盘 yaml（manage_goal.py 调个 goal
    就多 9 个段就是这个机制）。save 前剥掉值==默认的段 → 写盘是极简形态；
    下次 load 又会从 preset 补回相同值 → 行为完全等价。

    规则:
    - 顶层骨架旋钮（_KEEP_TOP_KEYS）无条件保留（人面板, 即使==默认也留）。
    - preset 提供且 raw[k] deep-equal preset[k] → 删（运行时补回相同值）。
    - preset 提供但 raw[k] != preset[k]（手改过）→ 保留。
    - preset 没有的段（scenario/goal/keep/ledger/agent.* 等业务数据）→ 保留。

    失败安全: 解析 mode 或 default_for_mode 失败时原样返回 raw, 不破坏 save。
    """
    try:
        from lib.presets import default_for_mode
        preset = default_for_mode(str(mode or "optimize").strip().lower())
    except Exception:
        return raw

    out: dict[str, Any] = {}
    for k, v in raw.items():
        if k in _KEEP_TOP_KEYS:
            out[k] = v
            continue
        if k in preset and v == preset.get(k):
            # 值 == preset 默认 → 剥离（运行时补回, 行为等价）
            continue
        out[k] = v
    return out


def forward_and_pop_agent_aliases(raw: dict[str, Any]) -> list[str]:
    """把 agent 里仍存的迁移别名 forward 到顶层（agent 值 wins），再 pop。

    返回被 pop 的 old_key 列表。幂等：无别名时空列表。
    """
    from .migrate_goal_schema import STOP_MODE_MAP

    agent = raw.get("agent")
    if not isinstance(agent, dict):
        return []
    popped: list[str] = []
    for old_key, (block, new_key) in AGENT_TO_TOP_KEYS.items():
        if old_key not in agent:
            continue
        top = raw.get(block)
        if not isinstance(top, dict):
            top = {}
            raw[block] = top
        val = agent[old_key]
        if old_key == "goal_stop_mode":
            val = STOP_MODE_MAP.get(val, val)
        top[new_key] = val
        del agent[old_key]
        popped.append(old_key)
    raw["agent"] = agent
    return popped


def load_nn_config(repo_root: Path) -> dict[str, Any]:
    """读 nn-config.yaml；顶层 block 唯一权威（不回填 agent.*）。

    - 文件缺失 → 返回 ``{"agent": {}}``（合法「无全局配置」）。
    - 解析失败或根节点非 mapping → ``RuntimeError``（no-fallback；禁止静默当空配置）。
    - 返回的 dict 含顶层 block + preset 补全；``agent`` 仅保留非迁移键。
    """
    path = Path(repo_root) / "nn-config.yaml"
    if not path.exists():
        return {"agent": {}}
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"nn-config.yaml parse error ({path}): {exc}") from exc
    if loaded is None:
        raw: dict[str, Any] = {}
    elif isinstance(loaded, dict):
        raw = loaded
    else:
        raise RuntimeError(
            f"nn-config.yaml root must be a mapping ({path}); "
            f"got {type(loaded).__name__}"
        )

    raw, _warns = migrate_goal(raw)
    # warnings intentionally suppressed here; load path is silent;
    # CLI writers (manage_goal.py, governance-sync) surface them

    # Preset expansion：exploration_mode 选 bundle（单一权威）；显式 yaml 段 presence-check win
    from lib.presets import default_for_mode
    mode = raw.get("exploration_mode")
    if isinstance(mode, str) and mode.strip():
        preset = default_for_mode(mode.strip().lower())
    else:
        preset = default_for_mode("optimize")   # 缺旋钮给基底（resolve_exploration 才 strict KeyError）

    PRESET_TOP_KEYS = (
        "early_stop", "keep", "reflect", "goal", "external",
        "innovation", "tier_attestation", "gpu", "training", "context",
        "analyse", "compress", "safety",
    )
    for key in PRESET_TOP_KEYS:
        if key not in raw:
            raw[key] = preset.get(key, {})
        else:
            raw[key] = _deep_merge_preset(raw[key], preset.get(key, {}))

    # preset 注入的 goal.scenario_goals 在「下次」migrate_goal 才会写成 per_scenario；
    # 此处预写 v4 别名（不删 v3 键），使首轮 save 已是稳定形，load→save 幂等。
    goal = raw.get("goal")
    if isinstance(goal, dict):
        if "scenario_goals" in goal and "per_scenario" not in goal:
            goal["per_scenario"] = dict(goal["scenario_goals"])

    if "agent" not in raw or not isinstance(raw.get("agent"), dict):
        raw["agent"] = {}

    return raw


def save_nn_config(repo_root: Path, raw: dict[str, Any]) -> None:
    """forward 残留 agent 迁移别名到顶层后 pop，剥离 preset 默认段，再写回 yaml。

    - 若 writer 仍误写 ``agent.reflect_interval`` 等：先顶层化再删别名。
    - 磁盘上不再保留 AGENT_TO_TOP 映射内的 agent 键。
    - 写盘前剥离"值 == preset 默认"的段（load 时会从 preset 补回相同值，行为不变；
      治 manage_goal.py 等 save 路径"调个 goal 就把 9 个默认段写进磁盘"的 bug）。
    - v2.5.4 用户手改持久: ``goal.metric`` / ``goal.op`` 写盘前白名单 + op 合法值校验
      （失败抛 ValueError 阻断）；direction 矛盾仅 warn（运行时也可能修）。
    """
    _validate_goal_user_fields(raw, repo_root)
    forward_and_pop_agent_aliases(raw)
    raw, _warns = migrate_goal(raw)
    mode = str(raw.get("exploration_mode") or "optimize")
    raw = _strip_preset_defaults(raw, mode)

    path = Path(repo_root) / "nn-config.yaml"
    path.write_text(
        yaml.dump(raw, default_flow_style=False, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _validate_goal_user_fields(raw: dict[str, Any], repo_root: Path) -> None:
    """v2.5.4: save 前校验 goal.metric/op 用户手写值（fail-fast）。

    - ``goal.op``: 仅接受 ``>=`` / ``<=``; 其它值抛 ValueError 阻断 save。
    - ``goal.metric``: 必须在 ``contract.metrics.METRIC_KEYS ∪ AUXILIARY_KEYS`` 白名单;
      init 时 METRIC_KEYS 为占位空 dict, 跳过白名单检查(不 NPE); contract 模块不可导入也跳过。
    - direction 一致性(op 与 metric_direction 推出来的 op 一致): 仅 warn, 不阻断
      (业务仓可能在 metric 与 direction 同时迁移过渡期)。

    Raises: ValueError 当 op 非法或 metric 不在白名单。
    """
    goal = raw.get("goal")
    if not isinstance(goal, dict):
        return

    yaml_op = goal.get("op")
    if yaml_op is not None and yaml_op not in (">=", "<="):
        raise ValueError(
            f"goal.op={yaml_op!r} 非法: 仅接受 '>=' 或 '<='。"
            f" 若方向不对, 改 contract.METRIC_KEYS / metric_direction, 不要在 yaml 写 op。"
        )

    yaml_metric = goal.get("metric")
    if yaml_metric is not None:
        try:
            from contract.metrics import AUXILIARY_KEYS, METRIC_KEYS

            whitelist = set(METRIC_KEYS.keys()) | set(AUXILIARY_KEYS.keys())
            # init 时 METRIC_KEYS 为占位 {} -> bool({}) = False -> 跳过(不 NPE)
            if whitelist and yaml_metric not in whitelist:
                raise ValueError(
                    f"goal.metric={yaml_metric!r} 不在 contract 白名单"
                    f" (METRIC_KEYS ∪ AUXILIARY_KEYS)。"
                    f" 若要新增指标, 改 contract.METRIC_KEYS, 不要在 yaml 写 metric。"
                )
        except ImportError:
            # contract 模块不在路径上(init/test 环境), 跳过白名单
            pass

    # direction 一致性软警告
    if yaml_op and yaml_metric:
        try:
            from lib.run_ledger_summary import metric_direction

            d = metric_direction(repo_root)
            expected_op = ">=" if d == "maximize" else "<="
            if yaml_op != expected_op:
                import warnings as _w
                _w.warn(
                    f"goal.op={yaml_op!r} 与 contract.metric_direction={d!r} 矛盾"
                    f" (期望 op={expected_op!r}); 运行时 _goal_metric_op 仍按 yaml,"
                    f" 但 goal_matrix 显示可能不一致。",
                    stacklevel=3,
                )
        except Exception:
            pass
