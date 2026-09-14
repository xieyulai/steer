---
name: auto-nn-clear
description: >-
  统一运行态清理（单词档名）：inspect 只看、junk 删试跑残留、runs / runs+journal 整仓清空、
  experience 归档旧叙事、reflect 清反思产物、factory 绿场、custom 条件 prune。
  Agent 先《清理计划》+ dry-run，用户确认后可代跑 --apply（本技能目的即代删；禁无确认擅自删）。
  NL: 清junk|绿场|factory reset|wipe runs. NOT: 压叙事→compress.
---

# auto-nn-clear — 分档清理（替代 reset + modify Track O）

改 contract / 模型 / loss → **`/auto-nn-modify`**（Modify-L / Modify-T）  
仅压 EXPERIENCE 叙事、不动 TSV/exp → **`/auto-nn-compress`**

**边界**：单轮 train → `/auto-nn-manual-run`；只读诊断 → `/auto-nn-analyse`

**本技能目的：** Agent **可以代删**（跑 `--apply`）。唯一闸门是**正式删除前必须得到用户确认**——不是让用户自己去终端敲命令。

---

## Code Contract（pilot，2026-07-15）

> `scripts/check_skill_contract.sh` 自动对账本段与 `template/package/*` 实际符号。
> 失败 → release-check 第 6 步门禁拦截。
> **强检字段**（对账失败即拦截）：`calls_scripts` / `reads_cfg_keys` / `env_vars_consumed`；其余（`pluggable_symbols` / `referenced_gates` 等）为 informational，release-check 不强检。

```yaml
calls_scripts:
  - scripts/govern-runs.sh                 # 主入口（clear --tier 分派 → clear-runs.sh）
  - scripts/clear-runs.sh                  # clear 实现骨架（按 tier 派发）
  - scripts/clear_inspect.py               # inspect 档只读扫描
  - scripts/clear_experience.py            # experience 档归档旧叙事
  - scripts/clear_reflect.py               # reflect 档归档反思产物
  - scripts/clear_factory.py               # factory 档绿场重置
  - scripts/lib/experiment_journal.py      # runs+journal reset_journal_for_runs_clear
  - scripts/prune-runs.py                  # custom 档透传（--drop-experiment / --ledger-only）
  - scripts/regen_results_tsv.py           # TSV 台账同步（表头 / 行数对齐）
  - scripts/smoke-check.sh                 # 清后复检（用户本地）
  - scripts/nn-doctor.sh                   # 清后可选结构复检
  - scripts/append-skill-activity.py       # 活动日志（agent.skill_activity_log）

reads_cfg_keys:
  - agent                                  # 父键（含 .skill_activity_log）
  - agent.skill_activity_log               # 活动日志开关（--apply 后 append）
  - ledger                                 # 台账段（runs / runs+journal 重置对齐）

env_vars_consumed:                         # junk 档清 preflight/smoke 残留、清后 smoke/doctor 复检时生效
  - NN_AUTO_FINALIZE_ROUND                 # round_decision.json 归属（runs 档删）
  - NN_GUARD_CFG_DEFAULTS                  # 清后 preflight/doctor 复检门禁
  - NN_GUARD_HARDCODED_PARAMS              # 清后 preflight/doctor 复检门禁
  - NN_GUARD_NO_FALLBACK                   # 清后 preflight/doctor 复检门禁
  - NN_GUARD_REPRO_ENV                     # 清后 preflight/doctor 复检门禁

pluggable_symbols:                         # 仅 informational，lint 不强检
  - govern-runs.sh clear --tier <inspect|junk|runs|runs+journal|experience|reflect|factory|custom>
  - _runs_legacy/experience/               # experience/reflect 归档落点
  - _runs_legacy/reflect/                  # reflect 归档落点
```

## 高频代号（人话见 glossary）

| 内部码 | 对用户怎么说 |
|--------|--------------|
| `inspect` | 只看看有多脏 |
| `junk` | 删试跑残留（preflight / smoke） |
| `runs` | 清空所有实验，记录表从头记 |
| `runs+journal` | 上面再加重置实验日记 |
| `experience` | 归档旧实验叙事（保留近 K 条；不动 TSV/exp） |
| `reflect` | 归档反思产物（含 experience 归档；点名归档改题待办 `_runs/analysis/e_feedback.jsonl`；**不**删成绩表探索格子） |
| `factory` | 完全绿场，像从没跑过 |

