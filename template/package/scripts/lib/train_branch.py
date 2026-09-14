"""v1.33.0 — train.py 双路径入口 dispatcher(单维度 metrics_shape)。

业务仓 zero knowledge: train.py 386 行调 ``dispatch_test_call`` 即可,
MetricsShape.EVALUATE_LEARNER / EVALUATE_RUNNER 二选一,纯函数可单测。
老字符串 "supervised" / "adapter" / "mammoth_cl" 通过 MetricsShape.from_legacy()
归一,标 DeprecationWarning(expand 阶段;contract 阶段 Task 9 删除 from_legacy)。

另含维度 A ``dispatch_training``（NATIVE / IN_PROCESS / SUBPROCESS 注入式分流）
与 SUBPROCESS 最小协议 ``run_subprocess_training``。
"""
from __future__ import annotations

from typing import Any, Callable

from scripts.lib.train_branch_types import MetricsShape, TrainingMech


def resolve_official_adapter_runner(*, is_evaluate_runner: bool, ws: Any) -> Callable[[], dict[str, float]] | None:
    """训末取 runner：仅评 runner 形态才读 ``ws.adapter_runner``；评模型路径不触碰该属性。"""
    if not is_evaluate_runner:
        return None
    return getattr(ws, "adapter_runner", None)


def dispatch_test_call(
    *,
    contract: Any,
    learner: Any,
    ws: dict,
    metrics_shape: MetricsShape | str,
    shared_context: dict,
    adapter_runner: Callable[[], dict[str, float]] | None,
) -> dict[str, float]:
    """train.py 386 行的 dispatcher。纯函数,无副作用。

    Args:
        contract: Contract 子类实例。
        learner: 当前 train 出来的 model。EVALUATE_RUNNER 模式可为 None。
        ws: workspace 实例。EVALUATE_RUNNER 模式从其 ``adapter_runner`` 属性取 callable。
        metrics_shape: MetricsShape enum 或老字符串("supervised"/"adapter"/"mammoth_cl")。
                       字符串会触发 MetricsShape.from_legacy() 归一 + DeprecationWarning。
        shared_context: train.py 维护的共享 dict,透传给 contract.test。
        adapter_runner: 业务仓在工作区实例上设置的可调用对象,返回 dict[str, float]。

    Returns:
        评估得到的 metrics dict(contract.test 原样返回)。

    Raises:
        ValueError: metrics_shape 不支持,或 EVALUATE_RUNNER 模式缺 adapter_runner。
    """
    # 字符串 → enum 归一(支持老 "supervised"/"adapter"/"mammoth_cl" 写法)
    if isinstance(metrics_shape, str):
        metrics_shape = MetricsShape.from_legacy(metrics_shape)

    if metrics_shape is MetricsShape.EVALUATE_LEARNER:
        return contract.test(learner, ws, shared_context=shared_context)

    if metrics_shape is MetricsShape.EVALUATE_RUNNER:
        if adapter_runner is None:
            raise ValueError(
                "metrics_shape=EVALUATE_RUNNER 必须显式提供 adapter_runner "
                "(来自 ws.adapter_runner 或 train.py 直接构造)"
            )
        return contract.test(
            None, ws, shared_context=shared_context,
            adapter_runner=adapter_runner,
        )

    raise ValueError(
        f"metrics_shape={metrics_shape!r} 不支持 "
        f"(支持: {[m.name for m in MetricsShape]})"
    )


def run_subprocess_training(
    *,
    cmd: list[str],
    result_path: Any,
    cwd: Any | None = None,
) -> dict:
    """SUBPROCESS 最小协议：跑命令 → 读 JSON 结果 → 映射为与 NATIVE 同形的四键 dict。

    JSON 必须含 ``best_metrics``（dict）。可选 ``best_state`` / ``best_epoch`` /
    ``last_completed_epoch``；缺省分别为 ``None`` / ``0`` / ``0``。
    """
    import json
    import subprocess
    from pathlib import Path

    result_path = Path(result_path)
    cwd_path = Path(cwd) if cwd is not None else None
    subprocess.run(list(cmd), check=True, cwd=str(cwd_path) if cwd_path else None)
    if not result_path.is_file():
        raise FileNotFoundError(
            f"SUBPROCESS 结果文件不存在: {result_path}（命令={cmd!r}）"
        )
    data = json.loads(result_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"SUBPROCESS 结果 JSON 须为 object，得到 {type(data).__name__}")
    best_metrics = data.get("best_metrics")
    if not isinstance(best_metrics, dict):
        raise ValueError(
            "SUBPROCESS 结果 JSON 须含 best_metrics（dict）；"
            f"得到 {type(best_metrics).__name__}"
        )
    return {
        "best_state": data.get("best_state"),
        "best_metrics": best_metrics,
        "best_epoch": int(data.get("best_epoch", 0) or 0),
        "last_completed_epoch": int(data.get("last_completed_epoch", 0) or 0),
    }


