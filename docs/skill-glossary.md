# auto-nn skill glossary

> **单一真源**：迁后日常技能 + `/auto-nn-init` 初始化。各技能保留就地的「高频代号」小表，完整对照以本表为准。
> 规则：迁后技能见 [`.cursor/rules/skills-plain-language.mdc`](../.cursor/rules/skills-plain-language.mdc)；init 见 [`skills/maintainer/auto-nn-init/SKILL.md`](../skills/maintainer/auto-nn-init/SKILL.md) §一轮一问 / 4 问自检。
> 原则：对用户先说人话，代号只在括号里补充，禁止裸抛。用户用英文时用下表 **In English** 列。

---

## 迁后日常

| 内部码 | 对用户怎么说 | In English |
|--------|--------------|------------|
| `MA-1` | 最新一轮 vs 历史最好的对比 | latest round vs the historical best |
| `MA-3` | 相比上次分析的新增量 | what is new since the last analysis |
| `MA-6` | 上次给的建议这轮是否兑现 | whether last round's advice was followed |
| `MA-R` | 上次反思建议这轮是否兑现 | whether last reflection's advice was followed |
| `MA-7` | 撞墙 / 高噪声提醒 | stuck / high-noise warning |
| `Tier A–E` | 实验成熟度档位（从能跑通到逼近上限；现为二维：字母档 × routine/derived/different；novel 仅盖章） | maturity band A–E (runnable → near ceiling; letter × routine/derived/different; novel is a stamp only) |
| `innovation_depth` / `routine` / `derived` / `different` / `novel` | 探索深度：routine（经典现成）、derived（论文/成熟组合；**旧称 extend，已迁 derived**）、different（自研结构层）、novel（different ⊕ 文献背书，仅 reflect 盖章） | depth: routine (off-the-shelf), derived (published/mature combo), different (own structure), novel (different + literature stamp) |
| `innovation_rationale` | 为何把本轮归为 routine/derived/different 的一句说明（用于审计与归因） | one-line why this round is routine/derived/different |
| `exploration_space` | 本轮探索格子（学习率/模型/目标/数据 × 深度；成绩表只记 A–D，不写 E-） | this round's exploration cell (training/model/objective/data × depth; ledger records A–D only) |
| `e_feedback` / 改题待办 | 改题主张另记于 `_runs/analysis/e_feedback.jsonl`；对人说「改题待办」 | a proposal to change the task itself (“task-change ticket”) |
| `pending` / `adopted` / `rejected` / `deferred` | 改题决议四态：待审 / 留下（只记建议、不改题） / 驳回（类似主张不再提） / 搁置（当没发生、下次可再提） | ticket states: pending / keep as advice / reject / defer |
| `plateau` / `plateau_streak` | 连续多轮没提升（撞墙） | no improvement for several rounds (stuck) |
| `beat_best` | 是否刷新了历史最好 | whether this beat the historical best |
| `keeper` / `KEEP` | 当前最好的那个结果 / 把它存为标杆 | the current best / keep it as the benchmark |
| `discard` | 这轮不如最好，丢弃不留 | worse than the best; do not keep |
| `leader` / `metric_leader` | 当前领跑的那次实验 | the leading run |
| `baseline_tag` | config/台账字段：本轮基线角色（plain 自跑下界 / reference 外部上界 / none 普通轮）。**给人看的表**里 none 显示为 `-` | role of this round: plain lower bound / public reference / ordinary (`-`) |
| `plain` | 自跑朴素基线，**下界锚**（须略胜随机、几分钟跑完） | naive lower-bound anchor (must beat random, minutes not hours) |
| `reference` | 外部已发表的公开最优或本仓对照轮，**上界/对照尺**（novel 任务常无；代码 `reference_anchor`，**不**叫 SOTA；测条件须对齐） | public or in-repo reference ruler (not called SOTA; protocol must match) |
| `none` | 默认普通轮（既不是 plain 也不是 reference） | ordinary round (neither plain nor reference) |
| 基线尺子体检 | analyse/check：有没有 plain / reference；缺 plain 可建议补一轮；缺 reference → 手跑按用户要求，不催 auto | check whether plain/reference rulers exist; suggest a plain round if missing; do not nag for reference |
| E5 系统列 | init 成绩表确认：`baseline_tag` 必写入（选 B 也不删列）；与 O3「跑不跑尺子」分工 | the ledger always has a baseline-role column; whether to *run* a ruler round is a separate question |
| `inspect`/`junk`/`runs`/`runs+journal`/`experience`/`reflect`/`factory` | 清理档位（只看 → 删脏数据 → 清空实验 → 重置日记 → 归档旧叙事 → 清反思 → 完全绿场重来） | cleanup tiers: inspect → junk → wipe runs → reset journal → archive narrative → clear reflection → factory reset |
| `junk` | 脏数据（preflight / smoke 等试跑残留） | leftover smoke/preflight junk |
| `factory` | 完全绿场，像从没跑过实验 | factory reset, as if never trained |
| `Modify-L` | 改记录表的列 / 参数 / 打分口径 | change ledger columns / scoring rule |
| `Modify-T` | 改训练本身（模型 / 目标 / 数据） | change training itself (model / loss / data) |
| `Modify-Scenario-complete` | 把场景信息补全 | fill in missing scenario fields |
| `Modify-Scenario-expand` | 新增一个实验场景 | add a new experiment scenario |
| `NN_RELAUNCH` | 改了口径，需要重启批次重新生效 | restart the batch so the new contract takes effect |
| `G-HUMAN` / `baseline` / `drift` | 路线图保护：防止跑着跑着路线图被偷改 | roadmap guard: the human roadmap must not drift mid-batch |
| `batch` | 多轮自动跑（一批实验） | a multi-round auto batch |
| `scenario_id` | 实验场景（不同场景成绩不能混着比） | experiment scenario (do not mix scores across scenarios) |
| `scenario_bindings` / `manifest` | 场景到参数的映射规则 | how scenario ids map to parameters |
| `R1–R6` | 触发反思的几种条件 | conditions that trigger a reflection round |
| `criteria_met` | 当前阶段的完成条件是否达成 | whether this phase's done-criteria are met |
| `governance_rev` | 体检项：模板版本是否对齐 | health check: template revision aligned |
| `.auto-nn/version` | 当前模板戳（升版会改） | current template stamp (changes on upgrade) |
| `.auto-nn/init-template-version` | 立项时的原始模板戳（只写一次，升版不改） | template stamp at onboarding (write-once) |
| `layout` | 体检项：目录结构是否规范 | health check: directory layout |
| `tsv_header` | 体检项：记录表表头是否正确 | health check: ledger header |
| `G-封装` / `G-评估` | 体检项：训练封装 / 评估口径是否合规 | health check: training encapsulation / eval authority |
| `PASS / WARN / FAIL` | 体检：通过 / 提醒 / 不通过 | pass / warning / fail |
| `[反思]` | 写进经验文档的一段反思 | a reflection block in the experience log |
| `REFLECT_INDEX pending` | 待消费的反思建议 | unused reflection advice |
| `精华摘要` | 经验文档置顶的滚动摘要 | rolling summary at the top of the experience log |
| `finalize` | 收尾结算这轮成绩 | close the books on this round |
| `Run Context` | 每轮喂给 Agent 的现状简报 | the per-round status brief for the agent |
| `finalize_round` | 单轮训练收尾（写成绩表、判更好、记日记） | finish one training slot (ledger, keep/discard, journal) |
| `ledger` / `results.tsv` | 成绩记录表（TSV） | the score ledger (TSV) |
| `/auto-nn-audit` / 审查 | 对当前最好（或指定对象）做复现、多种子、新不新判定、归因消融；**不进成绩表**；结论写卡片 | audit the current best (reproduce, multi-seed, novelty, ablation); not a search round |
| `saved/audit/` / 审查卡片 | 审查结论目录（人话 `card.md` + 机器 `card.json`）；活指针在 `saved/audit/index.json` | audit cards (human `card.md` + machine `card.json`) |
| `audit-card` | 盘面/反思里注入的「这套已审查」摘要（当前最好换了则降为上一套） | “this setup was audited” stub injected into later briefs |
| `journal` | 实验日记（结构化事件流） | experiment journal |
| `improve_mode` / `primary_delta` | 怎么判「更好」/ 主指标差多少算改善 | how “better” is decided / how much the primary metric must move |

