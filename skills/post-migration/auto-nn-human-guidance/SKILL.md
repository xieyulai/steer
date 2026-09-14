---
name: auto-nn-human-guidance
description: >-
  人类路线图代写通道：把人的自然语言意图收成合规 HUMAN_GUIDANCE 并落盘（Write+validate+commit）；
  固定代写步骤；实验轮 Agent 禁改此文件。清空：dry-run 后用户确认再 --apply。
  NL: 改路线图|roadmap|human guidance. NOT: 改goal→goal.
---

## Code Contract（pilot，2026-07-15）

> `scripts/check_skill_contract.sh` 自动对账本段与 `template/package/*` 实际符号。
> 失败 → release-check 第 6 步门禁拦截。
> **强检字段**（对账失败即拦截）：`calls_scripts` / `reads_cfg_keys` / `env_vars_consumed`；其余（`pluggable_symbols` / `referenced_gates` 等）为 informational，release-check 不强检。

```yaml
calls_scripts:
  - scripts/human_guidance_gate.py        # batch-hint / check / refresh / post-round-enforce
  - scripts/clear-human-guidance-roadmap.sh  # dry-run / --apply 清空路线图
  - scripts/validate-human-guidance.sh    # 改后 validate
  - scripts/refresh-human-guidance-baseline.sh  # drift 恢复（batch 活跃禁用）
  - scripts/append-skill-activity.py      # Agent 会话活动 log（end phase）

reads_cfg_keys:
  - agent                                  # 父键（含 .skill_activity_log）
  - agent.skill_activity_log               # 活动 log 开关（默认 true）

env_vars_consumed:
  - NN_AUTO_RUN_ROUND                      # post-round-enforce 轮次（human_guidance_gate.py）
  - NN_GUARD_HUMAN_GUIDANCE                # 加固开关（lib default 1；G-HUMAN-COMMIT 路径）

referenced_gates:                          # 仅 informational，lint 不强检
  - G-HUMAN                                # preflight FAIL：Agent 写 HUMAN_GUIDANCE 拦截
  - G-HUMAN-COMMIT                         # 轮末 post-round-enforce / baseline revert
  - validate-human-guidance                # 自定义 路线图 结构校验（阶段/目标/完成条件）
```

# auto-nn-human-guidance — 人类路线图

权威规则：`PROTOCOL.md` §7.5。

**边界**：train / auto-run → `/auto-nn-manual-run` / `/auto-nn-auto-run`；只读诊断 → `/auto-nn-analyse`

## 高频代号（人话见 glossary）

| 内部码 | 对用户怎么说 |
|--------|--------------|
| `路线图` / 空路线图 | 分阶段的目标计划 / 不设计划，全自主 |
| `G-HUMAN` / `baseline` | 路线图保护：防跑着被偷改 |
| `drift` | 路线图被改得和批次启动时不一致 |
| `batch` | 多轮自动跑 |

## 何时使用

- 用户要写 / 改 **分阶段路线图**
- 用户要 **清空路线图**（改走 Agent 全自主）
- **不要**用于手跑 train 或 `./auto-nn-run.sh`

## Agent 开场（必做）

- [ ] **批次活动软提示**（不阻断，exit 0）：

```bash
python3 scripts/human_guidance_gate.py --repo-root . batch-hint
```

- [ ] 若 stderr 含 `[human-guidance] WARN`：**原样告知用户**——先停 auto-run / 训练，再改 HUMAN；改完 validate → commit → 重开 batch。**batch 活跃时禁止** `refresh-human-guidance-baseline.sh`（见 PROTOCOL §7.5.3）
- [ ] **禁止**因 WARN 而拒绝执行本技能；也 **禁止**在 batch 运行中代用户 `--apply` 清空

## 允许修改范围

- **本技能可改**：`HUMAN_GUIDANCE.md`（`## 公平约束` 与/或 `## 路线图`；Write + validate + commit）
- **禁止改**：`EXPERIENCE.md`、`references/`、`contract/`、`train.py`、`workspace/`

## 代写过程（本技能主责 · 必遵）

**一句话**：人出意图 → 本技能代写成合规正文 → **本技能写入** `HUMAN_GUIDANCE.md` → validate → commit。  
人**不必**手改或粘贴文件。实验轮 / auto-run Agent **禁止**改该文件；**只有**本技能会话（用户显式 `/auto-nn-human-guidance` 或等价意图）可以写盘。

### 标准步骤（每次一样）

