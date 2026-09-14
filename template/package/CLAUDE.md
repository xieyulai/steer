# CLAUDE.md — Agent 入口（ExperimentBase 业务项目）

规则权威仍在 **`PROTOCOL.md`**。本文 = 操作入口（技能 / 命令 / 硬边界 checklist）；语义与细则见 PROTOCOL。

**Language / 对人说话：** Match the user's latest message. English in → English out. Chinese in → Chinese out. Do not mix. Slash names and `config.json` keys stay as written. Script tables (doctor / analyse) stay Chinese; prepend one sentence in the user's language. See `.cursor/rules/skills-plain-language.mdc`.

## 自然语言入口（与斜杠等价）

| 你说… | 进哪个技能 |
|-------|-----------|
| 看几行台账 / view runs | `/auto-nn-check` |
| 分析撞墙 / 下一步 / plateau | `/auto-nn-analyse` |
| 手跑一轮 / train once | `/auto-nn-manual-run` |
| 自动多轮 / batch / N rounds | `/auto-nn-auto-run` |
| 改能力 / 加 metric 列 / 扩场景 | `/auto-nn-modify` |

完整中英表：**`docs/nn-routing/intent-map.md`**（随 governance-sync 下发）。说不清时 Agent 会先问一句再进技能。对人说话跟用户语言走（中文或英文）；脚本体检表仍是中文，先用人话小结。

## NN 技能（全局 `auto-nn-*`）

技能 **不在本仓库**；真源在模板维护仓 `skills/post-migration/`，安装一次：

```bash
bash <template_root>/install.sh
```

| 场景 / 意图 | 斜杠技能 |
|-------------|----------|
| 选行选列看台账（**只读**；不 doctor、不算指标、不升 Tier） | `/auto-nn-check` — `scripts/view_runs.py`（`--cols` / `--where` / `--scenario` / `--best-by` / `--last`） |
| 结构体检（布局、表头、governance；深度档含 smoke） | `/auto-nn-doctor` — 见 `docs/nn-doctor/README.md` |
| 只读看台账、plateau、升 Tier、下一轮 Brief（silent doctor + `summarize-runs`；**不** train / reflect） | `/auto-nn-analyse` |
| **EXPERIENCE 百轮冗余**，收成精华 + 归档（**不**动 TSV） | `/auto-nn-compress` |
| 改模型 / loss / 新 TSV 列；**局部**删 exp / 删 TSV 行 | `/auto-nn-modify` — [`../../docs/nn-modify/README.md`](../../docs/nn-modify/README.md)（改能力文档枢纽，`governance-sync` 下发后以维护仓锚解析） |
| **清 preflight** / 整仓 / 绿场 | `/auto-nn-clear` |
| 设/改/查/清 实验目标值 + 实验模式（全局默认 + 按场景覆盖） | `/auto-nn-goal` — `manage_goal.py`；`show --all` / `stop-mode` |
| 写或改 `HUMAN_GUIDANCE.md`（指挥台） | `/auto-nn-human-guidance` |
| 手跑一轮：改代码 → train → KEEP（§6，不用 auto-run） | `/auto-nn-manual-run` |
| 手跑仅反思（`reflect.py`，要 REFLECT_INDEX pending） | `/auto-nn-reflect` |
| 审查当前最好或公开对照：复现 / 多种子（**不**进成绩表；审对照跳过新不新） | `/auto-nn-audit` |
| 立朴素下界 | `/auto-nn-plain` — `scripts/nn_baseline.py` |
| 立公开对照 | `/auto-nn-reference` — `scripts/nn_baseline.py` |
| `./auto-nn-run.sh N` 多轮编排 | `/auto-nn-auto-run` |
| 业务仓自助拉模板更新（governance-sync + verify） | `/auto-nn-update` — 按 `NN_TEMPLATE_ROOT` > symlink > `.auto-nn/template-root` 解析模板仓 → 无参 `governance-sync.sh` → verify + nn-doctor（前提：模板仓先 `git pull`） |