### 迁后违规自检（agent-only）

发出迁后技能任一条**用户可见**消息前，对照上表「对用户怎么说」列；**禁止裸抛**（须翻译或括号补充一次）：

`MA-1` / `MA-3` / `MA-6` / `MA-7` / `MA-R` / `KEEP` / `discard` / `keeper` / `plateau` / `Tier A`–`Tier E` / `scenario_id` / `Run Context` / `REFLECT_INDEX` / `finalize_round` / `ledger` / `journal` / `improve_mode` / `G-HUMAN` / `NN_RELAUNCH` / **`人生目标`** / **`人生模式`**

| token 类型 | 替换动作 |
|------------|----------|
| 分析块码（`MA-*`） | 贴 MA  stderr 前一句人话结论；chat 里用「数值/新增/撞墙/建议兑现」 |
| 成绩语义（`KEEP`/`keeper`/`plateau`） | 「保留/当前最好/连续 N 轮没提升」 |
| 场景（`scenario_id`） | 「场景」或具体场景名 |
| Modify 代号 | **须**「人话全称（Modify-L2）」；禁止裸 `L2`/`S-complete`。~~Modify-L1~~ 已退役（加参数列 = watchlist + regen） |
| 误称 | **实验目标** / **实验模式**（非「人生」） |