def invoke_framework_train(ws: Any, /, **kwargs: Any) -> dict:
    """IN_PROCESS：调 ``ws.framework_train``（新钩子，不复用 train_step）。"""
    fn = getattr(ws, "framework_train", None)
    if not callable(fn):
        raise NotImplementedError(
            "training_mech=IN_PROCESS 需要可调用的 ws.framework_train(...);"
            "见 PROTOCOL §3.0.3"
        )
    return fn(**kwargs)


def resolve_subprocess_cmd_and_result(ws: Any, exp_dir: Any) -> tuple[list[str], Any]:
    """从 workspace 解析 SUBPROCESS 命令与结果路径。

    - 命令：``ws.framework_subprocess_cmd(exp_dir) -> list[str]``
    - 结果：``ws.framework_result_path`` 为 Path/str，或 ``(exp_dir) -> Path``；
      相对路径相对于 ``exp_dir``。
    """
    from pathlib import Path

    exp_dir = Path(exp_dir)
    cmd_fn = getattr(ws, "framework_subprocess_cmd", None)
    if not callable(cmd_fn):
        raise NotImplementedError(
            "training_mech=SUBPROCESS 需要 ws.framework_subprocess_cmd(exp_dir) -> list[str];"
            "见 PROTOCOL §3.0.3"
        )
    cmd = cmd_fn(exp_dir)
    if not isinstance(cmd, (list, tuple)) or not all(isinstance(x, str) for x in cmd):
        raise ValueError(
            f"framework_subprocess_cmd 须返回 list[str]，得到 {type(cmd).__name__}"
        )
    raw = getattr(ws, "framework_result_path", None)
    if callable(raw):
        raw = raw(exp_dir)
    if raw is None:
        raise NotImplementedError(
            "training_mech=SUBPROCESS 需要 ws.framework_result_path"
            "（Path/str 或 (exp_dir)->Path）；见 PROTOCOL §3.0.3"
        )
    result_path = Path(raw)
    if not result_path.is_absolute():
        result_path = exp_dir / result_path
    return list(cmd), result_path


_TRAINING_RESULT_KEYS = (
    "best_state",
    "best_metrics",
    "best_epoch",
    "last_completed_epoch",
)


def normalize_training_result(raw: Any) -> dict:
    """三种 TrainingMech 共用的结果归一：四键必填 + 可选 ``stop_reason``。

    - ``best_state`` 可为 ``None``；``best_metrics`` 必须是 dict。
    - 缺 / 空 ``stop_reason`` → ``mech_complete``（NATIVE 应自行带出真实原因）。
    """
    if not isinstance(raw, dict):
        raise ValueError(
            f"训练结果须为 dict，得到 {type(raw).__name__}"
        )
    missing = [k for k in _TRAINING_RESULT_KEYS if k not in raw]
    if missing:
        raise ValueError(
            f"训练结果缺键 {missing}（须含 {_TRAINING_RESULT_KEYS}）"
        )
    best_metrics = raw["best_metrics"]
    if not isinstance(best_metrics, dict):
        raise ValueError(
            "训练结果 best_metrics 须为 dict；"
            f"得到 {type(best_metrics).__name__}"
        )
    stop_raw = raw.get("stop_reason")
    if stop_raw is None or (isinstance(stop_raw, str) and not str(stop_raw).strip()):
        stop_reason = "mech_complete"
    else:
        stop_reason = str(stop_raw)
    return {
        "best_state": raw["best_state"],
        "best_metrics": best_metrics,
        "best_epoch": int(raw["best_epoch"] or 0),
        "last_completed_epoch": int(raw["last_completed_epoch"] or 0),
        "stop_reason": stop_reason,
    }


