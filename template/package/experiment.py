"""
ExperimentBase — 实验系统统一基类（模板核心）

一个文件定义全部方法：contract/ 和 workspace/ 分别覆盖不同子集。
框架默认实现（TimeGuard、checkpoint、TSV、preflight、finalize）均在此处。

Agent 读此文件即理解全系统接口；文件夹即权限边界。
"""
from __future__ import annotations

import ast
import csv
import json
import math
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
import random

import numpy as np
import torch
import torch.nn as nn
import yaml


# ═══════════════════════════════════════════════════════════════
# D 档采样器注册表（训练技巧；勿写进 contract/prepare_data）
# ═══════════════════════════════════════════════════════════════
# contract.prepare_data 只锁「读哪个数据集」并返回 DataLoader；
# 「怎么抽 batch」走 cfg["DATA_SAMPLER"] + @register_sampler（workspace 注册）。
# 缺键 = 不改 loader（老仓兼容）；none/uniform = 显式关闭。
SAMPLER_REGISTRY: dict[str, Callable[..., Any]] = {}


def register_sampler(name: str):
    """注册 train DataLoader 采样器构造器：``fn(dataset, cfg) -> Sampler``。"""

    def _decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        SAMPLER_REGISTRY[str(name).lower().strip()] = fn
        return fn

    return _decorator


def rebuild_dataloader_with_sampler(train_loader: Any, sampler: Any) -> Any:
    """用新 sampler 重建 DataLoader，保留 batch_size / workers / collate 等。"""
    from torch.utils.data import DataLoader

    dataset = getattr(train_loader, "dataset", None)
    if dataset is None:
        raise RuntimeError("rebuild_dataloader_with_sampler 需要 train_loader.dataset")
    kwargs: dict[str, Any] = {
        "batch_size": getattr(train_loader, "batch_size", 1),
        "shuffle": False,  # 与 sampler 互斥
        "sampler": sampler,
        "num_workers": getattr(train_loader, "num_workers", 0),
        "collate_fn": getattr(train_loader, "collate_fn", None),
        "pin_memory": bool(getattr(train_loader, "pin_memory", False)),
        "drop_last": bool(getattr(train_loader, "drop_last", False)),
        "timeout": getattr(train_loader, "timeout", 0),
    }
    # 可选属性：旧 torch 可能没有
    for opt_key in ("persistent_workers", "prefetch_factor", "multiprocessing_context"):
        if hasattr(train_loader, opt_key):
            val = getattr(train_loader, opt_key)
            if val is not None:
                kwargs[opt_key] = val
    # persistent_workers 要求 num_workers>0
    if kwargs.get("persistent_workers") and int(kwargs.get("num_workers") or 0) <= 0:
        kwargs.pop("persistent_workers", None)
    return DataLoader(dataset, **kwargs)


# ═══════════════════════════════════════════════════════════════
# TimeGuard
# ═══════════════════════════════════════════════════════════════

class TimeGuard:
    """训练墙钟。budget=0 表示关闭（不限时）；未传时经 ``_resolve_time_budget()``
    解析（yaml 真值；``NN_TIME_BUDGET`` 仅一致性校验，不一致即拒启）。
    ``should_stop`` 在 ``elapsed >= budget`` 时为真（满预算；下一步开始前看表）。"""

    def __init__(self, budget: int | None = None) -> None:
        self._start = time.time()
        b = _resolve_time_budget() if budget is None else budget
        self._budget = int(b)

    def should_stop(self) -> bool:
        if self._budget <= 0:
            return False
        return self.elapsed >= self._budget

    @property
    def elapsed(self) -> float:
        return time.time() - self._start

    @property
    def remaining(self) -> float:
        return max(0.0, self._budget - self.elapsed)


class TimeBudgetStop(BaseException):
    """下一训练更新开始前墙钟已到点。

    必须由本地逐步训练循环接住并走收尾入账；``except Exception`` 接不住
    （避免写成 ``train_exception.txt`` 后跳过成绩表）。
    """


def _optimizer_classes_with_own_step() -> list[type]:
    """``Optimizer`` 子树里自己定义了 ``step`` 的类（Adam / LBFGS 等覆盖了基类）。"""
    import torch.optim as topt

    seen: set[type] = set()
    stack: list[type] = [topt.Optimizer]
    own: list[type] = []
    while stack:
        cls = stack.pop()
        if cls in seen:
            continue
        seen.add(cls)
        try:
            stack.extend(cls.__subclasses__())
        except TypeError:
            pass  # optional: 部分扩展类型无 __subclasses__
        if "step" in cls.__dict__:
            own.append(cls)
    return own


@contextmanager
def guard_optimizer_steps(timer: TimeGuard):
    """在本地逐步训练期间：每次 ``optimizer.step()`` 入口看表，到点抛 ``TimeBudgetStop``。

    只包本次 ``with``；退出即还原，避免泄漏到其它代码。
    """
    originals: dict[type, Any] = {}
    for cls in _optimizer_classes_with_own_step():
        orig = cls.__dict__["step"]
        originals[cls] = orig

        def _make(original: Any) -> Any:
            def wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
                if timer.should_stop():
                    raise TimeBudgetStop()
                return original(self, *args, **kwargs)

            return wrapped

        cls.step = _make(orig)
    try:
        yield
    finally:
        for cls, orig in originals.items():
            cls.step = orig


# ═══════════════════════════════════════════════════════════════
# EarlyStopMonitor — 训内 evaluate 主指标 patience（默认关闭）
# ═══════════════════════════════════════════════════════════════

def resolve_early_stop_patience(
    repo_root: str | os.PathLike | None = None,
    cfg: dict[str, Any] | None = None,
) -> int:
    """``nn-config early_stop.patience`` / ``NN_EARLY_STOP_PATIENCE`` / cfg；0=关闭。"""
    if cfg is not None:
        raw = cfg.get("EARLY_STOP_PATIENCE")
        if raw is not None and str(raw).strip() != "":
            try:
                return max(0, int(raw))
            except (TypeError, ValueError):
                pass  # optional: 非整数 patience，回落到下一来源（env/config）
    env = os.environ.get("NN_EARLY_STOP_PATIENCE", "").strip()
    if env:
        try:
            return max(0, int(env))
        except ValueError:
            pass  # optional: 非整数 env，回落到 nn-config
    root = Path(repo_root).resolve() if repo_root else Path(__file__).resolve().parent
    nn = _load_nn_config(root)
    block = nn.get("early_stop") if isinstance(nn, dict) else None
    if isinstance(block, dict):
        try:
            return max(0, int(block.get("patience", 0)))
        except (TypeError, ValueError):
            pass  # optional: 非整数，回落到默认 0
    return 0


class EarlyStopMonitor:
    """连续 ``patience`` 次 evaluate 无提升则建议停止（仅在有 evaluate 的 epoch 计数）。"""

    def __init__(self, patience: int, direction: str) -> None:
        self.patience = max(0, int(patience))
        self.direction = direction if direction in ("minimize", "maximize") else "maximize"
        self.epochs_without_improve = 0

    @classmethod
    def from_contract(
        cls,
        contract: Any,
        repo_root: str | os.PathLike,
        cfg: dict[str, Any] | None = None,
    ) -> EarlyStopMonitor:
        p = resolve_early_stop_patience(repo_root, cfg)
        direction = getattr(contract, "metric_direction", "maximize")
        return cls(p, direction)

    def after_eval(self, improved: bool) -> bool:
        if self.patience <= 0:
            return False
        if improved:
            self.epochs_without_improve = 0
        else:
            self.epochs_without_improve += 1
        return self.epochs_without_improve >= self.patience

    def should_stop(self) -> bool:
        return self.patience > 0 and self.epochs_without_improve >= self.patience


def eval_improved_for_best(
    current: float,
    best: float,
    direction: str,
    *,
    best_epoch: int,
) -> bool:
    """与训内 ``best_state`` 更新条件一致（首 eval 视为 improved）。

    NaN 防御：F1 E4 设计上 ``workspace.evaluate`` 写 ``test_accuracy=math.nan``
    （训内 evaluate 不算 test，test 只在 ``contract.test`` 算）。当 ``best`` 是 NaN
    时，``current > best`` 永远 False（Python NaN 比较语义）→ KEEP 永远不触发
    → ``best_epoch > 0`` 后所有评估都看起来「没改善」。修复：best 是 NaN 时
    视为不可比，**沿用旧 best**（不更新 best_state），避免假装改进。
    """
    if best_epoch <= 0:
        return True
    if math.isnan(best) or math.isinf(best):
        return False  # 旧 best 无效，沿用，不假装改进
    if math.isnan(current) or math.isinf(current):
        return False  # 当前评估无效，不更新 best
    return _metric_strictly_improved(current, best, direction)


def build_train_done_payload(
    *,
    last_completed_epoch: int,
    epochs_configured: int,
    best_epoch: int,
    stop_reason: str,
    early_stop: EarlyStopMonitor | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "training_loop_finished": True,
        "last_completed_epoch": last_completed_epoch,
        "epochs_configured": epochs_configured,
        "stopped_early": last_completed_epoch < epochs_configured,
        "stop_reason": stop_reason,
        "best_epoch": best_epoch,
    }
    if early_stop is not None and early_stop.patience > 0:
        payload["early_stop_patience"] = early_stop.patience
        payload["epochs_without_improve_at_stop"] = early_stop.epochs_without_improve
    if extra:
        payload.update(extra)
    return payload


def _load_nn_config(repo_root: Path | None = None) -> dict:
    """薄 shim：默认仓根 = 本文件目录；真源一律 ``lib.nn_config.load_nn_config``。

    缺文件 → 空配置；损坏/非 mapping → RuntimeError（no-fallback）。
    """
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent
    from lib.nn_config import load_nn_config

    return load_nn_config(Path(repo_root).resolve())


def _log_time_budget_violation(env_raw: str, yaml_val: int, repo_root: Path | None = None) -> None:
    """追加式违约记录到 ``_runs/time_budget_violations.log``（best-effort，不抛）。

    行格式：时间戳 | pid | ppid | cwd | env 值 | yaml 值 | cmdline。
    同 uid 下 agent 理论上可删本文件——删除本身会在收工审计
    （scripts/check_time_budget_audit.py）的文件存在性报告中露出。
    """
    try:
        if repo_root is None:
            repo_root = Path(__file__).resolve().parent
        runs = Path(repo_root) / "_runs"
        runs.mkdir(parents=True, exist_ok=True)
        try:
            cmdline = " ".join(
                Path("/proc/self/cmdline").read_bytes().decode("utf-8", "replace").split("\0")
            ).strip()
        except OSError:
            cmdline = ""
        line = "\t".join(
            [
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                str(os.getpid()),
                str(os.getppid()),
                str(Path.cwd()),
                env_raw,
                str(yaml_val),
                cmdline,
            ]
        )
        with (runs / "time_budget_violations.log").open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass  # optional: 记录失败不影响主守卫的 RuntimeError 上抛


def _resolve_time_budget(repo_root: Path | None = None) -> int:
    """``time_budget`` 唯一取值点（Config-Only，PROTOCOL §2.3）。

    真值 = ``nn-config.yaml:time_budget``（缺省 3600）。环境变量
    ``NN_TIME_BUDGET`` 仅作一致性校验（编排器从 yaml 解析后 export 的
    派生值应与 yaml 相等）：存在且与 yaml 不一致 → 记违约日志后
    RuntimeError，拒绝启动。改时限请停 batch 后由人/编排器改
    ``nn-config.yaml``（yaml diff 即审计痕迹）。
    """
    cfg = _load_nn_config(repo_root)
    yaml_val = int(cfg.get("time_budget", 3600))
    env_raw = os.environ.get("NN_TIME_BUDGET")
    if env_raw is not None:
        try:
            env_val = int(env_raw)
        except ValueError:
            env_val = None
        if env_val != yaml_val:
            _log_time_budget_violation(env_raw, yaml_val, repo_root)
            raise RuntimeError(
                f"NN_TIME_BUDGET={env_raw} 与 nn-config.yaml time_budget={yaml_val} 不一致："
                "时限已冻结为 Config-Only，会话内改墙钟一律拒绝启动。"
                "改时限请停 batch 后由人/编排器改 nn-config.yaml。"
                "本条已记入 _runs/time_budget_violations.log。"
            )
    return yaml_val


def _update_wall_hit_streak(repo_root: Path, kept: bool) -> None:
    """spec §4.1 + §4.2 撞墙信号注入。

    KEEP 成功 → reset streak = 0
    KEEP 失败（DISCARD） → streak += 1

    T8 ``auto_mode.check_and_promote_auto()`` 读 streak 决定是否升档。
    本函数不抛异常（IO 失败 → 静默 best-effort），不阻塞 KEEP/DISCARD 决策本身。
    """
    try:
        from lib.nn_config import load_nn_config, save_nn_config
        from lib.auto_mode import is_auto_mode
    except ImportError:
        return  # optional: nn_config 未装 → 跳过
    try:
        cfg = load_nn_config(repo_root) or {}
    except Exception as exc:
        import sys as _sys
        print(f"[wall_hit_streak] 读 nn-config 失败: {exc}", file=_sys.stderr)
        return  # optional: 读失败不阻塞
    if not isinstance(cfg, dict):
        cfg = {}
    # 显式档（exploration_mode != auto 且无 auto 段）不追踪 streak、不注入 auto 段——
    # 否则 setdefault 会给显式档凭空造 auto 段，使 check_and_promote_auto 的
    # is_auto_mode 守卫失灵（auto 段存在 → 误判 auto 模式 → 显式档被自动升档）。
    # exploration_mode: auto 首轮（无 auto 段）→ is_auto_mode True（exploration_mode 判定）→ 正常建段追踪。
    if not is_auto_mode(cfg):
        return  # optional: 显式档不追踪撞墙信号
    auto = cfg.setdefault("auto", {})
    if not isinstance(auto, dict):
        auto = {}
        cfg["auto"] = auto
    if kept:
        auto["wall_hit_streak"] = 0
    else:
        auto["wall_hit_streak"] = int(auto.get("wall_hit_streak", 0)) + 1
    cfg["auto"] = auto
    try:
        save_nn_config(repo_root, cfg)
    except Exception as exc:
        import sys as _sys
        print(f"[wall_hit_streak] 写 nn-config 失败: {exc}", file=_sys.stderr)
        return  # optional: 写失败不阻塞决策


def _resolve_deterministic() -> bool:
    """Resolve cuDNN deterministic setting: NN_DETERMINISTIC env > nn-config.yaml > default True."""
    env_val = os.environ.get("NN_DETERMINISTIC", "").strip().lower()
    if env_val in ("0", "false", "no"):
        return False
    if env_val in ("1", "true", "yes"):
        return True
    cfg = _load_nn_config()
    return bool(cfg.get("deterministic", True))


def _ensure_scripts_on_path(repo_root: Path) -> None:
    """使 ``scripts/lib`` 可 import（train.py 直跑时无 PYTHONPATH）。"""
    scripts = repo_root.resolve() / "scripts"
    scripts_s = str(scripts)
    if scripts.is_dir() and scripts_s not in sys.path:
        sys.path.insert(0, scripts_s)


# 模块加载即确保 scripts/lib 可 import（防 _effective_keep_spec 等 lazy lib import
# 早于任何运行期 _ensure 调用 → ModuleNotFoundError: No module named 'lib'）
_ensure_scripts_on_path(Path(__file__).resolve().parent)


# ═══════════════════════════════════════════════════════════════
# Round decision / per-slot keep suggestion（路径契约）
# ═══════════════════════════════════════════════════════════════

ROUND_DECISION_BASENAME = "round_decision.json"
LEGACY_ROUND_DECISION_BASENAME = "evaluation_result.json"
SLOT_KEEP_SUGGESTION_BASENAME = "keep_suggestion.json"
LEGACY_SLOT_KEEP_SUGGESTION_BASENAME = "evaluation_result.json"


def repo_round_decision_path(repo_root: str | os.PathLike) -> Path:
    """仓库级一轮汇总（单槽/多槽均由 ``finalize_round`` 写入）。"""
    return Path(repo_root).resolve() / "_runs" / ROUND_DECISION_BASENAME


def resolve_repo_round_decision_path(runs_dir: str | os.PathLike) -> Path | None:
    """解析非空的 round decision 文件（新名优先，兼容旧名）。"""
    rd = Path(runs_dir).resolve()
    for name in (ROUND_DECISION_BASENAME, LEGACY_ROUND_DECISION_BASENAME):
        p = rd / name
        if p.is_file() and p.stat().st_size > 0:
            return p
    return None


def load_repo_round_decision(runs_dir: str | os.PathLike) -> dict | None:
    p = resolve_repo_round_decision_path(runs_dir)
    if p is None:
        return None  # 文件不存在（轮次未汇总）—— 合法的“无”
    # no-fallback: 文件存在但损坏（JSONDecodeError/OSError）必须报错，不能静默返回 None
    # 掩盖台账损坏。返回 None 仅表示“文件不存在”（上面已处理）。
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"round_decision.json 损坏（{p}）: {exc}") from exc
    return data if isinstance(data, dict) else None


def _write_json_file(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def _to_repo_rel(repo_root: Path | str | None, p: Path | str | None) -> str:
    """把路径相对化为 repo_root 内的相对路径（v2.7.4 存储格式改相对）。

    所有持久化进状态文件（keepers.json / results.tsv / results.jsonl /
    round_decision.json / keep_suggestion.json）的实验地址一律存相对
    ``repo_root`` 的路径（如 ``_runs/exp/<tag>_<name>``）——换机/换用户/
    cp 到 sandbox 后不断链，绝对路径只活在内存（读侧运行时 join repo_root）。

    - p 在 repo_root 内 → 返回相对串（POSIX 风格 ``_runs/exp/...``）
    - p 不在 repo_root 内 / 无法相对化 → 保留原 str（向后兼容 + 跨 repo 场景）
    - p 为空 / repo_root 无法解析 → 返回 ""
    - 幂等：已相对的输入原样返回

    读侧约定：``(repo_root / rel).resolve() if not Path(rel).is_absolute() else Path(rel)``
    """
    if p is None or p == "":
        return ""
    try:
        pp = Path(p)
    except (TypeError, ValueError):
        return str(p)  # optional: Path() 构造失败(怪类型)回退原 str
    if not pp.is_absolute():
        return str(pp)  # 已相对,原样返回(幂等)
    if repo_root is None:
        return str(pp)  # 无 repo_root 锚,保守保留绝对
    try:
        rel = pp.resolve().relative_to(Path(repo_root).resolve())
        return str(rel)
    except (ValueError, OSError):
        return str(pp)  # optional: 跨 repo 路径不在 repo_root 内,保留绝对


def write_repo_round_decision(repo_root: str | os.PathLike, payload: dict) -> Path:
    """写入 ``_runs/round_decision.json`` 并移除同目录下的旧文件名。"""
    out = repo_round_decision_path(repo_root)
    _write_json_file(out, payload)
    legacy = out.parent / LEGACY_ROUND_DECISION_BASENAME
    if legacy.is_file():
        try:
            legacy.unlink()
        except OSError:
            pass  # optional: 旧文件删除失败不阻断写入（best-effort 清理）
    return out


SOURCE_BLOCK_BASENAME = "source_block.json"


def load_source_block(exp_dir):
    """读 agent 在 exp_dir 写的「实现撞墙」sidecar（fork 触发，spec §4 步 2）。

    best-effort：无文件 / 损坏 / 结构错 → None（不阻断 keep 判定）。
    返回归一化 dict：{blocked: bool, cell: str（≤32）, evidence: str（≤2000）}。
    """
    try:
        p = Path(exp_dir) / SOURCE_BLOCK_BASENAME
        if not p.is_file():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None  # optional: best-effort source-block read（无文件/损坏→None）
    if not isinstance(data, dict):
        return None
    return {
        "blocked": bool(data.get("blocked", False)),
        "cell": str(data.get("cell", ""))[:32],
        "evidence": str(data.get("evidence", ""))[:2000],
    }


def merge_source_block(eval_result, exp_dir):
    """把 source_block sidecar 并入单槽评估结果（无则原样返回）。"""
    sb = load_source_block(exp_dir)
    if sb is not None:
        eval_result["source_block"] = sb
    return eval_result


def _collect_round_source_block(exp_dirs):
    """多槽汇总：返回第一个含 blocked source_block 的槽位 sidecar（无则 None）。

    wall-hit 槽通常是 DISCARD（非 keeper），故 finalize_round 须扫所有候选槽。
    """
    for p in exp_dirs:
        sb = load_source_block(p)
        if sb and sb.get("blocked"):
            return sb
    return None


SAVED_KEEPER_BASENAME = "keeper.json"
SAVED_KEEPERS_BASENAME = "keepers.json"
LEGACY_KEEPER_MIGRATED_BASENAME = "keeper.json.migrated"


def saved_keeper_path(repo_root: str | os.PathLike) -> Path:
    """迁后单文件 keeper 指针路径（向后兼容；读写真源见 ``load_keepers``）。"""
    return Path(repo_root).resolve() / "saved" / SAVED_KEEPER_BASENAME


def saved_keepers_path(repo_root: str | os.PathLike) -> Path:
    """分场景 keeper map：``saved/keepers.json``。"""
    return Path(repo_root).resolve() / "saved" / SAVED_KEEPERS_BASENAME


def _keeper_migration_default_scenario_id(repo_root: Path) -> str:
    try:
        from lib.scenario_inventory import focus_scenario_id

        sid = focus_scenario_id(repo_root)
        if sid:
            return sid
    except ImportError:
        pass  # optional: scenario_inventory 未装（最小环境），回落到 nn-config
    nn = _load_nn_config(repo_root)
    agent = nn.get("agent") if isinstance(nn, dict) else None
    if isinstance(agent, dict):
        sid = str(agent.get("scenario_default", "") or "").strip()
        if sid:
            return sid
    return "default"


def _read_keepers_map(path: Path) -> dict[str, dict]:
    if not path.is_file():
        return {}  # 文件不存在（尚无 keeper）—— 合法的“空”
    # no-fallback: keeper 文件存在但损坏必须报错，不能静默丢失 keeper 状态。
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"keepers.json 损坏（{path}）: {exc}") from exc
    if not isinstance(data, dict):
        return {}
    return {str(k): v for k, v in data.items() if isinstance(v, dict)}


