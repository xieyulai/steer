# PROTOCOL.md — 实验协议（ExperimentBase）

## 0. 总原则

- 口径以 `contract/` 为准（`ExperimentBase` 子类的属性和方法）。
- 换任务：立项时更新 `contract/__init__.py`、`workspace/__init__.py`、`train.py`，并同步本文件。
- `experiment.py` 定义框架，`contract/` 和 `workspace/` 各覆盖不同方法子集。

## 0.1 改码三原则（Agent 改 train.py/workspace/contract 必遵）

Agent 每次改动 `train.py` / `workspace/` / `contract/`（常规迭代与立项均适用）须同时满足以下三条；preflight 对应守门在括号内：

1. **config-only**：实验参数从 config 读（`cfg["X"]` 强读，缺失即 KeyError）；禁 `cfg.get(K, 默认)` 静默兜底（preflight **G-cfg-no-defaults** 硬阻断；大写实验参数键带默认 → FAIL）。**系统参数**（`SMOKE_*` / `CHECKPOINT_*` / `NUM_WORKERS` / `SCENARIO_ID` 等）须显式登记 `SYSTEM_KEYS` 方可 `cfg.get` 默认；禁环境变量读实验参数（白名单外，**G-repro-env** 阻断）。详见 §2.3。
2. **no-fallback**：不兜底、不吞错；错误上抛。`try/except` 仅用于类型解析且须 `raise` / `log`，**不得** `except: pass` / `return 默认` 隐藏失败（preflight **G-no-fallback** WARN；合理 optional 路径用 `# optional:` 标注豁免）。
3. **pluggable**：新增修改（网络 / loss / 增强）走 **config 开关 + registry**（`@register_learner` / `@register_objective` + cfg 键 `MODEL_ARCH` / `LOSS`）；禁止硬编码不走 config 开关的修改。加变体 = 装饰类 + 设 cfg，**不改** `build_*`。

   **例外：** `build_optimizer` / `build_scheduler` 走 **cfg 强读分派**（`cfg["OPTIMIZER"]` / `cfg["SCHEDULER"]`），**不走** registry。理由：算法集合稳定（adam/adamw/sgd + cosine/step/none），不需要运行时插件；新增算法 = 在分派 if/elif 加分支（直接报错路径清晰）。

   **WP1③ 例外：** physical 范式的 `build_optimizer` 走 **`cfg["OPTIMIZER_SCHEME"]` 强读 elif 分派**（与上同形态，只是 cfg key 是 `OPTIMIZER_SCHEME` 而非 `OPTIMIZER`；不再用 registry / `@register_optim_scheme`）。物理方程天然 staged（PINN 典型 Adam→LBFGS），命名 scheme 整体可被锁（治理层可接 `OPTIMIZER_SCHEME.HARD=adam_lbfgs` 一锁锁死流水线）；supervised/rl 仍走 `cfg["OPTIMIZER"]` 分派。新增 physical scheme = 在 `build_optimizer` 加 elif 分支（范式锁死，Agent 不可改 cfg key）。

   **注册制与 ifelse 制都是合法分派形态**：α（sup/RL optimizer）走 ifelse、β（physical scheme）走 elif、B/C/D（模型/损失/增强）走 registry。Agent 改 train.py/workspace 时按所在档位既有形态贯彻，不混用。

   **D 档数据拆两半**：`prepare_data` 里 **读哪个数据集锁死**（supervised 由 contract 常量 `LOCKED_DATASET` 钉死，经 `DATASET_REGISTRY` 查表构造，**不走 cfg**、Agent 每轮动作不可达；换数据集 = E 档/人审级，非 A-D 轮内动作）vs **怎么处理可改**（transform / aug / **`DATA_SAMPLER`（`@register_sampler`）** / `BATCH_SIZE` / `NUM_WORKERS` 走 cfg，Agent 可调）。采样器等训练技巧在 **workspace** 注册，由 `ExperimentBase.wrap_train_loader`（`train.py` 在 `prepare_data` 之后调用）重包 loader；**禁止**把 `WeightedRandomSampler` 写进 `contract/prepare_data`（否则每加一种技巧都要 `NN_RELAUNCH`）。新增数据集 = 在 `DATASET_REGISTRY` 加一行 + 改 `LOCKED_DATASET`（contract 改，非 agent 每轮动作）；未知名 → `KeyError`（no-fallback，不静默回落）。

**三原则**适用于：常规迭代（`train.py` / `workspace/`）、立项 / 迁移（含 `contract/`）、`/auto-nn-modify` 所有 Modify 轨。违反 = 污染代码，须回滚。

> **当前 doctor 覆盖 (2/3 scanner)**：G-cfg-no-defaults (config-only) + G-no-fallback (no-fallback)。pluggable = 第 3 条 设计自检（prompt 注入，非 scanner，3/3 三原则）。每轮结束后自动跑 doctor，FAIL 行进入下轮 prompt 头部；pluggable 原则块每轮总是注入（见 §6 步骤 8b）。

### 0.1a 改法模式（按档）

| 档 | 第一次（代码改动） | 之后（日常迭代） | 三原则侧重 |
|----|-------------------|-----------------|-----------|
| **A 档** | 把硬编码 → `cfg["PARAM"]`（改 workspace/train.py） | 只改 config.json 值 | config-only |
| **B 档** | `@register_learner("new_arch")` + 设 `MODEL_ARCH` | 只改 config.json 的 `MODEL_ARCH` | pluggable |
| **C 档** | `@register_objective("new_loss")` + 设 `LOSS` | 只改 config.json 的 `LOSS` | pluggable |
| **D 档** | `@register_augmentation("new_aug")` + 设 `AUGMENTATION`；或 `@register_sampler("…")` + 设 `DATA_SAMPLER` | 只改 config.json 的 `AUGMENTATION` / `DATA_SAMPLER` | pluggable |
| **E 档** | 锁定；改 = 新 scenario 或人审 | 不动 | — |

> **关键区别**：A 档"第一次"不需要 registry，只需把硬编码改成 `cfg["X"]`；B/C/D 档"第一次"需要 registry（`@register_learner` / `@register_objective` / `@register_augmentation`）。所有档"之后"都只改 config.json——这正是 config-only 原则的体现。

## 1. 任务定义

- 入口：`poetry run python train.py`
- 当次结果在 `_runs/exp/<datetime>_<pid>_s<slot>of<total>_<experiment>/`（单槽默认为 `s0of1`）
- 训末：`finalize_run` 只写**该** `exp_dir/` 下的 `results.json`、`keep_suggestion.json` 等；**不**写仓库级台账（`train.py` 传 `append_repo_ledger=False`）
- 仓库级：`_runs/round_decision.json`、`_runs/results.tsv`、`_runs/results.jsonl` 由 **`finalize_round`** 在一次顺序调用中写入（单槽时 `train.py` 默认在训末自动调用；多槽并行由 `wait-train.sh` 在全部 slot 训完（且无 fail）时自动调用 `finalize-round`；二次幂等跳过）。**一轮一次决策**（`round_decision` / `keepers` / `wall_hit`）；**每个成功槽各追加一行**主 TSV/jsonl。**1 行 = 1 次实验（槽位）**，不是 1 轮编排。TSV **禁止**加 `keep`/`discard` 等 KEEP 决策列（见 §8）
- 训后钩子：`finalize_round` 之后 `train.py` 调用 `ws.post_train_hook(...)`（`ExperimentBase` 默认 no-op；课题在 **`workspace/`** 覆盖，**勿**在 `contract/` 画图）；`NN_POST_TRAIN_HOOK=0` 可跳过
- **官方 test 权重**：`contract.test`（经 `dispatch_test_call`）前须与 `nn-config.checkpoint` 一致（`best` → 载入训内 `best_state`；`last` → 末轮）；装权重由 `finalize_training_loop_artifacts` → `apply_checkpoint_policy_to_learner` 完成；`finalize_run` **只消费** `precomputed_official_metrics`，不再内部 `contract.test` / 再装 checkpoint
- **训内早停**：`nn-config.early_stop.patience`（默认 `0`=关闭）；`>0` 时连续 N 次 **evaluate** 主指标（`contract.metric_key`）无提升则停（仅 NATIVE 循环）；训后 `train_done.json` 由 `finalize_training_loop_artifacts` 统一写，`stop_reason` 来自 `dispatch_training` 出口归一结果（NATIVE 带出 `epochs_complete` / `early_stop_patience` / `time_budget` 等；缺省 `mech_complete`）；可用 `NN_EARLY_STOP_PATIENCE` 覆盖；与 `checkpoint:best` 配套可避免 best 后空转
- 台账：`EXPERIENCE.md` 仍由 Agent 维护
- 辅助 CLI（仓库根执行）：`poetry run python -m contract`（默认：对给定 `--exp-dir` 写其中 `keep_suggestion.json`）、`poetry run python -m contract finalize-round <…>`（写 `_runs/round_decision.json`；`keep_suggestion=true` 时自动更新 **`saved/keepers.json`** 中 **当轮 `scenario_id`** 条目）、`poetry run python -m contract write-keeper --exp-dir <keeper> [--scenario-id <id>]`（人工 adopt 基线或补写 **该场景** keeper 条目）、`poetry run python -m contract sanity`
- **运行态治理**（单词档名 `inspect` 只看 / `junk` 删脏 / `runs`·`runs+journal` 整仓 / `experience`·`reflect`·`factory` / `custom` prune）：走技能 **`/auto-nn-clear`**（Agent 出《清理计划》+ dry-run，**用户确认后可由 Agent 代跑** `bash scripts/govern-runs.sh clear --tier … --apply`；`factory` 另须 `--confirm factory`）。**禁止**未确认就 apply；**禁止**手改 `_runs/results.tsv` / `results.jsonl`；`prune`/`reset` 子命令已废止
- **结构体检**：走技能 **`/auto-nn-doctor`**（`scripts/nn-doctor.sh`；文档 [`docs/nn-doctor/README.md`](docs/nn-doctor/README.md)；默认轻量，深度档 `--deep` 含 smoke）。**`env_runtime`**：`libcudnn`/`.so` 动态库缺失与缺 pip 包分文案（仍 FAIL）；env 未通过时 **`contract_sanity` 为 SKIP**（不重复计 FAIL）。**`scenario_completeness`**：`agent.scenario_default` **空 → FAIL**（须钉 F1 清单内 ID）。governance-sync **强制下发** `contract/__main__.py`（`python -m contract` CLI 壳；无业务逻辑）。
- **迁后改能力（人）**：新 metric、场景、`contract/` 口径，以及人主动改 workspace/train 的能力扩展：走技能 **`/auto-nn-modify`**（文档地图 [`../../docs/nn-modify/README.md`](../../docs/nn-modify/README.md)）。
- **实验轮 Agent**：改 `train.py` / `workspace/` 属 E 闸门自主区（见下），守 §0.1；**不**经 `/auto-nn-modify`。
- **审查（不进成绩表）**：走技能 **`/auto-nn-audit`**。对人指定对象（默认当前最好）做复现 / 多种子 / novel 判定 / 归因消融；训练须 `--no-auto-finalize-round`，禁止随后 `finalize-round`；结论进 `saved/audit/` 卡片与 `index.json` 活指针，后续盘面 / 反思可注入。**禁止**与轮末 `finalize_round` 混名；**禁止**当搜索轮写入 TSV。

## 2. 指标与训练目标

### 2.1 主指标

- `contract.metric_key` / `metric_direction`
- keep/discard 由 `nn-config.yaml` 的 `keep` 段决定（`finalize_round` → `should_keep`；相对阈值经 `presets.py` / `experiment_mode._resolve_keep_delta` 定 `primary_delta_rel`）
  - 默认 **`improve_mode: any_primary`** + **`mode: relative`** + **`primary_delta_rel`**（如 `0.005` → 门槛 `best×(1+0.005)`）：`primary_metric_keys` 中**任一**键相对历史最佳达到该比例即建议 KEEP（单主指标项目即 `metric_key` 一项）。公式与例子见 §7.2.1。
  - **`improve_mode: primary`**：仅 `metric_key` 一项，规则同上（同样用 `primary_delta_rel`）。
  - **`improve_mode: "any_metric"`**：`metric_key` 与 `aux_metrics` 中每个在当次 `results` 里出现的键，**只要有一个**相对该键在 TSV 中的历史最佳有**严格**改善（按各自方向），即建议 KEEP；`primary_delta_rel` 在此模式下不参与 OR 判断（仍保留在 dict 中便于切回 `primary`）。`aux_guards` 仍可一票否决。
  - **`improve_mode: "any_primary"` / `"all_primary"`**：对 `contract.primary_metric_keys`（默认仅 `metric_key`；多主指标项目在 contract 中覆盖）逐项用 `primary_delta_rel` 与历史最佳比较；**任一**达标 → KEEP（`any_primary`），**全部**达标 → KEEP（`all_primary`）。键名与方向在 contract 定义，不在 yaml 列出。
  - 老字段 **`primary_delta`** 仅向后兼容只读；解析优先级见 `experiment_mode._resolve_keep_delta`（`primary_delta_rel` → `primary_delta` → 默认 `0.005`）。
  - **KEEP 可比历史（场景分池）**：`should_keep` **仅收集 TSV 中与当轮相同的 `scenario_id` 的行**参与历史对比；**禁止**跨场景混比。**`contract.history_experiment_substr`**（旧：`experiment` 子串过滤）**已废弃**；勿再依赖或在 contract 覆盖（遗留由 `nn-doctor` WARN 直至 **Modify-Scenario-complete** 移除）。
  - **`near_best_abs`（可选，默认 0 关闭）**：与 TSV 量纲一致的绝对容差。任一参与判断的指标在「未严格变好」时，若仍落在历史最佳附近（`maximize`：`current >= best - tol`；`minimize`：`current <= best + tol`），与严格改善**同等**视为建议 KEEP；`improve_mode: primary` 时仅用于主指标；`any_primary` / `all_primary` 下对 `primary_metric_keys` 各项同样适用。