**常见串联：** `/auto-nn-plain` →（有源仓则先本机校准）→ `/auto-nn-reference` → `/auto-nn-auto-run`；撞墙 → `/auto-nn-reflect` → 再实验；停搜或要对当前最好/公开对照做复现/多种子 → `/auto-nn-audit`。缺尺时看台账/分析会点名该开哪个立尺技能。有原仓时文献尺对不上禁止贴。

**loop 达标即停：** `./auto-nn-run.sh N` 在 **optimize/innovate** 且配了有效 goal 时每轮后 `check_goal.py` 判定（CLI `focus_only` → yaml `goal.policy: focus` 只盯主场景；CLI `all_in_scope` → yaml `strict` 多场景全达标 → `GOAL_MET_ALL`）；**explore 有效时跳过 goal 硬停**。设/改 goal → `/auto-nn-goal` / `scripts/manage_goal.py`。见 PROTOCOL §7.2.1。

技能清单与细节见 `<template_root>/skills/post-migration/README.md`（**勿用 `@` 提及技能**；须先 `install.sh` 安装到 Cursor）。

## Modify Track 速查（对人）

**下表给人开改能力会话用；实验 Agent 边界见「你可改 / 不可改（两态）」。**

Agent 对你说话须 **人话全称**；括号内为路由代号（`/auto-nn-modify`）。完整表见维护仓 `CONTEXT.md` §Modify Track。

| 人话 | 代号 | 一句话 |
|------|------|--------|
| ~~台账·参数字段~~ | ~~Modify-L1~~（退役） | 改 `ledger.watchlist` + regen；**非**改能力 |
| 台账·指标列 | Modify-L2 | 新 metric；参与 KEEP |
| 台账·KEEP 口径 | Modify-L3 | keep 规则；≠ 场景 ID |
| 训练·模型 | Modify-T1 | backbone / `build_learner` |
| 训练·目标 | Modify-T2 | loss / reward |
| 训练·数据 | Modify-T3 | Dataset / env |
| 场景·补完 | Modify-Scenario-complete | `scenario_id`、keepers map、backfill |
| 场景·扩充 | Modify-Scenario-expand | F1 新增 Scenario ID |

**注意：** 修 TSV/jsonl 行数不一致或只改 `ledger.watchlist`（`regen_results_tsv.py`）是 **台账同步**，不是 Modify 改能力。

## 快速命令

```bash
poetry install                     # 安装依赖（.venv 不入库；换机/重装走 /auto-nn-setup 一键拉起含此步；慢见 check-env 换源提示）
bash scripts/check-env.sh          # 验证 Poetry/torch/CUDA；动态库缺失与缺包分文案；FAIL 时含换源与复用本机环境建议
bash scripts/template-version.sh    # 业务仓查模板版本（stamp = semver+SHA）
poetry run python train.py --help  # 超参 / 槽位 CLI（优先于 NN_*）
poetry run python train.py         # 默认全量训练（NN_SMOKE=0；单槽训末自动 finalize_round）
NN_SMOKE=1 poetry run python train.py  # 短训 smoke（迁移验收请用 scripts/smoke-check.sh）
# 多槽训末由 wait-train.sh 自动 finalize（失败 WARN 时才手动补，加 --repo-root .）：
# poetry run python -m contract finalize-round _runs/exp/<dir1> _runs/exp/<dir2> --repo-root .
# 框架自检（不触训练）：
# poetry run python -m contract sanity
# 快速修改参数（Config-Only）：
python scripts/modify-config.py _runs/configs/exp.json --set LR=0.003
```

## 改码三原则（摘要）

Agent 改 `train.py` / `workspace/` / `contract/` 须同时满足（权威：**PROTOCOL §0.1**）：

