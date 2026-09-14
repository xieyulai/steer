---
name: auto-nn-modify
description: >-
  迁后改能力（Modify-L2/L3/T/Scenario）：metric、KEEP 口径、场景扩充/补完、模型、loss。
  加成绩表参数列（watchlist）≠ 本技能 → 改 nn-config + regen。
  对人须人话+Modify-前缀。运行态清理 → /auto-nn-clear。动 contract 须 NN_RELAUNCH=1。
  NL: 改能力|加metric|扩场景|capability. NOT: 调LR→manual-run; 加参数列→watchlist+regen; 清junk→clear.
---

# auto-nn-modify — 迁后能力修改（Modify Track）

> **读者 / 调用方：人（或人开的改能力会话）。实验 auto-run Agent 不要嵌套本技能；其边界见 CLAUDE / auto-nn-run 两态。**

> ⚠️ **Agent 必读：改实验参数前，先写 config.json！**
>
> **Config-Only 原则**：所有实验参数（LR、MODEL_ARCH、EPOCHS、SEED、scenario_id 等）**必须**先写入 `config.json`。
>
> - ❌ 禁止：直接改 train.py 常量，或用 `NN_LR=0.001` 环境变量
> - ❌ 禁止：在代码中 `os.environ.get("NN_XXX")` 读取实验参数
> - ✅ 正确：修改参数后，同步更新 config.json 示例
>
> **改码三原则**：所有 Modify 轨改码须遵守 **config-only / no-fallback / pluggable**。训前 preflight：`G-cfg-no-defaults` FAIL、`G-no-fallback` WARN；`nn-doctor` 同规则扫描且 **`G-no-fallback` 为 FAIL**。pluggable = 装饰类 + cfg 开关，不改 `build_*`。
> **收尾**：按 [`post-change.md`](../../../docs/nn-modify/post-change.md) **整轨命令链**跑完（含 regen / README 门 / smoke 等）；**禁止**只跑 `/auto-nn-doctor` 就宣称改完。体检是链内一步。权威：**PROTOCOL §0.1**。
>
> **不是本技能**：只改 `nn-config.yaml` 的 `ledger.watchlist`（加/删成绩表参数列）→ 改 yaml 后 `python3 scripts/regen_results_tsv.py --repo-root .`（台账同步；历史别名 Modify-L1 已退役）。

**对人说话：** 须 **人话全称（Modify-代号）**；禁止裸抛 L2/S-complete/Track S。速查见 `CONTEXT.md` §Modify Track。

## Code Contract（pilot，2026-07-15）

> `scripts/check_skill_contract.sh` 自动对账本段与 `template/package/*` 实际符号。
> 失败 → release-check 第 6 步门禁拦截。
> **强检字段**（对账失败即拦截）：`calls_scripts` / `reads_cfg_keys` / `env_vars_consumed`；其余（`pluggable_symbols` / `referenced_gates` 等）为 informational，release-check 不强检。

```yaml
calls_scripts:
  - scripts/append-skill-activity.py      # 活动日志
  - scripts/set-scenario-policy.py        # focus ↔ rotate 切换
  - scripts/check_goal.py                 # 达标停 batch
  - scripts/manage_goal.py                # goal 设/改/查/清
  - scripts/modify-config.py              # Config-Only 单键改
  - scripts/regen_results_tsv.py          # TSV 同步
  - scripts/modify-post-change.sh         # 改后按轨验收链（P1）
  - scripts/auto-nn-update.sh             # abcde-manual 补齐

reads_cfg_keys:
  - agent.skill_activity_log               # 活动日志开关
  - scenario_id                            # 训练·数据 / 场景·补完
  - scenario_active                        # 场景·切换策略
  - goal                                   # goal.target / per_scenario / policy
  - keep.improve_mode                      # Modify-L3 KEEP 口径（嵌套 cfg）
  - keep.primary_delta                     # Modify-L3 KEEP 口径（嵌套 cfg）

# 备注：以下不是 cfg.get 键，而是代码内常量/标记，下移到 informational 段
#   SCENARIO_POLICY    → README HTML 标记 + Python 标识符（见 set-scenario-policy.py）
#   LOCKED_DATASET     → contract 常量（题面保护；见 PROTOCOL.md §0.1（D 档数据拆两半））
#   METRIC_KEYS        → contract/metrics.py 模块级常量（见 contract/__init__.py import）
#   history_experiment_substr → profiles.yaml / PROTOCOL.md 文档键，非 cfg.get

env_vars_consumed:
  - NN_RELAUNCH                            # 触及 Modify-L/S 时重启批次
  - NN_NOTES                               # 轮次备注（PROTOCOL §6）
  - NN_GUARD_HUMAN_GUIDANCE                # post-change 强制恢复
  - NN_AUTO_RUN_ROUND                      # human_guidance_gate 轮次

pluggable_symbols:                         # 仅 informational，lint 不强检
  - @register_learner
  - @register_objective
  - build_learner / build_objective
  - build_optimizer / build_scheduler
  - ExperimentBase.apply_build_meta
  - contract.metrics.METRIC_KEYS           # 模块级常量（Modify-L2）
  - contract.metrics.SCENARIO_ID           # 模块级常量
  - contract.LOCKED_DATASET                # 范式锁常量（题面保护）
  - <!-- SCENARIO_POLICY -->                # README HTML 标记（set-scenario-policy.py）
```