- **KEEP 流程细节**（`finalize_round` 自动写盘）：
  - 写盘位置：`saved/keepers.json`（**map** by `scenario_id`）；单列 `saved/keeper.json` 仅为遗留形态
  - 命令：人工 adopt 或兼容旧模板用 `poetry run python -m contract write-keeper --exp-dir <keeper_exp_dir> --scenario-id <id>`（指向 `_runs/exp/<keeper>/`，**不**复制 `best_model.pt`）
  - 禁路径：禁止 `_runs/keep/`、禁止复制到 `saved/keep/*.pt`（迁前遗留）
  - skip env：`NN_SKIP_WRITE_KEEPER=1` 可跳过自动写入
  - 当轮 snapshot：见 Run Context `### keeper-status` 段（build-run-context.py 每轮注入 per-scenario 状态）
- 常规迭代中 Agent 不得私改 contract

### 2.2 辅助指标

- `contract.aux_metrics` 声明辅助指标名与方向
- 训练结果须包含这些键
- **不许假缺**：`finalize_run` 对声明键缺/`None` → FAIL；数值 **0 合法**。近若干轮台账辅指标**恒为 0** → analyse / doctor `aux_always_zero` **WARN**（提示可能未接线；合法恒零可忽略）。模板**不**替业务算框架遗忘指标。

**台账分级与跨场景 KEEP：** 参与 KEEP 对比的键须在 `metric_keys` / `auxiliary_keys`（TSV **metrics** 区）；运行参数进 `ledger_context_keys`（**parameters** 区）；仅备注进 `notes`。多场景：先 F1 **场景清单**（**必填台账列 `scenario_id`**）、再 `SCENARIO_POLICY`。勿跨场景 KEEP —— 靠 **`scenario_id` 分池**，**不使用** ~~`history_experiment_substr`~~。见维护仓 `docs/archive/metric-and-keep-system.md` §3。

**场景号归属：** 合法 `scenario_id` 属 **cfg（`config.json` / `cfg["scenario_id"]`）+ README / F1 场景清单**；`contract/` **不**持 `SCENARIO_ID` 常量或 `scenario_id` property。写入台账与 preflight 均经 `validate_scenario_id`（不在清单 → raise；G-场景阻断）。扩场景 = Modify-Scenario-expand（改清单），非改 contract 空壳常量。业务仓若残留 `SCENARIO_ID`∈contract → doctor `scenario_not_in_contract` FAIL；迁出到 cfg。

### 2.2.1 训练遥测 WARN（不阻断）

训中 `ExperimentBase` 对过程指标做轻量 stderr WARN，**不** raise、**不**影响写盘 / KEEP：

- **未声明 loss 分量**：`train_step` 返回的键名含 `loss`、且未在 `contract.loss_log_keys`（及 `train_loss`）声明时，首次出现 auto-capture 进 `metrics_series`，并 WARN 一次，提示在子类 `loss_log_keys` 显式声明。
- **non-finite 主/辅指标**：每 epoch `record_train_epoch` 对标量查 nan/inf；命中即 WARN（含 epoch 标签），训练继续。供 round-doctor / reflect 立刻看见「本轮曾 NaN」。

### 2.3 环境变量（Config-Only）

> ⚠️ **Config-Only**：实验参数（SEED、LR、EPOCHS 等）**禁止**通过环境变量或 CLI 设置。
> 所有实验参数必须通过 `--config config.json` 传入。

**系统参数**（允许通过环境变量）：

| 参数 | 说明 |
|------|------|
| NN_TIME_BUDGET | **冻结派生量，非可调参数**：`auto-nn-run.sh` 从 `nn-config.yaml:time_budget` 派生导出；train.py 取值点校验预置值 ≠ yaml 即拒启（RuntimeError）并记 `_runs/time_budget_violations.log`。改时限唯一通道 = 停 batch 后由人/编排器改 yaml |
| NN_DEVICE | auto\|cuda\|cpu |
| NN_SMOKE | 默认关（0=全量）；迁移验收 `smoke-check.sh` 显式 `NN_SMOKE=1` |
| NN_SMOKE_BUDGET | smoke 专用短墙钟（秒），默认 120；仅 `NN_SMOKE=1` 时经 TimeGuard 显式传参生效，不落 config.json（与 yaml 时限无关） |
| NN_PREFLIGHT | 默认开 |
| NN_AUTO_FINALIZE_ROUND | 默认 1 |
| NN_EXPERIMENT | 实验标识 |
| NN_PARALLEL_TOTAL | 并行槽数，默认 1 |
| NN_SLOT | 并行槽 0-based |
| NN_POST_TRAIN_HOOK | 默认 1 |
| NN_NOTES | 可选，写入台账 notes 列 |
| NN_EARLY_STOP_PATIENCE | Early stop patience，默认 0 |
| NN_APPEND_RESULTS_TSV / NN_APPEND_RESULTS_JSONL | 默认均为 1，须保持一致 |
| NN_GUARD_* | G-* 门禁开关（见 §3.3），默认 1 |
| NN_RELAUNCH | 非空表示立项/迁移轮次 |
| NN_ROOT_PY_ALLOWLIST | 逗号分隔，追加根目录允许的 `.py` 文件名 |
| NN_PREFLIGHT_LEDGER | preflight 台账，默认 0 |

> **注意**：`SEED`、`scenario_id` 等实验参数**禁止**通过 `NN_SEED`、`NN_SCENARIO_ID` 等环境变量设置，必须写入 `config.json`。

> **时限冻结（Config-Only）**：`time_budget` 唯一真值在 `nn-config.yaml`；会话内 export `NN_TIME_BUDGET` 改墙钟一律拒启（train.py 取值点 + launcher 双守卫，违约记 `_runs/time_budget_violations.log`）。旧第三来源 `NN_AGENT_TRAIN_TIME_BUDGET_SEC`（编排器 passthrough）已**弃用拆除**。收工审计：`python3 scripts/check_time_budget_audit.py`（config.json 落值对齐 yaml，偏离 exit 1）。

**实验参数**（**禁止**通过环境变量或 CLI 设置）：

所有超参（scenario_id、SEED、LR、EPOCHS、GRAD_CLIP、NET_ARCH、BATCH_SIZE、WEIGHT_DECAY、DROPOUT、SCHEDULER、STEP_SIZE、GAMMA、LABEL_SMOOTHING 等）必须通过 `--config config.json` 传入。

**实验参数唯一入口**：
```bash
# 实验配置统一放在 _runs/configs/ 目录，命名与实验目录一致
mkdir -p _runs/configs

# 方式 1：手动写（完整配置）
cat > _runs/configs/20260530_my_experiment.json << 'EOF'
{
  "SEED": 42,
  "LR": 0.001,
  "EPOCHS": 100,
  "scenario_id": "default"
}
EOF

# 方式 2：快速修改参数（推荐）
# 从已有配置复制并修改部分参数
python scripts/modify-config.py _runs/configs/20260530_lr003.json \
    --from-template _runs/configs/20260530_my_experiment.json \
    --set LR=0.003 --set EPOCHS=200

poetry run python train.py --config _runs/configs/20260530_my_experiment.json
```

**快速修改参数**（modify-config.py）：
```bash
# 只改 LR（不改其他字段）
python scripts/modify-config.py _runs/configs/20260530_my_experiment.json --set LR=0.003

# 从模板复制并修改
python scripts/modify-config.py _runs/configs/new_exp.json --from-template _runs/configs/base.json --set LR=0.005

# 预览（不写入）
python scripts/modify-config.py _runs/configs/experiment.json --set LR=0.003 --dry-run
```

**复现实验**（Config-Only）：
```bash
# 直接使用已有实验的 config.json 复现训练
poetry run python train.py --config _runs/exp/<experiment_dir>/config.json
```

**Config-Only 强化（无默认）**：基类与业务仓代码中**实验参数**读取必须用 `cfg["XXX"]`（缺失即 KeyError），**禁止**用 `cfg.get("XXX", default)` 静默兜底。系统参数（`SMOKE_*`、`CHECKPOINT_*`）可保留 `cfg.get`。

**路径/env 兜底（doctor `cfg_path_fallback`）**：`train.py` / `workspace/**/*.py` 中禁止向全大写 cfg 键写入 `os.environ.get` / `os.environ[...]` 或 `/mnt/`、`/home/`、`/Users/` 等绝对路径字面量；路径须进 `config.json` 或模块常量，运行时 `cfg["KEY"]` 强读。

**shared_context 禁 contract（doctor `shared_context_contract`）**：不得把 `contract` 实例塞进共享袋或从袋静默兜底读取；与 ADR-11 / CLAUDE「contract 不依赖 shared_context」一致。

**违规处理**：
- `nn-doctor.sh` G-repro-env FAIL → preflight 阻止训练启动
- Agent 在 train.py 中违规添加实验参数 NN_* 读取 → 视为污染代码，需回滚并重新通过 governance-sync 同步

### 2.4 实验复现（立项/迁移须在 HARD-GATE 钉死）

复现分三层，**澄清阶段**对应 HARD-GATE **D4-repro-data**（数据）与 **O4-repro-determinism**（随机性 + 快照），F1-contract 须落「复现配方表」。

| 层 | 须对齐什么 | 澄清编号 | 模板落盘 |
|----|------------|----------|----------|
| **环境** | Python/torch/CUDA、git、`cuDNN` 确定性策略 | O4 | `env_snapshot.json`（含 `repro`）；`train.py` 已设 `cudnn.deterministic=True`、`benchmark=False`（一般**不必**再 export `TORCH_CUDNN_*`） |
| **数据** | 数据根/版本（如 `NN_INDIVIDUAL_DIR`、v2 vs v3） | D4 | `contract/runtime.py` → `REPRO_ENV_KEYS`；`config.json` → `_repro.repro_env` |
| **训练** | `SEED`（`config.json`）、超参、`git_commit` | O4 + E7 | `config.json` 超参 + `cfg.SEED`；TSV `parameters` 区（`ledger_context_keys`） |

**复现某次 run 的最小步骤**（按优先级）：

1. `git checkout <TSV 或 env_snapshot 的 git_commit>`
2. 打开 `_runs/exp/<dir>/`：`code_snapshot/` + `config.json` + `env_snapshot.json` + `best_model.pt`
3. **Config-Only**：直接用已有实验的 `config.json` 复现训练，无需设置 `NN_SEED` 等环境变量
4. `poetry run python train.py --config _runs/exp/<dir>/config.json`（或课题规定的 eval 命令）

**Agent 维护**：`EXPERIENCE.md`「复现配方」段记录项目基线（种子、数据路径、已知等价数据集）；每轮重要实验可在实验记录下抄 `exp_dir` + `git_commit`。

## 2.5 从 config.json 复现实验（Config-Only）

> ⚠️ **Config-Only**：实验参数**仅从** `config.json` 读取，禁止通过环境变量或 CLI 设置。

复现步骤：
1. `git checkout <git_commit>`
2. 复制 config：`cp _runs/exp/<experiment_dir>/config.json ./_repro_config.json`（或任意路径）
3. 执行训练：`poetry run python train.py --config _repro_config.json`

```bash
cp _runs/exp/<experiment_dir>/config.json ./_repro_config.json
poetry run python train.py --config _repro_config.json
```

### 2.5.1 Config-Only 机制说明

**唯一入口**：`poetry run python train.py --config config.json`

**禁止**：
- 环境变量设置实验参数（`NN_SEED`、`NN_LR` 等）
- CLI 参数设置实验参数（`--lr`、`--seed` 等）

**允许**：系统参数通过环境变量（见 §2.3 白名单）

## 3. 修改边界

### 3.0 ExperimentBase + contract/ + workspace/

| 区域 | 文件 | 规则 |
|------|------|------|
| 框架 | `experiment.py` | 不可改（含 TimeGuard、checkpoint、preflight、finalize） |
| 契约 | `contract/__init__.py` | 常规迭代不可改；立项可改 |
| 实现 | `workspace/__init__.py` | 每轮可改 |
| 编排 | `train.py` | 每轮可改 |

### 3.0.0 立项 / 迁移五阶段（Agent 执行）

| 阶段 | 内容 | 官方命令 |
|------|------|----------|
| 0 分析 | 方法对照 + G-封装/评估/布局 | `bash <template_root>/scripts/migration-compare.sh --template-root T --project-root P` |
| 1 HARD-GATE | F1 仅签 H/D/T/E/O 口径（**H→D→T→E→O**；先 T2 再 E4-train-eval / E8-checkpoint） | 模板根 `skills/maintainer/auto-nn-init/SKILL.md` |
| 2 实现 | 改 contract/workspace/train（`NN_RELAUNCH=1`） | — |
| 3 交付卫生 | CHECKLIST §2–§4 | — |
| 4 验收 | **完成门禁** | `bash scripts/verify-migration-complete.sh`（exit 0）+ CHECKLIST §5 smoke；其中 **`references/manual/abcde-manual.md` 必须存在**（缺则 verify / doctor `abcde_manual` FAIL；立项 `new-project` 缺则 exit ≠ 0） |

**F1 签字 ≠ 迁移完成**；勿读业务仓 `docs/`。细则见模板根 SKILL 与 CHECKLIST §0。

### 3.0.1 ExperimentBase 方法分配

