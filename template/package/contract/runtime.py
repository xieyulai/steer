"""契约运行时常量（数据路径、归一化参数、评估参数）。

⚠️ 这是骨架占位符。init 时根据 profile 自动替换为具体实现。
用户需要根据项目定义常量。
"""
from __future__ import annotations

import os
from pathlib import Path

# ── 数据目录配置 ─────────────────────────────────────────────────
# 优先级：NN_DATA_DIR 环境变量 > DEFAULT_DATA_DIR > data/
# 数据量小（<1GB）：拷贝到 data/ 目录
# 数据量大（>=1GB）：软链接指向原始数据路径
#   ln -s /path/to/original/data data/dataset_name
DEFAULT_DATA_DIR = os.environ.get("NN_DATA_DIR", str(Path(__file__).resolve().parent.parent / "data"))

REPRO_ENV_KEYS: tuple[str, ...] = (
    "NN_SEED",
    "NN_DATA_DIR",
    "CUDA_VISIBLE_DEVICES",
)

# ── v1.24.0 默认 contract 行为 (业务仓 0 改动 = 0 影响) ──────────
# adapters_can_have_no_learner: True 时,contract.test 允许 learner=None;
#   False 时 (默认) 业务仓 ADAPTER 模式必须显式 opt-in 注册 (见 train.py + workspace kind)。
CONTRACT_DEFAULTS = {
    "adapters_can_have_no_learner": False,
}

# ── 信息权限登记表（立项三问的机器可读物）────
# 必须是字面量：experiment.py 用 ast.literal_eval 读取，读 env / 调函数即 IP0 违规。
# 对照实验两臂 = 两份合同（开臂 enforce True / 关臂 False），不用环境变量切换。
# 未登记（删掉本段）= 全部空转；改本段 = 改合同，须 NN_RELAUNCH=1。
INFO_PERM = {
    "enforce": True,
    "official_path": "full_model",        # full_model | restricted | eval_mode_locked（问②）
    "official_path_impl": None,           # restricted / eval_mode_locked 时 run() 必须调用的函数名
    "official_path_switch": "_official_path_enabled",   # 交卷开关函数名；存在则须单条 return True/False
    "eval_only_assets": (),               # 问①：只评资产——路径 glob，或 contract. 开头的读取函数名
    "eval_only_readers": ("contract/test.py",),          # 允许打开只评资产的文件（仓根相对路径）
    "train_batch_keys": None,             # 训练首 batch 键白名单（dict 键 / tuple 项数）；None 不校
    "strict_no_train_files": False,       # D2 TRAIN 为「无数据文件」时置 True：工作区不得读任何数据文件
}
