"""
Mammoth continual learning workspace。
- CLI 适配器(ADAPTER 场景):cfg ↔ CLI 双向桥(ABCD 四档)
  - 注意：CLI 适配器不是模型注册表(不注册 class),而是"方法 → CLI 翻译函数"的轻量映射。
  - 统一契约见 `template/package/CLAUDE.md` §pluggable 与 `docs/AUTO-NN-whitepaper.md` §1.3.1
    ——本仓 `register_*` 装饰 class 进公开 `X_REGISTRY` dict;CLI 适配器是 ADAPTER 场景的
    例外机制,使用 `@register_cli_adapter` 进 `CLI_ADAPTER_REGISTRY` 公开 dict(无下划线),
    与模型注册表语义分离。
- parse_mammoth_log:logs.pyd → metrics dict
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import torch

from experiment import ExperimentBase

try:
    from lib.adapter_accept import (
        append_cfg_cli,
        assert_cli_argv_no_empty_values,
        is_empty_cli_value,
    )
except ImportError:
    from scripts.lib.adapter_accept import (
        append_cfg_cli,
        assert_cli_argv_no_empty_values,
        is_empty_cli_value,
    )


def _append_cli_if_present(args: list, cfg: dict, cfg_key: str, cli_flag: str) -> None:
    """方法专属参数：缺键或空串/空白时不追加 CLI flag。"""
    if cfg_key in cfg and not is_empty_cli_value(cfg[cfg_key]):
        args.extend([f"--{cli_flag}", str(cfg[cfg_key])])


# ═══════════════════════════════════════════════════════════════
# Mammoth CLI 适配器(cfg ↔ CLI 双向桥,ADAPTER 场景专属)
# ═══════════════════════════════════════════════════════════════

# cfg key → CLI arg 映射(白名单)
CFG_TO_CLI = {
    # dataset/model(E 档,contract 锁)
    "MAMMOTH_DATASET":      "dataset",
    "MAMMOTH_DATASET_CONFIG": "dataset_config",
    "MAMMOTH_MODEL":        "model",
    # A 档(标量)
    "LR":                   "lr",
    "N_EPOCHS":             "n_epochs",
    "BATCH_SIZE":           "batch_size",
    "MINIBATCH_SIZE":       "minibatch_size",
    "NUM_WORKERS":          "num_workers",
    "SEED":                 "seed",
    "BUFFER_SIZE":          "buffer_size",
    # B 档(结构)
    "BACKBONE":             "backbone",
    # C 档(目标)
    "ALPHA":                "alpha",
    "BETA":                 "beta",
    "GAMMA":                "gamma",
    "LAMBD":                "lambd",
    "CONSTR_ETA":           "constr_eta",
    "SIMCLR_TEMP":          "simclr_temp",
    "SIMCLR_BATCH_SIZE":    "simclr_batch_size",
    "SIMCLR_NUM_AUG":       "simclr_num_aug",
    "DP_WEIGHT":            "dp_weight",
    # C 档(新方法专属)
    "REPLAY_TEMP":          "replay_temp",
    "CB_TAU":               "cb_tau",
    # D 档(数据)
    "REPLAY_AUG_PROB":      "replay_aug_prob",
    "REPLAY_AUG_STRENGTH":  "replay_aug_strength",
    # 开关
    "PERMUTE_CLASSES":      "permute_classes",
    "ENABLE_OTHER_METRICS": "enable_other_metrics",
}

# CLI 适配器注册表(method_name → CLI 翻译 fn)
# 公开 dict(无下划线),与全仓 register_* 契约一致:未知 key → KeyError
CLI_ADAPTER_REGISTRY: dict[str, callable] = {}


def register_cli_adapter(method_name: str):
    """装饰器:注册 mammoth 方法的 CLI 参数翻译函数(ADAPTER 场景专属)。

    与 `@register_learner`(注册 class 进 LEARNER_REGISTRY)语义分离——
    本装饰器注册的是 cfg → CLI args 的翻译 fn,不是模型类。命名规则
    `register_cli_adapter` 是为了显式标明这是 ADAPTER 场景的 CLI 适配器
    机制,避免与模型注册表同名混淆。
    """
    def decorator(fn):
        if method_name in CLI_ADAPTER_REGISTRY:
            raise KeyError(f"CLI adapter {method_name!r} 已注册(原: {CLI_ADAPTER_REGISTRY[method_name].__name__})")
        CLI_ADAPTER_REGISTRY[method_name] = fn
        return fn
    return decorator


# ── CLI 适配器实现(扩展,不改原有文件) ─────────────────────────

@register_cli_adapter("class-balanced-derpp")
def _class_balanced_derpp(cfg, args):
    """类平衡 DER++ 必传参数。"""
    _append_cli_if_present(args, cfg, "ALPHA", "alpha")
    _append_cli_if_present(args, cfg, "BETA", "beta")
    _append_cli_if_present(args, cfg, "CB_TAU", "cb_tau")

@register_cli_adapter("derpp-custom")
def _derpp_custom(cfg, args):
    """DER++ with replay temperature 必传参数。"""
    _append_cli_if_present(args, cfg, "ALPHA", "alpha")
    _append_cli_if_present(args, cfg, "BETA", "beta")
    _append_cli_if_present(args, cfg, "REPLAY_TEMP", "replay_temp")

@register_cli_adapter("derpp-replay-aug")
def _derpp_replay_aug(cfg, args):
    """DER++ with replay augmentation 必传参数。"""
    _append_cli_if_present(args, cfg, "ALPHA", "alpha")
    _append_cli_if_present(args, cfg, "BETA", "beta")
    _append_cli_if_present(args, cfg, "REPLAY_AUG_PROB", "replay_aug_prob")
    _append_cli_if_present(args, cfg, "REPLAY_AUG_STRENGTH", "replay_aug_strength")


def build_command(cfg: dict, exp_dir: Path) -> list[str]:
    """cfg → mammoth main.py CLI args。"""
    mammoth_root = Path(cfg["MAMMOTH_ROOT"])
    if not mammoth_root.exists():
        raise FileNotFoundError(f"MAMMOTH_ROOT not found: {mammoth_root}")

    cmd = ["python", str(mammoth_root / "main.py")]

    # 1. 白名单 cfg → CLI（空串/空白省略，见 adapter_accept.append_cfg_cli）
    append_cfg_cli(cmd, cfg, CFG_TO_CLI)

    # 2. 系统级(每轮 exp_dir 独立)
    cmd.extend(["--base_path", str(exp_dir / "mammoth_data")])
    cmd.extend(["--results_path", "mammoth_results"])
    cmd.extend(["--non_verbose", "1"])
    cmd.extend(["--nowand", "1"])

    # 3. pluggable:新方法专属参数(走 CLI_ADAPTER_REGISTRY,未知 model → KeyError)
    model = cfg["MAMMOTH_MODEL"]
    if model not in CLI_ADAPTER_REGISTRY:
        raise KeyError(
            f"MAMMOTH_MODEL={model!r} 不在 CLI_ADAPTER_REGISTRY {sorted(CLI_ADAPTER_REGISTRY)}；"
            f"新增方法请 @register_cli_adapter(<method_name>) 注册 CLI 翻译函数"
        )
    CLI_ADAPTER_REGISTRY[model](cfg, cmd)

    assert_cli_argv_no_empty_values(cmd)
    return cmd


def run_mammoth(cfg: dict, exp_dir: Path, log_path: Path, timeout: int = 7200) -> int:
    """subprocess 跑 mammoth。no-fallback:失败抛 RuntimeError。"""
    cmd = build_command(cfg, exp_dir)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[adapter] running: {' '.join(cmd[:8])}...")
    with open(log_path, "w") as f:
        proc = subprocess.run(
            cmd,
            cwd=cfg["MAMMOTH_ROOT"],
            stdout=f, stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout,
        )
    if proc.returncode != 0:
        raise RuntimeError(
            f"mammoth exit {proc.returncode}; log: {log_path}"
        )
    return proc.returncode


# ═══════════════════════════════════════════════════════════════
# Mammoth logs.pyd 解析器
# ═══════════════════════════════════════════════════════════════

import re


def load_last_row(log_path: Path) -> dict:
    """读 logs.pyd 最后一行,eval 解析(注入 np/torch/device 命名空间)。"""
    import ast
    lines = [l for l in Path(log_path).read_text().splitlines() if l.strip()]
    if not lines:
        raise RuntimeError(f"empty logs.pyd: {log_path}")
    # mammoth 字段含 np.float64 / torch.device → 必须 eval
    return eval(lines[-1], {"np": np, "device": torch.device, "torch": torch})


def framework_eval_raw_from_row(row: dict) -> dict:
    """logs.pyd 单行 → 框架原样主分（Discovery：最后一项 accmean_taskN 原值）。

    禁止在此做 mean(accmean_task1..N)。键名对齐 contract/framework_binding.yaml。
    """
    keys = sorted(
        [k for k in row if re.fullmatch(r"accmean_task\d+", k)],
        key=lambda k: int(k.replace("accmean_task", "")),
    )
    if not keys:
        raise RuntimeError("logs.pyd 缺 accmean_task* 字段")
    ntasks = len(keys)
    return {
        "class_il_accmean_last": float(row[keys[-1]]),
        "n_tasks": ntasks,
        "forgetting": row.get("forgetting"),
        "backward_transfer": row.get("backward_transfer"),
        "forward_transfer": row.get("forward_transfer"),
        "row": row,
        "keys": keys,
    }


def translate_eval_export(raw: dict, setting: str = "class-il") -> dict:
    """原样 raw → 台账 metrics（只键映射；主分 = raw 声明键）。"""
    row = raw["row"]
    ntasks = int(raw["n_tasks"])
    keys = raw["keys"]
    return {
        "final_avg_accuracy": float(raw["class_il_accmean_last"]),
        "average_forgetting": float(row["forgetting"]) if row.get("forgetting") is not None else None,
        "backward_transfer": float(row["backward_transfer"]) if row.get("backward_transfer") is not None else None,
        "forward_transfer": float(row["forward_transfer"]) if row.get("forward_transfer") is not None else None,
        "per_task_accuracy": {
            f"task{i}": float(row[f"accuracy_{i}_task{ntasks}"])
            for i in range(1, ntasks + 1)
            if f"accuracy_{i}_task{ntasks}" in row
        },
        "n_tasks": ntasks,
        "setting": setting,
    }


def to_metrics(row: dict, setting: str = "class-il") -> dict:
    """兼容入口：两段式 raw → translate。"""
    raw = framework_eval_raw_from_row(row)
    return translate_eval_export(raw, setting)


def load_logs(exp_dir: Path, dataset: str = "seq-cifar10", model: str = "derpp",
              base_path: Path = None, results_path: str = "mammoth_results") -> dict:
    """读 class-il + task-il 两套 logs.pyd,合并返回；并落盘 eval_export_raw.json。"""
    if base_path is None:
        base_path = exp_dir / "mammoth_data"
    out = {}
    class_il_raw = None
    for setting in ["class-il", "task-il"]:
        log_path = base_path / results_path / setting / dataset / model / "logs.pyd"
        if not log_path.exists():
            # 尝试直接在 base_path 下找
            log_path = base_path / setting / dataset / model / "logs.pyd"
        if not log_path.exists():
            raise FileNotFoundError(f"logs.pyd not found: {log_path}")
        row = load_last_row(log_path)
        raw = framework_eval_raw_from_row(row)
        if setting == "class-il":
            class_il_raw = {
                "class_il_accmean_last": raw["class_il_accmean_last"],
                "n_tasks": raw["n_tasks"],
            }
        out[setting] = translate_eval_export(raw, setting)

    # 合并主指标用 class-il
    out["final_avg_accuracy"] = out["class-il"]["final_avg_accuracy"]
    out["task_il_accuracy"] = out["task-il"]["final_avg_accuracy"]
    out["average_forgetting"] = out["class-il"]["average_forgetting"]
    out["backward_transfer"] = out["class-il"]["backward_transfer"]
    out["forward_transfer"] = out["class-il"]["forward_transfer"]

    if class_il_raw is not None:
        try:
            from lib.framework_binding import write_eval_export_raw
        except ImportError:
            try:
                from scripts.lib.framework_binding import write_eval_export_raw
            except ImportError:
                write_eval_export_raw = None
        if write_eval_export_raw is not None:
            write_eval_export_raw(Path(exp_dir), class_il_raw)

    return out


# ═══════════════════════════════════════════════════════════════
# Workspace ExperimentBase 子类
# ═══════════════════════════════════════════════════════════════

class Workspace(ExperimentBase):
    """Mammoth continual learning workspace."""

    def build_learner(self, cfg: dict, source=None) -> tuple[Any, dict]:
        """mammoth 自己构建模型,这里 no-op。"""
        return None, {}

    def build_objective(self, cfg: dict) -> tuple[Any, dict]:
        """mammoth 自己定义 loss,这里 no-op。"""
        return None, {}

    def train_step(self, learner: Any, source: Any, objective: Any, *, epoch: int, shared_context: dict) -> dict[str, float]:
        """一轮 mammoth run(不是逐 epoch,而是完整 task sequence)。"""
        cfg = shared_context["cfg"]
        exp_dir = Path(shared_context["exp_dir"])
        log_path = exp_dir / "mammoth.log"

        # 跑 mammoth
        run_mammoth(cfg, exp_dir, log_path, timeout=int(cfg["TIMEOUT"]))

        # 解析 logs.pyd
        metrics = load_logs(
            exp_dir,
            dataset=cfg["MAMMOTH_DATASET"],
            model=cfg["MAMMOTH_MODEL"],
        )

        # 存入 shared_context 供 contract.test 使用
        shared_context["mammoth_metrics"] = metrics

        return metrics

    def predict(self, learner: Any, batch: Any, *, shared_context: dict) -> tuple[Any, Any]:
        """mammoth 自己做推理,这里 no-op。"""
        return None, None

    def evaluate(self, learner: Any, *, shared_context: dict) -> dict[str, float]:
        """mammoth 自己做评估,这里返回 train_step 解析的 metrics。"""
        return shared_context.get("mammoth_metrics", {})


def create_workspace(cfg: dict) -> ExperimentBase:
    return Workspace()