| 方法 | 默认实现 | Contract 覆盖 | Workspace 覆盖 |
|------|---------|:---:|:---:|
| `metric_key` / `metric_direction` | raise | ✔ | |
| `aux_metrics` | raise | ✔ | |
| `prepare_data(cfg)` | raise | ✔ | |
| `test(learner, ws, *, shared_context)` | raise | ✔（所有 profile 必须实现） | |
| `evaluate(learner, *, shared_context)` | raise | | ✔ |
| `build_learner(cfg)` | raise | | ✔ |
| `build_objective(cfg)` | raise | | ✔ |
| `train_step(learner, source, objective, *, epoch, shared_context)` | raise | | ✔ |
| `predict(learner, batch, *, shared_context)` | raise | | ✔ |
| `should_keep` / `preflight_check` / `finalize_run` / `finalize_round` / `save_checkpoint` | ✔ | | |
| `pick_keeper_exp_dir`（多槽选 keeper） | ✔ | 可覆盖 | |
| `TimeGuard`（独立类，在 `experiment.py`） | ✔ | 若 `train.py` 写 `from contract import TimeGuard`，须在 `contract/__init__.py` re-export | |

### 3.0.1 Preflight 与 profile（train.py 编排，非 experiment 内分叉）

**要点：** `experiment.py` 里的 `preflight_check` **不读** `nn-config.yaml` 的 `profile`，也**没有** `if profile == "rl"`。  
**范式差异体现在各项目 `train.py` 如何调用**；验收时由 `scripts/smoke-check.sh` 按 profile 检查不同日志关键字。

#### `ExperimentBase.preflight_check` 做了什么

| 步骤 | 条件 | stderr 标记 |
|------|------|-------------|
| 静态守门 | 始终（`NN_PREFLIGHT≠0`） | `静态守门 OK` |
| loss → backward | 传入 `learner` **且** `loss_fn` | `loss OK` |
| 试写 finalize | 传入 `finalize_fn` | `finalize OK` |
| G-台账 | `preflight_check` 内、静态守门之后 | `[G-台账] 警告`（表头不一致时） |

#### 静态守门矩阵（与 `verify` / `_run_static_preflight_guards` 同源）

**何时跑**：`NN_PREFLIGHT≠0` 时，每次 `train.py` 进入 preflight 前执行 `_run_static_preflight_guards`；**G-台账**在 `preflight_check` 内、静态守门通过后再查 `_runs/results.tsv` 表头。

**三源 diff**（G-契约 / G-框架 / G-治理文档）：工作区 `git diff --name-only` ∪ 暂存 `git diff --cached --name-only` ∪ 最新 commit `git diff --name-only HEAD~1 HEAD`（无 `HEAD~1` 则第三项为空）；无 git 时不触发。`NN_RELAUNCH` 非空时跳过上述三项（**唯一正当解锁**）；紧急旁路：`NN_GUARD_EXPERIMENT_DIFF=0` / `NN_GUARD_CONTRACT_DIFF=0` / `NN_GUARD_GOVERNANCE_DOCS=0`（不推荐）。

| 代号 | 检查对象 | 结果 | 环境变量 | 说明 |
|------|----------|------|----------|------|
| **G-封装** | `train.py` 不得 `from workspace.<子模块> import` | **FAIL** | `NN_GUARD_ENCAPSULATION` | RuntimeError，阻断 preflight |
| **G-路径** | `train.py` 产物须在 `_runs/exp/`（`allocate_exp_dir`） | **FAIL** | `NN_GUARD_EXP_DIR` | |
| **G-评估** | `contract.test` 权威（门面 + `contract/test.py`） | **FAIL** | `NN_GUARD_TEST_AUTHORITY` | |
| **G-信息权限** | `contract/runtime.py::INFO_PERM`（字面量登记表）：合同静态拦登记表 / 受限交卷路径 / 开关字面量；只评材料 **训练真打开或真调用** 才拦（工作区预留字面量不拦预检）；`preflight_check(train_batch=)` 另校首 batch 键白名单 | **FAIL** | **无**（家族特例：只认 `INFO_PERM["enforce"]`；未登记或 `enforce=False` 空转） | RuntimeError，阻断 preflight 或训练中途真用只评材料；`enforce` 改动 = 改合同（受 G-契约 / `NN_RELAUNCH`）；对照两臂 = 两份合同 |
| **G-契约布局** | `contract/` 四文件拆分与引用 | **FAIL** | `NN_GUARD_CONTRACT_LAYOUT` | |
| **G-门面** | `profiles.yaml` 与 contract/workspace 类方法、`forbidden` | **FAIL** | `NN_GUARD_PROFILE_FACADE` | 与 G-范式互补：forbidden 在此硬失败 |
| **G-布局** | 仓库根目录 `*.py` 白名单 | **WARN** | `NN_GUARD_ROOT_PY`、`NN_ROOT_PY_ALLOWLIST` | 探路脚本放 `workspace/scripts/` |
| **G-cfg-no-defaults** | 实验参数不得用 `cfg.get("KEY", default)`，须 `cfg["K"]` 强读（严格：任何大写实验参数键带默认 → FAIL） | **FAIL** | `NN_GUARD_CFG_DEFAULTS` | RuntimeError，阻断 preflight |
| **G-no-fallback** | 吞错 `except`（`except: pass` / `return 默认` 隐藏失败；合理 optional 用 `# optional:` 豁免） | **WARN** | `NN_GUARD_NO_FALLBACK` | 三原则·no-fallback；scanner 始终 exit 0，仅汇总 stderr 供人审 |
| **G-契约** | `contract/` 三源 diff 有命中 | **FAIL** | `NN_GUARD_CONTRACT_DIFF`、`NN_RELAUNCH` | RuntimeError，阻断 preflight；立项/改口径须 `NN_RELAUNCH=1` |
| **G-框架** | `experiment.py` 三源 diff 有命中 | **FAIL** | `NN_GUARD_EXPERIMENT_DIFF`、`NN_RELAUNCH` | RuntimeError，阻断 preflight；治理 sync / 立项须 `NN_RELAUNCH=1` |
| **G-治理文档** | `CLAUDE.md` / `PROTOCOL.md` / `auto-nn-run.sh` 三源 diff 有命中 | **FAIL** | `NN_GUARD_GOVERNANCE_DOCS`、`NN_RELAUNCH` | RuntimeError，阻断 preflight；sync 后首训须 `NN_RELAUNCH=1` |
| **G-范式** | `nn-config.yaml` 的 `profile` 与 `profiles.yaml` 方法清单 | **WARN** | `NN_GUARD_PROFILE` | 缺失方法提示；`forbidden` 由 G-门面 FAIL |
| **G-台账** | `_runs/results.tsv` 表头 vs `contract._default_tsv_columns()`（须含必填 **`scenario_id`**) | **WARN** | `NN_GUARD_TSV_HEADER` | 修复：`scripts/regen_results_tsv.py --repo-root .`；新旧账衔接见 backfill/mandatory-scenario-id spec |

执行顺序（实现）：G-封装 → G-路径 → G-评估 → **G-信息权限** → G-契约布局 → G-门面 → G-布局 → **G-治理文档** → G-契约 → G-框架 → G-范式 → G-repro-env → G-cfg-no-defaults → **G-no-fallback**；通过后打印 `静态守门 OK`，再跑 loss / finalize 试写与 G-台账。

**旁路留痕（训末）**：`finalize_run` 把 `NN_PREFLIGHT` / `NN_GUARD` / `NN_GUARD_*` 取 `0/false/no/off` 的项写进 `config.json` 的 `_repro.guards_bypassed`；非空 → `keep_suggestion=False`（`reason` 前缀「守门被旁路」）；合同 `INFO_PERM["enforce"]=True` 且非空 → `[finalize G-旁路]` 抛错、不入账。跳过守门在本体系里不再是「无痕」操作。

**与 auto-run 的关系**：§7.3 常规轮不得设 `NN_RELAUNCH`；若三源 diff 命中 `contract/`、`experiment.py` 或治理文档（G-治理文档），训前 preflight **FAIL**（与 G-封装同级）；`nn-doctor` 对应 **`immutable_path_guard` FAIL**。轮末 shell **仅**警告 `EXPERIENCE.md` 是否在本轮 commit 中，**不**重复查破坏路径 diff。

#### supervised 与 rl 的 train.py 约定（迁后须遵守）

| 范式 | 训前调用 | 日志里应出现 | 不测什么 |
|------|----------|--------------|----------|
| **supervised** | `contract.preflight_check(learner, loss_fn=…, finalize_fn=…)`（dummy smoke 已移除；smoke = 真数据短跑，TimeGuard 按 `NN_TIME_BUDGET` 墙钟截断） | `静态守门 OK`、`loss OK` | — |
| **rl** | `contract.preflight_check(label=…)` **不传** learner；再 `ws.preflight_env_check()` | `静态守门 OK` | **不要求** `loss OK`（无单 batch CE backward） |

**为何 rl 不用 supervised 那条 loss 路径：** RL 学习器是 SAC + Gym/KNN 环境，数据经 `contract.prepare_data` 解析路径后由 env 消费；常见失败是数据集路径、env `reset/step`、reward/obs NaN，而不是「取一个 DataLoader batch 算 loss」。因此 rl 在 `profiles.yaml` 的 `workspace` 列表中有 **`preflight_env_check`**（实现通常在 `workspace/data_process.py` 或子模块），由 `train.py` 显式调用。

**smoke 验收（§5 `smoke-check.sh`）：** 通用墙钟（`NN_TIME_BUDGET`，默认 120s，`NN_SMOKE_BUDGET` 可覆盖）—— 不再按 profile 设 epoch/step/timestep，不再 grep `smoke: OK` dummy 标记，不再检查 train_dynamics 遥测产物。硬验收 = `train.py` exit 0 + `_runs/round_decision.json` 非空 + **实质指标闸**（`primary_metric.value` 有限；若 keeper `results.json` 含非空 `_error` 且主分为 0 → FAIL；合法真 0 无 `_error` 仍过）。**禁止：** 为通过旧 grep 而硬 `print("loss OK")` / `print("smoke: OK")`（无真实 forward/backward）。

#### `profile` 在哪些**脚本**里会路由（不是 experiment 自动路由）

| 脚本 / 配置 | 行为 |
|-------------|------|
| `profiles.yaml` | 各 profile 的 contract/workspace 方法清单、`workspace_forbidden` |
| `scripts/smoke-check.sh` | 读 `profile` → **supervised** 另 `export NN_EPOCHS=2`（迁移冒烟，不跑满业务 `EPOCHS`）；rl / physical 各用本范式 smoke 判据 |
| `scripts/rl_workspace_gate.py` | 仅 `profile=rl`：D2 `prepare_data`、E3 `evaluate→contract.test` |
| `scripts/verify-migration-complete.sh` | rl 专条 + 治理 rev；非 rl 演示指标检查等 |
| `train.py` / `workspace/` | **不**因改 `profile` 自动换实现；须按上表手写编排 |

立项 / 迁移收尾顺序：`governance-sync.sh` → `verify-migration-complete.sh` → `smoke-check.sh`（见 CHECKLIST §0、§5）。

### 3.0.2 metrics_shape（训末官方评估形态）

训末官方台账指标由 `train.py` 经 `dispatch_test_call`（`scripts/lib/train_branch.py`）按 **`metrics_shape`** 双路径调用 `contract.test`：

| 形态 | 含义 | 调用要点 |
|------|------|----------|
| **`EVALUATE_LEARNER`**（默认） | 进程内评估 learner | `contract.test(learner, ws, shared_context=…)` |
| **`EVALUATE_RUNNER`** | 外部/adapter runner 出指标 | `contract.test(None, ws, shared_context=…, adapter_runner=…)`；`learner` 可为 `None` |

- **Runner 取数**：工作区实例显式属性 **`ws.adapter_runner`**（可调用，返回 `dict[str, float]`）。**禁止**把 workspace 当 dict 用 `.get`；**不**从 `shared_context` 双源读取（ADR-11）。
- **`shared_context` 禁 `contract` 键**（doctor `shared_context_contract`）：`train.py` / `workspace/**` / `contract/**` 不得写入或读取 `shared_context["contract"]` / `.get("contract")`；题面对象只经 `dispatch_test_call` 的独立 `contract` 参数与显式 API（`cfg` / `prepare_data` / `ws.*`）。
- **签名契约**：`contract/test.py::run` **须**接受关键字参数 `adapter_runner`（可默认 `None`）；门面 `Contract.test` 与模板一致总是转发。doctor `contract_test_signature`：门面总转发但 `run` 缺参 → **FAIL**；仅非 None 才转发且缺参 → **WARN**。
- **形态注册键**：`@register_workspace_kind` 在构建时把 build 函数名写入实例 **`__workspace_name__`**；训末用该名查询。未注册默认 `EVALUATE_LEARNER`。
- **来源优先级**：上述注册表 → 未注册默认 `EVALUATE_LEARNER`；`nn-config.yaml` 的 **`workspace.metrics_shape`** 为 **opt-in** 覆盖（显式写出才生效）。
- **老字符串**：`"supervised"` / `"adapter"` 等经 `MetricsShape.from_legacy` 归一（DeprecationWarning）；治理同步会带 `scripts/lib/migrate_metrics_shape.py`（`workspace_kind` → `metrics_shape`）。
- 业务仓启用「评 runner」三旋钮：① `@register_workspace_kind(EVALUATE_RUNNER)` 装饰 build 并用其构建工作区（自动戳 `__workspace_name__`）② 设置实例 **`ws.adapter_runner`** ③ 可选 `nn-config.yaml` → `workspace.metrics_shape` opt-in。常规迭代**不**为换形态改 `contract/`。
- **硬约束（ADR-11）**：官方台账分必须经 `contract.test`（仅经 `dispatch_test_call` 调用）；`train.py` **禁止**私自算官方分写入台账；本轮**不**把评估调度「加深」成空壳透传 module。
- **`finalize_run`**：须传入必填 `precomputed_official_metrics`（由上节 `dispatch_test_call` 产出或测试/preflight 显式注入）；缺则硬失败；**禁止**内部再调 `contract.test` 或 `apply_checkpoint_policy_to_learner`。
- **`finalize_run` 旧 kwargs（非法）**：根级 `train.py` 调用 `finalize_run(..., best_metrics=...)` **已禁止**（`experiment.finalize_run` 不恢复该形参）。governance-sync 末自动 scan；脏则 **FAIL** 并提示 apply。修复：`python3 scripts/lib/migrate_finalize_run_kwargs.py <repo_root> --apply`（默认仅 scan；`--apply` 删/改挂 `best_metrics` 为 `precomputed_official_metrics`，写盘前 `.bak`）。
- **`default_metrics`**：合同上的骨架方法**不是**训末官方主路径；勿与 `adapter_runner` 门面路径混用为双主路径。

