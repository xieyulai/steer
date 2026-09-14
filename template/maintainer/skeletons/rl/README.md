# {PROJECT_NAME}

> **Profile**: rl
> **创建时间**: {CREATED_AT}
> **模板版本**: {TEMPLATE_VERSION}

## 1. 项目概述

<!-- TODO: 描述你的 RL 项目目标、环境、模型架构 -->

## 2. 快速开始

```bash
# 安装依赖
poetry install

# 数据准备（根据数据量选择）
# 方式 1：数据量小（<1GB），拷贝到 data/ 目录
cp -r /path/to/data data/

# 方式 2：数据量大（>=1GB），软链接
ln -s /path/to/original/data data/

# 训练
poetry run python train.py

# 查看帮助
poetry run python train.py --help
```

## 3. 配置

### 3.1 数据划分

<!-- D2_DATA_SPLIT -->
PROFILE: rl
DATA_ROOT: {DATA_ROOT}
SPLIT_KIND: {SPLIT_KIND}
TRAIN: {TRAIN_DESC}
VAL: {VAL_DESC}
TEST: {TEST_DESC}
<!-- /D2_DATA_SPLIT -->

### 3.2 场景策略

<!-- SCENARIO_POLICY -->
SCENARIO_AXIS: {SCENARIO_AXIS}
ACTIVE_SCENARIOS: {ACTIVE_SCENARIOS}
SCENARIO_POLICY: {SCENARIO_POLICY}
DEFAULT_SCENARIO: {DEFAULT_SCENARIO}
KEEP_HISTORY_FILTER:
TRAIN_BINDS: single
IMPROVE_MODE_NOTE: see nn-config keep.improve_mode

## 场景设计

**场景维度**：由用户定义（如 dataset+task_config、dataset、method+dataset）
**场景内方法**：reference（复现基线）+ automatic（Agent 搜索）

### Reference 方法（复现已有论文/方法）
<!-- REFERENCE_METHODS -->
<!-- 示例：derpp、er -->
<!-- /REFERENCE_METHODS -->

### Automatic 方法（Agent 自动搜索）
<!-- AUTOMATIC_METHODS -->
<!-- Agent 搜索的新方法会自动添加到这里 -->
<!-- /AUTOMATIC_METHODS -->
<!-- /SCENARIO_POLICY -->

### 3.3 指标快照

<!-- METRICS_SNAPSHOT -->
rect_norm_B: higher
<!-- /METRICS_SNAPSHOT -->

### 3.4 Agent 边界

<!-- AGENT_BOUNDARY -->
# 无则留空
<!-- /AGENT_BOUNDARY -->

## 4. 架构

### 4.1 文件结构

```
├── contract/          # 契约包（不可变）
│   ├── __init__.py    # 门面
│   ├── metrics.py     # 指标定义
│   ├── runtime.py     # 运行时常量
│   ├── prepare_data.py # 数据准备
│   └── test.py        # 官方测试
├── workspace/         # 工作区（可变）
│   └── __init__.py    # RL 模型、训练逻辑
├── train.py           # 训练脚本
├── experiment.py      # 基类（不可改）
├── nn-config.yaml     # 全局配置
└── _runs/             # 运行结果
```

### 4.2 关键方法

**Contract 侧（不可变）：**
- `prepare_data(cfg)` — 准备数据源（RL 通常返回 None）
- `test(learner, ws, *, shared_context)` — 官方台账评估
- `should_keep(current_metrics, history_rows)` — keep/discard 决策

**Workspace 侧（可变）：**
- `build_learner(cfg)` — 构建 RL 模型
- `train_step(learner, source, objective, *, epoch, shared_context)` — 一轮训练（1 segment）
- `evaluate(learner, *, shared_context)` — 训练过程监控评估
- `preflight_env_check(cfg)` — 环境预检查

## 5. 实验记录

<!-- TODO: 记录你的实验结果 -->

## 6. 参考文献

<!-- TODO: 添加相关论文 -->