| 步 | 谁 | 做什么 |
|----|-----|--------|
| 0 | Agent | `batch-hint`；有 WARN → 告知先停训/停 batch，**停稳前不写盘** |
| 1 | 人 | 自然语言说意图 |
| 2 | Agent | 收成定稿（见格式）；意图不清时用**一句**确认，清楚则直接落盘 |
| 3 | Agent | **Write** `HUMAN_GUIDANCE.md`（按意图改 `## 公平约束` 和/或 `## 路线图`；保留未改节） |
| 4 | Agent | `bash scripts/validate-human-guidance.sh`；FAIL 则改文件直到 OK |
| 5 | Agent | `git add HUMAN_GUIDANCE.md` + commit（中文说明意图） |
| 6 | Agent | `append-skill-activity`（phase=end）；若曾开 batch，提醒重开以刷新基线 |

**禁止**：让人「自己贴一段」；用 `git apply` 假装没 Write；实验轮 / auto-run / analyse 会话里改本文件。

### 代写质量（正文规范）

**硬规则：用户说什么只写什么。** 禁止用 PROTOCOL / 模板默认 /「常见公平约束」清单去补全用户没点名的项。

1. **路线图阶段**：是什么 / 目标 / 完成条件；NOTE 可选且极短（下一步一句）。用户只改某一阶段时，**只动该阶段**，其余阶段原样保留。  
2. **公平约束**（若有）：写在文首 **`## 公平约束`**，与路线图**并列、无关**。  
   - **增量改**：用户只提一条（例：「ep=200」）→ 公平约束里**只增/改这一条**（可写成 `- **ep = 200**：正式实验 cfg \`EPOCHS\` = 200`），**禁止**顺带写 KEEP、GPU、数据切分、禁刷种子等用户未说的内容。  
   - **全量重写**：仅当用户明确说「重写公平约束 / 换成这些」并给出条目列表时，才整节替换为用户给出的条目。  
   - 细则长文外链 `docs/`，不在 HG 里展开。  
3. **禁止**：把公平口径塞进阶段 NOTE；把实测曲线、打勾日记塞进 HG；标题带「当前/进行中」；**禁止「发挥」**（从源 README / PROTOCOL / 旧仓抄一长串「标准公平约束」）。  
4. **一次意图 → 落盘定稿**；须写盘+校验，禁止只聊天不交稿。  
5. 改公平约束或改路线图均可；两者独立更新，互不要求同阶段。

**坏例**：用户说「加 ep=200」→ 写成 KEEP 0.1% + 三项指标 + 禁刷种子 + GPU 2/3 + 数据 5万/1万。  
**好例**：用户说「加 ep=200」→ 公平约束仅一行（或仅改已有 ep 行），原有其它用户条目保留不动。

### 与「实验 Agent 禁写」的关系

| 场景 | 可否改 `HUMAN_GUIDANCE.md` |
|------|---------------------------|
| `/auto-nn-human-guidance`（本技能） | **可以**（代写落盘） |
| auto-run / manual-run 实验轮 | **禁止**（路线图保护） |
| analyse / doctor / modify 等 | **禁止** |

## 文件结构（两块并列）

```markdown
# 人类指导（Human guidance）

> 意图归人；经 `/auto-nn-human-guidance` 代写落盘。…

## 公平约束

（可选；与路线图无关。**用户说什么只写什么**，勿补全模板默认项。）
- **ep = 200**：正式实验 cfg `EPOCHS` = 200

## 路线图

### 阶段 N — <短名>

- **是什么**：…
- **目标**：…
- **完成条件**：…
- **NOTE**：…（可选，极短）
```

| 块 | 职责 | 不放什么 |
|----|------|----------|
| **`## 公平约束`** | 跨阶段的比较口径与禁止项（可长期不变） | 阶段进度、下一步、实测日记 |
| **`## 路线图`** | 分阶段战略（是什么/目标/完成条件） | 公平口径正文（应在上一节） |

无 `## 公平约束` = 不设文档级比较锁（仍可全自主或只靠路线图 NOTE）。  
无 `### 阶段` = 空路线图（全自主阶段推进）。

## 路线图格式（每阶段）

```markdown
### 阶段 N — <短名>

- **是什么**：…（一句）
- **目标**：…（一句）
- **完成条件**：…（未完成的可观察项；人话）
- **NOTE**：…（可选；仅下一步/临时提示）
```

**禁止**：`## 生效中`、`## 历史`、标题状态（进行中/待启动/当前）、`reflect:`；**禁止**在阶段里再开「公平约束」字段（口径只在文首 `## 公平约束`）。

## 清空路线图

用户说「清空 guidance / 全自主 / 不要路线图」时走本流程。

### Agent 必做

- [ ] 确认意图：**仅清空战略约束**，不清 TSV / EXPERIENCE / keeper
- [ ] 代跑 dry-run（**禁止** `--apply`）：

```bash
bash scripts/clear-human-guidance-roadmap.sh
```