出《清理计划》时，「档位」一行写**单词档名**（不再用 `C?` 标签），再附一句人话说明会动什么。

---

## 你怎么用（人）

| 你说… | 档位（`--tier`） |
|--------|------------------|
| 看看有多脏 / 该不该清 | `inspect` |
| 清 preflight / smoke | `junk` |
| 删某 experiment / 只删 TSV 行 | `custom` + prune 参数 |
| 清空所有 exp、TSV 从头记 | `runs` |
| 上面 + reset experiment journal | `runs+journal` |
| 归档旧 EXPERIENCE 叙事 | `experience` |
| 再清 reflect 产物 | `reflect` |
| **像从未跑过实验**（绿场） | `factory`（须 `--confirm factory`） |

Agent 输出 **《清理计划》** + 跑 dry-run → **向用户确认** → 用户明确同意后 **Agent 代跑 `--apply`**（`factory` 命令须带 `--confirm factory`，且确认话里须点名绿场）。

> **与 `/auto-nn-compress` 的边界（互补，勿混）：** `clear --tier experience` 是**破坏性归档清场**——把旧实验段搬到 `_runs_legacy/experience/`、只留近 K 条；`/auto-nn-compress` 是**非破坏性精简**——压正文、写回 `## 精华摘要`，不搬走旧段。日常瘦身用 compress，朝绿场清场用 clear。

---

## 档位（单词档名）

| `--tier` | 作用 |
|----------|------|
| `inspect` | 只读：junk 目录数、TSV/jsonl、EXPERIENCE 体积、建议 tier |
| `junk` | 删 `preflight_check` / `smoke_check` 与 `*_preflight_check` / `*_smoke_check` |
| `runs` | 清 `_runs/exp/*`、TSV 仅表头、jsonl、删 `round_decision.json` |
| `runs+journal` | `runs` + reset `saved/experiment_journal.json`（`entries=[]`，facts 对齐 TSV；可选 `--keep-analyse`） |
| `experience` | 归档旧实验叙事 → `_runs_legacy/experience/`，保留近 K 条（`--keep-recent`，默认 5；不动 TSV/exp） |
| `reflect` | 先做 `experience` 归档，再归档 reflect 产物（含点名 `_runs/analysis/e_feedback.jsonl`）→ `_runs_legacy/reflect/`、重置 REFLECT_INDEX pending；**不**删 TSV `exploration_space` 格子 |
| `factory` | 绿场重置：清 `_runs/`、`saved/`、`references/auto/`、归档 EXPERIENCE、重置 INDEX（保留 contract/workspace/train.py 等；apply 须 `--confirm factory`） |
| `custom` | 透传 `prune-runs.py`（`--drop-experiment`、`--ledger-only` 等） |

**`junk` 与 `runs` 不累积**：junk 只删脏数据；整仓清理由 `runs` 起。

**实现状态：** 全部档位（`inspect` / `junk` / `runs` / `runs+journal` / `experience` / `reflect` / `factory` / `custom`）均已实现可用。`factory` apply 须 `--confirm factory`。

---

## Agent 必做清单

- [ ] 复述用户目标（junk only / 整仓 / EXPERIENCE / 绿场？）
- [ ] 映射 **单一最高 tier**（`factory` 已含低档；勿默认连跑 `junk`+`runs` 除非用户分步确认）
- [ ] 只读：`EXPERIENCE.md` 体积、TSV、`_runs/exp/`、`saved/keeper.json`；或建议先 `clear --tier inspect`
- [ ] 输出 **《清理计划》**
- [ ] **先**跑 dry-run（无 `--apply`）；把 dry-run 要点用人话贴出
- [ ] **停问确认**（一句、≤3 选项）：例如「确认代你执行删除？A) 确认执行 B) 取消」
- [ ] **仅当**用户本轮明确同意（确认 / 执行 / apply / 干吧 / A）→ Agent 代跑 `--apply`（`factory` 须 `--confirm factory`）
- [ ] 用户首条已写「确认执行 / 直接删 / 代 apply」→ 仍须先计划+dry-run，可**同轮** apply（视为已确认）
- [ ] apply 后：smoke（或提示用户）+ `append-skill-activity`；**禁止**手改 TSV / `rm -rf` 绕开脚本

