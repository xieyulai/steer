# {PROJECT_NAME}

> **Profile**: {PROFILE}
> **创建时间**: {CREATED_AT}
> **模板版本**: {TEMPLATE_VERSION}

<!-- NN_TEMPLATE:NAV -->
| 你想… | 看这里 |
|--------|--------|
| 让 Agent 帮你做什么 | **§2 技能清单** |
| 指标、数据、场景怎么定 | **§3 项目口径** |
| 单轮流程与硬规则 | 根目录 **`CLAUDE.md`** |
| 进展、坑、组内约定 | **§4 维护笔记**（你自己写） |
<!-- /NN_TEMPLATE:NAV -->

本项目装自 **STEER** 实验框架。立项完成后**独立运行**——日常请用 **`/auto-nn-*` 技能**驱动 Agent，不要手改成绩表、不要绕过技能直接改脚本跑实验。

---

<!-- NN_TEMPLATE:QUICKSTART -->
## §1 快速开始

```bash
poetry install
poetry run python train.py              # 全量训练
NN_SMOKE=1 poetry run python train.py   # 短训验收（scripts/smoke-check.sh）
./auto-nn-run.sh N                      # 自动跑 N 轮（需已安装全局技能，见 §2）
```

代码分层：`experiment.py`（框架，不改）→ `contract/`（合同，立项时定）→ `workspace/` + `train.py`（实验迭代可改）。详见 **`CLAUDE.md`**。
<!-- /NN_TEMPLATE:QUICKSTART -->

---

<!-- NN_TEMPLATE:SKILLS -->
## §2 技能清单（用技能维护本仓库）

<!-- SKILLS_GUIDE -->
全局技能安装（每人一次，在 **STEER** 模板仓库根目录）：

```bash
./install.sh
```

之后在 Cursor 输入 **`/auto-nn-<name>`**（当前目录必须是**本项目根目录**）。请**优先用斜杠技能**，避免 Agent 和手跑混在一起。

**上下文优先级**：`HUMAN_GUIDANCE` → `REFLECT_INDEX pending` → `EXPERIENCE`

| 技能 | 什么时候用 | 你怎么说 / 怎么触发 |
|------|------------|---------------------|
| `/auto-nn-check` | 看台账某几行、某几列 | 「看 TSV 最近几行 / 某场景最优」 |
| `/auto-nn-doctor` | 检查目录、契约、治理 | 「跑 doctor」 |
| `/auto-nn-analyse` | 分析趋势、撞墙、升档（**不训练**） | 「分析最近几轮」 |
| `/auto-nn-modify` | 改模型、loss、指标列、场景 | 「加 loss / 改 TSV 列」 |
| `/auto-nn-clear` | 删 junk、清 exp | 「清理旧 run」（删除须本地 `--apply`） |
| `/auto-nn-human-guidance` | 写人类路线图 | 「写阶段 1 NOTE」 |
| `/auto-nn-goal` | 目标值、实验模式 | 「设目标值」「切 explore」 |
| `/auto-nn-manual-run` | 手控单轮：改码→训→KEEP | 仅要全程自己控时用 |
| `/auto-nn-auto-run` | **推荐** 自动 N 轮 | 「自动跑 20 轮」→ `./auto-nn-run.sh N` |
| `/auto-nn-reflect` | 撞墙反思、不训练 | 「跑 reflect」 |
| `/auto-nn-compress` | 经验文档太长 | 「压缩 EXPERIENCE」 |
| `/auto-nn-update` | 拉框架更新 | 「update」（**在本项目根目录**） |

**只读**（不训练、不改码）：`check`、`analyse`、默认 `doctor`。  
reflect 可选 `SERPER_API_KEY`、`GITHUB_TOKEN`；无则部分检索跳过，不阻断。
<!-- /SKILLS_GUIDE -->

### 推荐工作流（少手跑，多走技能）

<!-- SKILLS_SCENARIOS -->
| 阶段 | 串联 |
|------|------|
| **刚建好** | `/auto-nn-doctor` → `/auto-nn-human-guidance` → `/auto-nn-auto-run` 试 1 轮 |
| **日常** | `/auto-nn-analyse` → `/auto-nn-modify`（若改代码）→ `/auto-nn-auto-run` |
| **长跑** | （可选）`/auto-nn-goal` → `./auto-nn-run.sh N`（训中勿 update） |
| **撞墙** | `/auto-nn-check` → `/auto-nn-analyse` → `/auto-nn-reflect` → 继续 auto-run |
| **清磁盘** | `/auto-nn-clear` → `/auto-nn-auto-run` |
| **框架更新** | `/auto-nn-update` → `/auto-nn-doctor` |
| **文档太長** | `/auto-nn-compress` |