**单一真源**：各技能 `## 对用户怎么说（人话）` + [`.cursor/rules/skills-plain-language.mdc`](../.cursor/rules/skills-plain-language.mdc)。机器校验：`scripts/template_tests/test_post_migration_skills_plain_language.py`（须有对用户节 + 禁「人生模式」泄漏）。

---

## 项目初始化（`/auto-nn-init`）

### 宏观：阶段、签字与盘点

| 内部码 | 对用户怎么说 |
|--------|--------------|
| `F1-contract` / `F1` | **口径汇总，请最终确认**（签字表；锁定口径，**不等于**迁完） |
| `P0-project-brief` / `P0` | **对齐理解**（准备步，不计入 27/24 步） |
| `migration-compare` | 只读对比：旧项目与模板差在哪 |
| `init-qa-log` / `.auto-nn/init-qa-log.md` | **init 问答逐步记录**（每步确认后 append；F1 签字后 close；迁后只读审计） |
| `skill_activity_log` / `skill-activity.jsonl` | **全技能活动流**（`.auto-nn/`；`agent.skill_activity_log` 默认 true） |
| `迁移完成` | `verify` + `smoke` 都通过（**不等于**签字） |
| `HARD-GATE` | 逐项确认口径（阶段 1；一次只问一件事） |
| `verify-migration-complete` | 迁完验收脚本 |
| `smoke-check` | 短训试跑验收 |
| `governance-sync` | 把模板治理文件同步进新项目 |
| `块 A` | 盘点：历史与文档（→ 旧资产清理） |
| `块 B` | 盘点：数据与可比子世界（→ 数据划分） |
| `块 C` | 盘点：训练控制流（→ 训练方式） |
| `块 D` | 盘点：指标与台账（→ 评估与台账） |
| `块 E` | 盘点：场景与运行档（→ 场景清单草稿） |
| `块 F` | 盘点：运行环境（→ 运行设置） |
| `块 G` | 盘点：实验目标（→ 实验模式 + 主指标目标值） |
| `S_data` | （内部）**数据与指标** — 官方终评有几种数据/协议 |
| `S_run` | （内部）**默认配置（起跑线）** — 键=典型值 |
| `A_explore` / `S_method` | （内部）**后面允许试什么** — 探索轴/可调项 |
| `选后锁定` / `F1 会写什么` | （内部）用户选项锁定后写入签字表哪一行 — **不对用户展示** |