### 3.0.2a runner 出分验收（EVALUATE_RUNNER）

`metrics_shape=EVALUATE_RUNNER`（runner 出分）路径须过三道硬验收（真源 `scripts/lib/adapter_accept.py`，文件名/doctor 行名含 adapter 为**命名遗留**；**≠** 已退役的立项 ADAPTER 场景，也**≠** object_type）。判定：`is_evaluate_runner_repo`（`is_adapter_repo` 为兼容别名）。governance-sync 强制下发。

| 规则 | 行为 |
|------|------|
| **空串不透传 CLI** | `append_cfg_cli` 省略 `None`/空串/空白；自写透传仍出 `--flag ""` → doctor `adapter_cli_empty` **FAIL** |
| **辅指标不许假缺** | `finalize_run` 对合同 `aux_metrics` 声明键调用 `require_declared_aux_metrics`：缺/`None` → **FAIL**；数值 **0 合法**；禁止占位填 0 |
| **`baseline_tag` 列** | runner 出分：`ledger.watchlist` 与（若存在）`_runs/results.tsv` 表头须含 `baseline_tag`，否则 doctor `adapter_baseline_tag` **FAIL**（LEARNER / 非 runner 不触发）。全体：表头缺列 → doctor **WARN**。Init **E5** 明示系统列；`ledger_context_keys` / F1.5 `init_watchlist` **强制并入** |

示例：`docs/examples/adapter-mammoth/`（目录名遗留；形态为 runner 出分示例）。不绑死具体框架开关名——声明了辅指标就必须有真值。framework（如 Mammoth 默认 LEARNER）**不会**仅因框架身份触发本门。

### 3.0.2b framework 接入总表（五能力 Discovery）

真源：**`contract/framework_binding.yaml`**（合同附属；**不进** `nn-config.yaml`）。登记框架侧五件事：数据 / 训练 / 评估 / 训记 / 权重是否接得上 auto-nn。

| 节 | 含义 | 本版门禁 |
|----|------|----------|
| `data` / `train` / `train_log` / `checkpoint` | Discovery：`status: bound\|unavailable`（unavailable 必填 `reason`） | doctor 存在性；缺口 **WARN** |
| `eval` | 官方评估出口：`kind: api\|artifact\|stdout` + `primary_raw_key` / `ledger_primary_key` | schema **FAIL**；smoke **对账** |
| `innovation`（可选） | 第三方框架键注册（`primary_keys` + `tables`，schema 同种子 catalog）→ 指纹硬判定**第二真源**（ADR-13） | 缺段 no-op；畸形 **加载即 ValueError** |

**消费（谁读）：** `scripts/lib/framework_binding.py` ← doctor（`fw_binding_*`）/ smoke（`check_eval_binding_smoke`）；`innovation` 段另由 `scripts/lib/innovation_fingerprint.py` 的 `load_innovation_catalog` 合并进硬判定（**种子优先**，键/表冲突不覆盖；畸形注册段 ValueError 上抛）。**不读：** `dispatch_training` / `dispatch_test_call` / KEEP（调度轴仍是 §3.0.2 / §3.0.3）。

**评估两段式（`eval.status=bound`）：** ① 框架原样 raw（禁止在翻译层 mean/自创主分）→ ② 键映射进台账 → ③ 经 `contract.test`（ADR-11）。训末落盘 `_runs/exp/<tag>/eval_export_raw.json`；smoke 验 `ledger[ledger_primary_key] ≈ raw[primary_raw_key]`。

**触发：** `object_type=framework` 或仓库已放置该文件 → 启用；纯 supervised 无文件 → 整组跳过。与 §3.0.2a runner 出分门禁**正交**。

示例总表：`docs/examples/adapter-mammoth/contract/framework_binding.yaml`。

### 3.0.3 training_mech（训练调度分流）

训练主循环由 `train.py` 经 `dispatch_training`（`scripts/lib/train_branch.py`）按 **`training_mech`** 派发——对照 §3.0.2 的 `dispatch_test_call`（评估侧），这是训练侧 dispatcher。注入式：train.py 把 native / in-process / subprocess 三条路径包成闭包注入。

| 机制 | 含义 | 当前状态 |
|------|------|----------|
| **`NATIVE`**（默认） | 跑 train.py 注入的 native 训练闭包（ws.train_step / ws.evaluate / finalize） | **默认实跑路径**（supervised / RL） |
| **`IN_PROCESS`**（托管·回调） | 同进程框架开车；调 **`ws.framework_train(...)`**（**新钩子**，不复用 `train_step`） | **骨架已通**；返回与 NATIVE 同形四键 dict；缺钩子显式失败 |
| **`SUBPROCESS`**（外包·事后） | 外部 CLI；`ws.framework_subprocess_cmd(exp_dir) -> list[str]` + `ws.framework_result_path`；`run_subprocess_training` 读 JSON | **骨架已通**；JSON 须含 `best_metrics`（dict）；过程曲线本档不进台账 |

返回经 `normalize_training_result` 的 dict：必填四键 `best_state` / `best_metrics` / `best_epoch` / `last_completed_epoch`（`best_state` 可为 `None`；`best_metrics` 须为 dict）+ `stop_reason`（缺/空则 `mech_complete`）。`dispatch_training` **出口**统一归一。

- **训后收尾（mech 无关）**：`dispatch_training` 返回后，`finalize_training_loop_artifacts(..., result=归一结果)` 写 **`train_done.json`**（`stop_reason` 取自 result）并调用 **`apply_checkpoint_policy_to_learner`**；随后 `dispatch_test_call` → `finalize_run(precomputed_official_metrics=…)`（**不得**再传 `best_metrics=`）。三种 mech 共用；过程曲线 / `train_status.json` / 早停计数仍仅 NATIVE 循环内。
- **来源优先级**：workspace `@register_workspace_kind(training_mech=…)` 注册表 → 未注册默认 `NATIVE`；`nn-config.yaml` 的 **`workspace.training_mech`** 为 **opt-in** 覆盖（显式写出才生效；字符串原样透传，`dispatch_training` 边界归一为 enum）。
- **禁止静默回退**：IN_PROCESS / SUBPROCESS 缺注入或缺钩子 → `NotImplementedError` / 显式错误，**不得**改跑 NATIVE。
- 业务仓常规迭代：**不**为此改 `contract/`；真实 Lightning/mammoth 适配 = 实现上述钩子（本模板不捆绑具体框架）。

### 3.1 实现落点

- 实现（模型、损失、训练步、推理）放 `workspace/`
- 编排放 `train.py`
- 禁止根目录与 workspace/ 并列再建主实现包
- **临时/探路脚本**只放 `workspace/scripts/`（见该目录 `README.md`）；根目录仅保留白名单入口（`train.py`、`experiment.py`、`reflect.py` 等，G-布局 会警告其它 `.py`）

## 4. 领域知识来源

- L0：本文件 + contract/ + experiment.py
- **人类路线图（意图归人）**：根目录 **`HUMAN_GUIDANCE.md`**（`## 路线图`）；见 §7.5
- L1：`references/`（**可选**；`reflect.py` 会创建子目录）
  - `references/manual/` — 人长期文献、笔记；**必含** `abcde-manual.md`（探索说明书；缺 → doctor / verify FAIL）
  - `references/auto/` — reflect 写入 `*_auto_reflected.md`（**禁止**在 `references/` 根平铺）
  - `references/REFLECT_INDEX.md` — **机写**反思索引；实验 Agent **有 pending 时必读**（见 §7.6）
- L3：联网须在 EXPERIENCE.md 留 URL

## 5. 可视化与实验记录

- `_runs/exp/<tag>/`：`tag` 含时间戳、pid、**槽位** `s<slot>of<total>` 与 experiment 名；内含 `config.json`、`results.json`、`keep_suggestion.json`（训末，单槽建议）、`best_model.pt` 等
- `_runs/round_decision.json`：一轮（含多槽）汇总后的 keep 建议；由 `finalize_round` 写入（含 `finalize_round.candidate_exp_dirs` / `keeper_exp_dir` / `slots`）
- `_runs/results.tsv` / `_runs/results.jsonl`：仓库级台账；由 `finalize_round` **单次顺序**追加（避免并行 append）。**一轮一次决策**（`round_decision` / keepers / wall_hit）；**每个成功槽各一行**。**1 行 = 1 次实验（槽位）**，不是 1 轮编排；**禁止** TSV 加 `keep`/`discard` 等决策列
- **`_runs/logs/`**：`train.py` 控制台 stdout（单槽默认 `_runs/logs/run.log`；多槽 `run_slot*.log`）；见 `_runs/logs/README.md`
- **`_runs/agent/`**：`auto-nn-run.sh` 编排日志（批次 `*_batch.log`、会话 `*_agent-round-N.log`、stream-json 等）；见 `_runs/agent/README.md`；**勿**与训练日志混放
- 多槽并行训末只产生多个 `_runs/exp/.../`；全部 slot 训完（且无 fail）时由 `wait-train.sh` **自动** `finalize-round`（等价单槽训末自动 finalize；失败只 WARN）。仅 wait-train 报 auto-finalize WARN 时手动补：  
  `poetry run python -m contract finalize-round <exp_dir1> <exp_dir2> ... --repo-root .`

## §5.1 6 档 exploration_mode（unified-mode）

`nn-config.yaml` 顶层 **`exploration_mode`** 是唯一探索旋钮（6 档预定组合；取代已退役的顶层 `mode` / `experiment.mode` / `exploration.style` / `agent.experiment_mode` 等多字段叠床）。

### 6 档定义

| `exploration_mode` | 类型 | 人话 | 起手档 | 实验目标 | goal 硬停 | 撞墙处理 |
|---|---|---|---|---|---|---|
| `careful` | 显式 | 啥都不动，照手册做 | A 标量 | optimize | ✅ 达标即停 | reflect 建议 |
| `optimize` ⭐ | 显式 | 参考下同行，标准干活 | A 标量 | optimize | ✅ 达标即停 | reflect 建议 |
| `innovate` | 显式 | 撞墙，翻同行代码 | B 结构 | innovate | ✅ 达标即停 | reflect 建议 |
| `aggressive` | 显式 | 论文+文档+实现+生态全查 | D 数据 | innovate | ✅ 达标即停 | reflect 建议 |
| `explore` | 显式 | 啥都试，不被指标卡 | B 结构 | explore | ❌ 不停 | reflect 建议 |
| **`auto`** | **auto** | **放手** | 跟随档 | 跟随档 | 跟随档 | **系统写 yaml 升档** |

### 3 源联动（每档跟外源深度自动联动）

| `exploration_mode` | paper | docs | github_impl | github_ecosystem |
|---|---|---|---|---|
| `careful` | P0 | D0 | False | False |
| `optimize` | P1 | D1 | False | **True** |
| `innovate` | P2 | D2 | **True** | True |
| `aggressive` | P3 | D3 | True | True |
| `explore` | P2 | D2 | True | True |
| `auto` | 跟随档 | 跟随档 | 跟随档 | 跟随档 |

### 用户 override 优先

设/改档走 **`/auto-nn-goal mode`** → `set_experiment_mode` / `apply_mode`（**只写**顶层 `exploration_mode`；bundle 在读时由 `resolve_exploration` 从 preset 派生）。yaml 显式叶字段（`keep` / `reflect` / `external` / `early_stop` / `goal` 段）经 deep-merge **用户优先**；例如显式 `external.paper_depth=P3` 在切到 `optimize` 后仍 = P3。`auto` 时实际生效档 = `auto.effective_mode`（见 §7.2.1b）。

## 6. 实验循环

每轮只做一轮（单槽或多槽汇总后视为一轮）：

1. 读 **`HUMAN_GUIDANCE.md`**（**公平约束** 若有 → **`## 路线图`**；空路线图则阶段全自主）→ **`references/REFLECT_INDEX.md`**（若有待消费 pending）→ `contract/`、`_runs/results.tsv`、`saved/experiment_journal.json`（若有）、`EXPERIENCE.md`；若已有上一轮汇总则读 `_runs/round_decision.json`

   **基线尺子 discovery (BAS + O3-baseline-anchors)**：立尺轮用 `baseline_tag` 标记；写入权见下表。PDH 6 原则仍适用（推 plain_recipe、写 plain_anchor_value / plain_why 等）。测试条件未对齐时**禁止**把异协议论文分写入 `reference_anchor_value`。**不阻塞业务仓**（启发式，非硬约束，可跳过）。详见 `auto-nn-run.sh` base-prompt step 0c。

   **`baseline_tag` 写入权（2026-07-24）：**
   | 通道 | plain | reference |
   |------|-------|-----------|
   | auto-run | 先检索 TSV；有则禁止再写；无则可做至多 1 轮 | 前 10 轮不主动写；满 10 轮仍无标签则本轮必做（`### reference-anchor-init`），立上为止 |
   | `/auto-nn-plain` / `/auto-nn-reference` | 人确认后写（已有则问换不换） | 同左；满 10 轮自动触发可不确认 |
   | manual-run | 仅用户明确要求 | 仅用户明确要求 |
   | 默认 / `--from-template` | `none` | `none` |

   **文献尺本机原仓校准（2026-08-26）：** `--source literature` 且找得到原仓库时，须本机用原入口跑出校准分，再与本仓复现分比对（容差同审查 `repro_tolerance`）；超差或校准未完成 → **禁止贴**。尺子锚值 = 本仓复现分，不是论文分、不是校准分。`--source ledger_midpoint` 不走此门禁。满 10 轮 auto **不得**在未过线时把文献尺自动贴上。

   旧台账行不由模板 update 改写。

   **auto-run 起步**：开局检索 `_runs/results.tsv` 是否已有 `baseline_tag=plain`（当前场景）；有 → 禁止再写 plain，衍生轮须 `none`；无 → 可读 `saved/baseline_start_intent.json` 与 Run Context `plain-anchor-init`，跟 PDH 做至多 1 轮 plain。前 10 轮**禁止** auto 设 `baseline_tag=reference`；满 10 轮仍无公开对照 → 注入 `### reference-anchor-init`，本轮必做 `/auto-nn-reference`（文献尺须本机原仓校准过线才可贴；否则中点代用可自动贴）。立尺技能见 `/auto-nn-plain`、`/auto-nn-reference`。
