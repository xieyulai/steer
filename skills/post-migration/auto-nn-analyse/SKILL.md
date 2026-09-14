---
name: auto-nn-analyse
description: >-
  迁后台账只读分析：silent doctor + analyse_metrics + analyse_delta/code_delta、
  summarize-runs、路线图进度、进一步建议、EXPERIENCE、Tier 趋势；台账 cfg 缺口与
  NEED_MODIFY。禁止 train/reflect/改代码/HUMAN_GUIDANCE。结束时 journal_append analyse --apply；
  改题待办三选一后可 e_feedback resolve。结束时推荐 auto-nn-* 下一步。
  NL: 分析|撞墙|plateau|what next. NOT: 只看几行→check.
---

# auto-nn-analyse — 迁后台账只读分析

权威规则：指标与 KEEP 见 `PROTOCOL.md` §6–§8；路线图见 §7.5。

**台账行语义：** 主 TSV/jsonl **1 行 = 1 次实验（槽位）**，不是 1 轮编排；多槽并行时一轮可追加多行。成绩表按**实验行**扫；**轮次进度**读 `saved/round_decision.json` / EXPERIENCE / 实验名 `_sXofN_` 分组——**勿**把 TSV 行数或行数增量当「第几轮」。

**本技能只诊断，不执行训练/改码。** 结束时必须在回复中 **推荐** 至少一个 `/auto-nn-*` 下一步；**须** `journal_append --event analyse --apply` 写入游标与建议；**须** `append-skill-activity --phase end`。允许的写盘仅两项：`journal_append --apply`，以及人已明确三选一时的 `e_feedback.py resolve`。

## Code Contract（pilot，2026-07-15）

> `scripts/check_skill_contract.sh` 自动对账本段与 `template/package/*` 实际符号。
> 失败 → release-check 第 6 步门禁拦截。
> **强检字段**（对账失败即拦截）：`calls_scripts` / `reads_cfg_keys` / `env_vars_consumed`；其余（`pluggable_symbols` / `referenced_gates` 等）为 informational，release-check 不强检。

```yaml
calls_scripts:
  - scripts/nn-doctor.sh                  # silent doctor 前置（仅 WARN/FAIL）
  - scripts/runtime-activity.py           # 活跃/空闲判定（→ NN_AUTO_RUN_ACTIVE）
  - scripts/analyse_metrics.py            # Layer A 数值（MA-1..7/R 蒸馏）
  - scripts/analyse_delta.py              # Layer B TSV 增量
  - scripts/analyse_code_delta.py         # Layer B 代码增量（CD-WARN）
  - scripts/summarize-runs.py             # 台账门禁 / keeper / roadmap / reflect-brief
  - scripts/journal_append.py             # 写 journal（必做，含 --apply）
  - scripts/e_feedback.py                 # 改题待办：pending 只读 / 人三选一后 resolve
  - scripts/compress-experience.py        # EXPERIENCE 体积过大时建议（SUGGEST_COMPRESS）
  - scripts/append-skill-activity.py      # 活动 log（end 必做）

reads_cfg_keys:
  - agent.analyse_recent_rows             # MA-1 蒸馏窗口
  - agent.analyse_aux_max                 # MA 辅助指标上限
  - agent.analyse_flat_pct                # plateau 判读阈值
  - agent.analyse_noise_std_hint          # 噪声提示阈值（可选）
  - agent.experience_compress_min_lines   # 触发 SUGGEST_COMPRESS 的行数阈值
  - agent.skill_activity_log              # 活动 log 开关
  - agent.plateau_rounds                  # plateau 判读阈值（嵌套）
  - exploration_mode                      # 6 档 mode 校验（v1.21+）
  - goal                                  # goal.target / per_scenario / policy（v4 schema）
  - keep.improve_mode                     # KEEP 口径（嵌套 keep_cfg.get）
  - keep.primary_delta                    # KEEP 口径（嵌套）
  - keep.mode                             # KEEP 口径（嵌套）
  - keep.near_best_abs                    # KEEP 口径（嵌套）
  - ledger                                # ledger.watchlist 等只读访问

env_vars_consumed:
  # analyse 仅诊断不执行；本技能不直接读 NN_*
  # 下列由本技能调用的脚本间接读取（属 transitive 副作用）：
  - NN_AUTO_RUN_ACTIVE                    # runtime_activity 判定 auto-run batch
  - NN_REFLECT_FORCE                      # run_ledger_summary 一次性 env
  - NN_REFLECT_SKIP                       # run_ledger_summary 一次性 env
  - NN_EXPERIENCE_AUTO_COMPRESS           # experience_auto_compress 联动

referenced_gates:                          # 仅 informational，lint 不强检
  - G-cfg-no-defaults
  - G-no-fallback
  - G-repro-env
  - G-repro-cli
```

