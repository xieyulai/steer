---
name: auto-nn-reflect
description: >-
  手跑仅反思轮（不训练）：reflect.py、REFLECT_INDEX、撞墙分析、更新 EXPERIENCE 反思块。
  不计入 auto-run 的 N。禁止 train.py 与改 workspace/contract。
  NL: 反思|reflect|撞墙分析. NOT: 要训练→manual-run.
---

## Code Contract（pilot，2026-07-15）

> `scripts/check_skill_contract.sh` 自动对账本段与 `template/package/*` 实际符号。
> 失败 → release-check 第 6 步门禁拦截。
> **强检字段**（对账失败即拦截）：`calls_scripts` / `reads_cfg_keys` / `env_vars_consumed`；其余（`pluggable_symbols` / `referenced_gates` 等）为 informational，release-check 不强检。

```yaml
calls_scripts:
  - scripts/mark_reflect_consumed.py       # pending 移至历史（auto-run / 手调）
  - scripts/mark-reflect-consumed.sh       # pending 移至历史（shell 包装）
  - scripts/repair_reflect_index.py        # 修复 REFLECT_INDEX 历史表结构
  - scripts/repair-reflect-index.sh        # 修复历史表（shell 包装）
  - scripts/check_reflect_runtime.py       # 运行时检查（auto-nn-update / nn-doctor 门禁）
  - scripts/clear_reflect.py               # C5 归档 reflect 产物并重置 pending
  - scripts/external_tool.py               # Phase 1.85 文献原子工具（手跑调试）
  - scripts/append-skill-activity.py       # 活动日志（reflect 结束 append）
  - scripts/auto-nn-update.sh              # 治理缺失提示（runtime FAIL 时告知用户跑）
  - scripts/e_feedback.py                  # 人点名本技能时读 pending / 人答后 resolve

reads_cfg_keys:
  - agent                                  # 父键（reflect_force/skip/interval/plateau_rounds/skill_activity_log/reflect_evidence_recent/scenario_default）
  - agent.skill_activity_log               # 活动日志开关（SKILL.md 末尾）
  - agent.reflect_force                    # 强制触发 reflect（run_ledger_summary.agent_reflect_flags）
  - agent.reflect_skip                     # 跳过 reflect（同上）
  - agent.reflect_interval                 # 自动 reflect 间隔（agent_config）
  - agent.plateau_rounds                   # plateau 阈值（agent_config）
  - agent.reflect_evidence_recent          # 反思证据窗口（reflect_evidence.load_reflect_evidence_config）
  - agent.scenario_default                 # 默认 scenario（reflect_evidence._focus_scenario_id）

env_vars_consumed:
  - NN_AGENT_CLAUDE_CMD                    # Agent CLI 前端可覆盖（reflect._call_agent）
  - NN_AGENT_CALL_TIMEOUT                  # 单次 Agent 调用超时（reflect._agent_call_timeout）
  - NN_CC_SWITCH_HOME                      # 子进程 HOME 覆盖（reflect._call_agent）
  - NN_RELAUNCH                            # reflect 重启判定（reflect 末尾）
  - NN_REFLECT_FORCE                       # 环境强制 reflect（run_ledger_summary.agent_reflect_flags）
  - NN_REFLECT_SKIP                        # 环境跳过 reflect（同上）
  - NN_REPAIR_APPLY                        # repair_reflect_index 实际写入开关
```

# auto-nn-reflect — 手跑仅反思

权威规则：`PROTOCOL.md` §7.6；INDEX 与 pending 见 `references/REFLECT_INDEX.md`。

**不计入** `./auto-nn-run.sh` 的实验轮次 N。

## 高频代号（人话见 glossary）

| 内部码 | 对用户怎么说 |
|--------|--------------|
| `[反思]` | 写进经验文档的一段反思 |
| `REFLECT_INDEX pending` | 待消费的反思建议 |
| `plateau` | 连续多轮没提升（撞墙） |
| `Tier 梯子` | 下一步该往哪个成熟度档位 + 创新深度（routine/extend/novel）走 |
| `Innovation` | routine（经典现成）/ extend（论文级）/ novel（研究性） |

## 入口（统一走 reflect.py）

