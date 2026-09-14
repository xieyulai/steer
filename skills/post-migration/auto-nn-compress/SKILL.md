---
name: auto-nn-compress
description: >-
  EXPERIENCE 冗长时收成精华并归档：C0 体检、C1 去重、C2 standard（默认保留近 5 轮要点）。
  含历史债务清理（超长 Tier/REFLECT_INDEX 摘要、锚点前旧段）。facts 来自 TSV，不碰 results.tsv/jsonl/exp。
  auto-run 轮末（after_round）自动 apply；本技能用于人主动 dry-run/审阅。NL: 压缩经验|EXPERIENCE太长|compress experience. NOT: 清实验→clear.
---

## Code Contract（pilot，2026-07-15）

> `scripts/check_skill_contract.sh` 自动对账本段与 `template/package/*` 实际符号。
> 失败 → release-check 第 6 步门禁拦截。
> **强检字段**（对账失败即拦截）：`calls_scripts` / `reads_cfg_keys` / `env_vars_consumed`；其余（`pluggable_symbols` / `referenced_gates` 等）为 informational，release-check 不强检。

```yaml
calls_scripts:
  - scripts/compress-experience.py        # 主入口（C2 standard/apply）
  - scripts/append-skill-activity.py      # 活动日志（apply 后必 append）

reads_cfg_keys:
  - agent                                  # 父键（含 .experience_compress_* / .skill_activity_log）
  - agent.experience_auto_compress          # 自动压缩 mode（off/warn/after_round）
  - agent.experience_compress_preset        # 压缩预设（standard/minimal/wide）
  - agent.experience_compress_keep_n        # 保留近 N 轮实验段（默认 5）
  - agent.experience_compress_keep_reflects # 保留近 N 条 [反思]（默认 2）
  - agent.experience_compress_tier_cell_max # Tier 状态格字数上限（默认 80）
  - agent.experience_compress_scenario_cell_max # 场景格字数上限
  - agent.experience_compress_reflect_hist_summary_max # REFLECT_INDEX 历史摘要字数上限
  - agent.experience_compress_min_lines     # 触发压缩行数阈值
  - agent.experience_compress_min_archivable # 触发压缩待归档段阈值
  - agent.experience_compress_cooldown_rounds # after_round 冷却轮数
  - agent.skill_activity_log                # 活动日志开关（append-skill-activity 读）

env_vars_consumed:
  - NN_EXPERIENCE_AUTO_COMPRESS             # 自动压缩 mode 覆盖（debug/维护）
```

# auto-nn-compress — EXPERIENCE 压缩

权威：`PROTOCOL.md` §7.5.1–§7.5.2。

**与 reflect 分工：** reflect 写 `[反思]` + `references/auto/`；本技能**写回** `## 精华摘要`（**置顶**）并归档旧实验段到 `references/experience/`。

**与 `/auto-nn-clear --tier experience` 的边界（互补，勿混）：** 本技能是**非破坏性精简**——压正文、保精华、写回 `## 精华摘要`；clear 的 `experience` 档是**破坏性归档清场**——把旧实验段搬到 `_runs_legacy/experience/` 只留近 K 条。日常瘦身用本技能，朝绿场清场用 clear。

## 高频代号（人话见 glossary）

| 内部码 | 对用户怎么说 |
|--------|--------------|
| `C0 / C1 / C2` | 只统计 / 规则去重 / 收精华并归档 |
| `精华摘要` | 经验文档置顶的滚动摘要 |
| `Tier 状态` | 实验成熟度档位表 |
| `dry-run` / `--apply` | 先预演看效果 / 确认后真正执行 |

## EXPERIENCE 目标结构（C2 apply 后）

```text
# EXPERIENCE
├── ## 精华摘要（滚动，compress 维护）   ← 置顶；含 SOTA / Tier 快照 / REFLECT pending 一行
├── ## 信息索引（按需 Read）             ← C2 插入；指向 REFLECT_INDEX / saved / TSV / archive
├── ## 场景与 KEEP 约定（若有）
├── ## Tier 状态（滚动，每轮必更新）     ← 单格 ≤80 字
├── ## 近期实验（保留最近 5 轮要点）
├── ## [反思]（近 2 条，可选）
└── <!-- experience-log-start -->        ← 新轮 append 锚点（禁止 prepend 到精华前）
```

- **Tier 语义**在 `PROTOCOL.md` §7.5.1；EXPERIENCE 只保留 **`## Tier 状态` 二维矩阵**（Agent 每轮更新）。
- **已废弃**：`nn-repro-block`、`nn-tier-block`、`## Tier A–E` 长文 — doctor WARN，C1 删除重复梯子。
- **`## Tier 举证摘要`**：默认 **归档**（不再 protected）；深度叙事见 archive 或 Tier 状态「备注」。
- C2 **FAIL** 若缺 `## Tier 状态` 或精华 SOTA experiment ∉ TSV。