2. 假设 → 改 train.py / workspace/
3. `git commit -am "experiment: ..."`（**训前代码** commit；可选：`export NN_NOTES="本轮单一变量摘要"` → 写入 TSV/JSONL 的 `notes` 列。**不能**替代步骤 10 台账 commit）
4. **训练**
   - 单槽（默认）：`(mkdir -p _runs/logs && CUDA_VISIBLE_DEVICES=X setsid poetry run python train.py > _runs/logs/run.log 2>&1 < /dev/null &) && echo PID=$!`（**`setsid` 让 train.py 走新 session**，免受 Ctrl+C / SIGTERM 时 agent bash 退出所发 SIGHUP 影响 —— 编排停了训练仍可继续跑。默认 `NN_PARALLEL_TOTAL=1` 时训末会自动 `finalize_round`，写入主台账与 `_runs/round_decision.json`）
   - **训练日志**：单槽、多槽、试跑对比**一律**在 **`_runs/logs/`**（见 `_runs/logs/README.md`）；**勿**在仓库根写 `run.log`、`run2.log` 等。
   - 多槽：各进程设置**相同**的 `NN_PARALLEL_TOTAL`、**互异**的 `NN_SLOT`、各自的 `CUDA_VISIBLE_DEVICES` 与 `NN_*` 超参；并行跑多个 `train.py`，**每槽都用 `setsid`**：`CUDA_VISIBLE_DEVICES=X NN_SLOT=Y NN_PARALLEL_TOTAL=N setsid poetry run python train.py > _runs/logs/run_slot${NN_SLOT}.log 2>&1 < /dev/null &`；**全部 slot 训完（且无 fail）后由 `wait-train.sh` 训末自动 `finalize-round`**（见 step 5），agent 常规轮无需再手动跑；失败 WARN 时手动补：  
     `poetry run python -m contract finalize-round <各 exp 目录> --repo-root .`
5. 读 `_runs/round_decision.json`（单槽训末、多槽 `wait-train.sh` 训末均**已自动** finalize；同 `exp_dir` 二次 finalize 会跳过已入账行（幂等），但仍应避免无谓重复调用。仅当 wait-train 报 auto-finalize WARN 时才手动 `finalize-round <dirs> --repo-root .` 补账）

   **撞墙 / 跨场景 / 怀疑 bug (WPL trigger)**：满足任一条件触发 — `plateau_streak ≥ agent.plateau_rounds` / `scenario_id` 切 / 当前轮 fancy 主指标 `< plain_anchor_value`。Agent 须重新推 plain 并三分支决策：
   - `plain < best` → fancy 空间有效但耗尽 → 升档（不在本协议范围，见 §7.5.1）
   - `plain ≈ best` → 撞 plain 墙 → 收手或换 baseline
   - `plain > best` → SBN 派生，fancy 有 bug，必 DISCARD 本轮并回退 plain 当 baseline

   **共享 PDH 6 原则（P1-P6）**：`P1 弱于 random` / `P2 朴素经济` / `P3 领域 worst sane baseline`(CL=ER/Naive/DER++、时序=last-value/AR(1)、分类=per-class prior/LR、回归=mean predictor、RL=random/heuristic、物理=naive dynamics) / `P4 一眼看可解释(<100 超参)` / `P5 plain_why 必写` / `P6 预算感知(plain_budget 必填)`。详见 `auto-nn-run.sh` base-prompt step 5 镜像段。
6. keep/discard（KEEP 规则语义见 §2.1；KEEP 流程见 §2.1 段尾；discard 流程见 step 7）
7. discard：`git checkout HEAD~1 -- train.py workspace/` → commit。**注意：** 此回滚**不**删除已 append 的 TSV/jsonl 行；步骤 9 仍须 commit 本轮台账。
8. 更新 `EXPERIENCE.md`；`_runs/results.tsv` / `_runs/results.jsonl` 已由 `finalize_round` 维护，勿手写重复追加
8a. **轮末漂移检测**：`auto-nn-run.sh` 收尾自动跑 `scripts/nn-doctor.sh` → 写 `_runs/doctor_reports/R{N}.log`（**不**阻断 batch）；仅汇总 FAIL/WARN。下轮 prompt 装配时 `auto-nn-run.sh` 注入 `## Doctor R{N-1} 漂移报告` 块（FAIL 行 + 修复指引），让 Agent 在每轮开头知道上轮哪儿坏
8b. **轮初 prompt 装配**：注入 Pluggability 原则块（设计自检；与 8a 并列，总是注入，非 FAIL 门禁）
9. **训后 commit（台账闭环，强制）** — `finalize_round` 与 EXPERIENCE 更新完成后，**必须**将下列有变更的路径纳入 git commit（可与 EXPERIENCE 同 commit，或独立 `ledger:` 前缀）：
    - `_runs/results.tsv`、`_runs/results.jsonl`
    - `_runs/round_decision.json`（若本轮产生/更新）
    - `EXPERIENCE.md`
    - `saved/keepers.json`（若 KEEP 导致更新；`git add -f`）
    - `saved/experiment_journal.json`（若 `journal_append --event round --apply` 已写；`git add -f`）

    示例：`git add _runs/results.tsv _runs/results.jsonl _runs/round_decision.json EXPERIENCE.md && git add -f saved/experiment_journal.json saved/keepers.json && git commit -m "ledger: …"`

    **`finalize_round` 写入磁盘 ≠ git 持久化**；未 commit 的台账行可能在 `regen` / `checkout` 中丢失。

## 7. 自动化运行

### 7.1 与迁移完成的分界

| 阶段 | 命令 | 含义 |
|------|------|------|
| **迁移完成** | `bash scripts/verify-migration-complete.sh` + `bash scripts/smoke-check.sh` | 结构/契约验收 + **单槽短训**（`NN_SMOKE=1`）；**不是** auto-run |
| **迁后探索** | `./auto-nn-run.sh N` | 人**显式**启动；smoke **不会**自动接上 automation |

迁后口径合同见 **`.auto-nn/migration-summary.md`**（HARD-GATE / F1-contract 定稿；迁移留档，运行时不读）；场景权威见 `README` 的 `SCENARIO_POLICY`（实现块 `D2_DATA_SPLIT` 等同在 README）。

### 7.2 业务仓更新（/auto-nn-update）

业务仓主动拉模板更新（治理脚本 + experiment.py + profiles + CLAUDE/PROTOCOL）：

1. 前提：模板仓 auto-nn-experiment 先 `git pull`（业务用户或维护者拉到最新）。
2. `/auto-nn-update`（或手跑 `bash scripts/governance-sync.sh`——自发现 template-root/project-root，无参）。已有 `_runs/results.tsv` 时 **governance-sync 末自动** `regen_results_tsv.py --sync-jsonl`（对齐 overlay 列如 `untrained` / `exploration_space`，避免升版后表头顺序与 contract 不一致）。
3. `verify-migration-complete.sh` + `nn-doctor.sh` 确认 governance-rev 对齐、0 FAIL。
4. `git add -A && git commit -m "sync: 拉模板更新"`。

不动 train.py/workspace/contract（业务自有）。

**模板更新机制**：模板仓 `git push` 即收尾;**业务仓** Agent 跑 `/auto-nn-update`(触发 `governance-sync.sh` 单仓对齐)自助拉取。模板仓不维护业务仓登记、不批量下发。

### 7.2 命令与轮次含义

| 命令 | 含义 |
|------|------|
| `./auto-nn-run.sh N` | **N = 实验轮**；每轮执行 §6 全流程（改 `train.py`/`workspace` → train → finalize → KEEP/discard） |
| `./auto-nn-run.sh reflect` | **仅反思**（调用 `reflect.py`；更新 `EXPERIENCE.md`、`REFLECT_INDEX`、`references/auto/`）；**不计入** N |
| `./auto-nn-run.sh N reflect` | N 个实验轮；**每实验轮结束后按 §7.6 门禁**决定是否 reflect（reflect 不占实验配额） |

### 7.2.1 goal 与 loop 停止条件（达标即停，v4 schema）

- **goal 配置**（`nn-config.yaml` → `goal` 段；init **块 G2** 或 **`/auto-nn-goal`**）：
  - **`goal.target`**：全局默认目标；未在 `goal.per_scenario` 单独写的场景**继承**此值。值可为 `null`（presence 字段仍在；视作「设了但未达」而非「未设」）。
  - **`goal.per_scenario`**：按场景覆盖（如 `{"128b": 0.75}`）；键 = `scenario_id`，值 = 目标值；值 **`null`** = 该场景**豁免** goal。
  - **`goal.policy`**：`focus`（默认，只盯 `scenario_default` 停批）| `strict`（`scenario_active` 或场景清单里**有有效 goal** 的全达标才停）。
  - 设/改走 **`scripts/manage_goal.py`**（技能 `/auto-nn-goal` 封装）；常规迭代 Agent **勿**手改 yaml。
- **loop 停止**（`auto-nn-run.sh`）：每轮结束后跑 `scripts/check_goal.py`（exit `0`=达标 [`GOAL_MET` / `GOAL_MET_ALL`] / `1`=未达 / `2`=未配 goal 或 explore 跳过）。
  - **optimize / innovate 且已设有效 goal**：**达标**（exit 0）→ **提前停止**（不跑满 N；N 轮为底底网 / 兜底）。
  - **未配有效 goal**（exit 2，`NO_GOAL`）→ 跑满 N（兼容旧行为：仅 `goal.target`、无 map、默认 `focus` 与 v1 一致）。
  - **explore 有效**（exit 2，`GOAL_SKIPPED_EXPLORE`）→ **不**因 goal 提前停，跑满 N（见下条）。
- **可选字段（v2.5.4 yaml 显式优先 + contract 校验；用户手改持久）**：`goal.metric`（默认 = `contract.metric_key`，yaml 写了优先用，并校验 ∈ `contract.METRIC_KEYS ∪ AUXILIARY_KEYS` 白名单）、`goal.op`（`>=` / `<=`，默认按 `metric_direction` 反推，yaml 写了优先用）。`save_nn_config` 写盘前 fail-fast：op 非法 / metric 不在白名单 → `ValueError`；direction 与 op 矛盾 → `warnings.warn`（不阻断）。`migrate_goal_schema` 不再主动 pop yaml.metric/op——**用户在 yaml 显式写的值必持久**，存量仓 yaml 没写 metric/op 的继续 fallback contract（行为零变化）。
- **感知**（goal 是否到、当前 vs 目标）：
  - `/auto-nn-analyse` 的 goal 行；多场景时 **goal matrix** 块。
  - `/auto-nn-goal show`（`check_goal.py`）/ `show --all`（全场景矩阵）。
  - Run Context **`goal progress`** + 可选 **`goal matrix`**。
  - `nn-doctor` 的 **`goal_status`** 行（INFO/PASS；未设 → INFO 提示「loop 跑满 N」）。
- **探索期与 goal 硬停**：`resolve_exploration().skip_goal_stop` 为真（即 resolved 档 = `explore`）时，`check_goal.py` 输出 `GOAL_SKIPPED_EXPLORE`（exit 2），**不**因已设 `goal.target` 提前停 loop；仍跑满 N。设/改探索档走 **`/auto-nn-goal mode`** → `set_experiment_mode`（写顶层 `exploration_mode`）。
- **指标底线护栏（explore 专用）**：可选 `agent.explore.metric_floor`；轮末 `check_metric_floor.py` / `nn-doctor` **`metric_floor_status`** 破线 → **WARN**（Run Context 一行），**不** DISCARD、**不** break loop。
- **探索期 TAM 预写**：训末 `should_keep` 前 `upsert_finalize_tam_row` 写入当周 `saved/tier_attestation.json` 片段（供 `explore:attested_novel` 同轮读取）；reflect Phase 0.6 仍全量重建 TAM。
- **探索档（`exploration_mode` 单旋钮）**：用户面唯一旋钮是顶层 **`exploration_mode`**（6 档：careful / optimize / innovate / aggressive / explore / auto；见 §5.1）。设/改走 **`/auto-nn-goal mode`** → `set_experiment_mode`（显式档经 `apply_mode` 只写 `exploration_mode`；`auto` 经 `initialize_auto` 写 `auto` 段 + `exploration_mode: auto`）。运行时读路径：**`resolve_exploration()`** → `resolved_mode` / **`skip_goal_stop`** / **`innovate_prompt_boost`** / keep·reflect·external 等 bundle；`check_goal.py` 以 `skip_goal_stop` 判 explore 跳过硬停；doctor **`experiment_mode_status`** 展示同结构。`auto` 时 `resolved_mode = auto.effective_mode`。旧 API（`effective_experiment_mode` / `sync_agent_experiment_mode` / 顶层 `mode` / `agent.experiment_mode` 主路径）**已退役**，勿再写。