## 高频代号（人话见 glossary）

| 内部码 | 对用户怎么说 |
|--------|--------------|
| （退役）Modify-L1 | ~~加参数列~~ → 改 `ledger.watchlist` + regen（台账同步，非本技能） |
| `Modify-L2/L3` | 加指标列 / 改打分口径 |
| `Modify-T1/T2/T3` | 换模型 / 改训练目标(loss) / 改数据 |
| `Modify-Scenario-complete` | 把场景信息补全 |
| `Modify-Scenario-expand` | 新增一个实验场景 |
| `NN_RELAUNCH=1` | 改了口径，需要重启批次重新生效 |

**权威（docs/nn-modify hub）**：[README](../../../docs/nn-modify/README.md) · [track-catalog](../../../docs/nn-modify/track-catalog.md) · [post-change](../../../docs/nn-modify/post-change.md)

| 人话 | 代号 | 触发语示例 |
|------|------|------------|
| ~~台账·参数字段~~ | ~~Modify-L1~~（退役） | 改 `ledger.watchlist` + `regen_results_tsv.py` |
| 台账·指标列 | **Modify-L2** | 新 metric / 改 KEEP 键 |
| 台账·KEEP 口径 | **Modify-L3** | keep 规则 |
| 训练·模型 | **Modify-T1** | 换 backbone |
| 训练·目标 | **Modify-T2** | 改 loss |
| 训练·数据 | **Modify-T3** | Dataset / env |
| 场景·补完 | **Modify-Scenario-complete** | TSV 无 `scenario_id`、keeper 未分池 |
| 场景·扩充 | **Modify-Scenario-expand** | F1 新增 Scenario ID |
| 场景·切换策略 | **Modify-Scenario-policy** | focus ↔ rotate、`scenario_active` |

附属：TSV 四区 → `docs/archive/metric-and-keep-system.md` §3、`PROTOCOL.md` §2.2–§3；场景术语 → `CONTEXT.md`。
**清台账 / 删 exp / 整仓 runs / 绿场** → **`/auto-nn-clear`**。

---

## 你怎么用（人）

| 你说… | 走哪条轨（人话，代号见括号） |
|--------|---------|
| 清 preflight / 整仓 / 绿场 | 运行态清理 → **`/auto-nn-clear`**（非本技能） |
| 加新 metric / 改 KEEP 口径 | 台账·指标列 / KEEP 口径（**Modify-L2 / L3**） |
| 换模型 / 改 loss | 训练·模型 / 目标（**Modify-T1 / T2**） |
| **场景补完** | 场景·补完（**Modify-Scenario-complete**） |
| **场景扩充** | 场景·扩充（**Modify-Scenario-expand**） |
| **focus 改 rotate / 改轮换列表** | 场景·切换策略（见下 §切换 focus/rotate） |

---

## 切换 focus ↔ rotate（Modify-Scenario-policy）

多场景项目（CSI 码率档等）从 **只盯一个场景** 改成 **轮着试几个场景** 时：

1. **先停** 正在跑的 `./auto-nn-run.sh N`（batch 启动时读配置，**中途改 yaml 不生效**）
2. **一条命令** 同步 `nn-config.yaml` 与 README `SCENARIO_POLICY` 块（勿手改两处）：

```bash
# 例：64b 固定 focus
python3 scripts/set-scenario-policy.py focus --active 64b --default 64b --verify

# 例：128–1024 轮换，goal 仍盯 default（64b）
python3 scripts/set-scenario-policy.py rotate \
  --active "128b,256b,512b,1024b" --verify
```