## 活动 log

报告前可读近期轨迹：`python3 scripts/append-skill-activity.py recent --limit 15 --format markdown`  
结束时：`append-skill-activity.py append --skill auto-nn-analyse --phase end --summary "…"`（开关 `agent.skill_activity_log`，默认 true；见 [`README.md`](../README.md)）

## 高频代号（人话见 glossary）

| 内部码 | 对用户怎么说 |
|--------|--------------|
| `MA-1` | 最新一轮 vs 历史最好的对比 |
| `MA-3 / MA-6 / MA-R` | 新增量 / 上次建议是否兑现 / 上次反思是否兑现 |
| `MA-7` / `plateau` | 撞墙、连续多轮没提升 |
| `Tier A–E` | 实验成熟度档位（现为二维：字母档 × routine/derived/different；novel 仅盖章） |
| `Innovation` / 探索深度 | routine（经典现成）/ derived（论文级/成熟组合；旧称 extend）/ different（自研结构层）；`novel` = different ⊕ 文献背书（仅 reflect 盖章，非日常三选） |
| `exploration_space` | 本轮探索格子（学习率/模型/目标/数据 × 深度；成绩表只记 A–D） |
| `e_feedback` / 改题待办 | 改题主张另记；对人说「改题待办 / 待审改题」 |
| `pending` / `adopted` / `rejected` / `deferred` | 待审 / 留下（只建议） / 驳回（不再提类似） / 搁置（下次可再提） |
| `keeper` / `leader` | 当前最好结果 / 当前领跑实验 |
| `criteria_met` | 当前阶段完成条件是否达成 |

**数值只出现一次**：数值层给数字（蒸馏自 `analyse_metrics` / `summarize-runs`），结论层只判读不复述数字，下一步层只给动作。过程/编码码按下方「人话翻译」表处理。

## 对用户怎么说（人话）

本技能报告须 **三层**：① 数值（2–3 行）② 结论（判读）③ 下一步（推荐 `/auto-nn-*`）。细则见下节 **人话翻译** 与文末禁止项。

- **贴 MA / summarize 脚本输出前**：一句人话结论（例：「最近 3 轮没破最好，主指标卡在 0.82」）。
- **chat 里禁整块 MA 标签**；全量进 journal，用户只看蒸馏结论。
- **Tier / plateau / keeper**：用「成熟度档 / 撞墙 / 当前最好」；字母档 A–E 非必要不出现。
- **doctor-diff**：只报新增/恶化项，每项「人话（检查原名）」一次。

**坏**：「MA-1 beat_best=false plateau_streak=3；建议升 Tier B-routine」  
**好**：「最近 3 轮没破历史最好。建议下轮试学习率或换 backbone；详细分析已记入 journal，对话里只说结论。」

## 人话翻译

输出用人话。**过程/编码类术语禁裸用**（必须翻译或省略），**领域术语保留**（用户本就懂）。首次出现可「人话（原名）」一次，之后只用人话。

