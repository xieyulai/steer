# 迁后 NN 实验技能（`auto-nn-*`，全局安装）

规则权威：业务仓 **`PROTOCOL.md`**、**`CLAUDE.md`**。本目录为技能真源；经 `./install.sh`(仓库根) 链到 `~/.cursor/skills/auto-nn-*/`。

对人输出跟用户语言走（英文问 → 英文答）。细则：业务仓 `.cursor/rules/skills-plain-language.mdc`。

## 优先级（迁后技能共用）

```text
HUMAN_GUIDANCE（## 路线图；非空时）> REFLECT_INDEX pending > EXPERIENCE > references/auto
```

**关键概念（2026-06 新增）**：Tier 现为**二维矩阵**（A–E 字母档 × routine/extend/novel 创新深度）。EXPERIENCE `## Tier 状态` 必须按格子（B-routine 等）更新；升档须等具体格子穷尽后才考虑同档下一深度。详见 PROTOCOL §7.5.1a。

## 选哪个技能？

| 你想… | 在对话里输入（斜杠技能） |
|--------|-------------------------|
| 选行选列看台账（**只读**；默认先报参照；不 doctor、不判趋势、不升成熟度档） | **`/auto-nn-check`**（`check_brief.py` 参照 + `view_runs.py` 选列 / 行过滤 / scenario glob / 每 scenario best） |
| 结构体检（布局、表头、governance、gate；默认无 smoke） | **`/auto-nn-doctor`** |
| 看台账、找原因、是否撞墙、该不该升成熟度档（**不训练**；内置 silent doctor + **运行态检测**） | **`/auto-nn-analyse`** |
| EXPERIENCE 太长、重复踩坑，收成精华并归档（**不动 TSV**） | **`/auto-nn-compress`** |
| 改 metric / 场景 / contract / KEEP 口径（**人**开会话） | **`/auto-nn-modify`**（Modify Track 表见 package `CLAUDE.md`） |
| 实验轮试模型 / loss / 注册变体（改 workspace/train） | **`/auto-nn-manual-run`** 或 **`/auto-nn-auto-run`**（直接改，守 PROTOCOL §0.1） |
| 清 preflight / 删 exp / 整仓 / 绿场（确认后 Agent 可代 `--apply`） | **`/auto-nn-clear`** |
| 写或改 `HUMAN_GUIDANCE.md` | **`/auto-nn-human-guidance`** |
| 设/改/查/清 实验目标值 + 实验模式（optimize/innovate/explore；explore 跳过 goal 硬停） | **`/auto-nn-goal`**（goal CRUD + show；`mode` / `mode show`） |
| 手跑一轮：改代码 → train → KEEP/discard | **`/auto-nn-manual-run`** |
| 只反思：跑 `reflect.py`（要 pending） | **`/auto-nn-reflect`** |
| 审查当前最好：复现 / 多种子 / 归因消融（**不**进成绩表，写卡片）；审公开对照则跳过新不新 | **`/auto-nn-audit`** |
| 立朴素下界（契约内最容易的方法，每场景一把） | **`/auto-nn-plain`** |
| 立公开对照（先反思找；找不到中点挑；满 10 轮 auto 必做） | **`/auto-nn-reference`** |
| 多轮：`./auto-nn-run.sh N` / `reflect` | **`/auto-nn-auto-run`** |
| 业务仓自助拉模板更新（governance-sync + verify） | **`/auto-nn-update`**（业务仓自己拉自己） |
| 换机/重装/依赖损坏后一键拉起环境（检测 CUDA→torch 源/装依赖/GPU 白名单交集/smoke） | **`/auto-nn-setup`**（`scripts/auto-nn-setup.py`） |

## 常见串联

```text
/auto-nn-analyse → /auto-nn-compress（若 SUGGEST_COMPRESS）→ /auto-nn-human-guidance → /auto-nn-manual-run
/auto-nn-analyse → /auto-nn-reflect → /auto-nn-manual-run
/auto-nn-plain → /auto-nn-reference → /auto-nn-auto-run
/auto-nn-analyse → /auto-nn-audit（要对当前最好或公开对照做复现/多种子时）
/auto-nn-modify → /auto-nn-manual-run
/auto-nn-clear → /auto-nn-manual-run
/auto-nn-human-guidance → /auto-nn-auto-run
set goal / mode → /auto-nn-goal → /auto-nn-auto-run
刚完成 init：`/auto-nn-doctor` → `/auto-nn-human-guidance`（explore NOTE）→ `/auto-nn-auto-run`
换机 / 重装后：`/auto-nn-setup`（拉环境）→ 再 `/auto-nn-auto-run`
```

分析 **不能代替** 训练或反思；行动前请用 **`/auto-nn-…`** 切换技能（**勿写 `@`**）。

自然语言（中/英）与斜杠等价；完整触发词见业务仓 **`docs/nn-routing/intent-map.md`**（经 governance-sync 下发）。歧义时 Agent 先问一句（策略 D）。

## 技能活动 log（`.auto-nn/skill-activity.jsonl`）

**开关**：`nn-config.yaml` → `agent.skill_activity_log`（**默认 `true`**；`false` 时 append 脚本 SKIP，exit 0）。

各技能结束或用户确认写盘前 **须** append 一行（init 另保留 `init-qa-log.md` 逐步 transcript）：

```bash
python3 scripts/append-skill-activity.py append \
  --skill auto-nn-<name> --phase end \
  --summary "人话一句" [--lock 内部摘要] [--user "A) …"] [--artifacts path1,path2]

python3 scripts/append-skill-activity.py status    # 开关与条数
python3 scripts/append-skill-activity.py recent --limit 15 --format markdown  # analyse 用
```

**清理**：`clear factory` 清空本文件；**不**删 `init-qa-log.md` / `migration-summary.md`。