- [ ] 输出 **《清空计划》**（见下）
- [ ] 提示用户本地执行 `--apply` 后再 `validate-human-guidance.sh`

### 《清空计划》格式

```markdown
## 路线图清空计划

- **目标**：恢复空路线图 → Agent 全自主
- **将改动**：`HUMAN_GUIDANCE.md`（备份为 `.bak`）
- **将保留**：`_runs/`、`EXPERIENCE.md`、`saved/keepers.json`、代码与 contract
- **清空后**：auto-run 不再注入路线图；探索依 EXPERIENCE Tier + `nn-config.agent.exploration`

### 用户执行（须本地）

bash scripts/clear-human-guidance-roadmap.sh --apply
bash scripts/validate-human-guidance.sh
```

可选：`--no-backup`（仅当用户明确不要 `.bak`）

### 与 `/auto-nn-clear` 区别

| | human-guidance 清空 | clear C6 factory |
|--|---------------------|-------------------|
| 范围 | 仅 `HUMAN_GUIDANCE.md` | 台账 + EXPERIENCE + reflect + keeper 等 |
| 破坏性 | 低 | 高 |
| 用途 | 战略结束、改全自主 | 绿场重来 |

factory 若需空路线图，C6 实现后应调用同一空模板；**日常清空只用本脚本**。

## 编辑路线图自检

- [ ] 比较口径在文首 **`## 公平约束`**（若有），不在阶段字段里
- [ ] **公平约束条目 ⊆ 用户本轮点名项**（无擅自补 KEEP/GPU/数据等）
- [ ] 每阶段有 **是什么 / 目标 / 完成条件**；NOTE 无长文
- [ ] 未写 reflect / 状态标记（含标题「当前」）
- [ ] 探索阶段含 **探索网格** 或 **场景顺序**（仅当用户意图含探索摸底时）
- [ ] `bash scripts/validate-human-guidance.sh`

## F1 → 探索 NOTE handoff（迁后摸底）

1. **先**完成 `CHECKLIST.md` / `verify-migration-complete.sh`（迁移中 `doctor` 强制 `optimize`）
2. 在 F1 场景清单就绪后，写 **阶段 1 — 摸底** NOTE：
   - `- **objective**: explore`
   - **探索网格** / **场景顺序** / **证伪清单** / **禁止**
3. 可选仓级默认：`nn-config.yaml` → `agent.objective_mode: explore`
4. `validate-human-guidance.sh` → **`/auto-nn-auto-run`** 或 manual-run

## 优先级

```text
HUMAN_GUIDANCE（公平约束 + 路线图 / inferred phase NOTE）> REFLECT_INDEX pending > EXPERIENCE
```

与 `nn-config.agent.exploration` 冲突时，**非空路线图**以 NOTE Tier 为当前阶段硬约束。

## 改路线图后（auto-run 曾运行 / 将运行）

1. **本技能已 Write + validate + commit** 后：若 batch 曾开过 → **重开** `./auto-nn-run.sh`（新基线）。  
2. **drift 已发生、batch 已停**：`git checkout <baseline.git_head> -- HUMAN_GUIDANCE.md`（见 `saved/.human-guidance-baseline.json`），再经本技能重写意图或恢复后重开。  
3. **禁止**：batch 活跃时 `refresh-human-guidance-baseline.sh --apply` / `human_guidance_gate.py refresh`。

## 下一步常见推荐

看在第几阶段 → **`/auto-nn-analyse`**；手跑一轮 → **`/auto-nn-manual-run`**；多轮 → **`/auto-nn-auto-run`**；绿场清台账 → **`/auto-nn-clear`**。完整串联图见 [`skills/post-migration/README.md`](../README.md)。清空时 **勿**代用户 `--apply`（清空仍须人确认后本地 `--apply`）。

## 对用户怎么说（人话）

- **本技能在干什么**：「你说意图，我按你的话写成合规 guidance 并落盘；不擅自加条款。」
- **公平约束**：条目与用户说法一一对应；禁「发挥」成一整套标准锁。
- **路线图**：用「阶段 N：在做什么 / 目标 / 完成条件」；完成条件写人话，禁内部条件码。
- **空路线图**：「不锁阶段计划，Agent 全自主探索」。
- **还在训练时**：「先停训练/自动跑，停稳了我再改路线图。」
- **禁止**让用户自己粘贴正文。

**坏**：甩一段 diff 让人自己贴；或实验轮里改 HUMAN。  
**好**：「已按你的意图写入 HUMAN_GUIDANCE.md 并校验通过、已提交。」

## 活动 log

落盘并 validate 通过后，Agent **须** append：`python3 scripts/append-skill-activity.py append --skill auto-nn-human-guidance --phase end --summary "路线图阶段 N"`。开关 `agent.skill_activity_log`（默认 true）。