#### `keep.primary_delta_rel`（取代 `keep.primary_delta`）

相对值字段（`best × (1 + delta)`），不是 best + delta。与 §2.1 默认 KEEP 叙事一致。

| 起始 (best) | delta=0.005 | delta=0.01 |
|---|---|---|
| 0.5 (50%) | ≥ 0.5025 | ≥ 0.505 |
| 0.6 (60%) | ≥ 0.603 | ≥ 0.606 |
| 0.9 (90%) | ≥ 0.9045 | ≥ 0.909 |
| 0.95 (95%) | ≥ 0.95475 | ≥ 0.9595 |

**重要**：60% + 0.01 = 60.6%（不是 61%）。老 `primary_delta` 字段作 derived read-only，向后兼容（优先级见 `experiment_mode._resolve_keep_delta`）。

### 7.2.1b auto 档撞墙升档

`exploration_mode: auto` 是元模式：用户说"我放手"，系统撞墙自动升档。

| 配置 | 默认 | 含义 |
|---|---|---|
| `auto.start_mode` | `optimize` | auto 起步档 |
| `auto.promote_threshold` | `5` 轮 | 撞墙多少轮触发升档 |
| `auto.max_mode` | `aggressive` | 升档最高档（到 aggressive 停止）|
| `auto.effective_mode` | 跟随档 | 当前生效档；`resolve_exploration().resolved_mode` 取此值（旋钮仍为 `exploration_mode: auto`）|
| `auto.wall_hit_streak` | 0 | 撞墙连续 KEEP 失败轮数（`finalize_round` 写）|

**升档链**：`optimize → innovate → aggressive`（不含 explore，哲学冲突）
**aggressive 撞墙 → 不退**。
**旋钮保持 `exploration_mode: auto`**；当前跟随档写在 `auto.effective_mode`（如 `innovate`），不把顶层旋钮改写成显式档名。

### 撞墙处理双路径

- **5 显式档**：撞墙 → reflect 写建议到 `references/auto/`，**不动 yaml**
- **auto 档**：撞墙 → 系统写 yaml 升档（更新 `auto.effective_mode`）

用户改 `exploration_mode: <5 显式之一>` → 离开 auto。

### 7.2.1a v3 goal_spec（多 metric × 多 scenario 复合门槛）

**快速示例**：

```yaml
agent:
  goal_spec:
    combine: per_scenario_all_of
    predicates:
      - {metric: acc,  scenario: 128b, op: '>=', value: 0.90}
      - {metric: ssim, scenario: 128b, op: '>=', value: 0.85}
      - {metric: acc,  scenario: 256b, op: '>=', value: 0.92}
```

**关键规则**：

- **`agent.goal_spec` 存在时优先走 v3 路径**（与 `check_goal.py` / `parse_goal_spec(agent)` 一致）；此时单值 v4 字段（`goal.target` / `goal.per_scenario` / `goal.policy`）全部被忽略
- 评估 = 每 scenario 内的所有谓词 AND；全场景都过才停
- 退出码契约与单值字段一致：0=met / 1=pending / 2=NO_GOAL or SKIPPED_EXPLORE
- **`validate_goal_spec` 失败**（非法 metric / scenario 等）→ stderr **ERROR** + **exit 2**（与 `NO_GOAL` / `GOAL_SKIPPED_EXPLORE` 同档，不伪造成功）
- 数据源 = 各 scenario 的 best 历史行（与单值字段一致）
- metric 引用白名单：`contract.metric_key` ∪ `contract.auxiliary_keys`
- 不支持嵌套 boolean / 代数 / 时间窗口

**迁移**：旧 v2 字段（`agent.goal_value` / `agent.scenario_goals` / `agent.goal_stop_mode`）走 `migrate_goal_schema.py` 自动迁移到 v4 `goal.*` 段；v3 复合门槛现行读者为 **`agent.goal_spec`**（不在 `goal.spec`）。

### 7.3 迁后约束（常规 auto-run）

- **不得**设置 `NN_RELAUNCH`（禁止改 `contract/`、`experiment.py`）；改口径须停 automation，走再迁移 / 重签 F1。
- **训前守门**：每轮 `train.py` 自动跑 §3.0.1 静态守门。G-契约 / G-框架 / G-治理文档 若三源 diff 命中破坏路径且未设 `NN_RELAUNCH`，preflight **FAIL** 并退出；`nn-doctor` **`immutable_path_guard`** 同步 FAIL。常规轮勿用 `NN_RELAUNCH` 或 `NN_GUARD_*=0` 绕过。
- **轮末检查**（`auto-nn-run.sh`）：仅警告本轮 commit 是否包含 `EXPERIENCE.md`；**不**再查 contract/experiment diff（训前 preflight 已覆盖）。
- **墙钟（训练进程）**：以 `nn-config.yaml` 的 `time_budget` 为准（HARD-GATE O1）；`0` = 关闭训练墙钟；Agent **勿**改 `nn-config.yaml`。秒表在 `train.py` 数据加载与建模型之后按下，**不含** Agent 改代码 / 反思 / 等待训练。看表只在「下一步开始前」：外层下一轮开始前，以及本地逐步训练路径上每次 `optimizer.step()` 入口（同一只秒表、满预算即停）。到点不再开下一步，已经开始的那一次更新允许做完；停因 `time_budget`，走与早停相同的收尾入账（官方分 → 成绩表），半截轮不更新训内最好快照。**已知限制**：框架自带训练循环、子进程训练、完全不走 `torch.optim.Optimizer.step` 的手写更新，本版不保证步内停。`wait-train.sh` 到点只退出等待、不杀训练进程。
- **墙钟（整轮 Agent）**：编排日志里某一轮 SUCCESS 的上千秒是改代码 + 训练 + 反思的墙钟，与 `time_budget` 不是一回事。
- **单槽 / 多 slot**：**默认并行**（`≥2 独立候选 ∧ max_parallel≥2` → 并行 `min(max_parallel,候选数)` 槽）；串行（单槽）须理由（候选有依赖 / C-D 深单变量 / 结构大改 / E 预研 / max_parallel=1）。**迁后前几轮单槽验证链路**仍为正当串行情形。**OVAT ≠ 串行**（每槽单变量，多独立候选应并行）；**slot 与 GPU 解耦**（单卡可多 slot 共享同卡，受显存约束）；仅「已穷尽档∧plateau」禁同变量 grid。档位是否穷尽以 EXPERIENCE `## Tier 状态` **二维矩阵**（具体格子）为准（并行批次任一槽 KEEP 重置 plateau 计数）。本节为 auto-run 与 manual-run **两条路径共享权威**。
- **等待训练**：后台起训后**必须**调用 `./scripts/wait-train.sh`（见 `auto-nn-run.sh` prompt）；`time_budget=0` 时 wait 不因 MAX_WAIT 误杀。

### 7.3.1 Agent 行为配置（`agent.*`）

`nn-config.yaml` 的 `agent.*` 段是**业务仓级** Agent 行为配置，常规迭代 Agent 勿改；`/auto-nn-modify` 之外仅下列场景可改：

- `context.injection: full|off`（旧 `agent.run_context_injection`）— 关闭 RUN CONTEXT 注入（调试用；常规迭代保持 `full`）
- `context.recent_rows`（旧 `agent.run_context_recent_rows`）— Run Context 近窗 TSV 行数（默认 5，范围 1–10；事实陈述，非 stage 标签）
- **`context.language`**（旧 `agent.language`）— Agent 回答语种。注入到 RUN CONTEXT 顶部作为行为提示；不影响模板脚本 stderr / `HUMAN_GUIDANCE.md` / 台账列名。常用值 `"中文"` / `"English"` / `"日本語"`；`auto` 或空 = 不提示（默认）。设值后下一次 auto-run 轮即生效，无需重启
- `goal.*`（旧 `agent.goal_*`）— 设/改/查/清走技能 `/auto-nn-goal`，勿手改 yaml
- **Tier 起手档**（**非**顶层 `exploration_mode` 旋钮）：由 `resolve_exploration().tier_start` 读时从当前 `exploration_mode` 档 bundle 派生（见 §5.1「起手档」列；如 `careful`/`optimize`→A、`innovate`→B、`aggressive`→D）。设/改实验模式走 **`/auto-nn-goal mode`** → 写顶层 `exploration_mode`。**勿**写已退役的 `exploration.mode` / `agent.experiment_mode` / `exploration.style`。撞墙升 Tier 由 EXPERIENCE `## Tier 状态` + reflect 驱动；`aggressive`/`innovate` 档还联动 reflect router 外源深度（见 §7.6）

其他 `agent.*` 字段（`reflect_*` / `analyse_*` / `experience_auto_compress` 等）属模板内部参数，常规迭代不读不改。

### 7.4 日志与跟进度

编排日志：**`_runs/agent/`**（批次 `*_batch.log`、`*_agent-round-N.log`、stream-json 等）。  
训练 stdout：**`_runs/logs/run.log`**（单槽）或 `_runs/logs/run_slot*.log`（多槽）。

```bash
tail -f _runs/logs/run.log
tail -f _runs/agent/*_agent-round-1_stream.jsonl   # 按实际文件名
```

操作速查见根目录 **`CLAUDE.md`**（命令与架构边界）。

**Run Context 扩展段（`build-run-context.py` 注入，纯提示 / 不阻塞）：**

- **`### ablation-hint`**：当上轮 `round_decision` 为 **KEEP** 且 reason 标明相对历史**严格**改善（含「提升满足阈值」/「严格改善」/「↑」）时注入，建议下一步做组件归因消融（OVAT 单变量对照）。**`near_best_abs` 触发的 KEEP**（reason 仅「接近最佳」、无严格改善标记）**不**注入。启发式，非门禁。
- **`## 基线靶子 (baseline anchors)`**：公告栏**稳定段**（每轮恒注入，非条件触发）。三行：plain（自跑朴素基线，下界）/ reference（外部已发表公开最优或本仓 `baseline_tag=reference` 对照，上界；novel 任务常无，留空即常态）/ 当前最佳 + 差值（正=已超 plain）。plain 来自 `saved/plain_anchor.json` 或 EXPERIENCE Tier P 行；reference 来自 EXPERIENCE「基线锚点」段 `reference_anchor_value`（须与 OFFICIAL_TEST / 主指标**条件对齐**；命名铁律：外部锚点叫 reference，仓内历史最佳才叫 SOTA）。init 起步意图见 `saved/baseline_start_intent.json`（O3-baseline-anchors）。**`baseline_tag` 写入权**见 §6 step 1 表（auto 检索 plain；公开对照满 10 轮仍无则必做）。纯提示 / 不阻塞。

### 7.4a 数值分析段（MA-* Metric Analysis）

auto-run 每轮向 agent prompt 注入一段**数值快照**，**纯只读 / 不阻塞**。约定：

- **MA-1 brief-oneline**（`build-run-context.py` 注入 `### MA-1 brief-oneline`）
  一行格式：`leader=<exp> <metric>=<v> | last=<exp> <metric>=<v> Δ%=<pct> | plateau=<streak>/<round>`
  - `leader`：本场景历史最佳（focus 场景优先；无 exp_dir 回落 cross-scenario best）
  - `last`：本轮收尾指标 + 相对 leader 的 Δ%
  - `plateau`：连续未刷新 leader 的轮数 / 阈值（见 `nn-config.yaml` `agent.plateau_rounds`）
  - 实现：`scripts/lib/metric_analysis.py:format_ma1_brief_oneline`（L458-490）
  - 业务仓可忽略（数值事实，非指令）

- **MA-2~MA-7**（完整报告）：`scripts/analyse_metrics.py` 按需触发（quiet 模式默认仅 MA-1 + **基线尺子**节：plain/reference 有无与补尺建议）
  - MA-3 = 增量；MA-7 = plateau；MA-R = reflect 建议验证；其余按需
  - 详见 `scripts/lib/metric_analysis.py` 各 `section_ma*` 函数

**约定**：
- MA-* 段**不**复写 PROTOCOL §2 指标定义；只对当前指标值做事实陈述
- 与 keep/discard（§6 step 6）解耦：MA-1 报告 leader 是历史最佳，**≠** keeper（见 §6 step 7 KEEP 段）
- 不写 `_runs/results.tsv` / `_runs/results.jsonl`；台账闭合路径不变

### 7.5 人类路线图（HUMAN_GUIDANCE.md）

- **意图归人、代写落盘**：战略意图由人提出；经 **`/auto-nn-human-guidance`** 代写并写入本文件（validate + commit）。常规 auto-run / manual-run **实验 Agent 不得**修改本文件。
- **`## 公平约束`**（可选，与路线图**并列**）：跨阶段比较口径与禁止项；长文外置 `docs/`。**不是**阶段内字段。**代写硬规则**：用户说什么只写什么，禁止用模板默认补全未点名条款。
- **`## 路线图`**：分阶段 **是什么 / 目标 / 完成条件**；可选极短 **NOTE**。
- **空路线图**（无 `### 阶段`）= Agent **全自主**（依 EXPERIENCE / Tier / `exploration_mode` + `resolve_exploration().tier_start`）。
- **优先级**：高于 `REFLECT_INDEX` pending；**公平约束**（若有）约束比较口径；当前阶段以路线图 **NOTE**（含 Tier）为阶段硬约束，EXPERIENCE `## Tier 状态`（二维矩阵）为软参考。
- **探索期（`objective_mode: explore`）**：NOTE 内 `- **objective**: explore` 与探索网格 / 场景顺序 / 证伪清单 / 禁止项为**首要信息源**，高于 REFLECT pending 与 Run Context coverage brief。keeper 为探索链锚点（K1），**≠** metric_leader。Modify-Scenario-complete 须停 auto-run（见技能 `/auto-nn-modify`）。
- **送达方式**（`auto-nn-run.sh`）：注入 **`## 公平约束`**（若有正文）+ 非空 **`## 路线图`** 全文 + `summarize-runs --roadmap-status`；并要求 `Read HUMAN_GUIDANCE.md`。
- **阶段推进**：由台账 + 固定完成启发式（KEEP / plateau）推断；**不必**改文件切换阶段。
- **reflect** 不在本文件控制（见 §7.6、`nn-config`）。
- 清空路线图：`bash scripts/clear-human-guidance-roadmap.sh --apply`（技能 `/auto-nn-human-guidance`）。