### 人话主题 ↔ 内部码（阶段 1 抬头用）

| 人话主题（对用户说） | 内部编码 |
|----------------------|----------|
| 对齐理解 | `P0-project-brief` |
| 场景与数据 | `D1` → `D2` →（信息权限）→ `D3` → `D4` |
| **信息权限** | `I1` → `I2` → `I3`（**D2 之后、D3 之前**；步 #3–#5） |
| 旧资产清理 | `H1` → `H2` → `H3`（仅入口 A 迁入） |
| 训练方式 | `T1` → `T2` |
| 评估与台账 | `E1` → **`G1` → `G2`** → `E2` … `E9`（**实验目标须在场景探索方案 E6 之前**） |
| 运行设置 | `O1` → … → `O4` |
| 汇总确认（签字） | `F1-contract` |

入口 A 共 **27** 步 + 准备步 + 单独签字轮；入口 B 共 **24** 步（无「旧资产清理」段）。机器可读题库：`template/package/docs/init/init-question-registry.yaml`（`python3 scripts/init_answers.py steps --workflow …`）。

### HARD-GATE 逐项（slug → 人话）

| 内部码 | 对用户怎么说 | 程序员一步白（四段式第 0 段） |
|--------|--------------|------------------------------|
| `D1-scenario-inventory` | **场景清单**（有几个官方世界、各测什么、起跑线配置） | 几种官方实验设定 + 各自起跑配置 |
| `D2-data-split` | **数据划分**（训练/验证/测试怎么分；每场景官方终评集） | train/val/test 怎么分；终评用哪套数据 |
| `I1-train-consumes` | **训练许用材料**（全部能训 / 只训练份并列出只评资产 / 训练不读任何数据文件；落 `INFO_PERM.eval_only_assets` / `strict_no_train_files`） | 训练能碰哪些数据、哪些只在打分时打开 |
| `I2-official-path` | **官方打分通道**（整网前向 / 受限路径 + 手续函数 / 固定评测态；落 `INFO_PERM.official_path[_impl]`） | 官方分只能走哪条路算 |
| `I3-other-info-rules` | **其他信息规矩**（均无 / 逐条；机器只管训练 batch 键白名单 `INFO_PERM.train_batch_keys`，其余标「机器不管」） | 还有没有别的信息不许乱流 |
| `D3-workspace-data` | **训内数据处理**落在哪里（workspace 哪一层） | 数据加载/增强写在代码哪一层 |
| `D4-repro-data` | **复现数据**（数据根版本、复现环境要锁哪些键） | 复现时要锁哪套数据路径/版本 |
| `H1-legacy-artifacts` | **旧台账与实验产物**（旧记录表/exp/命名要不要留） | 旧成绩表和实验目录留不留 |
| `H2-experience` | **旧经验文档**（EXPERIENCE 取舍） | 旧踩坑笔记要不要写进新项目 |
| `H3-agent-boundary` | **旧文档硬约束**（旧 README 里有没有必须保留的规则） | 旧 README 硬规则要不要保留 |
| `T1-loss-layers` | **训练里什么能动**（**不是**问现在用哪个 loss；**是**定自动改实验时的底线与松紧。对用户用：必须留着/可以换/可以加/只能拧/可选技巧；**禁**「五档/五层」） | 自动改实验时训练目标能动到哪 |
| `T2-callchain` | **调用链**（外层循环、train→eval 怎么走，≤6 行） | 训练循环怎么转、何时打分 |
| `E1-metrics` | **主/辅指标**（记什么分、哪列是 KEEP 键） | 主分 + 辅分（KPI + 辅助 metric） |
| `E2-metric-tier` | **指标列分级**（哪些进台账、哪些仅辅助） | 哪些分写主列、哪些只备注 |
| `E3-official-test` | **官方终评**（训末 `contract.test` 怎么跑） | 训**结束后**正式打分怎么跑 |
| `E4-train-eval` | **训内评估**（训练过程中要不要评、怎么评） | 训**过程中**要不要打分、多久一次 |
| `E5-tsv-columns` | **记录表列**（台账四区与列名） | 成绩表有哪些列（像 DB schema） |
| `E6-scenario` | **场景探索方案**（每轮改什么、场景排期、KEEP 分池；**须在 G1/G2 之后**；清单已在 D1） | 每轮改什么、多场景怎么轮换比最好 |
| `E7-run-context` | **运行参数进台账**（哪些超参写入记录表） | 哪些超参记进成绩表（experiment metadata） |
| `E8-checkpoint` | **checkpoint 策略**（存不存、存哪、何时加载） | 要不要存权重、存 best 还是 last |
| `E9-keep` | **KEEP 策略**（怎么判最好、历史池范围） | 什么算「这次更好、要留下来」 |
| `O1-time-budget` | **训练墙钟**（单轮最长训多久） | 单次训练最长跑多久 |
| `O2-gpus-parallel` | **GPU 与并行**（用哪些卡、最多几路并行） | 用哪些 GPU、最多几路并行 |
| `O3-baseline-anchors` | **起步尺子意图**（init 问 plain/reference 与测条件；运行时 auto 检索/补 plain；公开对照满 10 轮仍无则催 `/auto-nn-reference`） | 开跑前怎么立对照尺 |
| `O4-repro-determinism` | **复现随机性**（种子、cuDNN、快照约定） | 随机种子与确定性 |
| `G1-experiment-mode` | **实验模式**（追指标 / 新方法+指标 / 纯探索摸底；**E1 后、E6 前**，步 #14/#11） | 主攻做分还是也要试新方法 |
| `G2-goal-value` | **主指标目标值**（全局默认；多场景可 `scenario_goals` 覆盖；`goal_stop_mode` 定停批范围）；explore 可选 **指标底线护栏** | 主分要到多少算达标（SLO） |
| `scenario_goals` | 按场景覆盖目标；未写则继承 `goal_value`；`null` = 该场景不参与 goal | 某档单独的目标线 |
| `goal_stop_mode` | `focus_only` = 只盯主场景停 batch；`all_in_scope` = 有 goal 的全达标才停 | 停批看一条线还是多条线 |

