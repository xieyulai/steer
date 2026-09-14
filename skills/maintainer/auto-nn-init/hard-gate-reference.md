# auto-nn-init — HARD-GATE 引擎参考（agent-only）

> **读者：仅执行 `/auto-nn-init` 的 agent。** 本文是 HARD-GATE 的**内部单一事实源**：编码体系、逐项问话内容、gate 自检、矛盾检查、F1/验收模板、contract/metrics/nn-config/executor 细则。
>
> **用户从不看本文的编码。** 对用户呈现规则见 [`SKILL.md`](SKILL.md)「用户可见交互协议」；**人读版**（进度、四段式、好/坏示例）见 [`docs/init-conversation-guide.md`](../../../docs/init-conversation-guide.md)——agent 内部按本文编码推进，对用户翻译成人话主题 + 进度 + 「这一步在定什么」+ A/B/C 选项。
>
> **人话翻译单一真源**：内部码 → 对用户怎么说，以 [`docs/skill-glossary.md`](../../../docs/skill-glossary.md) §项目初始化 为准；本节映射表与 glossary 同步，细则仍以本文为引擎真源。
>
> **不进业务仓**（与 `docs/` 同级，仅维护仓 / `target_root` 可读）。术语见 `CONTEXT.md`（`迁移完成` ≠ `F1-contract`）。

## 人话主题 ↔ 内部码 映射（翻译层）

> 完整逐项对照见 [`docs/skill-glossary.md`](../../../docs/skill-glossary.md) §项目初始化。

agent 对用户只说**人话主题 + 进度**；内部按右列编码逐项推进、自检、写 F1-contract。

| 人话主题（对用户说） | 内部编码（本文 / F1 用） | 入口 |
|----------------------|--------------------------|------|
| 对齐理解 | P0-project-brief | A/B |
| 场景与数据 | D1-scenario-inventory → D2-data-split →（信息权限三问）→ D3-workspace-data → D4-repro-data | A/B |
| **信息权限** | **I1-train-consumes → I2-official-path → I3-other-info-rules**（D2 之后、D3 之前） | A/B |
| 旧资产清理 | H1-legacy-artifacts → H2-experience → H3-agent-boundary | 仅 A |
| 训练方式 | T1-loss-layers → T2-callchain | A/B |
| 评估与台账 | E1-metrics → E2-metric-tier → E3-official-test → E4-train-eval → E5-tsv-columns → E6-scenario → E7-run-context → E8-checkpoint → E9-keep | A/B |
| 运行设置 | O1-time-budget → O2-gpus-parallel → O3-baseline-anchors → O4-repro-determinism | A/B |
| **实验目标** | **G1-experiment-mode → G2-goal-value** | A/B |
| 汇总确认（签字） | F1-contract | A/B |

**进度计数**（对用户的抬头 `第 N / 共 M`）：按 workflow 走不同步数。
- workflow=build → 24 步 picker（原 B 入口；2026-09 起含信息权限 I1–I3，原 21）
- workflow=migrate → 27 步 picker + 决策 1-3（原 A 入口,含原 migration + adapter；原 24）
- workflow=update → 15 步 picker（原 A 入口 reinit）

**绝不对用户暴露**：编码 slug（`H1-legacy-artifacts` 等）、`F1-contract`/`S_method`/`S_data`/`S_run`/`A_explore`/`E4_PATH` 等术语、块 A–F 全量盘点表、`选后锁定→F1 会写什么` 列。这些只在本文与 `.auto-nn/migration-summary.md` 内部使用。

## 安装包与边界（agent 背景）

将业务项目接入 **本仓库**（STEER）模板：`ExperimentBase` + `contract/` / `workspace/` 分层。**入口 A** 迁入已有项目；**入口 B** greenfield 立项。

**模板维护仓根**（`template_root`）：本仓库根目录（含 `.template-maintainer` 标记）。**业务安装包**在 **`template/package/`**（`new-project.sh` 将 `template/package/` rsync 到 `<project_root>/`）：含 `CLAUDE.md`、`CHECKLIST.md`、`README.md`、`PROTOCOL.md`、`pyproject.toml`、`profiles.yaml`、`nn-config.yaml`、`experiment.py`、`contract/`、`workspace/`、`auto-nn-run.sh`、`reflect.py`、`scripts/`（verify、smoke、governance-sync、wait-train 等）。**不复制**：`template/maintainer/`（含 `skeletons/`）、仓库根 `CLAUDE.md`、`skills/`、`docs/`。

**迁入已有项目时**易缺 README / `PROTOCOL.md` / `contract/__main__.py` 等——不是脚本失效，而是路径不同。**勿依赖 `docs/`**：迁移权威正文 = `SKILL.md` + 本文 + `template/package/CHECKLIST.md` + `profiles.yaml` + `PROTOCOL.md`。

**对外完成判据（唯一门禁）：** `bash scripts/verify-migration-complete.sh` **退出码 0** **且** `bash scripts/nn-doctor.sh` **0 FAIL** **且** [`template/package/CHECKLIST.md`](../../../template/package/CHECKLIST.md) **§5 训跑 smoke**。**不算完成：** 仅提交 contract/workspace、仅通过 G-评估、未跑 verify、或 doctor 有 FAIL 就向用户说「迁完了」。

## 编号速查（单一事实源）

**全阶段** HARD-GATE 编号格式为 **`<块><n>-<slug>`**（如 `H1-legacy-artifacts`、`E4-train-eval`）。问话、用户回复（`编号=①`）、F1-contract 汇总表行名**均用 slug**。