1. **config-only**：实验参数 `cfg["X"]` 强读；禁 `cfg.get(K, 默认)` 与环境变量读实验参数。
2. **no-fallback**：不兜底、不吞错；错误上抛。
3. **pluggable**：新变体走 config 开关 + registry（或既有 elif 分派）；禁止硬编码旁路。

全文与例外（LOCKED_DATASET / OPTIMIZER / OPTIMIZER_SCHEME 等）见 **PROTOCOL §0.1**。违反 = 污染代码，须回滚。

根级 `train.py` 禁止 `finalize_run(..., best_metrics=...)`；sync scan 脏则 FAIL → `python3 scripts/lib/migrate_finalize_run_kwargs.py <repo_root> --apply`（见 **PROTOCOL §3.0.2**）。

runner 出分（`EVALUATE_RUNNER`）：空串 CLI / 辅指标假缺 / `baseline_tag` 列 — 见 **PROTOCOL §3.0.2a** 与 `scripts/lib/adapter_accept.py`（文件名遗留；≠ 已退役立项 ADAPTER）。

## Config-Only（短约束）

| 允许 | 禁止 |
|------|------|
| `poetry run python train.py --config config.json` | `NN_LR=…` / `train.py --lr …` 覆盖实验参数 |
| 系统参数：`NN_SMOKE` / `NN_DEVICE` 等 | `os.environ.get("NN_XXX")` 读实验参数 |

```bash
python scripts/modify-config.py _runs/configs/exp.json --set LR=0.003
python scripts/modify-config.py _runs/configs/new.json --from-template _runs/configs/base.json --set LR=0.005
```

违规 → G-repro-env FAIL。细则见 **PROTOCOL §2.3**。

## 架构（极简）

核心：**`experiment.py`**（`ExperimentBase`）— 框架基类，**勿改**。

- **contract**：题面与官方 test（metric / `prepare_data` / `test` / `should_keep`）；framework 仓另有 **`contract/framework_binding.yaml`**（五能力 Discovery 总表 + `innovation` 框架键注册段→指纹硬判定第二真源，见 PROTOCOL §3.0.2b / ADR-13）。`prepare_data` 只锁数据集身份；**采样器等 D 档技巧**用 workspace `@register_sampler` + cfg `DATA_SAMPLER`（`ExperimentBase.wrap_train_loader`），勿写进 contract。`contract/runtime.py::INFO_PERM` 是**信息权限登记表**（训练可用材料 / 官方分路径 / 交卷开关，字面量；由立项「信息权限」三问经 `scripts/init_info_perm.py write` 落表，README `<!-- INFO_PERM -->` 块由 `scripts/info_perm_gate.py` 对账），也是合同的一部分：训前 **G-信息权限** 只认它、无环境变量开关；只评材料 **训练真打开才拦**（预留不算犯规）；`contract/test.py` 的 `_official_forward` 是官方分唯一出口（受限路径的手续写在这里）
- **workspace**：`build_*` / `train_step` / `evaluate` / `predict`
- **train.py**：编排两侧子类（`prepare_data` 后调用 `ws.wrap_train_loader`）

方法分配与 metadata 签名见 **PROTOCOL §3.0.1**。

**约束边界（操作向）：** 可覆盖基类已有方法、加 `_` 私有方法、在 `workspace/scripts/` 放探针；不可改 `experiment.py`、不可定义基类不存在的公开方法、不可手写绕过 `finalize_*` 写台账。

### 全局配置（nn-config.yaml）

- `profile` / `gpus`（`/auto-nn-setup` 专属可写；开训另读家目录 `~/.gpus`）/ `max_parallel` / `device` / `time_budget` / `seed`
- **`exploration_mode`**：顶层唯一探索旋钮（6 档；见 PROTOCOL §5.1）
- `keep`：`improve_mode` / `mode` / **`primary_delta_rel`**（老字段 `primary_delta` 仅兼容；见 PROTOCOL §2.1）
- `agent`：reflect_interval / plateau_rounds 等
- `goal`：`target` / `per_scenario` / `policy`（v4；CLI `focus_only`/`all_in_scope` → yaml `focus`/`strict`；见 PROTOCOL §7.2.1）

