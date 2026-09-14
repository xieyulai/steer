---
name: auto-nn-auto-run
description: >-
  迁后多轮自动化：auto-nn-run.sh、N 轮实验、reflect 变体、注入 HUMAN 路线图、
  轮末 round-doctor + 轮初漂移/pluggable/TAM/创新维 注入、实验模式与 goal 达标即停
  （explore 跳过 goal 硬停）、探索期 R7 reflect、场景 manifest / scenario_bindings /
  scenario_id 一致性、reflect 门禁。创新维（routine/extend/novel）与 A–E 正交，每轮必须在 EXPERIENCE 填写。不要在对话里手工模拟多轮实验。
  NL: 自动实验|batch|N轮|multi-round. NOT: 单轮→manual-run; 只分析→analyse.
---

# auto-nn-auto-run — 自动化编排

权威规则：`PROTOCOL.md` §7；场景分池见 mandatory-scenario-id design spec。

> **改码三原则**：实验轮 Agent 改 `train.py` / `workspace/` 须遵守 **config-only / no-fallback / pluggable**。训前 preflight：`G-cfg-no-defaults` FAIL、`G-no-fallback` WARN；`nn-doctor` 同规则扫描且 **`G-no-fallback` 为 FAIL**；本技能轮末 doctor FAIL 注入下轮 prompt。pluggable = 每轮 prompt 设计自检（非 scanner）。权威：**PROTOCOL §0.1**。

## 边界与交接（两态）

> **modify 标为人入口** — 实验 auto-run Agent **不要**嵌套 `/auto-nn-modify`；人在对话里改题面/metric/场景/立项式能力时才路由 modify。

| 角色 | 做什么 |
|------|--------|
| **人** | 改能力（`/auto-nn-modify`）；路线图（`/auto-nn-human-guidance`）；调 `exploration_mode` 等 |
| **实验 Agent（常规轮）** | 直接改 `config.json` 实验参数；直接改 `train.py`/`workspace/`（守 PROTOCOL §0.1）；**不**嵌套 modify；动 `contract/` 须人开 modify + `NN_RELAUNCH=1` 后重开 batch |
| **编排** | 注入 Run Context；门禁 reflect / HUMAN；轮末 round-doctor |

与 package `CLAUDE.md` §迁后 auto-run / §你可改·不可改（两态）同源；冲突以 PROTOCOL §0.1 与 CLAUDE 为准。

## Code Contract（pilot，2026-07-15）

> `scripts/check_skill_contract.sh` 自动对账本段与 `template/package/*` 实际符号。
> 失败 → release-check 第 6 步门禁拦截。
> **强检字段**（对账失败即拦截）：`calls_scripts` / `reads_cfg_keys` / `env_vars_consumed`；其余（`pluggable_symbols` / `referenced_gates` 等）为 informational，release-check 不强检。