| 过程/编码术语（禁裸用） | 人话 |
|---|---|
| `MA-1/3/6/7/R` | 不出现码：直接说「数值」/「新增」/「上次建议兑现」/「撞墙」/「上次反思兑现」 |
| `Δ` / `Δ%` / `Δleader` | 「提升 +0.03%」/「下降 -0.6%」；不用 Δ 符号 |
| `beat_best` | 「破纪录」/「未破纪录」 |
| `keeper` / `leader` | 「当前最好」/「当前领跑」 |
| `KEEP` / `DISCARD` | 「保留」/「作废」 |
| `Tier A–E` / `Tier C fail-safe 第 N 分支` | prose 不留字母档：「成熟度档」/「第 N 个备选方向」；提及升档时须说明具体深度（routine/derived/different；novel 盖章另说） |
| `Innovation` | routine/derived/different 深度（经典 vs 论文级 vs 自研结构）；novel 说「反思盖章」 |
| `e_feedback` / `pending` | 「改题待办」/「待审改题 N 条」；禁裸抛内部状态码 |
| `mechanism swap` / `mechanism 空间收窄` | 「换了核心机制」/「能试的方向快用完了」 |
| `criteria_met=plateau` | 「阶段完成条件已达成」 |
| `plateau_streak=N/3` / `rounds_since_reflect=N` | 「连续 N 轮无提升」/「距上次反思 N 轮」 |
| `reflect gate=... trigger=yes` | 「触发反思条件=是」（gate 码不出现） |
| `verdict=flat/refuted/inconclusive` | 「无效」/「被证伪」/「待定」 |
| `finalize_round` / `workspace reverted` | 「收尾」/「已回退改动」 |
| `TAM ...` | TAM 码不出现；必要时「首次真正实施」 |
| `focus 场景` / `scenario_id` | 「当前关注场景」 |
| `test_loss +X% rel 倒退` | 「测试损失涨 X%」 |
| doctor 检查名（`G-cfg-no-defaults` 等） | 仅在需操作的「新增/恶化」项里给「人话（原名）」；计数行不展开 |
| `env_runtime` / `contract_sanity` | 「运行环境未就绪（常见：poetry install）」/「contract 微测未过」 |

## 何时使用

- 「帮我看 TSV」「为什么 N 轮没提升」「在第几阶段」「该不该继续因子/升架构」
- 用户**尚未**要求 train、reflect 或改 `HUMAN_GUIDANCE`
- **不要**用于：手跑一轮 → `/auto-nn-manual-run`；多轮 auto-run → `/auto-nn-auto-run`

## 执行顺序（必做，严格按序）

### 0. 结构前置：silent doctor

```bash
bash scripts/nn-doctor.sh --quiet
```

- stdout 空且 exit 0 → 不写 `## 结构前置`
- 有 WARN/FAIL → 输出 `## 结构前置（doctor --quiet）`
- 任一 FAIL → 策略结论标注 **待结构修复后有效**

**doctor diff（机制 A，零脚本改动）**：
- 把 `nn-doctor --quiet` 归一为 canonical 快照（每行 `检查名<TAB>状态[<TAB>计数]`）。
- 与 `saved/doctor_last.txt`（上次快照）逐项比对。「结构（体检）」层**只报新增/恶化项**（新出现 / 状态变坏 / 计数升高），逐条用「人话（原名）」给出；其余写计数行「N 项已知无变化（X 失败 + Y 警告）→ journal」。
- 无新增/恶化 → 「0 新增 / N 已知无变化」。
- 全量 doctor 输出进 journal。
- 结束时把本次 canonical 快照**覆盖**写入 `saved/doctor_last.txt`。首次无快照 → 全表 + 标注「首次，无基线」。

**题面保护（`contract/` 源文件）**：常规迭代禁改 `contract/`（PROTOCOL 级约定，非 doctor 门禁）；reinit 场景可重审（须显式签字 + CHANGELOG 留 `BREAKING`）。`abcde_boundaries` doctor 检查已于 v1.16.0 退役——analyse 不实现题面门禁，doctor diff 链路也不再产出 abcde_boundaries 项。

### 0b. 运行态（auto-run / 训练）

```bash
python3 scripts/runtime-activity.py --repo-root . --format markdown
```

- **无输出**（空闲）→ 不写 `## 运行态`
- **有输出** → 粘贴 `## 运行态` 块；**`## 结论`** 须含 1 bullet：台账可能未闭合，勿并行改代码/开新训
- doctor `--quiet` 亦含 `runtime_activity` 行（WARN 时可在结构前置一并提及）