#### 7.5.1 探索梯度（Tier A–E）

**Tier 语义权威在本节。** 逐档是否已试、代表 experiment、证伪备注见 `EXPERIENCE.md` 的 **`## Tier 状态`** 表（Agent 每轮必更新）。

> **Tier = 本轮相对 keeper 的语义改动深度**，不是超参个数，也不是 experiment 名里的前缀。起手档见 `resolve_exploration().tier_start`（由顶层 `exploration_mode` 档 bundle 派生；§5.1）。

**路径映射（代码 → Tier）：**

| 改动区域 | Tier |
|----------|------|
| `train.py` 标量、`NN_*` env、scheduler、更长训练 | **A** |
| `workspace/` 模型结构、backbone、算子、容量 | **B** |
| `workspace/` loss、reward、正则、物理项进目标 | **C** |
| `workspace/` 或数据管线：课程、增广、采样、buffer 构造 | **D** |
| `contract/` 主指标、official test、KEEP 口径 | **E** |

**Tier 一行定义：**

| Tier | 改什么 |
|------|--------|
| **A** | 标量与日程：LR、epochs、scheduler、RL 的 ent_coef、单个 offline ratio 等 |
| **B** | 模型与表示：网络结构、容量、head、encoder |
| **C** | **优化目标**：loss 项、reward 加权、正则、物理项进目标（改 `workspace` 内目标逻辑） |
| **D** | **数据与任务分布**：课程、增广、采样权重、buffer 构造（改分布逻辑，非仅一个 ratio 标量） |
| **E** | **问题与评估**：主指标定义、场景划分、KEEP 口径（须 `NN_RELAUNCH` + 人审；**不是**更长训练或 OOM 技巧） |

**合格 / 反例（防假升档，通用）：**

| Tier | 合格（满足其一） | 反例（不算该档 / 记假升档） |
|------|------------------|---------------------------|
| A | 改 `train.py` 顶部常量或 `NN_*` env 标量 | 换 RL 算法库但 reward 公式不变 → 可记 **C-算法（目标未动）** |
| B | 改 `workspace` 模型结构（net_arch、hidden 等） | 只改 batch size（A） |
| C | 改 `workspace` 的 loss/reward/正则/物理残差权重 | 仅改 `NN_OFFLINE_TARGET_RATIO`；experiment 名写 TierC 但无代码路径 |
| D | 改课程 stage、增广、采样、buffer 构造等**逻辑** | 仅改一个 ratio → **D-浅**；连续 2 轮仅 D-浅 → 下轮须 **D-深** |
| E | 改 `contract` 指标或评估/task 定义 | 更长训练、grad accum、破 OOM（归 A 或 D-工程，**不是 E**） |

**跨范式举例（不绑具体课题 / run 名）：**

| 范式 | A | B | C | D | E |
|------|---|---|---|---|---|
| 监督 | lr、epochs | ResNet→ViT | focal、类权重 | Mixup、课程采样 | 换 primary / 划分 |
| RL | timesteps、LR | policy net_arch | reward shaping、分项权重 | curriculum、demo mix | 换 eval 聚合 |
| 物理/PINN | Adam lr | 网络深度 | PDE 残差权重 | collocation 采样 | 换验证场/误差定义 |

**B vs E（任务不变）：** **E = 改题**（动 `contract/`：主指标、official test、KEEP 口径）；**B = 改表示**（动 `workspace` 模型/backbone，任务不变）。

```text
1. 改 contract 的 metric / test / KEEP？ → E（须 NN_RELAUNCH + 人审）
2. 主要改 build_model / backbone / 算子？ → B
3. 主要改 loss / reward / 正则 / 物理项？ → C
4. 主要改采样 / 课程 / buffer？ → D
5. 否则 → A（或拆多轮）
```

**语义归类示例（非项目 run 名）：**

| 改动类型 | Tier |
|----------|------|
| 换 backbone/算子，仍优化同一主指标 | **B** |
| MSE → Huber/L1/Charbonnier | **C** |
| 加小 λ 软 PDE 残差 | **C** |
| 改 collocation / 课程采样逻辑 | **D** |
| 改主指标定义或 official test 规则 | **E** |

**每轮 EXPERIENCE 必填（结构化）：** `tier_this_round` / `tier_change` / `tier_verdict`，并更新 **`## Tier 状态`** 对应行。

- **假升档**：experiment 名含 `TierC` 但只改 `NN_*` 或 `train.py` 常量 → EXPERIENCE `## Tier 状态`（二维矩阵）记 **假升档**，不得声称「已试 C」。
- **撞墙**：`agent.plateau_rounds` 触发且当前**具体格子**在 EXPERIENCE `## Tier 状态`（二维矩阵）标 **已穷尽** → 考虑同档下一深度或升下一未试档；`resolve_exploration().tier_start` 仅决定**起手**档（A–D），不锁定终身只调 A。`aggressive`/`innovate` 档 reflect router 联动更深外源检索（绕过 beat_best 短路；见 §5.1 外源表）。
- Reflect / 文献 **禁止**把 Koopman、FNO、DeepONet 等 backbone 或 neural operator 默认标 **E**；应映射 **B**（`workspace` 模型）、**C**（目标）、**D**（分布）。**Tier E 仅当**明确建议改 `contract` 的 metric、official test 或 KEEP 口径。
- **C/B 穷尽 ≠ E 穷尽**；升档建议 **A→B→C→D→E**，勿跳过 B 直接文献 E。
- `tier_this_round` 须与 `tier_change` 路径一致：`workspace/.../model`→B，`loss`/reward→C，`contract/`→E；更长训练/OOM 归 A 或 D-工程，**不是 E**。**常规 auto-run 轮 `tier_this_round` 不得为 E**（人审 relaunch 轮可记 E）。

**E 闸门（自动化）：** 探索面 **A–D**；**E = 改宪法**，常规轮 **不实施**。

| 区域 | Tier | auto-run |
|------|------|----------|
| 自主区 | A–D | 可改 `train.py` + `workspace/` |
| 宪法区 | E | **禁止** Agent 设 `NN_RELAUNCH` 或改 `contract/`；须停 automation → 人审 → relaunch |

**仅当下面任一成立才记 / 提议 Tier E**（ledger 与旧 run 可能不可比）：

1. 改 `METRIC_KEY` 或主指标定义/方向  
2. 改 `contract.test` / 官方 test / F1 锁定的 `TEST_USES`、场景划分  
3. 改 `improve_mode` 或 KEEP 池使历史 SOTA 不可比（改 `primary_delta_rel` 只影响 KEEP 判定，不破坏历史可比性）  
4. 立项级换题（问题陈述与 F1 不一致）

**不算 E**（仍在 A–D）：换模型 **B**、改 loss/辅助任务 **C**、改采样 **D**、更长训练 **A**；多记 `AUX_METRICS` 但 KEEP 仍盯原主指标 → **不是 E**。

**Agent 行为**：`tier_this_round` 不得为 E；reflect 可写「E 待办 / 阈值提议」，不得在本轮改 `contract/`。`HUMAN_GUIDANCE` 若允许 E，须写明停 auto-run + `NN_RELAUNCH=1`（人设置）。

**Agent 读 Tier 顺序：** `EXPERIENCE.md` 的 `## 精华摘要`（若有）→ **`## Tier 状态`** → `## 近期实验`；争议升档 / 假升档时再 Read 本节全文（不默认通读 PROTOCOL 其它章）。

#### 7.5.1a 创新维（routine / extend / novel）—— Tier × 深度 二维矩阵

**§7.5.1 是 Tier 的"覆盖维"**（哪几档被代码/config 实际举证；TAM 负责记录）；**§7.5.1a 是 Tier 的"深度维"**（每档内部的实现深度）。两者正交：TAM 说"B 已 att"≠B 已穷尽；只有 routine + extend + novel 三档都标"已穷尽"，B 档才算整体穷尽。

| 深度 | 含义 | 典型例子 |
|------|------|----------|
| **routine** | 经典现成实现 | `torchvision.resnet50` / `nn.CrossEntropyLoss` / `kornia.augmentations.RandomCrop` |
| **extend** | 论文级 / 成熟组合（已发表 SOTA 或公开复现） | 按 FNO 论文复现 / 两阶段 detector（已知 loss 组合）/ 主流课程学习配方 |
| **novel** | 研究性新结构 / 新目标形式（无现成论文背书） | 自研 physics fusion block / 自定义 multi-task 平衡权重 / 全新采样策略 |

**为什么需要这一维：** 仅靠 TAM 的 "B:att×n" 易误判"B 已穷尽"——agent 可能只跑过 routine（torch 经典），extend/novel 未试就直接升 C，结果丢探索空间。

**EXPERIENCE `## Tier 状态` 矩阵（5×3）**：

| Tier \\ Depth | routine | extend | novel |
|--------------|---------|--------|-------|
| **A 标量日程** | 已浅尝 / 已穷尽 | … | … |
| **B 表示容量** | … | … | … |
| **C 优化目标** | … | … | … |
| **D 数据分布** | … | … | … |
| **E 改题/评估** | （常规 auto-run 不得 E） | … | … |

**升档规则（修订版）**：

1. 升档前先看矩阵：当前 Tier × Depth 单元是 routine→升级到 extend；extend→再考虑 novel；3 单元全"已穷尽"才升下一 Tier 字母。
2. **B-routine 已穷尽 ≠ B 整档穷尽**——这是 auto-run / reflect 误升 C 的常见根因；先看 B-extend / B-novel 是否已试。
3. **routine 段不需文献**（经典现成）；extend 段必须 reflect 查论文（已有 SOTA 背书）；novel 段需 record 自研动机 + 风险（无现成 baseline 可对）。
4. **Tie-break**：每个具体格子 cell ≤ 80 chars（避免 EXPERIENCE 漂长）。

**每轮必填字段**：

- `innovation_depth: routine | extend | novel`（本轮实现属哪一档）
- `innovation_rationale: <一句说明>`（用哪个具体实现 / 哪篇论文 / 哪段自研）

#### 7.5.2 EXPERIENCE 压缩（索引式 v2，近 5 轮）

冗长迭代叙述用 `scripts/compress-experience.py`（技能 `/auto-nn-compress`）收成精华并归档；**默认** `--preset standard`（C2 + EXP+REF-E，保留近 **5** 轮实验**要点**、近 **2** 条 `[反思]`）。

| 挡位 | 作用 |
|------|------|
| C0 | 只统计 EXPERIENCE 体积 |
| C1 | 规则去重（legacy 梯子 / 重复 Tier 表 / 相邻重复段） |
| C2 | C1 后：重写精华 + 信息索引 + Tier/场景表截断 + **全部可归档段**入 archive + **REFLECT_INDEX 历史摘要截断** |

**信息分层：** 数字 → TSV；反思 → `REFLECT_INDEX` → `references/auto/`；外部证据 → `saved/evidence_bundle.json`；远端叙事 → `references/experience/archive_*.md`。EXPERIENCE **只留决策摘要与指针**。

**永不压缩：** `_runs/results.tsv`、`results.jsonl`、`_runs/exp/*`、`HUMAN_GUIDANCE.md`、`REFLECT_INDEX`、`contract/`、`PROTOCOL.md`、`saved/` 外部证据。

**Agent 读法：** `## 精华摘要` → `## 信息索引` → `## Tier 状态` → `## 近期实验`（近 **5** 轮）；**默认不读** `archive_*` / `references/auto/` 全文，除非 INDEX 详文列或人点名。每轮 append ≤40 行；禁止正文 arxiv url。`REFLECT_INDEX` 历史「结果摘要」由程序截断 ≤240 字。

**auto-run 轮末（E1）：** `experience_auto_compress: after_round`（模板默认）→ 轮末自动 `compress-experience.py --apply`；**历史债务**（行数 ≥2×阈值、待归档段过多、或已有精华但 Tier/正文再次膨胀）**绕过冷却**立即再压。常规定期压缩仍受 `cooldown_rounds`（默认 2）约束。阈值见 `nn-config.yaml`；`NN_EXPERIENCE_AUTO_COMPRESS` 可覆盖。**业务仓无需手跑一次性 compress**；`/auto-nn-compress` 仅用于人主动 dry-run / 审阅效果。

#### 7.5.3 HUMAN 硬门禁（G-strict）

`auto-nn-run.sh` **批次启动**写 `saved/.human-guidance-baseline.json`（`HUMAN_GUIDANCE.md` 全文 sha256；reflect-only 不写）。**实验轮 train 前** `experiment.preflight_check` 执行 **G-HUMAN**：相对 baseline 有改动 → **RuntimeError**（`NN_GUARD_HUMAN_GUIDANCE=0` 可关）。

**人改路线图：** 停 `./auto-nn-run.sh` → **`/auto-nn-human-guidance`**（技能 Write + validate + commit）→ 重开 batch（新 baseline）。亦可人直接改文件后 commit，但仍推荐走技能以保证格式。**auto-run batch 活跃时禁止**运行 `scripts/refresh-human-guidance-baseline.sh`（及等价 `human_guidance_gate.py refresh`）；须先停 batch，再按需 `git checkout <baseline.git_head> -- HUMAN_GUIDANCE.md`（或备份恢复），使内容与 `saved/.human-guidance-baseline.json` 一致后重开。**勿**再在文档中采纳「同一 batch 内 refresh baseline 继续跑」的流程。