```yaml
calls_scripts:
  # 主编排 auto-nn-run.sh / reflect.py 在 template/package/ 根（非 scripts/），lint 不解析 → 见 pluggable_symbols
  - scripts/build-run-context.py               # 每轮 Run Context 注入
  - scripts/summarize-runs.py                  # brief / --roadmap-status / --keeper-status
  - scripts/gpu_snapshot.py                    # 轮初 GPU 三档快照
  - scripts/inject_innovation_segments.py      # 创新指南 Tier 切片注入
  - scripts/human_guidance_gate.py             # HUMAN 硬门禁 check / post-round-enforce
  - scripts/validate-human-guidance.sh         # 人改路线图后校验
  - scripts/refresh-human-guidance-baseline.sh # batch 活跃时禁用（负向引用）
  - scripts/nn-doctor.sh                       # 轮末 round-doctor
  - scripts/check_goal.py                      # 轮末 goal 达标停 batch
  - scripts/check_metric_floor.py              # explore 底线 WARN
  - scripts/check_round_ledger_closure.py      # reflect 前台账闭合
  - scripts/check_multi_slot_finalize.py       # 多槽 finalize 检查
  - scripts/journal_append.py                  # 轮末 journal_append round
  - scripts/sync_ledger.py                     # TSV/jsonl 台账同步
  - scripts/mark-reflect-consumed.sh           # reflect pending 消费
  - scripts/wait-train.sh                      # 训练等待
  - scripts/auto-run-batch-tail.sh             # batch 尾部收尾
  - scripts/claude_stream_summarize.py         # Agent 流式摘要
  - scripts/claude_stream_result_watchdog.py   # 流式结果看门狗
  - scripts/check-env.sh                       # 环境校验
  - scripts/append-skill-activity.py           # 活动日志（agent.skill_activity_log）
  - scripts/compress-experience.py             # E1 轮末压缩（after_round）
  - scripts/auto-nn-update.sh                  # 开 batch 前 governance-sync

reads_cfg_keys:
  - agent                                  # 父键（agent.* 家族）
  - agent.skill_activity_log               # 活动日志开关
  - agent.run_context_injection            # 关闭 Run Context
  - agent.reflect_force                    # R1 强制反思
  - agent.human_guidance_gate_fail_fast    # HUMAN drift 整批 exit
  - agent.experience_auto_compress         # E1 压缩策略
  - keep.improve_mode                      # KEEP 判定（嵌套 keep_cfg）
  - keep.primary_delta                     # KEEP 判定（嵌套 keep_cfg）
  - goal                                   # 父键（goal.target / policy）
  - goal.target                            # 达标停 batch 阈值
  - scenario_active                        # rotate 轮换当轮场景
  - scenario_id                            # 逆向推断 / config.json 显式
  - exploration_mode                       # 6 档 mode（explore 跳 goal 硬停）
  - ledger                                 # governance_rev 漂移检查

env_vars_consumed:
  - NN_REFLECT_FORCE                       # R1 强制反思
  - NN_NOTES                               # 轮次备注（PROTOCOL §6）
  - NN_AUTO_RUN_REQUIRE_GOV_SYNC           # governance-rev 漂移硬停（shell 读 → WARN）
  - NN_AUTO_RUN_SKIP_LEDGER_CLOSURE        # 跳过台账闭合（shell 读 → WARN）

pluggable_symbols:                         # 仅 informational，lint 不强检
  - auto-nn-run.sh                         # 主编排（template/package/ 根，非 scripts/）
  - reflect.py                             # 反思编排（template/package/ 根，非 scripts/）
  - build_agent_scenario_manifest          # 正向 bindings → NN_* env
  - format_agent_scenario_prompt_block     # scenario manifest prompt 块
  - gpu_snapshot.load_gpu_agent_config     # 读 agent.gpu_* 阈值
  - inject_innovation_segments.render_tier_slice  # 5×3 Tier 切片
  - finalize_run / finalize_round          # 逆向 scenario_id 写 TSV
```

```bash
./auto-nn-run.sh <N>
./auto-nn-run.sh <N> reflect
./auto-nn-run.sh reflect
```

**CLI flag**（位置参数 `<N>` / `reflect` 之外）：

| flag | 说明 |
|------|------|
| `--agent auto\|claude\|cursor` | Agent 后端（默认 auto：claude 在 PATH 则 claude，否则 cursor） |
| `--claude claude\|ccg\|ccm\|ccmm\|ccx` | Claude/cc-switch 前端（仅 `--agent claude` 分支） |
| `--model <name>` | Cursor 模型（仅 `--agent cursor` 分支） |
| `-h` / `--help` / `help` | 显示用法并退出 |

**并行默认**：每轮注入的 prompt（auto-nn-run.sh）已翻转默认——`≥2 独立 OVAT 候选 ∧ max_parallel≥2` → 并行（slot 与 GPU 解耦，单卡可多 slot 共享）；OVAT≠serial。行为权威在 PROTOCOL §6。

**GPU 三档快照**：轮初 `scripts/gpu_snapshot.py` 读 nvidia-smi，分 exclusive（近空独占）/ shareable（可同卡插队）/ busy（勿加任务）；写入 RUN CONTEXT batch 段与 Hardware prompt；`nn-config.yaml` `agent.gpu_*`（agent 段）可调阈值与单槽预估显存（reader：`gpu_snapshot.load_gpu_agent_config` 读 `agent` 段，非顶层 `gpu.`）。

