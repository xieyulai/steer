"""Lock field terminology：30+ 锁字段名 + 5-6 模板示例。

供 lib/lock_normalize.py 使用；用户可在本文件追加新字段，无需改 normalize。
"""

# ── 锁字段词汇（~30 词；normalize 时按此集识别 K=V 语法） ────────────────
LOCK_FIELDS: frozenset[str] = frozenset({
    # LR/BS/seed
    "LR", "BS", "BATCH_SIZE", "EPOCHS", "SEED", "OPTIMIZER", "WEIGHT_DECAY",
    "LR_SCHEDULER", "LABEL_SMOOTHING", "MOMENTUM", "GRAD_CLIP",
    # WP3:physical 范式 β 命名 scheme 锁(adam/lbfgs/adam_lbfgs;adam_lbfgs 一锁锁死流水线)
    "OPTIMIZER_SCHEME",
    # 模型
    "MODEL", "BACKBONE", "MODEL_ARCH", "LOSS",
    # 运行时
    "GPUS", "MAX_PARALLEL", "NUM_WORKERS", "PIN_MEMORY",
    # 数据
    "SPLIT_KIND", "TRAIN", "VAL", "TEST", "NORMALIZE_FIT_ON",
    "DATA_REPRO_PATH", "EVAL_USES", "TEST_USES", "VAL_TEST_SAME_DISTRIBUTION",
    # 可复现性
    "CUDNN_DETERMINISTIC", "CUDNN_BENCHMARK", "DETERMINISTIC", "BENCHMARK",
    # 业务语义
    "SCENARIO", "SCENARIO_AXIS", "SCENARIO_POLICY", "SCENARIO_ID",
    "METRIC_KEY", "KEEP_THRESHOLD", "PRIMARY_DELTA", "EVAL_EVERY",
    "E4_PATH", "E4_EVAL_FOR_KEEP", "TEST_LOADER", "VAL_LOADER",
    "TARGET", "OFFSET",
    # 立项信息权限三问 I1–I3 / 实验目标 G1–G2 / 运行设置 O1 的锁子键（题库 docs/init/init-question-registry.yaml）
    "CONSUMES", "EVAL_ONLY", "READERS", "STRICT", "PATH", "IMPL", "RULE", "RULES", "MACHINE",
    "MODE", "GOAL", "FLOOR", "TIME_BUDGET",
})