## 何时使用

- **默认路径**：`auto-nn-run.sh` 轮末 `experience_auto_compress: after_round` **自动** C2 apply（含历史债务 bypass 冷却）；**业务仓不必手跑本技能**
- 人想**预演**压缩效果、或 auto 未开 `after_round` 时人工 apply
- EXPERIENCE 数百行 / 百轮冗余、重复 preflight 叙述
- `/auto-nn-analyse` 给出 `SUGGEST_COMPRESS: C2 standard`
- **不要**用于改 TSV、删 exp（用 `/auto-nn-clear`）；改 contract 用 `/auto-nn-modify`

## 默认参数（用户已确认）

| 项 | 值 |
|----|-----|
| 预设 | **standard** = C2 + EXP+REF-E |
| 保留要点 | **5** 轮实验段 + **2** 条 `[反思]`（`--keep-n 5`） |

## 流程（必须）

**auto-run 已开 `after_round`（模板默认）时**：轮末 shell 自动 `--apply`；Agent **勿**重复手跑 apply，除非人点名预演。

**人主动审阅时**：

1. 建议在项目根先 `git status`；有未提交 EXPERIENCE 可先 commit。
2. **dry-run（默认）**：

```bash
python3 scripts/compress-experience.py --repo-root . --preset standard --dry-run
```

3. 人审输出：facts、`EXPERIENCE` 字符变化、VALIDATION 无 FAIL。
4. **apply**（**仅**人明确同意、且非 auto-run 自动路径时）：

```bash
python3 scripts/compress-experience.py --repo-root . --preset standard --apply
```

- **apply 前**：C2 自动跑 C1 去重；**历史债务**（超长 Tier 格、锚点前旧实验段、REFLECT_INDEX 长摘要）一并清理
- **apply 后**：存在 `references/experience/archive_*.md`（若有可归档段）；`EXPERIENCE.md` 含 `## 精华摘要` 与 `## 信息索引`；`_runs/results.tsv` **未变**
6. 建议 `git commit`；下一轮用 `/auto-nn-manual-run` 或 `/auto-nn-experiment-round`。

## 挡位与范围

| 预设 | 挡位 | 范围 |
|------|------|------|
| minimal | C1 | EXP |
| **standard** | C2 | EXP+REF-E |
| wide | C2 | EXP+REF-E（当前同 standard，预留扩展；scope 为描述性标签，仅 `REF-E` 子串触发归档告警） |

| 挡位 | 说明 |
|------|------|
| C0 | `--tier C0` 只打印 JSON 统计 |
| C1 | 规则去重（legacy 梯子 / 重复 Tier 表 / 相邻重复段） |
| C2 | 精华 + 信息索引 + Tier/场景截断 + 归档 + **REFLECT_INDEX 历史摘要截断** |

## 禁止

- 手改 `_runs/results.tsv` / `results.jsonl`
- 未 dry-run 直接 `--apply`（**auto-run after_round 除外**）
- 删除 `_runs/exp`
- 改 `HUMAN_GUIDANCE` / `contract`（C2 **会**截断 REFLECT_INDEX 历史「结果摘要」，不改 pending 行）

## 下一步常见推荐

压缩前台账乱 → **`/auto-nn-analyse`**；压缩后跑实验 → **`/auto-nn-manual-run`**；撞墙要方向 → **`/auto-nn-reflect`**。完整串联图见 [`skills/post-migration/README.md`](../README.md)。

## 对用户怎么说（人话）

- **dry-run 结果**：「经验文档将从 X 字收到 Y 字，归档 Z 条旧实验段，**不动**成绩表」；禁裸 `C2`/`EXP+REF-E`（可说「标准精简档」）。
- **auto-run**：「轮末已自动瘦身；agent log 可见 `EXPERIENCE auto-compress`」
- **手跑 apply 前**：须人确认；说明保留最近 **5** 轮要点（默认）。
- **与 clear 区分**：compress = 瘦身留精华；clear experience = 归档清场。

**坏**：「C2 standard EXP+REF-E dry-run VALIDATION PASS」  
**好**：「预演：经验文档 800 行→120 行，保留最近 5 轮要点，历史旧段进 archive，成绩表一行不动。」

## 活动 log

`compress-experience.py --apply` 成功后 **须** append：`--skill auto-nn-compress --phase end --summary "preset=standard"`。开关 `agent.skill_activity_log`（默认 true）。
