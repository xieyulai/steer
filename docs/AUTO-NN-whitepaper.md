# AUTO-NN Whitepaper

> **定位**：auto-nn 的唯一体系总览，面向维护者和高级使用者。本文是技术文档，不是论文，也不是脚本手册。
>
> **范围**：说明 auto-nn 如何把一个神经网络项目接入、治理并持续实验。具体命令、参数和脚本细节以 `PROTOCOL.md`、各技能 `SKILL.md` 和代码为准。
>
> **一句话**：auto-nn = 接入式 build + 围栏式 governance + 进化式 experiment。先把项目接进来，再守住边界，最后在边界内持续做实验。
>
> **版本演进速查（自 v1.7.0 起）**：v1.7.0 P0 探索契约落地（5 层 guidance）→ v1.7.2 撤回空壳归位 → v1.8.0 abcde-boundaries.yaml 物理退役 → v1.9.0 init presets 路线（aggressive-minimal / conservative-baseline，后续版本已退役）→ v1.10.0 注册制重构（WP0+WP1+WP3：scenarios/*.yaml 4 场景 + 三范式 contract/ 子目录布局 + learner/objective/augmentation registry + optimizer/scheduler cfg 分派 + physical β named scheme elif 分派 + 治理层锁 OPTIMIZER_SCHEME）→ v1.10.1 论文合成 → v1.14.0 init 对象类型 overlay（5 object_type + 5 overlay 模板 + framework 信号入口接通）→ v1.16.0 guidance.yaml + abcde_defaults.py 整体删除 → v1.19.0 paradigm-lock-aware ABCDE（要求1+2+4）→ **v1.22.0 init-workflow 重构（**4 scenarios × 5 object_type 双轴 → 3 workflow × 3 object_type 单轴 `detect()`**；ADAPTER scenario + atomic_package/workspace_full 退役；`init_workflow.py` 取代 `init_scenarios.py`，`detect()` 取代 `_classify_object_type`，`--force-workflow` 取代 `--force-scenario`，`templates/{build,migrate,update}.md` 取代 `templates/{greenfield,migration,adapter,reinit}.md`）**。沙箱测试设施自 v1.4.0 起剥离至独立仓 **`sandbox-auto-nn`**，模板仓不持有。

---

## 0. 总览

auto-nn 的核心不是“多几个自动化命令”，而是把 LLM Agent 参与神经网络实验拆成三个阶段：

| 阶段 | 节奏 | 解决的问题 | 主要产物 | 主技能 |
|---|---|---|---|---|
| **build** | 一次性 | 项目能不能被 auto-nn 接管 | 研究合同、初始配置、工作区结构 | `init` |
| **governance** | 持续性 | 实验会不会跑偏、越权、失证 | 边界、体检、目标、路线图、更新机制 | `doctor` / `update` / `modify` / `clear` / `goal` / `human-guidance` |
| **experiment** | 循环性 | 如何在边界内提出、执行、评估下一轮实验 | 运行记录、结果判定、反思、长期记忆 | `auto-run` / `manual-run` / `analyse` / `reflect` / `check` / `compress` / `audit` |

三阶段关系如下：

```text
build
  └─ 建立研究合同、目录结构和初始边界
      ↓
governance
  └─ 持续维护任务、行动、证据和状态边界
      ↓
experiment
  └─ 在边界内循环提出假设、运行实验、记录证据、反思下一步
      ↓
反馈到 governance
  └─ 每轮暴露的漂移、缺证、撞墙和维护问题进入治理层处理
```

不要把三阶段理解成三个互不相关的模块。它们是时间层级：

- build 只在接入或重接入时发生。
- governance 一直存在，保护系统不跑偏。
- experiment 反复发生，并把问题反馈给 governance。

---

## 1. build：接入式阶段

build 的任务是把一个项目变成“可治理、可运行、可记录”的 auto-nn 项目。

### 1.1 build 做什么

build 主要完成四件事：

| 事项 | 说明 |
|---|---|
| 项目接入 | 支持新项目、迁移旧项目、外部框架适配、同仓重新接入 |
| 研究合同 | 固定数据、场景、主指标、评估方式、KEEP 口径和停止条件 |
| 工作区结构 | 明确 contract 与 workspace 的职责分离 |
| 初始运行策略 | 写入实验模式、目标值、外部证据深度和反思节奏 |

**接入路径选择**（v1.10.0 注册制重构落地）：init 阶段按 workflow 自动判定选路：

**workflow 自动判定**：`scripts/init_workflow.py` 的 `classify()` 看 `source_root` 在不在、`contract/` 有没有、是否同仓 → **3 workflow（BUILD / MIGRATE / UPDATE，v1.22.0 取代原 4 场景 GREENFIELD / MIGRATION / ADAPTER / REINIT，ADAPTER 已退役）**。每 workflow 契约落在 `template/package/scenarios/<name>.yaml`（recognition / freedom_levels ABCDE / decision_tree 三段；v1.22.0 起 yaml 文件名 = workflow 名：`build.yaml` / `migrate.yaml` / `update.yaml`）。

"项目接入"按 `scripts/init_workflow.py` 判定 **3 种 workflow**（v1.22.0 init-workflow 重构：原 `init_scenarios.py` 4 场景 → `init_workflow.py` 3 workflow；ADAPTER 已退役），决定 init 走哪条路径：

| workflow | 判定条件 | 含义 |
|---|---|---|
| **BUILD**（原 GREENFIELD） | 无 source_root | 从零立项，无旧代码 |
| **MIGRATE**（原 MIGRATION） | 有 source_root、无 contract/ | 迁入已有项目，选择性移植 |
| **UPDATE**（原 REINIT） | source_root == repo_root | 同仓二次 init，沿用配置与历史 |

> v1.22.0 路径判据不变（替换的是命名 + 落盘产物路径），原 GREENFIELD/MIGRATION/REINIT 三个场景判据全部保留；**ADAPTER 已退役**——4 → 3 workflow。

**对齐环节**（picker 之前）：init 在 26/29 问逐项确认（picker；2026-09 起含信息权限三问，可由 `--answers` 答案清单预填 8 题）之前，有个**对齐理解**环节——agent 读 `source_root` 代码，按**单轴同链路**硬判 + **旁路探针**建议（v1.48.18+）：① **3 workflow**（路径硬判，`init_workflow.classify` / `detect`）；② **3 object_type**（`code` / `framework` / `data`——改码能碰多深；migrate 扫 **源仓**；**BUILD 默认建议 data**，避免脚手架 `@register_*` 误判 framework）；③ **`align_probe`** 另给 `profile_suggested`（supervised/rl/physical）与 `framework_name` 建议（可解释证据；与 `--profile` 冲突须 `--accept-profile-override`）。人对齐确认后落盘 **`.auto-nn/init-align.json`**；`new-project` / `init_o3` 生成手册以该文件为准。纯数据源禁止 migrate。O3 尺子意图落 `saved/baseline_start_intent.json`（跳过须 `.auto-nn/baseline-intent-skipped`）；qa-log 闭合后 verify/doctor 缺意图 → FAIL。

> ✅ **v1.14.0 接通信号入口 → v1.16.5 修 adapter 短路 → v1.22.0 5→3 档收口**：framework 信号入口已接代码（`write_init_outputs` 加 `framework` 入参 + 3 overlay 模板 + SKILL.md §4 HARD-GATE；v1.16.0 前经 `default_guidance` 中转，v1.16.0 `abcde_defaults.py` 删后改直传，v1.22.0 `detect()` 单轴入口）。**`framework` + 注册制框架（mammoth/lightning/avalanche…）已实证**：`detect(update, framework={name:mammoth})` 产 manual 头 `对象类型=framework`、B 行=跨系列架构切换、路径上限=register（1.16.5 前 adapter 短路曾架空 `_COMPLEX_FRAMEWORKS` 名单、无脑判 `atomic_package`，已修）。

build 的关键产物不是某个脚本，而是**研究合同**。研究合同回答：

- 用什么数据。
- 比什么指标。
- 哪个评估结果算官方结果。
- 什么情况下保留一轮结果。
- 哪些改动属于改题，需要重新确认。

### 1.2 contract / workspace 分工

auto-nn 的可治理性依赖 contract 与 workspace 的分工。

| 部分 | 负责什么 | 可以怎么改 |
|---|---|---|
| contract | 任务定义、数据口径、官方评估、指标和 KEEP 规则 | 只能在接入或明确重签时改 |
| workspace | 模型、损失、训练步骤、数据处理实现 | 日常实验可以改，但必须受 contract 约束 |
| train | 调度 contract 与 workspace（v1.24.0 起：`train.py:386` 走 `dispatch_test_call` 双路径分桶，按 `workspace_kind` 派发 supervised/adapter） | 可以编排训练，但不能私自改评估口径 |

这套分工的目的很简单：**什么算好**和**怎么变好**必须分开。  
如果模型提升来自 workspace 的变化，是实验进展；如果提升来自 contract 的变化，就是改题。

**题面归位（已全数回撤）**：1.7.0 曾把 `SCENARIO_ID` / `KEEP_THRESHOLD` / `protected_paths` 作为「任务级题面键」收进 `contract/`（init 填、常规冻结，仿 `METRIC_KEYS` 模式），后陆续核实均为空壳并回撤：

- **`SCENARIO_ID`**：`contract/__init__.py` 的 `Contract.scenario_id` property 读的是 `contract/metrics.py` 里 init 从不填充的空常量（`SCENARIO_ID = ""`），永远返回空——**断链**。真实场景号一直在 cfg 层（`config.json` / train.py 全局，init 填），防护靠 `validate_scenario_id`（不在 README「场景清单」表则 raise，no-fallback）。property 与常量已退役；**场景号属 cfg 层实验参数，contract 不持有场景号**（scenario 不写进 contract；1 场景或多场景由 README 清单声明，contract 不感知场景数量）。
- **`KEEP_THRESHOLD`**：keep 阈值是探索 mode 的函数（见 `presets.py`：conservative 0.01 / balanced 0.005 / aggressive 0.001 / inductive 0.0005）、不该跟场景号钉死。1.7.2 撤回，keep 口径回归 `nn-config.yaml` 的 `keep` 段（mode 经 `presets.py` 定 `primary_delta`）。
- **`protected_paths`**：无运行时消费者。1.7.2 撤回，仅作 guidance 软概念词保留（非 contract property、非硬门禁）。

### 1.3 workspace 注册机制

§1.2 只讲了 contract / workspace / train 的职责分工，没讲 workspace 内部的扩展机制。本节补完「**加一个新模型/损失/目标，应该改 workspace 的哪个文件、用什么装饰器、cfg 怎么关联**」。

#### 1.3.1 注册装饰器（pluggable 的物质基础）

workspace 用装饰器把模型类、目标函数、数据增强、CLI 翻译函数注册到 registry，让 `train.py` 不需要硬编码 import。三个 registry 与装饰器都定义在 `workspace/__init__.py`：

| 装饰器 | 作用 | registry | 调用入口 |
|--------|------|----------|----------|
| `@register_learner` | 把模型类注册到 LEARNER_REGISTRY | `workspace/__init__.py` | `Workspace.build_learner(cfg) → LEARNER_REGISTRY[cfg.MODEL_ARCH]` |
| `@register_objective` | 把 loss / 目标注册到 OBJECTIVE_REGISTRY | `workspace/__init__.py` | `Workspace.build_objective(cfg) → OBJECTIVE_REGISTRY[cfg.LOSS]` |
| `@register_augmentation` | 把数据增强注册到 AUGMENTATION_REGISTRY | `workspace/__init__.py` | `Workspace.build_transforms(cfg) → AUGMENTATION_REGISTRY[cfg.AUGMENTATION]` |
> **特例**：mammoth (`framework` object_type，**v1.22.0 起判为 `framework` 而非 `atomic_package`**；原 v1.16.5 前的 ADAPTER 场景承载)不在此表中——它的 CLI 适配器用 `@register_cli_adapter` 注册**翻译函数**(非模型类)进 `CLI_ADAPTER_REGISTRY`,命名独立以避免与 `@register_learner` 的类注册语义混淆。详见 `docs/examples/adapter-mammoth/workspace/__init__.py` docstring(原 `skeletons/mammoth/` 移至 `docs/examples/adapter-mammoth/`,原 ADAPTER 场景参考实例,v1.22.0 起改由 `framework` object_type 承载,**目录结构保留作 backward-compat 示例**)。

```python
# workspace/nn/my_model.py（模型类放 workspace/nn/ 或 workspace/models/）
from workspace import register_learner

@register_learner("SimpleCNN")  # 自动注册到 LEARNER_REGISTRY["SimpleCNN"]
class SimpleCNN:
    def __init__(self, cfg): ...

@register_learner("ResNet18")  # 再加一个不会破坏 train.py
class ResNet18:
    def __init__(self, cfg): ...
```

#### 1.3.2 cfg 键关联

注册后，模型/损失不再硬编码在 train.py，而是通过 cfg 字符串键查表：

| cfg 键 | 取值 | 运行时效果 | 适用范式 |
|--------|------|-----------|---------|
| `MODEL_ARCH` | `"SimpleCNN"` / `"ResNet18"` / 自定义类名 | `Workspace.build_learner()` 查表返回对应实例 | supervised/rl/physical |
| `LOSS` | `"CrossEntropy"` / `"LabelSmoothingCE"` / 自定义类名 | `Workspace.build_objective()` 查表返回对应实例 | supervised/rl |
| `OBJECTIVE` | `"ce"` / `"focal"` / `"dice"` 等（多分类 / 分割 / 检测不同）| 同上 | supervised/rl |
| `AUGMENTATION` | `"Cutout"` / `"MixUp"` / 自定义类名 | `Workspace.build_transforms()` 查表返回对应实例 | supervised |
| `OPTIMIZER`（v1.10.0 WP1 走 cfg 分派） | `"adam"` / `"adamw"` / `"sgd"` | `Workspace.build_optimizer(cfg)` 强读 cfg 分派（不走 registry，理由：算法集合稳定） | supervised/rl |
| `OPTIMIZER_SCHEME`（v1.10.0 WP1③ 走 β elif） | `"adam"` / `"lbfgs"` / `"adam_lbfgs"` | `Workspace.build_optimizer(cfg)` 强读 elif 分派（与 α 同形态，cfg key 不同；PINN 类分阶段流水线一锁锁死） | physical |

加新模型的标准流程：

```
1. 在 workspace/nn/ 下新增模型文件，写一个新类 + @register_learner("新类名")
2. cfg.json / config.json 里设 MODEL_ARCH="新类名"
3. train.py 不用改一行（查表自动拿新类）
```

#### 1.3.3 为什么这样设计

1. **pluggable 改码三原则的物质基础**：新加模型走装饰器 + cfg 键 = 不硬编码 → 改码三原则中「pluggable」不是文档约定，是代码层强制
2. **G-封装 防硬编码**：`train.py` 不能写 `from workspace.MLP import build_learner`（违反 G-封装，nn-doctor 会 FAIL），必须通过 `Workspace.build_learner(cfg)` 接口
3. **add 新能力不破坏现有**：加新模型不动 train.py / 不动 contract / 不动其它 workspace 模块 → fork-proof + 模块独立

权威细则见 `template/package/PROTOCOL.md §0.1`，注册 API 在 `workspace/__init__.py`。

### 1.4 build 不做什么

build 不负责长期调参，也不负责撞墙后的研究判断。它只负责让项目进入一个清楚、可执行、可审计的初始状态。

如果后续发现任务定义本身需要改变，应走重接入或明确重签，而不是在实验循环里静默修改。

### 1.5 运行时契约加固（v1.24.0 三层架构）

contract 的题面保护只防「静默改场景号」，但**指标单位**与**评估入口**仍散在 contract / run_ledger / goal_spec / train.py 四处，第三方接入（adapter/外部框架 CLI）走哪条路径不明。v1.24.0 把这块加固成三层架构：

| 层 | 位置 | 干什么 | 文件 |
|---|---|---|---|
| Layer 1 · helper | `lib/metric_units.py` | `UnitKind` 枚举 + `normalize_to` + `_safe_metric` + `METRIC_UNITS` 静态查表，统一指标单位 | `template/package/lib/metric_units.py` |
| Layer 2 · 契约加固 | `contract._safe_metric` property + `default_metrics` 骨架 + `goal_spec` 单位归一（`Predicate.metric_unit`）+ `_goal_met` 单一来源（from `run_ledger_summary`） | contract 自报「我用什么单位、不写时回什么」、goal_spec 不再每处独立 parse、单位全归一、单点判定达标 | `template/package/contract/__init__.py` + `contract/runtime.py` + `goal_spec.py` + `run_ledger_summary.py` |
| Layer 3 · train.py 分桶 | `workspace_kind` registry（`register_workspace_kind` / `get_workspace_kind`）+ `scripts/lib/train_branch.py` 调度器（`dispatch_test_call`）+ `contract.test.run(adapter_runner=...)` opt-in + `train.py:386` 双路径 | 第三方接入走 `kind="adapter"`（无 learner，adapter_runner 替它算指标）；自训走 `kind="supervised"`（backward-compat 默认） | `template/package/workspace/__init__.py` + `template/package/scripts/lib/train_branch.py` |

新关键字：**`workspace_kind` = `Literal["supervised", "adapter"]`**，supervised 是 backward-compat 默认（业务仓 zero knowledge 不动）。adapter 模式 contract.test 收 `learner=None` + `adapter_runner` callable，返回该 callable 的 metrics dict。

#### 1.5.1 dispatcher 三维正交（v1.33.0）

**原形态**：`workspace_kind` 单 enum（v1.24.0）把「评估形态 / framework 身份 / 训练机制」三维度压进一个值，导致 mammoth 仓需在 dispatcher 加 `mammoth_cl` 第 3 个字面（行为跟 `supervised` 一模一样，只为标身份）。

**新形态**：拆成三个正交 enum（`scripts/lib/train_branch_types.py`）：

- `MetricsShape`（评估形态）：`EVALUATE_LEARNER` / `EVALUATE_RUNNER` — 决定 `contract.test` 怎么被调（原 supervised / adapter）
- `TrainingMech`（训练机制）：`SUBPROCESS` / `IN_PROCESS` / `NATIVE` — 决定 train.py 怎么训 model（v1.33.0 声明 enum；**v1.43.0 接线 `dispatch_training`**，见 §1.5.2）
- `FrameworkKind`（framework 身份）：`MAMMOTH` / `LIGHTNING` / `HF_TRAINER` / `TIMM` / `AVALANCHE` / `UNKNOWN` — 由 `init_workflow.detect()` 推断（object_type=framework 时），workspace 显式声明

业务仓零改动即可享受：governance-sync 拉新版后，`mammoth_cl` 字面 → `MetricsShape.from_legacy("mammoth_cl")` → `EVALUATE_LEARNER`，加 `FrameworkKind.MAMMOTH` 推断；`WorkspaceKind = MetricsShape` alias 保 import 路径。**dispatcher 不再被业务仓魔改**。老字符串标 `DeprecationWarning`（v1.33.0 expand 阶段），v1.34.0 contract 阶段删 `from_legacy`，业务仓须先跑 `scripts/migrate_metrics_shape.py`。

#### 1.5.2 training_mech 训练侧 dispatch（v1.43.0）

三维里 metrics_shape 由评估侧 `dispatch_test_call`（训末调 `contract.test`）派发；**training_mech 由训练侧 `dispatch_training`（`scripts/lib/train_branch.py`，train.py 训练主循环入口）派发**。注入式接通——train.py 注入 `_run_native` / `_run_in_process` / `_run_subprocess`：`NATIVE` 走 native 闭包（默认实跑）；`IN_PROCESS` 调 `ws.framework_train`；`SUBPROCESS` 走 `run_subprocess_training`（命令 + JSON `best_metrics`）。缺钩子显式失败，禁止回退 NATIVE。真实 Lightning/mammoth 适配仍后续。来源优先级对称 metrics_shape：`register_workspace_kind(training_mech=…)` / `get_training_mech` registry + `nn-config.yaml` 的 `workspace.training_mech` opt-in 覆盖；dispatcher 边界做 str→enum 归一。维度 B（过程信息进台账）骨架未覆盖。

**v1.45.1 训后收尾与 mech 解耦**：`dispatch_training` 返回后，`finalize_training_loop_artifacts` 统一写 `train_done.json`（`stop_reason=mech_complete`）并调用 `apply_checkpoint_policy_to_learner`——三种 mech 共用；过程曲线 / `train_status.json` / 早停计数仍仅 NATIVE 循环内。避免非 NATIVE 缺训后完成信号与 checkpoint。

#### 1.5.3 framework 接入总表（v1.48.9）

三维 dispatcher 管 **怎么调度**；另有合同侧 **`contract/framework_binding.yaml`** 管 **框架五能力怎么接**（数据 / 训练 / 评估 / 训记 / 权重）。不进 `nn-config`。doctor/smoke 消费；`dispatch_*` **不读**总表分流。`eval` 节要求两段式（框架原样主分 → 键翻译 → `contract.test`）并对账，拦住 wrapper 自创公式。与 runner 出分门禁正交。详见 PROTOCOL §3.0.2b。

#### 1.5.4 信息权限登记表与交卷缝 + 立项三问 / 答案清单（子项目 A + B，待发版）

G-评估只保证「官方分必经 `contract.test`」，管不到**训练用了什么材料**、**官方分走的是整网还是受限路径**。合同侧新增字面量登记表 **`contract/runtime.py::INFO_PERM`**（训练可用材料 / 官方分路径 / 交卷开关 / 首 batch 键 / 严格档），阅卷骨架留 **`_official_forward` 交卷缝**（受限路径手续写在此，失败返回 None 不回退）。训前 **G-信息权限**（`scripts/lib/info_perm.py`）合同静态拦登记表非法 / 交卷缝未接 / 开关读 env；只评材料 **训练真打开或真调用** 才拦（工作区预留选项、默认不用不算犯规）——**无环境变量开关**，只认 `INFO_PERM["enforce"]`；对照实验两臂 = 两份合同（PINN：立项答卷拨「常见可试 data-loss」开/关，机械写入 `enforce`，**禁止克隆后改开关**）。训末 `finalize_run` 把 `NN_PREFLIGHT` / `NN_GUARD*=0` 写进 `config.json._repro.guards_bypassed`，非空不可 KEEP，`enforce` 下抛错不入账。README `<!-- INFO_PERM -->` 块由 `scripts/info_perm_gate.py` 对账（verify §6f / doctor §5、§14）。存量业务仓未登记 → 全部空转。**立项三问（子项目 B）**已接入 init：HARD-GATE 在 D2 之后插入 **信息权限** 三问 `I1-train-consumes`（训练许用材料）→ `I2-official-path`（官方打分通道）→ `I3-other-info-rules`（其他信息规矩），A 27 步 / B 24 步（qa-log 计数 28/25）；答案经 `scripts/init_info_perm.py write` 机械落进 `INFO_PERM` + README 块，`info_perm_gate.py` 对账。同时新增 **答案清单** 第 4 种触发（`/auto-nn-init … --answers 文件`）：机器可读题库 `docs/init/init-question-registry.yaml` + 校验器 `scripts/init_answers.py`。文件可以是标准 YAML，也可以是 md/txt 草稿（Agent 填表后再校验；猜的题仍问）。有合法答案的题不弹卡片但题序、逐题记录、口径汇总签字不变；v1 仅 8 题可跳（信息权限三问 / 实验模式 / 目标值 / 墙钟 / GPU / 种子），迁入源对齐题须改回确认。签完从问答记录 **export** 出 `.auto-nn/init-answers.yaml` 供下次复用。沙箱 `sandbox-init --answers` 同样收 YAML 或草稿。

---

## 2. governance：围栏式阶段

governance 的任务是让实验在边界内运行。它不直接追求最高分，而是保证每一次分数和每一次修改都有稳定语境。

### 2.1 五类边界

| 边界 | 防什么 | 主要机制 |
|---|---|---|
| 任务边界 | 指标、数据、场景、KEEP 口径漂移 | 研究合同、场景规则、目标规则 |
| 行动边界 | Agent 在错误层级做副作用 | 技能分层、改码规则、人工路线图 |
| 证据边界 | 声称试过但没有证据 | 结果记录、运行记录、TAM、反思索引 |
| 状态边界 | 模板、配置、运行态和长期记忆腐化 | update、doctor、clear、compress |
| 资源边界 | Agent 会话内自改训练墙钟（env 通道自延时限）；长 `train_step` 绕过轮次边界看表 | `time_budget` Config-Only 冻结（PROTOCOL §2.3）；训内满预算、在轮次边界与 `optimizer.step` 入口停并入账（PROTOCOL §7.3） |

这里的“边界”不是文档约定，而是尽量变成机器可检查的规则。文档负责说明意图，代码负责执行检查。

### 2.2 技能不是命令菜单

技能体系的本质是副作用分层。不同技能可以做的事情不同。

| 技能组 | 技能 | 主要副作用 |
|---|---|---|
| 接入类 | `init` | 建立项目结构和研究合同 |
| 边界类 | `goal` / `human-guidance` / `modify` | 改目标、路线图或能力边界 |
| 体检类 | `doctor` / `update` | 检查或同步治理状态 |
| 清理类 | `clear` / `compress` | 维护运行态和长期记忆 |
| 实验类 | `auto-run` / `manual-run` | 运行实验并写入结果 |
| 认知类 | `analyse` / `reflect` / `check` | 读取结果、分析趋势、生成下一步假设 |

这个分层有两个好处：

1. Agent 不会在“分析趋势”时顺手改训练代码。
2. Agent 不会在“跑实验”时顺手改评价口径。

### 2.3 governance 与 experiment 的边界

有些机制会被 experiment 使用，但主体仍属于 governance。例如：

- 目标值属于 governance，因为它定义何时停止。
- 人类路线图属于 governance，因为它定义优先级和禁区。
- doctor 属于 governance，因为它判断系统结构是否健康。
- clear 属于 governance，因为它清理运行态，不产生研究假设。

这些内容会影响 experiment，但不应放进 experiment 主体里讲。

### 2.4 外部证据反馈环 (v1.30 起)

| 维度 | 含义 | 落地点 |
|------|------|--------|
| PDF 全文可见 | `paper.method_excerpt` 注入 synthesis prompt | `synthesis.build_synthesis_prompt` A1 |
| Docs 符号自动推断 | `_run_docs` 入口从 rationale 拉 nn.CrossEntropyLoss 等 | `executor._run_docs` C1 |
| Key 即时感知 | 启动 banner 4 个 key 配齐状态 | `auto-nn-run.sh` + `check-external-keys.py` D2 |

**v1.31 增量** (A2+B2+D1):

| 维度 | 含义 | 落地点 |
|------|------|--------|
| 骨架队列 | `skeleton_queue.json` 落盘 + release-check 第 6.5 步 lint | `executor` 写盘 + `check_skeleton_queue_health.sh` A2 |
| Query 改写 | `_run_github_ecosystem` 调 `rewrite_for_awesome` 多路查询去重 | `lib.external.query_refiner` B2 |
| 健康度落盘 | 每轮 `external_evidence_health.json` 报告 green/yellow/red | `lib.external.evidence_health` D1 |

**v1.32 增量** (B1):

| 维度 | 含义 | 落地点 |
|------|------|--------|
| seed_repos 前馈 | `seed_repos.json` 通用 framework/task → GitHub repo 映射，`_run_github_code` 注入 candidates 兜底 | `scripts/data/seed_repos.json` + `executor._seed_repos_lookup` B1 |

**设计要点：**

- **universal、不绑业务**：JSON 仅列常见框架（pytorch/vision/timm/transformers/lightning/monai 等）和任务主题（image-classification/detection/segmentation/nlp/rl/pinn 等），不含任何 mammoth/fashionmnist/cifar 等具体数据集。
- **三路文本命中**：`fingerprint.MODEL_ARCH` + `fingerprint.task_domain` + `rationale` 合并 lowercased，token 命中即累计 full_name。
- **顺序 + 去重 + 5 项封顶**：frameworks 先于 task_themes（稳定命中序），full_name 全局 set 去重，最多 5 项（cap 内置，JSON 可列更多）。
- **容错**：JSON 缺失/解析失败/非 dict fingerprint → 返回 `[]`，不抛。
- **不覆盖原候选**：seed_repos 命中的 full_name 仅在原 `impl_candidates` 不存在时追加尾部，标 `source=seed_repos`，原 arxiv/scholar 命中优先。

---

## 3. experiment：进化式阶段

experiment 的任务是在治理围栏内持续改进项目。它包含两条循环：

| 循环 | 回答的问题 | 主要动作 |
|---|---|---|
| 执行循环 | 本轮结果是否更好 | 提候选、改代码、训练、评估、KEEP/DISCARD |
| 认知循环 | 下一轮应该为什么这样做 | 分析历史、归因失败、检查覆盖、生成下一步假设 |

执行循环产生结果，认知循环产生方向。两者不能混成一个自然语言总结。

### 3.1 单轮实验

单轮实验的最小闭环是：

```text
读取路线图和历史
  → 选择一个候选改动
  → 在 workspace 内实现
  → 使用 contract 评估
  → 判定 KEEP 或 DISCARD
  → 写入结果和经验
```

关键原则是 **OVAT（One Variable At a Time，单变量实验）**：一次实验尽量只证明一个改动的效果。并行实验也应理解为多个独立单变量候选同时运行，而不是把多个因素混成一个大改动。

### 3.2 多轮实验

多轮实验由 auto-run 编排。它负责：

- 每轮提供当前状态摘要。
- 注入人类路线图和反思建议。
- 运行候选实验。
- 记录结果。
- 在撞墙或周期条件满足时触发反思。
- 在达标时停止。

auto-run 负责节奏，不负责替代 contract。多轮运行不能静默改变主指标、测试集、场景或 KEEP 规则。

**auto-run 与 manual-run 的关系**：两者共享上文 §3.1 的单轮内核（改 config → train → KEEP/DISCARD → 写 EXPERIENCE → commit 台账）。区别只在编排层——auto-run 的 `auto-nn-run.sh` 在每轮**开头**注入上下文（Run Context 状态摘要、场景 manifest、路线图、反思 pending、创新维切片），在**结尾**追加无人值守守护（轮末 round-doctor、goal 达标即停、reflect 门禁、EXPERIENCE 自动压缩、HUMAN 路线图漂移恢复）。这些守护只因 batch 无人值守才需要；manual-run 人在场，等价检查前移到开训前（goal / HUMAN gate）或推给 `/auto-nn-analyse`（含 doctor diff）。两者都不建设新能力（注册变体 / 扩场景 / 动 contract → `/auto-nn-modify` + `NN_RELAUNCH=1`）；改 `train.py`/`workspace/` 迭代代码守改码三原则（PROTOCOL §0.1）。

**输入加载策略：决策键热重载 vs 路线图门禁冻结。** auto-run 每轮起的 claude 子进程消费两类外部输入，加载策略**故意相反**，是 batch 无人值守的核心设计取舍：

- **决策类（nn-config 的 `keep.*` / `goal.*` / `exploration_mode` / `agent` 注入开关）→ 每轮子进程现读 = 热重载**。判定真源每次重读：KEEP 走 `experiment.py` `_effective_keep_spec()` → `_load_nn_config()` 薄 shim → **`lib.nn_config.load_nn_config`（ADR-12 统一加载 seam；坏 yaml → `RuntimeError`，no-fallback）**（不从 contract 死值读——注释明说"keep 阈值是探索策略的函数，不该跟场景号钉死"）；goal 走 `check_goal.py` 每轮跑；exploration_mode 走 `effective_objective()` 每轮 spawn。中途改这些，**下一轮判定立刻按新值**——鼓励探索途中动态调探索参数。注：编排 shell（`auto-nn-run.sh` `_nn_cfg_load_static` 批次启动缓存 15 键到 `CFG_*`）只用于显示行 / poll 间隔 / 硬件 / 场景段，**不是真判定**（file:line 证据 `auto-nn-run.sh:1175` 缓存 vs `experiment.py` 每次经 shim 现读）。
- **路线图类（`HUMAN_GUIDANCE.md`）→ 门禁冻结**。批次启动拍 sha256 基线（`_write_human_guidance_baseline`，`auto-nn-run.sh:1156`），每轮 `_check_human_guidance_gate`（`:1430`）对比；中途改了 → 下一轮**跳过 agent**（`agent.human_guidance_gate_fail_fast=true` 则直接终止 batch），收尾还有 G-HUMAN-COMMIT 复检（`:1658`）兜底轮内 HG 偏离基线。技术上 prompt 每轮也现读 HG 文件（`_inject_guidance_reflect_prompt` `:1451`），但门禁保证当前文件 ≡ 批次基线、变了就被拦——等效批次冻结。

**为什么相反（用意）**：不是"怕 agent 恶意偷改"——HG 不参与 metric 计算，agent 刷分的直接动机指向主指标 / 测试集，改 HG 不直接提分（且 agent 写 HG 会被 G-HUMAN preflight 直接拦截、prompt 明令禁编辑，动机与通道都弱）。真正的首要目的是**批次不变量保护**：HG 是人类指挥意图，须锁定为整批的不变量，与本节上文"多轮不能静默改主指标 / 测试集 / 场景 / KEEP 规则"同源——一旦 batch 内 HG 变了，前 N 轮和后 M 轮跑在不同指挥意图下，KEEP 比较与归因即不 fair。次要才是兜底任何来源的意外变动（agent 有写权限手滑、人中途动摇、`git checkout` 串版本）。

**改 HG 的合规路径（唯一）**：停 `./auto-nn-run.sh` → 用 `/auto-nn-human-guidance`（**非实验执行轮**操作：agent 只 dry-run、`--apply` 由人本地执行）编辑并 `git commit` → 重开 batch（重排 baseline）。`human_guidance_gate.py refresh` 命令虽存在，但 **batch 活跃时被运行时拒绝**（`lib/human_guidance_gate.py:318/354/378` + `refresh-human-guidance-baseline.sh` REFUSE），PROTOCOL §7.5.3 明令"勿再采纳 batch 内 refresh baseline 继续跑"。即"决策键欢迎中途改、路线图严禁中途动"——可变的探索参数走热重载，不可变的指挥意图变了就要重开一批。规则真源见 PROTOCOL §7.5.3（HUMAN 硬门禁 G-strict）。

### 3.3 动作空间

auto-nn 用二维动作空间描述“这一轮到底改了什么”。**两张脸不要合成一张**：

| | 思维手册 `references/manual/abcde-manual.md` | 成绩表 `exploration_space`（运行时格子） |
|--|--|--|
| 形状 | 仍 **5×3 = 15 格**（A–E × routine/derived/different） | **仅 A–D** × 深度（训末最高 different；novel 仅反思盖章） |
| 谁写 | init 生成；反思只许改原则错误 | `finalize_round` 入账前必打；反思只许 different→novel |
| E | 说明书：题面锁定、人审开闸 | **不进格子**。主张走改题待办 `_runs/analysis/e_feedback.jsonl` |

手册 15 格是探索的全部落点说明；正式训完行墙上钉的是 A–D 一格，不是 E。

第一维是改动层级：

| 层级 | 含义 | 例子 |
|---|---|---|
| A | 标量与训练日程 | 学习率、batch size、epoch、scheduler、optimizer（adam/adamw/sgd）；physical 加 **OPTIMIZER_SCHEME**（β 命名 scheme：adam / lbfgs / adam_lbfgs——PINN 典型 Adam→LBFGS 分阶段流水线，scheme 名整体可被治理层锁，WP3 已接入） |
| B | 模型表示 | backbone、head、block、adapter |
| C | 目标与监督信号 | loss、regularizer、distillation、reward |
| D | 数据与采样 | augmentation、sampler、curriculum、replay |
| E | 任务与评估定义（**仅手册行**；运行时不占 `exploration_space`） | 主指标、测试协议、场景、KEEP 规则 → 改题待办 + 人决议 |

第二维是探索深度（RDDN 四档 routine/derived/different/novel，替原 REN 三档 routine/extend/novel；决策见 `说明`）：

| 深度 | 偏离已知 | 含义 | 谁判 |
|---|---|---|---|
| routine | 0 | 已有代码原样、catalog baseline 命中 | fingerprint 确定性 |
| derived | 小 | 有可识别祖先（catalog drop_in / 库标准件 / 已有件）或纯 routine 重排 | fingerprint 确定性 |
| different | 大 | 零祖先（catalog 零命中、手搓）——形式化创新的默认天花板 | fingerprint 确定性 |
| novel | 确证真新 | different + 文献正面支持 | LLM 判 + P3+ 全文 |

> **菜单 3 列 ≠ 判定 4 档（ADR-5）**：探索菜单（manual）只留 routine/derived/different 三列（**15 格不变**，原 extend→derived、原 novel→different 仅 rename）；novel 是事后 attestation 才盖的章、agent 事前瞄不准 → 不进事前菜单，纯下游 fingerprint/router 标签涌现（`router._DEPTH_MATRIX` 5×4=20 是判定基数，与菜单 15 格不同物）。
> **novel 弱验证语义（ADR-2）**：different→novel 只走 `attestation=supported`（LLM 读 P3+ 全文判，非旧 docs_hits 糙判）；inconclusive/skipped 留 different，**不升也不卡**。受 P4 约束（全文仅 arxiv 有、默认 P2 只摘要）novel 在普通档几乎不出、P3+ 才有真机会——稀少是约束必然。
> **评估 / 寻找双胞胎（ADR-3/6）**：同一套检索管道（router + arxiv/scholar/github/pdf/local-docs）数据流反向——**评估**（事后）抓说谎、定档（强半 fingerprint 戳穿 routine/derived 谎、确定性常开；弱半 different→novel attestation）；**寻找**（事前）撞墙 reflect 周期内捞可试候选件（trigger = plateau ∧ depth∈{different,novel}、P3+ 全文）。评估发现"different 其实是已知"→降档 derived + 喂 catalog → 养大寻找菜单。

E 层级很特殊。A–D 是“在题内改解法”，E 是“改题”。常规自动实验不能静默进入 E；主张在反思时**只记进改题待办，不等待人答、不打断自动跑**。人稍后点名分析或手跑反思时才看记录、问留下 / 搁置 / 驳回；**无论哪项只更新记录、不改实验**。留下只给人建议；驳回后不得再提类似主张；搁置当没发生，下次该提还提。若人自己要改题，另开会话开闸，不由三选一代劳。**A–D 之间没有硬性顺序**（不强制 A→B→C→D→E）：任意选档、B/C/D 可组合多槽并行（OVAT 每槽单变量），只有 E 锁在手册、不进成绩表格子——手册是 15 格棋盘，运行时墙上钉的是 A–D，不是 5 级阶梯。

#### 3.3.1 α / β 范式分派（v1.10.0 WP1）

A 档 optimizer 走两种范式分派，由 `cfg` 键决定走哪条路：

| 范式 | cfg 键 | 分派机制 | 适用 | 治理可锁性 |
|------|--------|----------|------|-----------|
| **α atomic** | `cfg["OPTIMIZER"]` | 强读 cfg 分派（`adam` / `adamw` / `sgd`），`_NullScheduler` 具名 no-op，**不走 registry** | supervised / rl | 单算法锁（`OPTIMIZER.HARD=adam`），算法集合稳定 |
| **β named scheme** | `cfg["OPTIMIZER_SCHEME"]` | 强读 cfg elif 分派（与 α 同形态，cfg key=OPTIMIZER_SCHEME；`adam` / `lbfgs` / `adam_lbfgs`），第 1 阶段返回 Adam 优化器 + STAGES 标记，**阶段切换由 `train_step` 管（WP3 边界保留）** | physical（PINN 类分阶段流水线） | **scheme 名整体可被锁**（`OPTIMIZER_SCHEME.HARD=adam_lbfgs`，一锁锁死流水线——拆流水线即撞该 contract 级 HARD 锁） |

为什么 physical 走 β 不走 α：PINN 类分阶段训练天然 staged（Adam 粗训 → LBFGS 精调），“先 Adam 后 LBFGS” 是一类业务语义，不只是算法选择；用 named scheme 把“流水线整体”作为治理对象，避免 Agent 拆流水线的尝试。supervised/rl 算法集合稳定，atomic 足够。

#### 3.3.2 6 mode 运行策略：深度天花板

15 格探索空间定义“能改什么”，**6 个 unified mode** 定义运行期“允许改到多深”。mode 来自 `scripts/lib/presets.py` 的 `_MODE_DEFAULTS`（careful / optimize / innovate / aggressive / explore / auto 等 6 档），每个 mode 钉一个**深度天花板**（ADR-7：`paper_depth` 梯子显式解读为深度天花板——P0 routine / P1 derived / P2 different / P3 = different + novel-可证）与 KEEP 阈值。mode↔depth 解耦（depth 仍 agent 每轮声明 + `innovation_audit` 审计，模式不直接选列）：careful→routine / optimize→derived / innovate→different / aggressive→different+novel-可证（**唯一**能经 attestation 触及 novel 的模式）/ explore→different / auto→derived 起步。

| 维度 | 说明 |
|---|---|
| mode 何时定 | init 期定死，写入 `nn-config.yaml`；运行期不动 |
| mode 决定什么 | 探索深度天花板 + KEEP 阈值（aggressive 0.001 / careful 0.01） |
| mode 不决定什么 | 不改动作空间（15 格不变）、不改 contract |

> **自动升档（auto promotion）**：撞墙后沿 mode 升档链（`PROMOTE_CHAIN`：optimize→innovate→aggressive）自动提档。**1.15.0 已全接线**——信号侧（每轮写 `auto.wall_hit_streak`）+ 执行侧（`experiment.py:3827` 轮末调 `check_and_promote_auto`）都活，双 `is_auto_mode` 守卫确保仅 `mode: auto` 时触发、显式档不动；撞墙 `promote_threshold`（默认 5）轮自动升一档并写 next_mode preset。另有 **Tier 轴**升档（reflect 门禁 + EXPERIENCE Tier 矩阵 + TAM 穷尽跳层）独立运作。详见探索空间 §3-§4/§6。

### 3.4 ABCDE guidance：从防御到指导

动作空间回答“能改什么”，但 Agent 真正缺的是“撞墙后该往哪改”。ABCDE 框架的设计本意因此是双层：

| 层 | 回答 | 机制 |
|---|---|---|
| **防御层** | 别乱改（守住 E、不静默改题） | 动作空间 §3.3 + E 闸门 + TAM §3.5 |
| **指导层** | 撞墙后知道试什么 | references/manual/abcde-manual.md（5×3 思维框架唯一活载体）+ 每轮切片注入 + TAM exhausted→强跳 |

指导层的物质基础在 init 阶段一次性生成（`scripts/init_o3_abcde.py` 的 `write_init_outputs()`，framework 信号走内存入参，v1.16.0 起不再落 yaml）：

- ~~`.auto-nn/abcde-guidance.yaml`~~（v1.16.0 整体删除）：原 **5 层探索契约**（`capability_surface` 能力面 / `guidance_matrix` 指导矩阵 / `joint_constraints` 联合约束 / `tam_contract` / `rescue_ladder` 救援阶梯）于 2026-07-11 enforcement 退役后只剩 framework 元信息空壳，运行期零消费者，v1.16.0 连空壳一并删。撞墙指导职责由 `references/manual/abcde-manual.md` + `render_tier_slice` 切片 + TAM exhausted→强跳 承接。
- 题面保护：`enforcement` + `modifier_seeds` 块已于 2026-07-11 退役（结构性冗余），v1.16.0 连 `abcde-guidance.yaml` 空壳 + nn-doctor 内联 `check_ABCDE_boundaries`（WARN-only 死代码）一并删除。题面保护纯靠 `contract/` IMMUTABLE 门禁（`Contract(ExperimentBase)` 锁 E 档 metric/keep + `auto-nn-run.sh:1289` 标 IMMUTABLE）。`abcde_migrate.py` 保留——老业务仓补写 `references/manual/abcde-manual.md` 的薄壳（委托 `write_init_outputs`），skip-check 现仅判 manual。旧的 `.auto-nn/abcde-boundaries.yaml` 及其 producer（`default_boundaries()` / `init_abcde.py` / `BoundariesSpec`）已于 P4（2026-07-10）物理删除。
- `references/manual/abcde-manual.md`：人/Agent 可读的思维框架，5×3 表（ABCDE × routine/derived/different）× **3 workflow（v1.22.0 起替代原 4 场景）** + object-type header（3 object_type：`code` / `framework` / `data`，v1.22.0 收口 5→3；对象类型决定每格"改什么/路径上限"，由 §1.1 对齐环节判定）。**init 后静态，但 reflect 遇原则错误可直接改 cell**（HTML 留痕 `<!-- reflect-fix Rn date: ... >`）。动态行为靠每轮切片。**存在性是完成门禁（v1.48.16）**：`new-project` 缺文件 → 立项 exit ≠ 0；`verify-migration-complete` / doctor `abcde_manual` 缺 → FAIL（非「事后手动即可算立项成功」）。缺文件时训环 inject 仍软降级为空串，靠门红逼补、不硬崩训练。

每轮 experiment 由 `auto-nn-run.sh` 的 `_inject_innovation_prompt()` 用 `render_tier_slice` 读 EXPERIENCE.md 的 Tier 状态 matrix → 找最高 rank cell（letter, depth）→ 切 `references/manual/abcde-manual.md` 对应 cell 注入。Segment A（enforcement 摘要）已删；guidance.yaml v1.16.0 起整体删除，注入与 yaml 零耦合。Agent 把切出的 cell 内容当**操作约束**（不能越的界）+ **方向指引**（撞墙后往哪试），不是自由发挥。

撞墙救援：当某层 TAM 进入 `exhausted`，指导层合成”建议下轮跳下一层”（B 穷尽→跳 C），并配 HUMAN_GUIDANCE 路线图导航——这曾由 `abcde-guidance.yaml` 的第 5 层 `rescue_ladder` 承载（2026-07-11 enforcement 退役时删，活逻辑现落 `run_ledger_summary.py` 的 `plateau_streak` + `tier_exhaust_keywords`，v1.16.0 连 guidance.yaml 空壳一并删）。机制已随 P0 落地（1.7.0），但实证仍待验证：71 轮旧数据显示防御层已达标（E 闸门 0 触发）、指导层常缺失（撞墙后无 in-experiment 救援）；`rescue_ladder` 是否真能补上这一环，需新一轮跑数据。

**runtime fork 触发通道（register 上限对象的运行期升级机制）**：除 mode 轴 auto-promotion（optimize→innovate→aggressive，探索空间 §4）与 Tier 轴 TAM 救援（跳下一层）外，还有 cell 级路径上限升级通道——register-ceiling 对象（**v1.22.0 起 = `framework` object_type**，原 `atomic_package`/`complex_framework` 收口）的 different/derived cell 若需改源码且 register/adapter/monkey-patch/slim 等轻量手段确实无法表达 → experiment agent 写 `_runs/exp/<run_dir>/source_block.json` sidecar → reflect 核实轻量手段确实穷尽（独立证据质量门禁）→ reflect 写 `[升级建议] register→fork` 到 `references/REFLECT_INDEX.md` → 下轮 agent 编辑该 cell 路径从 `register` 改为 `fork`（cell 级、单向、单维度；不可降档，不影响其他 cell）。`HUMAN_GUIDANCE.md` 可 cell 级覆盖 manual 路径上限（最高优先级）。

### 3.5 TAM：动作证据状态

TAM（Tier Attestation Matrix，层级举证矩阵）负责回答：

> 系统声称试过某类动作，这个说法有没有证据？

TAM 不判断科学解释一定正确，只判断证据是否支撑声明。

| 状态 | 含义 |
|---|---|
| not_attested | 没有足够证据 |
| shallow | 有尝试，但覆盖很浅 |
| attested | 有较明确证据 |
| exhausted | 当前条件下形成较充分负证据 |
| false_claim | 声称与证据不一致 |

**与运行时格子分家**：成绩表 `exploration_space` 在 `finalize_round` 入账前当场写入（A–D 必打；未开训可空）；**不**等反思补账。战役 TAM 窗口仍比**当前最好（keeper）**做升档/穷尽举证，与本轮格子（相对上一有效训行）分存、勿混。改题不占格子，进 `_runs/analysis/e_feedback.jsonl`。

TAM 的主体属于 experiment，因为它直接影响下一轮怎么选候选。但 TAM 依赖 governance 提供的证据边界。

### 3.6 PDH：朴素基线锚定

PDH（Plain-Discovery Heuristic，朴素发现启发式）规定：正式实验前先跑一个**朴素 plain baseline** 作为锚，后续所有 fancy 改动都对照它。它解决“第一轮凭什么说变好”——没有 plain 锚，分数提升无法归因。

PDH 六原则（`PROTOCOL.md §4.4`）：

| 原则 | 含义 |
|---|---|
| P1 弱于 random | plain 略胜随机即可，不与 fancy 争辉 |
| P2 朴素经济 | plain 几分钟跑完，不是几小时 |
| P3 领域 worst sane baseline | 选该领域最朴素但合理的基线 |
| P4 一眼看可解释 | <100 超参，可一眼读懂 |
| P5 plain_why 必写 | 必须记录为何选这个 plain |
| P6 预算感知 | plain_budget 必填 |

落地：init **O3-baseline-anchors** 仍可问「要不要立尺子、对照方法是什么」→ 落盘 `saved/baseline_start_intent.json`（测条件不对齐禁止抄论文分当上界）。**运行时写入权**：auto-run 先检索台账是否已有 `baseline_tag=plain`——有则不再立；无则可补至多 1 轮。公开对照走 `/auto-nn-reference`；前 10 轮 auto 不催，满 10 轮仍无则必做（中点代用可自动贴；文献尺须本机原仓校准过线才可贴）。`--from-template` 默认把标签清成 `none`。

plain 是**下界**锚；对应的上界是 **reference**——外部已发表的公开最优。三态命名铁律：plain = 自跑朴素基线（下界）/ reference = 外部已发表公开最优（上界，代码 `reference_anchor`，**不**叫 sota）/ none = 默认普通轮；仓内历史最佳才叫 SOTA。novel（研究性自创）任务常无现成 reference，留空即常态。每轮注入的 Run Context 含一个**基线靶子（baseline anchors）**稳定段（公告栏，三行：plain 下界 / reference 上界 / 当前最佳 + 差值，正差值=已超 plain），供 Agent 对照——定义见 `PROTOCOL §7.4`。`baseline_tag` 是稀有立尺贴纸，不是实验族分类。

### 3.7 reflect 与 synthesis

reflect 不是“写总结”。它的作用是把历史实验转成下一轮受约束假设。

reflect 的输入包括：

- 结果历史。
- 当前最好结果。
- 最近失败或平台期。
- TAM 状态。
- 人类路线图。
- 已验证外部证据。
- 训练过程的 loss 动力学（anomaly / train-loss 趋势 / train-val gap / plateau / stop 原因；读各实验目录的 `train_dynamics.json`）。

reflect 的输出应该满足三类约束：

| 约束 | 作用 |
|---|---|
| 动作约束 | 优先选择未覆盖或浅覆盖的动作空间 |
| 证据约束 | 外部引用必须来自已验证证据 |
| 适配约束 | 外部方法不能照搬，必须说明如何适配当前任务 |

synthesis 是 reflect 中最关键的认知步骤。它把“试过什么、失败说明什么、外部证据支持什么”合成下一轮候选。  
因此，auto-nn 的核心不是让 Agent 自由想点子，而是让 Agent 在证据约束下生成下一步。

### 3.8 analyse、check、compress、audit 的位置

这四个技能都支持 experiment，但权重不同：

| 技能 | 位置 | 作用 |
|---|---|---|
| check | 辅助读取 | 查看结果记录；默认先报参照（当前最好/尺子/场景/目标/关注场景），不做策略判断 |
| analyse | 状态分析 | 看趋势、平台期、目标进度和下一步建议 |
| compress | 长期维护 | 压缩长期经验，保留可用记忆 |
| audit | 出口/中途审查 | 对人指定对象（默认当前最好）做复现、多种子、novel 判定与归因消融；**不进成绩表**；卡片挂活指针，之后反思可读。规格 `20260821_1830_spec_auto-nn-audit.md` |

compress 会服务自动运行和人工调用，但它不是研究主线。它的价值是避免长期运行时记忆膨胀、重复和噪声污染。

audit **不是**搜索轮：不走 `finalize_round` 入账，不改当前最好，不写反思待消费建议。搜索期 `reflect` 仍只为下一轮想招；审查判定 novel 时强制深文献（P3），不改项目实验模式。

### 3.9 外部证据用量诊断 (v1.31 起,doctor 子检查)

`nn-doctor §X` 新增 `external_evidence_health` 子检查,读 `saved/external_evidence_health.json`,
按 verdict 分级:`real_external` / `partial` (HTTP 打了且有命中,但 method_excerpt 缺) → PASS;
`empty` / `fake_active` → WARN (round ≥ 3 时);`disabled` → SKIP。

---

## 4. 三阶段中的共享概念

有些概念会跨阶段出现，但本文只在一个主体阶段展开，避免重复。

| 概念 | 主体放在哪里 | 其他阶段怎么用 |
|---|---|---|
| 研究合同 | build | governance 检查它，experiment 遵守它 |
| 技能副作用 | governance | build 和 experiment 通过技能入口执行 |
| 动作空间 | experiment | build 初始化边界，governance 防止越界 |
| ABCDE guidance（manual） | experiment | build 生成 references/manual/abcde-manual.md（5×3 思维框架活载体；abcde-guidance.yaml v1.16.0 已删），governance 路线图导航 |
| TAM | experiment | governance 提供证据边界 |
| 人类路线图 | governance | experiment 读取并执行 |
| 目标值 | governance | experiment 用它判断是否停止 |
| 长期记忆 | experiment | governance 维护健康状态 |

原则：一个概念只在最主要的阶段讲完整，其他阶段只说明依赖关系。

---

## 5. 17 个技能的当前定位

| 技能 | 阶段 | 一句话定位 |
|---|---|---|
| `init` | build | 接入或重接入项目，建立研究合同和初始边界 |
| `goal` | governance | 设置目标值、停止策略和实验模式 |
| `human-guidance` | governance | 维护人类路线图、禁区和阶段意图 |
| `modify` | governance | 扩展 contract 或 workspace 能力 |
| `doctor` | governance | 体检结构、合同、证据和运行条件 |
| `update` | governance | 同步模板和治理能力 |
| `clear` | governance | 清理运行态（计划+确认后可由 Agent 代删） |
| `auto-run` | experiment | 编排多轮自动实验 |
| `manual-run` | experiment | 执行人工控制的单轮实验 |
| `analyse` | experiment | 只读分析趋势、平台期和下一步方向 |
| `reflect` | experiment | 生成受证据约束的下一步假设 |
| `check` | experiment | 只读查看结果记录（默认先报参照再出表） |
| `compress` | experiment | 维护长期经验摘要 |
| `setup` | env | 换机/重装环境拉起（torch 源映射 / 依赖安装 / 有 `~/.gpus` 时按 ∩ 本机写项目名单，没建则跳过 / smoke 验收），独立于 `governance→verify→doctor→smoke` 迁移验收链 |
| `audit` | experiment | 审查当前最好（或公开对照）：复现、多种子、novel 判定、归因消融；审对照则跳过新不新；不进成绩表。规格 `20260821_1830_spec_auto-nn-audit.md` |
| `plain` | experiment | 立朴素下界（契约内最容易的方法）。规格 `20260822_0030_spec_auto-nn-plain-reference.md` |
| `reference` | experiment | 立公开对照（先反思找；找不到中点挑；有原仓须本机校准，对不上禁止贴文献尺；满 10 轮 auto 必做） |

这个表是技能体系的主入口。更细的命令参数不放在本总览里。

### 5.1 技能之间的边界

modify 改的是**能力本身**（人入口：题面/metric/场景/KEEP 口径；亦可主动改 workspace/train；走代码 + track-catalog + post-change；改完须 nn-doctor 0 FAIL + 必要时 `NN_RELAUNCH=1`）。它不跑实验。实验 Agent **不**调用该技能。

实验轮（manual-run / auto-run）改**实验参数**写 `config.json`；改 `train.py`/`workspace/` 守 PROTOCOL §0.1，**可在单轮内直接执行**。人改题面/metric/场景/KEEP 口径（常需 `NN_RELAUNCH=1`）走 `/auto-nn-modify` + 改后链。人亦可主动用 Modify 改 workspace；实验 Agent 不调用该技能。

auto-run 是 manual-run 的 shell 编排包装：**单轮内核与 manual-run 一致**（§3.1），只在每轮开头注入上下文、结尾追加无人值守守护（doctor / goal 停 / reflect 门禁 / EXPERIENCE 压缩 / HUMAN 守护），同样不改能力。详见 §3.2。

- **改参数（LR / seed / scenario_id / 超参）** → manual-run / auto-run 直接写 `config.json`。
- **改 `train.py`/`workspace/` 迭代代码** → 守改码三原则（PROTOCOL §0.1）；单轮内直接执行，auto-run 每轮自改 + round-doctor。
- **改题面/metric/场景/KEEP 口径 / 动 contract** → 人走 `/auto-nn-modify` + 必要时 `NN_RELAUNCH=1`，再回 manual-run / auto-run 验证。
- **对当前最好或公开对照做复现 / 多种子 / 归因消融** → `/auto-nn-audit`（审对照跳过新不新，不入成绩表）。立尺 → `/auto-nn-plain` / `/auto-nn-reference`。结构体检 → doctor；下一轮该试什么 → reflect / analyse。

**入口拦截**（v1.28.0 起；IMMUTABLE 硬锁见后续版本）：`auto-nn-manual-run` SKILL.md 启动段对**人在对话里**提改能力（metric/场景/contract 等）做意图判别 → 推荐人开 `/auto-nn-modify`；**实验轮**改 `train.py`/`workspace/` 不在此路由。nn-doctor §8：`immutable_path_guard` 对 `experiment.py` / `contract/**` / 治理文档（无 `NN_RELAUNCH`）记 **FAIL** 并 exit 1；`manual_run_scope_check` 对 workspace/train 等仅 emit **workspace-edit WARN**（exit 1，不阻断、不推 modify）。训前 preflight 对 IMMUTABLE 破坏路径同步 `raise`。详见 PROTOCOL §3.0.1 与 `docs/nn-modify/track-catalog.md`。

### 5.2 改码三原则的 doctor 覆盖

`/auto-nn-modify` 走代码改动，须遵守 PROTOCOL §0.1 的「config-only / no-fallback / pluggable」三原则。doctor 对其扫描覆盖如下：

| 原则 | doctor 是否扫 | 子检查 | 严重度 |
|---|---|---|---|
| **config-only** | ✅ 全扫 | `G-cfg-no-defaults`、`G-repro-env`、`G-repro-cli` | FAIL（轻量 + 深度档均强检） |
| **no-fallback** | ✅ 全扫 | `G-no-fallback`（`scan_no_fallback.py`） | doctor 档 FAIL / 训前 preflight WARN |
| **pluggable** | ❌ 不扫 | — | 装饰器 `@register_learner` / `@register_objective` + cfg 键 `MODEL_ARCH` / `LOSS` 在代码层自证 |

例外豁免：标 `# optional:` 的 `try/except`（同行或上一行）会被 `G-no-fallback` 豁免。

为何「pluggable」不扫：分派形态（α ifelse / β elif / B/C/D registry）是代码结构约束，静态扫描代价高且易误报；改码时由 Agent + 人按既有形态贯彻，违反即污染代码须回滚。

---

## 6. 代码阅读入口

本文只保留第一层代码入口，细节从代码继续读。

| 目的 | 入口 |
|---|---|
| 看技能定义 | 维护仓 `skills/post-migration/`、`skills/maintainer/auto-nn-init/`。**业务仓不应含 skills/**（v1.28+ governance-sync 不再下发；模板真源在维护仓根，业务仓按 `.auto-nn/template-root` 或 `~/.cursor/skills/auto-nn-*` symlink 解析） |
| 看 init 场景契约（3 yaml，**v1.22.0 起替代原 4 yaml**） | `template/package/scenarios/{build,migrate,update}.yaml` |
| 看 workflow 自动判定 | `template/package/scripts/init_workflow.py`（`Workflow` enum + `classify()` + `resolve_workflow()` override，**v1.22.0 取代原 `init_scenarios.py`**） |
| 看实验协议 | `template/package/PROTOCOL.md` |
| 看多轮编排 | `template/package/auto-nn-run.sh` |
| 看基础实验接口 | `template/package/experiment.py` |
| 看三范式 skeleton（WP0.1 统一为 `contract/` 子目录布局） | `template/package/contract/{supervised,rl,physical}/` |
| 看 workspace 注册机制（`@register_learner` / `@register_objective` / `@register_augmentation`）| `template/package/workspace/__init__.py`（supervised/rl） + `template/maintainer/skeletons/physical/workspace/__init__.py`（physical β named scheme elif 分派，在 `build_optimizer` 内） |
| 看 ADAPTER 场景 CLI 适配器参考（**v1.22.0 起改由 `framework` object_type 承载；目录保留作 backward-compat 示例**） | `docs/examples/adapter-mammoth/workspace/__init__.py`（原 `skeletons/mammoth/`，原 ADAPTER 场景参考实例，**ADAPTER 已退役但目录保留**；非范式骨架） |
| 看 ABCDE manual 生成与注入 | `scripts/init_o3_abcde.py`（`write_init_outputs()` 生成 `references/manual/abcde-manual.md`，framework 信号走内存入参）+ `scripts/inject_innovation_segments.py`（`render_tier_slice` 每轮切 manual cell）+ `auto-nn-run.sh` `_inject_innovation_prompt()`（注入）。注：`scripts/abcde_defaults.py` + `.auto-nn/abcde-guidance.yaml` v1.16.0 已整体删除 |
| 看反思流程 | `template/package/reflect.py` |
| 看审查（复现/多种子/卡片） | 技能 `/auto-nn-audit`；`scripts/nn_audit.py` |
| 看立尺（朴素下界/公开对照） | 技能 `/auto-nn-plain` / `/auto-nn-reference`；`scripts/nn_baseline.py` |
| 看结构体检 | `template/package/scripts/nn-doctor.sh` |
| 看共享库 | `template/package/scripts/lib/`（含 `presets.py` 4 档 nn-config preset / `lock_terminology.py` 30+ 锁字段 / `lock_normalize.py`） |
| 看沙箱测试设施（独立仓） | 独立仓库 `sandbox-auto-nn`（持 `/sandbox-init` / `/sandbox-run` / `/sandbox-register`，模板仓 v1.4.0 起不再持有） |

维护规则：

- 改技能数量或技能职责时，同步本文第 5 节。
- 改三阶段职责时，同步本文第 0-4 节。
- 改动作空间或 TAM 口径时，同步本文第 3 节。
- 改具体命令时，优先同步对应 `SKILL.md`，本文只在第一层概念变化时更新。
- 改注册装饰器、新增/移除 registry、同步 §1.3.1 / §1.3.2 两表。
- 改 doctor 检查覆盖或三原则严重度，同步 §5.2 表格。
- 改 workflow 契约、增减 workflow 类型，同步 §1.1 3 workflow 表（v1.22.0 起替代原 4 场景表） + `scenarios/` 同步增 yaml。

---

## 7. 说人话

auto-nn 不是一堆命令，而是一套让 Agent 做神经网络实验时不跑偏的系统。

第一步 build：先把项目接进来，把“比什么、怎么比、什么时候算更好”说清楚。  
第二步 governance：持续看住边界，防止 Agent 偷改题、乱改口径、丢证据。  
第三步 experiment：在边界里一轮轮试，跑完要记账，失败要反思，下一轮建议要有证据。对人指定的当前最好，可以走审查：再跑一遍、换种子、必要时拆零件，这些不记进成绩表。

以后讨论体系时，优先用这三个词：**接入、治理、实验**。不要先陷入脚本名和内部文件名。

---

## 缩略语说明

- LLM = Large Language Model，大语言模型
- Agent = 能读取上下文、调用工具并执行任务的智能体
- TAM = Tier Attestation Matrix，层级举证矩阵
- OVAT = One Variable At a Time，单变量实验
- PDH = Plain-Discovery Heuristic，朴素发现启发式（首跑 plain baseline 锚定）
- BAS = Baseline-Active-Suggestion，基线主动建议（第 1 轮主动跑 plain）
- WPL = Within-Plateau-Loop，平台期回基线复核
- KEEP = 保留本轮作为新的有效最好结果
- DISCARD = 本轮不作为新的有效最好结果
- ABCDE = 动作空间五层级（A 标量日程 / B 模型表示 / C 目标监督 / D 数据采样 / E 任务评估；见 §3.3）
- RDDN = Routine / Derived / Different / Novel 四档深度轴（v1.20.0 起取代旧 REN 三档 routine/extend/novel；菜单 3 列 routine/derived/different + 路由 4 档 = 5×3=15 + 5×4=20 双副面孔，ADR-5；novel 是事后 attestation 才盖的章、P3+ 全文 + LLM 判才给，弱验证不卡严）
- P0/P1 = Phase 0/1，探索契约重构阶段（P0 已落地于 v1.7.0，P1 延期）
- WP0/WP1/WP3 = Work Package 0/1/3，v3.2 spec 全注册制重构三大包（WP0 = skeletons 结构统一 + **3 workflow + 3 object_type（v1.22.0 起替代原 4 场景 + 5 对象）** + register 语义统一；WP1 = build_* cfg 分派 + physical β scheme；WP3 = 治理层接入锁 OPTIMIZER_SCHEME；v1.10.0 落地）
- α atomic = 范式分派第一型，单算法 cfg 分派（`OPTIMIZER`），supervised/rl 走这条
- β named scheme = 范式分派第二型，分阶段 scheme elif 分派（`OPTIMIZER_SCHEME`），与 α 同形态只是 cfg key 不同，physical 走这条；scheme 名整体可被治理层锁
- PINN = Physics-Informed Neural Network，物理信息神经网络，physical 范式代表场景
- sandbox-auto-nn = 独立仓，v1.4.0 起持有 `/sandbox-init` / `/sandbox-run` / `/sandbox-register` 三 slash 技能；模板仓不持有
- scenarios/*.yaml = init 阶段 **3 workflow** 契约真源（**v1.22.0 起替代原 4 场景**：`build` / `migrate` / `update`，原 `greenfield` / `migration` / `adapter` / `reinit`，ADAPTER 已退役），由 `init_workflow.classify()` 自动判定（v1.22.0 取代原 `init_scenarios.classify()`），`--force-workflow` CLI 显式 override（v1.22.0 取代原 `--scenario`）
- 5 层探索契约（历史术语，2026-07-11 enforcement 退役删除）= v1.7.0 P0 落地的 abcde-guidance 5 层（capability_surface / guidance_matrix / joint_constraints / tam_contract / rescue_ladder）；5×3 思维框架迁 `references/manual/abcde-manual.md`，见 §3.4
- boundaries（历史术语，v1.8.0 物理退役）= 旧 `.auto-nn/abcde-boundaries.yaml`，enforcement + modifier_seeds 亦于 2026-07-11 退役（结构性冗余）；题面保护现由 `contract/` IMMUTABLE 门禁承载（`auto-nn-run.sh:1289` + `Contract(ExperimentBase)`，nn-doctor 内联 `check_ABCDE_boundaries` v1.16.0 已删）；`abcde-guidance.yaml` v1.16.0 整体删除；人/Agent 思维框架由 `references/manual/abcde-manual.md` 承载
- ADR = Architecture Decision Record（架构决策记录），正文里的 `ADR-n` 是维护者设计存档中的决策编号：`ADR-1`=RDDN 四档深度轴定义、`ADR-2`=novel 背书独占 attestation（弱验证）、`ADR-3`=catalog 软层 overlay 反馈、`ADR-5`=菜单 5×3 vs 路由 5×4 双副面孔、`ADR-6`=寻找/评估双胞胎（撞墙 ∧ 深度门控触发）、`ADR-7`=mode = 深度天花板（paper_depth 梯子）、`ADR-8`=eagerness 按 mode 调（plateau_rounds 阈值）、`ADR-9`=github code-fetch（T9，P3+ 才拉 raw code + README）、`ADR-10`=seed_repos 前馈（B1，universal framework/task → GitHub repo 兜底候选）、`ADR-13`=框架键第二真源（contract `innovation` 注册段并入指纹硬判定，种子优先）
- P_F = reflect cycle 「寻找」阶段（Plateau-Find，ADR-6）：与「评估」`P1.85` 共享 router + channel，dataflow 相反，按需触发（`plateau_streak ≥ plateau_rounds ∧ depth ∈ {different, novel}`）
- catalog overlay = `innovation_catalog.yaml` 软层（ADR-3，发版冻结 + 运行期 overlay 可回滚）；寻找阶段反馈边写入此处，下轮 run_context 读取。硬判定真源 = 种子 + contract `innovation` 注册段（ADR-13，框架仓第三方键、立项期人审、种子优先），overlay 永不改 tier/depth
