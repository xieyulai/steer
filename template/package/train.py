"""
可变训练脚本 — 通过 ExperimentBase 编排。

Agent 主入口：顶部超参 + 编排；实现在 workspace/。
contract/ 不可变（除非立项/迁移）。

**超参优先级**：`train.py` 顶部常量 < **`--config config.json`**（实验参数）；系统控制走 `NN_*` / 系统 CLI（见 PROTOCOL §2.3）。
"""
from __future__ import annotations

import copy
import json
import os
import signal
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent
_scripts = _REPO_ROOT / "scripts"
if _scripts.is_dir() and str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))

from lib.home_gpus import HomeGpusError, enforce_cuda_visible_devices  # noqa: E402

try:
    enforce_cuda_visible_devices()
except HomeGpusError as exc:
    print(f"[gpu] {exc}", file=sys.stderr)
    raise SystemExit(1)

import torch  # noqa: E402

from contract import create_contract
from experiment import (
    EarlyStopMonitor,
    ExperimentBase,
    TimeBudgetStop,
    TimeGuard,
    allocate_exp_dir,
    eval_improved_for_best,
    guard_optimizer_steps,
    resolve_early_stop_patience,
)
from lib.nn_config import load_nn_config
from scripts.lib.train_branch import dispatch_test_call, resolve_official_adapter_runner
from workspace import create_workspace, get_workspace_kind, get_training_mech

# ═══════════════════════════════════════════════════════════════
# HYPERPARAMETERS — Agent 每轮优先改这里
# ═══════════════════════════════════════════════════════════════
MODEL_ARCH = "cnn"
BATCH_SIZE = 128
LR = 1e-3
WEIGHT_DECAY = 0.0
DROPOUT = 0.0
EPOCHS = 30
SEED = 42                   # Config-Only 默认种子；config.json 的 SEED 可覆盖
SCHEDULER = "cosine"
# E4_CADENCE=C：跳过前 EVAL_START_FRAC 比例的 epoch 不做 evaluate（0.2 ≈ 仅最后 80% 圈 eval）
EVAL_START_FRAC = 0.0
EVAL_EVERY_N = 1  # 在允许 eval 的区间内，每 N 个 epoch eval 一次
# ═══════════════════════════════════════════════════════════════


def build_cfg() -> dict[str, Any]:
    return {k: v for k, v in globals().items() if k.isupper() and not k.startswith("_")}


def _load_config_overrides(config_path: str | Path) -> dict[str, Any]:
    """从 config.json 读取实验参数（Config-Only 唯一入口）。"""
    path = Path(config_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"[Config-Only] 配置文件不存在: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"[Config-Only] 配置文件 JSON 无效: {path}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"[Config-Only] 配置文件须为 JSON 对象: {path}")
    return {
        k: v for k, v in raw.items()
        if isinstance(k, str) and not k.startswith("_")
    }


def _apply_config_file(cfg: dict[str, Any], config_path: str | Path) -> None:
    overrides = _load_config_overrides(config_path)
    if not overrides:
        print(f"[train] Config-Only: {config_path} 无可用键（跳过）", file=sys.stderr, flush=True)
        return
    cfg.update(overrides)
    print(
        f"[train] Config-Only: 已加载 {config_path}（{len(overrides)} 键覆盖 train.py 默认值）",
        file=sys.stderr,
        flush=True,
    )


def _parse_train_cli() -> str | None:
    """解析 CLI：系统控制写 env；返回 --config 路径（若有）。"""
    import argparse

    p = argparse.ArgumentParser(
        prog="train.py",
        description="auto-nn-experiment 训练入口；实验参数来自 --config config.json",
    )
    p.add_argument(
        "--config",
        type=str,
        default=None,
        help="从 config.json 读取实验参数（覆盖 train.py 顶部常量）",
    )
    p.add_argument("--experiment", type=str, default=None, help="设置 NN_EXPERIMENT")
    p.add_argument("--experiment-desc", type=str, default=None, help="设置 NN_EXPERIMENT_DESC")
    p.add_argument("--slot", type=int, default=None, help="NN_SLOT（与 --parallel-total 联用）")
    p.add_argument("--parallel-total", type=int, default=None, help="NN_PARALLEL_TOTAL")
    p.add_argument("--device", type=str, choices=("auto", "cpu", "cuda", "gpu"), default=None, help="NN_DEVICE（cuda/gpu 同义）")
    p.add_argument(
        "--no-auto-finalize-round",
        action="store_true",
        help="等价 NN_AUTO_FINALIZE_ROUND=0（单槽也不自动 finalize_round）",
    )

    args, rest = p.parse_known_args()
    if rest:
        print(f"[train] 警告：未识别 CLI 参数将忽略: {rest}", file=sys.stderr, flush=True)

    if args.experiment is not None:
        os.environ["NN_EXPERIMENT"] = str(args.experiment).strip()
    if args.experiment_desc is not None:
        os.environ["NN_EXPERIMENT_DESC"] = str(args.experiment_desc).strip()
    if args.slot is not None:
        os.environ["NN_SLOT"] = str(int(args.slot))
    if args.parallel_total is not None:
        os.environ["NN_PARALLEL_TOTAL"] = str(int(args.parallel_total))
    if args.device is not None:
        d = args.device.strip().lower()
        os.environ["NN_DEVICE"] = "cuda" if d == "gpu" else d
    if args.no_auto_finalize_round:
        os.environ["NN_AUTO_FINALIZE_ROUND"] = "0"

    return str(args.config).strip() if args.config else None