### E4 子字段（在「训内评估」一轮内）

| 内部码 | 对用户怎么说 |
|--------|--------------|
| `E4_PATH` | 训内打分走哪条路：① 整包官方测试；② 同指标、不同数据加载器（监督学习默认） |
| `E4_训内节奏` / `CADENCE` | 训中多久评一次：**A** 每圈都评；**B** 训中不评；**C** 稀疏评 |
| `E4-keys` | 训内 `evaluate` 须覆盖哪些指标键 |
| `E4_EVAL_FOR_KEEP` | KEEP 判定只看官方终评（不对用户裸抛代号） |

### 场景清单表头（对用户只用左列）

| 内部码 | 对用户表头 |
|--------|------------|
| `S_data` | **数据与指标** |
| `S_run` | **默认配置（起跑线）** |
| `A_explore` | **后面允许试什么** |
| （KEEP 列） | **成绩和谁比** |

### 违规自检（agent-only）

发出 init 对话任一条用户可见消息前，grep 本节 token 列表：

`D1-` / `D2-` / `I1-` / `I2-` / `I3-` / `H1-` / `H2-` / `H3-` / `T1-` / `T2-` / `E1-` … `E9-` / `O1-` … `O4-` / `P0-` / `F1-contract` / `F1=` / `选后锁定` / `F1 会写什么` / `①` / `②` / `③` / `E4_PATH` / `E4_训内节奏` / `E4-keys` / `CADENCE` / `E4_EVAL_FOR_KEEP` / `块 A` … `块 F` / `S_data` / `S_run` / `S_method` / `A_explore` / `SCENARIO_AXIS` / `SCENARIO_POLICY` / `SCENARIO_CANDIDATES` / `scenario_bindings` / `AGENT_BOUNDARY` / `D2_DATA_SPLIT` / `METRICS_SNAPSHOT` / `INFO_PERM` / `eval_only_assets` / `official_path` / `strict_no_train_files` / `train_batch_keys` / `skip_ui` / `confirm_required` / `EXPERIENCE` / `KEEP` / `台账` / `checkpoint` / `ckpt.pth` / `results.tsv` / `exp_*` / `migration-compare` / `governance-sync` / `verify-migration-complete` / **`人生目标`** / **`人生模式`** / **`finalize_round`** / **`Run Context`** / **`contract.test`** / **`ws.evaluate`** / **`improve_mode`** / **`primary_delta`** / **`ledger`** / **`journal`** / **`keeper`** / **`HARD-GATE`**