## 高频代号（人话见 glossary）

| 内部码 | 对用户怎么说 |
|--------|--------------|
| `batch` | 多轮自动跑（一批实验） |
| `scenario_bindings` / `manifest` | 场景到参数的映射规则 |
| `scenario_id` | 实验场景（不同场景成绩不能混着比） |
| `R1–R6` | 触发反思的几种条件 |
| `R7` | 探索期覆盖停滞时额外触发反思 |
| `experiment_mode` / `goal` / `metric_floor` | 实验模式；目标达标即停（explore 跳过）；探索底线 WARN |
| `G-HUMAN` / `baseline` / `drift` | 路线图保护，防跑着被偷改 |
| `Run Context` | 每轮喂给 Agent 的现状简报 |

## 开跑前（批次级）

- [ ] Read `nn-config.yaml` → `agent.scenario_*` + README `SCENARIO_POLICY` 场景全貌（manifest prompt 块已注入）
- [ ] `scenario_completeness_gate` / `nn-doctor` 场景项无 FAIL
- [ ] 确认 **`scenario_bindings`**：
  - **正向**（`build_agent_scenario_manifest(apply_env=True)`）：`scenario_default` → `NN_*` env
  - **逆向**（`finalize_run`）：train cfg → 推断 **`scenario_id`** 写 TSV
  - 两向共用同一套 bindings；多场景仓 bindings **须覆盖所有区分维**（例 PINN：MODE + GAMMA + N_SIP）
- [ ] `HUMAN_GUIDANCE.md` 路线图若点名场景（如 2sip）→ 与 `scenario_active` / 当轮 **config.json `scenario_id`** 一致
- [ ] **多场景仓训前 dry-run**（改 train 场景轴前，与 manual-run 同源）：

```bash
python3 -c "
import sys; sys.path.insert(0,'scripts')
from pathlib import Path
from lib.scenario_inventory import resolve_scenario_id
cfg = {...}  # 与当轮 train.py / manifest 意图一致
print('resolved scenario_id:', resolve_scenario_id(Path('.'), cfg))
"
```
- [ ] **开局检索** `baseline_tag=plain`；有则不再立 plain；无则可跟 plain-anchor-init 做一轮。
- [ ] 前 10 轮**禁止**自动设 `baseline_tag=reference`。满 10 轮仍无公开对照 → 跟 `### reference-anchor-init` 走 `/auto-nn-reference`（可自动贴）。

## 注入

**每轮 Run Context**（A1 全量，与 `/auto-nn-analyse` 同源脚本）：

- `summarize-runs` brief（metric_leader / code_baseline / plateau）— **metric_leader 按 focus scenario 分池**
- `--keeper-status`（**`saved/keepers.json` 按 scenario_id map**）
- **MA-1 brief-oneline** + **journal 尾部** + **last_recommendation**（Run Context；无 progress.txt）
- **recent ledger window**（近 K 行 TSV `delta_vs_leader` / summary；事实陈述，非 stage）
- **keeper recipe keys**（focus keeper 的 config 键摘要，有则注入）
- **goal_progress** / **metric_floor_progress**（有配置时；explore 跳过 goal 硬停仍显示进度）
- **`scenario_bindings` env 白名单实际值**（Run Context §env）
- **`## 当前阶段的创新指南`**（按 Tier 切片自 `references/manual/abcde-manual.md`：读 `EXPERIENCE.md` Tier 状态矩阵 → 最高 rank cell → manual 对应 cell；缺失 manual/EXPERIENCE → 空操作 drift-lock）
  - 实际注入逻辑见 `template/package/scripts/inject_innovation_segments.py` `render_tier_slice()`（切片 5×3 表对应 cell 注入 prompt）
- `round_decision` 一行
- 落盘 `saved/run_context.md`

**每轮 Agent prompt 另含 scenario manifest**（`build_agent_scenario_manifest` → `format_agent_scenario_prompt_block`）：

- `scenario_axis` / `scenario_policy` / `default` / `active`
- `env_applied` / `env_skipped`（bindings 正向是否生效）

