# auto-nn-* 自然语言意图路由表

> Agent：路由前 Read 本文件；命中后 Read 对应 `~/.cursor/skills/auto-nn-<name>/SKILL.md`。斜杠 `/auto-nn-*` 与自然语言同等。

## 歧义策略 D

| 风险 | 技能 | 行为 |
|------|------|------|
| 只读·低 | check / analyse / doctor | 直接 Read SKILL |
| 只读·中 | compress / reflect / update | 有对象直进，否则一句澄清 |
| 写盘·高 | modify / clear / human-guidance / goal | 缺对象 → 一句 A/B/C 澄清 |
| 执行·高 | manual-run / auto-run / audit / plain / reference | 见 §manual-run vs auto-run；审查 vs 体检见下；立尺 vs 手跑见下；都没有则澄清 |

## manual-run vs auto-run

| → auto-run | → manual-run |
|------------|--------------|
| 自动、多轮、batch、N 轮、loop、auto-run、overnight | 手跑、单轮、一轮、改完训一下、试 LR |
| automatic, multi-round, batch, N rounds, loop | single round, hand-run, train once, one shot |

## modify vs manual-run

| → modify | → manual-run / auto-run | → 澄清 |
|----------|-------------------------|--------|
| 加 metric 列、扩场景、动 contract（**人**开会话） | 改 LR、试 SAM、tune、换 config；实验轮加 backbone/改 workspace | 仅「改一下 / change it / modify」 |

## 澄清话术（只问一句；跟用户语言）

- **实验**：A) 手跑一轮 / run one round by hand  B) 多轮自动 batch / multi-round auto batch
- **修改**：A) 日常扫参（manual-run） / everyday sweep  B) 改能力（modify） / change capabilities
- **查看**：A) 快速看台账（check） / quick ledger  B) 完整分析（analyse） / full analysis
- **审查 vs 体检**：A) 结构体检（doctor） / health check  B) 对当前最好复现/多种子（audit） / reproduce the current best
- **立尺**：A) 朴素下界（plain） / naive lower bound  B) 公开对照（reference） / public reference

---

## 技能路由表

每行四列：**中文触发 | English | NOT（排斥） | 斜杠等价**

### 只读三件套（直接进）

| 技能 | 中文 | English | NOT | 斜杠 |
|------|------|---------|-----|------|
| check | 看台账、筛几行、最近几次、各场景最好；默认先报参照（当前最好/尺子/场景/目标/关注） | view runs, filter tsv, tail, best per scenario | 分析原因/升档 → analyse | `/auto-nn-check` |
| analyse | 分析、撞墙、升档、下一步、进度 | analyse, plateau, tier, what next | 只看几行 → check；结构报错 → doctor | `/auto-nn-analyse` |
| doctor | 体检、结构检查、governance、表头 | doctor, health check, layout | 看成绩 → check/analyse | `/auto-nn-doctor` |

### 治理 / 叙事

| 技能 | 中文 | English | NOT | 斜杠 |
|------|------|---------|-----|------|
| compress | 经验太长、压缩 EXPERIENCE | compress experience, slim narrative | 清实验 → clear | `/auto-nn-compress` |
| human-guidance | 改路线图、指挥台、HUMAN | roadmap, human guidance, steering | 改 goal 数值 → goal | `/auto-nn-human-guidance` |
| goal | 目标值、达标即停、实验模式、升级 goal、迁移到 v3、多 metric goal | goal, target, experiment mode, upgrade goal, migrate v3, multi-metric goal | 改路线图 prose → human-guidance | `/auto-nn-goal` |

### 改 / 清（高险：缺对象则澄清）

| 技能 | 中文 | English | NOT | 斜杠 |
|------|------|---------|-----|------|
| modify | 改能力、加指标列、扩场景、新 loss 类型（执行方：人） | capability, new metric, expand scenario | 调 LR → manual-run；删 junk → clear；实验轮自己注册模型 → auto-run/manual-run 直接改 workspace | `/auto-nn-modify` |
| clear | 清 junk、整仓、绿场；计划确认后 Agent 可代删 | clear junk, factory reset, wipe runs | 压缩叙事 → compress | `/auto-nn-clear` |

### 执行