3. **commit** 后 **重开** batch：`./auto-nn-run.sh N`

**rotate 后 Agent 行为（框架约定，非项目特例）：**

| 点 | 说明 |
|----|------|
| 每轮场景 | `config.json` 写 `"scenario_id": "<当轮>"`，参数跟该档一致 |
| 轮换顺序 | Agent 按 manifest 的 active 列表安排（无硬编码 round-robin 脚本） |
| goal 停 batch | `check_goal.py` 仍走 `effective_goal(goal, sid)`（v4 `goal_spec`）或 `goal.target`（v2 back-compat）按焦点场景定，其他场景达标不会停 batch |
| KEEP | 各 scenario **分池**，勿跨池比 keeper |

可选：在 **`HUMAN_GUIDANCE.md`** 写轮换顺序（如「R1–R5 依次 64→128→…」），停 batch → 改 → commit → 重开。

---

## 何时必须用本技能

- **改能力**：新模型、loss、数据管线、新 TSV 列、metric、场景/KEEP
- **场景补完 / 扩充**：勿与「只加 watchlist 参数列」混为一谈
- **清 preflight、删 exp、reset、factory** → **`/auto-nn-clear`**
- 普通单轮扫参 → **`/auto-nn-manual-run`**

---

## 硬边界

- **禁止**改 `experiment.py`
- **禁止**手改 `_runs/results.tsv`、`_runs/results.jsonl`
- **禁止**在本技能做运行态清理（用 **`/auto-nn-clear`**）
- 新 `.py` 只进 `workspace/` 或 `workspace/scripts/`
- **layout 卫生（doctor `layout`）**：领域术语/速查放 **`docs/CONTEXT.md`**（勿在仓库根新建 `CONTEXT.md`）；一次性维护脚本放 **`workspace/scripts/`**，在根 `.gitignore` 对 `workspace/scripts/*` 加 **`!workspace/scripts/<name>.py`** 显式入库；**禁止**在 `scripts/` 或根目录新增非 `template/package/scripts` 白名单脚本
- **Modify-Scenario-expand**：**须先停** `./auto-nn-run.sh`；**禁止**在 auto-run 跑着时改 F1 场景清单
- 触及 **Modify-L**（或 **Modify-Scenario-expand** 触达 contract/test/metric）时 `export NN_RELAUNCH=1`。**Modify-Scenario-complete** 若只改 `nn-config` 场景字段 + backfill、**不动** contract/test/metric → 可无 `NN_RELAUNCH`；若删 `history_experiment_substr` 等 contract 变更 → **要** `NN_RELAUNCH=1`
- **无 `NN_RELAUNCH=1` 改 `contract/`**（含未 commit 工作区脏改）→ 训前 preflight **FAIL**、doctor **`immutable_path_guard` FAIL**，训练起不来。
- **所有 `build_*` 方法必须遵守可插拔构建原则**（见 `track-catalog.md` §Modify-T）：单一 cfg 参数选择变体，返回 `(obj, metadata_dict)`，`train.py` 调用处执行 `apply_build_meta(cfg, meta, "build_xxx")`
- **Config-Only 硬约束**：所有实验参数（LR、MODEL_ARCH、EPOCHS、SEED、scenario_id 等）通过 `config.json` 传入，**禁止**在代码中 `os.environ.get("NN_XXX")` 读取实验参数
- **题面保护（E 档）**：`contract/` 源文件（SCENARIO_ID/METRIC_KEYS）常规迭代**禁改**（PROTOCOL 级约定；reinit 场景可重审，须显式签字 + CHANGELOG 留 `BREAKING`）。`abcde_boundaries` doctor 检查已于 v1.16.0 退役，不再靠 doctor 门禁阻断。`references/manual/abcde-manual.md` 缺失 → 跑 `/auto-nn-update` 补齐。

---

## 与 explore objective 互斥（§14）

1. Explore 与改能力并行会污染批次与归因；改 contract/metric / 扩场景须 **停 auto-run**，并按需 **`NN_RELAUNCH=1`**。  
2. **Modify-Scenario-complete** apply 后 keeper 按场景重建，explore 覆盖计数从新场景首次出现重计。  
3. 迁中存在 `CHECKLIST.md` 时 **禁止**以 explore 作验收。  
4. 改完指标 / KEEP / 新场景后，恢复探索前由人走 **`/auto-nn-human-guidance`** 更新路线图；本技能不改 `HUMAN_GUIDANCE.md`。  
5. 换模型 / loss 用单轮或 `/auto-nn-manual-run` 验证后再续探索，不要在长批次中途改 workspace。