def _smoke_enabled() -> bool:
    v = os.environ.get("NN_SMOKE", "0").strip().lower()
    return v not in ("0", "false", "no", "off")


def _eval_start_epoch(epochs_total: int, start_frac: float) -> int:
    """首个执行 evaluate 的 epoch（1-based）。start_frac=0.2 → 跳过前 20%，约最后 80% 才 eval。"""
    if start_frac <= 0:
        return 1
    return min(epochs_total, max(1, int(epochs_total * start_frac) + 1))


def _should_run_evaluate(epoch: int, epochs_total: int, cfg: dict[str, Any]) -> bool:
    """E4_CADENCE=C 时在 train.py 控制 evaluate 频率（框架无内置，由编排层实现）。"""
    start = _eval_start_epoch(epochs_total, float(cfg.get("EVAL_START_FRAC", 0)))
    every = max(1, int(cfg.get("EVAL_EVERY_N", 1)))
    if epoch < start:
        return False
    return (epoch - start) % every == 0


def _training_epochs(cfg: dict[str, Any]) -> int:
    """训练循环 epoch 数。smoke 模式同样跑 cfg['EPOCHS']，由 TimeGuard 按墙钟截断（NN_SMOKE_BUDGET）。"""
    return int(cfg["EPOCHS"])


