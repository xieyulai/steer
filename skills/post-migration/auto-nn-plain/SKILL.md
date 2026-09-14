---
name: auto-nn-plain
description: >-
  立朴素下界：在契约内容易落地的最傻方法上跑一轮（或给已有实验贴 plain）。
  每场景一把尺；已有则先报、问换不换。不改当前最好。
  NL: 立朴素下界|跑最傻的方法|plain 尺子. NOT: 公开对照→reference；审查→audit；改契约→modify.
---

# auto-nn-plain — 立朴素下界

按当前问题、在**遵守契约**的前提下，选最容易拧到的方法，立一把朴素下界尺子。贴上后看台账、审查、每轮公告栏都认这把尺。

权威：`PROTOCOL.md` §6。

对人说**朴素下界**，不要说 SOTA。

## Code Contract（pilot，2026-07-15）

> `scripts/check_skill_contract.sh` 自动对账本段与 `template/package/*` 实际符号。

```yaml
calls_scripts:
  - scripts/nn_baseline.py
  - scripts/append-skill-activity.py
reads_cfg_keys:
  - agent.scenario_default
  - agent.skill_activity_log
env_vars_consumed: []
```

## 何时使用

- 「立朴素下界」「跑个最傻的方法当尺子」
- **不要**用于：公开对照（→ `/auto-nn-reference`）；审查（→ `/auto-nn-audit`）；改契约（→ `/auto-nn-modify`）

## 流程

1. `python3 scripts/nn_baseline.py status --repo-root .` 先看有没有尺。已有 → 报出来，问留下还是换成这次。
2. 推候选：配置里已有、注册表里已有的最朴组合。必须改契约才能跑 → **停**，去 `/auto-nn-modify`。
3. 人确认后：新训则 `config.json` 里 `baseline_tag=plain` 跑 1 轮；已有实验则：

```bash
python3 scripts/nn_baseline.py stamp --repo-root . --tag plain --exp-dir _runs/exp/<dir>
# 换尺：
python3 scripts/nn_baseline.py stamp --repo-root . --tag plain --exp-dir _runs/exp/<dir> --replace
```

4. 改 `train.py` / `workspace/` 守协议书改码三原则（参数从配置读、不许偷兜底、新方法走开关注册）。不改当前最好。
5. `append-skill-activity.py append --skill auto-nn-plain --phase end --summary "立朴素下界 …"`

## 硬边界

- 每场景最多一行 `plain`；没 `--replace` 不准贴第二把。
- 衍生实验标签必须是 `none`。
- 禁止为「朴素」去改契约。