**常规迭代仅可修改 `ledger:` 段**；其余与 `contract/` 同级冻结（**例外**：顶层 `gpus` 仅 `/auto-nn-setup` 可写——换机/重装时**若有** `~/.gpus` 则按 `~/.gpus ∩ 本机` 收敛，没建该文件则跳过收紧。开训时有 `~/.gpus` 才按文件限制占用，无文件不拦）。

### 文件结构

- `HUMAN_GUIDANCE.md` — 人类指导：文首可选 **公平约束** + **路线图**（意图归人；经 `/auto-nn-human-guidance` 代写落盘；空路线图 = 阶段全自主；PROTOCOL §7.5）
- `references/REFLECT_INDEX.md` — 反思索引（机写；PROTOCOL §7.6）
- `references/manual/` / `references/auto/` — 人文献 / reflect 长文
- `CHECKLIST.md` — init 完成判据
- `experiment.py` / `contract/` / `workspace/` / `train.py` — 框架与两侧实现

## 单轮迭代流程（checklist）

详见 **PROTOCOL §6**（并行默认、OVAT、训后台账 commit 等）。

1. 读 `HUMAN_GUIDANCE.md`（先 **公平约束** 若有；再路线图，空则阶段全自主）；有 REFLECT pending 则读 INDEX（低于 guidance）
2. 读 EXPERIENCE（精华 → Tier 状态 → 近期）+ 台账 / journal；auto-run 时优先注入的 **Run Context**（brief / keeper / MA-1 / journal / env / round_decision / **ablation-hint** / **基线靶子 (baseline anchors)**；见 `saved/run_context.md`）
3. 按两态改参或改码（见下）→ `git commit`（可选 `NN_NOTES`）
4. `poetry run python train.py`（单槽训末自动 `finalize_round`；多槽经 `wait-train.sh` 训末自动 finalize）
5. 读 `keep_suggestion` → 更新 EXPERIENCE（pending 须 `reflect_ack:`；开槽前 slot plan 三行）
6. **训后 commit 台账（强制）**：`results.tsv` / `results.jsonl` / `round_decision.json` / EXPERIENCE 等（PROTOCOL §6 步骤 10）

## 迁后 auto-run（`./auto-nn-run.sh`）

| 角色 | 做什么 |
|------|--------|
| **人** | 提路线图意图（经 `/auto-nn-human-guidance` 落盘）；可选 `export NN_NOTES=…`；调 `nn-config.yaml` 顶层 **`exploration_mode`**（立项/迁移时；`aggressive` 等档位的 reflect/外部检索策略见 PROTOCOL §5.1） |
| **编排** | 实验 prompt **注入** Run Context（每轮）+ guidance + reflect pending；**门禁**决定是否跑 reflect |
| **实验 Agent** | 遵守注入块与**两态**边界；常规轮勿改 `nn-config.yaml`（非 ledger）/ `contract/`；撞禁区则停、用人话等人改题面/口径（**不**调用改能力斜杠技能） |
| **reflect** | 非每轮必跑；成功则更新 INDEX + `references/auto/` + EXPERIENCE `[反思]` |

**人类路线图门禁（与 PROTOCOL §7.5.3 对齐）：** auto-run batch **活跃时禁止**刷新批次基线文件；人改路线图须停 batch → 提交 → 重开。**G-HUMAN-COMMIT** 见 PROTOCOL。

手跑单轮仍遵守上文 checklist 与 PROTOCOL §6。

## 你可改 / 不可改（两态）

与 auto-run prompt 同源：