| 技能 | 中文 | English | NOT | 斜杠 |
|------|------|---------|-----|------|
| manual-run | 手跑一轮、改完训一下 | hand-run, single round, train once | 多轮/auto → auto-run | `/auto-nn-manual-run` |
| auto-run | 自动实验、跑 N 轮、batch | auto-run, N rounds, batch experiment | 只 reflect → reflect；只分析 → analyse | `/auto-nn-auto-run` |
| reflect | 反思、撞墙分析（不训练） | reflect, wall analysis, no training | 要 train → manual-run；复现/多种子审查 → audit | `/auto-nn-reflect` |
| audit | 审查、复现、多种子、归因消融、打审查卡片 | audit, reproduce, multi-seed, attribution ablation | 结构体检 → doctor；下一轮该试什么 → reflect/analyse；多轮搜索 → auto-run；立尺 → plain/reference | `/auto-nn-audit` |
| plain | 立朴素下界、跑最傻的方法、plain 尺子 | plain baseline, naive baseline, lower bound | 公开对照 → reference；审查 → audit；改契约 → modify | `/auto-nn-plain` |
| reference | 立公开对照、找论文尺子、reference 尺子、原仓校准 | public reference, paper baseline, upper bound, source calibration | 朴素下界 → plain；只反思 → reflect；审查对照 → audit | `/auto-nn-reference` |

### 维护

| 技能 | 中文 | English | NOT | 斜杠 |
|------|------|---------|-----|------|
| update | 拉模板、governance-sync | sync template, update framework | 业务分析 → analyse | `/auto-nn-update` |
| init | 立项、迁入、初始化、答案清单、先交答卷 | init project, migrate, greenfield, --answers | 迁后日常 → 其他技能 | `/auto-nn-init` |

### 维护者侧（沙箱验证）

| 技能 | 中文 | English | NOT | 斜杠 |
|------|------|---------|-----|------|

---

## goal 操作路由（v4 schema）

`/auto-nn-goal` 子命令 → 写入 `nn-config.yaml → goal` 段（v4 字段；老 v2/v3 字段由 `migrate_goal_schema.py` 一次性迁移）：

| 用户说 | CLI | 写入 yaml 字段 |
|--------|-----|---------------|
| 「目标定 0.95」 | `set 0.95` | `goal.target: 0.95` |
| 「128b 场景单独定 0.75」 | `set 128b 0.75` | `goal.per_scenario.128b: 0.75` |
| 「所有场景全达标才停」 | `stop-mode all_in_scope` | `goal.policy: strict`（v3→v4 映射：`all_in_scope` ↔ `strict`） |
| 「只盯主场景」 | `stop-mode focus_only` | `goal.policy: focus`（v3→v4 映射：`focus_only` ↔ `focus`） |
| 「目标调到 0.97」 | `adjust 0.97` | `goal.target: 0.97` |
| 「128b 场景豁免 goal」 | `clear 128b` | 删 `goal.per_scenario.128b`（回退全局 `goal.target`） |
| 「不要 goal 了」 | `clear` | 删 `goal.target` + `goal.per_scenario`（presence 全清） |
| 「进入探索期」 | `mode explore` | 写顶层 `exploration_mode: explore`（`resolve_exploration` → `skip_goal_stop`；goal 段不动） |
| 「看当前 goal」 | `show` | 只读 `check_goal.py .` |
| 「看全场景矩阵」 | `show --all` | 只读 `manage_goal.py show --all` |

**v3 → v4 字段映射（写在维护仓 spec §6；老 reader 兼容 shim 已废弃，新 reader 仅认 v4 字段）：**

| v3（弃） | v4（当前） |
|----------|------------|
| `agent.goal_value` | `goal.target` |
| `agent.scenario_goals` | `goal.per_scenario` |
| `agent.goal_stop_mode: focus_only` | `goal.policy: focus` |
| `agent.goal_stop_mode: all_in_scope` | `goal.policy: strict` |
| `agent.goal_spec` | `agent.goal_spec`（保留；`parse_goal_spec(agent)` 读路径不变） |

**多 metric 复合门槛**（单/多场景 × 单/多 metric 的 4 组合）：单场景单 metric → `goal.target`；多场景单 metric → `goal.per_scenario` map；任一多 metric → **`agent.goal_spec`**（predicate 列表；详见 PROTOCOL §7.2.1a）。