---

## Agent：改代码前（必填计划）

对齐轨与误判见 [track-catalog.md](../../../docs/nn-modify/track-catalog.md)；改后整链见 [post-change.md](../../../docs/nn-modify/post-change.md)。

1. 类型：**Modify-L / Modify-T / Modify-Scenario-complete / Modify-Scenario-expand**（可多选）
2. 将改文件
3. 是否 `NN_RELAUNCH=1`（及原因）
4. 是否改 README `SCENARIO_POLICY` 场景清单（**Modify-Scenario-expand**：新增行 / Tier E 重签 F1；`.auto-nn/migration-summary.md` 场景表为留档副本同步）
5. **README 同步计划**（[readme-sync-after-modify.md](../../../docs/archive/readme-sync-after-modify.md)）
6. **场景轨**：F1 清单 ID、backfill 推断规则、keeper 迁移映射

---

## Agent：改代码后（收尾）

**勿在 SKILL 内复制 Bash。** 优先：

```bash
bash scripts/modify-post-change.sh --track L|T|Scenario-complete|Scenario-expand|ledger-sync
# Scenario-complete 人审后：再加 --apply-backfill
# 跳过烟雾：--skip-smoke
```

权威逐步说明仍见 [`post-change.md`](../../../docs/nn-modify/post-change.md)。

**禁止**仅 `nn-doctor` PASS 就向用户宣称「改能力已完成」——须链内步骤一并完成后再 handoff。

---

## 典型链 · 别名对照

**下一步常见推荐**：清运行态 → **`/auto-nn-clear`**；改完跑一轮 → **`/auto-nn-manual-run`**；先看最好成绩分场景 → **`/auto-nn-analyse`**。完整串联图见 [`skills/post-migration/README.md`](../README.md)。

**典型链**：`/auto-nn-analyse` → **`/auto-nn-modify`**（**Modify-Scenario-complete**）→ `/auto-nn-manual-run`；扩充：停 auto-run → 人签 F1 → **`/auto-nn-modify`**（**Modify-Scenario-expand**）→ 按 post-change → 恢复 batch。

### 别名对照（迁移期；勿对人裸用旧称）

| 旧称 | 新称 | 人话 |
|------|------|------|
| L1 | ~~Modify-L1~~（退役） | 加参数列 → `ledger.watchlist` + regen |
| L2 / L3 | Modify-L2 / L3 | 台账·指标列 / KEEP 口径 |
| T1 / T2 / T3 | Modify-T1 / T2 / T3 | 训练·模型 / 目标 / 数据 |
| S-complete | Modify-Scenario-complete | 场景·补完 |
| S-expand | Modify-Scenario-expand | 场景·扩充 |
| Track S | Modify-Scenario-* | 场景轨 |
| Track L / Track T | Modify-L* / Modify-T* | 台账轨 / 训练轨 |

## 对用户怎么说（人话）

- **改能力前**：用「人话全称（Modify-L2）」说明改什么；例：「给成绩表加一列指标（Modify-L2）」。
- **加参数列**：说「改成绩表要记哪些参数（watchlist），再重生表」——**不是**改能力。
- **NN_RELAUNCH**：说「改了打分口径，需要重启批次才生效」；禁裸 env 名除非用户要命令。
- **场景轨**：「补全场景分池 / 新增一个实验场景（Modify-Scenario-expand）」。
- **收尾**：按改后链跑完再 handoff；对人报「改后验收链通过（含结构体检）」——**禁止**只说「体检过了」。

**坏**：「走 Modify-L3 改 improve_mode + history_experiment_substr，export NN_RELAUNCH=1」  
**好**：「要改「怎么算更好」的规则（Modify-L3），改完需重启自动批次；我先停 batch，改完跑验收链确认。」

## 活动 log

用户确认改码 / **改后链**通过后 **须** append：

```bash
python3 scripts/append-skill-activity.py append \
  --skill auto-nn-modify --phase end \
  --summary "<人话改了什么；post-change track=…>" --lock "Modify-L2" \
  --artifacts contract/metrics.py
```

开关 `agent.skill_activity_log`（默认 true）；见 [`README.md`](../README.md)。