def migrate_legacy_keeper_if_needed(
    repo_root: str | os.PathLike,
    default_scenario_id: str,
) -> bool:
    """若存在 ``saved/keeper.json`` 且 keepers map 为空，迁移到 ``keepers[default_scenario_id]``。"""
    root = Path(repo_root).resolve()
    legacy = saved_keeper_path(root)
    if not legacy.is_file():
        return False
    keepers_path = saved_keepers_path(root)
    keepers = _read_keepers_map(keepers_path)
    if keepers:
        return False
    try:
        legacy_data = json.loads(legacy.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        # no-fallback: 损坏的旧 keeper.json 必须报错，不能静默跳过迁移（会丢 keeper）。
        raise RuntimeError(f"legacy keeper.json 损坏（{legacy}）: {exc}") from exc
    if not isinstance(legacy_data, dict):
        return False
    sid = (default_scenario_id or "").strip() or _keeper_migration_default_scenario_id(root)
    entry = dict(legacy_data)
    entry["scenario_id"] = sid
    keepers = {sid: entry}
    keepers_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json_file(keepers_path, keepers)
    migrated = legacy.with_name(LEGACY_KEEPER_MIGRATED_BASENAME)
    legacy.rename(migrated)
    return True


def load_keepers(repo_root: str | os.PathLike) -> dict[str, dict]:
    """读取 ``saved/keepers.json``；必要时自 ``keeper.json`` 迁移。"""
    root = Path(repo_root).resolve()
    default_sid = _keeper_migration_default_scenario_id(root)
    migrate_legacy_keeper_if_needed(root, default_sid)
    return _read_keepers_map(saved_keepers_path(root))


def _experiment_name_from_exp_dir(exp_dir: Path) -> str:
    """从 ``{tag}_s*of*_<experiment>`` 或 ``{tag}_{experiment}`` 解析实验名。"""
    name = exp_dir.name
    m = re.search(r"_s\d+of\d+_(.+)$", name)
    if m:
        return m.group(1)
    parts = name.split("_", 1)
    if len(parts) == 2 and re.match(r"^\d{8}_\d{6}_\d+$", parts[0]):
        return parts[1]
    return name


def write_saved_keeper_pointer(
    repo_root: str | os.PathLike,
    keeper_exp_dir: str | os.PathLike,
    *,
    scenario_id: str,
    experiment: str | None = None,
) -> Path:
    """KEEP 后更新 ``saved/keepers.json`` 中 ``scenario_id`` 对应 entry（不复制 ``best_model.pt``）。"""
    sid = (scenario_id or "").strip()
    if not sid:
        raise ValueError("write_saved_keeper_pointer: scenario_id 不能为空")
    keeper_p = Path(keeper_exp_dir).resolve()
    root = Path(repo_root).resolve()
    ex = (experiment or os.environ.get("NN_EXPERIMENT", "") or "").strip()
    if not ex:
        ex = _experiment_name_from_exp_dir(keeper_p)
    best_p = keeper_p / "best_model.pt"
    payload = {
        "scenario_id": sid,
        "experiment": ex,
        # v2.7.4: 实验地址存相对 repo_root(换机不断链); 读侧 (repo_root/rel).resolve()
        "keeper_exp_dir": _to_repo_rel(root, keeper_p),
        "best_model_path": _to_repo_rel(root, best_p) if best_p.is_file() else "",
        "git_commit": _git_head_short(root),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    keepers = load_keepers(root)
    keepers[sid] = payload
    out = saved_keepers_path(root)
    out.parent.mkdir(parents=True, exist_ok=True)
    _write_json_file(out, keepers)
    print(f"saved_keeper: scenario_id={sid} → {out}", file=sys.stderr, flush=True)
    return out


def _skip_auto_write_keeper() -> bool:
    v = os.environ.get("NN_SKIP_WRITE_KEEPER", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _slot_meta_from_exp_dir(exp_dir: Path) -> dict[str, int]:
    """从 ``…_s{slot}of{total}_…`` 目录名解析槽位；缺省为单槽 0/1。"""
    m = re.search(r"_s(\d+)of(\d+)(?:_|$)", exp_dir.name)
    if m:
        return {"slot": int(m.group(1)), "parallel_total": int(m.group(2))}
    return {"slot": 0, "parallel_total": 1}


# ═══════════════════════════════════════════════════════════════
# Private helpers — checkpoint / TSV / JSONL

_CHECKPOINT_POLICIES = frozenset({"best", "last", "none"})
_PREFLIGHT_EXPERIMENT_NAME = "preflight_check"


def resolve_append_repo_ledger(
    experiment: str | None,
    append_repo_ledger: bool | None = None,
) -> bool:
    """是否向 ``_runs/results.tsv`` / ``results.jsonl`` 追加行。

    - 显式 ``append_repo_ledger=False`` → 不追加（preflight 应用此方式）
    - ``experiment`` 为 ``preflight_check`` 时默认不追加（仍写 ``exp_dir/results.json`` 等）
    - ``NN_PREFLIGHT_LEDGER=1`` 可强制 preflight 也记账（仅调试用）
    """
    if append_repo_ledger is not None:
        return append_repo_ledger
    ex = (experiment or os.environ.get("NN_EXPERIMENT", "")).strip()
    if ex == _PREFLIGHT_EXPERIMENT_NAME:
        force = os.environ.get("NN_PREFLIGHT_LEDGER", "").strip().lower() in (
            "1", "true", "yes", "on",
        )
        if not force:
            return False
    return True


def resolve_checkpoint_policy(
    repo_root: str | os.PathLike | None = None,
    cfg: dict[str, Any] | None = None,
) -> str:
    """``nn-config.yaml`` ``checkpoint`` 或 ``NN_CHECKPOINT``；默认 ``best``。"""
    raw = os.environ.get("NN_CHECKPOINT", "").strip().lower()
    if not raw and isinstance(cfg, dict):
        raw = str(cfg.get("CHECKPOINT_POLICY", "") or "").strip().lower()
    if not raw:
        nn = _load_nn_config(Path(repo_root).resolve() if repo_root else None)
        raw = str(nn.get("checkpoint", "best") or "best").strip().lower()
    if raw not in _CHECKPOINT_POLICIES:
        print(
            f"[checkpoint] 未知 policy={raw!r}，回退 best（可用: best|last|none）",
            file=sys.stderr,
            flush=True,
        )
        raw = "best"
    return raw


def _learner_module(learner: Any) -> Any:
    if learner is None:
        return None
    return learner.module if hasattr(learner, "module") else learner


def apply_checkpoint_policy_to_learner(
    learner: Any,
    *,
    repo_root: str | os.PathLike,
    cfg: dict[str, Any] | None = None,
    best_state: dict[str, Any] | None = None,
    policy: str | None = None,
) -> str:
    """训末 ``contract.test`` 前：按 ``checkpoint`` 策略将权重载入 ``learner``。

    - ``best``：有 ``best_state`` 时 ``load_state_dict(best_state)``，否则保持末轮（last 回退）
    - ``last`` / ``none``：不改 ``learner``（末轮权重）

    Returns:
        ``best_train_eval`` | ``last_epoch`` | ``last_epoch_fallback`` | ``n/a``
    """
    pol = (policy or resolve_checkpoint_policy(repo_root, cfg)).lower()
    if pol == "best" and best_state is not None:
        mod = _learner_module(learner)
        if mod is not None and hasattr(mod, "load_state_dict"):
            mod.load_state_dict(best_state)
            print(
                "[checkpoint] contract.test 使用训内最优权重（policy=best）",
                file=sys.stderr,
                flush=True,
            )
            return "best_train_eval"
        return "last_epoch_fallback"
    if pol == "last":
        return "last_epoch"
    if pol == "best":
        return "last_epoch_fallback"
    return "n/a"


def build_repro_snapshot(contract: Any) -> dict[str, Any]:
    """config.json / env_snapshot.json 用：当次复现关键参数。

    config-only 机制：不再扫描 NN_* 环境变量，直接存储 experiment_config。
    所有实验参数必须通过 --config config.json 传入。
    """
    snap: dict[str, Any] = {}
    try:
        snap["seed_resolved"] = int(contract.seed)
    except (TypeError, ValueError, AttributeError):
        pass  # optional: contract.seed 非整数（动态/未设），省略该快照键
    if torch.cuda.is_available():
        snap["cudnn_deterministic"] = bool(torch.backends.cudnn.deterministic)
        snap["cudnn_benchmark"] = bool(torch.backends.cudnn.benchmark)

    # config-only: 不再扫描 NN_* 环境变量
    # 实验参数统一通过 config.json 传入
    snap["config_only_mode"] = True
    snap["repro_env"] = {}  # 保留空结构以兼容旧格式

    return snap


def json_safe_train_cfg(cfg: dict[str, Any]) -> dict[str, Any]:
    """checkpoint / config.json 用：可 JSON 序列化的完整训练超参（跳过 ``_`` 内部键）。"""
    safe: dict[str, Any] = {}
    for k, v in sorted(cfg.items()):
        if str(k).startswith("_"):
            continue
        if isinstance(v, Path):
            safe[k] = str(v)
            continue
        try:
            json.dumps(v)
            safe[k] = v
        except (TypeError, ValueError):
            safe[k] = str(v)  # optional: 不可 JSON 序列化 → 转字符串（确定性回退，非吞错）
    return safe


def _state_dict_cpu(state: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in state.items():
        if hasattr(v, "detach"):
            out[k] = v.detach().cpu()
        else:
            out[k] = v
    return out
# ═══════════════════════════════════════════════════════════════

def _git_head_short(repo_root: Path) -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root, capture_output=True, text=True, timeout=8,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass  # optional: 非 git 仓库 / git 不可用 / 超时 → "nogit"
    return "nogit"


def _read_tsv_header(path: Path) -> list[str] | None:
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as f:
        line = f.readline()
    line = line.lstrip("﻿")
    if not line.strip():
        return None
    return line.rstrip("\n").split("\t")


def _escape_tsv_field(s: str) -> str:
    return s.replace("\t", " ").replace("\r", " ").replace("\n", " ")


def _format_metric_cell(v: Any) -> str:
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return ""
        return f"{v:.6f}"
    if v is None:
        return ""
    return str(v)


_NOTES_CELL_SEP = " || "


def _resolve_notes_human(notes: str | None = None) -> str:
    if notes is not None:
        return notes.strip()
    return os.environ.get("NN_NOTES", "").strip()


def _known_ledger_metric_keys(contract: Any) -> set[str]:
    return (
        set(contract.metric_keys.keys())
        | set(contract.auxiliary_keys.keys())
        | set(contract.ledger_context_keys)
    )


# ═══════════════════════════════════════════════════════════════
# Agent 场景清单（结构化传递给 Agent / 可选 env 绑定）
# ═══════════════════════════════════════════════════════════════

ScenarioParserFn = Callable[[str], dict[str, Any]]


def parse_scenario_sip_value(scenario_id: str) -> float | None:
    """内置 parser ``sip``：``1sip`` / ``2p5sip`` → 数值（供 PINN N_SIP 等复用）。"""
    parsed = _scenario_parser_sip(scenario_id)
    val = parsed.get("numeric")
    return float(val) if val is not None else None


def _scenario_parser_literal(scenario_id: str) -> dict[str, Any]:
    s = (scenario_id or "").strip()
    return {"value": s, "scenario_id": s}


def _scenario_parser_sip(scenario_id: str) -> dict[str, Any]:
    s = (scenario_id or "").strip().lower()
    out: dict[str, Any] = {"scenario_id": (scenario_id or "").strip()}
    if not s:
        return out
    body = s[:-3] if s.endswith("sip") else s
    body = body.strip()
    if not body:
        return out
    if "p" in body and "." not in body:
        body = body.replace("p", ".", 1)
    try:
        out["numeric"] = float(body)
    except ValueError:
        pass  # optional: 非数值 scenario_id，保留字符串 value
    return out


def _scenario_parser_float(scenario_id: str) -> dict[str, Any]:
    s = (scenario_id or "").strip()
    out: dict[str, Any] = {"scenario_id": s, "value": s}
    try:
        out["numeric"] = float(s)
    except ValueError:
        pass  # optional: 非数值 scenario_id，保留字符串 value
    return out


def _scenario_parser_int(scenario_id: str) -> dict[str, Any]:
    s = (scenario_id or "").strip()
    out: dict[str, Any] = {"scenario_id": s, "value": s}
    try:
        out["numeric"] = int(float(s))
    except ValueError:
        pass  # optional: 非数值 scenario_id，保留字符串 value
    return out


_SCENARIO_PARSERS: dict[str, ScenarioParserFn] = {
    "literal": _scenario_parser_literal,
    "sip": _scenario_parser_sip,
    "float": _scenario_parser_float,
    "int": _scenario_parser_int,
}


def run_scenario_parser(parser: str, scenario_id: str) -> dict[str, Any]:
    fn = _SCENARIO_PARSERS.get((parser or "literal").strip().lower())
    if fn is None:
        raise ValueError(f"未知 scenario parser: {parser!r}；可用: {', '.join(sorted(_SCENARIO_PARSERS))}")
    return fn(scenario_id)


def _split_scenario_active_list(raw: str) -> list[str]:
    if not raw.strip():
        return []
    parts = re.split(r"[,;\s]+", raw.strip())
    return [p.strip() for p in parts if p.strip()]


def _format_env_binding_value(val: Any) -> str:
    if isinstance(val, bool):
        return "1" if val else "0"
    if isinstance(val, float) and val == int(val):
        return str(int(val))
    return str(val)


def _normalize_scenario_binding(spec: Any) -> dict[str, Any]:
    from lib.scenario_bindings import normalize_scenario_binding

    return normalize_scenario_binding(spec)


def _resolve_scenario_bindings(agent: dict[str, Any], contract: Any | None) -> list[dict[str, Any]]:
    raw = agent.get("scenario_bindings")
    if isinstance(raw, list) and raw:
        return [_normalize_scenario_binding(x) for x in raw]
    if contract is not None:
        cb = getattr(contract, "agent_scenario_bindings", None)
        if callable(cb):
            cb = cb()
        if cb:
            return [_normalize_scenario_binding(x) for x in cb]
    return []


def _load_agent_section(repo_root: str | os.PathLike | None = None) -> dict[str, Any]:
    root = Path(repo_root).resolve() if repo_root is not None else None
    cfg = _load_nn_config(root)
    agent = cfg.get("agent")
    return agent if isinstance(agent, dict) else {}


@dataclass
class AgentScenarioManifest:
    """结构化优化/场景目标，供 Agent prompt 与 train 日志共用。"""

    axis: str = ""
    policy: str = ""
    default_id: str = ""
    active_ids: list[str] | None = None
    ledger_context_keys: tuple[str, ...] = ()
    exploration: str = ""
    env_applied: dict[str, str] | None = None
    env_skipped: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "axis": self.axis,
            "policy": self.policy,
            "default_id": self.default_id,
            "active_ids": list(self.active_ids or []),
            "ledger_context_keys": list(self.ledger_context_keys),
            "exploration": self.exploration,
            "env_applied": dict(self.env_applied or {}),
            "env_skipped": dict(self.env_skipped or {}),
        }


def build_agent_scenario_manifest(
    repo_root: str | os.PathLike,
    *,
    contract: Any | None = None,
    apply_env: bool = False,
) -> AgentScenarioManifest:
    """从 nn-config ``agent`` 段 + 可选 contract 组装场景清单（不修改环境，除非 ``apply_env=True``）。"""
    agent = _load_agent_section(repo_root)
    axis = str(agent.get("scenario_axis", "") or "").strip()
    policy = str(agent.get("scenario_policy", "") or "").strip()
    default_id = str(agent.get("scenario_default", "") or "").strip()
    active_raw = str(agent.get("scenario_active", "") or "").strip()
    active_ids = _split_scenario_active_list(active_raw)
    # exploration_mode(6档) → run-context 显示 mode + tier_start（缺旋钮不崩）
    from lib.experiment_mode import resolve_exploration

    try:
        _res = resolve_exploration(repo_root)
        exploration = f"{_res.mode} (tier_start={_res.tier_start})"
    except KeyError:
        exploration = ""
    ledger: tuple[str, ...] = ()
    if contract is not None:
        ledger = tuple(getattr(contract, "ledger_context_keys", ()) or ())

    env_applied: dict[str, str] = {}
    env_skipped: dict[str, str] = {}
    if apply_env and default_id:
        bindings = _resolve_scenario_bindings(agent, contract)
        for b in bindings:
            if b.get("from", "default") != "default":
                continue
            env_var = b["env_var"]
            if b.get("skip_if_set", True) and os.environ.get(env_var, "").strip():
                env_skipped[env_var] = "already_set"
                continue
            parsed = run_scenario_parser(b["parser"], default_id)
            val = parsed.get(b["value_key"])
            if val is None or val == "":
                env_skipped[env_var] = f"parser {b['parser']!r} 无 {b['value_key']!r}"
                continue
            os.environ[env_var] = _format_env_binding_value(val)
            env_applied[env_var] = os.environ[env_var]

    return AgentScenarioManifest(
        axis=axis,
        policy=policy,
        default_id=default_id,
        active_ids=active_ids,
        ledger_context_keys=ledger,
        exploration=exploration,
        env_applied=env_applied,
        env_skipped=env_skipped,
    )


def format_agent_scenario_prompt_block(manifest: AgentScenarioManifest | dict[str, Any]) -> str:
    """Markdown 片段，注入 auto-run / 人工 prompt。"""
    if isinstance(manifest, AgentScenarioManifest):
        d = manifest.to_dict()
    else:
        d = dict(manifest)
    lines = ["**Agent scenario manifest (structured):**"]
    if d.get("axis"):
        lines.append(f"- axis: {d['axis']}")
    if d.get("policy"):
        lines.append(f"- policy: {d['policy']}")
    if d.get("default_id"):
        lines.append(f"- default: {d['default_id']}")
    active = d.get("active_ids") or []
    if active:
        lines.append(f"- active: {', '.join(active)}")
    ledger = d.get("ledger_context_keys") or []
    if ledger:
        lines.append(f"- ledger_context_keys: {', '.join(ledger)}")
    if d.get("exploration"):
        lines.append(f"- exploration: {d['exploration']}")
    applied = d.get("env_applied") or {}
    if applied:
        lines.append("- env_applied: " + "; ".join(f"{k}={v}" for k, v in applied.items()))
    skipped = d.get("env_skipped") or {}
    if skipped:
        lines.append("- env_skipped: " + "; ".join(f"{k}={v}" for k, v in skipped.items()))
    if len(lines) <= 1:
        return ""
    return "\n".join(lines)


def apply_agent_scenario_env(
    repo_root: str | os.PathLike,
    *,
    contract: Any | None = None,
) -> dict[str, str]:
    """应用 ``scenario_bindings`` → 环境变量，并返回扁平摘要（兼容旧日志格式）。

    绑定来源（优先级）：``nn-config.agent.scenario_bindings`` > ``contract.agent_scenario_bindings``。
    结构化全文请用 ``build_agent_scenario_manifest(..., apply_env=True)``。
    """
    manifest = build_agent_scenario_manifest(repo_root, contract=contract, apply_env=True)
    out: dict[str, str] = {}
    if manifest.default_id:
        out["scenario_default"] = manifest.default_id
    if manifest.policy:
        out["scenario_policy"] = manifest.policy
    if manifest.active_ids:
        out["scenario_active"] = ",".join(manifest.active_ids)
    if manifest.axis:
        out["scenario_axis"] = manifest.axis
    out.update(manifest.env_applied or {})
    return out


SCENARIO_ID_COLUMN = "scenario_id"


def _extract_scenario_tsv(contract: Any, cfg: dict[str, Any] | None) -> dict[str, Any]:
    if not cfg:
        return {}
    for key in (SCENARIO_ID_COLUMN, "SCENARIO_ID"):
        if key in cfg and cfg[key] not in (None, ""):
            return {SCENARIO_ID_COLUMN: cfg[key]}
    return {}


def _resolve_validated_scenario_context(
    repo_root: str | os.PathLike,
    cfg: dict[str, Any] | None = None,
    contract: Any | None = None,
) -> dict[str, Any]:
    """解析并校验 scenario_id（须 ∈ F1 场景清单），供台账写入与 preflight 共用。"""
    root = Path(repo_root).resolve()
    _ensure_scripts_on_path(root)
    try:
        from lib.scenario_inventory import resolve_scenario_id, validate_scenario_id

        agent = _load_agent_section(root)
        bindings = _resolve_scenario_bindings(agent, contract)
        sid, _ = resolve_scenario_id(root, cfg, scenario_bindings=bindings or None)
        validate_scenario_id(root, sid)
        return {SCENARIO_ID_COLUMN: sid}
    except ImportError:
        ctx = _extract_scenario_tsv(None, cfg)
        sid = str(ctx.get(SCENARIO_ID_COLUMN, "") or "").strip()
        if not sid:
            raise ValueError("scenario_id 为空") from None
        return {SCENARIO_ID_COLUMN: sid}


def resolve_cfg_for_ledger_key(cfg: dict[str, Any], key: str) -> Any | None:
    """按 ``ledger_context_keys`` 名从 ``cfg`` 取值：先精确匹配，再大小写不敏感。

    TSV 列名以 contract 声明为准；``train.py``/``build_cfg()`` 常用大写 env 键，
    迁移 E7 若写成小写仍可读入。
    """
    if not cfg or not key:
        return None
    if key in cfg:
        val = cfg[key]
        return None if val is None else val
    key_lower = key.lower()
    for k, v in cfg.items():
        if not isinstance(k, str) or k.startswith("_"):
            continue
        if k.lower() == key_lower:
            return None if v is None else v
    return None


# 台账观察列：finalize 由 exploration_stamp 写入；不从 cfg 取值
_LEDGER_OVERLAY_KEYS = frozenset({"exploration_space", "untrained"})


def _extract_ledger_context(contract: Any, cfg: dict[str, Any] | None) -> dict[str, Any]:
    if not cfg or not contract.ledger_context_keys:
        return {}
    out: dict[str, Any] = {}
    for key in contract.ledger_context_keys:
        if key in _LEDGER_OVERLAY_KEYS:
            continue
        val = resolve_cfg_for_ledger_key(cfg, key)
        if val is None:
            continue
        if isinstance(val, (str, int, float, bool)):
            out[key] = val
        else:
            out[key] = str(val)
    return out


def _resolve_cfg_for_ledger(exp_dir: Path, results_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """合并 ``exp_dir/config.json`` 与 ``results.json`` 的 ``cfg``/``train_cfg``（后者覆盖同名键）。"""
    cfg: dict[str, Any] = {}
    config_path = Path(exp_dir) / "config.json"
    if config_path.is_file():
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                cfg = {
                    k: v
                    for k, v in raw.items()
                    if isinstance(k, str) and not k.startswith("_")
                }
        except (OSError, json.JSONDecodeError):
            pass  # optional: 台账 cfg 合并是描述性元数据；results.json 的 cfg 仍会兜底
    payload = results_payload if isinstance(results_payload, dict) else {}
    for key in ("cfg", "train_cfg"):
        block = payload.get(key)
        if isinstance(block, dict):
            cfg.update(block)
    return cfg


def _load_jsonl_exp_dir_set(repo_root: Path) -> set[str]:
    """已入账 exp_dir 集合（finalize 幂等跳过用）。

    缺 ``results.jsonl`` → 空集（``load_jsonl_exp_dirs`` 已处理）。
    缺 lib → 硬失败（不可静默当成「无人账」，否则会重复入账）。
    """
    try:
        from lib.round_ledger_closure import load_jsonl_exp_dirs
    except ImportError as exc:
        raise RuntimeError(
            "缺 scripts/lib/round_ledger_closure.py（请 governance-sync / auto-nn-update）",
        ) from exc
    return set(load_jsonl_exp_dirs(repo_root / "_runs" / "results.jsonl", repo_root))


def _build_notes_overflow(metrics: dict[str, Any], contract: Any) -> str:
    known = _known_ledger_metric_keys(contract)
    verbose = os.environ.get("NN_NOTES_VERBOSE", "").strip().lower() in ("1", "true", "yes", "on")
    parts: list[str] = []
    for k in sorted(metrics.keys()):
        if k in known:
            continue
        v = metrics[k]
        if not isinstance(v, (int, float)):
            if verbose:
                print(f"[notes] 跳过非数值溢出键 {k!r}", file=sys.stderr, flush=True)
            continue
        cell = _format_metric_cell(v)
        if not cell:
            continue
        parts.append(f"{k}={cell}")
    return "; ".join(parts)


def _build_notes_cell(human: str, metrics: dict[str, Any], contract: Any) -> str:
    human_esc = _escape_tsv_field(human)
    overflow = _build_notes_overflow(metrics, contract)
    segments = [s for s in (human_esc, overflow) if s]
    return _NOTES_CELL_SEP.join(segments)


def _append_results_tsv_enabled() -> bool:
    v = os.environ.get("NN_APPEND_RESULTS_TSV", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _append_results_jsonl_enabled() -> bool:
    v = os.environ.get("NN_APPEND_RESULTS_JSONL", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _repo_ledger_sync_mode() -> str:
    """仓库级 TSV/JSONL 须同事务：``both`` 都写、``skip`` 都不写、``mismatch`` 均不写（stderr 警告）。"""
    t = _append_results_tsv_enabled()
    j = _append_results_jsonl_enabled()
    if t and j:
        return "both"
    if not t and not j:
        return "skip"
    return "mismatch"


def _clean_metrics_dict(metrics: dict[str, Any]) -> dict[str, object]:
    clean: dict[str, object] = {}
    for k, v in sorted(metrics.items()):
        if isinstance(v, float):
            if math.isnan(v) or math.isinf(v):
                continue
            clean[k] = round(v, 6)
        else:
            clean[k] = v
    return clean


def _upgrade_tsv_add_exp_dir_column(path: Path) -> None:
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    if not lines:
        return
    header = lines[0].lstrip("﻿").split("\t")
    if "exp_dir" in header:
        return
    insert_pos = (
        header.index("description")
        if "description" in header
        else (header.index("git_commit") + 1 if "git_commit" in header else len(header))
    )
    new_header = header[:insert_pos] + ["exp_dir"] + header[insert_pos:]
    out_lines = ["\t".join(new_header)]
    for line in lines[1:]:
        cells = line.split("\t")
        while len(cells) < len(header):
            cells.append("")
        cells = cells[: len(header)]
        new_cells = cells[:insert_pos] + [""] + cells[insert_pos:]
        out_lines.append("\t".join(new_cells))
    path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


def _upgrade_tsv_add_exploration_space_column(path: Path) -> None:
    """旧表头缺 exploration_space 时补列：插在 parameters 区末、elapsed_sec 前。"""
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    if not lines:
        return
    header = lines[0].lstrip("﻿").split("\t")
    if "exploration_space" in header:
        return
    if "elapsed_sec" in header:
        insert_pos = header.index("elapsed_sec")
    elif "description" in header:
        insert_pos = header.index("description")
    else:
        insert_pos = len(header)
    new_header = header[:insert_pos] + ["exploration_space"] + header[insert_pos:]
    out_lines = ["\t".join(new_header)]
    for line in lines[1:]:
        cells = line.split("\t")
        while len(cells) < len(header):
            cells.append("")
        cells = cells[: len(header)]
        new_cells = cells[:insert_pos] + [""] + cells[insert_pos:]
        out_lines.append("\t".join(new_cells))
    path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


def _upgrade_tsv_add_untrained_column(path: Path) -> None:
    """旧表头缺 untrained 时补列：插在 exploration_space 后，否则 parameters 区末、elapsed_sec 前。"""
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    if not lines:
        return
    header = lines[0].lstrip("﻿").split("\t")
    if "untrained" in header:
        return
    if "exploration_space" in header:
        insert_pos = header.index("exploration_space") + 1
    elif "elapsed_sec" in header:
        insert_pos = header.index("elapsed_sec")
    elif "description" in header:
        insert_pos = header.index("description")
    else:
        insert_pos = len(header)
    new_header = header[:insert_pos] + ["untrained"] + header[insert_pos:]
    out_lines = ["\t".join(new_header)]
    for line in lines[1:]:
        cells = line.split("\t")
        while len(cells) < len(header):
            cells.append("")
        cells = cells[: len(header)]
        new_cells = cells[:insert_pos] + [""] + cells[insert_pos:]
        out_lines.append("\t".join(new_cells))
    path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


def _upgrade_tsv_add_timestamp_column(path: Path) -> None:
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    if not lines:
        return
    header = lines[0].lstrip("﻿").split("\t")
    if "timestamp" in header:
        return
    new_header = header + ["timestamp"]
    out_lines = ["\t".join(new_header)]
    for line in lines[1:]:
        cells = line.split("\t")
        while len(cells) < len(header):
            cells.append("")
        cells = cells[: len(header)] + [""]
        out_lines.append("\t".join(cells))
    path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


def _ensure_tsv_elapsed_sec(path: Path) -> None:
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    if not lines:
        return
    header = lines[0].lstrip("﻿").split("\t")
    if "elapsed_sec" in header:
        return
    insert_pos = header.index("val_accuracy") + 1 if "val_accuracy" in header else 1
    new_header = header[:insert_pos] + ["elapsed_sec"] + header[insert_pos:]
    out_lines = ["\t".join(new_header)]
    for line in lines[1:]:
        cells = line.split("\t")
        while len(cells) < len(header):
            cells.append("")
        cells = cells[: len(header)]
        new_cells = cells[:insert_pos] + [""] + cells[insert_pos:]
        out_lines.append("\t".join(new_cells))
    path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


def _upgrade_tsv_add_notes_column(path: Path) -> None:
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    if not lines:
        return
    header = lines[0].lstrip("﻿").split("\t")
    if "notes" in header:
        return
    if "timestamp" in header:
        insert_pos = header.index("timestamp")
    elif "description" in header:
        insert_pos = header.index("description") + 1
    else:
        insert_pos = len(header)
    new_header = header[:insert_pos] + ["notes"] + header[insert_pos:]
    out_lines = ["\t".join(new_header)]
    for line in lines[1:]:
        cells = line.split("\t")
        while len(cells) < len(header):
            cells.append("")
        cells = cells[: len(header)]
        new_cells = cells[:insert_pos] + [""] + cells[insert_pos:]
        out_lines.append("\t".join(new_cells))
    path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


# ═══════════════════════════════════════════════════════════════
# Private helpers — evaluation / should_keep
# ═══════════════════════════════════════════════════════════════

def _load_results_json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"缺少 {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_tsv_rows(tsv_path: Path) -> list[dict[str, str]]:
    if not tsv_path.is_file():
        return []
    with open(tsv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        return list(reader)


def _float_metric(row: dict[str, str], key: str) -> float | None:
    if key not in row:
        return None
    raw = row[key].strip()
    if raw == "" or raw.lower() == "none":
        return None
    try:
        return float(raw)
    except ValueError:
        return None  # optional: TSV 单元格非数值（占位/空）→ None，由调用方判 None 跳过


def _history_best_metric(
    history: list[dict[str, str]], metric_key: str, direction: str,
) -> float | None:
    vals: list[float] = []
    for row in history:
        v = _float_metric(row, metric_key)
        if v is not None and not math.isnan(v):
            vals.append(v)
    if not vals:
        return None
    return max(vals) if direction == "maximize" else min(vals)


def _primary_improved(
    current: float, best_hist: float, *, delta: float, mode: str, direction: str,
) -> bool:
    if mode == "relative":
        denom = max(abs(best_hist), 1e-12)
        if direction == "maximize":
            return (current - best_hist) / denom >= delta
        return (best_hist - current) / denom >= delta
    if direction == "maximize":
        return (current - best_hist) >= delta
    return (best_hist - current) >= delta


def _metric_strictly_improved(current: float, best: float, direction: str) -> bool:
    """相对历史最佳是否有**严格**改善（用于 improve_mode=any_metric，不要求 primary_delta）。"""
    eps = 1e-12
    if direction == "maximize":
        return current > best + eps
    return current < best - eps


def _metric_near_best(current: float, best: float, direction: str, tol: float) -> bool:
    """在 ``near_best_abs`` 容差内视为接近历史最佳（**与 TSV 量纲一致**：如百分制 0–100 则 tol=0.5≈0.5pp；若为 0–1 小数则 tol=0.005≈0.5pp）。"""
    if tol <= 0.0:
        return False
    if direction == "maximize":
        return current >= best - tol
    return current <= best + tol


def _check_aux_guards(
    current: dict[str, float],
    prev: dict[str, float] | None,
    guards: dict,
    aux_metrics: dict,
) -> tuple[bool, dict]:
    checks: dict = {}
    if not prev or not guards:
        return True, checks
    for aux_key, guard in guards.items():
        if aux_key not in current or aux_key not in prev:
            checks[aux_key] = {"skipped": True, "guard_passed": True}
            continue
        c, p = float(current[aux_key]), float(prev[aux_key])
        direction = aux_metrics.get(aux_key, "maximize")
        passed = True
        detail: dict = {"value": c}
        ratio = c / (abs(p) + 1e-30)
        detail["ratio_vs_prev"] = ratio

        if "min_ratio_vs_prev" in guard:
            need = float(guard["min_ratio_vs_prev"])
            if direction == "maximize":
                passed = ratio >= need
            else:
                passed = ratio <= (1.0 / max(need, 1e-12))

        if "max_ratio_vs_prev" in guard:
            max_r = float(guard["max_ratio_vs_prev"])
            passed = ratio <= max_r

        detail["guard_passed"] = passed
        checks[aux_key] = detail
        if not passed:
            return False, checks
    return True, checks


def allocate_exp_dir(
    repo_root: str | Path,
    experiment: str,
    *,
    tag: str | None = None,
    slot: int | None = None,
    parallel_total: int | None = None,
) -> Path:
    """分配官方实验产物目录：``<repo>/_runs/exp/{tag}_{experiment}/``（须由 train.py 使用）。"""
    root = Path(repo_root).resolve()
    exp_name = (experiment or "").strip() or "run"
    if tag is None:
        if slot is not None and parallel_total is not None:
            tag = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{os.getpid()}_s{slot}of{parallel_total}"
        else:
            tag = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{os.getpid()}"
    path = root / "_runs" / "exp" / f"{tag}_{exp_name}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _resolve_history_tsv_path(exp_dir: Path) -> Path:
    """解析 ``should_keep`` 用的历史台账 TSV（``_runs/results.tsv`` 布局）。"""
    exp_dir = exp_dir.resolve()
    if exp_dir.parent.name == "exp" and exp_dir.parent.parent.name == "_runs":
        return exp_dir.parent.parent / "results.tsv"
    legacy = exp_dir.parent.parent / "_runs" / "results.tsv"
    if legacy.is_file():
        return legacy
    return exp_dir.parent.parent / "results.tsv"


def _resolve_repo_root(exp_dir: Path) -> Path:
    exp_dir = exp_dir.resolve()
    if exp_dir.parent.name == "exp" and exp_dir.parent.parent.name == "_runs":
        return exp_dir.parent.parent.parent
    if exp_dir.parent.name == "exp":
        return exp_dir.parent.parent
    return exp_dir


# ═══════════════════════════════════════════════════════════════
# Private helpers — preflight
# ═══════════════════════════════════════════════════════════════

def _env_enabled(name: str, *, default: str = "1") -> bool:
    v = os.environ.get(name, default).strip().lower()
    return v not in ("0", "false", "no", "off")


def _static_guards_enabled() -> bool:
    return _env_enabled("NN_PREFLIGHT", default="1")


def _guard_encapsulation_enabled() -> bool:
    return _static_guards_enabled() and _env_enabled("NN_GUARD_ENCAPSULATION", default="1")


def _guard_contract_diff_enabled() -> bool:
    return _static_guards_enabled() and _env_enabled("NN_GUARD_CONTRACT_DIFF", default="1")


def _guard_experiment_diff_enabled() -> bool:
    return _static_guards_enabled() and _env_enabled("NN_GUARD_EXPERIMENT_DIFF", default="1")


def _guard_governance_docs_enabled() -> bool:
    return _static_guards_enabled() and _env_enabled("NN_GUARD_GOVERNANCE_DOCS", default="1")


def _guard_profile_enabled() -> bool:
    return _static_guards_enabled() and _env_enabled("NN_GUARD_PROFILE", default="1")


def _guard_root_py_enabled() -> bool:
    return _static_guards_enabled() and _env_enabled("NN_GUARD_ROOT_PY", default="1")


def _guard_test_authority_enabled() -> bool:
    return _static_guards_enabled() and _env_enabled("NN_GUARD_TEST_AUTHORITY", default="1")


def _guard_contract_layout_enabled() -> bool:
    return _static_guards_enabled() and _env_enabled("NN_GUARD_CONTRACT_LAYOUT", default="1")


def _guard_tsv_header_enabled() -> bool:
    return _static_guards_enabled() and _env_enabled("NN_GUARD_TSV_HEADER", default="1")


def _guard_scenario_id_enabled() -> bool:
    return _static_guards_enabled() and _env_enabled("NN_GUARD_SCENARIO_ID", default="1")


def _guard_exp_dir_enabled() -> bool:
    return _static_guards_enabled() and _env_enabled("NN_GUARD_EXP_DIR", default="1")


def _guard_profile_facade_enabled() -> bool:
    return _static_guards_enabled() and _env_enabled("NN_GUARD_PROFILE_FACADE", default="1")


_ROOT_PY_DEFAULT_ALLOWLIST = frozenset({"train.py", "experiment.py", "reflect.py"})


def _root_py_allowlist() -> frozenset[str]:
    names = set(_ROOT_PY_DEFAULT_ALLOWLIST)
    extra = os.environ.get("NN_ROOT_PY_ALLOWLIST", "").strip()
    if extra:
        names.update(x.strip() for x in extra.split(",") if x.strip())
    return frozenset(names)


def _relaunch_declared() -> bool:
    return bool(os.environ.get("NN_RELAUNCH", "").strip())


def _run_optional_subprocess(
    args: list[str], cwd: Path | str
) -> subprocess.CompletedProcess[str] | None:
    """跑一条外部命令（git / grep / python scanner）；命令缺失或进程异常 → 返回 None。

    optional 契约的单一声明点：所有「命令可能不在环境里、失败就当 optional 跳过」的
    subprocess 探测都走这里，`# optional:` 只在此写一次；调用方据 None 给各自的空默认
    （False / [] / 直接 return）。集中声明根除「每处各写 try/except、各标一次 optional →
    漏标」的重复模式（scan_no_fallback 从此只看到这一处，且已豁免）。
    """
    try:
        return subprocess.run(
            args, cwd=str(cwd), capture_output=True, text=True, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None  # optional: 命令缺失/进程异常 → 调用方走 optional 空默认


def _git_has_committed_diff(repo_root: Path, pathspec: str) -> bool:
    """HEAD 相对 HEAD~1 在 pathspec 下是否有已提交 diff（无 git 或仅一次提交则 False）。"""
    r = _run_optional_subprocess(["git", "rev-parse", "--verify", "HEAD~1"], repo_root)
    if r is None or r.returncode != 0:
        return False
    diff = _run_optional_subprocess(["git", "diff", "HEAD~1", "--", pathspec], repo_root)
    if diff is None or diff.returncode != 0:
        return False
    return bool((diff.stdout or "").strip())


def _git_changed_paths(repo_root: Path, pathspecs: list[str] | tuple[str, ...]) -> list[str]:
    """working tree ∪ staged ∪ HEAD~1..HEAD 中匹配 pathspecs 的相对路径。"""
    root = Path(repo_root)
    names: set[str] = set()
    for args in (
        ["git", "diff", "--name-only"],
        ["git", "diff", "--cached", "--name-only"],
        ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
    ):
        r = _run_optional_subprocess(args, root)
        if r is None or r.returncode != 0:
            continue
        for line in (r.stdout or "").splitlines():
            p = line.strip()
            if p:
                names.add(p)

    def _match(path: str) -> bool:
        for spec in pathspecs:
            if spec.endswith("/"):
                if path == spec.rstrip("/") or path.startswith(spec):
                    return True
            elif path == spec or path.startswith(spec.rstrip("/") + "/"):
                return True
        return False

    return sorted(p for p in names if _match(p))


def _check_train_encapsulation(train_py_path: str | Path) -> list[dict]:
    """G-封装: train.py 不得直接 import workspace 子模块（与 init comparator 同规则）。"""
    path = Path(train_py_path)
    if not path.exists():
        return []

    code = path.read_text(encoding="utf-8")
    violations: list[dict] = []

    for m in re.finditer(r"([^\n]*)", code):
        line = m.group(0)
        line_no = code[: m.start()].count("\n") + 1

        frm = re.search(r"from\s+workspace\.(\w+)\s+import", line)
        if frm and frm.group(1) != "__init__":
            violations.append({
                "line": line_no,
                "text": line.strip(),
                "module": frm.group(1),
                "rule": "train.py 不得直接 import workspace 子模块",
                "fix": "通过 ws 的公开方法调用（build_learner / train_step / evaluate 等）",
            })
            continue

        imp = re.search(r"import\s+workspace\.(\w+)", line)
        if imp and imp.group(1) != "__init__":
            violations.append({
                "line": line_no,
                "text": line.strip(),
                "module": imp.group(1),
                "rule": "train.py 不得 import workspace 子模块",
                "fix": "通过 ws 的公开方法调用",
            })

    return violations


def check_train_encapsulation(repo_root: str | Path) -> list[dict]:
    """G-封装：train.py 不得直接 import workspace 子模块（nn-doctor / migration 静态扫描）。"""
    return _check_train_encapsulation(Path(repo_root).resolve() / "train.py")


def _guard_train_encapsulation(repo_root: Path) -> None:
    if not _guard_encapsulation_enabled():
        return
    violations = _check_train_encapsulation(repo_root / "train.py")
    if not violations:
        return
    lines = [
        "[Pre-flight] train.py 封装违规（G-封装）：不得直接 import workspace 子模块。",
        "修复：只通过 ws.<方法> 调用；或临时设 NN_GUARD_ENCAPSULATION=0（不推荐）。",
    ]
    for v in violations:
        lines.append(f"  L{v['line']}: {v['text']}  → {v['fix']}")
    raise RuntimeError("\n".join(lines))


def _guard_contract_unchanged(repo_root: Path) -> None:
    if not _guard_contract_diff_enabled() or _relaunch_declared():
        return
    hits = _git_changed_paths(repo_root, ["contract/"])
    if not hits:
        return
    raise RuntimeError(
        "[Pre-flight G-契约] 检测到 contract/ 改动（常规迭代禁止）："
        f" {', '.join(hits)}\n"
        "  若立项/迁移/改口径：export NN_RELAUNCH=1\n"
        "  紧急跳过（不推荐）：NN_GUARD_CONTRACT_DIFF=0"
    )


def _guard_human_guidance_enabled() -> bool:
    return _static_guards_enabled() and _env_enabled("NN_GUARD_HUMAN_GUIDANCE", default="1")


def _guard_human_guidance_unchanged(repo_root: Path) -> None:
    if not _guard_human_guidance_enabled():
        return
    _ensure_scripts_on_path(repo_root)
    try:
        from lib.human_guidance_gate import check_human_guidance
    except ImportError:
        return  # optional: 门面模块未装（最小环境），SKIP 该 guard（不阻断其他）
    err = check_human_guidance(repo_root)
    if err:
        raise RuntimeError(f"[Pre-flight G-HUMAN] {err}")


def _guard_experiment_unchanged(repo_root: Path) -> None:
    if not _guard_experiment_diff_enabled() or _relaunch_declared():
        return
    hits = _git_changed_paths(repo_root, ["experiment.py"])
    if not hits:
        return
    raise RuntimeError(
        "[Pre-flight G-框架] 检测到 experiment.py 改动（常规迭代禁止）："
        f" {', '.join(hits)}\n"
        "  若立项/迁移/governance-sync 后首训：export NN_RELAUNCH=1\n"
        "  紧急跳过（不推荐）：NN_GUARD_EXPERIMENT_DIFF=0"
    )


def _guard_governance_docs_unchanged(repo_root: Path) -> None:
    if not _guard_governance_docs_enabled() or _relaunch_declared():
        return
    hits = _git_changed_paths(
        repo_root, ["CLAUDE.md", "PROTOCOL.md", "auto-nn-run.sh"]
    )
    if not hits:
        return
    raise RuntimeError(
        "[Pre-flight G-治理文档] 检测到治理文档改动（常规迭代禁止）："
        f" {', '.join(hits)}\n"
        "  若立项/迁移/governance-sync 后首训：export NN_RELAUNCH=1\n"
        "  紧急跳过（不推荐）：NN_GUARD_GOVERNANCE_DOCS=0"
    )


def _guard_repro_env(repo_root: Path) -> None:
    """Config-Only preflight: 检查 train.py/contract/workspace 是否违规读取实验参数 NN_* 环境变量。"""
    if not _static_guards_enabled():
        return
    if os.environ.get("NN_GUARD_REPRO_ENV", "1") in ("0", "false", "no", "off"):
        return

    # 系统参数白名单（Config-Only：不包含 SEED，SEED 须从 config.json）
    allowed_nn_vars = (
        "NN_DEVICE|NN_PREFLIGHT|NN_SMOKE|NN_AUTO_FINALIZE_ROUND|NN_EXPERIMENT|"
        "NN_PARALLEL_TOTAL|NN_SLOT|NN_POST_TRAIN_HOOK|NN_TIME_BUDGET|NN_DATA_DIR|"
        "NN_GUARD|NN_RELAUNCH|NN_GRAD_CLIP|NN_NOTES|NN_EARLY_STOP_PATIENCE|"
        "NN_APPEND_RESULTS_TSV|NN_APPEND_RESULTS_JSONL|NN_PREFLIGHT_LEDGER|NN_ROOT_PY_ALLOWLIST"
    )

    # 扫描 train.py, contract/, workspace/ 中的 os.environ.get("NN_XXX") / os.getenv("NN_XXX")
    # 用 -E（扩展正则）以支持 | 交替；子模式在 basic/extended 下语义一致。
    result = _run_optional_subprocess(
        [
            "grep", "-rhE",
            'os\\.environ\\.get\\("NN_[^"]*"\\)|os\\.getenv\\("NN_[^"]*"\\)',
            str(repo_root / "train.py"),
            str(repo_root / "contract/"),
            str(repo_root / "workspace/"),
        ],
        repo_root,
    )
    if result is None:
        return  # grep 不可用/失败 → SKIP 该 guard（不阻断训练）
    nn_calls = result.stdout.strip().split("\n") if result.stdout.strip() else []

    forbidden = []
    for line in nn_calls:
        if not line.strip():
            continue
        # 提取 NN_* 变量名
        import re
        matches = re.findall(r'NN_[A-Z_]+', line)
        for var in matches:
            if var not in allowed_nn_vars.split("|"):
                forbidden.append((var, line))
                break

    if forbidden:
        lines = "\n  ".join(f"- {var}: {line.strip()}" for var, line in forbidden)
        raise RuntimeError(
            f"[Pre-flight G-repro-env] FAIL — 发现读实验参数的 NN_* 环境变量:\n"
            f"  {lines}\n"
            f"  实验参数应通过 --config config.json 传入，禁止通过环境变量。\n"
            f"  可设 NN_GUARD_REPRO_ENV=0 临时跳过（需回滚违规代码）。"
        )


def _guard_cfg_no_defaults(repo_root: Path) -> None:
    """Config-Only preflight: 实验参数禁止 cfg.get(K, 默认)（须 cfg["K"] 强读）。

    复用 scripts/scan_cfg_defaults.py：EXPERIMENT_KEYS 的 cfg.get 默认值 → scanner
    退出码 1 → 阻断训练。SYSTEM_KEYS（SMOKE_*/CHECKPOINT_*）仅 WARN 不阻断。
    """
    if not _static_guards_enabled():
        return
    if os.environ.get("NN_GUARD_CFG_DEFAULTS", "1") in ("0", "false", "no", "off"):
        return
    scanner = repo_root / "scripts" / "scan_cfg_defaults.py"
    if not scanner.exists():
        return  # 最小环境无 scanner，SKIP（不阻断其他 guard）
    result = _run_optional_subprocess(
        [sys.executable, str(scanner), ".", "--allow-system"], repo_root,
    )
    if result is None:
        return  # scanner 跑不起来（最小环境），SKIP 该 guard
    if result.returncode != 0:
        detail = (result.stdout + result.stderr).strip()
        raise RuntimeError(
            "[Pre-flight G-cfg-no-defaults] FAIL — 发现实验参数 cfg.get 默认值（须 cfg[\"X\"] 强读）:\n"
            f"{detail}\n"
            "  实验参数禁止 cfg.get(K, 默认)；改成 cfg[\"K\"] 强读（缺失即 KeyError）。\n"
            "  可设 NN_GUARD_CFG_DEFAULTS=0 临时跳过（需回滚违规代码）。"
        )


def _guard_hardcoded_params(repo_root: Path) -> None:
    """hardcoded-params preflight（WARN-only）：扫描 workspace 函数签名硬编码默认值。

    config-only 合规检查：函数签名里的默认值应该在 config.json 里，不是写死在代码里。
    复用 scripts/scan_hardcoded_params.py。**仅 WARN 不阻断**。
    可用 NN_GUARD_HARDCODED_PARAMS=0 跳过。
    """
    if not _static_guards_enabled():
        return
    if os.environ.get("NN_GUARD_HARDCODED_PARAMS", "1") in ("0", "false", "no", "off"):
        return
    scanner = repo_root / "scripts" / "scan_hardcoded_params.py"
    if not scanner.exists():
        return  # optional: 最小环境无 scanner，SKIP
    result = _run_optional_subprocess(
        [sys.executable, str(scanner), str(repo_root)], repo_root,
    )
    if result is None:
        return  # scanner 跑不起来，SKIP
    out = (result.stdout or "").strip()
    warn_lines = [ln for ln in out.splitlines() if ln.startswith("[WARN]")]
    if warn_lines:
        print(
            "[Pre-flight G-hardcoded-params] WARN — workspace 函数签名含硬编码默认值"
            "（config-only 违规；应提取到 config.json）:\n"
            + "\n".join(warn_lines),
            file=sys.stderr,
        )


def _guard_no_fallback(repo_root: Path) -> None:
    """no-fallback preflight（WARN-only）：扫描吞错 except（静默 pass/return/continue）。

    复用 scripts/scan_no_fallback.py。**仅 WARN 不阻断**（合法 optional 场景也会被命中），
    汇总打 stderr 供人审；scanner 始终 exit 0。可用 NN_GUARD_NO_FALLBACK=0 跳过。
    """
    if not _static_guards_enabled():
        return
    if os.environ.get("NN_GUARD_NO_FALLBACK", "1") in ("0", "false", "no", "off"):
        return
    scanner = repo_root / "scripts" / "scan_no_fallback.py"
    if not scanner.exists():
        return  # optional: 最小环境无 scanner，SKIP
    result = _run_optional_subprocess(
        [sys.executable, str(scanner), "."], repo_root,
    )
    if result is None:
        return  # scanner 跑不起来，SKIP
    out = (result.stdout or "").strip()
    warn_lines = [ln for ln in out.splitlines() if ln.startswith("[WARN]")]
    if warn_lines:
        print(
            "[Pre-flight G-no-fallback] WARN — 发现吞错 except（勿隐藏错误，请上抛或显式处理；\n"
            "  合法 optional 特性须加 `# optional:` 注释抑制）：\n"
            + "\n".join(warn_lines),
            file=sys.stderr,
        )


def _extract_class_methods(file_path: Path) -> set[str]:
    code = file_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return set(re.findall(r"^\s+def\s+(\w+)\s*\(", code, re.MULTILINE))  # optional: AST 不可解析 → regex 降级

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    if item.name.startswith("_"):
                        continue
                    if len(item.body) == 1 and isinstance(item.body[0], ast.Expr):
                        val = item.body[0].value
                        if isinstance(val, ast.Constant) and val.value is ...:
                            continue
                    names.add(item.name)
    return names


def _load_profile_method_lists(repo_root: Path, profile: str) -> tuple[list[str], list[str]] | None:
    rules = _load_profile_facade_rules(repo_root, profile)
    if rules is None:
        return None
    return rules["contract"], rules["workspace"]


def _load_profile_facade_rules(repo_root: Path, profile: str) -> dict[str, list[str]] | None:
    import yaml

    yaml_path = repo_root / "profiles.yaml"
    if not yaml_path.is_file():
        return None
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    prof = (data.get("profiles") or {}).get(profile)
    if not prof:
        return None
    return {
        "contract": list(prof.get("contract") or []),
        "workspace": list(prof.get("workspace") or []),
        "contract_forbidden": list(prof.get("contract_forbidden") or []),
        "workspace_forbidden": list(prof.get("workspace_forbidden") or []),
    }


def _diff_profile_side(expected: list[str], actual: set[str]) -> tuple[list[str], list[str]]:
    exp_set = set(expected)
    return sorted(exp_set - actual), sorted(actual - exp_set)


def check_train_exp_dir_layout(repo_root: str | Path) -> list[TrainExpDirViolation]:
    """G-路径：train.py 须用 ``allocate_exp_dir`` 或 ``/_runs/exp/``，禁止仓库根 ``exp/``。"""
    root = Path(repo_root).resolve()
    train_py = root / "train.py"
    violations: list[TrainExpDirViolation] = []
    if not train_py.is_file():
        return violations

    src = train_py.read_text(encoding="utf-8")
    if "allocate_exp_dir(" in src:
        return violations
    if re.search(r'["_\w]+\s*/\s*["_\']_runs["\']\s*/\s*["_\']exp["\']', src):
        return violations

    if re.search(r'(?:^|[^\w])["\']/?exp["\']|/\s*["\']exp["\']\s*/', src):
        for i, line in enumerate(src.splitlines(), 1):
            if "exp_dir" in line and "exp" in line and "_runs" not in line:
                violations.append(TrainExpDirViolation(
                    rule="E1",
                    detail=f"train.py L{i}: exp_dir 未使用 _runs/exp（{line.strip()[:80]}）",
                    fix="from experiment import allocate_exp_dir；exp_dir = allocate_exp_dir(repo_root, experiment, ...)",
                ))
                break
        if not violations:
            violations.append(TrainExpDirViolation(
                rule="E1",
                detail="train.py 未使用 allocate_exp_dir 且未见 _runs/exp 路径",
                fix="exp_dir = allocate_exp_dir(<repo_root>, experiment)",
            ))

    legacy_exp = root / "exp"
    if legacy_exp.is_dir() and not any(legacy_exp.iterdir()):
        pass
    return violations


def check_profile_facade(repo_root: str | Path) -> list[ProfileFacadeViolation]:
    """门面 forbidden：Contract/Workspace 类上不得出现 profiles.yaml 的 *_forbidden 方法。"""
    root = Path(repo_root).resolve()
    cfg = _load_nn_config(root)
    profile = cfg.get("profile", "").strip()
    if not profile:
        return []

    rules = _load_profile_facade_rules(root, profile)
    if rules is None:
        return []

    violations: list[ProfileFacadeViolation] = []
    contract_py = root / "contract" / "__init__.py"
    workspace_py = root / "workspace" / "__init__.py"

    if contract_py.is_file():
        actual = _extract_class_methods(contract_py)
        for name in rules["contract_forbidden"]:
            if name in actual:
                violations.append(ProfileFacadeViolation(
                    rule="P2",
                    detail=f"contract 门面禁止方法: {name}",
                    fix=f"从 Contract 移除 {name}，改由 ExperimentBase 默认或子模块",
                ))

    if workspace_py.is_file():
        actual = _extract_class_methods(workspace_py)
        for name in rules["workspace_forbidden"]:
            if name in actual:
                violations.append(ProfileFacadeViolation(
                    rule="P4",
                    detail=f"workspace 门面禁止方法: {name}（数据入口仅 contract.prepare_data）",
                    fix=f"从 Workspace 删除 {name}；在 build_* 内调用 Contract().prepare_data(cfg)",
                ))

    return violations


def _guard_train_exp_dir(repo_root: Path) -> None:
    if not _guard_exp_dir_enabled():
        return
    violations = check_train_exp_dir_layout(repo_root)
    if not violations:
        return
    lines = [
        "[Pre-flight] train.py 实验目录违规（G-路径）：产物须在 _runs/exp/。",
        "修复：使用 experiment.allocate_exp_dir；或设 NN_GUARD_EXP_DIR=0（不推荐）。",
    ]
    for v in violations:
        lines.append(f"  [{v.rule}] {v.detail} → {v.fix}")
    raise RuntimeError("\n".join(lines))


def _guard_profile_facade_hard(repo_root: Path) -> None:
    if not _guard_profile_facade_enabled():
        return
    violations = check_profile_facade(repo_root)
    if not violations:
        return
    lines = [
        "[Pre-flight] 门面契约违规（G-门面）：profiles.yaml 与 contract/workspace 类方法不一致。",
        "修复：见 profiles.yaml 的 contract/workspace/workspace_forbidden；或 NN_GUARD_PROFILE_FACADE=0",
    ]
    for v in violations:
        lines.append(f"  [{v.rule}] {v.detail} → {v.fix}")
    raise RuntimeError("\n".join(lines))


def _guard_profile_alignment(repo_root: Path) -> None:
    if not _guard_profile_enabled():
        return
    cfg = _load_nn_config(repo_root)
    profile = cfg.get("profile", "").strip()
    if not profile:
        return

    lists = _load_profile_method_lists(repo_root, profile)
    if lists is None:
        return
    exp_contract, exp_workspace = lists

    contract_py = repo_root / "contract" / "__init__.py"
    workspace_py = repo_root / "workspace" / "__init__.py"
    if not contract_py.is_file() or not workspace_py.is_file():
        return

    c_miss, c_extra = _diff_profile_side(exp_contract, _extract_class_methods(contract_py))
    w_miss, w_extra = _diff_profile_side(exp_workspace, _extract_class_methods(workspace_py))

    if not (c_miss or c_extra or w_miss or w_extra):
        return

    parts = [f"[Pre-flight] 警告（G-范式）：profile={profile!r} 与 profiles.yaml 方法清单不完全一致。"]
    if c_miss:
        parts.append(f"  contract 缺失（应在 contract/ 覆盖）: {', '.join(c_miss)}")
    if w_miss:
        parts.append(f"  workspace 缺失: {', '.join(w_miss)}")
    if c_extra:
        parts.append(f"  contract 额外（profile 未列，可忽略）: {', '.join(c_extra)}")
    if w_extra:
        parts.append(f"  workspace 额外（实现助手可保留，如 run_training）: {', '.join(w_extra)}")
    parts.append("  设 NN_GUARD_PROFILE=0 可跳过；forbidden 方法由 G-门面 硬失败。")
    print("\n".join(parts), file=sys.stderr, flush=True)


def _list_unexpected_root_py(repo_root: Path) -> list[str]:
    """G-布局：返回根目录不在白名单内的 .py 文件名（供 preflight / 迁移对照复用）。"""
    allow = _root_py_allowlist()
    return [p.name for p in sorted(repo_root.glob("*.py")) if p.name not in allow]


def _guard_root_py_whitelist(repo_root: Path) -> None:
    """G-布局: 仓库根目录 *.py 应在白名单内；违规仅警告，建议移到 workspace/scripts/。"""
    if not _guard_root_py_enabled():
        return
    unexpected = _list_unexpected_root_py(repo_root)
    if not unexpected:
        return
    allow = _root_py_allowlist()
    print(
        "[Pre-flight] 警告（G-布局）：仓库根目录存在未在白名单的 .py 文件。\n"
        f"  文件: {', '.join(unexpected)}\n"
        f"  允许: {', '.join(sorted(allow))}\n"
        "  探路/临时脚本请放到 workspace/scripts/，勿作为训练入口。\n"
        "  设 NN_GUARD_ROOT_PY=0 可跳过；长期需要的脚本可用 NN_ROOT_PY_ALLOWLIST=foo.py 追加白名单。",
        file=sys.stderr,
        flush=True,
    )


@dataclass(frozen=True)
class TestAuthorityViolation:
    rule: str
    detail: str
    fix: str


@dataclass(frozen=True)
class ContractLayoutViolation:
    rule: str
    detail: str
    fix: str


@dataclass(frozen=True)
class TrainExpDirViolation:
    rule: str
    detail: str
    fix: str


@dataclass(frozen=True)
class ProfileFacadeViolation:
    rule: str
    detail: str
    fix: str


_CONTRACT_SPLIT_FILES: tuple[str, ...] = (
    "metrics.py",
    "runtime.py",
    "prepare_data.py",
    "test.py",
)


def _cl_imports_module(tree: ast.Module, module: str) -> bool:
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == module:
            return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == module:
                    return True
    return False


def _cl_imports_from_package(tree: ast.Module, package: str, name: str) -> bool:
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module == package:
            if any(alias.name == name for alias in node.names):
                return True
    return False


def _cl_runtime_referenced(repo_root: Path) -> bool:
    init_tree = _ta_read_ast(repo_root / "contract" / "__init__.py")
    if init_tree is not None and _cl_imports_module(init_tree, "contract.runtime"):
        return True
    for rel in ("prepare_data.py", "test.py"):
        tree = _ta_read_ast(repo_root / "contract" / rel)
        if tree is not None and _cl_imports_module(tree, "contract.runtime"):
            return True
    return False


def check_contract_layout(repo_root: str | Path) -> list[ContractLayoutViolation]:
    """G-契约布局：四文件拆分存在且门面从 metrics/prepare_data/test 引用；runtime 被同包引用。"""
    root = Path(repo_root).resolve()
    violations: list[ContractLayoutViolation] = []
    contract_dir = root / "contract"

    for name in _CONTRACT_SPLIT_FILES:
        if not (contract_dir / name).is_file():
            violations.append(ContractLayoutViolation(
                rule="L1",
                detail=f"缺少 contract/{name}",
                fix="从模板复制 contract/ 四文件；或 new-project.sh --profile <范式> [--skeleton <范式>]",
            ))

    init_py = contract_dir / "__init__.py"
    init_tree = _ta_read_ast(init_py)
    if init_tree is None:
        violations.append(ContractLayoutViolation(
            rule="L0",
            detail=f"无法解析 {init_py}",
            fix="修复 contract/__init__.py 语法",
        ))
        return violations

    if not _cl_imports_module(init_tree, "contract.metrics"):
        violations.append(ContractLayoutViolation(
            rule="L2",
            detail="contract/__init__.py 未从 contract.metrics 导入指标",
            fix="添加: from contract.metrics import METRIC_KEYS, AUXILIARY_KEYS",
        ))
    if not _cl_imports_from_package(init_tree, "contract", "prepare_data"):
        violations.append(ContractLayoutViolation(
            rule="L2",
            detail="contract/__init__.py 未 import contract.prepare_data",
            fix="添加: from contract import prepare_data as data_entry（并委托 prepare_data）",
        ))
    if not _cl_imports_from_package(init_tree, "contract", "test"):
        violations.append(ContractLayoutViolation(
            rule="L2",
            detail="contract/__init__.py 未 import contract.test",
            fix="添加: from contract import test as terminal_test（并委托 test）",
        ))
    if not _cl_runtime_referenced(root):
        violations.append(ContractLayoutViolation(
            rule="L3",
            detail="contract.runtime 未被 __init__/prepare_data/test 引用",
            fix="在 prepare_data.py 或 test.py 中: from contract.runtime import ...",
        ))

    return violations


def _format_contract_layout_violations(violations: list[ContractLayoutViolation]) -> str:
    lines = ["[Pre-flight] contract 布局违规（G-契约布局）："]
    for v in violations:
        lines.append(f"  [{v.rule}] {v.detail}")
        lines.append(f"       修复：{v.fix}")
    lines.append("  临时绕过：NN_GUARD_CONTRACT_LAYOUT=0（不推荐）。")
    return "\n".join(lines)


def _guard_contract_layout(repo_root: Path) -> None:
    if not _guard_contract_layout_enabled():
        return
    violations = check_contract_layout(repo_root)
    if violations:
        raise RuntimeError(_format_contract_layout_violations(violations))


def _ta_read_ast(path: Path) -> ast.Module | None:
    if not path.is_file():
        return None
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return None  # optional: 文件 AST 不可解析 → 调用方判 None 跳过


def _ta_contract_class(tree: ast.Module) -> ast.ClassDef | None:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Contract":
            return node
    return None


def _ta_method_def(cls: ast.ClassDef, name: str) -> ast.FunctionDef | None:
    for item in cls.body:
        if isinstance(item, ast.FunctionDef) and item.name == name:
            return item
    return None


def _ta_module_function(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _ta_effective_test_bodies(repo_root: Path, cls: ast.ClassDef) -> list[ast.FunctionDef]:
    """门面 Contract.test + contract/test.py 的 run（若存在）。"""
    bodies: list[ast.FunctionDef] = []
    test_fn = _ta_method_def(cls, "test")
    if test_fn is not None:
        bodies.append(test_fn)
    test_py = repo_root / "contract" / "test.py"
    ttree = _ta_read_ast(test_py)
    if ttree is not None:
        run_fn = _ta_module_function(ttree, "run")
        if run_fn is not None:
            bodies.append(run_fn)
    return bodies


def _ta_is_trivial_test(func: ast.FunctionDef) -> bool:
    if not func.body:
        return True
    if len(func.body) == 1:
        stmt = func.body[0]
        if isinstance(stmt, ast.Raise):
            return True
        if isinstance(stmt, ast.Expr):
            v = stmt.value
            if isinstance(v, ast.Constant) and v.value is ...:
                return True
    return False


def _ta_func_calls_ws_evaluate(func: ast.FunctionDef) -> bool:
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if isinstance(fn, ast.Attribute) and fn.attr == "evaluate":
            base = fn.value
            if isinstance(base, ast.Name) and base.id == "ws":
                return True
    return False


def _ta_func_has_substantive_logic(func: ast.FunctionDef) -> bool:
    if _ta_is_trivial_test(func):
        return False
    for node in ast.walk(func):
        if isinstance(node, (ast.For, ast.While, ast.With, ast.Try)):
            return True
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute) and fn.attr == "evaluate":
                if isinstance(fn.value, ast.Name) and fn.value.id == "ws":
                    continue
            return True
    return len(func.body) >= 1 and not _ta_is_trivial_test(func)


def _ta_rl_test_locks_eval_mode(func: ast.FunctionDef) -> bool:
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "mode":
                    if isinstance(kw.value, ast.Constant) and str(kw.value.value).lower() == "knn":
                        return True
                    if isinstance(kw.value, ast.Name) and kw.value.id in (
                        "EVAL_PERF_MODEL_MODE",
                        "eval_perf_model_mode",
                    ):
                        return True
                if kw.arg == "eval_perf_model_mode":
                    if isinstance(kw.value, ast.Constant) and str(kw.value.value).lower() == "knn":
                        return True
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and k.value == "eval_perf_model_mode":
                    if isinstance(v, ast.Constant) and str(v.value).lower() == "knn":
                        return True
    text = ast.unparse(func) if hasattr(ast, "unparse") else ""
    if "eval_perf_model_mode" in text and "knn" in text:
        return True
    if re.search(r"""mode\s*=\s*['"]knn['"]""", text):
        return True
    if re.search(r"""EVAL_PERF_MODEL_MODE\s*=\s*['"]knn['"]""", text):
        return True
    return False


def _ta_infer_func_param_names(func: ast.FunctionDef) -> list[str]:
    names = [a.arg for a in func.args.args]
    names.extend(a.arg for a in func.args.kwonlyargs)
    return names


def _ta_find_make_eval_env_file(workspace_dir: Path) -> Path | None:
    """按方法（make_eval_env）而非固定文件名定位 RL eval-env 工厂；workspace 子模块名自由。

    优先 workspace/infer.py（推荐位），否则扫描 workspace/**.py 找首个定义 make_eval_env 的文件。
    """
    if not workspace_dir.is_dir():
        return None
    preferred = workspace_dir / "infer.py"

    def _defines_make_eval_env(path: Path) -> bool:
        tree = _ta_read_ast(path)
        if tree is None:
            return False
        return any(
            isinstance(node, ast.FunctionDef) and node.name == "make_eval_env"
            for node in ast.walk(tree)
        )

    if preferred.is_file() and _defines_make_eval_env(preferred):
        return preferred
    for py in sorted(workspace_dir.rglob("*.py")):
        if py == preferred:
            continue
        if _defines_make_eval_env(py):
            return py
    return None


def _ta_infer_make_eval_env_accepts_mode(infer_path: Path) -> bool:
    tree = _ta_read_ast(infer_path)
    if tree is None:
        return True
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "make_eval_env":
            return "mode" in _ta_infer_func_param_names(node)
    return True


def _ta_infer_make_eval_env_env_only_mode(infer_path: Path) -> bool:
    tree = _ta_read_ast(infer_path)
    if tree is None:
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "make_eval_env":
            continue
        if "mode" in _ta_infer_func_param_names(node):
            return False
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                fn = sub.func
                if isinstance(fn, ast.Name) and fn.id == "create_multi_structure_env":
                    for kw in sub.keywords:
                        if kw.arg == "mode":
                            if isinstance(kw.value, ast.Name) and kw.value.id == "PERF_MODEL_MODE":
                                return True
    return False


def _ta_load_profile(repo_root: Path) -> str:
    cfg = _load_nn_config(repo_root)
    return str(cfg.get("profile", "")).strip()


def check_test_authority(repo_root: str | Path) -> list[TestAuthorityViolation]:
    """G-评估：contract.test 权威违规列表（供 preflight / 迁移 comparator）。"""
    root = Path(repo_root).resolve()
    violations: list[TestAuthorityViolation] = []

    contract_py = root / "contract" / "__init__.py"
    train_py = root / "train.py"
    infer_py = _ta_find_make_eval_env_file(root / "workspace")
    profile = _ta_load_profile(root)

    ctree = _ta_read_ast(contract_py)
    if ctree is None:
        violations.append(TestAuthorityViolation(
            rule="S0",
            detail=f"无法解析 {contract_py}",
            fix="修复 contract/__init__.py 语法",
        ))
        return violations

    cls = _ta_contract_class(ctree)
    if cls is None:
        violations.append(TestAuthorityViolation(
            rule="S1",
            detail="contract/__init__.py 中未找到 Contract 类",
            fix="实现 class Contract(ExperimentBase)",
        ))
        return violations

    test_fn = _ta_method_def(cls, "test")
    if test_fn is None:
        violations.append(TestAuthorityViolation(
            rule="S1",
            detail="Contract 未实现 test()",
            fix="在 contract 子类中实现 test(learner, ws, *, shared_context)",
        ))
    else:
        bodies = _ta_effective_test_bodies(root, cls)
        if any(_ta_func_calls_ws_evaluate(b) for b in bodies):
            violations.append(TestAuthorityViolation(
                rule="S2",
                detail="contract.test / contract.test.run 调用了 ws.evaluate()（权威方向错误）",
                fix="将评估写在 contract/test.py 的 run 内；ws.evaluate 可调用 contract.test，不可反向",
            ))
        elif all(_ta_is_trivial_test(b) for b in bodies):
            violations.append(TestAuthorityViolation(
                rule="S1",
                detail="contract.test() 与 contract/test.py 均无实质实现",
                fix="在 contract/test.py 的 run() 内实现台账评估（门面 test 可委托）",
            ))
        elif not any(_ta_func_has_substantive_logic(b) for b in bodies):
            violations.append(TestAuthorityViolation(
                rule="S1",
                detail="contract.test / contract.test.run 缺少实质评估逻辑",
                fix="实现完整 test 流程（数据/模式/指标计算）",
            ))
        elif profile == "rl" and not any(_ta_rl_test_locks_eval_mode(b) for b in bodies):
            violations.append(TestAuthorityViolation(
                rule="A1",
                detail="RL profile：contract.test / contract.test.run 未显式锁定 eval 模式为 knn",
                fix='在 contract/test.py 的 run 内显式 mode="knn"（或 eval_perf_model_mode="knn"）并实现完整评估',
            ))

    if train_py.is_file():
        if "contract.test(" not in train_py.read_text(encoding="utf-8"):
            violations.append(TestAuthorityViolation(
                rule="S3",
                detail="train.py 未调用 contract.test()",
                fix="训末以 contract.test() 作为官方指标来源，再传入 finalize_run",
            ))
    else:
        violations.append(TestAuthorityViolation(
            rule="S3",
            detail="缺少 train.py",
            fix="从模板复制 train.py",
        ))

    if profile == "rl" and infer_py is not None and infer_py.is_file():
        rel = infer_py.relative_to(root) if infer_py.is_relative_to(root) else infer_py
        if not _ta_infer_make_eval_env_accepts_mode(infer_py):
            violations.append(TestAuthorityViolation(
                rule="A5",
                detail=f"{rel} make_eval_env 缺少 mode 参数",
                fix="def make_eval_env(..., mode: str | None = None)，由 contract.test 传入",
            ))
        elif _ta_infer_make_eval_env_env_only_mode(infer_py):
            violations.append(TestAuthorityViolation(
                rule="A5",
                detail="make_eval_env 仅以 PERF_MODEL_MODE 环境常量决定 mode",
                fix="mode 优先使用函数参数（contract.test 传入），默认可为 knn",
            ))

    return violations


def _format_test_authority_violations(violations: list[TestAuthorityViolation]) -> str:
    lines = ["[Pre-flight] contract.test 权威违规（G-评估）："]
    for v in violations:
        lines.append(f"  [{v.rule}] {v.detail}")
        lines.append(f"       修复：{v.fix}")
    lines.append("  临时绕过：NN_GUARD_TEST_AUTHORITY=0（不推荐）。")
    return "\n".join(lines)


def _guard_test_authority(repo_root: Path) -> None:
    if not _guard_test_authority_enabled():
        return
    violations = check_test_authority(repo_root)
    if violations:
        raise RuntimeError(_format_test_authority_violations(violations))


# ── G-信息权限 ────────────────────
# 家族特例：**无 NN_GUARD_* 开关**。enforce 只来自 contract/runtime.py 的字面量 INFO_PERM
# （改它 = 改合同，受 G-契约 / NN_RELAUNCH 约束）。未登记 → 全部空转（存量业务仓 0 影响）。

def _load_info_perm_or_none(repo_root: Path):
    _ensure_scripts_on_path(repo_root)
    try:
        from lib.info_perm import InfoPermError, load_info_perm  # noqa: WPS433
    except ImportError:
        return None  # optional: 最小环境无 scripts/lib（governance-sync 前），视为未登记
    try:
        return load_info_perm(repo_root)
    except InfoPermError as exc:
        raise RuntimeError(f"[Pre-flight G-信息权限] IP0 {exc}") from exc


def _guard_info_perm(repo_root: Path) -> None:
    """合同静态（登记表 / 交卷缝）+ 安装运行时挂钩：只评材料真打开才拦。"""
    _ensure_scripts_on_path(repo_root)
    try:
        from lib.info_perm import (  # noqa: WPS433
            InfoPermError,
            check_info_perm,
            format_violations,
            install_eval_only_runtime_guard,
        )
    except ImportError:
        return  # optional: 最小环境无 scripts/lib（governance-sync 前），SKIP
    try:
        violations = check_info_perm(repo_root)
    except InfoPermError as exc:
        raise RuntimeError(f"[Pre-flight G-信息权限] IP0 {exc}") from exc
    if violations:
        raise RuntimeError(format_violations(violations))
    install_eval_only_runtime_guard(repo_root)


def _guard_train_batch_keys(repo_root: Path, batch: Any) -> None:
    """动态：训练首 batch 的键 / 项数须在 INFO_PERM["train_batch_keys"] 白名单内。"""
    if batch is None:
        return
    perm = _load_info_perm_or_none(repo_root)
    if perm is None or not perm.enforce or perm.train_batch_keys is None:
        return
    from lib.info_perm import check_train_batch_keys  # noqa: WPS433

    problems = check_train_batch_keys(batch, perm.train_batch_keys)
    if problems:
        raise RuntimeError(
            "[Pre-flight G-信息权限] 训练 batch 键越权：" + "；".join(problems)
            + "。修复：只评材料不得进训练 loader（contract.prepare_data 只给训练份）"
        )


def collect_guard_bypasses(environ: Mapping[str, str] | None = None) -> list[str]:
    """finalize 留痕：``NN_PREFLIGHT`` / ``NN_GUARD`` / ``NN_GUARD_*`` 取 0/false/no/off 的项。"""
    try:
        from lib.info_perm import collect_guard_bypasses as _impl  # noqa: WPS433

        return _impl(environ)
    except ImportError:
        env = os.environ if environ is None else environ
        return sorted(
            f"{k}={env[k]}" for k in env
            if (k == "NN_PREFLIGHT" or k == "NN_GUARD" or k.startswith("NN_GUARD_"))
            and str(env[k]).strip().lower() in ("0", "false", "no", "off")
        )


def _raise_if_bypassed_under_enforce(repo_root: Path, bypasses: list[str]) -> None:
    """合同 ``INFO_PERM["enforce"]=True`` 且本次训练带守门旁路 → 训末抛错，不入账、不判 KEEP。"""
    if not bypasses:
        return
    perm = _load_info_perm_or_none(repo_root)
    if perm is None or not perm.enforce:
        return
    raise RuntimeError(
        "[finalize G-旁路] 本次训练带守门旁路 " + ", ".join(bypasses)
        + "；合同 INFO_PERM.enforce=True 下不入账、不判 KEEP。"
        "已在 config.json._repro.guards_bypassed 留痕。修复：去掉旁路重跑。"
    )


def _read_guards_bypassed(exp_dir: Path) -> list[str]:
    try:
        cfg = json.loads((Path(exp_dir) / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):  # optional: 缺 config.json 时视为无旁路留痕
        return []
    v = (cfg.get("_repro") or {}).get("guards_bypassed") if isinstance(cfg, dict) else None
    return [str(x) for x in v] if isinstance(v, list) else []


def _guard_results_tsv_header(repo_root: Path, contract: Any) -> None:
    """G-台账：results.tsv 表头须与 contract._default_tsv_columns() 一致，否则指标会被静默丢弃。"""
    if not _guard_tsv_header_enabled():
        return
    tsv = repo_root / "_runs" / "results.tsv"
    if not tsv.is_file() or tsv.stat().st_size == 0:
        return
    header = _read_tsv_header(tsv)
    if header is None:
        return
    expected = contract._default_tsv_columns()
    if header == expected:
        return
    mk = contract.metric_key
    required = (
        set(contract.metric_keys.keys())
        | set(contract.auxiliary_keys.keys())
        | set(contract.ledger_context_keys)
    )
    required.add(SCENARIO_ID_COLUMN)
    missing = sorted(required - set(header))
    lines = [
        "[G-台账] 警告: _runs/results.tsv 表头与当前 contract 不一致，指标列可能无法写入或 should_keep 读不到历史。",
        f"  当前主指标: {mk!r}；表头中位置: {header.index(mk)!r}" if mk in header else f"  当前主指标: {mk!r}（不在表头）",
    ]
    if missing:
        lines.append(f"  缺列 ({len(missing)}): {', '.join(missing[:8])}{'…' if len(missing) > 8 else ''}")
    if mk not in header:
        lines.append("  主指标列不在表头中，append 时指标值会被静默丢弃（曾见于 val_accuracy 占位表头）。")
    lines.append("  修复: python3 scripts/regen_results_tsv.py --repo-root .")
    lines.append("  或设 NN_GUARD_TSV_HEADER=0 跳过本警告。")
    print("\n".join(lines), file=sys.stderr, flush=True)


def _guard_scenario_id(
    repo_root: Path,
    cfg: dict[str, Any] | None = None,
    contract: Any | None = None,
) -> None:
    """G-场景：scenario_id 须可解析且 ∈ F1 场景清单。"""
    if not _guard_scenario_id_enabled():
        return
    try:
        _resolve_validated_scenario_context(repo_root, cfg, contract=contract)
    except ValueError as exc:
        raise RuntimeError(
            "[Pre-flight] scenario_id 校验失败（须解析出非空 ID 且属于 F1 场景清单）："
            f" {exc}"
        ) from exc


def _run_static_preflight_guards(repo_root: Path | None = None) -> None:
    root = (repo_root or Path(__file__).resolve().parent).resolve()
    _guard_train_encapsulation(root)
    _guard_train_exp_dir(root)
    _guard_test_authority(root)
    _guard_info_perm(root)
    _guard_contract_layout(root)
    _guard_profile_facade_hard(root)
    _guard_root_py_whitelist(root)
    _guard_human_guidance_unchanged(root)
    _guard_contract_unchanged(root)
    _guard_experiment_unchanged(root)
    _guard_governance_docs_unchanged(root)
    _guard_profile_alignment(root)
    _guard_repro_env(root)
    _guard_cfg_no_defaults(root)
    _guard_no_fallback(root)
    _guard_hardcoded_params(root)


def _assert_scalar_loss_finite(loss: torch.Tensor, name: str = "loss") -> float:
    if loss.dim() != 0:
        raise ValueError(f"{name}: expected scalar tensor, got shape {tuple(loss.shape)}")
    v = float(loss.detach().item())
    if not (v == v and abs(v) < 1e38):
        raise RuntimeError(f"{name}: non-finite ({v})")
    return v


def _assert_grads_finite(module: nn.Module) -> None:
    for p in module.parameters():
        if p.grad is None:
            continue
        if not torch.isfinite(p.grad.detach()).all():
            raise RuntimeError("non-finite gradient in model parameter")


def _dummy_backward_once(
    model: nn.Module,
    loss: torch.Tensor,
    *,
    grad_clip: float = 1.0,
    set_train: bool = True,
) -> float:
    if set_train:
        model.train()
    model.zero_grad(set_to_none=True)
    _assert_scalar_loss_finite(loss, "loss")
    loss.backward()
    if grad_clip > 0:
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=grad_clip)
    _assert_grads_finite(model)
    return float(loss.detach().item())


def _verify_loss_fn(
    model: nn.Module,
    loss_fn: Callable[[], Any],
    *,
    grad_clip: float = 1.0,
    set_train: bool = True,
) -> float:
    if set_train:
        model.train()
    result = loss_fn()
    loss = result["total"] if isinstance(result, dict) else result
    return _dummy_backward_once(model, loss, grad_clip=grad_clip, set_train=False)


# ── Train PID 文件 ───────────────────────────────────

def write_train_pid(repo_root: str | os.PathLike) -> None:
    """写入 saved/.train_pid（训练启动时调用）。"""
    saved = Path(repo_root) / "saved"
    saved.mkdir(parents=True, exist_ok=True)
    pid_path = saved / ".train_pid"
    pid_path.write_text(
        json.dumps({
            "pid": os.getpid(),
            "cwd": os.getcwd(),
            "started_at": datetime.now(timezone.utc).isoformat(),
        }),
        encoding="utf-8",
    )


def clear_train_pid(repo_root: str | os.PathLike) -> None:
    """清理 saved/.train_pid（finalize 结束后调用）。"""
    pid_path = Path(repo_root) / "saved" / ".train_pid"
    if pid_path.exists():
        pid_path.unlink()


def _load_ledger_watchlist() -> tuple[str, ...]:
    """从 CWD 的 nn-config.yaml 的 ledger.watchlist 读白名单。
    缺失或异常 → 返回 ()（向后兼容：旧 Contract override / 无 yaml 都不破坏）。"""
    try:
        cfg_path = Path.cwd() / "nn-config.yaml"
    except Exception:
        return ()  # optional: CWD/Path 构建异常 → 回落空 watchlist（向后兼容旧 Contract override）
    if not cfg_path.is_file():
        return ()
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return ()  # optional: yaml 损坏/IO 异常 → 回落空 watchlist（向后兼容，旧 Contract override 不破坏）
    watchlist = (cfg.get("ledger") or {}).get("watchlist") or []
    if not isinstance(watchlist, list):
        return ()
    return tuple(str(x).strip() for x in watchlist if x is not None and str(x).strip())


# ═══════════════════════════════════════════════════════════════
# ExperimentBase
# ═══════════════════════════════════════════════════════════════

class ExperimentBase:
    """实验系统统一基类。contract/ 和 workspace/ 分别覆盖不同子集。"""

    # ── 环境属性（可由子类覆盖） ──────────────────────────────

    @property
    def time_budget(self) -> int:
        # Config-Only（与 seed 同款先例）：唯一真值 nn-config.yaml，
        # 经 _resolve_time_budget() 校验 env 一致性，不一致拒启留痕。
        return _resolve_time_budget()

    def bind_train_cfg(self, cfg: dict[str, Any]) -> None:
        """绑定本轮 ``train.py`` 已合并的实验 config（含 ``SEED``）。

        ``setup_seed`` / ``build_full_snapshot`` 经 ``seed`` 属性读 ``cfg["SEED"]``
        （Config-Only；禁止用 ``NN_SEED`` 覆盖实验种子）。
        """
        self._train_cfg = cfg

    @property
    def seed(self) -> int:
        """解析本轮随机种子（Config-Only）。

        优先级：已绑定 train cfg 的 ``SEED`` → ``nn-config.yaml`` 的 ``seed`` → ``42``。
        不读 ``NN_SEED``（实验参数禁止走环境变量；见 PROTOCOL §2.3）。
        """
        train_cfg = getattr(self, "_train_cfg", None)
        if isinstance(train_cfg, dict) and "SEED" in train_cfg and train_cfg["SEED"] is not None:
            return int(train_cfg["SEED"])
        cfg = _load_nn_config()
        return int(cfg.get("seed", 42))

    @staticmethod
    def _extract_metric_percent(text: str, label: str | None = None, default: float | None = None) -> float | None:
        """从外部框架 stdout 抽最后一个 'X%' 或 '[label]: X%'，归一为 0~1 小数。

        覆盖 mammoth 'Accuracy for N task(s): [Class-IL]: 85.94 %' + 标准 'accuracy: 0.85'。
        adapter 场景的 contract.test 可用它解析子进程 stdout，避免硬编码框架格式。

        Args:
            text: 子进程 stdout / 框架输出
            label: 若给，只匹配 '[label]: X%' 形式（如 'Class-IL'）
            default: 无匹配时返回（None）
        """
        import re
        if label:
            # [Class-IL]: 85.94 %  或  [Class-IL] 85.94%
            pattern = re.compile(rf"\[{re.escape(label)}\][^\d\-]+(\d+\.?\d*)\s*%")
            matches = pattern.findall(text)
            if matches:
                return round(float(matches[-1]) / 100.0, 6)
        else:
            # 优先 'X%'（百分比），取最后一个
            pcts = re.findall(r"(\d+\.?\d*)\s*%", text)
            if pcts:
                return round(float(pcts[-1]) / 100.0, 6)
            # fallback: 'accuracy: 0.85'（已是小数）
            decs = re.findall(r"(?:accuracy|acc)[^\d]+(0\.\d+)", text, re.IGNORECASE)
            if decs:
                return float(decs[-1])
        return default

    @staticmethod
    def setup_seed(contract_or_self) -> None:
        """统一设置所有随机种子 + cuDNN 确定性 + Python 哈希种子 + cuBLAS 固定工作区。
        在 train.py main() 开头调用一次。"""
        seed = contract_or_self.seed
        # 1. Python 哈希种子（影响 dict/set 遍历顺序）
        os.environ.setdefault("PYTHONHASHSEED", str(seed))
        # 2. cuBLAS 固定工作区（禁用异步分配，确保确定性）
        os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
        # 3. 随机种子
        torch.manual_seed(seed)
        random.seed(seed)
        np.random.seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        # 4. cuDNN / cuBLAS 确定性
        deterministic = _resolve_deterministic()
        torch.backends.cudnn.deterministic = deterministic
        torch.backends.cudnn.benchmark = not deterministic
        if deterministic:
            # 强制使用确定性算法（可能牺牲部分性能）
            try:
                torch.use_deterministic_algorithms(True, warn_only=False)
            except TypeError:
                torch.use_deterministic_algorithms(True)

    @property
    def data_dir(self) -> str:
        """业务仓数据目录（spec T-A3）。

        优先级：subclass override > ``NN_DATA_DIR`` env > ``./data`` 兜底。
        不再硬编码模板仓的 ``data/example-cls`` 路径（防模板/业务仓混淆）。
        业务仓 contract 可在子类 override 返回绝对路径或相对业务仓根的路径。
        """
        env = os.environ.get("NN_DATA_DIR")
        if env:
            return env
        return "./data"

    @property
    def num_classes(self) -> int:
        return int(os.environ.get("NN_NUM_CLASSES", "10"))

    @property
    def val_ratio(self) -> float:
        return float(os.environ.get("NN_VAL_RATIO", "0.1"))

    @property
    def checkpoint_kind(self) -> str:
        return "classification"

    # ── Low-level hooks (override optionally) ──

    def build_model(self, cfg: dict) -> Any:
        raise NotImplementedError("override build_model or build_learner")

    def build_loss(self, cfg: dict) -> Any:
        raise NotImplementedError("override build_loss or build_objective")

    def build_optimizer(self, model: Any, cfg: dict) -> Any:
        lr = float(cfg["LR"])
        wd = float(cfg["WEIGHT_DECAY"])
        return torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd), {"LR": lr, "WEIGHT_DECAY": wd}

    def build_scheduler(self, optimizer: Any, cfg: dict) -> Any:
        epochs = int(cfg["EPOCHS"])
        return torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs), {"EPOCHS": epochs}

    def build_dataloader(self, cfg: dict) -> Any:
        return self.prepare_data(cfg)

    def wrap_train_loader(self, train_loader: Any, cfg: dict) -> Any:
        """D 档：按 ``cfg["DATA_SAMPLER"]`` 可选重包训练 loader（不改 contract）。

        - 无 ``DATA_SAMPLER`` 键 → 原样返回（老仓 / 未启用）
        - ``none`` / ``uniform`` / 空串 → 原样返回
        - 其它值 → ``SAMPLER_REGISTRY`` 查表；未知 → KeyError（no-fallback）
        - ``train_loader is None``（rl/physical）→ None
        """
        if train_loader is None:
            return None
        if "DATA_SAMPLER" not in cfg:
            return train_loader
        name = str(cfg["DATA_SAMPLER"]).lower().strip()
        if name in ("", "none", "uniform"):
            return train_loader
        if name not in SAMPLER_REGISTRY:
            raise KeyError(
                f"DATA_SAMPLER={name!r} 不在 SAMPLER_REGISTRY {sorted(SAMPLER_REGISTRY)}；"
                f"在 workspace 用 @register_sampler({name!r}) 注册，"
                "禁止把 WeightedRandomSampler 等训练技巧写进 contract/prepare_data"
            )
        dataset = getattr(train_loader, "dataset", None)
        if dataset is None:
            raise RuntimeError(
                f"DATA_SAMPLER={name!r} 需要 train_loader.dataset；"
                "contract.prepare_data 须返回标准 DataLoader（带 .dataset）"
            )
        sampler = SAMPLER_REGISTRY[name](dataset, cfg)
        return rebuild_dataloader_with_sampler(train_loader, sampler)

    # ── Contract 侧（由 contract/ 目录覆盖） ────────────────

    @property
    def metric_keys(self) -> dict[str, str]:
        """主指标 dict {key: direction}。第一个 key = 台账主列 + pick_keeper 排序。
        与 ``auxiliary_keys`` 必须互斥。"""
        raise NotImplementedError

    @property
    def auxiliary_keys(self) -> dict[str, str]:
        """辅助指标 dict {key: direction}。TSV 后排 + aux_guards 守卫。
        与 ``metric_keys`` 必须互斥。"""
        return {}

    @property
    def ledger_context_keys(self) -> tuple[str, ...]:
        """运行上下文参数（非 metric）。写入 TSV **parameters** 区；不参与 ``should_keep``。
        键名须与 ``finalize_run`` 传入的 ``cfg`` 字段一致（如 ``N_SIP``、``MODE``）。
        优先读 YAML (nn-config.yaml["ledger"]["watchlist"])；缺失/异常 → 回退到
        Contract 子类 override（保持向后兼容）。

        系统键 ``baseline_tag`` 始终并入（E5 / 尺子可观测）：即使 watchlist 手改漏掉，
        出列与写行仍能带上基线角色列。
        系统键 ``exploration_space`` 始终并入（探索空间格子，事后回填；非 cfg 超参）。
        """
        from_yaml = _load_ledger_watchlist()
        if from_yaml:
            keys = list(from_yaml)
        else:
            contract = getattr(self, "contract", None)
            if contract is not None:
                keys = list(getattr(contract, "ledger_context_keys", ()) or ())
            else:
                keys = []
        if "baseline_tag" not in keys:
            keys.append("baseline_tag")
        if "exploration_space" not in keys:
            keys.append("exploration_space")
        return tuple(keys)

    def _effective_ledger_context_keys(self) -> tuple[str, ...]:
        """合并 ``ledger_context_keys`` 与系统 pin/overlay。

        Contract 用类属性盖掉 ``ledger_context_keys`` property 时，仍保证
        ``baseline_tag`` / ``_LEDGER_OVERLAY_KEYS``（含 ``exploration_space`` /
        ``untrained``）入表头与写行。
        """
        keys = list(self.ledger_context_keys)
        if "baseline_tag" not in keys:
            keys.append("baseline_tag")
        for k in _LEDGER_OVERLAY_KEYS:
            if k not in keys:
                keys.append(k)
        return tuple(keys)

    @property
    def loss_log_keys(self) -> tuple[str, ...]:
        """除 ``train_loss`` 外写入 ``metrics_series.tsv`` 的训练 loss 分量。默认空元组。"""
        return ()

    @property
    def repro_env_keys(self) -> tuple[str, ...]:
        """复现须对齐的环境变量名（写入 ``config.json`` 的 ``_repro.repro_env`` 与 ``env_snapshot.json``）。
        立项/迁移时在 HARD-GATE **D4-repro-data** / **O4-repro-determinism** 钉死；课题在 ``contract/runtime.py`` 声明。"""
        return ("NN_SEED", "NN_DATA_DIR", "CUDA_VISIBLE_DEVICES")

    @staticmethod
    def build_train_cfg() -> dict[str, Any]:
        """捕获 train.py 顶部大写常量，返回完整实验参数配置。

        此方法供 build_repro_snapshot() 使用，记录所有实验参数到 config.json。
        train.py 应在文件顶部定义大写常量（如 SEED、LR、EPOCHS），这些常量
        会被本方法捕获并存储到 snapshot 中。

        注意：此方法需要在 train.py import 后调用，因为 globals() 返回的是
        调用时刻的全局命名空间。
        """
        cfg: dict[str, Any] = {}
        for k, v in globals().items():
            if k.isupper() and not k.startswith("_"):
                cfg[k] = v
        return cfg

    @property
    def agent_scenario_bindings(self) -> tuple[dict[str, Any], ...]:
        """可选：``scenario_default`` → ``NN_*`` 绑定（``nn-config.agent.scenario_bindings`` 优先）。

        每项示例::

            {"env_var": "NN_N_SIP", "parser": "sip", "value_key": "numeric"}
        """
        return ()

    # ── 向后兼容派生属性（新代码勿用） ──

    @property
    def metric_key(self) -> str | None:
        """主指标的第一个 key（spec T-A1）。

        ``metric_keys`` 为空时（如 greenfield init 还未 ``set_metric_keys``）
        返回 ``None`` 而非抛 ``StopIteration``；下游 ``_default_tsv_columns``
        的 set 减法 ``... - {self.metric_key}`` 在 None 时退化为不减。
        """
        keys = list(self.metric_keys.keys())
        return keys[0] if keys else None

    @property
    def metric_direction(self) -> str | None:
        """主指标方向（spec T-A1）。

        ``metric_keys`` 为空时（如 greenfield init 还未 ``set_metric_keys``）
        返回 ``None`` 而非抛 ``StopIteration``；与 ``metric_key`` 同形态（空字典
        → None，下游 ``== "maximize"`` 等比较退化为 False / 字符串插值退化为
        ``None``，由调用方选择 default；包一层 ``metric_direction(repo_root)``
        在 run_ledger_summary.py:162 已默认 ``"maximize"`` 兜底）。
        """
        values = list(self.metric_keys.values())
        return values[0] if values else None

    @property
    def primary_metric_keys(self) -> tuple[str, ...]:
        return tuple(self.metric_keys.keys())

    @property
    def aux_metrics(self) -> dict:
        return dict(self.auxiliary_keys)

    @property
    def primary_metric_directions(self) -> dict[str, str]:
        return dict(self.metric_keys)

    @property
    def history_experiment_substr(self) -> str:
        """@deprecated KEEP 分池已改按 TSV ``scenario_id``；此属性保留仅为向后兼容，``should_keep`` 不再读取。"""
        return ""

    def _effective_keep_spec(self) -> dict:
        # keep spec 由 nn-config.yaml keep 段驱动（mode 决定 primary_delta，见 presets.py）；
        # 不从 contract 常量读——keep 阈值是探索策略的函数，不该跟场景号钉死成死值。
        keep_cfg = _load_nn_config().get("keep", {}) or {}
        # spec §0.1：primary_delta_rel 优先，老 primary_delta 作 derived read-only
        from lib.experiment_mode import _resolve_keep_delta
        delta = _resolve_keep_delta(keep_cfg, default=0.005)
        return {
            "mode": keep_cfg.get("mode", "relative"),
            "improve_mode": keep_cfg.get("improve_mode", "any_primary"),
            "primary_delta": float(delta),
            "primary_delta_rel": float(delta),
            "near_best_abs": keep_cfg.get("near_best_abs", 0.0),
        }

    @staticmethod
    def apply_build_meta(cfg: dict, meta: dict, label: str) -> None:
        """Merge build metadata into cfg and print non-empty results to stderr."""
        cfg.update(meta)
        if meta:
            print(f"[{label}] {meta}", file=sys.stderr, flush=True)

    def build_full_snapshot(self, device: str | None = None) -> dict[str, Any]:
        """返回所有系统级 resolved 参数快照，供 train.py 写入 config.json。

        调用时机：train.py 中 contract = create_contract(cfg) 后，
        _pick_device() 确定 device 之后。
        """
        keep = self._effective_keep_spec()
        return {
            "deterministic": _resolve_deterministic(),
            "checkpoint_policy": resolve_checkpoint_policy(),
            "keep_mode": keep["mode"],
            "keep_improve_mode": keep["improve_mode"],
            "keep_primary_delta": keep["primary_delta"],
            "keep_near_best_abs": keep["near_best_abs"],
            "time_budget": self.time_budget,
            "device": device or ("cuda" if torch.cuda.is_available() else "cpu"),
            "profile": _load_nn_config().get("profile", "unknown"),
            "seed_resolved": self.seed,
        }

    def _filter_history_for_keep(
        self,
        history_rows: list[dict[str, str]],
        *,
        current_scenario_id: str,
        current_exp_dir: str | os.PathLike | None = None,
    ) -> list[dict[str, str]]:
        sid = (current_scenario_id or "").strip()
        if not sid:
            return []
        cur_dir = ""
        if current_exp_dir is not None:
            try:
                cur_dir = str(Path(current_exp_dir).resolve()).strip()
            except (OSError, ValueError):
                cur_dir = str(current_exp_dir).strip()
        rows = [
            row for row in history_rows
            if str(row.get(SCENARIO_ID_COLUMN, "")).strip() == sid
        ]
        if cur_dir:
            # 撞墙信号修复：剔除当前 exp_dir 行，避免「自己与自己比」导致 keep 假阳
            # （单槽路径 report_train_artifacts 写 TSV 在前，write_slot_keep_suggestion 比较在后）
            # v2.7.4: row.exp_dir 现存相对 repo_root(新) 或绝对(老数据); cur_dir 是内存绝对。
            # 两侧都 resolve 成绝对再比, 否则相对/绝对格式不一致 → != 永真 → 当前行剔不掉 → keep 假阳。
            try:
                _base = _resolve_repo_root(Path(current_exp_dir))
            except (OSError, ValueError):
                _base = None

            def _norm_exp(p: object) -> str:
                ps = str(p or "").strip()
                if not ps:
                    return ""
                pp = Path(ps)
                if not pp.is_absolute() and _base is not None:
                    pp = _base / pp
                try:
                    return str(pp.resolve())
                except (OSError, ValueError):
                    return str(pp)  # optional: resolve 失败(路径不存在)回退未 resolve 版

            return [row for row in rows if _norm_exp(row.get("exp_dir", "")) != cur_dir]
        return rows

    def _direction_for_metric_key(self, key: str) -> str | None:
        if key in self.metric_keys:
            return self.metric_keys[key]
        if key in self.auxiliary_keys:
            return self.auxiliary_keys[key]
        return None

    def _check_metric_key_exclusive(self) -> None:
        # ledger 来源 = YAML (nn-config.yaml["ledger"]["watchlist"]) ∪ Contract override
        # （YAML 优先；Contract 仅 fallback，detail 见 property + _load_ledger_watchlist）
        # 显式 union 防御未来 property 行为漂移
        ledger = set(self.ledger_context_keys) | set(_load_ledger_watchlist())
        overlap = set(self.metric_keys) & set(self.auxiliary_keys)
        if overlap:
            raise ValueError(f"metric_keys 与 auxiliary_keys 存在重叠: {overlap}")
        if SCENARIO_ID_COLUMN in self.metric_keys or SCENARIO_ID_COLUMN in self.auxiliary_keys:
            raise ValueError(f"scenario_id 与 metric 键重叠: {SCENARIO_ID_COLUMN!r}")
        if SCENARIO_ID_COLUMN in ledger:
            raise ValueError(
                f"scenario_id 与 ledger (YAML ∪ Contract) 重叠: {SCENARIO_ID_COLUMN!r}"
            )
        if ledger & set(self.metric_keys):
            raise ValueError(
                f"ledger (YAML ∪ Contract) 与 metric_keys 重叠: {ledger & set(self.metric_keys)}"
            )
        if ledger & set(self.auxiliary_keys):
            raise ValueError(
                f"ledger (YAML ∪ Contract) 与 auxiliary_keys 重叠: {ledger & set(self.auxiliary_keys)}"
            )
        loss_keys = set(self.loss_log_keys)
        reserved = set(self.metric_keys) | set(self.auxiliary_keys) | ledger | {SCENARIO_ID_COLUMN, "train_loss", "lr"}
        overlap_loss = loss_keys & reserved
        if overlap_loss:
            raise ValueError(f"loss_log_keys 与 reserved 键重叠: {overlap_loss}")
        if not self.metric_keys:
            raise ValueError("metric_keys 不能为空")

    def _should_keep_multi_primary(
        self,
        current_metrics: dict[str, float],
        history_rows: list[dict[str, str]],
        *,
        spec: dict,
        improve_mode: str,
        aux_checks: dict,
    ) -> tuple[bool, str, dict]:
        """``improve_mode`` 为 ``any_primary``（任一达标）或 ``all_primary``（全部达标）。"""
        keys = list(self.primary_metric_keys)
        mode = str(spec.get("mode", "absolute"))
        delta = float(spec.get("primary_delta", 0.0))
        near_tol = float(spec.get("near_best_abs", 0.0))

        if not history_rows:
            return True, "无历史 TSV 可比，默认可 keep", aux_checks

        strict_ok: list[str] = []
        near_ok: list[str] = []
        no_hist: list[str] = []
        failed: list[str] = []
        for key in keys:
            direction = self._direction_for_metric_key(key)
            if direction is None:
                failed.append(f"{key}=无方向")
                continue
            if key not in current_metrics:
                failed.append(f"{key}=缺失")
                continue
            cur = float(current_metrics[key])
            if math.isnan(cur):
                failed.append(f"{key}=nan")
                continue
            best = _history_best_metric(history_rows, key, direction)
            if best is None:
                no_hist.append(key)
                continue
            if _primary_improved(cur, best, delta=delta, mode=mode, direction=direction):
                strict_ok.append(key)
                continue
            if near_tol > 0.0 and _metric_near_best(cur, best, direction, near_tol):
                near_ok.append(key)
                continue
            diff = cur - best if direction == "maximize" else best - cur
            failed.append(f"{key} {cur:.4f} vs {best:.4f} (Δneed {delta}, got {diff:.4f})")

        passed = bool(strict_ok or near_ok or no_hist)
        if improve_mode == "any_primary":
            if passed:
                parts: list[str] = []
                if strict_ok:
                    parts.append("严格改善: " + ", ".join(strict_ok))
                if near_ok:
                    parts.append(f"接近最佳(near_best_abs={near_tol}): " + ", ".join(near_ok))
                if no_hist:
                    parts.append("无历史: " + ", ".join(no_hist))
                return True, "任一主指标达标: " + "；".join(parts), aux_checks
            snap = ", ".join(failed) if failed else "（无有效主指标）"
            return False, f"无一主指标达标（near_best_abs={near_tol}）: {snap}", aux_checks

        if not failed:
            ok_parts = (
                [f"{k}↑" for k in strict_ok]
                + [f"{k}≈best" for k in near_ok]
                + [f"{k}(无历史)" for k in no_hist]
            )
            return True, "全部主指标达标: " + ", ".join(ok_parts), aux_checks
        ok_parts = (
            [f"{k}↑" for k in strict_ok]
            + [f"{k}≈best" for k in near_ok]
            + [f"{k}(无历史)" for k in no_hist]
        )
        return (
            False,
            "未全部主指标达标; 失败: " + "; ".join(failed) + " | 通过: " + ", ".join(ok_parts),
            aux_checks,
        )

    def prepare_data(self, cfg: dict) -> Any:
        raise NotImplementedError

    def test(self, learner: Any, ws: Any, *, shared_context: dict) -> dict[str, float]:
        """官方台账评估。**必须**在 contract 子类自主实现（禁止调用 ws.evaluate）。

        ws.evaluate 可调用 contract.test 复用口径，不可反向。台账参数（数据集、
        eval 模式、episode 数等）由 contract.test 决定，在 contract/test.run 内实现。
        """
        raise NotImplementedError("contract.test() must be implemented by each project")

    # ── Workspace 侧（由 workspace/ 目录覆盖） ──────────────

    def build_learner(self, cfg: dict, source=None) -> Any:
        raise NotImplementedError

    def build_objective(self, cfg: dict) -> Any:
        raise NotImplementedError

    def train_step(self, learner: Any, source: Any, objective: Any, *, epoch: int, shared_context: dict) -> dict:
        raise NotImplementedError

    def predict(self, learner: Any, batch: Any, *, shared_context: dict) -> Any:
        raise NotImplementedError

    def evaluate(self, learner: Any, *, shared_context: dict) -> dict:
        raise NotImplementedError

    # ── should_keep 默认实现 ───────────────────────────────

    def should_keep(
        self,
        current_metrics: dict[str, float],
        history_rows: list[dict[str, str]],
        *,
        current_scenario_id: str | None = None,
        current_exp_dir: Path | None = None,
    ) -> tuple[bool, str, dict]:
        spec = self._effective_keep_spec()
        history_rows = self._filter_history_for_keep(
            history_rows,
            current_scenario_id=(current_scenario_id or ""),
            current_exp_dir=current_exp_dir,
        )
        mode = str(spec.get("mode", "absolute"))
        delta = float(spec.get("primary_delta", 0.0))
        improve_mode = str(spec.get("improve_mode", "primary")).strip().lower()
        near_tol = float(spec.get("near_best_abs", 0.0))

        guards = spec.get("aux_guards") or {}
        prev_row = history_rows[-1] if history_rows else None
        prev_metrics = (
            {k: float(_float_metric(prev_row, k) or 0) for k in self.auxiliary_keys if _float_metric(prev_row, k) is not None}
            if prev_row else None
        )
        curr_aux = {k: float(current_metrics[k]) for k in self.auxiliary_keys if k in current_metrics}

        ok_guard, aux_checks = _check_aux_guards(curr_aux, prev_metrics, guards, self.auxiliary_keys)
        if not ok_guard:
            result: tuple[bool, str, dict] = (False, "auxiliary guard 未通过", aux_checks)
        else:
            result = None
            root = Path(__file__).resolve().parent
            _ensure_scripts_on_path(root)
            try:
                from lib.explore_objective import (
                    effective_objective,
                    evaluate_explore_keep,
                    explore_attested_for_exp,
                )

                res = effective_objective(root)
                if res.mode == "explore" and not res.migration_blocked:
                    attested = False
                    if current_exp_dir is not None:
                        attested = explore_attested_for_exp(root, Path(current_exp_dir))
                    ok_exp, exp_reason = evaluate_explore_keep(
                        root,
                        scenario_id=(current_scenario_id or ""),
                        history_rows=history_rows,
                        attested=attested,
                    )
                    if ok_exp:
                        result = (True, exp_reason, aux_checks)
            except ImportError:
                pass  # optional: explore_objective 未装 → 跳过 explore keep，走常规 keep 逻辑

            if result is None and improve_mode in ("all_primary", "any_primary"):
                result = self._should_keep_multi_primary(
                    current_metrics, history_rows, spec=spec, improve_mode=improve_mode, aux_checks=aux_checks,
                )

            if result is None and not history_rows:
                result = (True, "无历史 TSV 可比，默认可 keep", aux_checks)

            if result is None and improve_mode == "any_metric":
                keys: list[str] = []
                seen: set[str] = set()
                for k in (*self.metric_keys.keys(), *self.auxiliary_keys.keys()):
                    if k in seen:
                        continue
                    seen.add(k)
                    keys.append(k)
                strict_ok: list[str] = []
                near_ok: list[str] = []
                for key in keys:
                    if key not in current_metrics:
                        continue
                    direction = self.metric_keys.get(key) or self.auxiliary_keys.get(key)
                    if not direction:
                        continue
                    best = _history_best_metric(history_rows, key, direction)
                    if best is None:
                        continue
                    cur = float(current_metrics[key])
                    if _metric_strictly_improved(cur, best, direction):
                        strict_ok.append(key)
                    elif _metric_near_best(cur, best, direction, near_tol):
                        near_ok.append(key)
                if strict_ok or near_ok:
                    parts: list[str] = []
                    if strict_ok:
                        parts.append("严格改善: " + ", ".join(strict_ok))
                    if near_ok:
                        parts.append(
                            "接近最佳(near_best_abs="
                            f"{near_tol}): "
                            + ", ".join(near_ok),
                        )
                    result = (True, "；".join(parts), aux_checks)
                else:
                    snap = ", ".join(
                        f"{k}={float(current_metrics[k]):.6f}"
                        for k in keys
                        if k in current_metrics
                    )
                    result = (
                        False,
                        f"主指标与辅助指标均未相对历史最佳改善或接近（near_best_abs={near_tol}）。当前 {{{snap}}}",
                        aux_checks,
                    )

            if result is None:
                best_hist = _history_best_metric(history_rows, self.metric_key, self.metric_direction)
                if best_hist is None:
                    result = (True, "无历史 TSV 可比，默认可 keep", aux_checks)
                else:
                    primary = float(current_metrics[self.metric_key])
                    improved = _primary_improved(primary, best_hist, delta=delta, mode=mode, direction=self.metric_direction)
                    diff = primary - best_hist if self.metric_direction == "maximize" else best_hist - primary

                    if improved:
                        result = (
                            True,
                            f"主指标较历史最佳提升满足阈值：当前 {primary:.6f}，历史最佳 {best_hist:.6f}，"
                            f"diff={diff:.6f} (mode={mode}, delta={delta})",
                            aux_checks,
                        )
                    elif near_tol > 0.0 and _metric_near_best(primary, best_hist, self.metric_direction, near_tol):
                        result = (
                            True,
                            f"主指标未达 primary_delta，但在 near_best_abs={near_tol} 内接近历史最佳："
                            f"当前 {primary:.6f}，历史最佳 {best_hist:.6f}，净差 {diff:.6f}",
                            aux_checks,
                        )
                    else:
                        result = (
                            False,
                            f"主指标未达阈值且未接近最佳：当前 {primary:.6f}，历史最佳 {best_hist:.6f}，"
                            f"mode={mode} delta={delta}，净差 {diff:.6f}，near_best_abs={near_tol}",
                            aux_checks,
                        )

        return result

    # ── Preflight ────────────────────────────────────────

    def preflight_check(
        self,
        learner=None,
        loss_fn: Callable[[], Any] | None = None,
        *,
        grad_clip: float = 1.0,
        finalize_fn: Callable[[], None] | None = None,
        label: str = "Pre-flight",
        cfg: dict[str, Any] | None = None,
        train_batch: Any = None,
    ) -> float:
        _pf = os.environ.get("NN_PREFLIGHT", "1").strip().lower()
        if _pf in ("0", "false", "no", "off"):
            print(f"[{label}] skipped (NN_PREFLIGHT=0)", file=sys.stderr, flush=True)
            return 0.0

        repo_root = Path(__file__).resolve().parent
        print(f"[{label}] 静态守门 (G-封装–G-评估–G-信息权限–G-台账–G-布局) ...", file=sys.stderr, flush=True)
        _run_static_preflight_guards(repo_root)
        _guard_train_batch_keys(repo_root, train_batch)  # G-信息权限（动态）：首 batch 键白名单
        self._check_metric_key_exclusive()
        _guard_results_tsv_header(repo_root, self)
        _guard_scenario_id(repo_root, cfg, contract=self)
        print(f"[{label}] 静态守门 OK", file=sys.stderr, flush=True)

        write_train_pid(repo_root)
        print(f"[{label}] PID 文件已写入 saved/.train_pid", file=sys.stderr, flush=True)

        v = 0.0
        if learner is not None and loss_fn is not None:
            print(f"[{label}] 验证 loss → autograd → backward ...", file=sys.stderr, flush=True)
            v = _verify_loss_fn(learner, loss_fn, grad_clip=grad_clip)
            print(f"[{label}] loss OK (total={v:.4e})", file=sys.stderr, flush=True)

        if finalize_fn is not None:
            print(f"[{label}] 验证 finalize_run ...", file=sys.stderr, flush=True)
            finalize_fn()
            print(f"[{label}] finalize OK", file=sys.stderr, flush=True)

        return v

    # ── Checkpoint / 报告 ────────────────────────────────

    def save_checkpoint(
        self,
        exp_dir: str | os.PathLike,
        *,
        repo_root: str | os.PathLike,
        cfg: dict[str, Any],
        official_metrics: dict[str, float],
        policy: str | None = None,
        best_state: dict[str, Any] | None = None,
        last_state: dict[str, Any] | None = None,
        best_epoch: int = 0,
        last_epoch: int = 0,
        train_eval_metrics: dict[str, float] | None = None,
    ) -> Path | None:
        """按 ``checkpoint`` 策略写入 ``best_model.pt``（KEEP 复制此文件；内含完整 ``train_cfg``）。

        - **best**：优先训内 ``evaluate`` 最优权重（``best_state``），否则训末 ``last_state``
        - **last**：训末最后一轮权重（``last_state``）
        - **none**：不写文件
        """
        pol = (policy or resolve_checkpoint_policy(repo_root, cfg)).lower()
        if pol == "none":
            print("[checkpoint] policy=none，跳过 best_model.pt", file=sys.stderr, flush=True)
            return None

        state: dict[str, Any] | None = None
        selection = ""
        epoch_saved = 0
        if pol == "last":
            if last_state is not None:
                state = last_state
                selection = "last_epoch"
                epoch_saved = last_epoch
            elif best_state is not None:
                state = best_state
                selection = "best_train_eval_fallback"
                epoch_saved = best_epoch
        else:
            if best_state is not None:
                state = best_state
                selection = "best_train_eval"
                epoch_saved = best_epoch
            elif last_state is not None:
                state = last_state
                selection = "last_epoch_fallback"
                epoch_saved = last_epoch

        if state is None:
            print("[checkpoint] 警告：无 state_dict，跳过保存", file=sys.stderr, flush=True)
            return None

        root = Path(repo_root).resolve()
        out_path = Path(exp_dir).resolve() / "best_model.pt"
        ckpt: dict[str, Any] = {
            "checkpoint_policy": pol,
            "selection": selection,
            "kind": cfg.get("CHECKPOINT_KIND", self.checkpoint_kind),
            "state_dict": _state_dict_cpu(state),
            "metrics_official": dict(official_metrics),
            "metric_key": self.metric_key,
            "epoch_saved": epoch_saved,
            "best_epoch": int(best_epoch),
            "last_epoch": int(last_epoch),
            "train_cfg": json_safe_train_cfg(cfg),
            "git_commit": _git_head_short(root),
        }
        if train_eval_metrics:
            ckpt["metrics_train_eval"] = dict(train_eval_metrics)
        torch.save(ckpt, out_path)
        print(
            f"[checkpoint] policy={pol} selection={selection} epoch={epoch_saved} → {out_path}",
            file=sys.stderr,
            flush=True,
        )
        return out_path

    def report_results(self, metrics: dict, elapsed: float, *, extra_json_paths: list[Path | str] | None = None) -> None:
        clean: dict[str, object] = {}
        for k, v in sorted(metrics.items()):
            if isinstance(v, float):
                if math.isnan(v) or math.isinf(v):
                    print(f"WARNING: {k} = {v} (non-finite)", file=sys.stderr)
                    continue
                print(f"{k}: {v:.6f}")
                clean[k] = round(v, 6)
            else:
                print(f"{k}: {v}")
                clean[k] = v
        print(f"elapsed_sec: {elapsed:.1f}")

        output = {"metrics": clean, "elapsed_sec": round(elapsed, 2)}
        paths = [Path(p) for p in (extra_json_paths or [])]
        for p in paths:
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("w", encoding="utf-8") as f:
                json.dump(output, f, indent=2)

    def _train_metrics_for_series(
        self,
        train_metrics: dict[str, Any],
        optimizer: Any | None,
    ) -> dict[str, Any]:
        row: dict[str, Any] = {}
        if "train_loss" in train_metrics:
            row["train_loss"] = float(train_metrics["train_loss"])
        for k in self.loss_log_keys:
            if k in train_metrics:
                row[k] = train_metrics[k]
        # optional: 自动纳入未声明但疑似 loss 的分量（key 名含 loss），避免静默丢弃 train_step
        # 新增的 loss 分量（B2）。首次发现每个 key WARN 一次，提示在 loss_log_keys 显式声明。
        declared = {"train_loss", *self.loss_log_keys}
        warned = getattr(self, "_auto_loss_warned", None)
        if warned is None:
            warned = set()
        for k, v in train_metrics.items():
            if k in declared or k in row or "loss" not in k.lower():
                continue
            try:
                row[k] = float(v)
            except (TypeError, ValueError):
                continue  # optional: 非标量 loss 分量（如 dict）跳过，不阻断
            if k not in warned:
                warned.add(k)
                print(
                    f"WARNING: 检测到未声明的 loss 分量 '{k}'，已自动纳入 metrics_series；"
                    f"建议在子类 loss_log_keys 显式声明。",
                    file=sys.stderr,
                )
        self._auto_loss_warned = warned
        if optimizer is not None and hasattr(optimizer, "param_groups"):
            try:
                row["lr"] = float(optimizer.param_groups[0]["lr"])
            except (IndexError, KeyError, TypeError, ValueError):
                pass  # optional: param_groups 结构异常/无 lr → 省略 lr 列（台账描述性）
        return row

    def _warn_non_finite_metrics(
        self,
        metrics: dict[str, Any],
        *,
        epoch: int | None = None,
    ) -> None:
        """B3: 轻量 nan/inf 实时检查（WARN 级 stderr，不阻断）。

        每 epoch 由 record_train_epoch 调用一次，对标量值查 non-finite（nan/inf），
        命中即 WARN 一条——让 round-doctor / reflect 立刻看到"本轮 loss 曾 NaN"。
        不阻断：不 raise、不影响写盘。非标量值（str/dict）float() 失败即跳过。
        """
        for k, v in metrics.items():
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue  # optional: 非标量 metrics（如 str/dict）float 失败即跳过，不阻断
            if math.isfinite(fv):
                continue
            tag = f"epoch {epoch} " if epoch is not None else ""
            print(
                f"WARNING: {tag}检测到 non-finite 值 {k}={v}（nan/inf）；"
                f"训练继续不阻断，请检查 loss/lr/数据。",
                file=sys.stderr,
                flush=True,
            )

    def record_metrics(
        self,
        exp_dir: str | os.PathLike,
        *,
        step: int,
        step_kind: str,
        phase: str,
        metrics: dict[str, Any],
    ) -> None:
        """Append 一行 ``exp_dir/metrics_series.tsv``（训中过程分析；不参与 KEEP）。"""
        exp_p = Path(exp_dir).resolve()
        root = _resolve_repo_root(exp_p)
        _ensure_scripts_on_path(root)
        from lib.train_dynamics import append_metrics_row  # noqa: WPS433

        append_metrics_row(
            exp_p,
            step=int(step),
            step_kind=str(step_kind),
            phase=str(phase),
            metrics=metrics,
        )

    def record_train_epoch(
        self,
        exp_dir: str | os.PathLike,
        epoch: int,
        train_metrics: dict[str, Any],
        optimizer: Any | None,
        timer: Any | None = None,
    ) -> None:
        """supervised：每 epoch 末写入 ``epoch_train``（含 train_loss / loss_log_keys）。"""
        _ = timer
        self._warn_non_finite_metrics(train_metrics, epoch=epoch)
        row = self._train_metrics_for_series(train_metrics, optimizer)
        if not row:
            return
        self.record_metrics(
            exp_dir, step=int(epoch), step_kind="epoch_train", phase="training", metrics=row,
        )

    def record_eval_epoch(
        self,
        exp_dir: str | os.PathLike,
        epoch: int,
        train_metrics: dict[str, Any],
        eval_metrics: dict[str, float],
        optimizer: Any | None,
        timer: Any | None = None,
    ) -> None:
        """supervised：evaluate 当轮写入 ``epoch_eval``（train_loss + 主/辅指标）。"""
        _ = timer
        row = self._train_metrics_for_series(train_metrics, optimizer)
        row[self.metric_key] = float(eval_metrics[self.metric_key])
        for k in self.auxiliary_keys:
            if k in eval_metrics:
                row[k] = eval_metrics[k]
        self.record_metrics(
            exp_dir, step=int(epoch), step_kind="epoch_eval", phase="training", metrics=row,
        )

    def log_step(self, step: int, metrics: dict) -> None:
        parts = [f"step={step}"]
        for k, v in metrics.items():
            if isinstance(v, float):
                parts.append(f"{k}={v:.4f}")
            else:
                parts.append(f"{k}={v}")
        print(" | ".join(parts), file=sys.stderr, flush=True)

    def progress_log_dict(self, *, train_loss: float, eval_metrics: dict[str, float], optimizer: Any, timer: TimeGuard) -> dict[str, Any]:
        row: dict[str, Any] = {
            "train_loss": train_loss,
            self.metric_key: eval_metrics[self.metric_key],
            "lr": optimizer.param_groups[0]["lr"],
            "remaining": f"{timer.remaining:.0f}s",
        }
        for k in self.aux_metrics:
            if k in eval_metrics:
                row[k] = eval_metrics[k]
        return row

    def post_train_hook(
        self,
        *,
        repo_root: Path,
        exp_dir: Path,
        learner: Any,
        cfg: dict,
        device: torch.device,
        contract: Any,
        shared_context: dict,
        experiment: str,
        best_state: dict | None,
        official_metrics: dict[str, float],
        **kwargs: Any,
    ) -> None:
        """课题可选：训后可视化/额外产物。默认 no-op；在 workspace.Workspace 子类中覆盖。"""
        return

    # ── TSV 台账 ──────────────────────────────────────────

    def append_tsv_row(
        self,
        metrics: dict[str, Any],
        *,
        repo_root: str | os.PathLike,
        experiment: str,
        description: str,
        exp_dir: str = "",
        elapsed_sec: float = 0,
        notes: str | None = None,
        ledger_context: dict[str, Any] | None = None,
        scenario_context: dict[str, Any] | None = None,
        tsv_rel: str = "_runs/results.tsv",
    ) -> None:
        if not _append_results_tsv_enabled():
            return
        root = Path(repo_root).resolve()
        path = root / tsv_rel
        experiment = _escape_tsv_field(experiment.strip() or "unnamed")
        description = _escape_tsv_field(description.strip())
        # v2.7.4: exp_dir 列存相对 repo_root(换机不断链), 集中在此相对化,
        # 所有调用方(report_train_artifacts/finalize_round)无需逐个改
        exp_dir = _to_repo_rel(root, exp_dir) if exp_dir else ""
        exp_dir_cell = _escape_tsv_field(exp_dir.strip())

        if path.is_file() and path.stat().st_size > 0:
            existing = _read_tsv_header(path)
            if existing and "exp_dir" not in existing:
                _upgrade_tsv_add_exp_dir_column(path)
            if existing and "elapsed_sec" not in existing:
                _ensure_tsv_elapsed_sec(path)
            if existing and "timestamp" not in existing:
                _upgrade_tsv_add_timestamp_column(path)
            if existing and "notes" not in existing:
                _upgrade_tsv_add_notes_column(path)
            # 升级可能改写了表头，缺 overlay 列时按最新 header 再判一次
            existing = _read_tsv_header(path) or existing
            if existing and "exploration_space" not in existing:
                _upgrade_tsv_add_exploration_space_column(path)
            existing = _read_tsv_header(path) or existing
            if existing and "untrained" not in existing:
                _upgrade_tsv_add_untrained_column(path)

        new_file = (not path.is_file()) or path.stat().st_size == 0
        header = None if new_file else _read_tsv_header(path)
        if header is None:
            header = self._default_tsv_columns()
        write_header = new_file

        git_c = _git_head_short(root)
        notes_cell = notes if notes is not None else _build_notes_cell(_resolve_notes_human(None), metrics, self)
        row_map: dict[str, str] = {
            "experiment": experiment,
            "git_commit": git_c,
            "exp_dir": exp_dir_cell,
            "description": description,
            "notes": notes_cell,
            "elapsed_sec": _format_metric_cell(elapsed_sec),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for key, val in (scenario_context or {}).items():
            row_map[key] = _format_metric_cell(val)
        ctx = ledger_context or {}
        for key in self._effective_ledger_context_keys():
            if key in ctx:
                row_map[key] = _format_metric_cell(ctx[key])
            else:
                row_map[key] = ""
        for k, v in metrics.items():
            row_map[k] = _format_metric_cell(v)

        if not new_file and header and self.metric_key not in header:
            print(
                f"[台账] 警告: 表头无 {self.metric_key!r}，本条指标不会写入 TSV。"
                " 请运行: python3 scripts/regen_results_tsv.py --repo-root .",
                file=sys.stderr,
                flush=True,
            )
        elif (
            not new_file
            and header
            and self.metric_key in metrics
            and row_map.get(self.metric_key, "").strip() == ""
            and _format_metric_cell(metrics[self.metric_key]).strip() != ""
        ):
            print(
                f"[台账] 警告: {self.metric_key} 有值但未写入 TSV 列，请检查表头是否与 contract 一致。",
                file=sys.stderr,
                flush=True,
            )

        cells = [row_map.get(col, "") for col in header]
        line = "\t".join(cells) + "\n"

        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "w" if new_file else "a"
        with path.open(mode, encoding="utf-8") as f:
            if write_header:
                f.write("\t".join(header) + "\n")
            f.write(line)
        print(f"台账已追加 {tsv_rel}：experiment={experiment} git_commit={git_c}", file=sys.stderr, flush=True)

    def _default_tsv_columns(self) -> list[str]:
        """TSV 四区：场景 | metrics | parameters | 运行/notes（见 metric-and-keep-system §3.5）。

        spec T-A1: ``metric_keys`` 为空时 ``self.metric_key`` 为 None，
        此时主列占位为空字符串（不写 None 触发下游 str() 失败）。
        """
        primary_col = self.metric_key or ""
        metric_rest = sorted(
            (set(self.metric_keys.keys()) | set(self.auxiliary_keys.keys())) - {self.metric_key}
        )
        return [
            "experiment",
            SCENARIO_ID_COLUMN,
            primary_col,
            *metric_rest,
            *list(self._effective_ledger_context_keys()),
            "elapsed_sec",
            "git_commit",
            "exp_dir",
            "description",
            "notes",
            "timestamp",
        ]

    # ── JSONL 台账 ───────────────────────────────────────

    def append_jsonl_record(
        self,
        *,
        repo_root: str | os.PathLike,
        metrics: dict[str, Any],
        elapsed_sec: float,
        experiment: str = "",
        exp_dir: str = "",
        description: str = "",
        notes: str | None = None,
        scenario_context: dict[str, Any] | None = None,
        train_mat_path: str = "",
        eval_mat_path: str = "",
        jsonl_rel: str = "_runs/results.jsonl",
    ) -> None:
        if not _append_results_jsonl_enabled():
            return
        root = Path(repo_root).resolve()
        path = root / jsonl_rel
        ex = (experiment or "").strip()
        if not ex and exp_dir:
            ex = Path(exp_dir).name
        if not ex:
            ex = "unnamed"
        experiment = _escape_tsv_field(ex)
        description = _escape_tsv_field(description.strip())
        # v2.7.4: exp_dir/train_mat_path/eval_mat_path 存相对 repo_root
        exp_dir_rel = _to_repo_rel(root, exp_dir) if exp_dir else ""

        sid = str((scenario_context or {}).get(SCENARIO_ID_COLUMN, "") or "").strip()
        record: dict[str, Any] = {
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "schema_version": 2 if sid else 1,
            "kind": "train_end",
            "metric_key": self.metric_key,
            "experiment": experiment,
            "git_commit": _git_head_short(root),
            "exp_dir": exp_dir_rel,
            "elapsed_sec": round(float(elapsed_sec), 2),
            "metrics": _clean_metrics_dict(metrics),
        }
        if sid:
            record[SCENARIO_ID_COLUMN] = sid
        if description:
            record["description"] = description
        notes_cell = notes if notes is not None else _build_notes_cell(_resolve_notes_human(None), metrics, self)
        if notes_cell:
            record["notes"] = notes_cell
        if train_mat_path:
            record["train_mat_path"] = _to_repo_rel(root, train_mat_path)
        if eval_mat_path:
            record["eval_mat_path"] = _to_repo_rel(root, eval_mat_path)

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"台账已追加 {jsonl_rel}: experiment={experiment}", file=sys.stderr, flush=True)

    # ── 训末快照 ─────────────────────────────────────────

    def report_train_exp_snapshot(
        self, metrics: dict[str, Any], elapsed: float, *, repo_root: str | os.PathLike, exp_dir: str | os.PathLike, experiment: str | None = None, description: str | None = None, train_mat_path: str = "", eval_mat_path: str = "", results_json_name: str = "results.json",
    ) -> None:
        """只写 ``exp_dir/results.json``；仓库级 ``_runs/results.tsv`` / ``_runs/results.jsonl`` 仅由 ``finalize_round``（或 ``report_train_artifacts``）经 ``_append_repo_ledger_row`` **成对**追加。"""
        exp_p = Path(exp_dir).resolve()
        self.report_results(metrics, elapsed, extra_json_paths=[exp_p / results_json_name])

    def report_train_artifacts(
        self,
        metrics: dict[str, Any],
        elapsed: float,
        *,
        repo_root: str | os.PathLike,
        exp_dir: str | os.PathLike,
        experiment: str | None = None,
        description: str | None = None,
        notes: str | None = None,
        cfg: dict[str, Any] | None = None,
        results_json_name: str = "results.json",
        append_repo_ledger: bool | None = None,
    ) -> None:
        exp_p = Path(exp_dir).resolve()
        self.report_train_exp_snapshot(
            metrics, elapsed, repo_root=repo_root, exp_dir=str(exp_p),
            experiment=experiment, description=description, results_json_name=results_json_name,
        )
        if not resolve_append_repo_ledger(experiment, append_repo_ledger):
            print(
                "[台账] preflight：跳过 _runs/results.tsv / results.jsonl（仅写 exp_dir 快照）",
                file=sys.stderr,
                flush=True,
            )
            return
        ex = (experiment if experiment is not None else os.environ.get("NN_EXPERIMENT", "")).strip()
        desc = (description if description is not None else os.environ.get("NN_EXPERIMENT_DESC", "")).strip()
        ex_led = ex or exp_p.name
        ledger_ctx = _extract_ledger_context(self, cfg)
        self._append_repo_ledger_row(
            metrics=metrics, repo_root=repo_root, experiment=ex_led, description=desc,
            exp_dir=str(exp_p), elapsed_sec=elapsed, notes=notes, ledger_context=ledger_ctx,
            cfg=cfg if isinstance(cfg, dict) else None,
        )

    def _append_repo_ledger_row(
        self,
        *,
        metrics: dict[str, Any],
        repo_root: str | os.PathLike,
        experiment: str,
        description: str,
        exp_dir: str,
        elapsed_sec: float,
        notes: str | None = None,
        ledger_context: dict[str, Any] | None = None,
        scenario_context: dict[str, Any] | None = None,
        cfg: dict[str, Any] | None = None,
    ) -> None:
        if ledger_context is None and isinstance(cfg, dict) and cfg:
            ledger_context = _extract_ledger_context(self, cfg)
        # 须捕获返回值；丢弃会导致 merged_scenario.update(validated_scenario) NameError
        validated_scenario = _resolve_validated_scenario_context(repo_root, cfg, contract=self)
        merged_scenario = dict(scenario_context or {})
        merged_scenario.update(validated_scenario)
        mode = _repo_ledger_sync_mode()
        if mode == "mismatch":
            print(
                "[台账] 警告：NN_APPEND_RESULTS_TSV 与 NN_APPEND_RESULTS_JSONL 不一致；"
                "为保持 _runs/results.tsv 与 _runs/results.jsonl 同步，已跳过本条仓库台账追加。"
                "请将两变量设为相同（均为 1 或均为 0）。",
                file=sys.stderr,
                flush=True,
            )
            return
        if mode == "skip":
            return
        notes_cell = _build_notes_cell(_resolve_notes_human(notes), metrics, self)
        self.append_tsv_row(
            metrics, repo_root=repo_root, experiment=experiment, description=description,
            exp_dir=exp_dir, elapsed_sec=elapsed_sec, notes=notes_cell,
            ledger_context=ledger_context, scenario_context=merged_scenario,
        )
        self.append_jsonl_record(
            repo_root=repo_root, metrics=metrics, elapsed_sec=elapsed_sec,
            experiment=experiment, exp_dir=exp_dir, description=description, notes=notes_cell,
            scenario_context=merged_scenario,
        )

    # ── Snapshot ─────────────────────────────────────────

    def snapshot_code(self, exp_dir: str | os.PathLike, repo_root: str | os.PathLike) -> Path | None:
        import shutil
        root = Path(repo_root).resolve()
        dest = Path(exp_dir).resolve() / "code_snapshot"
        dest.mkdir(parents=True, exist_ok=True)
        copied: list[str] = []

        tp = root / "train.py"
        if tp.is_file():
            shutil.copy2(tp, dest / "train.py")
            copied.append("train.py")

        ws = root / "workspace"
        if ws.is_dir():
            ws_dest = dest / "workspace"
            if ws_dest.exists():
                shutil.rmtree(ws_dest)
            shutil.copytree(ws, ws_dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            copied.append("workspace/")

        # contract/：供开闸改题后 executed 对照；不进入 A–D 打格路径扫描
        ct = root / "contract"
        if ct.is_dir():
            ct_dest = dest / "contract"
            if ct_dest.exists():
                shutil.rmtree(ct_dest)
            shutil.copytree(ct, ct_dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            copied.append("contract/")

        if not copied:
            return None
        print(f"code_snapshot: {', '.join(copied)} → {dest}", file=sys.stderr, flush=True)
        return dest

    def snapshot_env(
        self,
        exp_dir: str | os.PathLike,
        repo_root: str | os.PathLike,
        *,
        contract: Any = None,
    ) -> Path:
        import importlib
        import platform

        exp_p = Path(exp_dir).resolve()
        env: dict[str, Any] = {
            "python": sys.version,
            "python_executable": sys.executable,
            "platform": platform.platform(),
            "hostname": platform.node(),
            "torch_version": torch.__version__,
            "cuda_available": torch.cuda.is_available(),
            "cuda_version": torch.version.cuda if torch.cuda.is_available() else None,
            "cudnn_version": str(torch.backends.cudnn.version()) if torch.cuda.is_available() else None,
            "gpus": [],
            "git_commit": _git_head_short(Path(repo_root).resolve()),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                env["gpus"].append({"index": i, "name": props.name, "total_memory_mb": round(props.total_memory / 1024 / 1024)})

        dep_pkgs = ["numpy", "scipy", "scikit-learn", "pandas", "einops", "timm", "transformers", "accelerate", "matplotlib", "tensorboard", "tqdm"]
        deps: dict[str, str | None] = {}
        for pkg in dep_pkgs:
            try:
                mod = importlib.import_module(pkg)
                deps[pkg] = getattr(mod, "__version__", "installed")
            except ImportError:
                pass  # optional: 依赖未安装 → 不记入 env snapshot（探测契约）
        if deps:
            env["dependencies"] = deps

        try:
            r = subprocess.run(["poetry", "show", "--no-dev"], cwd=str(repo_root), capture_output=True, text=True, timeout=15)
            if r.returncode == 0 and r.stdout.strip():
                env["poetry_show"] = r.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass  # optional: poetry 不可用/超时 → 省略 poetry_show（env snapshot 描述性）

        env["repro"] = build_repro_snapshot(contract if contract is not None else self)

        out = exp_p / "env_snapshot.json"
        with open(out, "w", encoding="utf-8") as f:
            json.dump(env, f, indent=2, ensure_ascii=False)
        print(f"env_snapshot: → {out}", file=sys.stderr, flush=True)
        return out

    # ── Finalize ─────────────────────────────────────────

    def finalize_run(
        self, *, repo_root: str | os.PathLike, cfg: dict[str, Any], timer: TimeGuard,
        best_state: dict | None, exp_dir: str | os.PathLike | None = None,
        experiment: str | None = None, best_epoch: int = 0, last_epoch: int = 0,
        train_eval_metrics: dict[str, float] | None = None,
        contract: Any = None, ws: Any = None, learner: Any = None,
        shared_context: dict | None = None,
        precomputed_official_metrics: dict[str, float] | None = None,
        append_repo_ledger: bool | None = None,
    ) -> Path:
        root = Path(repo_root).resolve()
        if exp_dir is not None:
            exp_path = Path(exp_dir).resolve()
            exp_path.mkdir(parents=True, exist_ok=True)
            experiment = (experiment or os.environ.get("NN_EXPERIMENT", "").strip() or "unnamed").strip()
        else:
            exp_tag = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{os.getpid()}"
            experiment = os.environ.get("NN_EXPERIMENT", "").strip() or f"run_{exp_tag}"
            exp_path = root / "_runs" / "exp" / f"{exp_tag}_{experiment}"
            exp_path.mkdir(parents=True, exist_ok=True)

        _repro_src = contract if contract is not None else self
        _bypasses = collect_guard_bypasses()  # G-信息权限 §4.3：旁路留痕（NN_PREFLIGHT / NN_GUARD*=0）
        with open(exp_path / "config.json", "w", encoding="utf-8") as f:
            if isinstance(cfg, dict):
                _safe_cfg: dict[str, Any] = dict(json_safe_train_cfg(cfg))
                _safe_cfg["_repro"] = build_repro_snapshot(_repro_src)
                _safe_cfg["_repro"]["guards_bypassed"] = list(_bypasses)
                _safe_cfg.setdefault("baseline_tag", "none")  # ② 层2：兜底字段存在，默认 none
            else:
                _safe_cfg = cfg
            json.dump(_safe_cfg, f, indent=2, ensure_ascii=False)
        # 合同 enforce=True 且带旁路 → 留痕后抛错：不写台账、不判 KEEP（对照关臂 enforce=False 放行）
        _raise_if_bypassed_under_enforce(root, _bypasses)

        desc = os.environ.get("NN_EXPERIMENT_DESC", "").strip() or "train.py 单次训练"
        if precomputed_official_metrics is None:
            raise ValueError(
                "finalize_run 须提供 precomputed_official_metrics "
                "（经 dispatch_test_call 或显式注入）；禁止内部 contract.test 回退"
            )
        official_metrics = precomputed_official_metrics
        from lib.adapter_accept import require_declared_aux_metrics  # noqa: WPS433
        require_declared_aux_metrics(official_metrics, self.aux_metrics.keys())
        self.report_train_artifacts(
            official_metrics, timer.elapsed, repo_root=str(root), exp_dir=str(exp_path),
            experiment=experiment, description=desc, cfg=cfg if isinstance(cfg, dict) else None,
            append_repo_ledger=append_repo_ledger,
        )

        if os.environ.get("NN_SKIP_POST_EVAL", "").strip().lower() not in ("1", "true", "yes", "on"):
            ev = self.write_slot_keep_suggestion(exp_path, history_tsv=root / "_runs" / "results.tsv")
            print(json.dumps(ev, indent=2, ensure_ascii=False), flush=True)

        last_state: dict[str, Any] | None = None
        if learner is not None and hasattr(learner, "state_dict"):
            last_state = _state_dict_cpu(learner.state_dict())
        le = int(last_epoch or 0)
        if le <= 0 and isinstance(cfg, dict):
            le = int(cfg.get("last_completed_epoch", 0) or 0)
        self.save_checkpoint(
            str(exp_path),
            repo_root=str(root),
            cfg=cfg if isinstance(cfg, dict) else {},
            official_metrics=official_metrics,
            best_state=best_state,
            last_state=last_state,
            best_epoch=int(best_epoch or 0),
            last_epoch=le,
            train_eval_metrics=train_eval_metrics,
        )

        if os.environ.get("NN_SNAPSHOT_CODE", "1").strip().lower() not in ("0", "false", "no", "off"):
            self.snapshot_code(exp_path, root)
            self.snapshot_env(exp_path, root, contract=_repro_src)

        _repro_src_final = contract if contract is not None else self
        try:
            _ensure_scripts_on_path(root)
            from lib.train_dynamics import finalize_train_dynamics  # noqa: WPS433

            finalize_train_dynamics(exp_path, _repro_src_final, repo_root=root)
            print(f"train_dynamics: → {exp_path / 'train_dynamics.json'}", file=sys.stderr, flush=True)
        except Exception as exc:
            print(f"[train_dynamics] 警告：写入失败（不影响 finalize）: {exc}", file=sys.stderr, flush=True)

        clear_train_pid(root)
        return exp_path

    def pick_keeper_exp_dir(self, exp_dirs: list[Path]) -> Path:
        """在若干已完成的 ``exp_dir`` 中按主指标选 keeper；Contract 可覆盖（如多目标聚合）。"""
        if not exp_dirs:
            raise ValueError("pick_keeper_exp_dir: exp_dirs 为空")
        best_p: Path | None = None
        best_v: float | None = None
        for p in exp_dirs:
            rp = p.resolve()
            try:
                payload = _load_results_json(rp / "results.json")
            except FileNotFoundError as e:
                raise FileNotFoundError(f"pick_keeper_exp_dir: 缺少 {rp / 'results.json'}") from e
            metrics_raw = payload.get("metrics") or {}
            raw_v = metrics_raw.get(self.metric_key)
            if raw_v is None:
                continue
            try:
                v = float(raw_v)
            except (TypeError, ValueError):
                continue  # optional: 候选指标非数值 → 跳过该候选（最后无有效则 raise）
            if math.isnan(v) or math.isinf(v):
                continue
            if best_v is None:
                best_p, best_v = rp, v
                continue
            if self.metric_direction == "maximize":
                if v > best_v:
                    best_p, best_v = rp, v
            else:
                if v < best_v:
                    best_p, best_v = rp, v
        if best_p is None:
            raise ValueError(
                f"pick_keeper_exp_dir: 候选目录中无有效主指标 {self.metric_key!r}（direction={self.metric_direction}）",
            )
        return best_p

    def finalize_round(
        self,
        exp_dirs: list[str | os.PathLike],
        *,
        repo_root: str | os.PathLike | None = None,
    ) -> Path:
        """全部槽位结束后**顺序**调用一次：选 keeper、写 ``_runs/round_decision.json``、每槽一行主台账。"""
        paths = [Path(p).resolve() for p in exp_dirs]
        root = Path(repo_root).resolve() if repo_root is not None else _resolve_repo_root(paths[0])
        history_tsv = root / "_runs" / "results.tsv"
        keeper = self.pick_keeper_exp_dir(paths)

        payload = _load_results_json(keeper / "results.json")

        desc = (os.environ.get("NN_EXPERIMENT_DESC", "") or "").strip() or "finalize_round（多槽汇总）"

        ev = self._build_evaluation_result(keeper, history_tsv=history_tsv)
        slot_metas = [_slot_meta_from_exp_dir(p) for p in paths]
        parallel_total = max(m["parallel_total"] for m in slot_metas)
        ev["finalize_round"] = {
            # v2.7.4: 落盘的 exp_dir 一律相对 repo_root(换机不断链); 内存内仍用绝对 paths
            "candidate_exp_dirs": [_to_repo_rel(root, p) for p in paths],
            "keeper_exp_dir": _to_repo_rel(root, keeper),
            "n_candidates": len(paths),
            "parallel_total": parallel_total,
            "slots": [
                {"exp_dir": _to_repo_rel(root, p), "slot": m["slot"], "parallel_total": m["parallel_total"]}
                for p, m in zip(paths, slot_metas)
            ],
        }
        # fork 触发（spec §4 步2→3）：wall-hit 可能在非 keeper 的 DISCARD 槽；
        # _build_evaluation_result 只读 keeper 的 source_block，这里补扫所有候选槽。
        if "source_block" not in ev:
            _collected = _collect_round_source_block(paths)
            if _collected is not None:
                ev["source_block"] = _collected
        # spec §4 主体闭环：本轮外部证据（saved/evidence_bundle.json）→ round_decision 的
        # evidence_refs / paper_hint（字段注入；下轮 build-run-context 读入 step1）。
        # 与 source_block 同型 sidecar-read；collect_round_evidence 空包永返回 dict 不崩。
        # 懒 import 防循环依赖；落盘决策不可被证据收集阻塞（同 wall_hit/auto_promote try 模式）。
        try:
            from lib.external.evidence_refs import collect_round_evidence
            ev.update(collect_round_evidence(root / "saved"))
        except Exception as exc:
            print(f"[finalize_round] evidence_refs 收集失败（决策仍 OK）: {exc}", file=sys.stderr)
        write_repo_round_decision(root, ev)

        cfg_for_sid = _resolve_cfg_for_ledger(keeper, payload)
        # 全员入账（2026-07-24）：每槽一行主台账；决策仍一轮一次（上已写 round_decision）
        finalized_dirs = _load_jsonl_exp_dir_set(root)
        for path in paths:
            slot_payload = _load_results_json(path / "results.json")
            slot_metrics: dict[str, float] = {}
            for k, v in (slot_payload.get("metrics") or {}).items():
                if isinstance(v, (int, float)):
                    slot_metrics[str(k)] = float(v)
            slot_elapsed = float(slot_payload.get("elapsed_sec", 0.0))
            slot_exp_name = path.name
            slot_cfg = _resolve_cfg_for_ledger(path, slot_payload)
            slot_ledger_ctx = _extract_ledger_context(self, slot_cfg or None)
            resolved = str(path.resolve())
            if resolved in finalized_dirs:
                print(
                    f"[finalize_round] 跳过已入账 exp_dir={path.name}",
                    file=sys.stderr,
                    flush=True,
                )
                continue
            from lib.exploration_stamp import compute_stamp

            # 与 train.py _smoke_enabled 对齐：勿把字面 "0" 当 smoke
            _smoke_raw = os.environ.get("NN_SMOKE", "0").strip().lower()
            smoke = _smoke_raw not in ("0", "false", "no", "off")
            sid = self._resolve_keep_scenario_id(root, cfg=slot_cfg or None)
            stamp = compute_stamp(
                root,
                path,
                elapsed_sec=slot_elapsed,
                smoke=smoke,
                scenario_id=sid,
                metric_key=self.metric_key,
                metrics=slot_metrics,
            )
            slot_ledger_ctx = dict(slot_ledger_ctx)
            if stamp.untrained:
                slot_ledger_ctx["exploration_space"] = ""
                slot_ledger_ctx["untrained"] = "1"
            elif not stamp.cell:
                raise RuntimeError(
                    f"正式训练未写出探索格子 exp_dir={path.name} reasons={stamp.reasons}"
                )
            else:
                slot_ledger_ctx["exploration_space"] = stamp.cell
                slot_ledger_ctx["untrained"] = "0"
            for slot_info, cand in zip(ev["finalize_round"]["slots"], paths):
                if cand.resolve() == path.resolve():
                    slot_info["untrained"] = stamp.untrained
                    slot_info["exploration_space"] = stamp.cell
                    break
            self._append_repo_ledger_row(
                metrics=slot_metrics,
                repo_root=str(root),
                experiment=slot_exp_name,
                description=desc,
                exp_dir=str(path),
                elapsed_sec=slot_elapsed,
                ledger_context=slot_ledger_ctx,
                cfg=slot_cfg or None,
            )
            finalized_dirs.add(resolved)
        slots_meta = ev["finalize_round"]["slots"]
        if any("untrained" in s for s in slots_meta):
            if all(s.get("untrained") is True for s in slots_meta):
                ev["untrained"] = True
            write_repo_round_decision(root, ev)
        # spec §4.1 + §4.2 撞墙信号注入（轮级一次，per-候选应在 finalize_round 写）
        # 注意：这里 `keep_suggestion` 是从 _build_evaluation_result 写入 ev 的最终 KEEP/DISCARD 决策
        # （多槽并行时为 keeper 的决策 = pick_keeper 后最终结果）；一轮一次决策，每槽一行台账。
        try:
            _update_wall_hit_streak(root, bool(ev.get("keep_suggestion")))
        except Exception as exc:
            import sys as _sys
            print(f"[finalize_round] wall_hit_streak 写盘失败（决策仍 OK）: {exc}", file=_sys.stderr)
        # R8 paradigm_mismatch —— 软警告（要求1 + R8 原则）：沿用现有 try 模式，
        # 不 raise、不中断批次。宽判决命中 → ev 标 paradigm_fit=MISMATCH 并重写盘，
        # 供 check/analyze 技能读给 human（agent 只产出信号，切范式决策锁在 human）。
        try:
            from lib.auto_mode import check_paradigm_mismatch
            if check_paradigm_mismatch(root):
                ev["paradigm_fit"] = "MISMATCH"
                write_repo_round_decision(root, ev)
        except Exception as exc:
            if isinstance(exc, (ImportError, ModuleNotFoundError)):
                raise RuntimeError(
                    "缺 scripts/lib/auto_mode.py（请 governance-sync / auto-nn-update）",
                ) from exc
            import sys as _sys
            print(f"[finalize_round] R8 paradigm_mismatch 写盘失败（决策仍 OK）: {exc}", file=_sys.stderr)
        # spec §4.2: auto 模式撞墙升档（紧接 streak 写盘后；非 auto 模式内部 is_auto_mode 判定 no-op）
        try:
            from lib.auto_mode import check_and_promote_auto
            check_and_promote_auto(root)
        except Exception as exc:
            if isinstance(exc, (ImportError, ModuleNotFoundError)):
                raise RuntimeError(
                    "缺 scripts/lib/auto_mode.py（请 governance-sync / auto-nn-update）",
                ) from exc
            import sys as _sys
            print(f"[finalize_round] auto promote 失败（不阻塞决策）: {exc}", file=_sys.stderr)
        print(json.dumps(ev, indent=2, ensure_ascii=False), flush=True)
        print(f"keeper_exp_dir={keeper}", file=sys.stderr, flush=True)
        if ev.get("keep_suggestion") and not _skip_auto_write_keeper():
            scenario_id = self._resolve_keep_scenario_id(root, cfg=cfg_for_sid or None)
            write_saved_keeper_pointer(
                root,
                keeper,
                scenario_id=scenario_id,
                experiment=keeper.name,
            )
        clear_train_pid(root)
        return keeper

    # ── round_decision / keep_suggestion ─────────────────

    def write_slot_keep_suggestion(self, exp_dir: Path, *, history_tsv: Path | None = None) -> dict:
        """单槽训末：写 ``<exp_dir>/keep_suggestion.json``（多槽并行时各槽一份，汇总见 ``finalize_round``）。"""
        exp_dir = exp_dir.resolve()
        out = self._build_evaluation_result(exp_dir, history_tsv=history_tsv)
        out_path = exp_dir / SLOT_KEEP_SUGGESTION_BASENAME
        _write_json_file(out_path, out)
        legacy = exp_dir / LEGACY_SLOT_KEEP_SUGGESTION_BASENAME
        if legacy.is_file():
            try:
                legacy.unlink()
            except OSError:
                pass  # optional: 旧 keep_suggestion 删除失败不阻断（best-effort 清理）
        return out

    def write_evaluation_result(self, exp_dir: Path, *, history_tsv: Path | None = None) -> dict:
        """兼容别名 → :meth:`write_slot_keep_suggestion`。"""
        return self.write_slot_keep_suggestion(exp_dir, history_tsv=history_tsv)

    def _resolve_keep_scenario_id(
        self,
        repo_root: Path,
        *,
        cfg: dict[str, Any] | None = None,
    ) -> str:
        """KEEP 分池：从 cfg / env / nn-config 解析当前 scenario_id。"""
        try:
            from lib.scenario_inventory import resolve_scenario_id

            agent = _load_agent_section(repo_root)
            bindings = _resolve_scenario_bindings(agent, self)
            sid, _ = resolve_scenario_id(repo_root, cfg, scenario_bindings=bindings or None)
            return sid
        except ImportError:
            ctx = _extract_scenario_tsv(self, cfg)
            sid = str(ctx.get(SCENARIO_ID_COLUMN, "") or "").strip()
            if sid:
                return sid
            # Config-Only: scenario_id must come from cfg
            if cfg is not None:
                cfg_sid = str(cfg.get("scenario_id", "") or cfg.get("SCENARIO_ID", "") or "").strip()
                if cfg_sid:
                    return cfg_sid
            nn = _load_nn_config(repo_root)
            agent = nn.get("agent") if isinstance(nn, dict) else None
            if isinstance(agent, dict):
                return str(agent.get("scenario_default", "") or "").strip()
            return ""

    def _build_evaluation_result(
        self,
        exp_dir: Path,
        *,
        history_tsv: Path | None = None,
        current_scenario_id: str | None = None,
    ) -> dict:
        exp_dir = exp_dir.resolve()
        repo_root = _resolve_repo_root(exp_dir)
        tsv_path = history_tsv if history_tsv is not None else _resolve_history_tsv_path(exp_dir)
        payload = _load_results_json(exp_dir / "results.json")
        metrics_raw = payload.get("metrics") or {}
        current_metrics: dict[str, float] = {k: float(v) for k, v in metrics_raw.items() if isinstance(v, (int, float))}
        history_rows = _load_tsv_rows(tsv_path)
        cfg_for_sid = _resolve_cfg_for_ledger(exp_dir, payload)
        sid = (
            (current_scenario_id or "").strip()
            if current_scenario_id is not None
            else self._resolve_keep_scenario_id(repo_root, cfg=cfg_for_sid if cfg_for_sid else None)
        )
        desc = (os.environ.get("NN_EXPERIMENT_DESC", "") or "").strip()
        exp_name = str(payload.get("experiment") or exp_dir.name)
        try:
            from lib.tier_attestation import upsert_finalize_tam_row  # noqa: WPS433

            upsert_finalize_tam_row(
                repo_root,
                exp_dir,
                description=desc,
                experiment=exp_name,
            )
        except Exception:
            pass  # optional: 探索期 TAM 预写失败不阻断 keep 判定
        keep_suggestion, reason, aux_checks = self.should_keep(
            current_metrics,
            history_rows,
            current_scenario_id=sid,
            current_exp_dir=exp_dir,
        )
        _bp = _read_guards_bypassed(exp_dir)  # G-信息权限 §4.3：带守门旁路的实验不可 KEEP
        if _bp:
            keep_suggestion = False
            reason = "守门被旁路：" + ", ".join(_bp) + "；不可 KEEP。" + (reason or "")
        result = {
            # v2.7.4: evaluated_exp_dir 存相对 repo_root(写进 round_decision + keep_suggestion)
            "evaluated_exp_dir": _to_repo_rel(repo_root, exp_dir),
            "primary_metric": {"key": self.metric_key, "value": current_metrics.get(self.metric_key), "direction": self.metric_direction},
            "keep_suggestion": keep_suggestion,
            "reason": reason,
            "aux_checks": aux_checks,
        }
        return merge_source_block(result, exp_dir)


# ═══════════════════════════════════════════════════════════════
# 公开工具函数
# ═══════════════════════════════════════════════════════════════

def weighted_minimize_combo(values: dict[str, float], parts: tuple[tuple[str, float], ...]) -> float:
    """对若干「越小越好」的分项做权重加权平均。``parts`` 为 ``(键, 权重)``。"""
    if not parts:
        raise ValueError("weighted_minimize_combo: parts 为空")
    s = sum(float(w) for _, w in parts)
    if s <= 0:
        raise ValueError("weighted_minimize_combo: 权重和须为正")
    acc = 0.0
    for key, w in parts:
        if key not in values:
            raise KeyError(f"weighted_minimize_combo: 缺少键 {key!r}")
        acc += float(values[key]) * float(w)
    return acc / s


def write_sanity_ok(exp_dir: str | Path, detail: str, extra: dict[str, Any] | None = None) -> Path:
    """写入 ``sanity_ok.json``。"""
    exp = Path(exp_dir)
    exp.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "ok": True,
        "utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "detail": detail,
    }
    if extra:
        payload.update(extra)
    path = exp / "sanity_ok.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


# ═══════════════════════════════════════════════════════════════
# CLI entry points
# ═══════════════════════════════════════════════════════════════

def _cli_evaluation_main() -> None:
    """``python -m contract``（默认子命令）：写 ``<exp_dir>/keep_suggestion.json``。"""
    import argparse
    ap = argparse.ArgumentParser(description="Evaluate last train run and suggest keep/discard.")
    ap.add_argument("--exp-dir", type=Path, default=Path("."), help="实验根目录（含 results.json）；默认 '.' 时历史台账为 <cwd>/_runs/results.tsv")
    ap.add_argument("--history-tsv", type=Path, default=None, help="历史台账 TSV（默认按 exp-dir 自动解析）")
    args = ap.parse_args()
    from contract import create_contract
    c = create_contract({})
    out = c.write_slot_keep_suggestion(args.exp_dir.resolve(), history_tsv=args.history_tsv.resolve() if args.history_tsv else None)
    print(json.dumps(out, indent=2, ensure_ascii=False))


def _cli_finalize_round_main() -> None:
    """``python -m contract finalize-round``：多槽汇总（写 ``_runs/round_decision.json`` + 台账）。"""
    import argparse
    ap = argparse.ArgumentParser(description="Pick keeper among exp dirs and append repo ledgers once.")
    ap.add_argument("exp_dirs", nargs="+", type=Path, help="各槽位训末目录（各含 results.json）")
    ap.add_argument("--repo-root", type=Path, default=None, help="仓库根（默认识别自第一个 exp_dir）")
    args = ap.parse_args()
    root = Path(args.repo_root).resolve() if args.repo_root else _resolve_repo_root(args.exp_dirs[0])
    _ensure_scripts_on_path(root)
    from contract import create_contract
    c = create_contract({})
    c.finalize_round(args.exp_dirs, repo_root=args.repo_root)


def _scenario_cfg_from_exp_results(exp_dir: Path) -> dict[str, Any]:
    """从 ``exp_dir/results.json`` 合并 ``cfg`` / ``train_cfg``。"""
    payload = _load_results_json(exp_dir.resolve() / "results.json")
    merged: dict[str, Any] = {}
    for key in ("cfg", "train_cfg"):
        block = payload.get(key)
        if isinstance(block, dict):
            merged.update(block)
    return merged


def _resolve_write_keeper_scenario_id(
    repo_root: Path,
    exp_dir: Path,
    *,
    scenario_id: str | None = None,
) -> str:
    """write-keeper：``--scenario-id`` → exp ``results.json`` cfg → 仓库级解析。"""
    sid = (scenario_id or "").strip()
    if sid:
        return sid
    cfg: dict[str, Any] = {}
    try:
        cfg = _scenario_cfg_from_exp_results(exp_dir)
    except FileNotFoundError:
        pass  # optional: exp 无 results.json（未跑完）→ cfg 空，走仓库级解析
    try:
        from lib.scenario_inventory import resolve_scenario_id

        agent = _load_agent_section(repo_root)
        bindings = _resolve_scenario_bindings(agent, None)
        sid, _ = resolve_scenario_id(repo_root, cfg or None, scenario_bindings=bindings or None)
    except ImportError:
        sid = ""
        if cfg:
            sid = str(cfg.get("scenario_id", "") or cfg.get("SCENARIO_ID", "") or "").strip()
        if not sid:
            nn = _load_nn_config(repo_root)
            agent = nn.get("agent") if isinstance(nn, dict) else None
            if isinstance(agent, dict):
                sid = str(agent.get("scenario_default", "") or "").strip()
    return (sid or "").strip()


def _cli_write_keeper_main() -> None:
    """``python -m contract write-keeper``：KEEP 后写 ``saved/keepers.json``（不复制权重）。"""
    import argparse
    ap = argparse.ArgumentParser(
        description="Record current keeper exp_dir in saved/keepers.json (no weight copy).",
    )
    ap.add_argument("--exp-dir", type=Path, required=True, help="keeper 的 exp 目录（含 best_model.pt）")
    ap.add_argument("--repo-root", type=Path, default=Path("."), help="仓库根")
    ap.add_argument("--experiment", type=str, default="", help="实验名（默认识别自目录名）")
    ap.add_argument(
        "--scenario-id",
        type=str,
        default="",
        help="场景 ID（缺省则从 exp_dir/results.json 的 cfg 或仓库 nn-config 推断）",
    )
    args = ap.parse_args()
    root = args.repo_root.resolve()
    scenario_id = _resolve_write_keeper_scenario_id(
        root,
        args.exp_dir,
        scenario_id=(args.scenario_id or None),
    )
    if not scenario_id:
        raise SystemExit(
            "write-keeper: 无法解析 scenario_id"
            "（请传 --scenario-id 或确保 exp_dir/results.json 的 cfg 含 scenario_id）"
        )
    write_saved_keeper_pointer(
        root,
        args.exp_dir,
        scenario_id=scenario_id,
        experiment=(args.experiment or None),
    )


def _cli_sanity_main() -> None:
    """``python -m contract sanity``：最小 Linear + MSE 自检。"""
    model = nn.Linear(4, 2)
    x = torch.randn(8, 4)
    y = torch.randn(8, 2)
    loss = (model(x) - y).pow(2).mean()
    _dummy_backward_once(model, loss, grad_clip=1.0)
    out = Path(os.environ.get("NN_CONTRACT_SANITY_CLI_DIR", "/tmp"))
    write_sanity_ok(out, "experiment sanity CLI demo (Linear+MSE)")
    print("experiment sanity: demo OK", file=sys.stderr)


# ── __all__ ─────────────────────────────────────────────────

__all__ = [
    "ExperimentBase",
    "TimeGuard",
    "weighted_minimize_combo",
    "write_sanity_ok",
]