**宏观顺序（入口 A）**：**P0 → D1–D2 → I1–I3 → D3–D4 → H → T → E1 → G → E2–E9 → O → F**（**D1–D3 先于 H1–H3**；**信息权限 I 在 D2 之后、D3 之前**（[阶段 I](#阶段-i信息权限谁能看什么-d2-之后d3-之前)）；**G1/G2 在 E1 之后、E6 之前**）。**入口 B**：**P0 → D1–D2 → I1–I3 → D3–D4 → T → E1 → G → E2–E9 → O → F**（无 H）。**E4-train-eval**、**E8-checkpoint** 须在 **T2-callchain** 之后。

**用户心智顺序**（与步号一致，入口 A）：对齐项目 → **场景+数据（含信息权限）** → 历史清理 → 怎么训 → **主指标** → **实验目标** → **评估其余（含场景探索方案）** → 机器 → 签字。

**F1-contract** = 阶段 1 结束时锁定的 **口径合同表**（≠ 迁移完成）；仅在**入口 A migrate 27** / **入口 B build 24** / **二次 init update 15** 全部确认后的**单独一轮**汇总。

### 入口 A — 27 项速查

| # | 编号 | 人话 |
|---|------|------|
| 1 | **D1-scenario-inventory** | **场景清单**（数据与指标 / 方法族 / 默认配置；P0 后第一项） |
| 2 | **D2-data-split** | 数据根 + 划分表 + 每场景 OFFICIAL_TEST |
| 3 | **I1-train-consumes** | **训练许用材料**：全部 / 只训练份（哪些只评）/ 不读数据文件 |
| 4 | **I2-official-path** | **官方打分通道**：整网前向 / 受限路径（手续函数）/ 固定评测态 |
| 5 | **I3-other-info-rules** | **其他信息规矩**：均无 / 逐条（机器只管训练 batch 键白名单） |
| 6 | **D3-workspace-data** | 训内数据处理落 workspace |
| 7 | **D4-repro-data** | **复现数据**：数据根版本、`REPRO_ENV_KEYS` 数据项 |
| 8 | **H1-legacy-artifacts** | 旧台账 / exp / 命名线索（**可对照 D1 场景 ID**） |
| 9 | **H2-experience** | EXPERIENCE.md 取舍 |
| 10 | **H3-agent-boundary** | 旧文档硬约束 → README |
| 11 | **T1-loss-layers** | loss / 约束 / 技巧分层 |
| 12 | **T2-callchain** | 外层循环、调用链 ≤6 行 |
| 13 | **E1-metrics** | 主/辅指标键 |
| 14 | **G1-experiment-mode** | **实验模式**（追指标 / 新方法+指标 / 摸底） |
| 15 | **G2-goal-value** | **主指标目标值**（达标即停；explore 可选护栏） |
| 16 | **E2-metric-tier** | 指标列分级 |
| 17 | **E3-official-test** | 训末 `contract.test`（须与 **I2** 通道一致） |
| 18 | **E4-train-eval** | E4_PATH + E4_训内节奏 + 返回键 |
| 19 | **E5-tsv-columns** | TSV 四区与列 |
| 20 | **E6-scenario** | **探索方案与排期**（须在 **G1/G2** 之后；清单已在 D1） |
| 21 | **E7-run-context** | 台账运行参数键 |
| 22 | **E8-checkpoint** | checkpoint 策略 |
| 23 | **E9-keep** | KEEP / 历史池 |
| 24 | **O1-time-budget** | 训练墙钟 |
| 25 | **O2-gpus-parallel** | GPU 白名单 + 并行 |
| 26 | **O3-baseline-anchors** | 该场景起步尺子（plain+reference；测条件；找不到请用户给；**须在 G + E6 之后**） |
| 27 | **O4-repro-determinism** | **复现随机性**：基线 `NN_SEED`、cuDNN、快照约定 |

→ 随后 **F1-contract** 汇总签字（不计入 27）。

**P0-project-brief** 在 **#1 之前**单独一轮，**不计入** 27/24/15 项。见 [P0-project-brief](#p0-project-brief项目摘要确认不计入-272415-项)。

> **入口 A 为何 D 在 H 前？** 先钉「测谁、数据契约」，再清理旧台账/EXPERIENCE；H1 可对齐 D1 场景 ID。**信息权限 I 为何在 D2 后、D3 前？** D2 定了有哪些数据、怎么划分，I1 才能指着它说「哪些只评」；D3 训内数据处理须先知道训练能碰什么。**G1/G2 为何在 E6 前？** 探索方案与**实验目标**（模式 + 达标线）紧密相关——须先定「追数 / 方法+数 / 摸底」，再定「每轮允许改什么、场景怎么排期」；E6 **禁止**裸写内部轴名，须引用 G1 人话结论。**O3** 在 G + E6 之后，定该场景起步 **plain/reference 尺子**（起手改哪一类已由 G1 `exploration_mode`→`tier_start` 隐含；见 O3 节）。

### 入口 B — 24 项速查

无 H 段；与上表 **#1–7、#11–27** 相同（重编为 1–24）：`P0 → D1→D2 → I1→I2→I3 → D3→D4 → T1→T2 → E1 → G1→G2 → E2…→E9 → O1→O4 → F1-contract`。机器可读题序：`python3 scripts/init_answers.py steps --workflow build|migrate`（题库 `docs/init/init-question-registry.yaml`，单测对照本表）。

### E4 子字段（在 E4-train-eval 一轮内）

| 子字段 | 含义 |
|--------|------|
| **E4_PATH** | ① `evaluate→contract.test` 整包；② 同指标函数、不同 loader（supervised 默认） |
| **E4_训内节奏** | **A** 每圈都评；**B** 训中不评；**C** 稀疏评 |
| **E4-keys** | 训内 `ws.evaluate` 须覆盖 E1 键（或 physical proxy 集） |

> **别名**：**CADENCE**、**E4_CADENCE** = **E4_训内节奏**。

---

## 迁移五阶段（入口 A / B 通用）

| 阶段 | 名称 | 产出 | 禁止 |
|------|------|------|------|
| **0** | 分析 | 确认 **source/target 路径** + `migration-compare`（入口 A 对 **source**）+ **盘点表 v0** | 改 **source** 或 **target** 代码 |
| **1** | HARD-GATE | **F1-contract 口径合同表** 用户签字（H/E/D/T/O/**G** 决定） | 改代码；在 F1-contract 里列删文件/跑 verify 等实现清单 |
| **2** | 实现 | 按 **F1-contract 口径合同表** 改 contract/workspace/train | 宣称迁移完成 |
| **3** | 交付卫生 | `template/package/CHECKLIST.md` §2–§4 | 跳过 verify |
| **4** | 验收 | `verify` exit 0 + `nn-doctor` 0 FAIL + CHECKLIST §5 smoke | 未过 verify / doctor 有 FAIL 对用户说完成 |

**官方命令**

```bash
# 阶段 0 — 分析（禁止手写 compare_side 循环）
bash <template_root>/scripts/migration-compare.sh \
  --template-root <template_root> --project-root <project_root>

# 阶段 3 — 治理同步（业务仓必做，在 verify 之前）
bash <template_root>/scripts/governance-sync.sh \
  --template-root <template_root> --project-root <project_root>

# 阶段 4-A — 验收
cd <project_root> && bash scripts/verify-migration-complete.sh
```

---

## 入口

### 入口 A：analyze-existing

迁移已有项目（RL、CSI、physical/PINN 等）到模板模式。

#### 迁移落点原则（入口 A 必遵 — 禁止原地修改）

| 路径 | 变量名 | 规则 |
|------|--------|------|
| **旧项目（只读）** | `source_root` | 现有代码/台账所在目录；**阶段 0～1 只读**；**阶段 2 起禁止写入**（不删不改其 `contract/`/`train.py`） |
| **迁后项目（唯一写入）** | `target_root` / `project_root` | 模板化后的**新**目录；**必须** `realpath(target) ≠ realpath(source)` |

**禁止**：把 `source_root` 当作 `project_root` 在原目录上直接改模板化代码并宣称迁完（**原地迁移**）。

#### 迁后目录命名建议（入口 A — Agent 必须给出，用户确认后执行）

在确认 `source_root` 之后、**P0 之前**，Agent **必须**给出 **1～3 条**可执行的 `target_root` 建议（含完整 `new-project.sh` 命令），**不得**只问「迁到哪」而不给例子。

**Agent 负责推荐排版；用户负责拍板**（可改连字符/版本号/父目录，确认后才 `new-project.sh`）。

**推荐落点（默认启发式）**

- **同父目录、新目录名**：与 `source_root` **同级**新建目录（便于对比、旧仓保持只读）。
- **推荐目录名（首选）**：`auto-nn-<任务短名>-vN`（连字符，与全局 `auto-nn-*` 技能/模板命名空间一致），例如：
  - `…/auto_rl_design` → **`…/auto-nn-rl-design-v10`**（任务短名 `rl-design`；`N` 由用户确认或 Agent 建议下一版）
  - `…/auto_pinn_3d_v7` → **`…/auto-nn-pinn-3d-v8`**
  - `…/auto-clip-flow-v1` → **`…/auto-nn-clip-flow-v2`**
- **任务短名 `<slug>` 推导**（仅用于推荐，用户可改）：
  1. 取 `source_root` 目录 basename；
  2. 去掉前缀 `auto_` / `auto-`；
  3. 去掉末尾 `_vN` / `-vN`（若有）；
  4. `_` → `-`，合并重复连字符，得 `<slug>`（小写）。
- **版本号 `vN`**：扫描**同父目录**下已有 `auto-nn-<slug>-v*` 与旧式 `auto_*` / `auto-*` 同名系列，建议 **下一整数**；若用户希望迁后「从 v1 重新计」须在确认时写明。
- **备选（可列入表供对比，不作默认首选）**：沿用旧仓命名递增，如 `my_project_v10`（未加 `auto-nn-` 前缀）。
- **Poetry 项目名**（`new-project.sh` 第二参数）：默认与**用户确认的目录名**一致（含 `auto-nn-…`；合法字符见 `new-project.sh`）。

**建议消息格式（示例）**

```markdown
### 迁后目录建议（请选一或改路径/排版）

| # | target_root（拟） | new-project.sh（在 <template_root> 下执行） |
|---|-------------------|---------------------------------------------|
| **推荐** | `/…/OPTICAL_DESIGN/auto-nn-rl-design-v10` | `./scripts/new-project.sh ../OPTICAL_DESIGN/auto-nn-rl-design-v10 auto-nn-rl-design-v10 --profile rl` |
| 备选 | `/…/OPTICAL_DESIGN/auto_rl_design_v10` | `./scripts/new-project.sh ../OPTICAL_DESIGN/auto_rl_design_v10 auto_rl_design_v10 --profile rl` |

- `source_root`（只读）：`/…/OPTICAL_DESIGN/auto_rl_design`
- 推荐短名推导：`auto_rl_design` → slug `rl-design` → **auto-nn-rl-design-v10**（版本号待你确认）
- 校验：`realpath(target) ≠ realpath(source)`；目标路径 **尚不存在** 或为空（将由脚本创建）

**请确认**：采用 **推荐** / **备选** / **自定义**（可只改版本号或 slug，请给出绝对路径 + Poetry 项目名 + profile）
```

**规则**

- 用户明确同意某一行（或给出自定义路径）后，才写入 P0 的 `target_root` 并执行 `new-project.sh`。
- 用户不同意所有建议时：根据用户路径 **更新建议表** 再确认一轮；**禁止**未经确认擅自 `new-project.sh`。
- 若用户坚持用已存在且非空的目录作 `target_root`：须说明风险（非 `new-project.sh` 干净安装）；仍须满足 `≠ source` 且最终为 git 仓 + verify。

**必须**用 `new-project.sh` 创建 `target_root`（阶段 2 之前、P0 中须与用户确认路径；**禁止** `cp -r` 整包旧仓作迁后目录）：

```bash
cd <template_root>
./scripts/new-project.sh <target_root> <项目名> --profile <supervised|rl|physical> [--skeleton auto]
# 脚本会：rsync template/package/、git init、首次 commit、写入 .auto-nn/migration-source（入口 B 为 # greenfield）
```

然后从 `source_root` **选择性移植** `contract/`、`workspace/`、`train.py`、业务 `data/` 引用等到 `target_root`（数据大文件可 symlink 或 README 指回 source，须在 D2/README 写明）。阶段 2 起在 `target_root` 写入 `.auto-nn/migration-source`（**一行** `source_root` 绝对路径）。阶段 2 起所有 `governance-sync` / `verify` / `smoke` **只在 `target_root` 执行**。

**落盘标记（`.auto-nn/migration-source`，verify 硬检）**：**入口 A** 写 `source_root` **绝对路径**；**入口 B** 由 `new-project.sh` 写 `# greenfield`（**标记名，非 scenario 枚举**；无旧仓）。`verify_project_layout.py` 另检根目录白名单、禁止整包拷贝残留（根 `results.tsv`、`LOGS/`、`parallel-agents.sh` 等）。

**阶段 0 对照 CLI**：对 **`source_root`** 运行（分析旧仓与模板差距）；`target_root` 建好后应对 **`target_root`** 再跑一次（迁后对齐检查）。

#### 阶段 0：分析（只读）

1. 锁定 **`source_root`**（只读）；按上节 **[迁后目录命名建议](#迁后目录命名建议入口-a--agent-必须给出用户确认后执行)** 给出建议并获用户确认 **`target_root`** + `new-project.sh` 命令；**禁止**二者为同一路径。
2. 读 **`source_root`** 下 `contract/`、`workspace/`、`train.py`；若有项目内 `experiment.py` 记路径（迁后 `target_root` 用模板 `experiment.py`）。
3. **必须**对 **`source_root`** 运行官方对照 CLI（对照表以 stdout 为准）：

```bash
bash <template_root>/scripts/migration-compare.sh \
  --template-root <template_root> \
  --project-root <source_root>
```

- **exit 1**：先修 G-封装 / G-评估，再进入阶段 1。
- **禁止**即兴 `python -c "... compare_side ... .items()"`；`compare_side` 返回 **list**，不是 dict。

4. **入口 A 必做 — [现状盘点表 v0](#阶段-0-现状盘点表入口-a-只读)**：`migration-compare` 通过后、**P0-project-brief 之前** 填完（可边读码边补）。用户 **P0=①** 后，阶段 1 各编号 **【现状】须引用 v0 / P0 已确认摘要**，禁止不读仓库重新猜。

5. **快速路径**（可选，满足则 D2-data-split/D3-workspace-data、T1-loss-layers、**E1-metrics/E3-official-test/E5-tsv-columns** 等可标「确认即可」；**E9-keep 永远不可快速路径**——须按 [E9-keep](#e9-keep--keep-进步线按指标族选型) 给档位让用户选；**D2-data-split 划分表 + D2-data-split 可比性子集、D4-repro-data、T2-callchain 调用链 ≤6 行、E4-train-eval、E2-metric-tier、E6-scenario、O1-time-budget～O4-repro-determinism 仍须完整**；见 [阶段 T](#阶段-t--agent-提问规范必遵)）：
   - `migration-compare` **exit 0**
   - 输出中 `fast_path_eligible` 为真（`--json` 时 stderr 可见），或对照表 contract/workspace 几乎全为「保留」且无 experiment 注入项
   - **仍须单独问**：**D1-scenario-inventory**、**D2-data-split 划分表 + 每场景 OFFICIAL_TEST**、**D4-repro-data**、H1-legacy-artifacts～H3-agent-boundary（入口 A）、**T2-callchain（含调用链）**、**E4-train-eval**、**E6-scenario**、**O1-time-budget～O4-repro-determinism**、**G1-experiment-mode～G2-goal-value**、**F1-contract 汇总**
   - **快速路径亦不可跳过**：README `<!-- D2_DATA_SPLIT -->` 块（见 [D2-data-split 数据划分确认表](#d2-数据划分确认表必遵)）

#### 阶段 0 — 现状盘点表（入口 A，只读）

**目的**：在 HARD-GATE 之前，从**被迁项目**一次性归纳「现在是什么样」，避免每项澄清时重新搜仓库、漏掉 **数据与指标 / 默认配置** 分层，或**只依赖旧台账**而跳过代码里的可比世界。

**时机**：`migration-compare` **exit 0** 之后、**P0-project-brief 之前** 须有 **v0**；读 `contract/` / `train.py` / 旧 `_runs/` 时可继续补全，但 **不得** 写入迁后决策（决策留阶段 1 + F1-contract）。

**规则**

| 规则 | 说明 |
|------|------|
| 只读 | 本表阶段 **禁止改** 业务代码 |
| 事实 vs 决策 | 只写提取到的事实或 `待确认`；「迁后要不要」留 HARD-GATE |
| 引用 | H1-legacy-artifacts～O4-repro-determinism 每条 **【现状】** 第一段须能对应下表 **块 A–F**（可写「见盘点表块 E」） |
| 与清单关系 | 块 E 是 **D1-scenario-inventory** 的 v0 草稿；**用户签字**在 HARD-GATE **#1 D1**（入口 A）；D2 `SCENARIO_CANDIDATES` 从 D1 已确认 ID 摘取 |
| **块 E 完成条件** | v0 须 **五问有草稿** + 清单 **≥1 行**（进 D1 前）；D1 确认后才是 F1-contract「场景清单」定稿 |

**从哪里读（检查清单，按需勾选已扫；无旧台账仍须扫代码填块 E）**

| 来源 | 主要填哪一块 |
|------|----------------|
| **无历史 / 仅代码** | **块 E 五问**（必做）；B、C 从 contract/train |
| `_runs/results.tsv` / 旧 `results.csv`（**可选**） | A、D、E 线索 |
| `EXPERIENCE.md`、旧 README/PROTOCOL | A、E |
| `train.py` 顶部常量、`NN_*` / CLI | C、**E（S_run）** |
| `contract/`、`prepare_data`、`test` | B、D、**E（S_data）** |
| `workspace/` loss、采样、`evaluate` | C |
| 近期 `exp_dir/config.json`、`results.json` | D、E 线索 |

**铁律（块 E）**：`SCENARIO_AXIS=none` **仅表示**无「后面允许试什么」的轮换；**不表示**无场景清单、**默认配置（起跑线）**可空。单场景 = 清单 **1 行**，默认配置仍须写清。对用户澄清时**表头只用**「数据与指标 / 默认配置（起跑线）/ 后面允许试什么 / 成绩和谁比」，**禁止**用 S_data、S_run 作列名。

**盘点表模板（复制到对话记录或迁移笔记；进 H1-legacy-artifacts 前至少块 A/B/C/D/E 非空；块 E 须满足完成条件）**

```markdown
## 迁移现状盘点 v0 — <项目名>

profile: （nn-config.yaml）
migration-compare: exit 0 / 1（日期）

### 块 A — 历史与文档（→ H1-legacy-artifacts～H3-agent-boundary）

| 项 | 现状（事实） |
|----|----------------|
| 旧台账路径 | 有/无；行数；表头摘要 |
| 旧 experiment 命名模式 | 例：`*sip*_*mode*` |
| EXPERIENCE 场景/KEEP 人话 | 摘录或「无」 |
| 旧文档硬约束候选 | 类型 + 摘录（供 H3-agent-boundary 勾选） |

### 块 B — 数据与可比子世界（→ D2-data-split）

| 项 | 现状 |
|----|------|
| 数据根 | 路径 / env |
| TRAIN / VAL / TEST（或 physical：`TRAIN=none`、官方 test=SSFM） | 各是什么；**physical 须另写「采样可调=yes」** |
| 官方终评入口 | `contract.test` / 脚本 / 函数 |
| 可比子世界 ≥2? | 是/否；若是有哪些（短 ID 候选） |
| val 与 test 同分布? | yes/no/未知 |

### 块 C — 训练控制流（→ T1-loss-layers～T2-callchain）

| 项 | 现状 |
|----|------|
| loss 组成（一句） | |
| 不可变物理/任务项（候选） | 供 T1-loss-layers |
| 外层循环 | epoch/segment/stage |
| 每圈 evaluate? | 是/否 |
| 训末 test? | 是/否 |
| checkpoint 习惯 | best/last/无/未知 |
| 每轮绑定场景数（推断） | 1 / 1→N / 未知 |

### 块 D — 指标与台账（→ E1-metrics, E2-metric-tier, E5-tsv-columns）

| 项 | 现状 |
|----|------|
| 代码中 metric/aux 声明 | 键列表 |
| 旧 TSV 列 vs 声明 | 缺列 / 多列 / notes 藏键 |
| TSV 四区（旧表） | 场景/metrics/parameters/notes 是否分得清 |
| 曾用于 KEEP 的键 | 主指标 + improve 习惯 |

### 块 E — 场景与运行档（v0 草稿 → **D1-scenario-inventory** 用户确认 → D2/E6/E7/E9）

**线索来源（多选，≥1）**：□ 无历史  □ 旧台账(csv/tsv)  □ exp配置  □ 命名习惯  □ EXPERIENCE  □ 仅代码与README

1. **数据与指标**（内部代号 S_data）：官方终评有几种数据/协议？多种 → 多场景 ID
2. **默认配置（起跑线）**（内部代号 S_run）：键=典型值；来自 train/contract/nn-config，**不是** metric 名
3. **后面允许试什么**（内部代号 A_explore）：无 | ≤1 个可调项 + 约束写法
4. **成绩和谁比**（KEEP 池）：（谁与谁可比；供 E9 / EXPERIENCE）
5. **与 H1-legacy-artifacts 线索关系**：有/无命名或台账线索；无则写「块 E 仅来自代码」

**场景清单草稿（≥1 行；禁止仅 default 且「默认配置」全空）**

| 场景 ID | 数据与指标 | 默认配置（起跑线） | 后面允许试什么 | 成绩和谁比 |
|---------|------------|-------------------|----------------|------------|
| default | | | 无 | |
| … | | | | |

### 块 F — 运行环境（→ O1-time-budget～O3-baseline-anchors；可与 O 阶段同轮探测）

| 项 | 现状 |
|----|------|
| 历史常用 GPU / 并行 | 从旧脚本推断或未知 |
| 本机 GPU（O 时填） | |
```

**块 → HARD-GATE 映射（Agent 自检）**

| 块 | 主要编号 |
|----|----------|
| A | H1-legacy-artifacts, H2-experience, H3-agent-boundary |
| B | D2-data-split（含可比性子集） |
| C | T1-loss-layers, T2-callchain → E4-train-eval, E8-checkpoint |
| D | E1-metrics, E2-metric-tier, E5-tsv-columns |
| E | **D1-scenario-inventory**（清单签字）；E6-scenario（探索策略）；E7-run-context；E9-keep |
| F | O1-time-budget, O2-gpus-parallel, O3-baseline-anchors, O4-repro-determinism |
| D（复现数据） | D4-repro-data（在 D3 之后；与 D2 DATA_ROOT 对齐） |

**入口 B**：无被迁仓库 → **跳过** 块 A–D、F 的【现状】；**仍须**在 **D1-scenario-inventory** 用【模板默认】+ 用户描述起清单（≥1 行）。

#### 阶段 1：HARD-GATE（7.5 确认门禁）— **禁止在确认前修改任何代码**

> **交互：** 内部按本文编码 **每轮一问一编号**（先 P0 对齐），但**对用户只呈现人话**——见 [`SKILL.md`](SKILL.md)「用户可见交互协议」与本文下方 [Agent 交互规范](#agent-交互规范cursor--claude-code-通用)；不得批量贴 H1～O3 或整表 F1-contract。

#### P0-project-brief（项目摘要确认，不计入 27/24/15 项）

**目的**：在逐项澄清（H1/D1/…）之前，让用户对 Agent 的「项目理解」**对齐一次**；避免一上来就问 collocation、指标键，用户还不知道 Agent 是否看对了仓库。

**时机**

| 入口 | 何时发 P0 |
|------|-----------|
| **A（迁移）** | `migration-compare` exit 0 + [盘点表 v0](#阶段-0-现状盘点表入口-a-只读) 块 A–E 有草稿之后 |
| **B（新建）** | 已知 `profile` + 用户目标/数据描述之后；无 v0 则从【模板默认】+ 用户输入归纳 |

**本条消息结构（唯一允许「一条里多 bullet 讲全项目」的轮次）**

```markdown
### P0-project-brief — 请确认我们对本项目的理解

（以下 6～10 条 bullet，每条一句事实；禁止散文段落）

- **项目**：`<路径或项目名>`；入口 **A|B**；`profile=` …
- **迁移落点**（**仅入口 A**）：`source_root=` …（只读）→ `target_root=` …（**用户已确认**的建议路径；**≠ source**；**须为 git 仓库**，由 `new-project.sh` 创建）
- **训练范式**：…（如 PINN 配点 + Adam/L-BFGS / RL SAC+KNN / 监督 epoch）
- **数据**：…（如 无固定 train 集、实时配点 / `DATA_DIR` 离线 JSON / train-val-test 路径）
- **官方评估**：…（如 训末 SSFM → rL2_* / `contract.test` KNN / holdout test）
- **场景/多目标**：…（如 多 SIP 实验；当前主线场景 ID …；或「单场景待 D1 具名」）
- **主指标与 KEEP 习惯**：…（旧台账主指标、是否仅终评）
- **与模板差距**：…（`migration-compare` 一句：封装/评估/缺 README 等）
- **迁移高风险（待后续编号澄清）**：…（1～2 条，如「SIP 未钉」「训内无 evaluate」）

**请确认**：以上理解是否准确？

【确认选项】
| 你选 | 含义 |
|------|------|
| **①** | 理解正确 → 开始 HARD-GATE（下一消息才发 H1 或 D1） |
| **②** | 有偏差 → 请直接改 bullet / 补充（Agent 更新后再发一轮 P0） |
| **③** | 重大遗漏 → Agent 回阶段 0 补读仓库后再发 P0 |
```

**Agent 禁止（P0 轮）**

- 在本条出现 `H1`/`D1`/`D2` 的子问题或 ①②③ **锁定表**（那是后续编号的事）。
- 用户未 `P0=①`（或等价确认）就进入 `H1-legacy-artifacts` 及之后任一编号。

**P0=① 之后**

- 将用户确认后的 bullet 写入 **`<project_root>/.auto-nn/migration-summary.md`「项目摘要（P0 锁定）」** 节（并可选迁移笔记）。
- **下一条消息**：入口 A / B 均 → `D1-scenario-inventory`（入口 A 在 D 段结束后才进入 `H1-legacy-artifacts`）。

---

**五阶段**逐项确认：入口 A **`P0 → D → H → T → E1 → G → E2–E9 → O → F`**（**24** 项）；入口 B **`P0 → D → T → E1 → G → E2–E9 → O → F`**（**21** 项，无 H）。**D 段**：D1→D2→D3→D4；**G 段**：G1→G2（**E1 后、E6 前**）；**E 段** 9 项 slug 不变，问话顺序见 [阶段 E 编号约定](#阶段-e-编号约定)。**须先 D1（场景清单）→ D2（划分）→ T2 → E1 → G1/G2 → E4/E8**（E4/E8 仍须在 T2 之后）。逐项话术见下文。

**入口分支：**

| | 入口 A（迁移） | 入口 B（新建） |
|---|---|---|
| 有无源码 | 有 — Agent 提取现状作为提问基础 | 无 — 从零开始，Agent 提供模板默认值 + 空白选项 |
| 【现状】部分 | **【现状】** 从源码提取当前做法 | 改为 **【模板默认】**：展示模板 demo 的对应实现，作为参照 |
| 【模板建议】部分 | 对比现状与模板精神的差距，给出迁移建议 | 给出该 profile 的推荐做法（基于 profiles.yaml 语义） |
| 【确认选项】部分 | "按模板建议改 / 保持现状 / 自定义" | "按模板默认 / 自定义" |
| 阶段 H（历史） | **必须**：逐项确认旧台账/经验/文档的处理 | **跳过**：无历史数据 |
| 阶段 D（数据） | D2-data-split 必须确认源项目数据路径和划分逻辑 | D2-data-split 改为"你的数据在哪、格式是什么"，用户提供后 Agent 填入 |
| 阶段 T（训练） | T1-loss-layers 必须对照源项目的 loss 组成 | T1-loss-layers 改为"你的 loss 由什么组成"，用户描述后 Agent 映射到 build_objective |
| 阶段 O（运行） | O1/O2：探测**当前**本机 GPU、确认 `time_budget`/`max_parallel`；O3：该场景起步 plain+reference 尺子 | **同左**（`new-project.sh` 预填 gpus 仅作【模板默认】，**仍须**与用户确认；与旧仓历史无关） |
| 可跳过 | 现状已符合模板的项可标注"确认即可" | 无可跳过项，全部需用户确认 |

---

### 阶段 H：历史澄清（"怎么迁"）— History（仅入口 A，**在 D1–D3 之后**；入口 B 跳过）

**开场须写（H1）**：`D1 已确认场景 ID：…`（旧台账/exp 命名与场景对齐）。

#### 阶段 H 编号约定

- **格式**：`H<n>-<slug>`（**H1-legacy-artifacts～H3-agent-boundary**；问话顺序 = 数字顺序）。
- **F1-contract 汇总表**须用 slug 行名。

| 编号 | slug | 含义 |
|------|------|------|
| **H1-legacy-artifacts** | legacy-artifacts | 旧台账与实验产物 |
| **H2-experience** | experience | EXPERIENCE.md |
| **H3-agent-boundary** | agent-boundary | 旧文档硬约束 → README |

| # | 确认项 | 为什么问 | 答错的后果 |
|---|--------|---------|-----------|
| H1-legacy-artifacts | **旧台账与实验产物** | 旧 TSV/列名/checkpoint 与迁后 contract 不一致 | 脏数据 → keep 误判；旧 checkpoint 误导 |
| H2-experience | **EXPERIENCE.md** | 人类迭代经验（超参、踩坑） | 丢经验；或原样保留过时内容 |
| H3-agent-boundary | **旧文档硬约束候选** | 旧 README/PROTOCOL 有无须用户确认的硬约束；有则列候选、**F1-contract 勾选**；无则舍弃 | 全文提取 → 奇怪约束绑死 Agent |

**【模板建议】须给出默认推荐，不能只列选项。**

| 项 | 【模板建议】默认推荐 |
|----|---------------------|
| **H1-legacy-artifacts** | **① 舍弃**；要留历史最佳数字 → **③ 总结进 EXPERIENCE 后舍弃**；仅备查 → **② `_runs_legacy/` 归档** |
| **H2-experience** | **① 提炼重写**；无源文件 → **③ 重置** |
| **H3-agent-boundary** | 有硬约束候选 → **F1-contract 勾选** 后写入 README `AGENT_BOUNDARY` / 硬约束段；无或不可信 → **舍弃**（勿全文提取） |

**H3-agent-boundary 候选类型（勾选后映射 README `<!-- AGENT_BOUNDARY -->`）：**

| 类型 | 含义 | 典型落点 |
|------|------|----------|
| `schema_immutable` | 数据列/固有字段不可改 | `CONTRACT_IMMUTABLE` |
| `benchmark_protocol` | CR、划分、官方指标实现不可改 | `CONTRACT_IMMUTABLE` |
| `paradigm_frozen` | 某范式仅作对照 | `REFERENCE_ONLY` |
| `migration_scope` | 迁入子系统范围 | `MIGRATION_SCOPE`（D2-data-split 或 BOUNDARY 首行） |

**H1-legacy-artifacts 选「舍弃」时** 确认后自检：`_runs/results.tsv` 已删或已按迁后 contract `regen_results_tsv`。

#### H1-legacy-artifacts — 历史/命名线索（可选；仍属 H1-legacy-artifacts 一轮；**非**场景分析唯一入口）

**【现状】** 须引用 [阶段 0 现状盘点表](#阶段-0-现状盘点表入口-a-只读) **块 A**；并附（**有则填，无则整表写「无线索」**）：

| 线索来源 | 模式摘要 | 建议场景 ID | 不可比原因 |
|----------|----------|-------------|------------|
| 旧台账 / exp / 命名 / EXPERIENCE / 无 | （归纳前缀或配置模式） | 短 ID，供块 E / D2-data-split 核对 | 不同 test、数据根、协议等 |

**无旧台账 / 无 exp 命名习惯** → 子表写「无线索」；**块 E 五问仍须完成**（改扫 `train.py` / `contract` / `nn-config`）。

**【模板建议】** 有线索 → 写入块 E / H2-experience；H1-legacy-artifacts 选 ① 舍弃前若有线索建议先归纳。 **不得**因「无线索」跳过块 E。

**H2-experience 补充**：若 EXPERIENCE 含「轮换 / 勿跨某配置族比 KEEP」→ 记入块 E「KEEP 可比范围」与场景策略人话，供 E6/E9。

---

### 阶段 D：数据链路（"数据怎么来"）— **须在阶段 T、E 之前**

#### 阶段 D 编号约定

- **格式**：`D<n>-<slug>`（**D1-scenario-inventory → D2-data-split → D3-workspace-data → D4-repro-data**）；**D2 与 D3 之间**插入 [阶段 I 信息权限三问](#阶段-i信息权限谁能看什么-d2-之后d3-之前)（D2 定了数据，I 定谁能看）。
- **F1-contract 汇总表**须用 slug 行名。

| 编号 | slug | 含义 |
|------|------|------|
| **D1-scenario-inventory** | scenario-inventory | **场景清单**（四列白话表）；**须先于 D2** 用户签字 |
| **D2-data-split** | data-split | 数据契约 + 划分 + 每场景 OFFICIAL_TEST |
| **D3-workspace-data** | workspace-data | 训内数据处理在 workspace |
| **D4-repro-data** | repro-data | 复现数据路径/版本 + `REPRO_ENV_KEYS` 数据项 |

| # | 确认项 | 为什么问 | 答错的后果 |
|---|--------|---------|-----------|
| D1-scenario-inventory | **场景清单签字** | 先钉「有几个官方世界、各测什么、运行档冻结什么」；**禁止**拖到 E6 才问 SIP/方法族 | D2/E3/E9 无场景锚点 → default 糊弄、跨 SIP 混 KEEP |
| D2-data-split | **数据契约钉死** | 在 D1 已列 ID 下钉划分语义 + 每场景 test；见下专节 | 数据根漂移、val/test 混淆 → 不可比 / 误 KEEP |
| D3-workspace-data | **训内数据处理** | 增广/课程等在 workspace；不得污染 E2 eval 题集 | Agent 改错环节 |
| D4-repro-data | **复现数据钉死** | 复现须对齐数据根/版本；写入 `contract/runtime.py` `REPRO_ENV_KEYS` 与 `exp_dir` `_repro` | 只看 `config.json` 不知 v2/v3；复现读错 CSV |

#### D1-scenario-inventory — 场景清单（必遵；**P0 之后、D2 之前**；入口 A 为 **#1**）

**本编号 = 块 E 五问 + 场景清单表的用户确认轮**；阶段 0 只填 v0 草稿，**不得**代替本轮回话。

**对用户话术**：清单表头固定四列——**数据与指标** | **默认配置（起跑线）** | **后面允许试什么** | **成绩和谁比**（勿写 S_data / S_run / Agent 探索）。

**开场须写**：`盘点表块 E v0：…`（若无 v0 须先扫代码补草稿再发问）。

**【现状】** 引用 [块 E](#块-e--场景与运行档v0-草稿--d1-scenario-inventory-用户确认--d2e6e7e9) 五问 + 清单表（含 **S_method** 列：plain/flow、PINN SIP 等，禁止多方法压成一行 `default`）。

**【为什么问】** 先场景、后数据划分：否则 D2 会问 SSFM 路径却还不知道官方测哪个 SIP/哪种方法族。

**【模板建议】** 清单 ≥1 行；每行 **数据与指标**、**默认配置（起跑线）** 非空；**后面允许试什么** 在 **G1/G2 之后的 E6** 定轴，D1 可先写「待定」。

**【监督类项目推荐(2026-07 起)】** ≥2 行：
- **reference**（复现源项目内置基线，如 mammoth 内置 er / derpp / der / er-ace / icarl / bic 等）—— 与源项目 1:1 对齐，保证可比；
- **automatic**（Agent 搜索新方法 / 新 backbone / 新正则；命名须与 reference 池不重名）。

两池在 F1-contract **分开 KEEP**（同一数据下 baseline 池内历史最优 vs explore 池内历史最优）。监督类 v0 仅 single-baseline 时，Agent 须提示用户「建议拆为 reference + automatic 两场景」。

**【确认选项】**

| 你选 | F1-contract 写什么 |
|------|-------------------|
| **①** | 采纳 v0 清单（可改 ID/补 S_method 行；监督类项目推荐 **reference + automatic 双场景** ） |
| **②** | 用户重写清单（仍须 ≥1 行 + 默认配置） |
| **③** | 确认仅 1 个官方场景但仍须**具名 ID**（如 `ngl01_sip3_mix`），禁止空 `default`（监督类不推荐，违反可比性原则） |

**【选后锁定】** 场景 ID 列表 → D2 `SCENARIO_CANDIDATES`；清单全文 → F1-contract「场景清单」表。

**Agent 禁止**：在 D1 之前问 D2 可比性子集；在 D1 未确认时写「仅 default」。

#### 迁入推荐铁律（入口 A / migrate · 必遵）

**「推荐」= 源对齐，不是模板理想。**

| 入口 | 「我的建议」/ 选项「（推荐）」落点 |
|------|-----------------------------------|
| **A 迁入** | 与 `source_root` **可核对设定 1:1**（划分、训内 eval 是否看官方 test、默认增强、主指标定义、调用链默认等） |
| **B 立项** | 可推模板理想（公平划分、独立 val、test 只终评等） |

**禁止（迁入）**：把「更公平 / 更规范」改进标成推荐（例：源项目 5 万全训且每圈看 test → **推荐必须是保持源设定**；三段划分 / 只终评只能作备选并写清「与源表不同口径」）。  
**自检**：发出 D2 / E4 / T2 等问句前，核对「（推荐）」是否仍指向源行为；若推荐项与源码不一致 → **改标签后再发**。

#### D2-data-split 数据划分确认表（必遵）

**禁止**仅用一句「80/20 划分」带过。Agent 须按 **profile** 向用户确认后，将结果写入 **F1-contract** 并迁后写入 `README.md`（verify 硬检）。

**每条 D2-data-split 问题仍含四段**：【现状/模板默认】、【为什么问】、【模板建议】、【确认选项】。

**README 落盘格式**（阶段 2 改码前须有草稿，阶段 3 定稿；键名固定）：

```markdown
## D2 数据划分（F1-contract 锁定）

<!-- D2_DATA_SPLIT -->
PROFILE: <supervised|rl|physical>
DATA_ROOT: <路径>
...（见下表 profile 必填键）
<!-- /D2_DATA_SPLIT -->
```

**supervised 必填键**

| 键 | 向用户确认什么 |
|----|----------------|
| `SPLIT_KIND` | `train_val_test` / `train_val_holdout_test` / `train_holdout_no_val` / `custom`。**入口 A（迁入）**：**推荐 = 源项目切分 1:1**（`MIGRATION_DATA_ALIGN=source_split`；CIFAR 类「全训 + 每圈看官方 test、无独立 val」亦属源对齐，**不得**把三段划分标成推荐）。**入口 B（立项）** 才默认可推教科书式 train/val/test。KEEP 数据根与源项目相同（迁入）。 |
| `TRAIN` | 哪些样本/文件/索引 |
| `VAL` | 定义；无则写 `none` |
| `TEST` | 官方 test（仅 `contract.test`） |
| `NORMALIZE_FIT_ON` | 归一化/scaler 仅在何集合 fit |
| `EVAL_USES` | `ws.evaluate` 用哪个 loader（**迁入**：默认跟源；源每圈看 test → 可与 `TEST_USES` 同集，须在建议里写清「接受偷看偏差以对齐源表」；**立项** supervised 默认可推独立 val） |
| `TEST_USES` | `contract.test` 用哪个 loader/函数（仅官方 test） |
| `E4_EVAL_FOR_KEEP` | 固定写：`contract.test only`（`_runs/round_decision.json`） |
| `VAL_TEST_SAME_DISTRIBUTION` | `yes` / `no` / `na`；**no** 时须写「禁止用 val 推断 KEEP / test 表现」 |
| `MIGRATION_DATA_ALIGN` | 入口 A 专用：`source_split`（**唯一默认可标推荐**）/ `custom`（备选，须说明原因与口径差） |

#### D2-data-split — 可比性子集 / 场景候选（子表，仍属 D2-data-split 一轮）

**开场须写**：`D1 已确认场景 ID：…`（与下表一致；**禁止**写「块 E」代替 D1 签字）。

| 子项 | 向用户确认 |
|------|------------|
| 是否存在 **>1** 个官方可比世界 | 无 → **仍须** D1 具名单场景 ID；有 → 逐行列 ID（**须**与 D1 清单一致） |
| 每世界的 **TEST / OFFICIAL_TEST** | 与上表 profile 必填键一致 |
| 默认官方场景 | → `EVAL_SCENARIO:`（单场景可 `default`） |
| val≠test 分布 | `VAL_TEST_SAME_DISTRIBUTION=no` 时须单独成行或注明 val 不进 KEEP |

**README 可选（`<!-- D2_DATA_SPLIT -->` 末）：**

```text
EVAL_SCENARIO: default
SCENARIO_CANDIDATES: default
```

多候选：`SCENARIO_CANDIDATES: id1|id2`。**权威明细**在 F1-contract「场景清单」表。

**快速路径不可跳过本 sub表**（可「确认即可」，但须写出候选 ID）。

**D2-data-split 可选键（多场景 / 迁移范围）**

| 键 | 何时填 |
|----|--------|
| `EVAL_SCENARIO` | 官方默认场景 ID；单场景可 `default` 或省略 |
| `MIGRATION_SCOPE` | 入口 A：迁入子系统范围（如 `compression_only`） |

**README `<!-- SCENARIO_POLICY -->` 块（二期；多场景 F1-contract 后必填）**

| 键 | 含义 |
|----|------|
| `SCENARIO_AXIS` | 场景维度名；无则 `na` |
| `ACTIVE_SCENARIOS` | 逗号分隔 ID |
| `SCENARIO_POLICY` | `focus` \| `rotate` \| `multi_eval_one_train` |
| `DEFAULT_SCENARIO` | focus 时默认场景 |
| `KEEP_HISTORY_FILTER` | 建议与 `contract.history_experiment_substr` 一致 |
| `TRAIN_BINDS` | `single` \| `multi` |

业务仓 `scripts/scenario_policy_gate.py` + verify §6d 在校验（`SCENARIO_AXIS`/`EVAL_SCENARIO` 非 na 时块须完整）。

**RL 必填键**（无经典 train/val/test）

| 键 | 向用户确认什么 |
|----|----------------|
| `SPLIT_KIND` | `none` 或 `rl_benchmark` |
| `NO_CLASSIC_SPLIT` | `yes` |
| `TRAIN_DATA_SOURCE` | 离线 JSON / env / replay 路径 |
| `OFFICIAL_EVAL` | 冻结题集、`mode=knn`、episode 等（与 E2 一致） |

**physical 必填键**（README `D2_DATA_SPLIT`；`d2_data_split_gate.py` 硬检）

| 键 | 向用户确认什么 | 迁后能否改？ |
|----|----------------|--------------|
| `SPLIT_KIND` | `collocation` / `domain`：**无**经典 train/val/test **文件划分** | **否**（改语义须重迁 D2） |
| `TRAIN` | 固定训练集文件；PINN 写 `none` | **否** |
| `VAL` | 固定验证集；PINN 写 `none` | **否** |
| `TRAIN_SAMPLING` | **一句语义**（见下「格式」）；**禁止**只写函数调用 | **语义否**；实现见 `SAMPLING_TUNABLE` |
| `SAMPLING_TUNABLE` | `yes`：配点策略/n_pde/采样函数在 **workspace/超参** 可调，**不**算改 D2 | 恒 `yes`（PINN 常规） |
| `EVAL_USES` | 训内 proxy（`ws.evaluate`）；未实现写 `reserved` | E4 定是否调用 |
| `OFFICIAL_TEST` | 训末 SSFM npz **路径规则** + 指标名（细节在 E3/H3） | **否** |
| `E3_EVAL_FOR_KEEP` | `contract.test only` | **否** |
| `VAL_TEST_SAME_DISTRIBUTION` | PINN 写 `na` | — |

`TRAIN_SAMPLING` **推荐格式**（单行即可，须含「无固定训练集」类表述）：

```text
TRAIN_SAMPLING: 语义=训内 (z,x,y,t) 域实时 PDE 配点，无固定 train/val 文件
```

可选第二行（**不**进门禁必填）：`SAMPLING_IMPL_NOTE: 当前 workspace.importance_sample（迁后可换）`

#### D2-data-split — physical/PINN 问话包（必遵）

**本包解决**：用户误以为 D2 要把 `importance_sample`「条码锁死」——须先把 **划分语义** 与 **采样实现** 拆开问。

**Agent 禁止**

- 把 `importance_sample(n_pde, …)` 当作【模板建议】或【选后锁定】的主文案。
- 说「配点/importance 不可调」或「改采样 = 改 contract 数据段」。
- 在 **D1 未确认** 时问 D2 可比性子集；或用「仅 default」带过——须引用 **D1** 已列 `SCENARIO_ID`。

**Agent 必须先展示【现有清单】**（从代码/README 归纳，勿照抄函数名当结论）

| 项 | 填什么 |
|----|--------|
| 有无 `data/train` 类固定训练集 | 有/无 |
| 训练点如何产生 | 如「`train_step` 内实时采样」 |
| 当前采样实现（**脚注**） | 如 `workspace.importance_sample` |
| 官方 test 数据 | SSFM `ssfm_reference.npz` 路径规则 |
| KEEP 用谁 | 仅 `contract.test` / 训内 proxy |

**【为什么问】**（对用户原话，二选一展开）

> 不是不让你调配点。是要钉死：**没有 val 文件夹**、**KEEP 只看 SSFM 终评**，免得 Agent 按监督学习去找 `data/val/` 或用训内 loss 做 KEEP。

**【模板建议】** ① 采纳语义锁（推荐）

**【确认选项】**

| 你选 | .auto-nn/migration-summary / README 写什么 | 和【现状】差别 |
|------|---------------------------|----------------|
| **①** | 上表 physical 键 + `SAMPLING_TUNABLE: yes`；`TRAIN_SAMPLING` 写**语义句**；`SAMPLING_IMPL_NOTE` 可写当前函数 | 明确：**采样可调**；只锁划分与 SSFM test |
| **②** | 用户自定义划分语义（仍须 `TRAIN`/`OFFICIAL_TEST`/`E3_EVAL_FOR_KEEP`） | 用户指定 |

**【选后锁定】**（用户选 ① 后 Agent 必须复述，防误解）

| 锁定（改须重过 D2/H3） | 不锁定（常规迭代可改） |
|------------------------|------------------------|
| 无经典 train/val/test **文件**；`SPLIT_KIND=collocation`（或 ② 自定义语义） | `importance_sample` / uniform / `n_pde` / 域范围 |
| `OFFICIAL_TEST` = SSFM 路径**规则** + 终评指标族 | 具体网格点数、tau chunk（→ **E3**） |
| `E3_EVAL_FOR_KEEP=contract.test only` | PDE 残差与辅助 loss（→ **T1**） |
| SSFM **不参与训练**（若 H3 已勾选） | `norm_mode` 若未进 H3 则按 H3 表 |

**README 示例（PINN，块须通过门禁）**

```text
<!-- D2_DATA_SPLIT -->
PROFILE: physical
DATA_ROOT: data/
SPLIT_KIND: collocation
TRAIN: none
VAL: none
TRAIN_SAMPLING: 语义=训内 (z,x,y,t) 域实时 PDE 配点，无固定 train/val 文件
SAMPLING_TUNABLE: yes
SAMPLING_IMPL_NOTE: workspace.importance_sample（迁后迭代可替换，不视为改 D2）
EVAL_USES: ws.evaluate proxy（训内可选；见 E4）
OFFICIAL_TEST: data/ssfm_gamma{gamma_ssfm:.2e}_{mode}/ssfm_reference.npz；指标 rL2_s,rL2_t,P_ratio
E3_EVAL_FOR_KEEP: contract.test only
VAL_TEST_SAME_DISTRIBUTION: na
EVAL_SCENARIO: ngl01_sip3_mix
SCENARIO_CANDIDATES: ngl01_sip3_mix
<!-- /D2_DATA_SPLIT -->
```

**D2-data-split 与 E4-train-eval 分工**：**先 D2-data-split** 钉 `EVAL_USES` / `TEST_USES`；**再 E4-train-eval** 钉训内是否调 `evaluate`、频率。**supervised**：训内 eval **算分方式与 test 相同**（共用指标实现），仅 loader 不同 — 见阶段 E 默认 `E4_PATH=②-same-metrics`。

### 阶段 I：信息权限（"谁能看什么"）— **D2 之后、D3 之前**

> 三问的每个答案都对应 `contract/runtime.py` `INFO_PERM` 的一个字段；训练前守门 **G-信息权限**（`scripts/lib/info_perm.py`，无 env 旁路）据此静态扫描，`scripts/info_perm_gate.py` 对账 README 块。**只问机器能拦的**；机器拦不住的规矩在 I3 标「机器不管」。

#### 阶段 I 编号约定

- **格式**：`I<n>-<slug>`（**I1-train-consumes → I2-official-path → I3-other-info-rules**）；入口 A 为 **#3–#5**，入口 B 亦为 **#3–#5**；update 亦问（15 步内按 reference 题序）。
- **F1-contract 汇总表**须用 slug 行名；锁文本用态 1 编码（`I1.CONSUMES=…; I1.EVAL_ONLY=[…]`），题库 `docs/init/init-question-registry.yaml` 给模板，`scripts/init_answers.py lock --slug I1 --choice B --field …` 可直接渲染。
- **人话主题**：**信息权限**。三问衔接句（第 3 步开场）：「接下来三问定死：训练能用哪些材料、官方分从哪条路出来、还有没有别的信息规矩。」

| # | 确认项 | 为什么问 | 答错的后果 |
|---|--------|---------|-----------|
| I1-train-consumes | **训练许用材料** | 哪些数据训练能碰、哪些只评；机器拦的是**训练真打开只评文件或真调用只评函数**（预留选项、默认不用不算犯规） | Agent 训练时偷看标准答案 → 成绩虚高、对照实验失真 |
| I2-official-path | **官方打分通道** | 官方分是整网前向还是必须走受限手续（如只凭规定码还原）；机器据此要求 `contract/test.py run()` 必调手续函数并守交卷缝（IP4/IP5） | 旁路（skip connection、直接用输入）把受限任务算成整网任务 |
| I3-other-info-rules | **其他信息规矩** | 兜底：还有没有别的信息不许乱流；机器只管训练 batch 键白名单（IP2），其余记 README 供人审 | 规矩只在人脑里，换 Agent 就丢 |

**依赖**：I1 依赖 D2（数据与划分已列出）；I2 依赖 D2 + I1；I3 依赖 I1 + I2。E3-official-test 须与 I2 一致（C-I2）；D3 须与 I1 一致（C-I3）。

#### 迁入铁律（入口 A · I1/I2 为源对齐题）

**「推荐」= 源项目实际怎么做**：I1 推荐项须与 `source_root` 训练脚本实际读取的文件集一致；I2 推荐项须与源项目官方打分脚本实际调用链一致（源码里官方分必须走规定手续、不能换一条路算 → 推荐 B）。**禁止**把「更严」标成推荐。带 `--answers` 时 I1/I2 清单值与源码不一致 → 必出卡片「清单说 X，源项目是 Y」，不得静默跳问。

#### I1-train-consumes — 训练许用材料（必遵；**D2 之后**）

**开场须写**：`D2 TRAIN=…；OFFICIAL_TEST=…`（引用 D2 已锁划分）。

| 部分 | 内容 |
|------|------|
| 【现状】/【模板默认】 | 入口 A：源训练脚本读了哪些文件（Agent 扫 `open` / `np.load` / `loadmat` / DataLoader 源）；入口 B：模板默认 `eval_only_assets=()`（全部可训） |
| 【现有清单】 | D2 `TRAIN` / `VAL` / `TEST` / `OFFICIAL_TEST` 各指向的文件或生成函数；合同里哪些文件读它们 |
| 【为什么问】 | 只评资产一旦被训练真用到，成绩不可信；机器拦的是真打开 / 真调用，不是源码里出现过文件名。工作区可以预留选项，默认不用不算犯规 |
| 【模板建议】 | 有独立官方测试集 → **B**；样本由公式/配点现算、无数据文件 → **C**；确无只评部分 → **A** |
| 【确认选项】 | **A** 全部数据都能训 / **B** 只能用训练份，以下只用来打分：`<资产列表>`（允许读它的合同文件：默认 `contract/test.py`，Agent 扫合同补全后请人确认）/ **C** 训练不读任何数据文件，起点和方程都是公式现算（只评资产可为 `contract.` 读取函数名，如生成参考解的函数） |
| 【选后锁定】 | **A** → `I1.CONSUMES=all; I1.EVAL_ONLY=[]; I1.STRICT=no`；**B** → `I1.CONSUMES=train_split_only; I1.EVAL_ONLY=[…]; I1.READERS=[…]; I1.STRICT=no`；**C** → `I1.CONSUMES=no_files; I1.EVAL_ONLY=[…]; I1.READERS=[…]; I1.STRICT=yes` |

**Agent 禁止**：把 D2 `OFFICIAL_TEST` 指向的数据在 I1 标为「全部能训」而不说明（C-I5；**豁免**：T1 常见可试 data-loss 开且 F1 写明「场可进训练、官方分仍打该场」）；选 B/C 却不列资产（C-I1）。

#### I2-official-path — 官方打分通道（必遵；**I1 之后**）

| 部分 | 内容 |
|------|------|
| 【现状】/【模板默认】 | 入口 A：源官方打分脚本从输入到分数的调用链（有无规定手续 / 固定评测态）；入口 B：模板默认 `official_path=full_model` |
| 【现有清单】 | 源打分脚本 ≤5 行调用链；手续函数名（若有）；任务自己的受限条件一句 |
| 【为什么问】 | 官方分必须和任务规定的打分方式一致；机器要求 `contract/test.py run()` 必调手续函数、交卷开关 `_official_path_enabled()` 单条 return、工作区不得改交卷缝 |
| 【模板建议】 | 源码有手续 → **B**（写函数名 + 一句规则）；打分须固定状态（eval 模式 / 固定随机源等）→ **C**；否则 **A** |
| 【确认选项】 | **A** 整网前向：模型看输入直接出结果 / **B** 受限路径：官方分必须走规定手续（手续函数 `<impl>`；规则一句）/ **C** 固定评测态：必须在指定状态下打分（手续函数 `<impl>`；规则一句） |
| 【选后锁定】 | **A** → `I2.PATH=full_model; I2.IMPL=none`；**B** → `I2.PATH=restricted; I2.IMPL=<impl>; I2.RULE=<一句>`；**C** → `I2.PATH=eval_mode_locked; I2.IMPL=<impl>; I2.RULE=<一句>` |

**与 E3 分工**：I2 定「通道是什么」；E3 定「训末怎么跑 `contract.test`」，E3 行须引用 I2（「run() 必经 `<impl>`」）。

#### I3-other-info-rules — 其他信息规矩（必遵；**I2 之后**）

| 部分 | 内容 |
|------|------|
| 【现状】/【模板默认】 | 模板默认 `train_batch_keys=None`（不校）；无其他规矩 |
| 【现有清单】 | I1/I2 已覆盖的规矩（不重复）；候选：训练 batch 只许含哪些键、某中间量不得进 loss、某标签只评等 |
| 【为什么问】 | 兜底一问，避免规矩只在人脑里；机器只能拦「训练首 batch 键白名单」，其余标「机器不管」进 README 供人审 |
| 【模板建议】 | 多数项目 **均无**；有额外规矩再逐条列（机器能拦的只有训练 batch 键） |
| 【确认选项】 | **均无** / **逐条列出**（每条一句；机器能拦的只有 batch 键白名单，其余自动标「（机器不管）」） |
| 【选后锁定】 | 均无 → `I3.RULES=none; I3.MACHINE=none`；逐条 → `I3.RULES=[…]; I3.MACHINE=[batch_keys=…]` |

#### 三问 → `INFO_PERM` / README 投影表（阶段 2 首步机械落表）

| 答案 | `contract/runtime.py` `INFO_PERM` | README `<!-- INFO_PERM -->` 行 |
|------|-----------------------------------|-------------------------------|
| I1=A | `eval_only_assets=()`；`strict_no_train_files=False` | `TRAIN_CONSUMES: A 全部数据都能训` |
| I1=B | `eval_only_assets=(<资产…>,)`；`eval_only_readers=(<读者…>,)`；`strict_no_train_files=False` | `TRAIN_CONSUMES: B 只有训练份；只评：<资产>（读者：<读者>）` |
| I1=C | 同 B 且 `strict_no_train_files=True` | `TRAIN_CONSUMES: C 无数据文件（样本由代码生成）；只评：…` |
| I2=A | `official_path="full_model"`；`official_path_impl=None` | `OFFICIAL_PATH: A 整网前向` |
| I2=B / C | `official_path="restricted"` / `"eval_mode_locked"`；`official_path_impl="<impl>"` | `OFFICIAL_PATH: B 受限路径（<impl>）：<规则>` / `C 固定评测态（<impl>）：<规则>` |
| I3 均无 | `train_batch_keys=None` | `OTHER_RULES: 均无` |
| I3 逐条 | `train_batch_keys=(<键…>,)`（无键则 `None`） | `OTHER_RULES: <条…>（机器管：训练 batch 键 …）` |
| T1 常见可试 data-loss **关**（缺省） | `enforce=True` | `ENFORCE: yes` |
| T1 常见可试 data-loss **开** | `enforce=False`；且 I1 不得为「训练不读数据文件」（C-DL1） | `ENFORCE: no` |
| — | `official_path_switch="_official_path_enabled"` | （函数名，两臂相同） |

**阶段 2 首步命令**（在 `<project_root>`；`NN_RELAUNCH=1` 语境）：

```bash
# 现场一问一答：按锁文本填参数
python3 scripts/init_info_perm.py write --repo-root . \
  --consumes B --eval-only-assets <glob|contract.func> --eval-only-readers contract/test.py [--eval-only-readers …] \
  --official-path B --official-path-impl <impl> --official-path-rule "<一句>" \
  --other-rules 均无 [--train-batch-keys k1 --train-batch-keys k2]
# 带 --answers：直接用清单归一结果
python3 scripts/init_info_perm.py write --repo-root . --from-resolved .auto-nn/init-answers.resolved.json
# --enforce 由 T1 常见可试 data-loss 投影（关=yes / 开=no）；禁止再手改 INFO_PERM.enforce
python3 scripts/info_perm_gate.py .      # 写后脚本已自动对账；此处复核 exit 0
```

I2=B/C 时阶段 2 还须在 `contract/test.py` 把 `_official_forward()` 改为调用 `<impl>`，并保持 `_official_path_enabled()` 单条 `return True`（模板缝已留；见 `template/package/contract/test.py`）。

**填法示例（两种典型形态）**

| 形态 | I1 | I2 | I3 |
|------|----|----|----|
| 有独立终评材料 + 官方分必须走规定手续 | B：只评终评材料；读者写合同打分文件 | B：手续函数名；任务自己的那一句规则 | 均无 |
| 训练不读数据文件、参考解打分时现算 | C：只评生成参考解的合同函数 | A：整网前向 | 有额外规矩再逐条列；机器能拦的只有训练 batch 键 |

#### D4-repro-data — 复现数据（必遵；**D3 之后**；入口 A 在 H1 之前）

**开场须写**：`D2 DATA_ROOT=…`；本问钉**复现时必须一致**的数据 env（D2=划分语义；D4=读哪套文件/版本）。

| 部分 | 内容 |
|------|------|
| 【现状】 | 数据根 env（如 `NN_INDIVIDUAL_DIR`）；v2/v3 等多套目录是否并存 |
| 【为什么问】 | `finalize_run` → `config.json` `_repro.repro_env`；无 D4 则复现不知数据版本 |
| 【模板建议】 | `contract/runtime.py` `REPRO_ENV_KEYS` 含数据项；写清默认路径与等价关系 |
| 【确认选项】 | ① 采纳键表+默认路径 / ② 用户增补 env / ③ 无 env 则 F1 写死相对路径 |

**【选后锁定】** → F1「复现配方」数据行 + `EXPERIENCE.md`；阶段 2 写入 `REPRO_ENV_KEYS`。

### 阶段 E：评估链路（"怎么量"）— **在 D2-data-split、T1-loss-layers/T2-callchain 之后**

#### 阶段 E 编号约定

- **格式**：`E<n>-<slug>`（`n` 与问话顺序一致，**E1…E9 连续**）。
- **E 段固定 9 项**，按 **E1→E9** 逐编号一问；**E6-scenario**、**E7-run-context** 为**条件必问**（仍占一轮，无场景时可快速答「不适用」）。
- **训内返回键**并入 **E4-train-eval** 的确认与 F1-contract 自检，不单独占编号。

| 编号 | 含义 | 必问 |
|------|------|------|
| **E1-metrics** | 主/辅指标定义 | 是 |
| **E2-metric-tier** | 指标列分级 primary/aux/notes | 是 |
| **E3-official-test** | 训末 `contract.test` 口径 | 是 |
| **E4-train-eval** | 训内 evaluate 路径与节奏（**T2-callchain 后**；含返回键自检） | 是 |
| **E5-tsv-columns** | TSV 四区 + 列覆盖 | 是 |
| **E6-scenario** | 场景轴、探索策略、KEEP 对照池 | 条件 |
| **E7-run-context** | 运行参数列 `ledger_context_keys` | 条件 |
| **E8-checkpoint** | 模型保存时机与权重口径 | 是 |
| **E9-keep** | KEEP 阈值与 `history_experiment_substr` | 是 |

**问话顺序（= 步号 #10–#20；slug 仍 E1…E9，G 插在 E1 与 E2 之间）**：

```text
E1-metrics → G1-experiment-mode → G2-goal-value
  → E2-metric-tier → E3-official-test → E4-train-eval → E5-tsv-columns
  → E6-scenario → E7-run-context → E8-checkpoint → E9-keep
```

（**宏观**：H → D → **T** → **E1 → G → E2–E9** → **O** → F。**E6-scenario 须在 G1/G2 之后**并引用 G1 人话结论。**E4-train-eval**、**E8-checkpoint** 须在 **T2-callchain** 之后并引用调用链。）

| # | 确认项 | 为什么问 | 答错的后果 |
|---|--------|---------|-----------|
| E1-metrics | **metrics 定义** | 主/辅指标决定 keep/discard 与 TSV 主列 | 主辅分错 → keep 误判；不互斥 → preflight 报错 |
| E2-metric-tier | **指标列分级** | 谁进 KEEP、谁仅 notes | 关键维在 notes → 扫表漏项 |
| E3-official-test | **`contract.test` 操作说明** | 训末 test 用什么数据、怎么跑（对齐 D2-data-split） | 口径错 → 台账不可比 |
| E4-train-eval | **训内 evaluate（PATH + 节奏）** | **T2-callchain 后**；训内/台账口径分离 | 与循环不一致；漏键 |
| E5-tsv-columns | **TSV 四区 + 列覆盖** | 场景/metrics/parameters/notes 分区；metric+auxiliary+ledger 齐全；**系统列 `baseline_tag` 必有** | 缺列或 KEEP 键在 notes → 扫表/KEEP 失效；缺基线角色列 → 认不出尺子 |
| E6-scenario | **场景探索方案** | 在 G1 **实验模式**下钉「每轮改什么、场景排期、KEEP 分池」；Agent manifest | 模式与方案脱节；跨场景混比 KEEP |
| E7-run-context | **运行参数列** | 非 metric 的 cfg 进 TSV，不参与 KEEP | 只能靠 experiment 名猜场景 |
| E8-checkpoint | **模型 checkpoint** | 何时存、存 best/last/none、与台账指标口径 | 权重与 official 指标不一致；KEEP 无文件 |
| E9-keep | **KEEP 策略** | 阈值、`improve_mode`、`history_experiment_substr`（**须**映射 F1-contract 场景清单 KEEP 列） | 跨场景混比；substr 空而清单多行 |

**E9 开场须写**：`块 E 成绩和谁比：…`；`history_experiment_substr` / yaml keep 须与此一致。清单多行且 **数据与指标** 不同而 substr 为空 → **不得**确认 E9。

#### E1-metrics — 指标族标注（E1 用户确认后立即内部记录）

E1 用户确认后，Agent **内部**标注 `metric_family`（**不对用户展示 M1–M6**；写入 init-qa-log `lock` 摘要用人话，如「比例类准确率」）：

| 族 | 判定（主指标） | 典型例子 |
|----|----------------|----------|
| **M1** | 比例 / 概率，越大越好，∈ [0,1] 或等价比率 | `test_acc`、`AUC`、`F1` |
| **M2** | 损失，越小越好 | `cross_entropy`、`train_loss`、`NLL` |
| **M3** | 误差 / 距离，越小越好 | `MSE`、`RMSE`、`MAE` |
| **M4** | 相对误差，越小越好 | `rL2`、`rel_error` |
| **M5** | 回报 / 得分，越大越好 | `return`、`episode_reward` |
| **M6** | E1 已写清但不进上表 | 通用相对三档 |

**量纲**：acc 为 0–100 时 F1 写清展示口径；落盘 relative 仍按比例（0.1% = 0.001）。

**G2 / E9 查表真源**：[`metric-family-keep-presets.yaml`](metric-family-keep-presets.yaml)。

#### E9-keep — KEEP 进步线（按指标族选型）

**目的**：钉「单次实验比历史最好好多少才算更好、要留下来」——与 G2「最终达标停」**不是一条线**。

**硬规则**

- **禁止**无档位建议即写入模板默认 `primary_delta: 0.005`
- **禁止**快速路径「确认即可」
- **不要求** baseline、旧 TSV、smoke；依据 **E1 指标族** 给档
- 用户选档后落盘 `nn-config.yaml` `keep`（`contract.keep_threshold={}` 时生效）
- 话术注明：迁后可改 `keep` 段；goal 仍走 `/auto-nn-goal`

**Agent 四段式（对用户）** — 见 [`SKILL.md`](SKILL.md) §5.3；选项 **必须** option 卡片（A/B/C/D），每档附 **一句理由**（来自 presets 或 reference 下表）。

**E9 档位表（与 presets 同步）**

##### M1 — 比例 / 概率（越大越好）

| 选项 | 人话 | 内部 | 理由 |
|------|------|------|------|
| **A（推荐）** | 涨 0.1% | `relative`, `0.001` | 高平台期波动常见在这一档；适合微调 |
| B | 涨 0.2% | `0.002` | 略严，仍允许稳定小步 |
| C | 涨 0.5% | `0.005` | 旧默认；只留大 jump，易长期无 KEEP |
| D | 自定义 | 用户给 | 极不平衡等 |

##### M2 — 损失（越小越好）

| A（推荐） | 降 1% | `relative`, `0.01` | 相对稳 |
| B | 降 0.5% | `0.005` | loss 已很低时 |
| C | 降 2% | `0.02` | 早期快速下降 |
| D | 自定义 | | |

##### M3 — 误差 / 距离（越小越好）

| A（推荐） | 相对降 1% | `relative`, `0.01` | 不知绝对尺度时最稳 |
| B | 相对降 0.5% | `0.005` | 更严 |
| C | 相对降 2% | `0.02` | 只留大改善 |
| D | 自定义；E1 有典型量级可 absolute | | |

##### M4 — 相对误差（越小越好）

| A（推荐） | 再降 0.01 | `absolute`, `0.01` | 本身已是相对量 |
| B | 再降 0.005 | `absolute`, `0.005` | 更严 |
| C | 再降 0.02 | `absolute`, `0.02` | 只留大改善 |
| D | 自定义 | | |

##### M5 — 回报（越大越好）

| A（推荐） | 涨 2% | `relative`, `0.02` | RL 方差大 |
| B | 涨 1% | `0.01` | 环境稳定时 |
| C | 涨 5% | `0.05` | 只留明显变好 |
| D | 自定义 | | |

##### M6 — 其它

| A（推荐） | 相对 1% | `relative`, `0.01` | 通用 |
| B | 相对 0.5% | `0.005` | 更严 |
| C | 相对 2% | `0.02` | 更松 |
| D | 自定义 + F1 写量纲 | | |

**F1-contract 附件 — KEEP 进步线**

```text
KEEP_IMPROVE_MODE: any_primary
KEEP_MODE: relative | absolute
KEEP_PRIMARY_DELTA: <用户所选>
KEEP_NEAR_BEST_ABS: 0
单次进步线（人话）: <例：test_acc 相对涨 0.1%>
```

**阶段 2 yaml 示例**

```yaml
keep:
  improve_mode: any_primary
  mode: relative
  primary_delta: 0.001
  near_best_abs: 0.0
```

#### E4-train-eval — 训内评估（须在 T2-callchain 之后）

**开场须引用 T2-callchain**：`外层循环=…`；`每圈后 evaluate=是/否`；`训末 contract.test=…`（与 D2-data-split `EVAL_USES`/`TEST_USES` 一致）。

**迁入推荐（与「迁入推荐铁律」一致）**：源项目若每圈在官方 test 上打分 → **「我的建议」= 保持源节奏与同集**（可写清偷看偏差）；**禁止**把「只终评 / 独立 val」标成推荐（备选即可）。立项才默认可推独立 val + 稀疏/只终评。

#### E8-checkpoint — 模型保存（须在 T2-callchain 之后）

| 部分 | 内容 |
|------|------|
| 【现状】 | 是否只存 `best_model.pt`、训内 eval 最优 vs 训末 last、`.pt` 是否含超参（对照 **T2-callchain 填空表**） |
| 【为什么问】 | KEEP 复制 checkpoint；复现需完整 `train_cfg`；physical 常无训内 eval |
| 【模板建议】 | `nn-config.yaml` → `checkpoint: best \| last \| none`；`.pt` 内 **`train_cfg` 全量训练超参** + `metrics_official`（`contract.test`）+ 可选 `metrics_train_eval`（训内选 best 时） |
| 【确认选项】 | ① **last**（无训内 evaluate / PINN 推荐） / ② **best**（有训内 evaluate 且按主指标选优） / ③ **none**（只保留 commit+台账） |

**策略说明（实现已对齐 yaml）：**

| policy | 权重来源 | 典型 profile |
|--------|----------|----------------|
| `best` | 训内 `ws.evaluate` 最优 epoch；若无则训末最后一轮 | supervised |
| `last` | 训末最后一轮 `learner.state_dict()` | physical / PINN |
| `none` | 不写 `best_model.pt` | 快速试跑 |

**F1-contract 附件 — checkpoint 策略：**

```text
CHECKPOINT_POLICY: best | last | none
CHECKPOINT_WEIGHT_SOURCE: train_eval_best | last_epoch | n/a
CHECKPOINT_METRICS_IN_FILE: official_test (+ train_eval if best)
KEEP_POINTER: poetry run python -m contract write-keeper --exp-dir <keeper> → saved/keeper.json（policy≠none 时；不复制权重）
```

环境变量 `NN_CHECKPOINT` 可覆盖 yaml（单轮临时）。

#### E2-metric-tier — 指标列分级（必问）

| 部分 | 内容 |
|------|------|
| 【现状】 | 列出 `metric_keys` / `auxiliary_keys`；扫描 TSV/`results.json` 是否有关键标量仅在 `notes` |
| 【为什么问】 | `notes` 不参与 KEEP；auxiliary 可参与 `any_metric` 但不进主列排序 |
| 【模板建议】 | 主指标 1 个；需分场景对比的 → `auxiliary_keys` 或额外 `metric_keys`；调试 → `notes` |
| 【确认选项】 | ① 按建议表锁定（F1-contract「台账分级表」） / ② 保持现状（说明故意留 notes 的键） |

**F1-contract 附件 — 台账分级表：**

```markdown
| 键名 | 级别 | 方向 | 说明 |
|------|------|------|------|
| （示例） | primary | maximize | KEEP 主列 |
| （示例） | auxiliary | maximize | 分维度对比 |
| （示例） | notes_only | — | 不进 contract |
```

**级别**：`primary` | `auxiliary` | `notes_only`（`notes_only` 不得写入 contract）。

#### E5-tsv-columns — TSV 四区（与场景清单对齐）

**【为什么问】** Agent 扫 `_runs/results.tsv` 须分区理解；要 KEEP 的键不得藏在 parameters/notes。成绩表还须能认出**尺子轮**（朴素基线 / 公开对照）vs 普通轮。

**对用户开场（人话）**：成绩表会固定多一列「这一轮角色」——普通轮 / 朴素基线 / 公开对照；**不是**主指标，也不进 KEEP。起步要不要**跑**尺子在后面 O3 问，本步只定表结构。

**TSV 左→右四区**（`experiment._default_tsv_columns()`，见 `docs/archive/metric-and-keep-system.md` §3）：

| 区 | 列 | KEEP |
|----|-----|------|
| **场景** | `experiment`；可选 `scenario_id`（`contract.scenario_tsv_column`） | 否 |
| **metrics** | 主指标 + 其余 metric/aux | **是** |
| **parameters** | `ledger_context_keys`（含系统列 **`baseline_tag`**） | 否 |
| **运行/notes** | `elapsed_sec`、`git_commit`、`exp_dir`、`description`、`notes`、`timestamp` | 否 |

**系统列（不可删）**：`baseline_tag` ∈ `{plain, reference, none}` — 落盘经 F1.5 `init_watchlist` 钉死 + 运行时 `ledger_context_keys` 强制并入；即使用户本步选 B，**表头仍写入该列**（B 只表示「本步不优先盯尺子」）。与 O3 分工：O3 = 起步跑不跑；E5 = 表里有没有角色列。

**【现状】** 扫 `ledger.watchlist` / 旧 TSV 是否已有 `baseline_tag`；缺则点名。

**【模板建议】** A：四区齐全 **且** 固定带基线角色列（推荐）。

**【确认选项】**（对用户 A/B/C，禁 ①②③）

- **A）按模板：四区 + 基线角色列（推荐）**
- **B）四区按我的清单；基线角色列仍写入，本步不作为关注重点**（须一句原因；**不得**真删列）
- **C）自定义四区**（须说明；**仍不得删除**基线角色列）

F1-contract「TSV 四区确认」须勾：`baseline_tag` 系统列 = 是。

迁后：`python3 scripts/regen_results_tsv.py --repo-root .`

#### E6-scenario — 探索方案与排期（须在 **D1-scenario-inventory**、**D2-data-split**、**G1/G2** 之后）

**对用户主题**：**场景探索方案**（不是「要不要探索」——**实验目标**已在 **G1/G2** 定过；本步定 **台账轮转结构**）。

**开场须写（人话，禁止裸抛内部轴名）**：

1. **你已选的主线**：…（G1 人话：追指标 / 方法+指标 / 摸底；若 G2 设了目标值或护栏，一句带过）
2. **D1 已锁场景**：…（场景 ID 列表）
3. **本步只定**：每轮允许改什么、一次专注几个场景、最好成绩怎么分开比；**不重填**起跑线超参（已在 D1 / E7 / F1-contract）

**流程：先清单（D1）→ 目标（G）→ 方案（E6）**。E6 **禁止**从零问「有没有场景 / 测哪个 SIP」——清单已在 **D1**；**禁止**让用户感觉「探索 = 只能试已有方法」——须写清 **reference（对照库）** vs **automatic（自主提出）** 等场景分工（若 D1 有）。

**全量问 E6 当满足任一**：`SCENARIO_CANDIDATES` 含 `|` 或多 ID；清单 ≥2 行且 **数据与指标** 不同；用户/H3-agent-boundary 声明多 benchmark。否则 `SCENARIO_AXIS: none`（F1-contract 仍须 **≥1 行场景清单**）。

| 子项 | 向用户确认（内部落盘见右栏） |
|------|------------------------------|
| **每轮允许改什么** | 内部 `A_explore` / `SCENARIO_AXIS`：≤1 维；无 → `none` |
| **哪些场景在轮转** | 内部 `scenario_active` / `ACTIVE_SCENARIOS` ⊆ 清单 ID |
| **排期** | 内部 `SCENARIO_POLICY`：`focus`（一次专注一个场景，**对人这么说**）/ `rotate` / `multi_eval_one_train` |
| **默认先跑哪个场景** | 内部 `scenario_default` / `DEFAULT_SCENARIO` |
| **其它超参** | 非「每轮允许改什么」的 cfg → F1「默认运行档」冻结 |
| **最好成绩和谁比** | 映射清单 KEEP 列 → `history_experiment_substr`；**分池不混比** |

**按 G1 分支 — 【模板建议】与【确认选项】（对用户须 A/B/C，禁 ①②③）**

| G1（内部） | 【模板建议】人话 | 选项 A（推荐）人话摘要 |
|------------|------------------|------------------------|
| `careful` | 保守档：只动 A 标量/日程，Agent 几乎不改 | 只换学习率/正则化，分池，超参先不动 |
| `optimize` | 标量/日程 + 简单结构 | 只换模型，超参先不动，一次专注一个场景，分池 |
| `innovate` | 标量/日程 + 结构 + 目标（routine/extend） | 只换结构（含创新维），分池 |
| `aggressive` | 标量/日程 + 结构 + 目标 + 数据（routine/extend/novel 全开）| 多维度可同时改（含数据），分池 |
| `explore` | **automatic 为主**（Agent 自主提架构）；reference 可选作对照库；仍建议**只换模型轴**、超参先冻住、**一次专注一个场景**、分池 | 摸底方案：automatic 为主，只换模型，分池，超参先不动 |
| `auto` | 起步同 optimize；撞墙后升档（G1 升档链）| 起步只换模型；撞墙升 innovate 后 E6 跟随档调整（结构）；再升 aggressive 后 E6 跟随档调整（数据+全源）|

**【确认选项】（所有 G1 共有骨架；Agent 按上表填 A 的具体文案）**

- **A) 按「{G1 人话}」建议来（推荐）** — 展开写：每轮改什么、默认场景、排期、分池、超参是否冻住  
- **B) 每轮允许多样东西一起改**（如模型+优化器+增广）— 须说明优先级；**默认不推荐**  
- **C) 固定单一架构，不换模型** — 仅冒烟/复现一条线；与「摸底 / 多架构对照」通常矛盾，选 C 须在 F1 说明  
- **D) 我来说：______**

**Agent 禁止**在选项正文里裸写 `SCENARIO_AXIS`、`A_explore`、`scenario_bindings`、`focus`——用「一次专注一个场景」「只换模型架构」等人话。

**配置落点：** `nn-config.agent` + README `SCENARIO_POLICY` + `contract.agent_scenario_bindings`；`train.py` → `apply_agent_scenario_env`；auto-run → `build_agent_scenario_manifest`（**仅**服务 `A_explore`）。

**F1-contract 必附 — 场景清单：**

```markdown
## 场景清单（F1-contract 锁定）
| 场景 ID | 数据与指标 | 默认配置（起跑线） | 后面允许试什么 | 成绩和谁比 |
|---------|------------|-------------------|----------------|------------|
| default | D2-data-split: TEST=… | … | 无 | … |
```

**F1-contract 必附 — 默认运行档（有非探索维时）：**

```markdown
## 默认运行档（非「后面允许试什么」的键，起跑线冻结）
| cfg 键 | 默认值 | 说明 |
|--------|--------|------|
| … | … | Agent 不得当首轮探索改动 |
```

**F1-contract 最小记录（无 README 块时）：** `SCENARIO_AXIS`、`KEEP_POOL`、`EXPERIMENT_NAMING`、`SCENARIO_POLICY_HUMAN`（同前）。

二期 README `<!-- SCENARIO_POLICY -->`：见 `2026-05-19-ledger-scenario-agent-policy-design.md` §5。

#### E7-run-context — 运行参数列（条件必问）

**开场须写**：`D1 清单「默认配置」里的键：…`；本问把**未**列入「后面允许试什么」的含义键落盘到 TSV **parameters** 区。

满足 **任一** 即须问（**在 E6-scenario 之后**）：

- **E6-scenario** 已确认场景轴 **非 none**；或
- D1 清单 **默认配置（起跑线）** 中 ≥2 个「非 metric 但决定实验含义」的 cfg 键；或
- ≥2 个此类键仅出现在 experiment 名 / `config.json` 而 D1 未写 → **须回补 D1 后再问 E7**。

| 部分 | 内容 |
|------|------|
| 【现状】 | 关键参数仅在 `config.json` / `experiment` 名 / `notes` |
| 【为什么问】 | Agent 扫表需固定列；与 metric 分离且 **不参与 KEEP** |
| 【模板建议】 | `ledger_context_keys` → TSV **parameters** 区（在 metrics 之后）；键名与 `finalize_run` 的 `cfg` / D1 **默认配置** 一致 |
| 【确认选项】 | ① 锁定运行参数表 → F1-contract / ② 仅 experiment 命名 / ③ 自定义键列表 |

- 清单 **默认配置（起跑线）** 中、**非**「后面允许试什么」的键 → 须进 `ledger_context_keys` 或 F1-contract「默认运行档」表；**禁止**仅代码默认、台账不可见。
- 探索轴绑定的键可同时进 ledger（便于 TSV 读）；Agent 轮换由 manifest 改 env。

**F1-contract 附件 — 运行参数表：**

```markdown
| cfg 键 | TSV 区 | 说明 |
|--------|--------|------|
| （示例） | parameters | 不参与 KEEP |
```

实现：`contract.ledger_context_keys`；`regen_results_tsv.py` 从 `config.json` 回填。

**三铁律（写入 F1-contract / README / EXPERIENCE）：**

1. 进 KEEP 对比的键 → 必须在 `metric_keys` 或 `auxiliary_keys`。
2. 仅展示 → `notes` 溢出。
3. 同 TSV 可混行；**KEEP 不得跨场景混比**（`history_experiment_substr` + 实验命名）。

**Preflight 与 profile：** `experiment.preflight_check` **不**按 profile 分叉；supervised 传 `learner+loss_fn`（有 `loss OK`），rl 仅静态守门 + `ws.preflight_env_check`（见模板根 **PROTOCOL §3.0.1**）。§5 用 `scripts/smoke-check.sh`，勿对 rl 硬凑 supervised 的 grep。

**E4_训内节奏（F1-contract 必写；主问项）**

| 选项 | 含义 |
|------|------|
| **A 每圈** | 每个 epoch/segment/stage 后 `ws.evaluate` |
| **B 仅训末 test** | 循环内**不**调 `ws.evaluate`；只训末 `contract.test` |
| **C 稀疏** | F1-contract 写清触发；supervised **推荐** `EVAL_START_FRAC=0.2` |

**E4_PATH（按 profile；supervised 不作开放二选一）**

| profile | 默认 | 须问用户的内容 |
|---------|------|----------------|
| **supervised** | **`②-same-metrics`**：在 D2-data-split `EVAL_USES` loader 上用与 `contract.test` **相同的指标函数**（非 `evaluate→test()` 整包调用） | **只问 训内节奏**（A/B/C）；**例外** `①-delegate-test`（`ws.evaluate`→`contract.test`，同 BM 遗留）须用户明确登记 |
| **rl** | 训内有 eval 时默认 **①**（`evaluate`→`contract.test`）；太慢 → **②** + README `E4_EVALUATE_INDEPENDENT: yes` | 训内节奏 + 是否例外 ② |
| **physical** | **②** proxy（`EVAL_USES`）；真实误差仅 E2 | 训内节奏 **A** 每 stage |

**supervised 实现要求（默认 ②-same-metrics）**

- `contract/test.py` 内指标计算抽成可复用函数（如 `_evaluate_on_loader`）；`ws.evaluate` 对 **val_loader** 调用同一函数。
- **禁止**训内只算 `val_loss` 而 test 算全套 E1 键（除非用户明确登记「轻量 monitor 例外」并写 README）。
- `EVAL_USES` ≠ `TEST_USES`（D2-data-split 已钉）；KEEP 仍 **仅** `contract.test` → `round_decision.json`。

**C 实现（supervised）**：`train.py` 用 `_should_run_evaluate` + `EVAL_START_FRAC` / `EVAL_EVERY_N`（`NN_*` 可覆盖）。

**E4-train-eval 与 T2-callchain**：E4 = 策略；T2-callchain = 调用链落实。`E4_训内节奏=B` → T2-callchain **无** `ws.evaluate`。

**墙钟**：`E4_PATH=①-delegate-test` 或 RL ① 且 训内节奏 A/C → 勾「接受训内 test 级墙钟」。

**E4-keys（返回键，并入 E4-train-eval 自检，不单独占编号）**：`E4_训内节奏≠B` 时 `ws.evaluate` 须覆盖 **E1-metrics** 全部键（supervised 默认与 test 同函数；RL ② 须在 E4-train-eval 列出键）。

**E4-train-eval 确认选项模板（Agent 须含；supervised 示例）**

```markdown
### E4-train-eval 训内评估（D2-data-split + **T2-callchain** 已确认 EVAL_USES / TEST_USES / 调用链之后）
- **E4_PATH**：supervised 默认 ②-same-metrics；□ 例外 ①-delegate-test（须说明）
- **E4_训内节奏**：A / B / C（触发：EVAL_START_FRAC=…）
- **墙钟**：□ 仅当 ①-delegate-test 或 RL ① 且 A/C
- **F1-contract**：E4_PATH=②-same-metrics; E4_训内节奏=C-last80
```

**RL 路径补充**

- **①-delegate-test**：`ws.evaluate` → `contract.test`（`rl_workspace_gate` 默认）
- **② 独立轻量**：README `E4_EVALUATE_INDEPENDENT: yes` + 返回键覆盖 E1

**示例（supervised，CSI 型）**

```text
SPLIT_KIND: train_val_holdout_test
TRAIN: TRAIN_UE 窗口池，除 val 索引外
VAL: 同 TRAIN_UE 池按 VAL_RATIO 切出（仅 monitor）
TEST: UE [TRAIN_UE:TRAIN_UE+TEST_UE]，仅 contract/test.py
VAL_TEST_SAME_DISTRIBUTION: no
```

**示例（BM 型）**

```text
SPLIT_KIND: train_holdout_no_val
VAL: none
TEST: 顺序后 20%，仅 contract.test；若 E4 例外 ①-delegate-test 须在 E4-train-eval 块写明
```

### 阶段 T：训练链路（"怎么训"）— Training

#### 阶段 T 编号约定

- **格式**：`T<n>-<slug>`（**T1-loss-layers～T2-callchain**）。
- **F1-contract 汇总表**须用 slug 行名。

| 编号 | slug | 含义 |
|------|------|------|
| **T1-loss-layers** | loss-layers | loss / 约束 / 技巧分层 |
| **T2-callchain** | callchain | 外层循环、调用链、evaluate/test 时机 |

| # | 确认项 | 为什么问 | 答错的后果 |
|---|--------|---------|-----------|
| T1-loss-layers | **build_objective / loss 组成**（**损失与约束：什么能改、什么不能改**） | 钉死不可改的任务/物理项 vs 可调正则 vs 非 loss 技巧（EMA/SWA） | PINN：Agent 把物理约束当可调 loss 改掉 → 不再满足 PDE |
| T2-callchain | **train_step 编排**（**训练循环：谁循环、一圈多大、何时评估**） | 钉死 `train.py` 与 `workspace` 的调用链：外层单位、一圈语义、evaluate/test 时机 | 少训/多训、验证时机错、循环与实现挪层 → 不可比 |

**本节不问**：指标键（E）、数据路径（D）、训练墙钟/GPU（O）。**T2-callchain 之后**才问 **E4-train-eval** / **E8-checkpoint**；T2-callchain 只写控制流，在填空表写明 `evaluate?` / `checkpoint?` / `训末 test?`，供 E4/E8 引用。

#### 阶段 T — Agent 提问规范（必遵）

**T1-loss-layers / T2-callchain 硬边界**

| 项 | 只许谈 | 禁止谈 |
|----|--------|--------|
| T1-loss-layers | loss/约束分层；`build_objective` 与正则分工 | `for epoch`、batch 循环、`evaluate`、scheduler |
| T2-callchain | 外层循环、一圈语义、evaluate 节奏、多阶段、`run_training` facade | loss 项名、权重、正则、metric 键 |

**T1-loss-layers — 用户要确认的一句话（Agent 内部提纲，勿原文贴给用户）**

> 迁完后：**(1)** **硬约束**（核心目标/物理项，**不得删换**）；**(2)** **是否允许追加**辅助 loss/正则（**不替换**核心）；**(3)** **是否允许替换**核心算法/目标族（如 SAC→其它 RL）；**(4)** **可调超参**；**(5)** **技巧**（不算 loss）。

**对用户怎么说（必遵）**

先讲清**这步在拍板什么**，再给建议。禁词：`五档` / `五层` / `五类` / `训练目标分层` / `T1` / 把内部表头「硬约束·允许追加·允许替换·可调·技巧」当小标题念给用户。

**第 0 段必须点破（两句，可改写）**：

1. **不是**在问「你现在用哪个 loss / 约束」。
2. **是在**定：以后机器自动改实验时，训练目标这块**底线在哪、松到哪算你允许**。

**「我的建议」用白话五句（按事情列；对用户用左列，内部 lock 用右列）**：

| 对用户怎么写 | 内部映射（lock / F1） |
|--------------|----------------------|
| 必须留着：… | 硬约束 |
| 可以换：… | 允许替换 |
| 可以加：… | 允许追加 |
| 只能拧旋钮：… | 可调 |
| 可选技巧：… | 技巧 |

无某条则写「暂无」或省略该句，勿留空壳标题。

**可照抄骨架（Agent 填空后发出）**：

```text
【训练方式 · 第 N / 共 27 步】

这一步在定什么
- 不是问「现在用哪个 loss」。
- 是定：以后自动改实验时，训练目标的底线与松紧（什么碰不得、什么可以动）。

我看到的现状
- （从源码归纳 2～4 条：现在怎么训、怎么评、有没有可换族）

我的建议
- 必须留着：…
- 可以换：…
- 可以加：…（没有就写暂无）
- 只能拧旋钮：…
- 可选技巧：…

你怎么选
A) 就按上面的边界来（推荐）
B) 我想更严：______
C) 我想更松 / 自己改：______
```

**铁律（T1）**

- **硬约束 ≠ 禁止加 loss**；**硬约束 ≠ 永远禁止换算法**——是否可换写在 **「允许替换」** 行。
- **允许追加**：只加项，**不替换**硬约束；入口通常 `workspace/train_step` 或 `build_objective` 扩展。
- **允许替换**：换的是**核心算法/目标族**（如 learner 类、PINN 范式）；须在 F1-contract 写清**范围**与 **KEEP 分池**（换算法 ≈ 新方法族，见块 E **S_method** / E9）。

**T1-loss-layers 确认选项（Agent 内部；对用户仍用 A/B/C 人话）**：

- **① 采纳建议** — 按【模板建议】写入 F1-contract（**内部五类表**，见下；**勿**对用户说「五类」）
- **② 只锁现有清单** — 【现有清单】原样进 F1-contract，**不套**建议表
- **③ 自定义** — 用户用白话说明更严/更松后，Agent 再映射进五类

**【模板建议】内部五类表（仅 F1 / lock；对用户禁念表头。必含「允许追加」「允许替换」；无则写「否」或「暂无，迭代可提案」）**

| 类型 | 含义 | Agent 迭代 |
|------|------|------------|
| **硬约束** | 无论是否允许替换，**迁后都不得删换**的项（如 PDE 残差、官方 eval 协议、任务定义） | **不得删换** |
| **允许追加** | workspace **新增**辅助 loss/正则/惩罚（**不替换**核心算法/目标） | **可以**加（写清位置与名称） |
| **允许替换** | **更换**核心算法/目标族（如 SAC↔CQL、监督头结构换代） | **仅当 F1 写「是」**；须写范围 + **KEEP 仅同算法池** + 常触发 **E9 substr** 更新 |
| **可调** | 当前算法下已有超参、权重、系数 | **可以**调 |
| **技巧** | Normalizer、EMA/SWA 等（不算 loss/算法本体） | **可以**用/关 |

**硬约束 vs 允许替换（勿混）**

| 用户意图 | 硬约束行 | 允许替换行 |
|----------|----------|------------|
| **算法钉死 SAC** | 可写「SAC 内置目标」 | **否** |
| **默认 SAC，允许换 off-policy** | 写 eval/任务/数据协议；**勿**把 SAC 写进硬约束 | **是**；范围如 `SAC|CQL|TD3`；当前默认 `SAC` |
| **只调超参、不换算法** | 按上栏「钉死」 | **否** |

_profile=rl 示例 A（钉死 SAC，`build_objective=None`）_：硬约束=SAC 内置目标 + 官方 KNN test 口径；允许追加=workspace 辅助项（当前无）；**允许替换=否**；可调=ent_coef、gamma…；技巧=Normalizer。

_profile=rl 示例 B（默认 SAC，允许换算法）_：硬约束=官方 eval 协议 + 离线 RL 任务定义；允许追加=workspace 辅助项；**允许替换=是（learner 族：SAC/CQL/TD3 等，须保持 contract.test 不变）**；可调=各算法超参；技巧=Normalizer；E9：按 `learner`/`algorithm` substr 分池。

**T1 发送前额外自检**：F1 是否含 **「允许追加」「允许替换」** 两行；若允许替换=是，是否已提示 E9/场景清单 **substr 分池**；① 与 ② 的【选后锁定】「差别」列不得留空。

**T2-callchain — 每条消息第一段（开场白，原样或等价）**

> **T2-callchain — train_step 编排**（训练循环：谁循环、一圈多大、何时评估）  
> 请确认的是**训练控制流**，不是 loss（T1-loss-layers 已确认）。  
> 你需要拍板：**(1)** 外层循环单位（epoch / segment / stage） **(2)** 一圈对应哪次 `train_step` 或 `run_training` **(3)** 每圈后是否 `ws.evaluate`、训末是否 `contract.test` **(4)** 迁后是否保持 `train.py` 编排 vs `workspace` 实现的分工。  
> 你**不需要**在此项改代码或选超参；只需确认「迁完后仍按此方式跑」或指出例外。

**T2 — 「facade」人话（RL 必讲清，禁止只写一词）**

**facade（门面）** = `train.py` **很薄**，只负责「开工 / 收尾」；**训练循环藏在 `workspace`** 里（常见入口 `ws.run_training`）。

| 对比 | **canonical（显式循环）** | **facade（门面）** |
|------|---------------------------|---------------------|
| `train.py` 长什么样 | 能看见 `for segment` / `for epoch`，每圈调 `ws.train_step` | 通常 **没有** `for`；一行 `ws.run_training(...)` |
| 「一圈」指什么 | 通常 = **一次** `train_step`（一段 segment / 一个 epoch） | 通常 = **一次** `run_training` 调用（里面可能 `model.learn(total_timesteps=…)` 一次跑完） |
| 循环写在哪 | `train.py` | `workspace`（`train_loop` / curriculum / learn） |
| 迁后要不要改 | 可保持 canonical | **允许**保持 facade；**不强制**把循环挪回 `train.py` |
| 填空表「与模板差异」 | 写 `无` 或 `canonical` | 写 **`facade：train.py→run_training`**（并列出 workspace 内实际步骤） |

**Agent 向用户说明时须含一句**：「你的项目是 **facade**：`train.py` 不自己写 segment 循环，训练在 `run_training` 里面完成；这不等于没有循环，只是循环在 workspace。」

**T2-callchain — 必含调用链（≤6 行）**（按 `nn-config.profile` 与实际代码选一；快速路径也**必须**贴，禁止只写「确认即可」）

_supervised_

```text
train.py:  for epoch = 1 .. EPOCHS
             └─► ws.train_step     （= 1 个 epoch 的全部 batch）
             └─► ws.evaluate
             └─► best / scheduler（在 train.py）
训末:       finalize_run（单槽常自动 finalize_round）
```

_rl — 写法 A：canonical（显式循环在 train.py）_

```text
train.py:  for segment = 0 .. S-1
             └─► ws.train_step(epoch=segment)  （= 本段 model.learn）
             └─► [可选] ws.evaluate
训末:       contract.test → finalize_run
注: 参数 epoch = segment 序号，不是 supervised 的 epoch。
```

_rl — 写法 B：facade（门面；多数离线 RL 迁项为此类）_

```text
train.py:  ws.run_training(...)              （门面：train.py 只「开工」）
             └─► train_loop.run_training    （【现状】须写出里面关键一步，如 model.learn）
             └─► [可选] curriculum / 权重插值（在 workspace，不在 train.py）
训末:       contract.test → finalize_run
F1-contract 须写: 编排入口=run_training；train.py 无显式 for-segment 循环
```

_facade 填空表示例（须贴在调用链后或写入 F1）_：

| 填空 | facade 项目怎么填 |
|------|-------------------|
| 外层循环 | `train.py`：**无**显式 `for`；循环在 `workspace`（或 SB3 内部） |
| 一圈 | **一次** `ws.run_training` → 内层 `model.learn(total_timesteps=…)` |
| 每圈后 | 训中是否 `evaluate`（常与 E4 一致）；facade 常见 **循环内不 evaluate** |
| 与模板差异 | **`facade（run_training）`** — 勿只写「facade」二字 |

_physical / PINN_

```text
train.py:  for stage in [预热, 主训, …]
             └─► ws.train_step（PDE/配点采样在 step 内）
             └─► ws.evaluate（常为 proxy）
正式指标:   contract.test
```

**T2-callchain — 【现状】填空表**（只写控制流，禁止 loss 列表）

| 填空 | 内容 |
|------|------|
| 外层循环 | 文件 + 变量 + 次数/终止条件 |
| 一圈 | 函数名 + 一句话 |
| 每圈后 | evaluate? scheduler? checkpoint? |
| 每轮绑定场景数 | 1（单场景训+评）/ 1→N（训末多场景终评） |
| 训末 | test? finalize? |
| 多阶段 | 无 / train.py 阶段名 / 在 run_training 内 |
| 与模板差异 | `无` / `canonical` / **`facade（train.py→run_training，须带箭头说明）`** |

**T2-callchain — 【为什么问】（短句）**：搞错「一圈」或 evaluate 时机 → 少训/多训、监控与台账不可比。RL facade 易误解为「没有循环」；须写清 **一圈 = 一次 run_training 还是一次 train_step**。PINN 可加阶段顺序错。

**T2-callchain — 【确认选项】（固定，须配【选后锁定】）**

- **① 采纳建议（推荐）** — 调用链 + 填空表写入 F1-contract；**已是 facade 时选 ① 即可**（含「门面 + 训末 test」全流程）
- **② 只锁现有清单** — 填空表原样进 F1-contract
- **③ 自定义** — 控制流与表不同（须在【选后锁定】写清）
- **④ 仅当 canonical 迁 facade 的窄确认** — **仅**书面确认「迁后入口改为 `run_training`」；**若【现状】已是 facade，不要单推 ④**（与 ① 重复，易懵）

**【选后锁定】（T2 必附）**

| 你选 | F1-contract 会写什么 | 和【现状】的差别 |
|------|----------------------|------------------|
| **①** | 编排=canonical 或 **facade（run_training）** + evaluate/test 时机 + 调用链 | 与 Agent 建议一致 |
| **②** | 填空表原文 | 不套 facade/canonical 命名 |
| **③** | 用户指定的控制流 | 写明例外 |
| **④** | 仅一行「入口=run_training」 | **仅**在要从 canonical **改成** facade 时用；**已是 facade 请选 ①** |

**T2-callchain 发送前自检**：已用**人话**解释 facade（若适用）✓ | 调用链 ✓ | 填空表「一圈」与 facade/canonical 一致 ✓ | 未重复 E4 训内选项 ✓ | 【选后锁定】可辨 ✓ | **已是 facade 时未把 ④ 当推荐** ✓

### 阶段 O：运行参数（"怎么占机器、怎么并行、怎么探索"）— Ops（**入口 A / B 均须**）

#### 阶段 O 编号约定

- **格式**：`O<n>-<slug>`（**O1-time-budget～O4-repro-determinism 连续**；问话顺序 = 数字顺序）。
- **F1-contract 汇总表**须用 slug 行名（与 E 段一致），**禁止**仅写 `O1`/`O2`/`O3`/`O4` 无后缀。

| 编号 | slug | 含义 |
|------|------|------|
| **O1-time-budget** | time-budget | 单次训练墙钟 `time_budget` |
| **O2-gpus-parallel** | gpus-parallel | `gpus` + `max_parallel` + 多槽 finalize 责任 |
| **O3-baseline-anchors** | baseline-anchors | 该场景起步 plain+reference 尺子（测条件；找不到请用户给） |
| **O4-repro-determinism** | repro-determinism | 基线 `NN_SEED`、cuDNN、快照与 `SEED` 进 cfg/TSV |

**本节与旧项目历史无关**：只根据 **当前机器**（GPU 探测）、用户希望的 **单轮并行度**、以及 **起步对照尺子** 签字。入口 B 的 `new-project.sh` 预填值仅作【模板默认】，不能代替 O 问答。起手改哪一类（A–D）由 G1 `exploration_mode`→`tier_start` 隐含，**本步不再问**旧四档。

| # | 确认项 | 为什么问 | 答错的后果 |
|---|--------|---------|-----------|
| O1-time-budget | **time_budget / 训练墙钟**（**训多久会被 TimeGuard 截断**） | 决定 `NN_TIME_BUDGET` / `TimeGuard`；与 smoke 步数（`NN_SMOKE`）无关 | 训练意外截断或跑太久占机 |
| O2-gpus-parallel | **gpus + max_parallel**（**用哪些卡、单轮开几个 train.py**） | `auto-nn-run.sh` 每轮注入 Hardware；多槽须手动 `finalize-round` | 白名单与机器不符；误开多槽损坏台账 |
| O3-baseline-anchors | **起步 plain + reference 尺子** | 同场景、同官方测试下先立下界/对照，后续 fancy 才可比 | 无尺瞎拧；抄条件不对齐的论文分骗自己 |
| O4-repro-determinism | **复现随机性与快照** | 钉 `NN_SEED` 基线、cuDNN 策略、`SEED` 进 `ledger_context_keys`；模板已落盘 `_repro` | 种子不一致无法复现；迁后 `train.py` 缺 cudnn 两行 |

**本节不问**：E4-train-eval 的 evaluate/test 墙钟（评估成本）；T1-loss-layers/T2-callchain 训练逻辑；旧仓曾用哪张卡（除非用户主动要求写入 EXPERIENCE）；**起手 Tier 四档**（已由 G1 隐含）。

**与 E4 边界**：E4-train-eval = RL **评估**是否走完整 `contract.test`；O1-time-budget = **训练**全程 `time_budget`。

**O2 原则**：`gpus` 写**显式** `[0, …, N-1]`（与 `new-project.sh` 一致）；**`max_parallel` 由【算力估算】推荐 K，禁止不估算就写死 1**（仅当 K=1 时训末自动 `finalize_round`）。

#### 阶段 O — Agent 提问规范（必遵）

**提问前（只读，在 O1-time-budget 前执行一次）**

```bash
cd <project_root>
python3 -c "
import torch
n = torch.cuda.device_count()
print('gpu_count', n)
print('gpu_indices', list(range(n)) if n else [])
"
nvidia-smi -L 2>/dev/null || true
# 读取 nn-config.yaml: gpus, max_parallel, time_budget, exploration_mode, agent.plateau_rounds
```

**O1-time-budget — 用户要确认的一句话**

> 单次 `train.py` 训练最多跑多少**墙钟秒**（`time_budget`）？`0` = 不限（须知情）。

| 部分 | 内容 |
|------|------|
| 【现状/模板默认】 | 入口 A：yaml 的 `time_budget`、是否常被 `NN_TIME_BUDGET` 覆盖；入口 B：模板默认 `3600` |
| 【模板建议】 | `3600`；长任务加大；调试可 `0` |
| 【确认选项】 | 维持 / 改为 ___ 秒 / `0`（不限） |

**O2-gpus-parallel — 用户要确认的一句话**

> 本项目允许用哪些 GPU（白名单），单轮 automation 最多同时跑几个 `train.py`（`max_parallel`）？

**【现状/模板默认】四块（O2 必含）**

1. **本机**：`gpu_count`、型号与单卡显存（`nvidia-smi -L` / `nvidia-smi --query-gpu=memory.total`）
2. **nn-config**：当前 `gpus`、`max_parallel`（入口 B：`new-project.sh` 预填须与**当前**探测对照）
3. **单槽占卡（g）**：每个 `train.py` **典型占几张 GPU**（读 `torchrun --nproc`、`CUDA_VISIBLE_DEVICES`、历史脚本/日志；**禁止猜**）
4. **入口 A 历史**：以往实验常占哪几张卡、是否多进程同时跑（例：总 8 卡、单次实验占 2 卡 → `g=2`）

**【算力估算】（O2 必含；给出推荐 K 与一句理由）**

```text
N = len(gpus 白名单)          # 例：8
g = 每个 train 典型占卡数      # 例：1（单卡 train）或 2（DDP 双卡）
K_upper = floor(N / g)        # 例：8 或 4
K_cap   = 按显存/任务调低（见下表）
K 推荐  = min(K_upper, K_cap) # 至少 1；写入【模板建议】
```

| 信号（满足则 **降低** K_cap） | 建议 K_cap（在 K_upper 基础上） |
|------------------------------|--------------------------------|
| 视频 + 光流/大 backbone、batch 大、显存常 >20GB/槽 | **1～2** |
| physical / PINN、3D 场、L-BFGS 段 | **1** |
| RL env + learner 同机、replay 占显存 | **1～2** |
| 轻量 supervised（小 MLP、表格时序） | **≤4**（仍 ≤ K_upper） |
| `time_budget=0` 且单次 train 很长 | 比上表 **再减 1**（防占满机器） |
| CPU/IO 瓶颈明显（数据加载重） | 不超过 **2**，除非用户要 sweep |

- **禁止**：不填 `g`、不写 `K 推荐` 理由，就把 ① 写成 `max_parallel: 1`。
- **K>1**：须在 F1-contract / O2 写明训末 **`python -m contract finalize-round`**（C11）。

**【模板建议】（示例句式）**

> `gpus: [0,…,N-1]`；**推荐 `max_parallel: K`**（因每槽约 **g** 卡、共 **N** 卡，且任务属 ___ 档显存）；若你主要做 Tier A 多组 LR 并行，可采用 K=___。

**O2 【确认选项】（固定；须配【选后锁定】）**

- **① 采纳推荐** — `gpus` 显式列表 + **`max_parallel: K`（与【算力估算】一致）**
- **② 保守单槽** — `max_parallel: 1`（台账最省事、训末自动 finalize；算力紧或首轮迁移推荐）
- **③ 自定义** — 自填 `K` / `gpus` / 是否 `gpus: []`（须在【选后锁定】写清与①差别）

**【选后锁定】**

| 你选 | nn-config / F1-contract | 与【算力估算】的差别 |
|------|-------------------------|----------------------|
| **①** | `gpus=[0..N-1]`；`max_parallel=K`（写出数字） | 一致；K>1 须写 finalize-round |
| **②** | `max_parallel=1`；显式 gpus | **主动放弃**并行，比推荐 K 少占机器 |
| **③** | 用户指定 | 写明 K、g、是否 [] |

**无 GPU**：`gpus: []`，`max_parallel: 1`。

**O3-baseline-anchors — 用户要确认的一句话**

> 在**当前默认场景**、同一套官方测试下，起步是否先跑 **朴素基线（plain）** 和 **公开对照（reference）**？Agent 已找的推荐对照是什么；测条件是否对齐；找不到时请你指定或确认 novel。

| 部分 | 内容 |
|------|------|
| 【开场须写】 | G1 人话 + E6「每轮改什么」+ D1 **默认场景 ID**；声明「起手改哪一类已随实验模式默认，本步只定尺子」 |
| 【会前作业 · 必做】 | ① 定起步 `scenario_id`；② 推 plain 配方（PDH P1–P6）；③ 按探测序找 reference 候选（D1 reference 池 → README/docs → framework 默认 → 复现配方）；④ 每候选填 **测试条件对齐**（场景协议 / OFFICIAL_TEST / `metric_key` / 预算软项）→ `aligned` / `partial` / `misaligned`；⑤ **零 aligned 候选** → 准备「请用户给出」空位，**禁止**静默推荐「无 reference」当 A |
| 【为什么问】 | 无同条件尺子则 fancy 不可归因；只抄条件不对齐的论文分比没有更糟 |
| 【模板建议】 | **A：该场景起步 plain + reference 各跑一轮**（reference 优先本仓实跑 `baseline_tag=reference`；发表分仅 `aligned` 可记入 EXPERIENCE 基线锚点） |
| 【确认选项 · 对人 A/B/C】 | **A（推荐）** 双跑 + Agent 推荐对照（已对齐）；**B** 双跑但方法/配方用用户指定；**C** 弱化（只 plain / 只记分 / 双跳过）——须逐项原因；跳过 reference 时若用户仍能给方法或分 → 写入；完全没有 → `pending_user` 或 novel 确认 |

**测试条件铁律**：`reference_conditions≠aligned`（且无用户 attested）时 **禁止**把论文分写入 `reference_anchor_value` 当主指标上界；可建议在本仓同 OFFICIAL_TEST 下 **R-run** 重测。

**请用户给出（零候选或不对齐时必出）**：对照方法名；或「发表分 + 指标 + 数据协议」；或「确认 novel 无公开对照」。

**【选后锁定】**

- F1 / migration-summary Ops：`scenario=…; start_runs=plain+reference|…; plain_recipe=…; reference_method=…; reference_conditions=…; reference_anchor=…|none|pending_user`
- 写 `saved/baseline_start_intent.json`（意图；无必填真值分数；字段见 design spec §6）
- 有对齐发表分 → EXPERIENCE「基线锚点」段
- **不写** `agent.exploration`

**O3 答完后 / F1 后必跑：`init_o3_abcde.py` 写 manual**（与尺子问话**解绑**；阶段 2 改代码前必跑）

```bash
python3 <template_root>/scripts/init_o3_abcde.py \
  --repo-root "<target_root>" \
  ${SOURCE_ROOT:+--source-root "<source_root>"} \
  --force-workflow build|migrate|update
```

产物（**必检**）：

| 文件 | 含义 | 缺失 → |
|------|------|--------|
| `<target_root>/references/manual/abcde-manual.md` | 5×3 表 × 3 workflow + 对象类型判定头 | 后续 Agent 改码无路径梯子可依 |
| `<target_root>/saved/baseline_start_intent.json` | O3 尺子意图（选 A/B 时） | 首轮 BAS/reference-start 无 init 口径 |

**为何仍跑 init_o3_abcde**：写对象类型 + manual 路径上限（非起手四档）。governance-sync 内 `abcde_migrate.py` 为兜底。

**快速路径**：O1～O4 **不可**空跳过。入口 B 亦须 O3 确认起步尺子（不可因 new-project 预填而省略）。

#### O4-repro-determinism — 复现随机性（必遵；**O3 之后、F1 之前**）

**开场须写**：`D4 已锁数据 env：…`；本问钉**训练随机性**与框架快照（与 O2 GPU 白名单正交）。

| 部分 | 内容 |
|------|------|
| 【现状】 | 旧仓常用 `NN_SEED`（如 99）；`train.py` 是否 `contract.seed` + `cudnn.deterministic` |
| 【为什么问】 | 同数据同代码不同种子 → 结果不可复现；`config.json` `_repro.seed_resolved` 供事后核对 |
| 【模板建议】 | `nn-config.yaml` `seed` 与基线 `NN_SEED` 一致；**不必**要求用户 export `TORCH_CUDNN_*`（模板 `train.py` 已在代码设 deterministic）；`ledger_context_keys` 含 `SEED`（`train.py` 已写 `cfg["SEED"]`） |
| 【确认选项】 | ① 种子=___（写入 yaml + EXPERIENCE 复现配方） / ② 维持模板默认 42 / ③ 自定义 + 说明是否仍用代码 cuDNN |

**【选后锁定】** → F1「复现配方」种子行；Ops 行追加 `seed=…`；迁后 `train.py` 须对齐模板种子/cuDNN 写法。

**复现检查表（Agent 须在 F1 附 3 行，用户可读）**

```text
环境：env_snapshot.json + train.py cuDNN 确定性（一般无需 TORCH_CUDNN_* env）
数据：见 D4 REPRO_ENV_KEYS
训练：NN_SEED=<基线>；复现单次 → git_commit + exp_dir + 上两项 export
```

**阶段 2/3**：按 O1-time-budget～O4-repro-determinism 写入 `nn-config.yaml`（见 [nn-config.yaml（入口 A/B）](#nn-configyaml入口-ab) 与 CHECKLIST §3.1）。

### 阶段 F：收尾（Finalize）— 仅 F1-contract

#### 阶段 F 编号约定

- **格式**：`F<n>-<slug>`（阶段 1 用户问项仅 **F1-contract**）。
- **F1-contract 汇总表**行名须用各阶段 slug（`H1-legacy-artifacts` … `O4-repro-determinism`），**禁止**无后缀的 `H1`/`D2`/`E4` 等。

| # | 确认项 | 为什么问 | 答错的后果 |
|---|--------|---------|-----------|
| F1-contract | **口径终检** | 汇总 H/E/D/T/O/**G** 的**决定** + H3-agent-boundary 勾选写入 README 的硬约束 + 用户补充；**用户拍板**后方可改代码 | 漏写口径或 Agent 擅自加约束 → 迭代踩雷 |

**F1-contract 允许**：**项目摘要（P0 锁定）**；H1-legacy-artifacts～H3-agent-boundary、**E1-metrics～E8-checkpoint**（含 **E4_PATH** / **E4_训内节奏** / **E4-keys** 自检）、**E9-keep**、D2-data-split～**D4-repro-data**、**I1-train-consumes～I3-other-info-rules**、T1-loss-layers～T2-callchain、**O1-time-budget～O4-repro-determinism**、**G1-experiment-mode～G2-goal-value** 的决定表（**须用 slug 行名**）；**台账分级表**（E2-metric-tier）；**场景清单表** + **默认运行档表**（inventory）；**复现配方表**（D4 数据 + O4 种子 + 3 行检查表，见 PROTOCOL §2.4）；**运行参数表**（E7-run-context）；**场景/探索记录**（E6-scenario）；**TSV 四区确认**（E5-tsv-columns）；**checkpoint 策略**（E8-checkpoint）；H3-agent-boundary 勾选进 README 的硬约束；**D2-data-split 划分表**（含可比性子集）；**Ops 一行**：`time_budget=…; gpus=…; max_parallel=…; exploration_mode=…; start_runs=…; experiment_mode=…; seed=…`。
**F1-contract 禁止**：文件删除清单、README 全文改写、regen TSV、复制 `experiment.py` 等——归入 **阶段 3**（CHECKLIST §2–§4），**不要求用户在 F1-contract 对实现项逐条签字**。

**F 与 T 无关：** F1-contract 不是训练逻辑，而是改代码前的「口径合同」签字。

---

## 块 G — 实验目标配置（→ G1-experiment-mode～G2-goal-value；**E1-metrics 之后、E6-scenario 之前**）

> **对用户主题**：**实验目标**（两轮：先选「这轮主要干什么」，再定「主指标要到多少 / 摸底护栏」）。  
> **问话步号**：入口 A **#11–#12** / 入口 B **#8–#9**（在 **E1-metrics** 之后）。  
> **与 E6 分工**：G = **实验目标**（**实验模式** G1：追数 / 方法+数 / 摸底 + G2 可量化目标或护栏）；E6 = **探索方案**（在 G 已定前提下，每轮改什么、场景排期、KEEP 分池）。**须先 G 后 E6**。  
> **与 O3 分工**：O3 = 该场景起步 **plain/reference 尺子**（测条件；找不到请用户给）；在 **G + E6 之后**问。起手改哪一类由 G1→`tier_start` 隐含。  
> **迁后改法**：`/auto-nn-goal`（`mode` / `set` / `show` / `clear`）；常规迭代 Agent 勿手改 yaml。

### G1-experiment-mode — 实验模式（粗粒度目标；6 档 = 5 显式 + auto）

**用户要确认的一句话**

> 迁后多轮自动实验，你**主要想干什么**？（六选一；决定 prompt 叙事与 KEEP 侧重，5 显式档的撞墙由 reflect 写建议不动 yaml，auto 档撞墙自动升档。）

| 选项 | 人话 | 内部 `exploration_mode` | bundle 特征（`resolve_exploration` 读时派生，**不落盘**） |
|------|------|--------------|----------------------------------------|
| A | **careful**（啥都不动，照手册做） | `careful` | reflect 间隔 2 轮；不起手撞墙升档 |
| B ⭐ | **optimize**（先把主指标做上去；方法怎么省事怎么来）| `optimize` | reflect 间隔 1 轮；可设 G2 数值目标 |
| C | **innovate**（既要指标，也要用更深一点的方法）| `innovate` | reflect 间隔 1 轮；prompt 强调创新维；G2 可设目标 |
| D | **aggressive**（论文+文档+实现+生态全查，全力推进）| `aggressive` | reflect 间隔 1 轮；3 源全开；G2 可设高目标 |
| E | **explore**（先摸清方法空间；指标别崩就行）| `explore` | reflect 间隔 1 轮；G2 默认不设主目标；可选护栏 |
| F | **auto**（放手让系统撞墙自动升档）| `auto` | 调 `apply_mode(repo, "auto")` → 写顶层 `exploration_mode: auto` + `auto.{start_mode, promote_threshold, max_mode, effective_mode}`（effective_mode 记实际起步档）|

**5 显式 vs auto 区别**：
- 5 显式档：撞墙 → reflect 写建议到 `references/auto/`，**不动 yaml**
- auto 档：撞墙 → 系统写 yaml 升档（optimize → innovate → aggressive）

**【模板默认】** `optimize`（与 `new-project.sh` 预填一致；**仍须用户确认**）。

**F1-contract 行**：`实验模式 = careful/optimize/innovate/aggressive/explore/auto`；附件 `exploration_mode=<mode>`（auto 时同时写 `auto.{start_mode, promote_threshold, max_mode, effective_mode}`）。

**落盘**：签字后调 `apply_mode(repo_root, mode)`（6 档全支持）：
- 5 显式档：仅写顶层 `exploration_mode`（bundle 含 keep/reflect/goal/early_stop/external 由 `resolve_exploration` 读时从 preset 派生，**不落盘**）
- auto 档：调 `apply_mode(repo_root, "auto")` → 写顶层 `exploration_mode: auto` + `auto` 段（effective_mode 记实际起步档）

| # | 确认项 | 为什么问 | 答错的后果 |
|---|--------|---------|-----------|
| G1-experiment-mode | **实验模式**（6 档 = 5 显式 + auto）| 粗粒度钉**这轮追什么**（避免只有 exploration 四档却不知追数还是摸底）| innovate 选 aggressive 起手 → 口径乱；explore 未验收就开 → doctor WARN；auto 不知道 effective_mode 升档机制 → 跑很久才发现已升 aggressive |

### G2-goal-value — 主指标目标值（可量化部分；按 G1 6 档分支问法）

> 对用户只说「目标值 / 达标」；内部 `goal_value` 等不出现在用户可见消息里。

**目的**：钉 **focus 主指标要到多少** 才算「数到了」；驱动 `auto-nn-run.sh` loop **达标即停**（`check_goal.py`）。**与 E9「单次进步线」分开**——须向用户说明：目标可以远（如 0.99），进步线仍可近（如涨 0.1%）。

**按 G1 6 档 + E1 指标族分支问法**

| G1 | 指标族 | G2 选项（须给理由 + option 卡片） |
|----|--------|-----------------------------------|
| careful | 任意 | A) 0.85 B) 0.90 C) 0.95 D) **暂不设（推荐）** |
| optimize | **M1** + 简单分类 | A) 0.95 B) 0.98 C) 0.99 D) **暂不设（推荐）** |
| innovate | **M1** + 简单分类 | A) 0.95 B) 0.98 C) 0.99 D) **暂不设** |
| aggressive | **M1** + 简单分类 | A) 0.95 B) 0.98 C) 0.99 D) **暂不设** |
| auto | **M1** + 简单分类 | A) 0.95 B) 0.98 C) 0.99 D) **暂不设（auto 撞墙升档后 hard-stop 取决于 effective_mode 实际档的 goal_value）** |
| optimize / innovate / aggressive / auto | **M1** 难分类/细粒度 | A) 0.90 B) 0.95 C) 自定义 D) **暂不设（推荐）** |
| optimize / innovate / aggressive / auto | **M2/M3/M4** | A) **暂不设（推荐）** B) 用户给数 C) 自定义 |
| optimize / innovate / aggressive / auto | **M5** RL | A) **暂不设（推荐）** B) 用户给数 C) 自定义 |
| explore | 任意 | A) 不设数值目标（推荐） B) 设护栏：主指标不低于 ___ C) 暂跳过 |

**auto 档 G2 特别说明**（写入「我的建议」）：
- auto 起步 = optimize，撞墙自动升 innovate → aggressive（aggressive 撞墙停止）
- G2 设的目标值是 effective_mode **实际生效档**的 hard-stop 线
- 例：G2 设 0.98，auto 起步 optimize → 0.98 停；撞墙升 innovate 后 → 还是 0.98 停（同一 goal_value，effective_mode 是 innovate）
- 用户回 D「暂不设」→ auto 模式 loop 不硬停

**G2 档位理由（须写入「我的建议」）** — 详见 [`metric-family-keep-presets.yaml`](metric-family-keep-presets.yaml) `g2_profiles`。

**禁止**：G2 要求用户「先看 baseline 再设」作为唯一路径；应给上表档位，用户可选「暂不设」。

**按 G1 模式分支问法（Agent 内部择一，对用户仍四段式）**

| G1 模式 | G2 问什么 | 选项 |
|---------|-----------|------|
| `careful` | 主指标目标值（保守档）| A) 设目标：`<数值>`（0.85/0.90/0.95） / B) 暂不设 |
| `optimize` / `innovate` / `aggressive` | 主指标目标值 | A) 设目标：`<数值>`（0.95/0.98/0.99） / B) 暂不设（跑满 N；之后 `/auto-nn-goal set`） |
| `auto` | 主指标目标值（effective_mode 实际档的 hard-stop）| A) 设目标：`<数值>` / B) 暂不设（auto 撞墙升档后 hard-stop 取决于 effective_mode 实际档的 goal_value） |
| `explore` | 是否设「指标护栏」 | A) 不设数值目标（默认；跑满 N + 看覆盖） / B) 设护栏：主指标不低于 `<数值>` / C) 暂跳过 |

**内部落盘（G2）**

- 5 显式档（careful/optimize/innovate/aggressive/explore）+ 用户给数 → `goal_value=<value>`（**全局默认**；未单独写的场景继承）
- auto + 用户给数 → `goal_value=<value>`（effective_mode 实际生效档的 hard-stop 线）
- 「暂不设」→ **不写** `goal_value`（`check_goal.py` exit `2=NO_GOAL`）
- `explore` + 不设 → 不写 `goal_value`；若用户给护栏 → 写 `explore.metric_floor: <value>`（破线 WARN，不硬停 loop）
- **多场景（D1 清单 ≥2 行且非单场景 na）追加一问**（G2b，仍属 G2 主题）：
  - 「只有主场景达标就停 batch，还是 active 里配了目标的都要达标？」
  - 仅主场景 → `goal_policy: focus_only`（默认，可不写）
  - 都要达标 → `goal_policy: all_in_scope` + 确认 `scenario_active` 与清单一致
  - 个别场景更严/更松 → `scenario_goals`（如 `"128b": 0.75`）；摸底档豁免 → `"1024b": null`
  - README 场景清单可选 **目标值** 列（人读；`readme_consistency_gate` R5 WARN 对账）
- `goal_metric` / `goal_op`：**init 不问**，默认 contract `metric_key` / `metric_direction`

**【auto 档 G2 落盘特别说明】**
- auto + 用户给数 → 调 `apply_mode(repo, "auto")` + 写 `goal_value=<value>`
- auto + 用户「暂不设」→ 调 `apply_mode(repo, "auto")`，**不**写 `goal_value`
- goal_value 字段对 5 显式档是 hard-stop 线；对 auto 档是 effective_mode 实际档的 hard-stop 线

| # | 确认项 | 为什么问 | 答错的后果 |
|---|--------|---------|-----------|
| G2-goal-value | **主指标目标值**（或 explore 护栏；或 auto 暂不设）| 唯一可机械判定的 loop 硬停开关 | 过松提前停；过紧永远跑满 N；auto 不写 goal_value 时撞墙升档不停 |

**F1-contract 行**：`目标值 = <数值> 或 暂不设`（explore 可写 `护栏 = … 或 无`）；附件 `goal_value=…`（无则不写；auto 档 goal_value 对 effective_mode 实际生效档生效）。

**与 `/auto-nn-goal` 分工**：init 块 G 一次性钉默认；迁后 `mode` / `set` / `adjust` / `clear` / `show` 走技能，不重复 init 全流程。

#### init-qa-log（问答忠实 log；`.auto-nn/init-qa-log.md`）

**分工**：`init-qa-log.md` = **逐步问答 transcript**（问摘要 / 选项 / 用户原话 / 锁定摘要）；`migration-summary.md` = **F1 口径结论合同**（仍独立覆盖）。运行时 **不读** log。

| 时机 | 动作（在 `<project_root>` 或 `--repo-root <project_root>`） |
|------|--------------------------------------------------------------|
| 确定 workflow + `target_root`（及 `source_root`） | `python3 scripts/append-init-qa-log.py init-header --workflow build\|migrate\|update --target-root … [--source-root …]`（PR2.5） |
| P0 用户确认 | `append … --step 准备 --slug P0-project-brief …` |
| 阶段 0 `migration-compare` 完成（migrate workflow） | `append … --step 0 --slug stage-0-compare …`（`lock` 附报告路径或 3 行摘要） |
| **每一编号**用户确认后 | `append … --step <n> --total 27\|24\|15 --slug <slug> --theme <人话主题> --ask … --options … --user … --lock …` |
| 用户**改选**某编号 | 同 slug 再 `append` 一次（脚本自动 `rev=2`；不删旧条） |
| F1 用户 **①** 签字 | **先** `close --user … --contradiction-fail 0`（内含 `F1-contract` 条 + `closed` 戳）；**再**覆盖 `migration-summary.md`；**再** `python3 scripts/init_answers.py export --repo-root <project_root>` 写 `.auto-nn/init-answers.yaml` |

**脚本路径**：目标仓已有 `scripts/append-init-qa-log.py`（`new-project.sh` 自 template/package 安装）时 `cd <project_root>` 执行；否则用 `<template_root>/template/package/scripts/append-init-qa-log.py --repo-root <project_root>`（`PYTHONPATH` 指向同目录 `scripts`）。

**硬规则**：用户确认后、**下一问发出前**必须 append；阶段 2 开始前自检 log 条目数与已确认 slug 一致；F1 矛盾检查 `FAIL=0` 须写入 `close --contradiction-fail 0`。

**验收**：`python3 scripts/validate-init-qa-log.py --repo-root . --require-closed`；`verify-migration-complete.sh` / `nn-doctor` 对缺 log 或未 close 仅 **WARN**（不 die）。

**并行**：同触发点调用 `append-skill-activity.py`（`--skill auto-nn-init`）。

#### .auto-nn/migration-summary 落盘（`target_root` / `project_root` 必遵）

---

**默认路径**：迁后项目 **`.auto-nn/migration-summary.md`**（`new-project.sh` 会安装占位稿；与代码层 `contract/` **不是**同一物，勿混称）。**纯迁移留档**：运行时（auto-run / doctor / gate）**不读**本文件；场景权威是 `README` 的 `SCENARIO_POLICY`。

| 时机 | 动作 |
|------|------|
| **P0=①** | 可选：将「项目摘要（P0 锁定）」写入 `.auto-nn/migration-summary.md` 对应节（或暂存迁移笔记，**F1 前须并入**） |
| **用户 F1-contract=①** | **先** [`init-qa-log` `close`](#init-qa-log问答忠实-logauto-nninit-qa-logmd)（含 `F1-contract` 条与 `closed`）；**再**将**完整** F1 汇总（口径决定表 + 附件表 + `## F1-contract 矛盾项检查`）**写入/覆盖** `<project_root>/.auto-nn/migration-summary.md`；**场景清单**同时写入 `README` 的 `SCENARIO_POLICY`（权威）+ `.auto-nn/migration-summary.md`（留档副本）；**块 G**：`G1` → 写 `nn-config.yaml agent.experiment_mode`（`explore` 时同步 `objective_mode: explore`）；`G2` optimize/innovate 用户给具体值 → 写 `agent.goal_value=<value>`，「暂不设」→ 不写；`G2` explore 护栏 → 写 `agent.explore.metric_floor=<value>`（不设护栏则不写）。`agent.goal_metric`/`goal_op` init 不问，走 contract 默认；**块 I**：I1–I3 → 阶段 2 首步 `python3 scripts/init_info_perm.py write --repo-root . …`（参数见阶段 I 投影表；答案清单则 `--from-resolved .auto-nn/init-answers.resolved.json`）写 `contract/runtime.py` `INFO_PERM` + README `<!-- INFO_PERM -->` 块，随后 `python3 scripts/info_perm_gate.py .` 须 exit 0；**E9** → 写 `nn-config.yaml` `keep.improve_mode` / `keep.mode` / `keep.primary_delta` / `keep.near_best_abs`（用户所选档，**禁止**未选而保留模板 0.005） |
| **阶段 2 开始前** | 确认 `.auto-nn/migration-summary.md` **非空**且与对话签字一致；`verify` 硬检 |

**禁止**：仅把 F1 留在对话里不落盘；**禁止**写在 `source_root`（入口 A 原地/只读旧仓）。

**与 README 分工**：`.auto-nn/migration-summary.md` = HARD-GATE 全文归档（迁移留档）；`README` 的 `D2_DATA_SPLIT` / `AGENT_BOUNDARY` / **`SCENARIO_POLICY`（场景权威）** 等 = 实现用结构化块（由阶段 2/3 按 F1 摘录，verify 检块而非全文 F1）。

#### F1-contract 矛盾项检查（发出 F1-contract 前必跑；有 FAIL 不得请用户「① 确认」）

Agent 汇总 F1-contract 后、请用户签字前，**必须**根据下表自检，并在 F1-contract 正文后附 **`## F1-contract 矛盾项检查`**（每项 `PASS` / `FAIL`；**任一 FAIL** 须先改 F1-contract 对应行并附**修改建议**，再重新发出整份 F1-contract）。

| ID | 若 F1-contract / T2-callchain 出现 | 且同时出现 | 判定 | 修改建议（二选一或补附件） |
|----|-----------------|------------|------|---------------------------|
| **C1** | T2-callchain：**无**训内 `ws.evaluate` /「循环内不 evaluate」 | E4：`E4_训内节奏=A` 或 `C`（含稀疏训内 eval） | **矛盾** | **甲**：T2-callchain 调用链补上 `ws.evaluate`（写清触发，与 E4 一致） / **乙**：E4 改为 `B`；E8 若曾为 `best` 改为 `last` |
| **C2** | T2-callchain：无训内 evaluate | E8：`checkpoint: best` 或「训内 eval 选 best」 | **矛盾** | **甲**：同 C1 甲 + 保留 E8 best / **乙**：E8 改为 `last`（`CHECKPOINT_POLICY: last`） |
| **C3** | E4：`E4_训内节奏=B` | E8：`best`（依赖训内指标选优） | **矛盾** | E8 改 `last` 或 `none`；或 E4 改为 A/C 并改 T2-callchain |
| **C4** | E4：`E4_训内节奏≠B` | E4-keys / 文案未说明 `ws.evaluate` 覆盖 **E1** 全部键（或 physical ② 的 proxy 键集） | **矛盾** | 在 E4 或 F1-contract 附件列出训内返回键；实现阶段对照 E1 |
| **C5** | E3：`contract.test` 仅返回 **E1 子集** | E2：其余 E1 键为 `primary`/`auxiliary`（非 `notes_only`） | **矛盾** | E3 改为返回 E1 全部键（可 NaN）；或 E2 把未返回键降为 `notes_only` 并说明用途 |
| **C6** | E6：`SCENARIO_AXIS=none` / 无可轮换项 | F1-contract **无**「场景清单」表，或 **默认配置（起跑线）** 全空 | **矛盾** | 附场景清单 ≥1 行；默认配置写清（见块 E）；`none` 只表示不轮换 |
| **C7** | D2-data-split / 块 E：声明多套 **不可比**默认配置或 `SCENARIO_CANDIDATES` 含 `\|` | E7：`ledger_context_keys` **未含** 那些决定含义的键；清单默认配置也未写 | **矛盾** | E7 补键（与 `finalize_run` cfg 同名）和/或清单补默认配置；E9 写清 substr/配置族 |
| **C8** | D2-data-split：`SCENARIO_CANDIDATES` 多 ID 或清单 ≥2 行且 **数据与指标** 不同 | E9：`history_experiment_substr` 空且未说明「全表混比」 | **矛盾** | E9 按行给 substr/池；或 D2-data-split 收窄为单场景并改清单 |
| **C9** | E6：`SCENARIO_POLICY=rotate` 或 `multi_eval_one_train` | E6：`SCENARIO_AXIS=none` 且无 **E6b 等价**说明（单场景多评等） | **矛盾** | 改 `SCENARIO_POLICY=focus`；或补探索轴 + `scenario_bindings` |
| **C13** | G1：`explore` 或 `innovate` | E6：`SCENARIO_AXIS=none` 或用户选「固定单一架构、不换模型」且 D1 含 **automatic** / 多架构对照意图 | **矛盾** | 按 G1 重定 E6（通常「只换模型 + 分池」）；或改 G1 为 `optimize` 并在 F1 说明只做单线冒烟 |
| **C14** | 对话顺序 | **E6-scenario 在 G1/G2 之前**已问用户 | **流程 FAIL** | 停止；补问 G1/G2 后 **重问 E6** 并引用 G1 结论 |
| **C10** | D2-data-split / F1-contract：`E4_EVAL_FOR_KEEP=contract.test only`（或 KEEP 仅终评） | E4：`E4_PATH=①-delegate-test` 且训内节奏 A/C（训内调完整 `contract.test`） | **风险提示** | 可并存但须在 F1-contract 勾「接受训内 test 级墙钟」；KEEP 仍仅终评 |
| **C11** | O2-gpus-parallel：`max_parallel>1` | F1-contract / O2 未写训末 **`finalize-round`** 责任 | **矛盾** | O2-gpus-parallel 或 F1-contract Ops 行写明：多槽训末须 `python -m contract finalize-round` |
| **C-I1** | I1：`CONSUMES=train_split_only` 或 `no_files` | `EVAL_ONLY=[]`（没写哪些只评） | **矛盾** | 补只评资产（路径 glob 或 `contract.` 读取函数名）；或改 I1=A 并说明确无只评数据 |
| **C-I2** | I2：`PATH=restricted` 或 `eval_mode_locked` | `IMPL` 空，或 E3 官方终评描述未写 `run()` 必调该手续 | **矛盾** | 补手续函数名 + 一句规则；E3 行写明「run() 必经 `<IMPL>`」 |
| **C-I3** | I1：`CONSUMES=no_files` | D2 `TRAIN` 写了数据文件路径，或 D3 声明训内读文件 | **矛盾** | 改 I1=B（列只评）；或 D2/D3 改为「训练样本由代码生成」 |
| **C-I4** | I3：列了训练 batch 键白名单 | T2 调用链 / E4 训内返回键与白名单键名不一致 | **矛盾** | 对齐键名（以 T2 为准改 I3，或反之） |
| **C-I5** | I1：`CONSUMES=all` | D2 `OFFICIAL_TEST` 用了 `TRAIN` 未含的数据（存在只评数据却选「全部能训」） | **矛盾**（**豁免**：T1 常见可试 data-loss **开** — 官方终评仍用该场、训练也允许用，须在 F1 写明） | 关按钮：改 I1=B 并把该数据列入 `EVAL_ONLY`；开按钮：保持 I1=A 并写「场可进训练，官方分仍打该场」 |
| **C-DL1** | T1 常见可试 data-loss **开** | I1 `CONSUMES=no_files` | **矛盾** | 改 I1=A（或训练份含该场）；或关掉 data-loss 按钮 |
| **C-DL2** | T1 常见可试 data-loss **关** | T1「可以加」仍含场监督 / data-loss | **矛盾** | 划掉可以加；或改开按钮 |
| **C-DL3** | T1 常见可试 data-loss **开** | `INFO_PERM.enforce=True` | **矛盾** | 阶段 2 必须 `write --enforce no`；禁止手改 |
| **C-DL4** | T1 常见可试 data-loss **关** | `INFO_PERM.enforce=False` | **矛盾** | 阶段 2 必须 `write --enforce yes`；禁止克隆后改关 |
| **C-DL5** | 对照两臂 | T1「必须留着」不是同一套（如一臂无 PDE 残差） | **矛盾** | 按钮只动「可以加」；必须留着两臂相同 |

**输出模板（贴在 F1-contract 表后）：**

```markdown
## F1-contract 矛盾项检查
| ID | 结果 | 说明 |
|----|------|------|
| C1 | PASS/FAIL | … |
| … | … | … |
**合计**：FAIL=0 方可请用户 F1-contract=①；FAIL≥1 须先改表并复述修改建议。
```

**与用户对话：** 若有 FAIL，消息须含「**矛盾项 Cx**：… → **建议**：…」；不得仅说「请确认 F1-contract」。

### Agent 交互规范（Cursor / Claude Code 通用）

> **双层呈现**：本节【确认选项】①②③、【选后锁定】、F1-contract 表是 **agent 内部工作表**（规划落盘 + `init-qa-log.lock`）。**用户消息**只发 [`SKILL.md`](SKILL.md) **四段式**（含 mandatory「这一步在定什么」）+ A/B/C；**禁止**把六段工作表或 lock 表复制给用户。`append-init-qa-log --ask` = 用户看到的问句（人话）；`--lock` 可技术化。

阶段 1（HARD-GATE）与用户的对话须遵守下列规则，**避免**一次贴出 H/D/I/E/T/O 全表或「27/24 项问卷」：

| 规则 | 要求 |
|------|------|
| **一问一轮** | 每轮用户可见回复**只处理一个编号**（如 `H1-legacy-artifacts` → 等用户确认 → 再 `H2-experience`）。允许 policy 并联（见 init-interaction-policy.yaml）；**默认单题**。 |
| **顺序固定** | 仍按 [确认流程](#确认流程) 第 2 步的顺序；不得跳号，不得并行抛出多项。 |
| **单条六段** | 含 ①②③ 类选项时 agent **内部**须含【现状】/【模板默认】、**【现有清单】**、【为什么问】、【模板建议】、**【确认选项】**、**【选后锁定】表**（见 [确认选项可辨规范](#确认选项可辨规范)）；**对用户只发 SKILL 四段式**，禁止把六段或【选后锁定】表复制给用户。 |
| **子表归属** | `D2-data-split` 划分表、`E4-train-eval` 内 E4_PATH/节奏等可在**该编号的一条消息内**用表格呈现，但仍算**一个编号**，不得与 `D3-workspace-data`、`E1` 等同条发出。 |
| **F1-contract 时机** | 入口 A **27** 项 / 入口 B **24** 项**全部**经用户确认后，**单独一轮**输出 [阶段 F — F1-contract 汇总表](#阶段-f收尾finalize仅-f1-contract)（含 **F1-contract 允许** 字段 + [F1-contract 矛盾项检查](#f1-contract-矛盾项检查发出-f1-contract-前必跑有-fail-不得请用户-确认)）供签字；此前**禁止**预发完整 F1-contract。 |
| **快速路径** | 即使 `fast_path_eligible`，「仍须单独问」的项（H1-legacy-artifacts～H3-agent-boundary、D2-data-split、**I1-train-consumes～I2-official-path**（迁入源对齐）、**D4-repro-data**、**T2-callchain**、**E4-train-eval**、O1-time-budget～O4-repro-determinism 等）也须**逐编号**问，不可因快速路径合并成一张总表。 |
| **阶段 0 例外** | `migration-compare` 的 Markdown 报告可整段贴出（只读分析，非 HARD-GATE 提问）。 |

用户修改某编号后：仅**重新展示该编号**（见确认流程第 3 步），不要顺带重发后续未问项。

**Cursor / Claude Code 无差异**：同一 Skill 正文；若产品默认批量输出，Agent **必须**主动拆成多轮。

**自检（发出前，与 SKILL 四问对齐）：**

1. 用户消息是否含 **「这一步在定什么」** 一句（见下表）？缺 → 补。
2. 本条是否**恰好一个** slug 级主题？若并联，子题是否 ≤2 且 policy 同一 bundle、入口/依赖满足？若 ≥2 个编号块且非 policy 并联 → 拆条发送。
3. 用户消息是否命中 SKILL 禁词表？命中 → 改人话。
4. 含 ①②③ 时（内部工作表）：用户能否**不读仓库**说出「选 B 比选 A 多/少锁哪一条」？**不能** → 补全【现有清单】与【选后锁定】后再发**给用户**的四段式（仍不得贴 lock 表）。

**用户若批量回复**（如 `H1-legacy-artifacts=①, H2-experience=①`）：视为已确认多项，Agent **仍须**在后续补问时**一次只追问一个**未决编号，不得因用户批量答而恢复「整表提问」。并联 bundle 内两 slug 同轮答完 → **各 append 一次** log；用户选「分开问」→ 本轮不 append，下轮恢复单题。

#### init-interaction-policy

真源：`docs/init/init-interaction-policy.yaml`（业务仓经 `governance-sync` Init 组 sync；未 sync 时 fallback `<template_root>/template/package/docs/init/`）。

- v1 仅 `bundle-h-cleanup`（入口 A：H2+H3，依赖 H1 已确认）
- 扩表须修订 spec + 本 reference 依赖审查 + 可选单测 fixture
- Agent **禁止**自行发明 bundle；读 policy 可用 `scripts/lib/init_interaction_policy.py`（`PYTHONPATH=scripts`）

#### 对用户一步白（四段式第 0 段；SKILL §2.1 副本）

agent 对用户发问前，从本表取 1 句（可改写，禁 slug/函数名）：

| 编号 | 一步白 |
|------|--------|
| `D1-scenario-inventory` | 要支持几种「官方实验设定」，各自起跑配置是什么。 |
| `D2-data-split` | 训练/验证/终评怎么分；终评用哪套数据。 |
| `I1-train-consumes` | 训练时哪些数据能碰、哪些只能等打分时才打开。 |
| `I2-official-path` | 官方分必须走哪条路算出来（多数整网直接出；必须走规定手续选受限路径；必须在指定状态下打分选固定评测态）。 |
| `I3-other-info-rules` | 除了训练材料和打分通道，还有没有别的信息不许乱流。 |
| `D3-workspace-data` | 数据加载、增强写在代码哪一层。 |
| `D4-repro-data` | 复现实验时要锁哪套数据路径/版本。 |
| `H1-legacy-artifacts` | 旧成绩表和实验目录留不留。 |
| `H2-experience` | 旧「踩坑笔记」要不要写进新项目。 |
| `H3-agent-boundary` | 旧 README 里硬规则要不要保留。 |
| `T1-loss-layers` | **不是**问现在用哪个 loss；**是**定以后自动改实验时训练目标的底线与松紧。 |
| `T2-callchain` | 训练循环怎么转：几层循环、何时打分。 |
| `E1-metrics` | 主分是什么、还有哪些辅分。 |
| `G1-experiment-mode` | 这轮主攻把分做高，还是也要试新方法。 |
| `G2-goal-value` | 主分要到多少算达标（或摸底护栏）。 |
| `E2-metric-tier` | 哪些分写进成绩表主列、哪些只当备注。 |
| `E3-official-test` | 训**结束后**正式打分怎么跑。 |
| `E4-train-eval` | 训练**过程中**要不要打分、多久打一次。 |
| `E5-tsv-columns` | 成绩表有哪些列、分哪几块；固定带基线角色列（`baseline_tag`）。 |
| `E6-scenario` | 每轮允许改什么、多场景怎么轮换、最好成绩怎么分开比。 |
| `E7-run-context` | 哪些超参要记进成绩表方便事后对照。 |
| `E8-checkpoint` | 要不要存权重、存最好还是最后一轮。 |
| `E9-keep` | 什么情况下算「这次更好、要留下来」。 |
| `O1-time-budget` | 单次训练最长跑多久。 |
| `O2-gpus-parallel` | 用哪些 GPU、最多几路并行。 |
| `O3-baseline-anchors` | 该场景起步 plain+reference 尺子。 |
| `O4-repro-determinism` | 随机种子与确定性设置。 |
| `P0-project-brief` | 先对齐「这是什么项目」再逐项确认。 |
| `F1-contract` | 汇总你已选的口径，签字后才开始改代码。 |

---

### 确认选项可辨规范

凡【确认选项】含 **采纳建议 / 只锁现有 / 自定义**（或「保持现状」等价语义）时，**每条消息**须按下列顺序（六段）；禁止只写「② 保持现状（写入 F1-contract）」而不附对比表。

1. **【现状】**（入口 A）或 **【模板默认】**（入口 B）— 可短句；事实条目进下条
2. **【现有清单】** — **3～7 条 bullet**（从阶段 0 盘点表 / 代码）；禁止用散文代替清单
3. **【为什么问】**
4. **【模板建议】**
5. **【确认选项】** — 须用人话标签（或等价）：
   - **① 采纳建议**（按【模板建议】写入 F1-contract）
   - **② 只锁现有清单**（不套建议表，【现有清单】原样进 F1-contract）
   - **③ 自定义**（用户指明不可改 / 可调 / 技巧）
6. **【选后锁定】** — 必填表：

| 你选 | F1-contract 会写什么 | 和【现有清单】的差别 |
|------|------------------------|----------------------|
| **①** | … | … |
| **②** | … | … |
| **③** | … | … |

**①≈② 时**：对比后无实质差别 → 写「**① 与 ② 等价，推荐只选 ①**」；【选后锁定】可只保留 ①、③ 两行并说明 ② 不另增约束。

**不适用六段全表**：无「保持现状」语义的简答项（如 O1 仅改秒数）— 仍须写清各选项后果，可用简表替代三行【选后锁定】。

**每条问题（无 ①②③ 时）** 仍至少含：【现状】或【模板默认】、【为什么问】、【模板建议】、【确认选项】。

**确认流程：**
1. Agent 确定入口类型（A/B）；入口 A 完成阶段 0（`migration-compare` + 盘点表 v0）
2. 发 **P0-project-brief**，用户 **P0=①**（或 ② 纠正至 ①）
3. 遵守 [Agent 交互规范](#agent-交互规范cursor--claude-code-通用)（**每轮一问一编号**）
4. 入口 A：**D1→D2 → I1→I2→I3 → D3→D4 → H1→H2→H3 → T1→T2 → E1 → G1→G2 → E2→…→E9 → O1→O2→O3→O4 → F1-contract**；入口 B：**D1→D2 → I1→I2→I3 → D3→D4 → T1→T2 → E1 → G1→G2 → E2→…→E9 → O1→O4 → F1-contract**（无 H）。带 `--answers` 时每步先查 `.auto-nn/init-answers.resolved.json`（见 [答案清单协议](#答案清单协议--answers)）
5. 用户修改某项后，Agent 立即重新展示**该项编号**的确认（仍须满足 [确认选项可辨规范](#确认选项可辨规范)，不得夹带其它编号）
6. 前后项有依赖时，Agent 自动重新推导后续提案
7. 入口 A：现状已符合模板的项可标注"确认即可"；**T1/T2 即使确认即可也须附内容**（T1：loss 一句摘要；T2：**调用链 ≤6 行**）
8. 入口 A **27** 项 / 入口 B **24** 项（**不含 P0**）全部确认后才可进入 **阶段 2（实现）**
9. F1-contract 通过后 **必须**向用户发送 [F1-contract 通过后 — 强制回复模板](#f1-通过后--强制回复模板)（澄清 ≠ 完成）

确认后、改代码前，Agent **必须**自检：
- `set(metric_keys) ∩ set(auxiliary_keys) == ∅`（互斥）
- `metric_keys` 非空
- `metric_keys` + `auxiliary_keys` 中每个键都在 `_default_tsv_columns()` 返回的列表中
- `ws.evaluate()` 返回 dict 覆盖 `metric_keys` + `auxiliary_keys` 所有键
- `contract.test()` 自主实现；禁止 `test`→`ws.evaluate`；`python3 -c "from experiment import check_test_authority; assert not check_test_authority('.')"`
- `keep_threshold` 为空时 `nn-config.yaml` keep 段配置合理
- H1-legacy-artifacts 选"舍弃"时：`_runs/results.tsv` 已删除或已覆盖为模板初始版本
- H2-experience 选"提炼重写"时：新 EXPERIENCE.md 已写入至少一条经验
- H3-agent-boundary 有候选时：F1-contract 确认记录含用户勾选项，且仅勾选项写入 README / `AGENT_BOUNDARY`；H3-agent-boundary 舍弃时 README 无旧文档照搬约束
- **E6-scenario** 非 `none` 或 H3-agent-boundary 勾选 `benchmark_protocol`/`migration_scope`：README 须有 `SCENARIO_POLICY` / `AGENT_BOUNDARY`（若适用）；业务仓 verify §6d 将通过
- **F1-contract 场景清单**：块 E 每行 **默认配置（起跑线）** 在清单或 E7「运行参数表」中有落点；`SCENARIO_AXIS=none` 时清单仍 **≥1 行**

#### 阶段 2：实现（按 **F1-contract 口径合同表** 改码）

**F1-contract 是什么？** 阶段 1（HARD-GATE）结束时，用户签字确认的一张 **口径合同表**：汇总 H/D/E/T/O 各块的决定（含 **E4_训内节奏** = 训内多久评一次、**E4_PATH** = 训内怎么算分）。定稿须落在 **`.auto-nn/migration-summary.md`**（见上节）。**有 F1-contract 才能改代码**；**有 F1-contract ≠ 迁移完成**（完成须阶段 4：`verify` + smoke）。

- HARD-GATE 全部确认且 **F1-contract 已发送给用户** 后：`executor.execute_plan` 或 Subagent（见下文）；`NN_RELAUNCH=1`。
- **只按 F1-contract 表**改 `contract/`、`workspace/`、`train.py`；**不在 F1-contract 里列**删文件、跑 verify、全文改 README（那些归阶段 3）。
- **不在此阶段**对用户说「迁移完成」。

**阶段 2 结束 — Agent 必跑自检（未通过不得进入阶段 3）**

```bash
cd <project_root>
# 通用
PYTHONPATH=. python3 -c "from experiment import check_test_authority; v=check_test_authority('.'); assert not v, v"
PYTHONPATH=. python3 -c "from experiment import check_train_exp_dir_layout; assert not check_train_exp_dir_layout('.')"
# profile=rl 时额外（D2-data-split/E4 代码级，不靠口头 F1-contract）
python3 scripts/rl_workspace_gate.py .
# 信息权限（I1–I3 落表后）：README 块 ↔ 合同一致 + 静态扫描（IP1–IP5）
python3 scripts/info_perm_gate.py .
python3 scripts/lib/info_perm.py .          # 静态扫描 IP1–IP5，exit 0 方可
```

- **禁止**用旧版 verify 输出充当「已自检」；须在本轮改码后执行上述命令。
- **RL** 若 F1-contract 选 **E4_PATH=② 独立轻量**：README 须含 `E4_EVALUATE_INDEPENDENT: yes`，否则 `rl_workspace_gate` 要求 `evaluate` → `contract.test`。
- **supervised** 默认 `E4_PATH=②-same-metrics`：无需该行；`ws.evaluate` 须复用 test 指标函数（非仅 val_loss）。

#### 阶段 3：交付卫生

入口 A **不会**自动复制根目录交付物；入口 B 的 `new-project.sh` **不再复制** `docs/`、`skills/`、`template/maintainer/`。按 **[`template/package/CHECKLIST.md`](../../../template/package/CHECKLIST.md) §2–§4** 处理 verify **未覆盖** 的手工项：

#### 阶段 4：验收（唯一对外门禁）

在 `<project_root>` 依次执行，**均通过前禁止宣称迁移完成**：

1. `bash <template_root>/scripts/governance-sync.sh --template-root <T> --project-root <P>`（若阶段 3 已做可重复）
2. `bash scripts/verify-migration-complete.sh` → **exit 0**（输出须含 `治理文件已与模板同步`；**缺此行 = 未 governance-sync，禁止报完成**）
3. **`bash scripts/nn-doctor.sh`** → **0 FAIL**（任一 FAIL = 真迁移缺陷，**阻断 handoff**：人话列 FAIL → `/auto-nn-modify` 修 → `/auto-nn-doctor` 确认 0 FAIL；WARN 不阻断。0 FAIL 时把输出归一为 `检查名<TAB>状态[<TAB>计数]` 写入 `saved/doctor_last.txt`，作 `/auto-nn-analyse` doctor-diff 首基线；check 名按人话翻译）
4. **`bash scripts/smoke-check.sh`** → exit 0（§5；**supervised 脚本内 `NN_EPOCHS=2`**，勿误以为要跑满 `train.py` 顶部 `EPOCHS`；按 profile 分轨，勿手写 grep）
5. 向用户发送 [验收通过 — 强制回复模板](#验收通过--强制回复模板)（**须粘贴 verify 末 5 行**，不得只写「已通过」）

阶段 3 手工项摘要：

   - **治理同步（必做）**：`bash <template_root>/scripts/governance-sync.sh --template-root <T> --project-root <P>` — 覆盖 `profiles.yaml`、`scripts/verify-migration-complete.sh`，写入 `.auto-nn/governance-rev`（verify §0 校验；防 experiment.py 新而 profiles/verify 旧）
   - **清理模板特有文件**（若存在则删）：`docs/`、`skills/`、`skeletons/`、`scripts/init.sh`、`scripts/generate-profile-locks.sh`、`scripts/new-project.sh`、根目录 **`automation-logs-nn/`**、`.claude/`、**`NN_PROFILE`**、历史名 **`run-nn-agent.sh`**（已废止）。**须保留**：`auto-nn-run.sh`、`reflect.py`、`scripts/wait-train.sh`、`scripts/claude_stream_summarize.py`、`scripts/regen_results_tsv.py`、`scripts/verify-migration-complete.sh`（`wait-train` 亦由 `governance-sync` 同步）。
   - **`CHECKLIST.md`** — 对照用模板根副本；业务仓库收尾后**应删除**。
   - **`_runs/logs/`**、**`_runs/agent/`** — 保留 README；勿在仓库根堆 `run_*.log`。
   - **`README.md`** — **只**改标题 + **`§3 立项口径`** + 可选 **`§4 PROJECT_NOTES`**；**禁止**改 `NN_TEMPLATE:*` / `SKILLS_*`；`governance-sync` 会 merge 模板 §1–§2
   - **TSV** — 迁 contract 后 `python3 scripts/regen_results_tsv.py --repo-root .`（verify 会校验表头）。
   - **verify** — 不在此重复列举；**以步骤 7 末尾硬停止为准**（失败项对照模板根 `CHECKLIST.md` §0–§4）。

---

## F1-contract 通过后 — 强制回复模板

F1-contract 确认后 **必须**发送（可填表）：

```markdown
### 口径已锁定（F1-contract）
| 项 | 决定 |
|----|------|
| H1-legacy-artifacts | … |
| D2-data-split | SPLIT_KIND=…; EVAL_USES/TEST_USES（详见 README `D2_DATA_SPLIT`） |
| I1-train-consumes | CONSUMES=all/train_split_only/no_files; EVAL_ONLY=[…]; READERS=[…]（来源：现场 / 清单） |
| I2-official-path | PATH=full_model/restricted/eval_mode_locked; IMPL=…; RULE=… |
| I3-other-info-rules | RULES=none/[…]; MACHINE=[batch_keys=…] |
| E4-train-eval | E4_PATH=②-same-metrics（或例外）; E4_训内节奏=A/B/C（触发：…） |
| O1-time-budget | time_budget=… |
| O2-gpus-parallel | gpus=…; max_parallel=…; finalize-round=… |
| O3-baseline-anchors | start_runs=plain+reference; … |
| D4-repro-data | REPRO_ENV_KEYS=…; 数据基线=… |
| O4-repro-determinism | seed=…; cudnn=train.py代码确定性; SEED∈ledger_context_keys |
| G1-experiment-mode | experiment_mode=optimize（或 innovate / explore） |
| G2-goal-value | goal_value=… 或 暂不设；explore 护栏 metric_floor=… 或 不设 |
| E9-keep | keep.mode=…; keep.primary_delta=…（用户所选档，非模板默认） |
| … | （H/E/D/I/T/O/G，≤21 行；带 `--answers` 时每行末注「来源：清单 / 现场」） |

### 下一步（未完成不得宣称迁移完成）
1. **阶段 2**：按上表改代码（`NN_RELAUNCH=1`）
2. **阶段 3**：`template/package/CHECKLIST.md` §2–§4（清理 / README / regen TSV / …）
3. **阶段 4-A**：`bash scripts/verify-migration-complete.sh` → 必须 exit 0
4. **阶段 4-B**：`bash scripts/nn-doctor.sh` → 必须 0 FAIL（FAIL 阻断 handoff）
5. **阶段 4-C**：`bash scripts/smoke-check.sh`

**禁止**在本消息使用：「迁移完成」「可以开始常规迭代」（除非 3+4 已执行并附命令输出摘要）。
```

---

## 验收通过 — 强制回复模板

阶段 4 全部通过后发送：

```markdown
### 迁移收尾验收通过
- governance-sync: rev=…（一行）
- verify: exit 0（粘贴含「治理文件已与模板同步」的原文末 5 行，禁止只写「通过」）
- doctor: 0 失败（粘贴 doctor 摘要：N 失败 / M 警告；`saved/doctor_last.txt` 已写）
- smoke-check: exit 0（粘贴 `[smoke-check] OK` 一行）
- 后续：可 `unset NN_RELAUNCH`，常规迭代只改 train.py / workspace/
```

---

### 入口 B：new-project（从 template/package/ 安装）

```bash
cd <template_root>
./scripts/new-project.sh <目标目录> <项目名> --profile supervised|rl|physical
```

立项对照 `profiles.yaml` → `profiles.<name>`；`new-project.sh` 会写 `nn-config.yaml`（**不复制** `docs/`、`skills/`，迁移技能见 `<template_root>/skills/maintainer/auto-nn-init`）；改 `contract/` 后仍须 **verify 0 + nn-doctor 0 FAIL + CHECKLIST §5** 方可声明立项收尾完成。

---

## `nn-config.yaml`（入口 A/B）

从模板根复制 [`nn-config.yaml`](../../../template/package/nn-config.yaml) 到目标项目（入口 B 由 `new-project.sh` 生成），按任务改 `profile`、`keep` 等。**`time_budget` / `gpus` / `max_parallel` / `exploration_mode` 须在 HARD-GATE O1/O2/G1 确认后写入或覆写**（O2：**算力估算推荐 K** + 显式 `gpus`；O3 写 `saved/baseline_start_intent.json`，**不**写 `agent.exploration`）。**`goal_value` 须在块 G（G2）确认后写入**。**不要**保留 `NN_PROFILE` 文件；若存在则删除。

- **`auto-nn-run.sh`**：启动时解析 `time_budget` → `export NN_TIME_BUDGET`；每轮 Agent prompt 注入 `gpus` 白名单、空闲 GPU、`max_parallel` 上限（仅 `max_parallel>1` 时文案推荐多槽 sweep）。

- **`exploration_mode`**（G1）控制总档与派生 `tier_start`；起步尺子见 O3-baseline-anchors / `saved/baseline_start_intent.json`（plain+reference）。
- **默认 keep 策略**（`nn-config.yaml`，`contract.keep_threshold={}` 时）：`improve_mode: any_primary`、`mode: relative`、`primary_delta: 0.005`（0.5% 相对改善）、`near_best_abs: 0`。**立项时 E9 须让用户按指标族选档，禁止直接保留此默认**；见 [E9-keep](#e9-keep--keep-进步线按指标族选型) 与 [`metric-family-keep-presets.yaml`](metric-family-keep-presets.yaml)。
- **`primary_delta`** 在 `mode: relative` 下为**相对历史最佳的比例**（与 TSV 量纲无关）；`mode: absolute` 时为绝对差值。
- **`near_best_abs`** 仅在与 `mode: absolute` 联用时有意义；默认相对模式下设 `0`。
- 若 `contract.keep_threshold` 非空 dict，yaml 的 `keep` 段**不生效**；模板演示项目 contract 为空 `{}`，由 yaml 提供 keep 默认。
- **`keep.improve_mode`**：`primary` | `any_metric` | `any_primary` | `all_primary`。后两者针对 `contract.primary_metric_keys`（默认 `(metric_key,)`；多主指标任务在 contract 覆盖，**勿**在 yaml 列指标名）。可选 `contract.history_experiment_substr` 限定历史对照池。

---

## Profile 边界

**不要在本 SKILL 里维护方法表** — 以 `profiles.yaml` 为准；语义见其中 `semantics`（`ws.evaluate` = epoch 监控，`contract.test` = 台账终评）。

```python
boundaries = load_profile_boundaries(template_root)
boundary = boundaries[profile_name]  # contract_methods / workspace_methods
```

### workspace 文件名自由（守门只认方法，不认文件名）

`profiles.yaml` 的 `recommended_files`（`model.py` / `loss.py` / `train_loop.py` / `data_process.py` / `infer.py`）**只是起步命名建议**，**不参与任何 gate**。迁移时旧项目的子模块叫什么、怎么拆包，**都不影响验收**：

- **被强制的是 `Workspace` 类上的方法**（`build_learner` / `train_step` / `evaluate` … 见 `profiles.yaml` 的 `workspace:`），由 **G-范式 / G-门面** 校验；逻辑散在 `models/`、`losses.py`、任意子包都行。
- **唯一与文件相关的历史耦合已移除**：RL 的 `make_eval_env` 守门（G-评估 A5 / nn-doctor `rl_make_eval_env`）现在**扫 `workspace/**.py` 按函数名定位**，不再绑定 `workspace/infer.py`。约束只剩「**若**提供 eval-env 工厂，函数须叫 `make_eval_env` 且 `mode` 优先用参数」（`profiles.yaml` → `rl.required_capabilities`）。
- 因此对用户/迁移 Agent 的口径：**「文件名随你，方法名照 `profiles.yaml`」**；`new-project.sh` 会在 `workspace/RECOMMENDED_LAYOUT.md` 写出建议布局，仅供参考。

---

## README 三层结构（init / governance-sync 契约）

业务仓根 `README.md` 与 **`template/package/README.md`** 同骨架；分工如下。

| 区域 | 标记 | 谁写 | `auto-nn-update` 行为 |
|------|------|------|------------------------|
| 标题 | 首行 `# …` | init 改项目名 | **保留**业务仓标题 |
| 导航 + §1 | `NN_TEMPLATE:NAV` / `QUICKSTART` | 模板 | **覆盖**为模板最新 |
| 技能体系 §2 | `NN_TEMPLATE:SKILLS`（内嵌 `SKILLS_GUIDE` / `SKILLS_SCENARIOS`） | 模板 | **覆盖** |
| 立项口径 §3 | `§3.1` prose + `D2_DATA_SPLIT` / `SCENARIO_POLICY` / `METRICS_SNAPSHOT` / `AGENT_BOUNDARY` | **init 阶段 3** | **保留**（merge 脚本强制还原业务块） |
| 项目维护 §4 | `PROJECT_NOTES` | init 摘要 + **人** | **保留** |
| 附录 | `NN_TEMPLATE:APPENDIX` | 模板 | **覆盖** |

**init Agent 禁止**：删除或重写 `NN_TEMPLATE:*` / `SKILLS_*` 块；把指标/数据写进 §2；全文覆盖 README。

**init Agent 必须**：更新首行标题；在 **`§3.1 评估与指标`** 写 test/evaluate/metrics（见下节）；填 §3.2–§3.5 结构化块；可选 **`§4 PROJECT_NOTES`** 一行摘要。

**阶段 3 governance-sync** 会运行 `scripts/merge-readme-template-blocks.py`（与迁后 `/auto-nn-update` 相同逻辑）。

---

## `contract.test`、`workspace.evaluate` 与 metrics（迁移必须写清）

与 `profiles.yaml` 中 **`semantics`** 对齐；Agent 在迁移收尾 **必须** 在目标仓库 **`README.md` → `§3.1 评估与指标`** 中写清下列三点，避免与训练损失（`build_objective`）混淆：

### 迁移要求：test 逻辑归 contract（所有 profile 必须实现）

**`contract.test()` 是台账评估的唯一实现；禁止调用 `ws.evaluate()`。`ws.evaluate()` 可调用 `contract.test()` 复用口径，不可反向。** 迁移时必须：

1. **明确 metrics** — 主指标键名、辅助指标、归一化方式（写入 `contract/metrics.py`）
2. **E2：向用户说明 `contract.test` 怎么操作**（数据、怎么跑、关键参数），用户确认对不对；RL 须在实现中显式 `mode="knn"` 等
3. **台账实现放在 `contract/test.py` 的 `run()`** — 门面 `Contract.test()` 仅委托；禁止 `ws.evaluate`；实现可内联或调用 `workspace.infer` 辅助函数（非模板 API）

模板目录（supervised 示范）：
```text
contract/
  metrics.py       # METRIC_KEYS, AUXILIARY_KEYS
  runtime.py         # 常量（数据根、归一化；RL 迁时扩展）
  prepare_data.py    # prepare_data(contract, cfg)；RL 可用 prepare_shared_context
  test.py            # def run(...): 台账循环 + ws.predict
  __init__.py        # 薄门面：委托上述模块
```

RL 项目 `contract/test.py` 示例（逻辑写在 contract，参数写死）：
```python
def run(learner, ws, *, shared_context):
    from workspace.infer import make_eval_env, run_independent_eval
    from contract import N_EVAL_EPISODES, EVAL_SEED, REWARD_TARGETS_FINAL
    env = make_eval_env(
        dataset_path=shared_context["dataset_path"],
        mode="knn",
        benchmark_jsonl="data/eval_benchmark_v1.jsonl",
    )
    try:
        return run_independent_eval(
            learner, env,
            targets=REWARD_TARGETS_FINAL,
            n_episodes=N_EVAL_EPISODES,
            eval_seed=EVAL_SEED,
            structure_names=...,
        )
    finally:
        env.close()
```

**反模式（禁止）：** `contract.test` 内 `return ws.evaluate(...)`；`infer.make_eval_env` 仅读 `PERF_MODEL_MODE` 环境变量（见 MLP self-eval 事故）。

| 主题 | 须说明的内容 |
|------|----------------|
| **`workspace.evaluate`** | **何时调用**（通常为 `train.py` 每个 epoch 后）；**用的哪个 DataLoader**（如 `prepare_data` 返回的 val）；**返回字典里有哪些键**、与 `contract.metric_key` / `contract.aux_metrics` 如何对应；**指标定义**（公式或口径一句话，或指向 `contract/metrics.py` 等实现文件）。 |
| **`contract.test`** | **何时调用**（`train.py` 训末 + `finalize_run`）；**自主实现**（禁止 `test→ws.evaluate`）；**test 集/模式**（RL：`mode="knn"` + 冻结题集）；**`ws.evaluate` 若需同口径可调用 `contract.test`**。 |
| **metrics** | **主指标键名**（`metric_key` + `metric_direction`）、**辅助指标**（`aux_metrics`）；**实现位置**（如 `contract/metrics.py` 或内联于 `workspace`）；**各键的量纲**（如百分比、dB、loss）；若 `evaluate` / `test` 返回值缺键，台账与 `should_keep` 会不一致。 |

**自检：** epoch 监控用 `ws.evaluate`；训末须 `contract.test(` 且通过 G-评估：`python3 -c "from experiment import check_test_authority; assert not check_test_authority('.')"`.

---

## experiment.py 策略

| 情况 | 做法 |
|------|------|
| 推荐 | **删除**目标项目内副本，使用模板根 `experiment.py`（单文件基类，勿 fork 修改）。 |
| 目标项目仍自带自维护 `experiment.py` | `compare_experiment_methods` + `executor.apply_experiment_injection` 补缺失方法（易漂移，迁完应删除副本、改用模板根文件）。 |

`executor` **不会**自动改写 `contract/` / `workspace/` 业务逻辑，只记录 plan 中的 `contract_changes` / `workspace_changes` 供 Agent/人改。

---

## executor 自动 vs 人工

| 自动（`execute_plan`） | 人工 / Agent |
|------------------------|----------------|
| `__backup_migration__/` 备份 | 按对照表改 `contract/`、`workspace/` |
| 可选 `experiment.py` 方法注入 | 拆模块到 `workspace/`，门面留在 `Workspace` |
| | 清理根目录探针 `.py` → `workspace/scripts/`；确保 ``train.py`` 中 `exp_dir` 为 ``_REPO_ROOT / "_runs" / "exp" / …`` |
| | 从模板复制并保持 **`scripts/claude_stream_summarize.py`**（与根目录 `auto-nn-run.sh` 配套；缺则 stream-json 摘要管道会失败） |
| | 从模板复制 **`_runs/logs/README.md`**、**`_runs/agent/README.md`**；训练 stdout → **`_runs/logs/`**，编排日志 → **`_runs/agent/`**（勿在仓库根堆 `run_*.log` 或 `automation-logs-nn/`） |
| | 写 `nn-config.yaml`、立项时改 `contract/` |
| | **`README.md`** — **只**改标题 + **`§3 立项口径`** + 可选 **`§4 PROJECT_NOTES`**（**禁止**改 `NN_TEMPLATE:*`）；`governance-sync` merge 模板 §1–§2 |
| | 创建 **`data/README.md`**（数据文件名 + 形状 + 来源）；**`pyproject.toml` 元数据** 按 CHECKLIST §2 |
| | 更新 `pyproject.toml` 的 name / description / authors |

---

## Subagent 执行模式

HARD-GATE 确认后，**代码编写应委派给 subagent**，主智能体负责 **review 和协调**：

**分工：**
- **主智能体（controller）**：逐项确认 HARD-GATE、分配任务、review 产物、跑 smoke test
- **Subagent（implementer）**：根据精确指令写单个文件（contract、workspace、train.py 等）

**流程：**
1. 主智能体完成阶段 1 HARD-GATE（入口 B 24 项 / 入口 A 27 项 / update 15 项）→ 发送 **F1-contract 通过后模板**
2. 主智能体为每个待写文件派发 subagent（阶段 2），prompt 含：
   - 确认过的 metrics/test/TSV/keep 具体值
   - 目标文件路径
   - 需要参考的源文件路径
   - 精确的接口要求（继承 ExperimentBase，实现哪些方法）
3. Subagent 完成后，主智能体 review 代码（同 HARD-GATE 后自检项）
4. 主智能体执行 **阶段 3**（CHECKLIST §2–§4）
5. **阶段 4-A**：`bash scripts/verify-migration-complete.sh` **exit 0**（未通过 **禁止** 对用户说迁移完成）
6. **阶段 4-B**：`bash scripts/nn-doctor.sh` **0 FAIL**（有 FAIL **禁止** handoff → `/auto-nn-modify` 修 → `/auto-nn-doctor` 复检）
7. **阶段 4-C**：CHECKLIST **§5 smoke**
8. 发送 **验收通过模板**

**Subagent prompt 要求：**
- 必须包含完整上下文（不依赖 subagent 自行搜索）
- 必须包含精确的文件路径
- 必须包含接口签名和返回值要求
- 禁止 subagent 修改确认表以外的内容

---

## 临时脚本

- 探路脚本只放 **`workspace/scripts/`**（见该目录 `README.md`）。  
- 不要留在仓库根目录（preflight **G-布局 会警告**；迁移对照表也会列出）。

---

## 模块说明

| 文件 | 作用 |
|------|------|
| `profile_data.py` | 读 `profiles.yaml`；`require_profile` 读 nn-config |
| `migration-compare.py` | **官方**阶段 0 CLI；`scripts/migration-compare.sh` 包装 |
| `comparator.py` | AST 方法对照（供 migration-compare 调用，勿手写循环） |
| `experiment_diff.py` | 项目 vs 模板 `experiment.py` 方法差异（自带副本时） |
| `executor.py` | 备份、`experiment.py` 方法注入（不自动改 `train.py`） |

---

## 完成确认

### 入口 B（新建）完成清单

与 CHECKLIST **§0** 一致（阶段 2 改 contract 后）：**verify 0 + nn-doctor 0 FAIL + §5 smoke**。

每项都要在交付前**人/Agent 真跑一遍**：

```bash
cd <目标项目>
# 阶段 0（可选，改 contract 前）
bash <template_root>/scripts/migration-compare.sh --template-root <template_root> --project-root .

poetry install
test -f nn-config.yaml && python3 -c "import yaml; print(yaml.safe_load(open('nn-config.yaml'))['profile'])"  # 1. 范式标签
test -f _runs/results.tsv && head -1 _runs/results.tsv    # 2. 台账初始化
poetry run python -c "from contract import create_contract; \
  c=create_contract({}); \
  assert c.metric_key and c.metric_direction in ('maximize','minimize'); \
  assert isinstance(c.keep_threshold, dict); print('contract OK')"     # 3. 指标 / keep_threshold
NN_RELAUNCH=1 NN_SMOKE=1 poetry run python train.py 2>&1 \
  bash scripts/smoke-check.sh                              # 4. §5（profile 分轨）
# 5. 单槽训末默认自动 finalize_round，须存在主汇总：
test -f _runs/round_decision.json && head -n 3 _runs/round_decision.json

# 阶段 4-A（立项收尾必做）
bash scripts/verify-migration-complete.sh
python3 scripts/info_perm_gate.py .    # 信息权限：README INFO_PERM 块 ↔ contract/runtime.py 一致（三问已落表）
```

**进入常规迭代的判据：** verify 0 + 上述 smoke 全过；之后**不再设** `NN_RELAUNCH`，再跑一次训练时 G-契约 不警告。

### 入口 A（迁移）完成清单

与 CHECKLIST **§0** 一致：先阶段 0–3，再 **§0-A verify** + **§0-B §5 smoke**。

```bash
cd <目标项目>
# 阶段 0 — 官方对照（exit 0 方可进入 HARD-GATE）
bash <template_root>/scripts/migration-compare.sh \
  --template-root <template_root> --project-root .

# 阶段 2–3 — 按 F1-contract 改码 + CHECKLIST §2–§4 后：
# 阶段 4-A
bash scripts/verify-migration-complete.sh   # 必须 exit 0
python3 scripts/info_perm_gate.py .         # 信息权限块 ↔ 合同一致（三问已落表）

# 阶段 4-B
NN_RELAUNCH=1 NN_SMOKE=1 poetry run python train.py 2>&1 \
  bash scripts/smoke-check.sh

rm -rf __backup_migration__ 2>/dev/null || true
```

**进入常规迭代的判据：** verify 0 + smoke 过；`unset NN_RELAUNCH` 再跑训练时 G-契约 不警告。

**Preflight 守门（每次 train 自动，与迁移检查同源）：**

| ID | 行为 | 迁移阶段 |
|----|------|----------|
| G-封装 | `train.py` 不得 `from workspace.<子模块> import` | 失败 |
| G-评估 | `contract.test` 须自主实现，禁止 `test→ws.evaluate`；`train.py` 须显式 `contract.test(` | 失败 |
| G-契约布局 | `check_contract_layout`：四文件 + 门面 import | 失败 |
| G-台账 | `_runs/results.tsv` 表头须与 `contract._default_tsv_columns()` 一致 | 警告 |
| G-契约 | `contract/` 相对 HEAD~1 有改动 | 警告（`NN_RELAUNCH=1` 跳过） |
| G-信息权限 | `INFO_PERM` 登记合法 + 静态扫描（只评资产读者 / 交卷缝 / 训练 batch 键）；无 env 旁路 | 失败 |
| G-范式 | `nn-config.yaml` 的 `profile` vs 实际方法集 | 警告 |
| G-布局 | 根目录非白名单 `.py` | 警告 |

旋钮：`NN_PREFLIGHT`、`NN_GUARD_*`、`NN_ROOT_PY_ALLOWLIST` — 见 `PROTOCOL.md` §2.3。

---

## 阶段 0 — 官方分析 CLI（禁止手写对照循环）

```bash
bash <template_root>/scripts/migration-compare.sh \
  --template-root <template_root> \
  --project-root <project_root>

# 机器可读摘要（stderr）
bash <template_root>/scripts/migration-compare.sh \
  --template-root <template_root> --project-root <project_root> --json
```

`compare_side` 返回 **list[MethodComparison]**，禁止 `.items()`。逻辑实现见 `migration-compare.py`。

---

## 答案清单协议（--answers）

> **第 4 种触发方式**：同一份问卷、同一题序、同一套记录与签字，只是「有合法答案的题不弹卡片」。md/txt 只当草稿，Agent 填成 YAML 后再走本协议。

### 文件与校验

- 机器只认 YAML：`version: 1` + `answers:`（键 = 人话键 / slug / 别名，见题库 `docs/init/init-question-registry.yaml`；`python3 scripts/init_answers.py template --workflow build|migrate` 出示例）。
- **开工前**先 `python3 scripts/init_answers.py classify --answers <文件>`：`answers` 原样校验；`draft`（md/txt/作文）→ Agent 填表到 `<target>/.auto-nn/init-answers.converted.yaml`，原文另存 `init-answers.input.*`。拿不准的题加 `guessed: true`（校验后 `skip_ui=false`，仍现场问）。对人出示覆盖表（写清 / 我猜的 / 没提 / 和源不一致）。
- **校验**：`python3 scripts/init_answers.py validate --answers <清单> --workflow <wf> --repo-root <target> --write-resolved` → `<target>/.auto-nn/init-answers.resolved.json`。**rc 1（有错误）→ 整份清单不生效，先把错误人话贴给用户**；rc 0 可有警告。
- v1 允许跳卡的题只有 **8 道**：I1 / I2 / I3 / G1 / G2 / O1 / O2 / O4；其余题即使清单写了也**照问**（值作参考）。`guessed: true` 的题即使在这 8 道里也不跳卡。
- **`confirm_only: true`**：对齐理解 + 该入口全部计步题都有合法答案 **且无 guessed** → 点选全跳，只出 F1 签字。缺题则整份不生效。含 guessed → 猜的题仍问。F1 仍不可代签。迁入源对齐差异并入签字表。答卷由项目自备，不进模板包。

### 每步怎么走

| 情形 | Agent 动作 |
|------|------------|
| 该题在 `resolved` 且 `skip_ui=true` | **不弹卡片**；直接按 `lock` 记 `append-init-qa-log`（`--user` 用 `user_text`，以「（来自清单）」开头），一句人话告知用户「第 N 步 · 主题：按你清单填 X」，进入下一题 |
| 该题在 `resolved` 但 `confirm_required=true`（迁入源对齐题 I1/I2） | 必出卡片「清单说 X，源项目是 Y」→ 用户确认后记录（`--user` 仍标「（来自清单，已确认）」） |
| 该题 `guessed=true` | 必出卡片（可提示「笔记里像是 X」）；不得静默跳问 |
| 该题不在 `resolved`（未填 / 参考项 / 有错误） | 照常一问一答 |
| 清单有错误（rc 1） | 全部照常一问一答；不得「部分生效」 |

- **题序不变**：清单不改变 27/24 步顺序，也不合并题；依赖题（如 I1 依赖 D2）仍等前题确认后才套用。
- **进度抬头照发**：`第 N / 共 M`；跳卡的题也占一步。

### F1、记录与导出

- `init-qa-log.md` 条目数与非清单路线一致（build 25 / migrate 28 / update 15）；来源只体现在 `--user` 文字。
- F1-contract 汇总表每行末注 **来源：清单 / 现场 / 草稿猜测**；签字**永远现场**（F1 不可由清单代签）。
- **close + 写 migration-summary 之后必跑**：`python3 scripts/init_answers.py export --repo-root <target>` → `.auto-nn/init-answers.yaml`（以 qa-log 每题最大 rev 为准）。下次 `--answers` 用这份，不用草稿、不用口径汇总 md。
- 阶段 2 首步：`python3 scripts/init_info_perm.py write --repo-root . --from-resolved .auto-nn/init-answers.resolved.json`（清单含 I 题时）。

### 与 `--fast` 叠用

清单命中的题 in-tmux Claude 不再推断、直接取清单值；其余题照旧看项目答。产物与协议层不变量不变；fast 结束同样 export。

### 禁止

- 不得把 md/txt 直接当 YAML 校验并声称生效（须 classify → 填表 → validate）。
- 不得用清单跳过 P0 / D1 / D2 / E3 / E4 / E9 / O3 / F1 等 v1 未登记的题（无 `confirm_only` 时）。
- 不得因清单省略 `append-init-qa-log`、省略 F1 汇总、或把清单当 `migration-summary.md`。
- 不得把猜测标成写清、不得替用户用模板默认补题：清单没写的题一律现场问；清单写错的题一律先报错再问。
- 运行时（train / auto-run / doctor）不读题库、不读清单、不读 `init-answers.resolved.json`、不读导出的 `init-answers.yaml`。

---

## --fast 路线（in-tmux Claude 看项目答 27 步，**主推自动化路线**）

### 触发原则

- ✅ 父 Agent / 编排器默认（sandbox-debug L1 / sandbox-loop 元循环 init / 回归测试）
- ✅ 用户明示（"用 fast" / "看项目答" / "全自动 init"）
- ❌ 真人日常 init（**默认走 picker**）

### 完整 schema 见

- 模板仓 SKILL.md §「fast 路线」章节
- 设计 spec：`sandbox-auto-nn/design/2026-07-10-auto-nn-init-fast-design.md`

### 协议层产物（与 picker 路径**完全一致**）

| 文件 | 路径 | 来源 |
|------|------|------|
| `init-qa-log.md` | `<target>/.auto-nn/` | init-header + 26/29 条 + F1-contract + close |
| `migration-summary.md` | `<target>/.auto-nn/` | F1 汇总表（agent 推断的 lock 值） |
| `abcde-manual.md` | `<target>/references/manual/` | O3 阶段 init_o3_abcde.py 自动生成（framework 元信息 name/mutability 见头注释） |
| `contract/ workspace/ train.py` | `<target>/` | **agent 真懂项目写的**（不是通用答案） |

### 协议层不变量

fast 路线**不破**协议层：

- ✅ `init-qa-log.md` 必含 init-header + build:25 / migrate:28 / update:15 条 entries + F1-contract + close（PR2.5；2026-09 含 I1–I3）
- ✅ `MIN_ENTRIES_BY_WORKFLOW={build:25, migrate:28, update:15}` 由 `validate()` 强制（不够数则警告，PR2.5）
- ✅ 写入主体必为 in-tmux Claude CLI（调 `scripts/append-init-qa-log.py`，cwd 在副本）
- ✅ `append-init-qa-log.py` 只验产物（init-header / 条目数 / F1-contract 标题 / close 时间戳），**不验证触发方式**

### 入口 A/B slug 白名单（与「编号速查」一致）

入口 B = 26 个 slug（含 F1-contract）：P0 + D1-D2 + I1-I3 + D3-D4 + T1-T2 + E1 + G1-G2 + E2-E9 + O1-O4 + F1
入口 A 在此基础上加 3 个 H slug = 29 个。

`--fast` 可与 `--answers` 叠用：清单命中的题 in-tmux Claude 不再推断、直接取清单值（仍逐条 append，`--user` 带「（来自清单）」）；其余题照旧看项目答。

### in-tmux Claude "看项目" 协议（核心实现细节）

```bash
# 扫描项目（3-5 秒）
ls -la <target_root>/
cat <target_root>/README.md | head -50
cat <target_root>/pyproject.toml
ls <target_root>/backbone/ 2>/dev/null | head -10
ls <target_root>/datasets/ 2>/dev/null | head -10
cat <target_root>/main.py 2>/dev/null | head -50
```

**in-tmux Claude 自己推断**：
- entry (A/B) — 看 main.py 有无迁移逻辑
- workflow（build|migrate|update）— `init_workflow.classify` / `--force-workflow`；路径：无 source→build，有外部 source→migrate，同仓二次→update（`# greenfield` 仅为入口 B 落盘标记，非 scenario）
- object_type（code|framework|data）— `detect()` / `--force-object-type`
- backbone / dataset — ls 出来
- loss / metric — 看 pyproject.toml + 训练脚本
- time_budget — 看 README 历史 R 轮 + R 耗时
- goal — 看历史 R 轮 primary metric + 峰值

**不**写死答案，**不**脚本化推断——in-tmux Claude 自己看自己答。

### P0 触发原则（必须用户/编排器明示）

- ✅ 父 Agent / 编排器默认（sandbox-debug L1 / sandbox-loop / 回归测试）
- ✅ 用户明示
- ❌ 真人日常 init（**默认走 picker**）

### 不在本节范围

- ❌ 不替代 picker 主路径（日常 init 仍推荐 picker）
- ❌ 不加新 slash 技能（仍是 `/auto-nn-init`，只是多 1 个 flag）
- ❌ 不默认被编排器自动调用（必须用户/编排器明示）
- ❌ 不改 `append-init-qa-log.py` / `init_qa_log.py` 代码层
