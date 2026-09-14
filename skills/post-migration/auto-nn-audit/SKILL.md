---
name: auto-nn-audit
description: >-
  审查当前最好：复现 / 多种子 / 归因消融（不进成绩表，写卡片）。
  未指定对象则先报当前最好并一句确认；跑 scripts/nn_audit.py pipeline；
  贴卡片人话后问留下/搁置/驳回（不代写）。禁止 reflect.py、finalize-round、改 HUMAN_GUIDANCE。
  NL: 审查|复现|多种子|归因消融|打审查卡片. NOT: 结构体检→doctor；下一轮该试什么→reflect/analyse；多轮搜索→auto-run.
---

# auto-nn-audit — 审查

对人指定的对象（默认当前最好）做一次**独立于搜索环**的审查：先判定新不新并写好消融策略，再复现、换种子，判定为新且复现成立才跑消融；**不进成绩表**；结论进卡片。技能**不替人盖章**。

指定对象是公开对照那一行时：复用复现 / 多种子 / 卡片，**跳过**新不新与消融。没尺子时卡片非正式，并点名先 `/auto-nn-plain` / `/auto-nn-reference`。

权威：`PROTOCOL.md`。

对人说**审查**，不说终审。禁止技能名或对用户口播 `finalize`。

## Code Contract（pilot，2026-07-15）

> `scripts/check_skill_contract.sh` 自动对账本段与 `template/package/*` 实际符号。
> 失败 → release-check 第 6 步门禁拦截。
> **强检字段**（对账失败即拦截）：`calls_scripts` / `reads_cfg_keys` / `env_vars_consumed`；其余（`pluggable_symbols` / `referenced_gates` 等）为 informational，release-check 不强检。

```yaml
calls_scripts:
  - scripts/nn_audit.py
  - scripts/append-skill-activity.py
reads_cfg_keys:
  - agent.scenario_default
  - agent.skill_activity_log
  - keep.near_best_abs
env_vars_consumed:
  - NN_SKIP_WRITE_KEEPER
  - NN_AUTO_FINALIZE_ROUND
  - NN_PARALLEL_TOTAL
```

## 何时使用

- 「审查当前最好」「复现一下」「多种子稳不稳」「归因消融 / 拆零件」「打审查卡片」
- 搜中或搜后都可以跑；不限「预算用尽才跑」
- **不要**用于：结构体检（→ `/auto-nn-doctor`）；只看成绩表（→ `/auto-nn-check`）；下一轮该试什么（→ `/auto-nn-reflect` / `/auto-nn-analyse`）；多轮搜索（→ `/auto-nn-auto-run`）

## 高频代号（人话见 glossary）

| 内部码 | 对用户怎么说 |
|--------|--------------|
| `keeper` | 当前最好 |
| `novel` | 新不新 |
| `ablation` | 归因消融 / 拆零件 |
| `TSV` | 成绩表 |
| `saved/audit/` | 审查卡片目录 |

## 流程

1. **未指定对象**：先报当前最好（关注场景的指针；没有则报该场景成绩表最高分那一行），**一句确认**后再开跑。指定了实验目录 / 实验名 / 场景则审那些。审公开对照：`--exp-dir` 指向 `baseline_tag=reference` 的那次（不要加 `--fetch-external`，脚本会跳过新不新）。
2. 跑编排：

```bash
python3 scripts/nn_audit.py pipeline --repo-root .          # cwd=业务仓根；默认不联网
# 要对照文献判定新不新时，Agent 必须显式加 --fetch-external（默认仍不发网）：
python3 scripts/nn_audit.py pipeline --repo-root . --fetch-external
# 指定对象：
python3 scripts/nn_audit.py pipeline --repo-root . --exp-dir _runs/exp/<dir>
python3 scripts/nn_audit.py pipeline --repo-root . --scenario <scenario_id>
python3 scripts/nn_audit.py show --repo-root .              # 只读贴已有卡片
```

审查臂走 `train.py --no-auto-finalize-round`；环境由脚本强制：`NN_SKIP_WRITE_KEEPER=1`、`NN_AUTO_FINALIZE_ROUND=0`、`NN_PARALLEL_TOTAL=1`。实验名必须以 `audit_` 开头。默认不联网；要做有文献支撑的审查，Agent **必须**传 `--fetch-external`。

3. **贴卡片人话**（路径 + 一句结论：复现过没、多种子稳不稳、新不新或「审的是公开对照已跳过」、消融掉没）。不裸抛内部码。
   没尺子时加一句：先立朴素下界 `/auto-nn-plain`，需要上界再 `/auto-nn-reference`。
4. **问用户**：留下 / 搁置 / 驳回。卡片上 `human_decision` 保持空；**不代写**裁决。
5. 结束 append 活动日志：

```bash
python3 scripts/append-skill-activity.py append \
  --skill auto-nn-audit --phase end \
  --summary "审查 …"
```

开关 `agent.skill_activity_log`（默认 true）。

## 硬边界

- **禁止**跑 `reflect.py`（会弄脏搜索期待消费建议）
- **禁止** `finalize-round`（审查跑次不入账、不改当前最好指针）
- **禁止**改 `HUMAN_GUIDANCE.md`
- **禁止**把审查跑次追加进 `_runs/results.tsv` / `results.jsonl`
- 清理反思档 **不删** `saved/audit/`；整仓绿场才会清整个 `saved/`

## 与其它技能

| 技能 | 分工 |
|------|------|
| **audit** | 对当前最好（或指定的公开对照）做复现 / 多种子 / 消融，写卡片，不进成绩表；审对照则跳过新不新 |
| **plain** | 立朴素下界 |
| **reference** | 立公开对照 |
| **check** | 只读看台账；默认参照含审查行（有卡则路径+一句结论） |
| **analyse** | 只读分析趋势 / 撞墙；不训练 |
| **reflect** | 搜索期反思，写下一轮建议 |
| **doctor** | 仓结构体检 |