| 入口 | 命令 | 更新 REFLECT_INDEX pending |
|------|------|---------------------------|
| **手跑** | `poetry run python reflect.py` | **是** |
| **编排** | `./auto-nn-run.sh reflect` | **是**（同 reflect.py） |
| **多轮** | `./auto-nn-run.sh N reflect` | 门禁通过时 **是**（见 `auto-nn-auto-run`） |

**禁止** Agent 手写 `[反思]` 而不跑 `reflect.py`（无 pending = 下轮实验无法强制消费）。

## reflect.py CLI flags

`--agent`（默认 `claude`）与 `--external-dry-run` 见上文入口 / Phase 1.85 节。其余 flag：

| flag | 默认 | 用途 |
|------|------|------|
| `--max-tokens` | 2048 | Phase1/Phase2 Agent 输出上限 |
| `--skip-phase2` | off | 跳过 phase2 联网搜索（调试） |
| `--skip-synthesis` | off | 跳过 synthesis 综合推理；回退现有 one_liner |
| `--skip-phase0` | off | 跳过 Phase0 大模型压缩；仅用规则摘要 |
| `--phase0-max-tokens` | 4096 | Phase0 输出 token 上限 |
| `--phase0-out-chars` | 12000 | Phase0 产出注入 Phase1 前最大字符数 |
| `--no-compress` | off | 关闭全部压缩（无 Phase0/规则摘要/jsonl rollup） |
| `--experience-raw-max` | 24000 | EXPERIENCE.md 超此字符数触发 Phase0/规则摘要 |
| `--experience-digest-chars` | 10000 | EXPERIENCE 摘要最大字符数 |
| `--protocol-digest-chars` | 6000 | 规则回退时 PROTOCOL 首部节选最大字符数 |
| `--last-reflect-chars` | 4000 | 最近 [反思] 块注入 Phase1 最大字符数 |
| `--jsonl-rollup-at` | 48 | jsonl 展平行数超此则附加 rollup 提示 |
| `--tier-stats-rows` | 30 | Tier 标签统计所用最近 N 行 description |
| `--reflect-gate` | "" | 覆盖 gate 标签（测试/auto-run 对齐） |
| `--run` | None | auto-run 轮次号；未指定用手跑默认 |

## reflect helper 脚本

| 脚本 | 用途 |
|------|------|
| `scripts/mark_reflect_consumed.py`（`.sh`） | 将 REFLECT_INDEX pending 移至历史（auto-run / 手调） |
| `scripts/repair_reflect_index.py`（`.sh`） | 修复 REFLECT_INDEX 历史表结构 |
| `scripts/check_reflect_runtime.py` | reflect 运行时检查（auto-nn-update 硬门禁 / nn-doctor reflect_runtime） |
| `scripts/clear_reflect.py` | C5 归档 reflect 产物并重置 pending（不动 TSV/exp/EXPERIENCE/keeper） |

## 开始前

- [ ] Read `_runs/results.tsv`、`_runs/results.jsonl`、`EXPERIENCE.md`（**Tier 状态 二维矩阵**（A–E × routine/extend/novel）+ §Tier A–E + §7.5.1a 创新维）；可选 `saved/innovation_audit.json`、`saved/experiment_journal.json`
- [ ] 若存在：`_runs/round_decision.json`
- [ ] 人工强制/关闭自动 reflect：`nn-config.yaml` `agent` 段 → `agent.reflect_force: true` / `agent.reflect_skip: true`（reader：`run_ledger_summary.agent_reflect_flags` 读 `agent` 段；**不在** `HUMAN_GUIDANCE.md` 写 `reflect:`）

## 执行

