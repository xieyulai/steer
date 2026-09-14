"""v1.33.0 — Dispatcher 三维正交 enum 定义(纯数据,无副作用)。

3 个正交 enum:
  - MetricsShape  : 评估形态(metric 怎么进 contract.test)
  - TrainingMech  : 训练机制(谁负责训 train 出来的 model)
  - FrameworkKind : framework 身份(已知 framework registry)

向后兼容:
  - 老字面值 "supervised" / "adapter" 通过 MetricsShape.from_legacy() 归一
  - 老字面值 "mammoth_cl" 走 MetricsShape.from_legacy() + FrameworkKind.MAMMOTH 推断
  - workspace.WorkspaceKind 是 MetricsShape 的别名(import 路径保留)
"""
from __future__ import annotations

import enum
import warnings


class MetricsShape(enum.Enum):
    """评估形态:metric 怎么进 contract.test(纯数据,1 维)。

    选择 EVALUATE_LEARNER / EVALUATE_RUNNER 同前缀 EVALUATE_*:
    一眼一组,读出来"评估 learner / 评估 runner",意图+对象都到位。
    """
    EVALUATE_LEARNER = "evaluate_learner"
    EVALUATE_RUNNER = "evaluate_runner"

    @classmethod
    def from_legacy(cls, value: str) -> "MetricsShape":
        """老字符串 → enum 归一入口(带 DeprecationWarning)。

        支持字面值:
          "supervised" → EVALUATE_LEARNER
          "adapter"    → EVALUATE_RUNNER
          "mammoth_cl" → EVALUATE_LEARNER(mammoth_cl 不改 dispatcher,走 builtin alias)
        未知字符串 → raise ValueError(不静默兜底)。
        """
        if not isinstance(value, str):
            raise ValueError(f"MetricsShape.from_legacy 仅接受 str,得 {type(value).__name__}")
        legacy_map = {
            "supervised": cls.EVALUATE_LEARNER,
            "adapter": cls.EVALUATE_RUNNER,
            "mammoth_cl": cls.EVALUATE_LEARNER,
        }
        if value not in legacy_map:
            raise ValueError(
                f"workspace_kind 字面值={value!r} 不支持(支持: {sorted(legacy_map)})"
            )
        if value in ("supervised", "adapter", "mammoth_cl"):
            warnings.warn(
                f"workspace_kind={value!r} 已弃用;改用 MetricsShape.{legacy_map[value].name}",
                DeprecationWarning,
                stacklevel=2,
            )
        return legacy_map[value]


class TrainingMech(enum.Enum):
    """训练机制:谁负责训 train 出来的 model。

    选择 3 值:
      SUBPROCESS  → subprocess.run([framework_cli, ...])
      IN_PROCESS  → from framework.X import X,workspace 自写 train_step
      NATIVE      → for batch in loader,自写训练循环(template 默认)
    """
    SUBPROCESS = "subprocess"
    IN_PROCESS = "in_process"
    NATIVE = "native"


class FrameworkKind(enum.Enum):
    """framework 身份:已知 framework registry;UNKNOWN = 自写框架/识别不到。

    选择 5 常见 + 1 fallback:
      MAMMOTH / LIGHTNING / HF_TRAINER / TIMM / AVALANCHE / UNKNOWN
    新增 framework = 业务仓手动加 enum 成员(本 enum 不会动态扩展)。
    """
    MAMMOTH = "mammoth"
    LIGHTNING = "lightning"
    HF_TRAINER = "hf_trainer"
    TIMM = "timm"
    AVALANCHE = "avalanche"
    UNKNOWN = "unknown"

    @classmethod
    def from_module_hint(cls, module_name: str | None, registry_hint: str | None = None) -> "FrameworkKind":
        """从模块名 + 显式 hint 推断 framework 身份。

        module_name: 业务仓 register_* 装饰器所在模块名(子串匹配)
        registry_hint: framework_hint.get("name") 的值(显式 opt-in)
        """
        candidates = (registry_hint or "", module_name or "")
        joined = " ".join(candidates).lower()
        if "mammoth" in joined:
            return cls.MAMMOTH
        if "lightning" in joined or "pytorch_lightning" in joined:
            return cls.LIGHTNING
        if "transformers" in joined or "hf_trainer" in joined or "huggingface" in joined:
            return cls.HF_TRAINER
        if "timm" in joined:
            return cls.TIMM
        if "avalanche" in joined:
            return cls.AVALANCHE
        return cls.UNKNOWN


# WorkspaceKind 别名 — 保留旧 import 路径
WorkspaceKind = MetricsShape

__all__ = ["MetricsShape", "TrainingMech", "FrameworkKind", "WorkspaceKind"]