### 确认闸门（硬规则）

| 情况 | Agent 行为 |
|------|------------|
| 尚未确认 | **禁止** `--apply` |
| 用户确认后 | **应当**代跑 `--apply`（本技能目的；勿再推「请你本地敲命令」） |
| `factory` | 确认话须点名「绿场 / factory」；命令带 `--confirm factory` |
| auto-run / 实验执行轮会话 | **禁止**顺手 clear apply（须用户显式开 `/auto-nn-clear` 并确认） |
| 手改 TSV / 裸 `rm -rf` | **永远禁止** |

### 《清理计划》格式

```markdown
## 清理计划

- **档位**：`--tier <单词>` / custom（…）
- **用户目标**：（一句）
- **将改动**：（列表）
- **将保留**：（正式 exp、contract、F1 等；**TSV `exploration_space` 格子**——clear reflect **不**清空探索格子）
- **归档路径**：（`experience` / `reflect` / `factory`）`_runs_legacy/…`；`reflect` 档须点名是否含 `_runs/analysis/e_feedback.jsonl`（默认随 reflect 产物归档）
- **风险 WARN**：（keeper、factory 不可逆等）

### 下一步（确认后由我代执行）

1. （已跑）dry-run：`bash scripts/govern-runs.sh clear --tier …`
2. 等你确认 → 我代跑：`… --apply`（`factory` 加 `--confirm factory`）
3. 清后：`bash scripts/smoke-check.sh`；可选 `bash scripts/nn-doctor.sh`
```

---

## 附录 — 命令

```bash
bash scripts/govern-runs.sh clear --tier inspect
bash scripts/govern-runs.sh clear --tier junk
bash scripts/govern-runs.sh clear --tier junk --apply

bash scripts/govern-runs.sh clear --tier runs
bash scripts/govern-runs.sh clear --tier runs+journal --apply

bash scripts/govern-runs.sh clear --tier reflect
bash scripts/govern-runs.sh clear --tier reflect --apply

bash scripts/govern-runs.sh clear --tier custom --drop-experiment preflight_check --apply
bash scripts/govern-runs.sh clear --tier custom --ledger-only --drop-experiment F01_old --apply
```

**已废止：** `govern-runs.sh prune|reset`、`/auto-nn-reset`。

---

## 硬边界

- **禁止**未确认就 `--apply`；**禁止**手改 `_runs/results.tsv` / `results.jsonl`；**禁止**裸 `rm -rf` 绕开 `govern-runs.sh clear`
- **禁止** EXPERIENCE 归档进 `references/`
- **禁止**在 auto-run / 实验执行轮里「顺手」clear apply（与显式 `/auto-nn-clear` + 确认 不同）
- 用户已确认 → Agent **应**代 `--apply`，不要把「请本地执行」当默认收尾

---

## 下一步常见推荐

清前先看该不该清 → **`/auto-nn-analyse`**；清后跑第一轮 → **`/auto-nn-manual-run`**；只压 EXPERIENCE 正文 → **`/auto-nn-compress`**。完整串联图见 [`skills/post-migration/README.md`](../README.md)。

## 对用户怎么说（人话）

- **《清理计划》**：第一行写**单词档名**（`junk`/`runs+journal`/`factory`…）+ 一句「会删什么/留什么」；禁 `C?` 档标签。
- **风险**：factory/整仓清不可逆，须显式 WARN；当前最好指针会不会丢要说清。
- **确认后再代删**：先计划+dry-run，问一句确认；同意后**我来跑** `--apply`，别默认甩命令让用户自己敲。
- **档位人话**：inspect→「只看看」；junk→「删试跑脏数据」；runs→「实验目录和成绩表从零」；factory→「像从没跑过」。

**坏**：「请你在仓库根自己执行 `--apply`。」（本技能就是为了代删）  
**好**：「清理计划：删试跑脏数据，正式实验保留。dry-run 如上。确认代你执行删除？回复「确认」我就 `--apply`。」

## 活动 log

**`--apply` 执行后**（或仅 inspect / 用户取消）**须** append：`--skill auto-nn-clear --phase end --summary "tier=runs+journal apply"`（取消则 summary 写 `cancelled`）。`factory` 会清空 `.auto-nn/skill-activity.jsonl`（保留 init 留档）。开关 `agent.skill_activity_log`（默认 true）。