### 1. 数值摘要（Layer A，必做，在 summarize 之前）

```bash
python3 scripts/analyse_metrics.py --repo-root . --since-analyse --quiet
```

**默认 `--quiet`**：脚本**开头必含** `## 基线尺子 (baseline anchors)`（plain / reference 有无 + 缺口建议）+ **MA-1** 蒸馏为「数值」层 2–3 行（当前最好 / 最近一轮 + 提升%，值逐字引用脚本，**禁手算**）；MA-3/6/7/R 的判读浓缩进「结论」bullet。**不**贴 MA-2/4/5 与 skip 类 stderr，也不整块贴 MA 输出进 chat（全量进 journal）。

**基线尺子（必读进结论）**：
- 缺 **plain** → 结论须写「还没立朴素下界」；下一步点名 `/auto-nn-plain`。
- 缺 **reference** → 结论须写「还没立公开对照」；需要时点名 `/auto-nn-reference`（满 10 轮 auto 会自己催；勿把异协议论文分当上界）。
- 两尺都有 → 一句「尺子已立，可对照靶子归因」即可，不必展开。

需要全量 MA 块（调试）时去掉 `--quiet`。

**禁止**手算 Δ、Δ%、plateau、beat_best；解读 MA 块即可。

### 2. 增量边界 + 代码规范（Layer B，仅异常时输出）

```bash
python3 scripts/analyse_delta.py --repo-root . --quiet
python3 scripts/analyse_code_delta.py --repo-root . --quiet
```

- **无新 TSV 实验行、无 git 增量、无 CD WARN** → **整节省略**（不输出「无新行 / SKIP」）
- 有内容时：`## 异常与增量` 下只贴 **有信息** 的小节；CD **WARN 原样**（CD-1～CD-5）

### 3. 台账门禁（一行，不贴全表）

```bash
python3 scripts/summarize-runs.py --repo-root .
```

从 brief 提取并写入结论：**leader / last / plateau_streak / reflect 门禁**。  
**仅当** keeper 跨场景明显不对齐或多场景需对照时，再跑 `--keeper-status` 并只贴 **focus 场景 ± 异常行**。

### 3b. REFLECT 建议摘要（必做）

```bash
python3 scripts/summarize-runs.py --repo-root . --reflect-brief
```

输出 `### REFLECT-BRIEF`：INDEX **pending** + 近 3 条已消费历史。**只读**；粘贴或摘要进 `## 结论`（与 MA-R 配对，见下）。

### 4. 路线图进度（空路线图则跳过阶段块）

```bash
# 公平约束（文首节；有则贴进报告）
python3 -c "
from pathlib import Path
import sys
sys.path.insert(0, 'scripts')
from lib.human_guidance_roadmap import fair_constraints_section_body
b = fair_constraints_section_body(Path('HUMAN_GUIDANCE.md').read_text(encoding='utf-8', errors='replace'))
print(b if b else '(无公平约束节)')
"
python3 scripts/summarize-runs.py --repo-root . --roadmap-status
```

若有公平约束正文，报告中单独一小节「公平约束」粘贴；若 `roadmap: empty`，写一句「空路线图，阶段全自主」并跳过路线图进度块（公平约束仍报）。

否则输出：

```text
## 路线图进度
- （粘贴 --roadmap-status 输出）
- 与人话「完成条件」对照（1–2 句）
- 证据：TSV **实验行**（1 行=1 槽；注意 **`scenario_id` 列**） / **分场景** `saved/keepers.json`
```

### 5. 只读清单