**G-HUMAN-COMMIT（轮末）：** 每实验轮收尾在 `journal_append` 之后调用 `human_guidance_gate.py post-round-enforce`。若检测到本轮 **commit** 或工作区改写 `HUMAN_GUIDANCE.md` 且 sha 与 baseline 不符，则从 baseline 恢复并生成修复 commit；batch log / agent log 可出现 `G-HUMAN-COMMIT_REVERT` / `G-HUMAN-WS_REVERT`。

**轮初双检：** auto-run 在 spawn Agent 前 `scripts/human_guidance_gate.py check`；drift 时 skip Agent（`agent.human_guidance_gate_fail_fast: true` 则整批 exit）。**实验轮** Agent **禁止** Write/Edit `HUMAN_GUIDANCE.md`（prompt + 路线图保护）；改路线图只经 **`/auto-nn-human-guidance`**。Prompt 另行禁止实验 Agent 调用 refresh baseline 脚本绕过门禁。

#### 7.5.4 Query 写作约束（Phase 1 reflect）

Phase 1 prompt 注入项目现状 + Query 规则；3 道校验（F1 overlap / 长度 ≤ 200 / 通用词密度 ≤ 30%）。
校验器：`scripts/lib/external/query_validator.py`；`lib/external/` 由 `governance-sync.sh` 整目录下发。

#### 7.5.5 Reflect Synthesis 综合推理

Phase 2.5 url 校验后、Phase 3 之前的合成阶段：跨证据 + 历史 → 下一步建议 + 推理链 + 为什么不照搬；4 硬约束全在 `lib/external/synthesis.py:parse_synthesis`。
失败 / `--skip-synthesis` → 逐字节回退现有。

### 7.6 反思门禁与结果消费

**何时运行 reflect（OR，由 shell 判定；详见维护仓 design spec）**

- **`reflect.force: true`**（旧 `agent.reflect_force`；或一次性 `NN_REFLECT_FORCE=1`）→ **R1** 强制 reflect（仍须 `reflect_interval > 0`）
- **`reflect.skip: true`**（旧 `agent.reflect_skip`；或 `NN_REFLECT_SKIP=1`）→ 跳过自动 reflect
- 连续 ≥ `agent.plateau_rounds` 轮无主指标改善
- 本轮 train 失败 / 无合法 `round_decision`
- 本轮 **DISCARD**（非重复噪声配置）
- EXPERIENCE 或 `saved/experiment_journal.json` entries 出现 Tier 穷尽类信号
- 距上次 reflect ≥ `reflect.interval`，且 TSV 自上次 reflect 后有新行
- **探索期（`effective_objective=explore` 且迁移未阻断）**：连续 ≥ `agent.explore.reflect_gate_coverage_stall` 轮无新 `scenario_id` / 无 explore 覆盖信号 → **R7 coverage_stall**

**实验模式与 reflect**：`optimize` / `innovate` 共用 R1–R6；**仅 explore** 额外 R7。`innovate` 无单独反思门禁，仅在实验轮 prompt 加强创新维（见 `auto-nn-run.sh`）。探索期 pending / `reflect_ack` 须服从 HUMAN NOTE 网格（NOTE **高于** REFLECT pending）。

**人工 override**：在 `nn-config.yaml` 的 `reflect.force` / `reflect.skip`（旧 `agent.reflect_force` / `reflect_skip`）；**不在** `HUMAN_GUIDANCE.md` 写 `reflect:`。

**`reflect_interval` 语义**：**上限频率**（最多每 N 轮实验**可** reflect 一次），**不是**每 N 轮必跑；`0` = 关闭自动 reflect（仍可 `reflect.py` 或 `./auto-nn-run.sh reflect` 手动）。

**跳过 reflect 时**：写 `_runs/agent/<ts>_reflect-skipped.log`；**不** append EXPERIENCE `[反思]`；**不**更新 `REFLECT_INDEX` pending。

**reflect 成功后**

- append EXPERIENCE `## [反思] …` 短块
- 长文写入 `references/auto/<ts>_auto_reflected.md`
- 更新 `references/REFLECT_INDEX.md` 的 **`## 待消费`**（**至多 1 条**：撞墙、**下轮建议**一行、Tier、详文路径）

**实验轮消费反思（有 pending 时）**

1. prompt **注入** pending 行 + 要求 `Read references/REFLECT_INDEX.md`
2. 本轮 `EXPERIENCE` 条目须含 **`reflect_ack:`**（采纳 / 推迟 / 与 guidance 冲突说明）
3. **程序门禁（auto-run）**：若轮初存在 pending，轮末 EXPERIENCE 最新块无有效 `reflect_ack:` → **不**调用 `mark-reflect-consumed.sh`；下轮 prompt 注入 WARN；batch 不中断
4. 实验轮结束后（ack 有效时）pending 移至 **`## 历史（已消费）`**（`auto-run` 或 `scripts/mark-reflect-consumed.sh`）

**优先级（实验假设）**

```text
HUMAN_GUIDANCE > REFLECT_INDEX pending > EXPERIENCE 教训 > references/auto 全文
```

> **路径上限覆盖（fork 触发，§11 ③）：** `HUMAN_GUIDANCE > manual 路径上限`（cell 级）。manual 标某格 `register`，但人在 `HUMAN_GUIDANCE.md` 写「这格必须 fork / 不许动」→ agent 无条件听人，覆盖 manual 那格的路径上限。主动覆盖，非被动审批；不新增 gate（复用轮首 `_check_human_guidance_gate`）。

无 pending 时：**不**通读 `references/auto/`；仅当 index 详文列或 `HUMAN_GUIDANCE` 点名路径时才 Read 对应文件。

**Reflect 证据包（REB，Phase 0.5）**

- `reflect.py` 在 Phase1 前调用 `scripts/lib/reflect_evidence.py`：组装 keeper ∪ recent ∪ flagged 的 exp 标准产物、日志信号、`code_snapshot` diff（与 `summarize-runs` brief/keeper/roadmap 同源）。
- 落盘：`saved/reflect_evidence.json`、`saved/reflect_evidence_gaps.json`、`saved/reflect_evidence.md`（截断注入 Phase1）。
- 缺口：**B+C** — EXPERIENCE append `## 证据缺口` + 机读 gaps JSON；profile 默认见 `profiles.yaml` → `reflect_diagnostics`；项目可增 `contract.reflect_diagnostic_manifest()`。
- Phase1 **硬约束**：无 snapshot diff 不得断言 Tier B/C/D 已试；无 L2 日志信号不得断言 OOM/NaN；gaps 非空须 fix-gap | defer | proceed。
- 配置：`nn-config.yaml` → `agent.reflect_evidence_*`（recent N、flagged、log tail、snapshot diff、**git log**）。
- **Git 更新**：各 run 的 `git_commit`（TSV / `env_snapshot.json`）→ `git log keeper..run -- train.py workspace/`（与 snapshot diff 同 scope）；无 git 仓或非 commit 则跳过。

**Tier Attestation Matrix（TAM，Phase 0.6）**

- `scripts/lib/tier_attestation.py`：对 ETS + 台账窗口行，用 **git/snapshot diff** 作 `evidence_tier`（权威），`description` 仅作 `claimed` 对照 → **false_claim** / **shallow** / **exhausted**。
- **路径**：`workspace/nn/`、`workspace/models/` → B；`workspace/objectives/` → C；`train.py` / `__init__.py` 为 **ambient**（有 B/C/D/E 实质变更时不单独计 A）；`__init__.py` 可按 diff 中 `register_learner` / `register_objective` 嗅探 B/C。
- **config.json Δ**：keeper vs run 的 `config.json` 键级 diff（`MODEL_ARCH`→B，`LOSS`/`FOCAL_*`→C，增广键→D，标量键→A）；与路径 evidence **并集**；行内 `evidence_config_keys` 列出变化键。
- **内容嗅探**：`train.py` / `__init__.py` 的 snapshot diff 文本（`LOSS`/`focal`/`bitempered`→C；`LR`/`EMA`→A；`register_learner`→B）；`workspace/nn/objectives/`→C。
- **rollup**：一行 run 的 `evidence_tiers` 中**每一档**各计一次 attested/shallow（共改不吞档）；`evidence_primary` 用于 verdict 行：claimed 最深档 ∈ evidence 时优先 claimed（OVAT 对齐）。
- 落盘：`saved/tier_attestation.json`、`saved/tier_attestation.md`；reflect pending 须含 `[TAM: …]`；**禁止**用 description 统计 Tier；**禁止**在 `not_attested` 存在时写「A–D 已试完」。
- 配置：`agent.tier_attestation_*`（window、exhaust_min_attempts、enabled）。

## 8. `_runs/results.tsv` 格式

**行语义**：**1 行 = 1 次实验（槽位）**，不是 1 轮编排。多槽并行时 `finalize_round` **一轮一次决策**（`round_decision` / keepers / wall_hit），**每个成功槽各追加一行**主 TSV/jsonl（不论该槽是否成为 keeper、分数好坏均入账）。

Tab 分隔；须含 **`experiment`、必填 `scenario_id`**（F1 场景清单 ID，见 §2.2 **场景号归属**；值来自 cfg，**非** contract 常量）、`git_commit`、`description`、**`notes`**、`exp_dir`；数值列须含主指标。`notes` = 人工备注（`NN_NOTES`）+ 未在 contract 声明的 metrics 键（`k=v; …`），两段以 ` || ` 连接；不参与 KEEP。

**可选列**：业务仓可追加 `timestamp`（ISO8601 字符串，由 `finalize_round` 自动写入，仅留档）、`average_forgetting` / `backward_transfer` 等领域指标；只要首行表头声明、对齐即可。**禁止**加 `keep` / `discard` 等 KEEP 决策列（决定由 `should_keep` / `round_decision.json` 承担）。

**系统观察列 `exploration_space`（探索空间）**：格式 `{TIER}-{depth}`（如 `B-routine` / `C-different` / `B-novel`）。`finalize_round` **必须**当场写入 A–D 格子（`{A|B|C|D}-{routine|derived|different}`）；正式训完不得空格。**禁止** `E-` 入列（改题另记 `_runs/analysis/e_feedback.jsonl`，不进成绩表列）。反思写待办只记账、不等待；人点名分析或手跑反思时才问留下 / 搁置 / 驳回，**三种处置都只更新记录、不改实验**。驳回后同主张不再提；留下只给建议；搁置下次可再提。深度为 RDDN（`routine`/`derived`/`different`/`novel`）；`novel` **仅**由 `reflect` 把结构层 `different` 升格盖章（`scripts/sync_exploration_ledger.py`），与 TAM 举证不同。旧仓：`regen_results_tsv` 加空列后可 `--backfill-all`。

**`_runs/results.jsonl`（与 TSV 成对追加）**

- 每行一个 JSON 对象；`finalize_round` / `_append_repo_ledger_row` 写入时 **须含 `scenario_id`**，与 TSV 同值、同解析源（`cfg["scenario_id"]`）。
- `schema_version`：`2` = 含 `scenario_id`；`1` = 历史行（无场景字段，只读兼容）。
- 同步字段：`experiment`、`git_commit`、`exp_dir`、`elapsed_sec`、`metrics`、`description`、`notes`（规则同 TSV）。

## 9. 依赖

依赖在 pyproject.toml / poetry.lock；Agent 勿 `pip install`。

## 10. 版本管理（template version mgmt，2026-07-06 spec）

模板维护仓 `auto-nn-experiment` 通过 **semver + git SHA 后缀**（`0.1.0+abc1234`）声明版本；业务仓 init 时下发 stamp，update 时 gate 对账。

### 10.1 数据模型

| 文件 | 维护者控 | 内容 | 谁写 |
|------|---------|------|------|
| `VERSION`（维护仓根） | ✅ git 控 | 纯 semver（`0.1.0`） | 维护者手动 bump |
| `CHANGELOG.md`（维护仓根） | ✅ git 控 | 人类 release notes | 维护者写 |
| `.auto-nn/version`（业务仓） | ❌ 业务仓只读 | `0.1.0+abc1234`（**当前**模板戳） | governance-sync 每次重写 |
| `.auto-nn/init-template-version`（业务仓） | ❌ 业务仓只读 | 同形；**立项/首次落戳**原始模板戳 | new-project 或首次 sync **只写一次**；已有则永不覆盖 |
| `.auto-nn/governance-rev`（业务仓） | ❌ 业务仓只读 | git rev of `template/package/` | 已存在（保留） |

### 10.2 跨版本策略（DUAL）

- **patch / minor**：自动接受；`auto-nn-update` 无 flag 即可
- **major**：需 `--accept-major-bump` 显式接受；否则 exit 1
- **降级**：默认 WARN + 仍 sync；`--strict-version` 才拒绝
- **stamp drift**（semver 同 SHA 异）：WARN + 仍 sync

### 10.3 维护者 release 流程

```bash
$EDITOR VERSION                       # 0.1.0 → 0.2.0
$EDITOR CHANGELOG.md                  # 加 ## 0.2.0 (2026-07-06) 段
git add VERSION CHANGELOG.md
git commit -m "release: 0.2.0 — <summary>"
bash scripts/release-check.sh         # 5 步短路拦截
git push
```

### 10.4 业务仓查询

```bash
bash scripts/template-version.sh       # 当前戳；有则另打 init-template-version 行
bash scripts/template-version.sh --init  # 只打立项原始戳
bash scripts/template-version.sh --json  # JSON（含 init-template-version）
```

> 旧仓若已升版且无 `init-template-version`：doctor WARN；**勿**用当前 `.auto-nn/version` 盲目回填。
