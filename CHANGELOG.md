# Changelog

All notable changes to the auto-nn template repository will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- docs: README 顶栏补上 STEER 全称（Steerable and Traceable autonomous Experimentation for Evidence-governed AI Research）
- docs: 新增知乎推广短文底稿（含图床封面与配图说明）

### Fixed

- ci: GitHub Actions pytest 补上 numpy / torchvision，并分开跑根目录 `tests/` 与 `template/package/scripts/tests/`（两边有同名测试文件，一次 collect 会互相踩）；包内测试补 `conftest` 让 `lib.*` 可导入
- test: 删掉根目录里已退役的旧 preset / 旧 5×3 表头 / 与包内重复的测试副本；`manage_goal clear` 与 overlay A–D 对齐现行实现
- ci: 包内测试补 `PYTHONPATH`（`template/package` + `scripts/`），否则 `from lib` / `from contract` 在 CI 里 collect 失败

### Changed

- docs: README 按上手顺序重排；27/24 问对照表改到文末附录并按主题归类（含信息权限三问）；clone 目录改为 `steer`
- 开训按家目录 `~/.gpus` 收紧占用：有文件才限制能用的卡，没建该文件仍用本机全部卡；空文件或与本机对不上仍拒绝
- repo: Gitee 仓库从 `auto-nn` 改名为 [`steer`](https://gitee.com/xieyulai/steer)
- docs: README 17 技能按立项 / 立尺 / 搜索 / 审查 / 改能力 / 维护分组
- docs: README 嵌入 [steer-cifar](https://github.com/xieyulai/steer-cifar) 约 20 轮成绩轨迹图（`.github/assets/steer-cifar-traj.png`）
- docs: 剩余中文文件名改为英文：`AUTO-NN-package-docs-checklist.md`、`init-conversation-guide.md`、`nn-literature/atomic-tools.md`，引用一并更新
- docs: README 加上探索空间图（`.github/assets/space-grid.png`）及横轴/纵轴/文献虚线/E 题面/风格条说明
- docs: CIFAR 原始训练仓仍是 [kuangliu/pytorch-cifar](https://github.com/kuangliu/pytorch-cifar)；接好之后的示例仓才是 [xieyulai/steer-cifar](https://github.com/xieyulai/steer-cifar)
- docs: README 五步流程图改为仓内 `.github/assets/flow-skills.png`，不再走图床
- docs: README 给外人看：前置与 CIFAR 接入流程写细；去掉「说人话」等内部用语；完整跑例另开独立仓
- docs: README 全程技能驱动：`/auto-nn-init <你的仓库路径>` 用占位符；更新只写 `/auto-nn-update`，不再让用户 export 路径或跑 new-project.sh
- docs: `AUTO-NN-白皮书.md` / `技能术语表.md` 改名为 `AUTO-NN-whitepaper.md` / `skill-glossary.md`，引用一并更新
- 对人输出跟用户语言走：术语表加 In English 列；立项四段式/进度抬头有英文外壳；说人话规则与路由澄清双语。不翻译 PROTOCOL / 技能内部正文 / 脚本表头。
- docs: 去掉 `nn-doctor/g-human.md`、`nn-modify/doctor-routing.md`（内容已在 fail-routing / 技能里）；mammoth 样例只留 `workspace/__init__.py` 与 `framework_binding.yaml`（其余 contract 演示 py 无测试/脚本读取）
- docs: 去掉 `nn-literature/README.md`（纯索引）、`examples/adapter-mammoth/README.md`（过期占位业务 README）、`nn-modify/explore-handoff.md`（边界已收进 modify 技能）
- README: 默认英文首页。中文版从 `README.zh-CN.md` 改名为 `README-zh.md`（Gitee 对 `README.zh-CN.md` 会按界面语言自动切走英文首页）；clone 地址改为本仓 URL；Issues 指向 Gitee
- skills: 业务专属参考 `auto-nn-modify/references/bm-report-reference-model-reproduction.md`（BM-Case1 复现说明）及其在 SKILL / docs 的入口不再随模板发布；init 参考里的旧仓命名举例改为中性名
- repo: 从原维护仓拆分为独立开源仓 **auto-nn**（全新 git 历史，功能与 v3.3.0 模板完全一致；测试集与门禁结果对齐原仓基线）
- docs: 只保留**必要**文档（27 个文件）：白皮书、术语表、init 对话指南、包文档维护检查清单，以及被技能 / 脚本 / 测试点名读取的 `nn-doctor/`、`nn-modify/`、`nn-literature/atomic-tools.md`、`archive/{metric-and-keep-system,readme-sync-after-modify}`、`maintainer/mirror-mechanism`、`examples/adapter-mammoth/`。流程图（含生成脚本）、探索空间、方法论总览、技能维护检查清单、ADR、设计 spec / plan、日期记录、论文与实验材料均不随仓发布；代码 / PROTOCOL / SKILL / 保留文档中约 110 处「设计见 docs/superpowers/specs/…」类引注一并删除（仅注释 / 文案，不动逻辑），并修正 7 处相对路径写错的文内链接
- test: `test_init_answers.py` 的 CSI 完整答卷举例改为包内 fixture（`scripts/tests/fixtures/csi-short-code.answers.yaml`），不再依赖维护仓 `docs/` 之外的文件

### Added
- 开源门面：STEER logo（`.github/assets/logo-{light,dark}.png`，README 按系统明暗自动切换）、`README.md`（English 默认）+ `README-zh.md`（中文；不用 README.zh-CN.md，避免 Gitee 按语言自动切走首页）、`LICENSE`（Apache-2.0）+ `NOTICE`、`CONTRIBUTING.md`、`docs/README.md` 文档地图、GitHub Actions CI（pytest × py3.10/3.12 + 契约 lint + install dry-run）、Issue / PR 模板

## [3.3.0] - 2026-09-07

### Added

- feat(info-perm): 立项常见可试场监督，只评材料改为真用才拦

## [3.2.1] - 2026-09-06

## [3.2.0] - 2026-09-06

### Fixed

- fix(train): 长步训练墙钟在优化更新边界满预算停并入账

## [3.1.0] - 2026-09-05

### Added

- feat(init): 立项支持草稿进、签完导出可复用答卷

## [3.0.0] - 2026-09-05

### Changed

- **BREAKING（立项协议）**：`auto-nn-init` 问答从 20/17 步改为 27/24 步——D2 后新增「信息权限」三问（I1 训练消费 / I2 官方通道 / I3 其他规则），`init-qa-log` 最少条数 22/25 → 25/28；`init-question-registry.yaml` 成为题库唯一真源，新增 `--answers` 答案清单入口。
- **BREAKING（业务仓门禁）**：`contract/runtime.py` 须登记 `INFO_PERM`、README 须有 `<!-- INFO_PERM -->` 块，`verify §6f` / `nn-doctor` / `info_perm_gate.py` 对账不过即 FAIL；`experiment.py` 新增 G-信息权限预检（无 `NN_GUARD_*` env 旁路），首 batch 键超出白名单拒启，finalize 旁路留痕判废。存量仓 `/auto-nn-update` 后用 `scripts/init_info_perm.py write` 补登记。
- **BREAKING（范式）**：`physical` 范式不再把 `prepare_data` 列为工作区方法。

### Added

- feat(init): init_info_perm.py 对存量业务仓（runtime.py 无 INFO_PERM）追加字面量补登记；dry 测试（CSI4 真合同 + 合成 PINN 仓）通过后勾 plan
- feat(init): 三问落表脚本 init_info_perm.py（write/show，写后 info_perm_gate 对账、失败回滚、--from-resolved 接答案清单）
- feat(init): 立项题库与答案清单校验器（init-question-registry.yaml / lib+CLI init_answers.py）
- feat(info-perm): README INFO_PERM 块门禁 info_perm_gate.py + verify §6f + nn-doctor 两项 + governance-sync/manifest 登记
- feat(info-perm): experiment.py 接 G-信息权限（无 env 开关）、首 batch 键校验、finalize 旁路留痕与判废；train.py 传首 batch；glob 支持 **/ 零层与裸文件名
- feat(info-perm): 合同骨架加 INFO_PERM 登记表与交卷缝（_official_path_enabled/_official_forward）；physical 范式不再把 prepare_data 列为工作区方法
- feat(info-perm): 新增信息权限扫描库 scripts/lib/info_perm.py（IP0–IP5、首 batch 键、旁路收集）+ 19 例单测

### Fixed

- fix: 改题建议只记账不停自动跑，处置只更新待办
- fix: 拉模板后自动对齐成绩表表头，布局忽略本地虚拟环境

## [2.13.0] - 2026-08-30

### Added

- feat: 未登记配置键在体检中警告
- feat: 自动多轮轮末提示改题待审
- feat: governance-sync 下发打格与改题待办脚本
- feat: 看台账默认参照增加改题待办条数
- feat: 反思当时写入改题待办；novel 仍只盖章
- feat: 改题待办 jsonl 与决议 CLI
- feat: doctor 检查探索格子必打与禁 E
- feat: 训末入账当场写入探索格子
- feat: 按上一有效轮计算 A–D 探索格子

### Fixed

- fix: 未开训行可扫标记以免误当正式对照
- fix: 课题覆盖台账键时仍写出探索格子列
- fix: 无上一轮题面快照时不记改题落地
- fix: 仅改题快照时探索格子继承上一行
- fix: 探索格子合成拒绝 E 档字母
- fix: 守卫违约日志 except 补 # optional: 标记——v2.11.0 新代码未过自家 G-no-fallback 门（scan_no_fallback 全仓扫描命中吞错 except，单文件模式 rglob 落空属假阴性）

## [2.12.0] - 2026-08-26

### Added

- feat: 文献尺贴签前强制本机原仓校准过线

### Fixed

- fix: 守卫违约日志 except 补 # optional: 标记——v2.11.0 新代码未过自家 G-no-fallback 门（scan_no_fallback 全仓扫描命中吞错 except，单文件模式 rglob 落空属假阴性，原拟 v2.11.1 未推，并入 v2.12.0 Fixed）

## [2.11.0] - 2026-08-26

### Added

- feat: time_budget 取值点守卫——唯一真值 nn-config.yaml（Config-Only），NN_TIME_BUDGET 仅一致性校验、不一致拒启并记 _runs/time_budget_violations.log（experiment.py `_resolve_time_budget` + auto-nn-run.sh launcher 同步拒启）
- feat: smoke 墙钟分离 NN_SMOKE_BUDGET（默认 120s；短训墙钟不再借用 NN_TIME_BUDGET，config.json 审计口径落 yaml 值）
- feat: 收工审计 check_time_budget_audit.py（扫 _runs/exp/*/config.json 对齐 yaml，偏离 exit 1）+ nn-doctor time_budget_violations 检查 + tests/test_time_budget_guard.py（5 用例）
- feat: CSI-3/4 接入正文图3–6出图并写交接说明
- feat: 落地朴素下界与公开对照两个立尺技能
- feat: 审查技能入口、governance-sync 下发，清理反思不删卡片
- feat: 审查卡片注入盘面、反思证据与看台账参照
- feat: 审查编排脚本（不入账训练 + 固定管线 + 写卡片）
- feat: 审查判定（指定两端指纹 + 强制 P3 天花板）
- feat: 审查活指针（按场景 index + 当前/上一套）
- feat: 审查核心纯函数（选对象、种子、消融臂、门槛）
- feat: 创新指纹支持指定基线与候选目录
- feat(layout): 根目录白名单收编 _paper——论文侧数据目录为四主仓既定实践，docs/reproduce 与论文定稿文档按 <repo>/_paper 绝对路径引用；v2.10.0 下发后 verify 布局门禁误报 FAIL
- feat: Enhance Fig 4 TAM visualization and data extraction
- feat: 框架键第二真源——指纹硬判定合并 contract/framework_binding.yaml 注册段
- feat(innovation): 种子目录登记 MAMMOTH_MODEL(B)/BUFFER_SIZE(D) 框架主键
- feat: generate six papers docs code icon variants
- feat(paper): TAM 重算脚本加收集模式，支持各业务仓独立跑后回传聚合
- feat(paper): TAM 全量重算脚本落地（2345 行三通道级联）+ 主张四条制定稿

### Changed

- 拆除 launcher env 时间通道：删 NN_TIME_BUDGET passthrough 盖章分支与 NN_AGENT_TRAIN_TIME_BUDGET_SEC 第三来源（弃用）；PROTOCOL §2.3 改判冻结派生量、CHECKLIST/README 同步；白皮书 §2.1 新增资源边界（四类→五类）
- refactor: Update Fig 4 TAM extraction and visualization
- refactor: Update Fig 4 TAM data extraction and visualization
- refactor: Update Fig 4 TAM data extraction and visualization
- refactor(paper): TAM 重算脚本改两层驱动——单仓模式为默认，聚合模式 --all

### Fixed

- fix: 修补当前最好指针时同步实验目录，审查可读 metrics.sgcs
- fix: 审查缺成绩文件不再当0，后续臂失败写半成品卡
- fix: 失败臂不得误读上一臂分数
- fix: Update JSON handling and encoding in analysis scripts; adjust summary data for accuracy

## [2.10.1] - 2026-08-19

### Added

- feat(layout): 根目录白名单收编 _paper——论文侧数据目录为四主仓既定实践，docs/reproduce 与论文定稿文档按 <repo>/_paper 绝对路径引用；v2.10.0 下发后 verify 布局门禁误报 FAIL
- feat: Enhance Fig 4 TAM visualization and data extraction
- feat: 框架键第二真源——指纹硬判定合并 contract/framework_binding.yaml 注册段

### Changed

- refactor: Update Fig 4 TAM data extraction and visualization
- refactor: Update Fig 4 TAM data extraction and visualization

### Fixed

- fix: Update JSON handling and encoding in analysis scripts; adjust summary data for accuracy

## [2.10.0] - 2026-08-19

### Added

- feat: 框架键第二真源——指纹硬判定合并 contract/framework_binding.yaml 注册段

## [2.9.0] - 2026-08-19

### Added

- feat(innovation): 种子目录登记 MAMMOTH_MODEL(B)/BUFFER_SIZE(D) 框架主键
- feat: lighten train icon palette
- feat: generate robot security gate variants
- feat: generate train compute icon variants
- feat: recolor hand-drawn barricade yellow and black
- feat: generate hand-drawn barricade variants
- feat: generate retractable validation barriers
- feat: generate roadblock icon variants
- feat: generate careful robot magnifier variants
- feat: generate thick black arrow asset atlas
- feat: generate independent arrow asset atlas
- feat: generate image2 loop rail variants
- feat: generate missing oblique icon atlases with image2
- feat: sketch rounded pentagon execution rail
- feat: generate oblique icon variant atlases
- feat: redraw AUTO-NN figure in NMI editorial style
- feat: simplify AUTO-NN figure to core icon set
- feat: integrate exploration board with AUTO-NN workflow
- feat: generate hierarchy-focused AUTO-NN figure revision
- feat: generate blue-person action icon variants
- feat: generate red-green check gate icon variants
- feat: generate code-change principle icon variants
- feat: generate frozen-score and round-decision icons
- feat: generate zero-baseline anchor icon variants
- feat: generate plain-reference anchor icon options
- feat: generate statistics and ablation icon variants
- feat: generate six papers docs code icon variants
- feat(paper): TAM 重算脚本加收集模式，支持各业务仓独立跑后回传聚合
- feat(paper): TAM 全量重算脚本落地（2345 行三通道级联）+ 主张四条制定稿

### Changed

- refactor(paper): TAM 重算脚本改两层驱动——单仓模式为默认，聚合模式 --all

### Fixed

- fix: regenerate blue-person icons as half-body poses
- fix(seed): Config-Only 从 cfg.SEED 解析种子，默认 42

## [2.8.8] - 2026-08-10

## [2.8.7] - 2026-07-31

### Fixed

- fix(scope): workspace/train 告警代号改为 workspace-edit
- fix(run): Agent 编辑边界改为两态并鼓励 innovate/aggressive 改 workspace

## [2.8.6] - 2026-07-30

### Added

- feat(run): --claude 新增 ccmm 前端 → minimaxM（cc-switch）

## [2.8.5] - 2026-07-30

### Fixed

- fix(experiment): v2.8.0 路径相对化的 3 处 try/except 加 # optional: 标记

## [2.8.4] - 2026-07-30

### Fixed

- fix(stream): think/text/tool body 去 dim——终端太浅看不清（v2.8.4）

## [2.8.3] - 2026-07-30

### Added

- feat(doctor): innovation_vocab 检查扫 TSV RDDN 旧词 → FAIL（v2.8.3）

## [2.8.2] - 2026-07-30

### Fixed

- fix(audit): 删 formal-novel 旧词检测（exploration_space 列从不出现）

## [2.8.1] - 2026-07-30

### Added

- feat(audit): 硬拦 RDDN 旧词 extend/formal-novel → legacy_depth FAIL（v2.8.1）

## [2.8.0] - 2026-07-30

### Added

- feat(paths): 实验地址全量相对化 — keepers/TSV/jsonl/round_decision 存相对 repo_root

## [2.7.3] - 2026-07-30

### Added

- feat(keeper): repair_keeper.py 修复路径硬编码 + pointer 滞后 + doctor check

## [2.7.2] - 2026-07-29

### Fixed

- fix(governance-sync): cp 列表补 scripts/auto-nn-setup.py（v2.5.6）

## [2.7.1] - 2026-07-28

### Fixed

- fix(clear): prune 时 regen 失败不阻断删目录；裸 python 可 AST 读 metrics

## [2.7.0] - 2026-07-28

### Added

- feat(D档): DATA_SAMPLER 钩子，采样器进 workspace 无需改 contract

## [2.6.0] - 2026-07-28

### Added

- feat(ledger): 台账登录 exploration_space，反思后自动回填

## [2.5.5] - 2026-07-28

### Fixed

- fix(manage_goal): cmd_show --all 补输出 goal.metric / goal.op（v2.5.5 UX 补）

## [2.5.4] - 2026-07-28

### Fixed

- fix(goal): goal.metric/op 用户手写必持久 + contract 校验（v2.5.4）

## [2.5.3] - 2026-07-28

### Fixed

- fix(nn-config): save 前剥离值==preset 默认的段, 治 manage_goal 把默认段落盘

## [2.5.2] - 2026-07-27

### Fixed

- fix(runtime_activity): 训练「在跑」仅认存活 pid，避免孤儿 status 误报
- fix(governance-sync): 下发 check_brief.py，供 auto-nn-check / console 看板

## [2.5.1] - 2026-07-25

### Fixed

- fix(update): governance-sync 后 doctor 自带 NN_RELAUNCH ack

## [2.5.0] - 2026-07-25

### Added

- feat(wait-train): 多槽训末自动 finalize-round

## [2.4.0] - 2026-07-24

### Added

- feat(clear): 确认后可由 Agent 代跑 --apply

## [2.3.0] - 2026-07-24

### Added

- feat(check): 默认先报参照再出表

## [2.2.4] - 2026-07-24

## [2.2.3] - 2026-07-24

### Fixed

- fix(verify): layout 校验改走 nn_resolve，跨机过期 template-root 不再误 FAIL

## [2.2.2] - 2026-07-24

### Fixed

- fix(finalize): 去掉入账目录集合的吞异常，消除 G-no-fallback FAIL

## [2.2.1] - 2026-07-24

### Fixed

- fix(sync): 补发 baseline_anchors_status.py，修复 update 后 ImportError

## [2.2.0] - 2026-07-24

### Added

- feat(finalize): 多槽全员入主台账（每槽一行 TSV/jsonl）

## [2.1.0] - 2026-07-24

### Added

- feat(auto-run): prompt 改为 plain 标签检索；禁 auto 立 reference
- feat(run-context): auto 不再注入 reference-start
- feat(run-context): plain-anchor-init 以 TSV plain 标签为门闩
- feat(baseline): 台账检索 has_plain/has_reference_baseline_tag

### Fixed

- fix(modify-config): --from-template 默认重置 baseline_tag=none

## [2.0.3] - 2026-07-23

### Fixed

- fix(setup): Poetry 2.x 兼容——lock 去 --no-update + package-mode=false

## [2.0.2] - 2026-07-23

### Fixed

- fix(setup): gpus 识别 YAML block/flow list，write 输出 check-env 认的 flow list

## [2.0.1] - 2026-07-23

### Fixed

- fix(human-guidance): 公平约束代写只写用户点名项，禁止发挥补全

## [2.0.0] - 2026-07-23

### Changed

- BREAKING: nn-config 切断 agent.* 迁移别名双写，只认顶层 block

## [1.48.31] - 2026-07-23

### Fixed

- fix: set-scenario-policy 导入改为 from lib.nn_config

## [1.48.30] - 2026-07-23

### Fixed

- fix(human-guidance): 消费者对齐——手跑/分析/清空也认文首公平约束

## [1.48.29] - 2026-07-23

### Fixed

- fix(human-guidance): 公平约束改为文首独立节，与路线图并列

## [1.48.28] - 2026-07-23

### Added

- feat(human-guidance): 可选字段「公平约束」，路线图与比较口径分离

## [1.48.27] - 2026-07-23

### Fixed

- fix(human-guidance): 代写含落盘——技能 Write+validate+commit，无需人粘贴

## [1.48.26] - 2026-07-20

### Fixed

- fix(init): 点破训练边界题义——不是问现在用哪个 loss

## [1.48.25] - 2026-07-20

### Fixed

- fix(init): 训练目标问话禁说五档，改用人话「什么能动」

## [1.48.24] - 2026-07-20

### Fixed

- fix(init): 迁入时推荐必须源对齐，禁止把公平划分标成推荐

## [1.48.23] - 2026-07-20

### Added

- feat(modify): P2 scope 对齐 watchlist 同步，STRICT 手跑拦 train/workspace

## [1.48.22] - 2026-07-20

### Added

- feat(modify): P1 modify-post-change.sh 按轨改后验收编排

## [1.48.21] - 2026-07-20

### Added

- feat(modify): P0 叙事对齐——watchlist 同步退役 Modify-L1，收尾须按 post-change 链

## [1.48.20] - 2026-07-20

### Added

- feat(check): table 展示 baseline_tag 的 none 为 -

## [1.48.19] - 2026-07-20

### Added

- feat(doctor): D0-D2 对齐卡轻闸、说明书卫生与目录路由同步

## [1.48.18] - 2026-07-20

### Added

- feat(init): align_probe + init-align 闭环（BUILD 去污染 / profile 建议 / 尺子闸）

## [1.48.17] - 2026-07-20

### Fixed

- fix(init): BUILD 手册模板去 workspace_full，与头注释 code 对齐

## [1.48.16] - 2026-07-20

### Added

- feat(init): 缺 abcde-manual 则立项失败，doctor/verify FAIL

## [1.48.15] - 2026-07-20

### Added

- feat(init): breakin 叙事修正与 migrate 扫源仓

## [1.48.14] - 2026-07-20

### Added

- feat(doctor): 禁止 shared_context 承载/读取 contract（方案 B）

## [1.48.13] - 2026-07-20

### Added

- feat(smoke): 实质指标闸——主分须有限，拒绝 _error+0 兜底

## [1.48.12] - 2026-07-20

### Added

- feat(sync): 立项原始模板戳 init-template-version 只写一次

## [1.48.11] - 2026-07-20

### Added

- feat(init): E5 成绩表必含基线角色列并钉死落盘
- feat(analyse/check): 报告与台账体检基线尺子（plain/reference）

## [1.48.10] - 2026-07-20

### Added

- feat(init): O3 改为起步 plain/reference 尺子（baseline-anchors）

## [1.48.9] - 2026-07-19

### Added

- feat(framework-binding): `contract/framework_binding.yaml` 五能力接入总表 + `scripts/lib/framework_binding.py`
- feat(doctor/smoke): `fw_binding_*` 门禁；`eval` 台账 ↔ 框架原样主分对账
- docs: PROTOCOL §3.0.2b / 白皮书 §1.5.3 / mammoth 示例两段式

### Changed

- sync: governance-sync 下发 `framework_binding.py`（stamp-required）

## [1.48.8] - 2026-07-19

### Added

- feat(sync): governance-sync 强制下发 `contract/__main__.py`（verify 对齐）
- feat(setup): 常见动态库缺失 → cu12 nvidia pip 轮 best-effort（如 cusparseLt）
- feat(analyse/doctor): 辅指标近轮恒 0 → `aux_always_zero` WARN

### Changed

- fix(scenario): `agent.scenario_default` 空由 WARN 升为 FAIL
- docs: PROTOCOL 脚手架硬门与辅指标恒零提示

## [1.48.7] - 2026-07-19

### Changed

- refactor(runner): 正名 `is_evaluate_runner_repo`（`is_adapter_repo` 兼容别名）；对外称 runner 出分验收
- docs: PROTOCOL §3.0.2a / CLAUDE 去掉「Adapter 验收包」主称呼；澄清 ≠ 立项 ADAPTER / object_type

### Added

- feat(doctor): `evaluate_runner_baseline_tag_doctor`；nn-doctor baseline 门委托该 helper
- test: `test_evaluate_runner_gates_live` 实弹夹具（缺 baseline_tag → FAIL；LEARNER 不触发）

## [1.48.6] - 2026-07-19

### Added

- feat(sync): stamp-required API；写戳前校验 train_runtime 齐套
- feat(doctor): sync_need_files 缺 stamp 文件硬 FAIL
- feat(doctor): contract_test_signature（always→FAIL / conditional→WARN）

### Fixed

- fix(sync): verify_governance_sync_dest 补 classify 与 stamp 对齐文件

## [1.48.5] - 2026-07-19

### Added

- feat(check-env): 分类 torch import 失败（动态库 vs 缺包）

### Fixed

- fix(doctor): env 动态库误诊文案；sanity 连锁改 SKIP

## [1.48.4] - 2026-07-19

### Added

- feat(hygiene): _vendor gitignore + 禁实验路径 env/绝对路径兜底
- feat(doctor): 场景回潮进 contract 硬 FAIL；init 文案对齐
- feat(finalize+doctor): 缺 auto_mode 硬失败，不再吞 ImportError
- feat(sync): 强制下发 auto_mode 与 refresh-human-guidance-baseline

## [1.48.3] - 2026-07-19

### Added

- feat(doctor): adapter 空串 CLI 透传硬 FAIL
- feat(sync): 强制下发 adapter_accept.py
- feat(doctor): adapter 形态缺 baseline_tag 列/watchlist 硬 FAIL
- feat(adapter): finalize 强制声明辅指标真值（禁假缺）
- feat(adapter): 空串 CLI helper（adapter_accept）

### Fixed

- fix(example): mammoth adapter 接入验收 helper，去掉辅指标假 0

## [1.48.2] - 2026-07-18

### Added

- feat(migrate): AST 迁移 finalize_run 旧 best_metrics kwargs

### Fixed

- fix(sync): 强制下发 train_branch* 且 finalize kwargs scan 阻断

## [1.48.1] - 2026-07-18

### Fixed

- fix(config): 修复 lock 导入与 nn-config load/save 幂等

## [1.48.0] - 2026-07-18

### Added

- feat(ledger): #6 find_unfinalized_multi_slot 单一真源

### Changed

- refactor(ledger): check_multi_slot_finalize 改为薄 CLI

## [1.47.0] - 2026-07-18

### Fixed

- fix(train): finalize_run 只传 precomputed_official_metrics
- fix(finalize): 官方分仅接受 precomputed，删除 test/checkpoint 回退

## [1.46.2] - 2026-07-18

### Fixed

- fix(train): 派发出口归一训练结果并保留 stop_reason

## [1.46.1] - 2026-07-18

### Fixed

- fix(experiment): 4 处 preflight guard 改用 _run_optional_subprocess helper
- fix(experiment): 抽 _run_optional_subprocess helper，修 _git_changed_paths 漏标 optional

## [1.46.0] - 2026-07-18

### Added

- feat(auto-nn-setup): 薄壳 SKILL.md + Code Contract（§10/§15 门禁）
- feat(auto-nn-setup): 编排 main（检测→改盘→lock/install→gpus→smoke+回滚+dry-run，§4/§7/§8）
- feat(auto-nn-setup): .bak 备份/还原 + 系统 pyyaml 探针（§7/§10.2）
- feat(auto-nn-setup): GPU 白名单解析/交集 + nn-config gpus 读写（§6）
- feat(auto-nn-setup): pyproject torch 源正则改写（4 处不碰 PyPI 段，§7/§10.2）
- feat(auto-nn-setup): CUDA 检测 + 五档 torch 源映射（§5.1/§5.2）

### Fixed

- fix(auto-nn-setup): nit #1 写 gpus 前备份 nn-config（防 truncate 中途被杀丢内容）
- fix(auto-nn-setup): M-1 失败路径告警诚实化
- fix(setup): main/nn-config 防 traceback 泄漏 + mirror 重试不重 lock（Task5 代码评审）
- fix(setup): pyproject 缺 → clean SetupFail（§4 检测项 2「齐全」）
- fix(setup): 补 §4 检测项 1-3（Python 版本/poetry/venv 探针 + poetry 缺 clean FAIL）
- fix(setup): backup_files 缺源文件抛 SetupFail 而非裸 FileNotFoundError

## [1.45.1] - 2026-07-18

### Fixed

- fix(train): dispatch 后统一写 train_done 与 checkpoint
- fix(nn-config): 统一加载 seam（ADR-12）

## [1.45.0] - 2026-07-18

### Added

- feat(train): TrainingMech 非 NATIVE 接线骨架（卡②方案 A）

### Fixed

- fix(sync): 下发 init_workflow，停发 init_scenarios（卡③）

## [1.44.0] - 2026-07-18

### Added

- feat(workspace): 显式 adapter_runner + 注册时戳 __workspace_name__

### Fixed

- fix(review): 戳名失败上抛、resolve 不误读 runner、ADR/PROTOCOL 对齐
- fix(train): 训末从 ws.adapter_runner 取 runner，真实对象回归双路径
- fix(contract): 门面转发 adapter_runner，接通评 runner 入口

## [1.43.1] - 2026-07-18

## [1.43.0] - 2026-07-18

### Added

- feat(train): 训练主循环接 dispatch_training seam(维度 A)
- feat(train_branch): dispatch_training 训练调度 dispatcher(维度 A)
- feat(workspace): training_mech 注册表(维度 A,对称 metrics_shape)

### Fixed

- fix(train_branch): dispatch_training 字符串归一对齐 metrics_shape (spec §5.3)

## [1.42.1] - 2026-07-18

## [1.42.0] - 2026-07-17

### Added

- feat(reflect): Phase 0 prompt 注入训练过程 loss 细节段
- feat(reflect): 加 _dynamics_compact_for_phase0 渲染 loss 细节 tail
- feat(reflect): 加 _load_train_dynamics 读现成 train_dynamics.json 摘要
- feat(doctor): 加 check_baseline_reference WARN 项（EXPERIENCE「基线锚点」段值域校验）
- feat(init): manual 追加「基线 reference 探测」段（B-轻）
- feat(run-context): 填实 _state_reference_anchor_value + 靶子段 reference 行显示真值
- feat(run-context): 基线靶子段（plain + reference 桩 + 当前最佳差值）
- feat(doctor): check_baseline_tag WARN（config 字段存在 + TSV 列值域）
- feat(experiment): finalize_run 兜底 config.json baseline_tag=none
- feat(profiles): baseline_tag 加入三 profile default_watchlist（TSV 列传播）

## [1.41.0] - 2026-07-17

### Added

- feat: release-check Step 7 挂包文档契约 lint
- feat: 包文档契约 lint（第一批 banned/required）

## [1.40.0] - 2026-07-17

### Added

- feat(preflight): CLAUDE/PROTOCOL/auto-nn-run 纳入 IMMUTABLE 硬锁

### Fixed

- fix(nn-doctor): IMMUTABLE 路径改动记 FAIL（immutable_path_guard）
- fix(scope-check): experiment/contract 拆入 IMMUTABLE 桶并 FAIL
- fix(preflight): G-框架/G-契约无 relaunch 时 raise（三源 diff）

## [1.39.4] - 2026-07-17

### Fixed

- fix(experiment): non-finite WARN 的 float 解析 except 补 # optional:

## [1.39.3] - 2026-07-17

### Fixed

- fix(runtime): doctor/auto-run 改用 resolve_exploration 并对齐三态边界
- fix(tests): 门面测试跟随 SCENARIO_ID 退役

## [1.39.2] - 2026-07-17

### Fixed

- fix(contract): 退役空壳 `SCENARIO_ID` 常量与 property（`metrics.py` 残留 + `__init__.py` property；属 cfg 层非 contract）
- fix(goal_spec): `validate_goal_spec` 从 WARN 升硬 FAIL（metric 与 scenario 双向 `raise ValueError`，对称 no-fallback）

## [1.39.1] - 2026-07-17

## [1.39.0] - 2026-07-17

### Added

- feat(run-context): ablation-hint 组件归因消融引导句（KEEP 且严格改善时注入，§4.1 路线A）
- docs(doctor): D-3g 数据体检规格（规划中；`nn-doctor.sh` 未实现）
- feat(train): per-epoch non-finite (nan/inf) 实时 WARN (B3)
- feat(loss): auto-capture undeclared loss components + first-time WARN (B2)

## [1.38.2] - 2026-07-17

### Fixed

- fix(manual-run): 修正能力倒挂 — 边界从"只改config"改为三态

## [1.38.1] - 2026-07-17

## [1.38.0] - 2026-07-16

### Added

- feat(doctor): run hardcoded_params scan in light tier (was deep-only placeholder)

## [1.37.1] - 2026-07-16

## [1.37.0] - 2026-07-16

### Changed

- refactor(init): retire --from-preset preset route

## [1.36.0] - 2026-07-16

### Added

- feat(external): B1 seed_repos.json universal + executor._seed_repos_lookup 前馈

## [1.35.0] - 2026-07-16

### Added

- feat(external): D1 external_evidence_health — bundle health JSON 落盘
- feat(external): B2 query_refiner — cross-round query rewrite + executor hookup
- feat(external): A2 — release-check step 6.5 skeleton_queue health lint
- feat(external): A2 — skeleton_queue cross-round tracking + prompt inject

## [1.34.0] - 2026-07-16

### Added

- feat(external): D2 — check_external_keys + startup banner
- feat(external): C1 — auto-infer docs_symbols from ctx.rationale/fingerprint
- feat(external): A1 — inject paper.method_excerpt into synthesis prompt

### Fixed

- fix(external): D2 — isolate key-check tests from real credentials + drop redundant exception guards

## [1.33.0] - 2026-07-16

### Added

- feat(governance-sync): ship migrate_metrics_shape.py + auto-run on business repo pull
- feat(migration): migrate_metrics_shape.py for business repos to adopt MetricsShape
- feat(init-workflow): detect() emits framework_kind for object_type=framework
- feat(dispatcher-types): 3 orthogonal enums (MetricsShape/TrainingMech/FrameworkKind) + from_legacy
- feat(external): spec — 外部证据反馈环改进 (v1.30/v1.31/v1.32)

### Changed

- refactor(init_o3): propagate framework_kind through interactive_run
- refactor(train.py): workspace_kind → metrics_shape; nn-config.yaml → workspace.metrics_shape
- refactor(workspace): WorkspaceKind = MetricsShape alias; register accepts enum/str dual-form
- refactor(dispatcher): rename workspace_kind → metrics_shape, accept enum/str dual-form

## [1.29.1] - 2026-07-15

### Fixed

- fix(init-doc): 对齐 exploration_mode 单旋钮语义 + 修正 G0→G1 合并后 stale

## [1.29.0] - 2026-07-15

### Added

- feat(retire-skills): governance-sync 不再下发 skills/;业务仓 doctor FAIL 建议删除

## [1.28.0] - 2026-07-15

### Added

- feat(manual-run): 白皮书 §5.1 边界段 + flowchart manual_run_scope_gate 节点 (双保险范围闸)
- feat(manual-run): doctor SKILL.md Code Contract + manifest 登记 manual-run-scope-check.sh
- feat(manual-run): SKILL.md 启动段加'启动前意图判别'段(关键词→推荐 /auto-nn-modify)
- feat(nn-doctor): §8 接入 manual_run_scope_check 子检查 (Idiom 3)
- feat(manual-run): scope-check.sh — preflight git diff 闸 (nn-doctor §8 兜底)

## [1.27.1] - 2026-07-15

### Fixed

- fix(doctor): template_residuals 白名单 maintainer/auto-nn-init/templates/
- fix(build-run-context): json.dumps 加 default=str 兜 PosixPath
- fix(experiment): metric_direction 空字典兜底返 None

## [1.27.0] - 2026-07-15

### Added

- feat(skill-contract): integrate lint into release-check step 6
- feat(contract): pilot extension to 12 skills (manual-run/auto-run/analyse/clear/doctor/modify)
- feat(update): add Code Contract section (pilot extension)
- feat(reflect): add Code Contract section (pilot extension)
- feat(human-guidance): add Code Contract section (pilot extension)
- feat(compress): add Code Contract section (pilot extension)
- feat(check): add Code Contract section (pilot extension)
- feat(goal): add Code Contract section (pilot extension)

## [1.26.1] - 2026-07-15

### Fixed

- fix(doctor): 加 2 检查 + 1 升级 (legacy mode / exploration_mode 值 / run_context FAIL)

## [1.26.0] - 2026-07-15

### Added

- feat(skill): HARD-GATE G0→G1 合并 + D1/D2 supervised 推荐修订

## [1.25.0] - 2026-07-15

### Added

- feat(pdf): persist pdftotext 全文为 .txt,让 agent 可深读
- feat:new dot position

## [1.24.0] - 2026-07-15

### Added

- feat(train): dispatcher 双路径 + workspace.kind cfg opt-in (Layer 3 complete)
- feat(workspace): register_workspace_kind registry + get_workspace_kind 默认 'supervised' (Layer 3)
- feat(contract/runtime): CONTRACT_DEFAULTS 默认 (Layer 2 配置兜底)
- feat(contract): _safe_metric property + default_metrics 骨架 (Layer 2)
- feat(goal_spec): Predicate.metric_unit 字段 + parse 自动归一 + evaluate normalize 比
- feat(lib): add metric_units helper skeleton (Layer 1)

### Changed

- refactor(goal_spec): 单一来源 _goal_met from run_ledger_summary (preserves v3 _goal_gap sign convention)

### Fixed

- fix(goal_spec): clarify evaluate normalizes via fresh metric_unit lookup
- fix(lib): dedup metric_unit unknown warning (per T1 code review Minor #1)

## [1.23.0] - 2026-07-15

### Added

- feat(rddn): T10 — 三份 living doc 同步 (RDDN 四档 + 寻找/评估双胞胎 + ADR-5 双副面孔)
- feat(rddn): T9 — github code-fetch (P3+ 抓 raw 代码喂寻找) (#25, ADR-9)
- feat(rddn): T8 — catalog seed + overlay 软层 (ADR-3)
- feat(fingerprint): T7 routine-recombination→derived detection (#23)
- feat(rddn): T6 — introspection→depth 标准件检测封顶 derived (#22, ADR-4)
- feat(rddn): T5 — 寻找(find) eagerness 按 mode 走 + paper_depth 双语义锁 (#21, ADR-7/8)
- feat(rddn): T4 — reflect cycle「寻找」(find) 阶段 (ADR-6)
- feat(rddn): T3 — novel=LLM-attestation-only (ADR-2)
- feat(innovation): T1 RDDN expand — derived/different coexist with extend/novel

### Changed

- refactor(rddn): T2 migrate producers old→new depth vocab + contract (#18)

## [1.22.1] - 2026-07-14

## [1.22.0] - 2026-07-14

### Added

- feat(init-workflow): detect() 单轴分类实现 + 9 格 matrix 测试覆盖 (PR2.1 — 替 _classify_object_type 的入口)
- feat(init-workflow): 加 VALID_SLUGS_BY_WORKFLOW/MIN_ENTRIES_BY_WORKFLOW/resolve_init_workflow(平行旧字段,PR2 切)
- feat(init-workflow): init_o3_abcde.py 切 detect() 单一入口,删 _classify_object_type 与 4-branch 复杂度 (PR2.2)
- feat(init-workflow): new-project.sh 切 3-branch (build/migrate/update) + abcde_migrate.py 走 detect() + new_project_scenarios.py 删 resolve_init_scenario (PR2.3)
- test(init-workflow): 重写 test_init_o3_abcde/test_init_overlay/test_init_o3_abcde_manual 适配 3-workflow + 3-object_type 单轴 (PR2.4)

### Changed

- refactor(init-o3-abcde): PR2.2 micro-fix — workflow 参数加 `Workflow` 真注解 (顶替 `# Workflow` 注释),detect import 顶层 (替内层 lazy import);无行为变更
- chore(presets+templates): L1 机械清理 body 内残留旧术语 (PR2.x body-rename — 4 文件 8+/14-,lint+测试 baseline 不变)

### Removed

- feat(init-workflow): lint_preset/init_qa_log/append-init-qa-log 删旧 entry 字段,改 workflow 单一维度 (PR2.5)

### Fixed

- chore(test): 删 abcde_defaults 孤儿测试（PR1 收尾 — fab11e5/v1.16.0 漏清对应单测）
- fix(templates): PR2.4 unblock — 建 migrate.md (PR1.2 改名漏造) + 修 overlay/data.md B-routine
- chore(test): 暂 skip test_abcde_migrate.py（PR1 收尾 — reinit.md → update.md rename 致 4 测试 fail）
- chore(test): 暂 skip test_new_project_scenarios.py（PR2.3 — resolve_init_scenario 删了,6 测试 pending PR2.4 rewrite for 3-workflow build/migrate/update）
- chore(test): 重写 test_scenarios_yaml.py 适配 3-workflow (PR1 收尾 — 4-scenario → 3-workflow yaml rename 致 16 测试 fail;resolve_scenario 段 skip 待 PR2)
- chore(test): 修 test_overlay_register_ceiling.py 适配 PR1.2 overlay 重命名 (atomic 删 / complex_framework → framework)
- chore(pr1): PR1 收尾完成 — 文件重命名 + 平行字段已就位,无遗留 PR1 回归 (FIX-1/2/3/4)

## [1.21.0] - 2026-07-14

### Added

- feat(migrate): migrate_to_exploration_mode 一次性迁移老 mode 字段 + governance-sync 接入
- feat(experiment_mode): resolve_exploration 集中自包含解析 exploration_mode → bundle + 旗标

### Changed

- refactor(cleanup): 退役 effective_experiment_mode/_resolve_mode/apply_experiment_mode(3档)，write-path 只写 exploration_mode，auto-promote 简化
- refactor(readers): check_goal/metric_floor/external/experiment 改读 resolve_exploration
- refactor(nn_config): load_nn_config 按 exploration_mode 选 bundle，退役 default/get shim
- refactor(presets): 单一权威 bundle 表 — _BASE + _MODE_DEFAULTS(含 tier_start/runtime)，退役 _PRESETS 4-style

## [1.20.0] - 2026-07-14

### Added

- feat(流程图): picker/reflect/context 三折叠组 + legend 收起 + 审计 5 行号修正
- feat(流程图): 展开 auto-nn-run shell 子过程为子链 + inject type 基建

### Fixed

- fix(流程图): arh_gate 行锚 (L329)→(L329/L1422) 对齐调用点

## [1.19.0] - 2026-07-13

### Added

- feat(流程图): 图例可点 + 按类型/边高亮 dim 节点
- feat(paradigm-lock): Phase 3 R8 — 范式撞墙软警告 + e_subtype 区分(要求1)
- feat(supervised): Phase 2 D-DATASET — 数据集身份锁死 contract 常量(要求2)
- feat(physical): B-soft Phase 1 — β scheme registry 改 build_optimizer elif 分派

## [1.18.0] - 2026-07-13

### Added

- feat(external-evidence-loop): #01+#02+#03+#05 wiring + flowchart 2-stage restructure

## [1.17.1] - 2026-07-13

## [1.17.0] - 2026-07-13

### Added

- feat(fork-trigger): auto-nn-run.sh 10 步接入（step0b 读建议/step2 放行 cell 级 manual/step7 写 source_block/doctor drift 同步）
- feat(fork-trigger): init 头注改写为 runtime fork 路径 + HUMAN_GUIDANCE 覆盖优先级（spec §5.2/§11 ③）
- feat(fork-trigger): reflect 产 register→fork 升级建议并注入 direction_full（spec §4 步4）
- feat(fork-trigger): reflect verify_source_block_exhaustion evidence-quality 门（spec §11 ①）
- feat(fork-trigger): source_block sidecar 读取/合并/多槽汇总（spec §4 步2→3）

### Fixed

- fix(fork-trigger): complex_framework overlay 6 cell 去「改源码」越界（含 spec 漏列 A-novel/C-extend，spec §6）
- fix(fork-trigger): atomic_package overlay 5 cell 去「改源码」越界 + 废弃标记（spec §6）

## [1.16.5] - 2026-07-12

### Fixed

- fix(init): adapter 短路架空 _COMPLEX_FRAMEWORKS 名单 — 命中升级 complex_framework

## [1.16.4] - 2026-07-12

### Fixed

- fix(template): AE-2 失败计数接线 + verify skills/_vendor 白名单 + clear-runs 删待实现标注

## [1.16.3] - 2026-07-11

### Fixed

- fix(experiment_mode): 6 档统一入口 set_experiment_mode(修 careful/aggressive/auto 崩溃)

## [1.16.2] - 2026-07-11

### Fixed

- fix(skills): 清退役机制残留引用 (guidance 载体退役漏清的 skills/ 文档漂移)

## [1.16.1] - 2026-07-11

### Fixed

- fix(scripts): 删 manifest 中 abcde_defaults.py 死引用

## [1.16.0] - 2026-07-11

### Changed

- refactor: 退役 abcde-guidance.yaml 载体 + abcde_defaults.py + check_ABCDE_boundaries 门禁

## [1.15.0] - 2026-07-11

### Changed

- refactor(presets): 删 default_upper_level 死字段（4 处定义零消费者）

### Fixed

- fix(auto-promote): 显式档不注入 auto 段，防误自动升档
- fix(experiment): finalize_round 接通 check_and_promote_auto（断点①）
- fix(auto-mode): 接通自动换挡执行侧三断点

## [1.14.1] - 2026-07-11

### Fixed

- fix(init): E 行归属场景模板，不被对象类型 overlay 覆盖（reinit 可改回归）

## [1.14.0] - 2026-07-11

### Added

- feat(init): manual 5×3 表按对象类型 overlay（4 场景 marker + 5 overlay + splice）
- feat(init): write_init_outputs/interactive_run/CLI 透传 framework 信号
- feat(abcde): default_guidance/_framework_block 接 framework 入参

### Fixed

- fix(init): overlay splice 加 fail-loud 守卫（marker 计数 + 空表检测）

## [1.13.1] - 2026-07-11

### Fixed

- fix(tests): 修 v1.13.0 退役后 8 个 stale 测试 + 流程图文档

## [1.13.0] - 2026-07-11

### Added

- feat(abcde): init 对象类型分析 + manual 生成（退役 derive_modifier_examples/locked_keys 派生）

### Changed

- refactor(abcde_migrate): md_path 改 references/manual/abcde-manual.md
- refactor(inject): render_tier_slice 改读 manual cell、删 Segment A + modifier_seeds 拼接
- refactor(verify-governance-sync-dest): 去 abcde_modifier_derive + init_qa_log_walker 断言
- refactor(governance-sync): cp 列表去 abcde_modifier_derive/init_qa_log_walker/check_abcde_boundaries
- refactor(abcde): build-run-context 删 _render_abcde_boundaries_suggestion（enforcement 展示退役）
- refactor(abcde): 删 abcde_modifier_derive + check_abcde_boundaries + init_qa_log_walker（退役模块）
- refactor(abcde): 删 enforcement/modifier_seeds/5 死块，default_guidance 只留 framework
- refactor(abcde): 4 场景 template 4段叙述 → 5×3 表骨架 + 对象类型适配

### Fixed

- fix(abcde): _classify_object_type mutability 用文档契约值 register（修 registry 笔误）
- fix(nn-doctor): E 档门禁硬编码 contract/ + 读 init_scenario 判 reinit（enforcement 归位）

## [1.12.1] - 2026-07-11

### Fixed

- fix(flowchart): 拖动节点边跟随(修边脱节)

## [1.12.0] - 2026-07-11

### Added

- feat(flowchart-v2): 整图单次 ELK DOWN + 4 tab + 分区堆叠
- feat(flowchart-v2): 改用 React Flow + ELK 自动布局(根治边穿节点)
- feat(flowchart-v2): 收敛 nodes.yaml 单源 + 内容同步源码 + 防 stage 堆叠
- feat(flowchart-v2): 整体图视角改造(不分块) + tip hover 整合 + 跨 stage 边 BOTTOM→TOP 统一
- feat(flowchart-v2): hover tooltip(节点说明)

### Fixed

- fix(flowchart-v2): NNNode 补隐藏 Handle 修复边不渲染

## [1.11.0] - 2026-07-10

### Added

- feat(init): SKILL.md 加「fast 路线」章节（**主推自动化路线**）—— in-tmux Claude 看项目答 24 步
- docs(init): hard-gate-reference.md 末尾加「--fast 路线」章节
- docs(init): presets/README.md 加废弃说明（preset 路线保留兼容，不推荐）

### Changed

- **preset 路线从「主推」降为「保留兼容」** —— mammoth preset 烟测实测暴露写死通用答案不适配项目（5 backbone continual learning 项目 phase 2 失败）
- **fast 路线替代 preset 路线** —— `--fast` flag 让 in-tmux Claude **看项目**答 24 步（不写死、不脚本化）

### Notes

- **触发原则（P0 升级）**：父 Agent / 编排器默认走 fast（自动化场景），真人默认走 picker（教学 + 决策）
- 不替代 picker 主路径（日常 init 仍推荐 picker）
- 不加新 slash 技能（仍是 `/auto-nn-init`，只是多 1 个 flag）
- 不默认被编排器自动调用（必须用户/编排器明示）
- 不改 `append-init-qa-log.py` / `init_qa_log.py` 代码层
- 不写 `gen-preset.py` 脚本（fast 路线不要脚本化）
- 不写死通用答案（preset 旧路线错）

## [1.10.1] - 2026-07-10

### Added

- docs: 合成 auto-nn autonomous research 论文第十二版，融入 pluggable workspace、ABCDE guidance 与 PDH 基线锚定主线

## [1.10.0] - 2026-07-10

### Added

- WP0.1: 三范式 skeleton 结构统一为 contract/ 子目录布局(supervised/rl/physical 一致)
- WP0.2: mammoth skeleton 移出至 `docs/examples/adapter-mammoth/`(留 ADAPTER 参考)
- WP0.3: 四场景 `scenarios/*.yaml` 落地(greenfield/migration/adapter/reinit)+ `--scenario` CLI 维度
- WP0.4: mammoth CLI 适配器 `register_cli_adapter` 契约统一(语义:外部框架 CLI 注入注册点)
- WP1: package `build_optimizer` cfg 分派(adam/adamw/sgd) + `_NullScheduler` 具名 no-op
- WP1: 三范式 skeleton `build_*` 全部走 cfg 分派;修 `cfg.get` 违规 + 消 fallback
- WP1③: physical OPTIMIZER_SCHEME β named scheme registry(@register_optim_scheme,adam/lbfgs/adam_lbfgs)
- WP3: 治理层接入 OPTIMIZER_SCHEME(锁字段 + `a_optim_schemes` 枚举 + tam_contract red_line)

### Changed

- refactor(template): 模板仓物理骨架分层理清(contract/ 子目录布局),mammoth 不再在 skeletons/ 下

### Tests

- test_build_layer_dispatch.py:30 测覆盖三范式 build_* 分派 + unknown-key raise
- test_scenarios_yaml.py:4 场景 yaml 结构对齐审查
- test_mammoth_cli_adapter.py:register_cli_adapter 契约统一回归
- test_wp3_governance_integration.py:13 测锁 WP3 治理接入不变量 + scope 限
- 276/276 测试全绿

### Notes

- 全 register 重构只动「存在层」(workspace/ registry);**不碰** 评估口径(contract/)和锁(ledgers)
- 沙箱 1 轮 smoke 跳过(per user 决策;沙箱仓 sandbox-auto-nn 需独立安装)
- 详见 `docs/20260709_2230_方案_全注册制重构spec.md` §4 WP0/WP1/WP3 + §6 验证策略

## [1.9.0] - 2026-07-10

### Added

- feat(init): presets/aggressive-minimal.yaml — 入口 B 23 条预设, aggressive 模式 (smoke/回归/批量)
- feat(init): presets/conservative-baseline.yaml — 入口 B 23 条预设, conservative 模式 (baseline/长训)
- feat(init): presets/README.md — schema 文档 + P0 触发原则
- feat(init): lint_preset.py + test_lint_preset.py — preset schema 校验 (15 测覆盖 7 类场景)
- feat(init): SKILL.md L144 加 preset 例外 + 新增「preset 路线」章节
- feat(init): hard-gate-reference.md 末尾加「preset YAML 模板」章节

### Notes

- 触发原则 (P0): 默认走 picker 主路径. 必须用户明示才走 preset. 编排器默认不调.
- 不替代 picker 主路径, 不加新 slash 技能, 不改 append-init-qa-log.py 协议层.
- sandbox-init `--preset` flag 在 sandbox-auto-nn 仓独立发版.

## [1.8.0] - 2026-07-10

### Added

- feat(init): guidance 接管 enforcement + modifier_seeds（boundaries 迁移 P2/加法阶段）

### Changed

- refactor(abcde): P4 物理退役 abcde-boundaries.yaml（producer 删除 + 死引用清零）
- refactor(abcde): P3 迁读者读 guidance.enforcement + 修 nn-doctor 假门禁

## [1.7.2] - 2026-07-10

### Changed

- refactor(contract): 撤回 keep_threshold / protected_paths 空壳归位

## [1.7.1] - 2026-07-10

### Changed

- docs: 白皮书（§1.2/§3.4/§4/§6/缩略语）同步 1.7.0 P0 探索契约机制 + 沉淀研究记录/spec WIP；无 template/package 功能性变更。

## [1.7.0] - 2026-07-10

### Added

- feat(init): write_init_outputs 同产 abcde-guidance.yaml（boundaries.yaml 保留）
- feat(abcde): Layer 5 rescue_ladder + framework 块（ADAPTER/MIGRATION）+ 最终组装
- feat(abcde): Layer 4 tam_contract（scenario_required + capability_path + verdict_rules）
- feat(abcde): Layer 3 joint_constraints（ADAPTER 禁 B+C / B+C+D）
- feat(abcde): Layer 2 guidance_matrix（5 tier × 3 depth，深度=查询维度）
- feat(abcde): default_guidance 骨架 + Layer 1 capability_surface
- feat(contract): protected_paths 模块常量 + Contract.protected_paths property
- feat(contract): Contract 门面接题面归位（keep_threshold 读常量 + scenario_id property）
- feat(contract): 题面归位 KEEP_THRESHOLD/SCENARIO_ID 常量入 metrics

### Fixed

- fix(experiment+auto-nn-run): AE-1 NaN 防御 + AE-2 batch 早退根治

## [1.6.2] - 2026-07-08

### Fixed

- fix(bump-version): REPO_ROOT 解析改用 git toplevel，兼容 .claude/skills/ 路径
- fix(auto-nn-run): A5 v4 schema 解析 + _abcde_bd_out 未绑定变量兜底

## [1.6.1] - 2026-07-08

## [1.6.0] - 2026-07-08

### Added

- feat(experiment_mode): apply_mode 加 auto 分支（start_mode override）
- feat(auto_mode): 新文件（撞墙检测 + effective_mode + yaml 写盘升档）
- feat(experiment): should_keep 注入撞墙信号（streak 计数）
- feat(reflect_hook): 3 源状态行 + 显式未启用提示（不是 silent skip）
- feat(router): 3 源联动（paper + docs + github 跟 mode 走）
- feat(experiment_mode): apply_mode 写 6 档（联动 7 字段 + 用户 external override 优先）
- feat(nn_config): _resolve_mode 6 档解析 + 老 12 组合 → 5 档 derive
- feat(presets): default_for_mode 6 档 + reflect.interval 默认 1（careful=2）
- feat(mode): primary_delta 重命名 primary_delta_rel（相对值防误读）
- feat(design): unified-mode 加 auto 第 6 档（5 显式 + auto = 6 档）
- feat(L3-T6): init_qa_log_walker.py ABCDE 4 tier 端到端 dry-run
- feat(L3-D1): auto-nn-run.sh 多槽 finalize 门禁
- feat(L3-A1): dest 端到端镜像验证脚本 + 集成测试

### Changed

- refactor(experiment): streak 移到 finalize_round 末尾 + stderr 警告
- refactor(experiment_mode): apply_mode docstring 澄清 + 强化 test
- refactor(nn_config): drop _infer_legacy_mode from __all__ (private helper)
- refactor(mode): dedupe _resolve_keep_delta + bool guard

### Fixed

- fix(new-project): A4 --force 旗覆盖但保留 _runs 跑数据
- fix(experiment): A3 data_dir 不再硬编码 data/example-cls
- fix(init-qa-log): A2 防漂移到 template/package（3 道防线）
- fix(experiment): A1 metric_key 空 dict StopIteration 兜底（5 行）
- fix(format_prompt): spec 格式对齐（方括号 + github_impl/ecosystem 分行）+ hits_cap=0 兜底
- fix(L3-A1): verify_governance_sync_dest.sh 加 --template-root + L3 脚本检查
- fix(governance-sync): 补 L3 3 脚本白名单（多槽门禁/walker/dest 验证）
- fix(config): P0-A3 兼容裸字符串 exploration（r27 长跑实测 mode: innovate 失效修复）
- fix(abcde): P0-A2 _ENTRY_HEADER_RE 扩 [A-Za-z0-9_-]（兼容小写语义 slug + 数字 + 连字符）

## [1.5.5] - 2026-07-08

### Added

- feat(append-init-qa-log): T6.5 append 入口接三态 normalize + warn 双写（防 ABCDE 全空）
- feat(lock-normalize): T6.5 warn 双写（log CSV + stderr 打印）+ 边界 test（P0-2 第二阶段第二步）
- feat(lock-normalize): T6.5 词库 + 三态 normalize + 9 case test（P0-2 第二阶段第一步）
- feat(experiment): P1-6 加 _extract_metric_percent helper（adapter 仓通用指标抽取，防硬编码）

### Changed

- refactor(executor): P1-7 plan-fill 挪进 empty_bundle（single chokepoint，4 路径全覆盖 + to_dict 去 drift）

### Fixed

- fix(verify): P0 skills/ 白名单放行 ABCDE 模板（skills/maintainer/auto-nn-init/templates/）
- fix(governance-sync): P0 VERSION 加 fallback 链（template/package/VERSION 与仓库根都接受）
- fix(experiment): P0 修 _load_ledger_watchlist 两处 except: return () 加 # optional 注释
- fix(abcde): P0-2 _ENTRY_HEADER_RE 改抓 step_label 代号（三格式 qa-log 都认；r26 向后兼容）
- fix(auto-run): P1-5 P1-3 auto-commit add 清单加 .auto-nn/skill-activity.jsonl（防 G1 漏尾巴）
- fix(executor): P1-7 bundle 落盘补 plan 字段（paper_depth/docs_depth/eco/hits_cap，防 None）
- fix(reflect): P1-4 回流 ccg phase2 coerce（findings/references_to_add 规整为 list-of-dict，防 str 元素 .get() 崩）
- fix(governance-sync): P0-3 补下发 presets.py + abcde_modifier_derive.py 2 lib
- fix(external): P0-1 exploration.style 读新 schema + _pick helper 兼容顶层/agent

## [1.5.4] - 2026-07-07

## [1.5.3] - 2026-07-07

### Added

- feat(presets): stop_mode → policy (v4 goal schema 对齐, 4 档 preset)

### Fixed

- fix(auto-nn-update): inline Python goal 字段走 load_nn_config + v4 schema (target/per_scenario)

### Changed

- (compat: presets.py 4 档仍含 deprecated v3 value/metric/op 字段,下轮清理)

## [1.5.2] - 2026-07-07

### Changed
- docs(PROTOCOL): §6 step 7 KEEP 段镜像去重 — 内容合并至 §2.1 keep_threshold(KEEP 流程细节)

## [1.5.1] - 2026-07-07

### Added
- docs(spec): MA-1 正式定义 §7.4a (brainstorm 2026-07-07)
- docs(plan): MA-1 §7.4a 实施计划(3 task, doc-only)
- docs(PROTOCOL): §7.4a 数值分析段(MA-* Metric Analysis) — MA-1 brief-oneline 正式定义

## [1.5.0] - 2026-07-07

### Added

- feat(nn-config): Phase 2 collapse — 207→~31 行, 14 段走 preset 注入
- feat(lib): load_nn_config() preset expansion — 缺段自动注入(exploration.style 选 preset)
- feat(lib): presets.py — 4 档 preset 默认值(14 段,conservative/balanced/aggressive/inductive)

### Changed

- refactor(scripts): set-scenario-policy / wait-train / nn-doctor → load_nn_config()

## [1.4.4] - 2026-07-07

### Added

- feat(nn-doctor): check_PDH_plain_anchor adds round=1 routine WARN (BAS active trigger parity)
- feat(pdh): _emit_plain_anchor_init adds round==1 FIRST-ROUND marker (active BAS path)

### Fixed

- fix(pdh): build_run_context injects ctx['run'] — enables _pdh_bas_first_round active branch (sandbox E2E caught)

## [1.4.3] - 2026-07-07

### Added

- feat(abcde): heuristic modifier_examples 推导从 init-qa-log
- feat(pdh): _pdh_bas_first_round() helper — round==1 主动触发判定 (5 scenarios)
- feat(pdh): _emit_plain_anchor_init round==1 显式标注（active BAS path）
- feat(nn-doctor): check_PDH_plain_anchor round=1 例行 WARN（BAS active trigger parity）

### Fixed

- fix(bump-version): tag 改 annotated——--follow-tags 才会真推 tag
- fix(pdh): build_run_context 注入 ctx["run"]，使 _pdh_bas_first_round 在真实集成路径下激活（沙箱 E2E 捕获）

## [1.4.2] - 2026-07-07

### Changed

- refactor(gate): extract _LEVEL_PATHS canonical mapping in check_abcde_boundaries

### Fixed

- fix(explore): is_migration_in_progress archive 反向读取 + verify 自动归档 CHECKLIST
- fix(bump-version): release-check cross-repo isolation via RELEASE_CHECK_ROOT

## [1.4.1] - 2026-07-07

### Changed

- refactor(sandbox): dry-convergence — 收缩本仓对沙箱仓知识面至「3 slash + 一句话」

## [1.4.0] - 2026-07-07

### Changed

- refactor(sandbox): strip sandbox/ to independent repo sandbox-auto-nn v1.0.0
- refactor(sandbox): 沙箱副本 = 业务仓 cp 语义改写 + CLAUDE.md 关键叙述
- refactor(sandbox): clarify 模版仓 vs 业务仓副本 boundary + slash 注入 in 3 原则
- refactor(sandbox): replace 铁律 0/1/2 with new 3 原则 model

## [1.3.0] - 2026-07-07

### Added

- feat(config): nn-config.yaml.exploration.mode schema 升格注释（创新维默认上限）
- feat(init): init_abcde.py F1.5 一次性脚本（仿 init_watchlist.py 模式）
- feat(sandbox): sandbox-test.yaml 启用 check_abcde_artifacts.py 路由校验
- feat(sandbox): sandbox-registry 9 业务仓补 init_entry/init_scenario/abcde_boundaries/init_ts
- feat(run): auto-nn-run.sh 每轮末调 check_ABCDE_boundaries（仿 PDH/ledger-watchlist 模式）
- feat(doctor): nn-doctor.sh inline check_ABCDE_boundaries() 仿 check_ledger_watchlist 模式
- feat(run): build-run-context._render_abcde_boundaries_suggestion() 仿 _render_watchlist_suggestion
- feat(skill): SKILL.md HR1-HR3（Re-init H 段变体）
- feat(skill): SKILL.md HA1-HA3（Adapter H 段变体）
- feat(skill): SKILL.md O3-ABCDE 三选项（A 默认 / B 自定义 / C 宽松）
- feat(init): new-project.sh 调 init_o3_abcde.write_init_outputs() 写 boundaries.yaml + init-guidance.md
- feat(init): new-project.sh 4 场景路由 + _adapter_ask_strategy + _update_reinit_config

### Changed

- refactor(template): remove stale inline tests/ directory (10 files, 77 tests)

### Fixed

- fix(config): nn-config.yaml 升格注释加 conservative 行 + 标 planned mapping
- fix(scripts): governance-sync.sh — echo init_abcde in ABCDE 组 summary line
- fix(init): init_abcde.py — remove dead template_root var + trailing newline
- fix(sandbox): check_abcde_artifacts — enforce init_scenario cross-check + DRY cfg + trailing newline
- fix(run): auto-nn-run.sh abcde_boundaries check — mktemp + trap + multi-violation
- fix(run): _render_abcde_boundaries_suggestion — read boundaries.* + use real schema fields
- fix(init): Task 2 boundaries write — wrap with if/then/else (set -e safe) + clarify missing-template warning
- fix(bump-version): 5-step gate skipped after root scripts/ symlink removal

## [1.2.1] - 2026-07-06

## [1.2.0] - 2026-07-06

### Added

- feat(scripts): init_watchlist.py — F1.5 一次性迁移 (仿 migrate_agent_keys 模式)
- docs(skills): 6 SKILL.md touchpoint — ledger carve-out + Modify-L1 retarget + watchlist suggest
- docs: ledger-watchlist 1.2.0 端到端沙箱首跑记录

### Changed

- chore(r25): register init_watchlist.py + governance-sync cp (Task 10 wiring fix)

注：ledger-watchlist 主体改动（`feat(profiles)` / `feat(experiment)` / `feat(lib)` / `feat(build-run-context)` / `feat(nn-doctor)` / `test(regen)`）在 v1.1.1 发布周期中合并但未归入 v1.1.1 CHANGELOG；功能行为以本版为准。

## [1.1.1] - 2026-07-06

### Fixed

- fix(new-project): 业务仓 init 后 CHECKLIST.md 自动移到 `.auto-nn/migration-completed-checklist-<ts>.md`（业务仓根目录不再保留；is_migration_in_progress glob 兼容无回归）

## [1.1.0] - 2026-07-06

### Added

- feat(pdh): Plain-Discovery Heuristic v2 (PDH) — 6 原则自悟 plain baseline，零业务负担
- feat(pdh): BAS trigger (first round) — RUN CONTEXT 注入 `### plain-anchor-init` 段
- feat(pdh): WPL trigger (plateau / 切场景 / fancy<plain) — RUN CONTEXT 注入 `### plain-anchor-check` 段
- feat(pdh): build-run-context 4 helper (state / WPL detector / BAS emit / WPL emit)
- feat(pdh): EXPERIENCE Tier 矩阵第 5 列 `plain(P)` — 触发轮必填 4 字段（anchor / recipe / budget / why）
- feat(pdh): nn-doctor 加 `check_PDH_plain_anchor` sub-check 1e — 触发轮校验 P 行字段

### Changed

- feat(pdh): PROTOCOL §6 step 1/5 镜像 BAS / WPL trigger 段（base-prompt ↔ §6 双向同步）
- feat(pdh): auto-nn-run.sh base-prompt step 0c BAS 锚 + step 5 WPL 锚 + 6 原则全文


## [1.0.1] - 2026-07-06

### Added

- feat(skills): add /bump-version quick reference to CLAUDE.md
- feat(bump-version): parse_args + git/VERSION/tag detect + bump infer + CHANGELOG update + release-check gate
- feat(skills): bump-version SKILL.md — 入口 + 流程指引

### Changed

- refactor(template-meta): drop 8 root symlinks + 1 broken (mirror mechanism root elimination)
- refactor(template-meta): rewrite root CLAUDE.md to maintainer view (305 -> 40 lines)
- refactor(auto-nn-run): RUN CONTEXT 注入段瘦身 — 删 9 行并行能力重复段

### Fixed

- fix(bump-version): CHANGELOG 3-section alias bug + regression test
- fix(skills/reflect): cross-file typo tried/not_tried → attested/not_attested
- fix(template): 撞墙信号 best_tsv_row fallback + exp_dir 反自比
- fix(auto-nn-run): typo tried/not_tried → attested/not_attested (TAM 字段对齐)
- fix(auto-nn-run): P1-3 journal_uncommitted_warns auto-commit
- fix(auto-nn-run): P1-1 删段 8 ABCDE 2nd 真重复
- fix(auto-nn-run): P1-2 删段 11 并行能力 前置重复
- fix(reflect): P0-1 N1 LLM contamination propagation 3 guards

## [1.0.0] - 2026-07-06

### Changed

- BREAKING: version gate now enforces major-bump contract (--accept-major-bump required for major version upgrades)

## [0.2.0] - 2026-07-06

### Added

- End-to-end version mgmt test (init -> minor bump -> update)

## [0.1.0] - 2026-07-06

### Added

- Initial release of `auto-nn-experiment` template (semver + governance-rev)
- `scripts/auto-nn-init` / `auto-nn-update` governance sync flow
- `ExperimentBase` framework + `contract/` / `workspace/` two-class split
- ABCDE/v4 minimal `nn-config.yaml` (31 keys)