- [ ] `HUMAN_GUIDANCE.md`（`## 公平约束` + `## 路线图`）
- [ ] `references/REFLECT_INDEX.md`（`## 待消费` 若有；**REFLECT-BRIEF 已脚本化**，勿通读 EXPERIENCE `[反思]` 找建议）
- [ ] `_runs/results.tsv`、`EXPERIENCE.md`（**二维 `## Tier 状态` 矩阵** + 近期实验的 `innovation_depth` / `innovation_rationale`）
- [ ] **`saved/keepers.json`**（按 **`scenario_id`** 的 map）
- [ ] `contract/__init__.py`、`nn-config.yaml`（只读）
- [ ] 可选 `saved/innovation_audit.json`（上一轮 reflect 的轻量审计结果）
- [ ] **`saved/experiment_journal.json`**（只读；MA-6 / MA-R / 增量游标）
- [ ] **`_runs/analysis/e_feedback.jsonl`**（改题待办；`python3 scripts/e_feedback.py pending`；结论层必报）

## 改题待办（必读 + 人点名才问）

1. **每轮 analyse 必跑** `python3 scripts/e_feedback.py pending --repo-root .`（或读 jsonl）。
2. **结论层必报**：有无待审改题、几条、最新一条想改什么（人话）。自动跑**不**在这里等人。
3. **人点名本技能且 `pending>0`**：破例只问 **一句**（≤3 选项）。活跃态（batch 在跑）也问，**batch 不停、不改实验**。
   - A) 留下（只记建议，不改题）
   - B) 搁置（当没发生，下次可再提）
   - C) 驳回（类似主张以后不要再提）
4. 人**本回合**明确选了 → `python3 scripts/e_feedback.py resolve --id <id> --status adopted|deferred|rejected --note "…" --repo-root .`。**只更新改题记录**。未答 → 保持 pending，analyse 照常结束。
5. **三种处置都不改实验**（不改 `contract/`、不开闸、不代跑改能力、不改 `train.py`/`workspace/`）。留下 → 复述建议；驳回 → 以后不提类似；搁置 → 当没发生，下次仍可再提。
6. **仍禁止**：改代码、`HUMAN_GUIDANCE.md`、`train`、手改 jsonl。**禁止**因「留下」去推 `/auto-nn-modify`。

## 输出顺序（回复结构 — 两态精简）

**原则：真脚本表留、agent 自造表砍；数值只出现一次；人话优先（过程码翻译/省略，领域术语保留）；机器连续性走 journal。**

态由 `runtime-activity.py` 判定：有输出 = **活跃**（auto-run batch 或训练在跑）；空 = **空闲**。

### 六层单序列（两态共用）

| 层 | 内容 | 来源 | 规则 |
|---|---|---|---|
| 标题行 | 「第 N 轮分析 · 活跃/空闲」 | summarize + runtime-activity | 一行 |
| 数值 | 当前最好 / 最近一轮 + 提升% | `analyse_metrics --quiet` | 蒸馏 2–3 行；含 **goal 进度行**（若已设目标；explore 跳过硬停仍显示）；值逐字引用脚本；**禁手算** Δ/Δ%/plateau/beat_best |
| 状态 | auto-run/训练 pid、上一条反思建议、连续无提升/距上次反思/触发反思 | summarize brief + runtime-activity | 2–4 行；空闲态用 `○` 头 |
| 结论 | 3+ bullet：判读 + 上次反思判定 + 台账异常 + **改题待办** | MA + reflect-brief + e_feedback | **只判读不复述数字**；上次反思与上次建议判读分开 bullet；待审改题用人话报条数/最新主张 |
| 结构（体检） | 只报新增/恶化项 + 计数行 | `nn-doctor --quiet` vs `saved/doctor_last.txt` | 见「doctor 判定口径」 |
| 下一步 | 活跃=状态行；空闲=单条推荐 | — | 见「下一步两态」 |

### 活跃态模板（目标 ~25 行）