非空 `HUMAN_GUIDANCE.md` 时，额外注入：

- **`## 公平约束`**（有正文时；与阶段无关，全程遵守）
- **`## 路线图`** 全文（有 `### 阶段` 时）
- `summarize-runs --roadmap-status`（inferred_phase、criteria_met）

空路线图 → 不注入路线图块；**仍注入公平约束**（若有）。Run Context **仍每轮注入**。

关闭 Run Context：`nn-config.agent.run_context_injection: off`。

## 轮末结构体检与三原则（round-doctor）

`auto-nn-run.sh` 每轮自动闭环（**不阻断 batch**；FAIL 由下轮 Agent 修）：

| 时机 | 动作 | 产物 |
|------|------|------|
| **轮末** | `bash scripts/nn-doctor.sh` | `_runs/doctor_reports/R{N}.log` |
| **轮初** | 上轮有 FAIL → 注入 `## Doctor R{N-1} 漂移报告` | Agent prompt 头部 |
| **轮初** | 总是注入 `## Pluggability 原则` | 设计自检（非 FAIL 门禁） |
| **轮初** | 总是注入 `## TAM 共改与 config 举证` | 读 `saved/tier_attestation.json` 的 `[TAM: …]`；OVAT 勿共改 `data_process.py` |
| **轮初** | 总是注入 `## 创新维度（routine/extend/novel）` | 读上一轮 `saved/innovation_audit.json`（若有）；`innovate` 实验模式加强 extend/novel；每轮必须填 `innovation_depth` + `rationale` |
| **轮初** | explore 有效时注入 `0e. EXPLORE MODE` | HUMAN NOTE **高于** REFLECT pending；`reflect_ack` 对照探索网格 |
| **探索训末** | `upsert_finalize_tam_row`（仅 explore） | 预写 `saved/tier_attestation.json` 片段供证伪 KEEP；reflect Phase 0.6 仍全量重建 |

- **scanner（2/3）**：`G-cfg-no-defaults`（config-only）+ `G-no-fallback`（doctor 档 **FAIL**）
- **prompt 自检（3/3）**：pluggable — 新增不影响存量；重构须在 config.json 显式保留老值（**禁止** `cfg.get(KEY, default)` 静默兜底）
- **TAM 一致性**：`attested/not_attested` **以 `saved/tier_attestation.json` 为准**；勿用 EXPERIENCE `## Tier 状态`（二维矩阵）覆盖；写「已深/浅尝」时 TAM 该档不得 `not_attested`（reflect stderr WARN）

**三条 doctor 反馈通道（勿混）**：

| 通道 | 何时 | 产物 | 消费者 |
|------|------|------|--------|
| **round-doctor**（本技能） | 每轮实验末/初 | `_runs/doctor_reports/R{n}.log` → 下轮 prompt | Agent 批内修漂移 |
| **init 阶段 4** | 迁完验收 | `saved/doctor_last.txt` 首基线 | `/auto-nn-analyse` diff |
| **analyse 静默前置** | 人工分析时 | 覆盖 `doctor_last.txt` | 给人看的结构恶化 |

## 场景一致性（Agent 每轮必守）

| `scenario_policy` | Agent 行为 |
|-------------------|------------|
| **`focus`**（或空） | 默认只跑 **`scenario_default`**；改场景轴参数 = 换场景，须在 **config.json 写 `scenario_id`** 或靠完整 bindings 推断 |
| **`rotate`** | 按 **`scenario_active`** 轮换；**每轮** 生成 config.json，**显式 `"scenario_id": "<当轮 ID>"`**；train 参数与当轮场景默认配置一致 |
| **`multi_eval_one_train`** | 一次训练、多场景 eval 时按 README/PROTOCOL 约定；台账仍须每行合法 **`scenario_id`** |

**硬规则：**