def dispatch_training(
    *,
    training_mech: TrainingMech | str,
    run_native: Callable[[], dict],
    run_in_process: Callable[[], dict] | None = None,
    run_subprocess: Callable[[], dict] | None = None,
) -> dict:
    """train.py 训练主循环的 dispatcher(维度 A — 训练调度分流)。纯函数,无副作用。

    对照 ``dispatch_test_call``(评估侧)。注入式:
    - NATIVE → ``run_native``
    - IN_PROCESS → ``run_in_process``（缺注入则 NotImplementedError，禁止回退 NATIVE）
    - SUBPROCESS → ``run_subprocess``（同上）

    出口经 ``normalize_training_result``：四键 + ``stop_reason``（缺省 ``mech_complete``）。

    Args:
        training_mech: TrainingMech enum 或字符串(成员名 NATIVE/IN_PROCESS/SUBPROCESS
            或值 native/in_process/subprocess;YAML cfg ``workspace.training_mech`` 写法)。
        run_native: train.py 注入的 native 训练闭包,返回四键 dict（可含 stop_reason）。
        run_in_process: 可选；IN_PROCESS 时必填。
        run_subprocess: 可选；SUBPROCESS 时必填。

    Returns:
        归一后的训练产物 dict（见 PROTOCOL §3.0.3）。

    Raises:
        NotImplementedError: 非 NATIVE 且对应 callable 未注入。
        ValueError: training_mech 为不支持的值，或结果缺键 / 形不对。
    """
    # 字符串 → enum 归一(YAML cfg 产出 str;先按成员名,再按值,对照 dispatch_test_call)
    if isinstance(training_mech, str):
        try:
            training_mech = TrainingMech[training_mech]        # 按成员名(NATIVE/IN_PROCESS/SUBPROCESS)
        except KeyError:
            try:
                training_mech = TrainingMech(training_mech)    # 按值(native/in_process/subprocess)
            except ValueError:
                raise ValueError(
                    f"training_mech={training_mech!r} 不支持 "
                    f"(支持: {[m.name for m in TrainingMech]})"
                ) from None

    if training_mech is TrainingMech.NATIVE:
        return normalize_training_result(run_native())

    if training_mech is TrainingMech.IN_PROCESS:
        if run_in_process is None:
            raise NotImplementedError(
                "training_mech=IN_PROCESS 未注入 run_in_process；"
                "train.py 应注入调用 ws.framework_train 的闭包（见 PROTOCOL §3.0.3）"
            )
        return normalize_training_result(run_in_process())

    if training_mech is TrainingMech.SUBPROCESS:
        if run_subprocess is None:
            raise NotImplementedError(
                "training_mech=SUBPROCESS 未注入 run_subprocess；"
                "train.py 应注入 run_subprocess_training 闭包（见 PROTOCOL §3.0.3）"
            )
        return normalize_training_result(run_subprocess())

    raise ValueError(
        f"training_mech={training_mech!r} 不支持 "
        f"(支持: {[m.name for m in TrainingMech]})"
    )


def finalize_training_loop_artifacts(
    *,
    exp_dir: Any,
    learner: Any,
    repo_root: Any,
    cfg: dict | None,
    epochs_configured: int,
    result: dict,
) -> dict:
    """dispatch_training 之后的 mech 无关收尾：写 ``train_done.json`` + checkpoint 策略。

    ``result`` 应为 ``normalize_training_result`` / ``dispatch_training`` 出口形
   （四键 + ``stop_reason``）。三种 TrainingMech 共用。
    """
    import json
    from pathlib import Path

    from experiment import apply_checkpoint_policy_to_learner, build_train_done_payload

    exp_path = Path(exp_dir)
    stop_reason = str(result.get("stop_reason") or "mech_complete")
    payload = build_train_done_payload(
        last_completed_epoch=int(result["last_completed_epoch"]),
        epochs_configured=int(epochs_configured),
        best_epoch=int(result["best_epoch"]),
        stop_reason=stop_reason,
        early_stop=None,
    )
    with open(exp_path / "train_done.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    apply_checkpoint_policy_to_learner(
        learner, repo_root=repo_root, cfg=cfg, best_state=result["best_state"],
    )
    return payload