```text
第 9 轮分析 · auto-run 活跃

— 数值 —
当前最好  R8 CutMix   准确率 0.9684（本轮新冠军，提升 +0.91%，换了核心机制→保留）
最近一轮  R9 混合     准确率 0.9687（数值更高但作废：测试损失涨 24%）

— 状态 —
▶ auto-run 正在跑 Label Smoothing 0.1（pid 2154275，第 3 个备选方向）
  上一条反思建议「试 LS 0.1」已被自动采纳为当前训练
  连续无提升 0/3 · 距上次反思 9 轮 · 触发反思条件=是

— 结论 —
• R8 CutMix 成新冠军；R9 混合数值高但作废（损失倒退，已回退改动）
• 上一条反思（混合方案）：无效（损失倒退，已回退）
• 台账新增 3 条实验行（本轮 3 槽 finalize；行数≠轮数，正常）

— 结构（体检）—
🔺 配置默认值应强读（G-cfg-no-defaults）  失败  1→3（加 LS 触发，__init__.py 152/238）
其余 7 项已知无变化（4 失败 + 3 警告）→ 见记录
→ 结构修复待 auto-run 收尾后 /auto-nn-modify

— 下一步 —
auto-run 正在跑 LS 0.1（pid 2154275）。等它跑完 → 收尾 → 反思一轮，勿并行改代码/开新训。
```

### 空闲态模板（目标 ~20 行）

```text
第 9 轮分析 · 空闲

— 数值 —
当前最好  R8 CutMix  准确率 0.9684
最近一轮  R8 CutMix  准确率 0.9684（无变化）

— 尺子 —
plain 有 · reference **缺**（建议同条件跑对照或请用户给）

— 状态 —
○ 无 auto-run / 无训练
  连续无提升 3/3（撞墙）· 触发反思条件=是

— 结论 —
• 还没立公开对照上界，fancy 归因不完整
• 连续 3 轮无提升，当前关注场景撞墙
• 改题待办：待审 1 条——想改评估口径（简述）

— 结构（体检）—
  [新增/恶化项，或「0 新增 / N 已知无变化」]

— 下一步 —
先补 reference 对照轮（同官方测试），再考虑升档 fancy。
→ /auto-nn-manual-run

（人点名本技能且有待审时追加一句三选一，例：）
这条改题待办你选？ A) 留下（只建议、不改题）  B) 搁置（下次可再提）  C) 驳回（别再提类似的）
```

**省略整层**：数值/状态/结论必出；结构层无新增则写「0 新增 / N 已知无变化」；活跃「下一步」只状态，空闲才出单条推荐。

完整 MA-2~7 / 全 keeper 表：**仅用户明确要求「详细 analyse」** 时去掉各脚本 `--quiet`，但**只进 journal，不进 chat**。

## 禁止清单（输出）

- ❌ **自造表**：leaderboard 排名表、实验对比表（如 V44 vs baseline）、todo 优先级表（P0/P1/P3）。
- ❌ **装饰性 emoji**：🚨 📊 🧠 🎯 📌 🟢 💥。仅允许固定状态字形：`▶`（运行中）`✅`（保留）`❌`（作废）`⚠️`（失败/警告）`ℹ️`（信息）`○`（空闲）。
- ❌ **stream-of-consciousness 叙述**：「TSV 行数 152→153 立刻查」（行数≠轮数；轮次看 round_decision/EXPERIENCE）「Thought for Ns」式中途独白。判读直接落结论层。
- ❌ **对话式提问**：「❓ 你想做哪几项？」「我一口气跑 P1 那些？」。**唯一例外**：人点名本技能且改题待办 `pending>0` 时的一句三选一（留下 / 搁置 / 驳回）；**不停自动跑、不改实验**。
- ❌ **数值重述**：结论 / 下一步层复述数值层的具体数字（提升%、指标值）。
- ❌ **过程/编码术语裸用**：按「人话翻译」表替换或省略（领域术语如指标值/实验名/具体技术不受此限）。
- ❌ **手算 MA 字段**：Δ / Δ% / plateau / beat_best（逐字引用脚本输出）。

## 台账完整性

（表头、ledger_context_keys、cfg 缺口、NEED_MODIFY → `/auto-nn-modify`）

## 下一步（两态）

**不写 EXPERIENCE。** 不超出当前阶段 NOTE（含成熟度档）。主推荐须引用数值结论，勿手算。