def _pick_device() -> torch.device:
    mode = os.environ.get("NN_DEVICE", "auto").strip().lower()
    if mode == "cpu":
        return torch.device("cpu")
    if mode in ("cuda", "gpu"):
        if not torch.cuda.is_available():
            raise RuntimeError("NN_DEVICE=cuda 但 torch.cuda.is_available() 为 False。")
        return torch.device("cuda")
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def main() -> None:
    config_path = _parse_train_cli()
    cfg = build_cfg()
    if config_path:
        _apply_config_file(cfg, config_path)
    contract = create_contract(cfg)
    ws = create_workspace(cfg)

    cfg["NUM_CLASSES"] = contract.num_classes
    cfg["CHECKPOINT_KIND"] = contract.checkpoint_kind
    cfg["EARLY_STOP_PATIENCE"] = resolve_early_stop_patience(_REPO_ROOT, cfg)

    contract.bind_train_cfg(cfg)
    ExperimentBase.setup_seed(contract)

    device = _pick_device()
    cfg.update(contract.build_full_snapshot(device=str(device)))
    print(f"device: {device} | torch={torch.__version__} | cuda_available={torch.cuda.is_available()}", file=sys.stderr, flush=True)
    if device.type == "cuda":
        print(f"cuda_runtime={torch.version.cuda} | gpu={torch.cuda.get_device_name(0)}", file=sys.stderr, flush=True)

    # ① Data — contract 准备数据；D 档采样器在 workspace 钩子（勿改 contract）
    train_transform, _m = ws.build_transforms(cfg); ExperimentBase.apply_build_meta(cfg, _m, "build_transforms")
    cfg["_train_transform"] = train_transform
    train_loader, val_loader = contract.prepare_data(cfg)
    train_loader = ws.wrap_train_loader(train_loader, cfg)
    del cfg["_train_transform"]

    # ② Build — workspace 构建模型和目标
    learner, _m = ws.build_learner(cfg, source=train_loader); ExperimentBase.apply_build_meta(cfg, _m, "build_learner")
    learner = learner.to(device)
    objective, _m = ws.build_objective(cfg); ExperimentBase.apply_build_meta(cfg, _m, "build_objective")
    # Smoke：dummy 已移除；真数据短跑由 TimeGuard 按墙钟截断
    epochs_total = _training_epochs(cfg)
    if _smoke_enabled():
        # smoke 专用墙钟 NN_SMOKE_BUDGET（默认 120s）：显式传 TimeGuard（合法缩短通道）。
        # 通用 NN_TIME_BUDGET 已冻结为 yaml 一致性校验（不一致拒启），smoke 不再借用。
        smoke_budget = int(os.environ.get("NN_SMOKE_BUDGET", "120").strip() or "120")
        timer = TimeGuard(smoke_budget)
        print(
            f"[train] smoke: 墙钟 {smoke_budget}s（NN_SMOKE_BUDGET；TimeGuard 到点截断；epochs_total={epochs_total}）",
            file=sys.stderr,
            flush=True,
        )
    else:
        timer = TimeGuard(contract.time_budget)

    # Exp dir（槽位：单实验 = s0of1；并行时各进程设 NN_SLOT / NN_PARALLEL_TOTAL）
    slot = int(os.environ.get("NN_SLOT", "0").strip() or "0")
    parallel_total = int(os.environ.get("NN_PARALLEL_TOTAL", "1").strip() or "1")
    if slot < 0 or parallel_total < 1 or slot >= parallel_total:
        raise RuntimeError(f"无效槽位: NN_SLOT={slot} NN_PARALLEL_TOTAL={parallel_total}（须 0<=SLOT<TOTAL）")
    if slot > 0 and parallel_total <= 1:
        print(
            "[train] 警告：NN_SLOT>0 但 NN_PARALLEL_TOTAL<=1；多 GPU 并行时请对所有子进程设置相同且 >1 的 NN_PARALLEL_TOTAL",
            file=sys.stderr, flush=True,
        )
    shared_context: dict[str, Any] = {
        "device": device,
        "val_loader": val_loader,
        "objective": objective,
        "metric_key": contract.metric_key,
        "cfg": cfg,
    }

    # Pre-flight（独立目录 …_preflight_check，与正式实验 exp_dir 分离）
    preflight_dir = allocate_exp_dir(
        _REPO_ROOT, "preflight_check", slot=slot, parallel_total=parallel_total,
    )

    def _preflight_finalize():
        dummy_metrics = {k: 0.0 for k in (contract.metric_key,)}
        contract.finalize_run(
            repo_root=_REPO_ROOT, cfg=cfg,
            timer=timer, best_state=None, exp_dir=preflight_dir,
            experiment="preflight_check",
            precomputed_official_metrics=dummy_metrics,
            append_repo_ledger=False,
        )

    try:
        data_pf, target_pf = next(iter(train_loader))
    except StopIteration:
        raise RuntimeError("Pre-flight: train_loader 为空") from None

    logits_pf, target_eff_pf = ws.predict(learner, (data_pf, target_pf), shared_context=shared_context)
    loss_pf = objective(logits_pf, target_eff_pf)
    gc_pf = float(os.environ.get("NN_GRAD_CLIP", "1.0"))
    contract.preflight_check(
        learner, lambda: {"total": loss_pf}, grad_clip=gc_pf, finalize_fn=_preflight_finalize,
        cfg=cfg,
        train_batch=(data_pf, target_pf),  # G-信息权限：首 batch 对 INFO_PERM["train_batch_keys"]
    )

    experiment = os.environ.get("NN_EXPERIMENT", "").strip() or "run"
    exp_dir = allocate_exp_dir(
        _REPO_ROOT, experiment, slot=slot, parallel_total=parallel_total,
    )

    # Signal handlers
    train_status: dict[str, Any] = {"epoch": 0, "epochs_total": epochs_total, "phase": "init", "pid": os.getpid()}
    train_status_path = exp_dir / "train_status.json"

    def _on_signal(signum: int, _frame: object) -> None:
        try:
            name = signal.Signals(signum).name
        except ValueError:
            name = f"SIG_{signum}"
        payload = {"signal": int(signum), "signal_name": name, "train_snapshot": dict(train_status),
                    "hint": "SIGKILL(9) 无法在进程内捕获；若疑似 OOM 请查 dmesg。"}
        try:
            with open(exp_dir / "interrupt.json", "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except OSError:
            pass
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    for _sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(_sig, _on_signal)
        except (AttributeError, ValueError, OSError):
            pass

    # 维度 A — training_mech 训练调度分流(对照下方 metrics_shape 接线,同款 registry→cfg 覆盖)
    from scripts.lib.train_branch_types import TrainingMech
    from scripts.lib.train_branch import (
        dispatch_training,
        finalize_training_loop_artifacts,
        invoke_framework_train,
        resolve_subprocess_cmd_and_result,
        run_subprocess_training,
    )
    _ws_name = getattr(ws, "__workspace_name__", None) or type(ws).__name__
    training_mech_value: TrainingMech | str = get_training_mech(_ws_name)
    # nn-config.yaml 是 system 配置 (约定于 PROTOCOL;非实验 cfg),可安全 fallback:
    try:  # optional: load_nn_config 是 system config (PROTOCOL/CLAUDE.md 约定),缺失即跳
        nn_cfg = load_nn_config(_REPO_ROOT)
        cfg_training_mech = (nn_cfg.get("workspace") or {}).get("training_mech")
        if cfg_training_mech:
            training_mech_value = cfg_training_mech  # 用户 cfg 显式 opt-in (str 原样透传,dispatch_training 归一)
    except (FileNotFoundError, KeyError):
        pass  # defaults to registry / TrainingMech.NATIVE

    # ── Training loop ────────────────────────────────────
    def _run_native():
        """Native 训练主循环(闭包,捕获 main() locals)。

        注入 seam:dispatch_training(NATIVE) 调本闭包;IN_PROCESS/SUBPROCESS
        分别注入 _run_in_process / _run_subprocess（见 PROTOCOL §3.0.3）。
        闭包形态而非抽到 lib:避免移动 75 行循环+helper、避免 12 参签名穿透。
        返回训练产物(best_state/best_metrics/best_epoch/last_completed_epoch/stop_reason)。
        """
        # ── Training loop ────────────────────────────────────
        best_primary = 0.0
        best_metrics: dict[str, float] = {}
        best_state: dict[str, torch.Tensor] | None = None
        best_epoch: int = 0
        last_completed_epoch = 0
        early_stop = EarlyStopMonitor.from_contract(contract, _REPO_ROOT, cfg)
        stop_reason = "epochs_complete"
        if early_stop.patience > 0:
            print(
                f"[early_stop] patience={early_stop.patience} direction={early_stop.direction} "
                f"metric={contract.metric_key}",
                file=sys.stderr,
                flush=True,
            )

        try:
            with guard_optimizer_steps(timer):
                for epoch in range(1, epochs_total + 1):
                    if timer.should_stop():
                        stop_reason = "time_budget"
                        break
                    try:
                        train_metrics = ws.train_step(learner, train_loader, objective, epoch=epoch, shared_context=shared_context)
                    except TimeBudgetStop:
                        stop_reason = "time_budget"
                        break
                    train_loss = train_metrics["train_loss"]
                    _opt = shared_context.get("optimizer")
                    contract.record_train_epoch(exp_dir, epoch, train_metrics, _opt, timer)

                    if _should_run_evaluate(epoch, epochs_total, cfg):
                        eval_metrics = ws.evaluate(learner, shared_context=shared_context)
                        contract.record_eval_epoch(exp_dir, epoch, train_metrics, eval_metrics, _opt, timer)
                        if _opt is not None:
                            contract.log_step(epoch, contract.progress_log_dict(
                                train_loss=train_loss, eval_metrics=eval_metrics, optimizer=_opt, timer=timer,
                            ))
                        _curr = float(eval_metrics[contract.metric_key])
                        improved = eval_improved_for_best(
                            _curr, best_primary, contract.metric_direction, best_epoch=best_epoch,
                        )
                        if improved:
                            best_primary = _curr
                            best_metrics = eval_metrics.copy()
                            best_state = copy.deepcopy(learner.state_dict())
                            best_epoch = epoch
                        if early_stop.after_eval(improved):
                            print(
                                f"[early_stop] 触发于 epoch {epoch}/{epochs_total} "
                                f"(连续 {early_stop.epochs_without_improve} 次 eval 无提升)",
                                file=sys.stderr,
                                flush=True,
                            )
                            stop_reason = "early_stop_patience"
                            last_completed_epoch = epoch
                            break
                    elif _opt is not None:
                        print(
                            f"[train] epoch {epoch}/{epochs_total}: skip evaluate "
                            f"(EVAL_START_FRAC={cfg.get('EVAL_START_FRAC', 0)}, EVAL_EVERY_N={cfg.get('EVAL_EVERY_N', 1)})",
                            file=sys.stderr, flush=True,
                        )

                    last_completed_epoch = epoch
                    train_status["epoch"] = epoch
                    train_status["epochs_total"] = epochs_total
                    train_status["phase"] = "training"
                    train_status["unix_time"] = time.time()
                    try:
                        tmp = train_status_path.with_suffix(train_status_path.suffix + ".tmp")
                        with open(tmp, "w", encoding="utf-8") as f:
                            json.dump(dict(train_status), f, indent=2, ensure_ascii=False)
                        tmp.replace(train_status_path)
                    except OSError:
                        pass

        except Exception:
            try:
                (exp_dir / "train_exception.txt").write_text(traceback.format_exc(), encoding="utf-8")
            except OSError:
                pass
            raise

        # train_done / checkpoint 提到 dispatch 后统一写；stop_reason 经 normalize 带出
        return {
            "best_state": best_state,
            "best_metrics": best_metrics,
            "best_epoch": best_epoch,
            "last_completed_epoch": last_completed_epoch,
            "stop_reason": stop_reason,
        }

    def _run_in_process():
        """IN_PROCESS：调 ws.framework_train（与 train_step 不同钩子）。"""
        return invoke_framework_train(
            ws,
            learner=learner,
            train_loader=train_loader,
            objective=objective,
            shared_context=shared_context,
            exp_dir=exp_dir,
            cfg=cfg,
            contract=contract,
        )

    def _run_subprocess():
        """SUBPROCESS：workspace 给出命令 + 结果路径，跑完读 JSON。"""
        cmd, result_path = resolve_subprocess_cmd_and_result(ws, exp_dir)
        return run_subprocess_training(cmd=cmd, result_path=result_path, cwd=exp_dir)

    _native_result = dispatch_training(
        training_mech=training_mech_value,
        run_native=_run_native,
        run_in_process=_run_in_process,
        run_subprocess=_run_subprocess,
    )
    best_state = _native_result["best_state"]
    best_metrics = _native_result["best_metrics"]
    best_epoch = _native_result["best_epoch"]
    last_completed_epoch = _native_result["last_completed_epoch"]
    finalize_training_loop_artifacts(
        exp_dir=exp_dir,
        learner=learner,
        repo_root=_REPO_ROOT,
        cfg=cfg,
        epochs_configured=epochs_total,
        result=_native_result,
    )
    # v1.33.0 — workspace_kind (str) → metrics_shape (MetricsShape | str)
    from scripts.lib.train_branch_types import MetricsShape
    metrics_shape_value: MetricsShape | str = get_workspace_kind(_ws_name)
    # nn-config.yaml 是 system 配置 (约定于 PROTOCOL;非实验 cfg),可安全 fallback:
    try:  # optional: load_nn_config 是 system config (PROTOCOL/CLAUDE.md 约定),缺失即跳
        nn_cfg = load_nn_config(_REPO_ROOT)
        cfg_metrics_shape = (nn_cfg.get("workspace") or {}).get("metrics_shape")
        if cfg_metrics_shape:
            metrics_shape_value = cfg_metrics_shape  # 用户 cfg 显式 opt-in
    except (FileNotFoundError, KeyError):
        pass  # defaults to registry / MetricsShape.EVALUATE_LEARNER
    _is_runner = (
        metrics_shape_value is MetricsShape.EVALUATE_RUNNER
        if isinstance(metrics_shape_value, MetricsShape)
        else metrics_shape_value == "adapter"  # 老字符串 fallback
    )
    official_metrics = dispatch_test_call(
        contract=contract,
        learner=learner,
        ws=ws,
        metrics_shape=metrics_shape_value,
        shared_context=shared_context,
        adapter_runner=resolve_official_adapter_runner(
            is_evaluate_runner=_is_runner, ws=ws,
        ),
    )
    cfg["last_completed_epoch"] = last_completed_epoch
    contract.finalize_run(
        repo_root=_REPO_ROOT, cfg=cfg,
        timer=timer, best_state=best_state, exp_dir=exp_dir,
        experiment=experiment, best_epoch=best_epoch, last_epoch=last_completed_epoch,
        train_eval_metrics=best_metrics if best_state is not None else None,
        contract=contract, ws=ws, learner=learner, shared_context=shared_context,
        precomputed_official_metrics=official_metrics,
        append_repo_ledger=False,
    )

    auto_finalize = os.environ.get("NN_AUTO_FINALIZE_ROUND", "1").strip().lower() not in ("0", "false", "no", "off")
    if auto_finalize and parallel_total <= 1:
        contract.finalize_round([exp_dir], repo_root=_REPO_ROOT)

    if os.environ.get("NN_POST_TRAIN_HOOK", "1").strip().lower() not in (
        "0", "false", "no", "off",
    ):
        try:
            ws.post_train_hook(
                repo_root=_REPO_ROOT,
                exp_dir=exp_dir,
                learner=learner,
                cfg=cfg,
                device=device,
                contract=contract,
                shared_context=shared_context,
                experiment=experiment,
                best_state=best_state,
                official_metrics=official_metrics,
            )
        except Exception:
            print("[train] post_train_hook 失败（不影响训练主流程）", file=sys.stderr, flush=True)
            traceback.print_exc()


if __name__ == "__main__":
    main()