出现 → 改人话或拆下一轮。**自身在描述"禁词"时引用除外**（即本节、SKILL.md §禁词表、指南 §9.1 内的 token 出现不算违规）。机器校验脚本：`scripts/template_tests/test_init_user_facing_no_internal_codes.py`。

### 替换动作（给 agent）

| token 类型 | 替换动作 |
|------------|---------|
| 阶段 slug（`D1-…` / `E4-…` 等） | 改人话主题 + 进度抬头；内部按 slug append `init-qa-log`，F1 汇总写 `.auto-nn/migration-summary.md` |
| 合同 / 签字（`F1-contract` / `选后锁定` / `F1 会写什么`） | 改"口径备忘" / "口径汇总"；落盘格式 agent 内部维护，不展示 |
| 选项号（`①` / `②` / `③`） | 改 A / B / C；内部按 reference §确认选项可辨规范 6 段推进 |
| 等式速记（`H1=舍弃` / `E4_PATH=①`） | 改短句（"此步记…" / "训内打 X 节奏"） |
| 块标（`块 A` … `块 F`） | 落 `.auto-nn/migration-summary.md` 不展示；阶段 0 对用户只讲 3~5 条人话理解 |
| 子字段代号（`E4_PATH` / `E4_训内节奏`） | 改描述（"训内打哪条路" / "训内评节奏"），不用代号 |
| README 块名（`AGENT_BOUNDARY` / `INFO_PERM` 等） | 改"硬约束段" / "数据划分段" / "信息权限段"；实施时再引用块名 |
| 信息权限内部键（`eval_only_assets` / `official_path` / `train_batch_keys` …） | 改「只评资产 / 官方打分通道 / 训练 batch 键白名单」；答案清单内部件（`skip_ui` / `confirm_required` / `guessed`）改「按你清单填 / 清单与源项目不一致需确认 / 我猜的」 |
| 文件 / 概念（`EXPERIENCE` / `KEEP` / `台账`） | 改"经验记录" / "历史最好成绩" / "成绩记录表" |
| 系统 action（`migration-compare` / `governance-sync` / `verify-migration-complete`） | 阶段 0/3/4 系统消息可保留；提问中改人话（"跑对照分析" / "同步治理" / "跑验收"） |
| 迁后/实现术语（`finalize_round` / `Run Context` / `contract.test` / `ws.evaluate` / `improve_mode` / `ledger` / `journal` / `keeper` / `HARD-GATE`） | 改「每轮收尾 / 运行参数进表 / 训末官方测试 / 训内打分 / 怎么判更好 / 成绩记录 / 实验日记 / 历史最好 / 逐项确认」；init 阶段 1 **不问**迁后 auto-run 细节 |
| init 误称（`人生目标` / `人生模式`） | 改 **实验目标** / **实验模式**（内部 `experiment_mode` 只在括号补充） |

**单一真源**：[`skills/maintainer/auto-nn-init/SKILL.md` §禁词表（单一真源）](../skills/maintainer/auto-nn-init/SKILL.md)；本节为机器可读副本。
