---
name: auto-nn-reference
description: >-
  立公开对照：先走反思找公开方法；找不到则从已有成绩按中点挑。
  有原仓须本机校准，对不上禁止贴文献尺。每场景一把尺；已有则先报、问换不换。
  满 10 轮仍无尺时自动多轮必做；文献未校准过线不得自动贴。
  NL: 立公开对照|找论文尺子|reference 尺子. NOT: 朴素下界→plain；只反思→reflect；审查对照→audit.
---

# auto-nn-reference — 立公开对照

给当前场景立一把公开对照尺子（上界/对照）。先用现成反思找公开方法；找不到就从已有成绩里挑「当前最好」和「朴素下界」中间那一档。贴上后审查可以把这把尺当对象（跳过新不新）。

权威：`PROTOCOL.md` §6。

对人说**公开对照**，不要把仓内当前最好叫公开对照。

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

- 「立公开对照」「找论文当尺子」
- **不要**用于：只反思不想贴尺（→ `/auto-nn-reflect`）；朴素下界（→ `/auto-nn-plain`）；审查这把尺（→ `/auto-nn-audit --exp-dir`）

## 流程

1. `python3 scripts/nn_baseline.py status --repo-root .` 已有 → 报出来，问留下还是换。
2. 用现成反思找公开方法；测条件须与本题官方测试/主指标对齐。对不齐禁止抄论文分。
3. **找得到原仓库**（`.auto-nn/migration-source` 真目录或 intent 里的 `source_repo_path`）：先在本机用**原入口**跑出校准分（不进成绩表，写入 `saved/source_calibration.json`），再跑本仓对照。贴文献尺前必须校对：

```bash
python3 scripts/nn_baseline.py check-source-cal --repo-root . --exp-dir _runs/exp/<dir>
```

未达标（exit≠0 / `verdict` 不是 pass）→ **禁止** `stamp --source literature`。先改本仓配方或调度，只重跑本仓对照；不要把论文分数写进尺子。
4. 找不到公开方法：

```bash
python3 scripts/nn_baseline.py pick-reference --repo-root .
```

无朴素下界算不了中点 → 先 `/auto-nn-plain`。中点代用走 `--source ledger_midpoint`，不要求校准文件。
5. 人手开技能：确认后才贴。满 10 轮自动触发：不确认也可贴**中点代用**；**文献尺**须校准已过线，不得在未 pass 时自动贴 `--source literature`。

```bash
# 文献复现（须校准过线）
python3 scripts/nn_baseline.py stamp --repo-root . --tag reference \
  --exp-dir _runs/exp/<dir> --source literature
# 中点代用
python3 scripts/nn_baseline.py stamp --repo-root . --tag reference \
  --exp-dir _runs/exp/<dir> --source ledger_midpoint
# 换尺加 --replace
```

贴已有行**不重跑**。禁止贴当前最好，禁止把已是朴素下界的那行改成公开对照。尺子锚值 = 本仓复现分。
6. `append-skill-activity.py append --skill auto-nn-reference --phase end --summary "立公开对照 …"`

## 硬边界

- 每场景最多一行 `reference`。
- 不改当前最好。
- 默认不从头训论文。
- 代用来源必须是 `ledger_midpoint`，不得写成论文分。
- 有原仓且走文献尺：校准未过线禁止贴；不准把发表分当尺子。