**原则**：看用 `analyse`，改用 `modify`，跑实验优先 **`auto-run`**；不要跳过技能手改台账或手敲正式训练。
<!-- /SKILLS_SCENARIOS -->
<!-- /NN_TEMPLATE:SKILLS -->

---

## §3 项目口径（立项时确定）

> 本节在 **`/auto-nn-init`** 阶段填写；改指标、数据划分、场景须走 **`/auto-nn-modify`**，改 `contract/` 时常需 `NN_RELAUNCH=1`。  
> **`/auto-nn-update` 不会改本节**——你的指标和数据约定会保留。

### 3.1 评估与指标

<!-- TODO: 立项时填写：`contract.test` 与 `workspace.evaluate` 何时调用、用什么数据、返回哪些键；与 `contract/metrics.py` 一致。 -->

### 3.2 数据划分

<!-- D2_DATA_SPLIT -->
PROFILE: {PROFILE}
DATA_ROOT: {DATA_ROOT}
SPLIT_KIND: {SPLIT_KIND}
TRAIN: {TRAIN_DESC}
VAL: {VAL_DESC}
TEST: {TEST_DESC}
NORMALIZE_FIT_ON:                # 归一化 fit 用的数据（通常 train）
EVAL_USES:                       # 训内评估用哪份
TEST_USES:                       # 训末官方测试用哪份
E3_EVAL_FOR_KEEP: contract.test  # KEEP 仅看 contract.test（勿用 ws.evaluate）
VAL_TEST_SAME_DISTRIBUTION: yes  # 验证集/测试集同分布？yes/no/na
<!-- /D2_DATA_SPLIT -->

### 3.2b 信息权限（立项三问落盘；须与 `contract/runtime.py` 的 `INFO_PERM` 一致）

<!-- INFO_PERM -->
TRAIN_CONSUMES:                  # 问①：A 全部 / B 只有训练份（一句写哪些只评）/ C 无数据（样本由代码生成）
OFFICIAL_PATH:                   # 问②：A 整网前向 / B 受限路径（写手续函数名）/ C 固定评测态
OTHER_RULES:                     # 问③：均无 / 逐行写；机器不管的规则标「（机器不管）」
ENFORCE:                         # yes / no（对照关臂 no）；须与 INFO_PERM["enforce"] 一致
<!-- /INFO_PERM -->

### 3.3 场景策略

多场景时：**focus** = 只盯一个场景；**rotate** = 在 active 列表里轮着试。  
改策略须 **先停** 正在跑的 `auto-nn-run`，再用：

```bash
python3 scripts/set-scenario-policy.py rotate --active "场景1,场景2,…" --verify
```

（同步 `nn-config.yaml` 与下方块，勿手改两处。）

<!-- SCENARIO_POLICY -->
SCENARIO_AXIS: {SCENARIO_AXIS}
ACTIVE_SCENARIOS: {ACTIVE_SCENARIOS}
SCENARIO_POLICY: {SCENARIO_POLICY}
DEFAULT_SCENARIO: {DEFAULT_SCENARIO}
KEEP_HISTORY_FILTER:
TRAIN_BINDS: single
IMPROVE_MODE_NOTE: see nn-config keep.improve_mode

## 场景设计

**核心原则**：场景内的东西是可以比的；场景间的东西是不可比的

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

### 3.4 指标快照

<!-- METRICS_SNAPSHOT -->
<!-- TODO: 键须与 contract.metrics.METRIC_KEYS 一致 -->
<!-- 示例：val_accuracy: higher -->
<!-- /METRICS_SNAPSHOT -->

### 3.5 额外硬约束（可选）

<!-- AGENT_BOUNDARY -->
<!-- TODO: 无则留空 -->
<!-- 示例：ENV_OVERRIDES_OK=NN_DEVICE（会话可改环境变量白名单；NN_TIME_BUDGET 已冻结为 yaml 派生量，勿列入） -->
<!-- /AGENT_BOUNDARY -->

---

## §4 维护笔记（你自己写）

<!-- PROJECT_NOTES -->
立项时可留一行摘要；之后随时更新，例如：

- 当前最好成绩、对应哪一轮
- 数据在哪、怎么下载、已知坑
- 用哪张 GPU、并行几槽、谁负责 commit 台账

**不要把 §2 技能表复制到这里**——技能说明以 §2 为准，框架更新时会自动对齐 §2。
<!-- /PROJECT_NOTES -->

---

<!-- NN_TEMPLATE:APPENDIX -->
## 附录 · 新建同类项目

```bash
# 在 STEER 模板仓库根目录
./scripts/new-project.sh ../<目录> <项目名> --profile <supervised|rl|physical>
```

新建或迁入走 **`/auto-nn-init`**。
<!-- /NN_TEMPLATE:APPENDIX -->