1. **可改**：改 `config.json` 实验参数（含 `scenario_id` 等）via `modify-config.py` / 写 config；改 `train.py` / `workspace/`（须守 PROTOCOL §0.1）。
2. **禁改**：改 `experiment.py`；手改台账 TSV/jsonl；常规轮改 `PROTOCOL.md` / `nn-config.yaml`（非 `ledger:`；`gpus` 仅 `/auto-nn-setup`）/ `HUMAN_GUIDANCE.md` / `REFLECT_INDEX.md` / `auto-nn-run.sh`；常规轮改 `contract/`（无 `NN_RELAUNCH`）。需要改禁区时停并等人；人可通过 `/auto-nn-modify` 改能力（含 contract，常需 `NN_RELAUNCH=1`）——**实验轮文案不要求 Agent 调用该技能**。

无 `NN_RELAUNCH=1` 时改 `experiment.py` / `contract/` / 治理文档（含本文件、`PROTOCOL.md`、`auto-nn-run.sh`）→ 训前 preflight **硬失败**、`nn-doctor` **`immutable_path_guard` FAIL**。

**立项 / 迁移**：可改 `contract/`（PROTOCOL §3.0），之后回到常规两态。

**新项目接入：** `bash <template_root>/scripts/new-project.sh …` → 对照 `profiles.yaml` → 立项改 contract → 常规只走两态 → 初始化收尾见 `/auto-nn-init`（CHECKLIST §2–§5 + verify/smoke）。

## 硬规则

1. 改动范围按上文**两态**；常规轮以 `train.py` / `workspace/` / `config.json` 为主；动 `contract/` 须人审 + `NN_RELAUNCH=1`。
2. 入口：`poetry run python train.py`（`--help`；优先级：文件默认 < `NN_*` < CLI）。Pre-flight / G-封装 / G-布局 / G-cfg-no-defaults / G-no-fallback 见环境变量开关。台账 TSV 与 jsonl 仅经 `finalize_round` / `report_train_artifacts` **成对追加**。
3. keep 口径（`improve_mode` / **`primary_delta_rel`** / KEEP 池）常规迭代不得改，只能在 `EXPERIENCE.md` 提议。
4. `EXPERIENCE.md` 每轮至少追加一条。
5. **指挥命令**写在 `HUMAN_GUIDANCE.md`，勿只写在 EXPERIENCE 或 `references/auto`。
6. 有 `REFLECT_INDEX` pending 时须响应并写 `reflect_ack:`（无有效 ack 时 auto-run **不会** mark consumed）。
7. `shared_context` 跨 epoch 共享；workspace 读写。**禁止**把 `contract` 实例放进袋 / 从袋读取（`shared_context["contract"]` / `.get("contract")`）；题面对象经函数参数或 `cfg` / `prepare_data` / `ws` 显式属性传递（doctor `shared_context_contract` FAIL）。
8. 杀进程须先确认 PID 属本仓（`saved/.train_pid`）；禁止 `pkill` / `killall`。

## 不要

- 不要问是否继续。
- 不要 `pip install`；用 `poetry run`。
- 不要长期仅 Tier A 标量微调；读 EXPERIENCE **Tier 状态**，撞墙后升档（PROTOCOL §7.5.1）。
- EXPERIENCE 过长：先读精华摘要 + 信息索引 + Tier 状态 + 近 5 轮；人可跑 `/auto-nn-compress`（PROTOCOL §7.5.2）。

## shared_context 生命周期

- train.py 创建：`{"device", "val_loader", "objective", "cfg"}`（及 `metric_key` 等训环状态）
- workspace.train_step 可写入：`optimizer`, `scheduler`（首次懒初始化）
- ws.evaluate 只读其中的 `device`, `val_loader`, `objective`
- **禁止键 `contract`**：不得注入、不得 `.get("contract")` 兜底（与 ADR-11「不双源」同精神；方案 B）
- 每个 epoch 共享同一 dict，epoch 间不重置