1. 修改 **`contract.ledger_context_keys` 里决定场景含义的键**（如 `N_SIP`、`MODE`、`model_arch`）→ **换场景**，不是同池刷参
2. **禁止**只改 `train.py` 场景轴却指望 `experiment` 命名或 `scenario_default` 自动对齐
3. **禁止**跨 `scenario_id` 比较 KEEP / 写「新 SOTA」/ 更新错误 keeper 键
4. bindings 歧义或未配全时 → **config.json 显式 `scenario_id`**，不要赌 default
5. 轮末核对 TSV 新增行：`scenario_id`、parameters 与 manifest 当轮意图一致；stderr `saved_keeper:` 的键正确

**训后快速验：**

```bash
tail -1 _runs/results.tsv | cut -f1-3    # experiment, scenario_id, 主指标…
python3 -c "
import sys; sys.path.insert(0,'scripts')
from pathlib import Path
from lib.scenario_inventory import focus_scenario_id
print('focus:', focus_scenario_id(Path('.')))
"
```

## HUMAN 硬门禁（G-strict）

批次启动写 `saved/.human-guidance-baseline.json`（reflect-only 不写）。轮初 `human_guidance_gate.py check`；drift → skip Agent（`agent.human_guidance_gate_fail_fast: true` 整批 exit）。train preflight **G-HUMAN** 同样 FAIL。

**人改路线图：** 停 `./auto-nn-run.sh` → 改 `HUMAN_GUIDANCE.md` → `bash scripts/validate-human-guidance.sh` → `git commit` → 重开 batch（新 baseline）。

**batch 活跃时禁止** `scripts/refresh-human-guidance-baseline.sh` 及 `human_guidance_gate.py refresh`。drift 时：`git checkout <baseline.git_head> -- HUMAN_GUIDANCE.md`（`git_head` 见 `saved/.human-guidance-baseline.json`），**勿** refresh bypass。

**G-HUMAN-COMMIT（轮末）：** shell 在 `journal_append` 之后调 `human_guidance_gate.py post-round-enforce`；若 Agent commit/工作区改了 HUMAN，自动恢复 baseline；batch log 可出现 `G-HUMAN-COMMIT_REVERT` / `G-HUMAN-WS_REVERT`（ERROR 日志但 batch 继续）。

Agent **禁止** Write/Edit `HUMAN_GUIDANCE.md`；prompt 已注入同句。HTML 注释内 `### 阶段` **不计**入路线图阶段（见 `human_guidance_roadmap`）。

## EXPERIENCE 轮末压缩（E1）

`agent.experience_auto_compress`：`warn`（默认）| `after_round` | `off`（reader：`lib/experience_auto_compress.py` 读 `agent` 段，非顶层 `compress.`）。超阈值时 warn 写 log 或 after_round 调用 `compress-experience.py --preset standard --apply`（见 PROTOCOL §7.5.2–7.5.3）。

## 轮末台账 commit