- **活跃态**：`auto-run 正在跑 X。等它跑完 → 收尾 → 反思一轮，勿并行改代码/开新训。` + 一行结构 FAIL 待修提示（`待收尾后 /auto-nn-modify`）。**禁** todo 表 / 备选清单。**例外**：`pending>0` 时仍可问一句改题处置（batch 不停）。
- **空闲态**：**单条**推荐（引用数值结论 + 当前阶段 NOTE / **二维成熟度档**），+ 一行 `/auto-nn-*` 执行入口（manual-run / auto-run）。**禁** 备选 A/B/C/D 清单式提问（**例外**：改题待办三选一，见上节）。
  - **若缺 plain**：主推荐可先补 plain（auto 无标签时可 `/auto-nn-auto-run`；否则 `/auto-nn-manual-run`），**压过**升档/换 fancy；结构 FAIL 仍优先于补尺子。
  - **若缺 reference**：主推荐须说明「手跑按用户要求补对照」，**勿推 auto**；结构 FAIL 仍优先于补尺子。
  - 若阶段完成条件已达成：下轮按阶段 N+1 NOTE 继续（勿改 HUMAN_GUIDANCE）。
  - 若空路线图：依 EXPERIENCE **二维 Tier 状态**（字母档 × routine/derived/different） + exploration。
  - 撞墙时：若 B-routine 已穷尽但 B-derived 未试 → 推荐「试 B-derived（论文级/成熟组合）」，**不要**直接说“换 loss（C）”。
  - 当前最好无效或未按场景对齐：核对 TSV `scenario_id` 与 map 键。
  - **改题待办 pending>0**：结论已报后，追加一句三选一；人答则 `e_feedback.py resolve`。**无论哪项都不改题面**；留下只给人建议，勿推 `/auto-nn-modify`。

结构 FAIL 时主推荐 = 修结构（`/auto-nn-modify` / `/auto-nn-clear`）。

## 结束：写 journal（必做）

报告输出后 **必须** apply（无 `--apply` 不算完成 analyse）：

```bash
python3 scripts/journal_append.py --event analyse --apply --summary "…" \
  --recommendation-json '{"tier_hint":"B","innovation_hint":"B-derived","single_variable":"…","summary":"…","roadmap_phase":2,"e_pending":1,"e_resolution":null}'
```

`e_pending` = 本回合开始时待审条数；人当场决议后可写 `e_resolution`（如 `"rejected"` / `"adopted"` / `"deferred"`），未问或未答则 `null`。

随后提醒用户训后 commit 含 `saved/experiment_journal.json`（`git add -f`）；若本回合 resolve 过，一并 commit `_runs/analysis/e_feedback.jsonl`。

## EXPERIENCE 体积

若 `EXPERIENCE.md` 行数 ≥ `nn-config.agent.experience_compress_min_lines`（默认 800），输出一行：

```text
SUGGEST_COMPRESS: python3 scripts/compress-experience.py --preset standard --dry-run
```

## 禁止

- train、reflect.py、改代码、改 `HUMAN_GUIDANCE.md`、启动 auto-run
- 读/写 **`progress.txt`**（已废弃；用 journal + MA）
- 无 `--apply` 写 journal
- **手改** `_runs/analysis/e_feedback.jsonl`（决议只许 `e_feedback.py resolve`）
- **手算** MA 字段（Δ、Δ%、plateau、beat_best）
- 除 `journal_append --apply` 与（人已三选一后的）`e_feedback.py resolve` 外的任何写盘

## 下一步常见推荐

写/改/清空路线图 → **`/auto-nn-human-guidance`**；手跑一轮 → **`/auto-nn-manual-run`**；多轮 → **`/auto-nn-auto-run`**；改能力 → **`/auto-nn-modify`**。完整串联图见 [`skills/post-migration/README.md`](../README.md)。

## Watchlist 建议

`build-run-context.py` 渲染时若 `_render_watchlist_suggestion()` 返回非空，会在末尾自动追加 `### 📋 Watchlist 建议` 段（top-5 推荐）。
Agent 在 SKILL 输出末尾展示此段；用户采纳 → `vim nn-config.yaml` 改 `ledger.watchlist` → 调 `regen_results_tsv.py --sync-jsonl`。
用户说"不要建议" → 当前无 CLI flag；agent 直接**不展示**该段（建议仍渲染进 run_context.md，仅不在回复末尾贴出）。