- [ ] 在项目根运行：`poetry run python reflect.py`（或 `./auto-nn-run.sh reflect`；可选 `--agent claude|cursor`）
- [ ] 确认 stderr/日志：已 append `EXPERIENCE.md` 的 `## [反思]` 块
- [ ] 若有 `WARN experience_tam`：EXPERIENCE **Tier 状态** 与 `saved/tier_attestation.json` 不一致 → 下轮更正（**以 TAM 为准**）
- [ ] 若有 `WARN innovation_audit`：检查 EXPERIENCE 二维矩阵与 `innovation_depth` 声明是否矛盾 → 更正矩阵（以 reflect 审计 + EXPERIENCE 实际格子为准）
- [ ] 确认 `references/auto/*_auto_reflected.md` 与 `references/REFLECT_INDEX.md` 的 **待消费** 已更新（至多 1 条；应同时包含 `[TAM: …]` 与 `[Innovation: …]`）
- [ ] **禁止**在本轮修改 `train.py`、`workspace/`、`contract/`、`experiment.py`。
- [ ] **改题待办**：`reflect.py` 三条齐全则只**记账**（`e_feedback.jsonl`），**不等待人答**。若本技能是**人点名**的手跑反思（不是 auto-run 脚本拉起）：跑完后 `python3 scripts/e_feedback.py pending --repo-root .`，有待审则只问一句留下/搁置/驳回；人答则 `resolve`，**只改记录、不改实验**。auto-run 内的 reflect **只记账、不问**。
- [ ] 反思块「下轮建议」须映射 **二维梯子**（例如 B-routine 穷尽 → 优先 B-extend，而非直接升 C）；**禁止**仅凭 TAM `B:att×n` 就说“该档已穷尽”；**禁止** E=更长训练/OOM/算力；文献方案写 C 或 D + 路径

## Phase 1.85 — 外部证据（reflect 内自动查文献）

`reflect.py` 在 Phase 1 LLM 之前自动跑 **Phase 1.85**：按 Tier / 创新维 / 门禁确定性编排 arXiv、OpenAlex、文档、GitHub 等检索，写入 `saved/evidence_bundle.json` 与 `saved/external_plan.json`，并把已验证摘要注入 Phase 1 prompt。

| 要点 | 说明 |
|------|------|
| **人话** | 外部论文与文档证据由 reflect 脚本查，不是 Agent 临场编的 |
| **硬约束** | Agent **禁止手搓 arXiv url** 或引用 bundle 外链接；bundle 空时 prompt 明示「禁止编造 url」 |
| **non-fatal** | Phase 1.85 失败 / 缺 key / 无网 → skip 或空 bundle，**不阻断** reflect 后续 Phase |
| **手跑调试** | `python3 scripts/external_tool.py arxiv -q "..."` 等（说明文档仅模板仓 `docs/nn-literature/atomic-tools.md`，不分发到业务仓）；**不写** REFLECT_INDEX pending |
| **优先级** | **待消费** pending 仍是下轮实验硬约束；evidence bundle 仅为 Phase 1/2 参阅，**不取代** pending |
| **bundle 定位** | `saved/evidence_bundle.json` 是当轮检索真源，**不是** pending 的替代品；下轮方向仍以 INDEX pending + HUMAN 路线图为准 |

可选：`reflect.py --external-dry-run` 只写 plan、不调 HTTP（维护者验编排）。

## 边界

- 实验轮后的 **自动 reflect + 门禁 R1–R7**（探索期 R7=coverage_stall）→ `auto-nn-auto-run`，不在此展开；探索期 pending 须服从 HUMAN NOTE 网格
- 手跑一轮 train + KEEP → `auto-nn-manual-run`

## 下一步常见推荐

反思前理清趋势 → **`/auto-nn-analyse`**；按 pending 落地 → **`/auto-nn-manual-run`** 或 **`/auto-nn-human-guidance`**；多轮自动门禁 reflect → **`/auto-nn-auto-run`**。完整串联图见 [`skills/post-migration/README.md`](../README.md)。

## 对用户怎么说（人话）

- **反思结论**：「连续 N 轮没提升 / 建议下轮试 X 方向 / 成熟度档建议往 extend 走」；禁裸 `plateau`/`Tier B`/`REFLECT_INDEX pending`。
- **创新维**：用「经典现成 / 论文级 / 研究自创」；括号可写 routine/extend/novel **一次**。
- **不训练**：明确「这轮只反思不改代码」；勿贴 `[TAM: …]` 原文 unless 用户要细节。
- **改题待办**：人点名本技能且有待审时，结论后追加一句三选一；自动多轮里的反思只说「记了一条改题建议，稍后分析/反思再处置」，**不停 batch**。

**坏**：「REFLECT_INDEX pending: Tier C fail-safe 分支 2；plateau_streak=3」  
**好**：「撞墙了：连续 3 轮主指标没涨。建议下轮在「论文级改进」档试一个新 backbone，而不是再加训练轮数。」

## 活动 log

`reflect.py` 成功结束后 **须** append：`python3 scripts/append-skill-activity.py append --skill auto-nn-reflect --phase end --summary "pending 已消费"`。开关 `agent.skill_activity_log`（默认 true）。
