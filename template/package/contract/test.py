"""台账终评实现（官方分数唯一来源）。禁止 ws.evaluate。

⚠️ 这是骨架占位符。init 时根据 profile 自动替换为具体实现。
用户需要根据项目实现 test。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from experiment import ExperimentBase


def get_test_loader(
    data_dir: str,
    batch_size: int = 256,
    num_workers: int = 2,
):
    """官方测试集 loader。

    Raises:
        NotImplementedError: 用户需要根据项目实现此函数
    """
    # TODO: 根据你的项目实现 get_test_loader
    # 示例（supervised）：
    # from torch.utils.data import DataLoader
    # from torchvision import datasets, transforms
    # test_set = datasets.FashionMNIST(data_dir, train=False, download=True, transform=...)
    # return DataLoader(test_set, batch_size=batch_size, shuffle=False, num_workers=num_workers)
    raise NotImplementedError("请根据你的项目实现 get_test_loader")


def _official_path_enabled() -> bool:
    """交卷开关：写死字面量（对照臂另拷一份合同改 False）。

    读环境变量会被 G-信息权限 IP5 拦；函数名登记在 runtime.INFO_PERM["official_path_switch"]。
    """
    return True


def _official_forward(learner, ws, batch, *, shared_context: dict):
    """交卷缝：官方分只能从这里出（runtime.INFO_PERM["official_path"]）。

    默认整网前向（full_model）。问② 选受限路径（restricted）时把手续写在这里或它调用的函数里，
    并把该函数名登记到 INFO_PERM["official_path_impl"]；任何一步不满足返回 None——该批记失败，
    **不回退**到整网前向。
    """
    data, _target = batch
    pred, _ = ws.predict(learner, (data, data), shared_context=shared_context)
    return pred


def run(
    learner, ws, *, shared_context: dict,
    adapter_runner: Callable[[], dict[str, float]] | None = None,
) -> dict[str, float]:
    """官方台账评估。

    Args:
        learner: 默认非 None。ADAPTER 模式可传 None (此时必须有 adapter_runner)。
        adapter_runner: ADAPTER 模式业务仓注册的可调用对象,返回 dict[str, float]。
                       None 时走原 supervised 路径(现状)。

    Returns:
        dict: 指标字典（必须与 contract.metrics.METRIC_KEYS 一致）

    Raises:
        NotImplementedError: 用户需要根据项目实现此函数
    """
    # ===========================================================================
    # 业务仓 init 时根据 profile 覆盖本函数;骨架默认行为:
    # - learner 非 None → 跑通常评估
    # - learner is None + adapter_runner 存在 → 调 adapter_runner() 返回 dict
    # - learner is None + adapter_runner 缺 → raise ValueError
    # ===========================================================================
    if learner is None:
        if adapter_runner is not None:
            return adapter_runner()
        raise ValueError(
            "contract.test.run: learner=None 且 adapter_runner=None,"
            " 请显式指定 ADAPTER 路径或确保 supervised 路径传 learner"
        )
    # TODO: 根据你的项目实现 test
    # 示例（supervised）：
    # learner.eval()
    # correct = 0
    # total = 0
    # for data, target in test_loader:
    #     logits, target = ws.predict(learner, (data, target), shared_context=shared_context)
    #     pred = logits.argmax(dim=1)
    #     correct += pred.eq(target).sum().item()
    #     total += target.size(0)
    # return {"val_accuracy": correct / total}
    #
    # 示例（官方分须走交卷缝时，照抄；INFO_PERM["official_path"] != "full_model"）：
    # n_fail = 0
    # for batch in test_loader:
    #     if _official_path_enabled():
    #         pred = _official_forward(learner, ws, batch, shared_context=shared_context)
    #     else:
    #         pred, _ = ws.predict(learner, batch, shared_context=shared_context)
    #     if pred is None:
    #         n_fail += 1          # 该批记失败，不回退整网
    #         continue
    #     ... 累计指标 ...
    # shared_context["official_fail_batches"] = n_fail
    # 全部失败 → 返回零分（不要抛错吞掉台账）
    #
    # 示例（rl）：
    # env = make_eval_env(cfg)
    # obs, _ = env.reset()
    # total_reward = 0
    # done = False
    # while not done:
    #     action, _ = learner.predict(obs, deterministic=True)
    #     obs, reward, terminated, truncated, _ = env.step(action)
    #     total_reward += reward
    #     done = terminated or truncated
    # return {"rect_norm_B": total_reward}
    raise NotImplementedError("请根据你的项目实现 test")