`auto-nn-run.sh` 在 finalize 成功且 TSV 新增行后自动 `journal_append --event round`；轮末 WARN：台账未 commit、或 TSV 行数增但最近 commit 无 `_runs/results.*`。Agent prompt 含 PROTOCOL §6 **步骤 10**（训后 `git add` TSV/jsonl/**`saved/experiment_journal.json`**（若 journal 已写）/ EXPERIENCE / **keepers.json** 等）。**finalize 写盘 ≠ git 持久化。**

## 轮末 goal 与底线（loop 停止）

每实验轮末（finalize 之后）：

- `scripts/check_goal.py`：**optimize/innovate** 且设了 `goal.target` → `GOAL_MET` 时 **提前停 batch**；**explore 有效** → `GOAL_SKIPPED_EXPLORE`（exit 2），跑满 N
- `scripts/check_metric_floor.py`：explore + `agent.explore.metric_floor` 破线 → **WARN only**，不 break

设/改实验模式或目标值 → **`/auto-nn-goal`**（`mode` / set / show）；见 PROTOCOL §7.2.1。

## reflect 门禁

**不由 HUMAN_GUIDANCE 控制**（无 `reflect:` 行）。见 PROTOCOL §7.6 + `nn-config`：

- **R1**：`agent.reflect_force: true` 或 `NN_REFLECT_FORCE=1`
- **关闭**：`reflect_skip: true` 或 `reflect_interval: 0`
- **R2–R6**：plateau / DISCARD / interval 等
- **R7**（仅 explore）：连续 N 轮无覆盖进展 → `run:R7:coverage_stall`

`innovate` 实验模式**无**单独反思门禁（仅轮初创新维 prompt 加强）。

reflect / REB 的 metric_leader、keeper 摘要均 **按 scenario 分池**；场景标错则 reflect 结论不可信。

`./auto-nn-run.sh reflect` 与 `reflect.py` 等价（写 REFLECT_INDEX pending）。

**外部证据（Phase 1.85）**：仅在 `reflect.py` 内编排（论文 / 文档 / GitHub bundle）；`auto-nn-run.sh` **无额外改动**——batch 实验轮不单独调文献工具；reflect 触发时走同一 Phase 1.85（失败 non-fatal，不阻断 batch）。

**pending 消费（实验轮轮末）**：轮初有 pending 时，须 EXPERIENCE 最新块含有效 `reflect_ack:` 才 `mark-reflect-consumed`；缺失 → batch log WARN、下轮注入提醒、batch 不中断（PROTOCOL §7.6）。

**开 batch 前**：业务仓须 `/auto-nn-update`（模板 push 后）；`governance-rev` 漂移 → batch 启动 WARN（`NN_AUTO_RUN_REQUIRE_GOV_SYNC=1` 可硬停）。

**reflect 前台账闭合**：`check_round_ledger_closure.py` 检测未 finalize 多槽 / jsonl·TSV 漂移；FAIL → **skip reflect**（`reflect_skipped`）；`NN_AUTO_RUN_SKIP_LEDGER_CLOSURE=1` 可跳过。

## 下一步常见推荐

开跑前诊断 → **`/auto-nn-analyse`**；设目标/实验模式 → **`/auto-nn-goal`**；写/清空路线图 → **`/auto-nn-human-guidance`**；单轮 → **`/auto-nn-manual-run`**；场景补完 → **`/auto-nn-modify`**。完整串联图见 [`skills/post-migration/README.md`](../README.md)。

## 对用户怎么说（人话）

- **批次进度**：用「第 N/M 轮、在训/已收尾、主指标大概多少」；**不要**贴 Run Context 全文或 `MA-1` 块。
- **轮末/轮初注入**（doctor 漂移、三原则、TAM）：对用户只报「体检发现 X，下轮会提醒 Agent 改 Y」；检查名可「人话（G-no-fallback）」一次。
- **轮末改题待办**：若 pending>0，日志一句「有 N 条改题建议已记下；本批不等人。你稍后做分析或手跑反思时再处置」。**不问三选一、不决议、不停 batch、不改实验**。
- **场景**：说「当前场景是 reference/automatic」；禁裸 `scenario_id`（除非括号对照列名）。
- **贴 stderr/心跳**：可保留路径；结论须先一句人话（例：「这轮 accuracy 0.82，还没破最好 0.85」）。

**坏**：「Run Context 已注入 summarize-runs brief + keeper-status + MA-1」  
**好**：「第 3 轮训完了：准确率 0.82，历史最好仍 0.85；下轮继续按路线图扫学习率。」

## 改题待办（实验轮边界）

- 训末探索格子由 finalize 写好（A–D）；改题主张可进 `_runs/analysis/e_feedback.jsonl`（只记账）。
- **batch 不等人、不问处置**：有 pending 只打日志，继续 A–D。
- **禁止**实验 Agent：`e_feedback.py resolve`、手改 jsonl、改题面、代写 HUMAN。处置只在人点名 `/auto-nn-analyse` 或手跑 `/auto-nn-reflect` 时问一句，且只更新记录。

## 活动 log

batch 正常结束或用户停批后 **须** append：`python3 scripts/append-skill-activity.py append --skill auto-nn-auto-run --phase end --summary "N 轮完成"`（shell 已有 `journal_append round`；本 log 补 Agent 侧摘要）。开关 `agent.skill_activity_log`（默认 true）。

启动前确认 `HUMAN_GUIDANCE.md` 已按需填写或已清空为全自主；**多场景仓确认 `scenario_bindings` 已启用且与 F1 清单一致**。
