# 指标体系与 KEEP/DISCARD 机制

**Modify Track（2026-05-22）：** 涉及改台账/场景/训练实现时，代号与对人话术见 `CONTEXT.md` §Modify Track。

本文说明模板的指标定义方式和实验结果保留（KEEP / DISCARD）决策逻辑。
面向项目迁移者和 Agent 常规迭代者。

---

## 1. 两个核心属性

contract 子类必须实现 `metric_keys`，可选实现 `auxiliary_keys`：

```python
class Contract(ExperimentBase):

    @property
    def metric_keys(self) -> dict[str, str]:
        """主指标 {key: direction}。第一个 key = 台账主列。"""
        return {"val_accuracy": "maximize"}

    @property
    def auxiliary_keys(self) -> dict[str, str]:
        """辅助指标 {key: direction}。用于 aux_guards 守卫和 TSV 记录。"""
        return {"val_loss": "minimize", "val_top2_accuracy": "maximize"}
```

**方向（direction）**：`"maximize"` 越大越好，`"minimize"` 越小越好。`should_keep`、TSV 排序、preflight 全依赖它。

**互斥约束**：`set(metric_keys) ∩ set(auxiliary_keys) == ∅`。preflight 阶段自动检查，违反则训练不启动。

**主指标特殊地位**：`metric_keys` 的 **第一个 key**（`self.metric_key`）在 TSV 中位于 **`experiment` 与必填 `scenario_id` 之后**（metrics 区首列）；同时是：
- `improve_mode=primary` 时的唯一判定依据
- `pick_keeper` 排序基准（在同类 `scenario_id` 可比集内）

---

## 2. 向后兼容派生属性

以下属性从 `metric_keys` / `auxiliary_keys` 自动派生，**新项目不要直接用**：

| 派生属性 | 来源 | 说明 |
|---|---|---|
| `metric_key` | `next(iter(metric_keys))` | 第一个主指标的 key |
| `metric_direction` | `next(iter(metric_keys.values()))` | 第一个主指标的方向 |
| `primary_metric_keys` | `tuple(metric_keys.keys())` | 全部主指标 key |
| `aux_metrics` | `dict(auxiliary_keys)` | 辅助指标 dict |
| `primary_metric_directions` | `dict(metric_keys)` | 主指标方向 dict |

旧代码中引用 `self.metric_key`、`self.aux_metrics` 等仍然有效，无需改动。

---

## 3. TSV 列生成

`_default_tsv_columns()` 按 **四区** 生成表头（左→右），便于 Agent 扫表与 KEEP 隔离。**`scenario_id` 为必填列**（对齐 F1 场景清单行 ID；单场景也需显式写入，常为 `default`）。`should_keep` **仅与同 `scenario_id` 的历史行**比较，**禁止**跨场景混比。

| 区 | 列 | 声明 / 来源 | KEEP |
|----|-----|-------------|------|
| **场景** | `experiment`；**必填** `scenario_id` | 实验名 + F1 场景清单 ID | 否（**KEEP 历史分池键**：与同 ID 行对比） |
| **metrics** | `metric_key`（主指标）+ 其余 `metric_keys` / `auxiliary_keys`（字母序） | contract | **是** |
| **parameters** | `ledger_context_keys` 各列 | `cfg` / `config.json` 回填 | **否** |
| **运行 / notes** | `elapsed_sec`、`git_commit`、`exp_dir`、`description`、`notes`、`timestamp` | 框架写入；`notes` 含人工备注 + 溢出指标 | 否 |

**列序（模板定稿，`scenario_id` 始终紧随 `experiment`）：**

```text
experiment | scenario_id | <metrics…> | <ledger…> | elapsed_sec | … | notes | timestamp
```

- **parameters** 与 **场景** 分离：`N_SIP`、`MODE`、架构标签等进 **parameters**（`ledger_context_keys`）；**不得**用它们代替 `scenario_id` 作为 KEEP 分池键。
- **`scenario_id` 对齐** F1「场景清单」行 ID（见迁移 inventory spec 与下文 §3.5）。
- **metrics** 区不含 `elapsed_sec`（算运行元数据，放末区）。
- 其余指标 = `sorted((metric_keys.keys() ∪ auxiliary_keys.keys()) - {metric_key})`。

示例（FashionMNIST 模板，无 ledger；省略具体 ID，实为 `scenario_id` 占位）：

```text
experiment  scenario_id  val_accuracy  val_loss  val_top2_accuracy  elapsed_sec  git_commit  exp_dir  description  notes  timestamp
```

TSV 列 **保证覆盖** `metric_keys` + `auxiliary_keys` + `ledger_context_keys` + **固定** `scenario_id`；preflight G-台账 检查表头一致；缺列或行前 ID 无效见门禁（`preflight`、`nn-doctor`）。

**训后 git：** `finalize_round` 追加 TSV/jsonl 后须 PROTOCOL §6 步骤 10 commit 台账；`nn-doctor` 的 `ledger_git` 对未提交/untracked 发 WARN。

### 3.1 `notes` 列（人工备注 + 溢出指标）

| 列 | 职责 |
|----|------|
| `description` | 流程标签（`train.py 单次训练`、`finalize_round（多槽汇总）`） |
| `notes` | 实验语义：人工备注 + 未在 contract 声明的 metrics 键 |

**写入**（`append_tsv_row` / `append_jsonl_record` 经 `_append_repo_ledger_row` 一次构建、双写）：

- TSV 与 JSONL **均写入 `scenario_id`**（同解析源；JSONL `schema_version=2`）。
- `notes` 规则：

```text
<NN_NOTES 或 notes= 参数> || k1=v1; k2=v2
```

- 人工：`export NN_NOTES="本轮单一变量摘要"`（训练前，与 commit 同轮）。
- 溢出：`metrics` 中不在 `metric_keys ∪ auxiliary_keys` 的数值键，按 `k=v` 用 `; ` 拼接。
- **不参与** `should_keep`；要进 KEEP 对比的键须列入 contract。
- 长文仍写 `EXPERIENCE.md`。

**表头迁移**：`python3 scripts/regen_results_tsv.py --repo-root .`

### 3.2 台账分级（迁移 **E2-metric-tier**）

| 级别 | 声明位置 | TSV | KEEP |
|------|----------|-----|------|
| primary | `metric_keys` 首键 | 主列 | 是 |
| auxiliary | `auxiliary_keys` 或额外 `metric_keys` | 列 | 视 `improve_mode` |
| notes_only | 不声明 | `notes` 溢出 | 否 |

**三铁律：**

1. 进 KEEP 对比的键必须在 contract 的 `metric_keys` 或 `auxiliary_keys` 中声明。
2. 仅展示、不参与 KEEP 的标量 → `notes` 溢出（或 `results.json` 全文）。
3. 同一 `_runs/results.tsv` 可混多场景行；**KEEP 不得跨场景混比历史** — 靠 **`scenario_id` 列分池**。旧版 `history_experiment_substr` **已废弃**（见 §5）。

### 3.3 `ledger_context_keys`（运行参数列，迁移 **E7-run-context**）

| 级别 | 声明位置 | TSV 区 | KEEP |
|------|----------|--------|------|
| ledger_context | `contract.ledger_context_keys` 元组 | **parameters**（metrics 区之后） | **否** |

- 键名须与 `finalize_run` 传入的 `cfg` 字段一致（如 `N_SIP`、`MODE`、`NORM`）。
- 与 `metric_keys` / `auxiliary_keys` **互斥**；preflight 与 `_check_metric_key_exclusive` 会检查。
- **推荐（多场景 physical）**：`("N_SIP", "MODE", "NORM")` 等由 F1 锁定；探索目标用 `agent.scenario_*` + `scenario_bindings` / `contract.agent_scenario_bindings` 结构化传给 Agent（见 `build_agent_scenario_manifest`）。
- 表头迁移：`python3 scripts/regen_results_tsv.py --repo-root .`（从各 `exp_dir/config.json` 回填）。

### 3.4 强制 `scenario_id`（场景区，必填）

| 级别 | 声明 | TSV 区 | KEEP |
|------|------|--------|------|
| scenario | 列名 **固定** `scenario_id`（基类生成；不再使用可配置的 `scenario_tsv_column`） | **场景**（紧邻 `experiment` 后） | **否**（作历史分池键，不参与数值比较） |

- **写入**：`finalize_run` / 台账追加从 **Scenario ID resolution** 取值写入（优先级：`cfg["scenario_id"]` / `cfg["SCENARIO_ID"]` → `NN_SCENARIO_ID` → `nn-config.yaml` → `agent.scenario_default`）。  
- **门禁**：解析结果须 **非空** 且 **∈ F1 场景清单**，否则 preflight **FAIL**。  
- 与 `metric_keys` / `auxiliary_keys` / `ledger_context_keys` **互斥**。

### 3.5 与迁移场景清单的关系

清单 **场景 ID** → TSV **`scenario_id` 必填列**（`experiment` 名仅作人读标签）；**S_run 冻结档** → parameters 区；**主指标** → metrics 区。

---

### 3.6 keeper 映射（`saved/keepers.json`）

KEEP 基线指针按 **`scenario_id` 分场景**存放在 **`saved/keepers.json`**：**键** = 场景清单 ID，**值** = 与各场景对应的 keeper 元数据（`keeper_exp_dir`、`best_model_path`、`git_commit`、`updated_at` 等），与历史上单列 `saved/keeper.json` 字段风格一致；**`saved/keeper.json` 已不再作为读写真源**（若仍存在，`nn-doctor` / 迁移流程可能 WARN「待迁至 map」）。

| 时机 | 行为 |
|------|------|
| `finalize_round` 且 `keep_suggestion=true` | **自动**更新 **当轮 `scenario_id`** 在 map 中的 entry（stderr：`saved_keeper:`，含 scenario id） |
| `keep_suggestion=false`（含打平历史 best） | **不**更新任何场景的 keeper entry |
| 人工 adopt 基线 | 手动 `poetry run python -m contract write-keeper --exp-dir <exp_dir> --scenario-id <id>`（或从产物推断 `--scenario-id`） |
| smoke / 特殊回放 | `NN_SKIP_WRITE_KEEPER=1` 跳过自动写入 |

权重始终在 `_runs/exp/<keeper>/best_model.pt`；**禁止**复制到 `saved/keep/*.pt`（迁前遗留）。

### 3.7 Checkpoint（迁移 **E8-checkpoint**）

| 配置 | 说明 |
|------|------|
| `nn-config.yaml` → `checkpoint` | `best` \| `last` \| `none`；可被 `NN_CHECKPOINT` 覆盖 |
| 产物 | `exp_dir/best_model.pt`（权重留 exp 目录；policy=`none` 时不写） |
| `.pt` 内容 | `train_cfg`（完整可 JSON 的训练超参）、`metrics_official`（`contract.test`）、`state_dict`、`checkpoint_policy`、`selection` |

- **best**：训内 evaluate 主指标最优权重；无训内 eval 时回退训末最后一轮。  
- **last**：训末最后一轮权重（PINN / 无训内 eval 推荐）。  
- **none**：仅台账与 `config.json`，无 `best_model.pt`。

---

## 4. KEEP / DISCARD 决策

每次训练结束后 `finalize_round` 调用 `should_keep(current_metrics, history_rows)`，
对照 `_runs/results.tsv` 历史行决定本轮实验是否保留。

### 4.1 配置来源

优先级：`contract.keep_threshold`（非空 dict）> `nn-config.yaml` 的 `keep:` 段。

`keep_threshold` 返回空 `{}` 时走 yaml 默认值：

```yaml
keep:
  improve_mode: any_primary   # 决策模式
  mode: relative              # 绝对/相对比较
  primary_delta: 0.005        # 相对改善阈值（0.5%）
  near_best_abs: 0.0          # 绝对容差（默认关闭）
```

### 4.2 improve_mode 四种模式

| 模式 | 判定逻辑 | 适用场景 |
|---|---|---|
| **`primary`** | 仅看第一个主指标（`metric_key`）是否达标 | 单主指标项目（默认 fallback） |
| **`any_primary`** | 任一主指标达标即 KEEP | 多主指标、任一改善即可 |
| **`all_primary`** | 全部主指标达标才 KEEP | 多主指标、要求全面提升 |
| **`any_metric`** | 主指标 + 辅助指标任一改善即 KEEP | 探索阶段，允许辅助指标改善来保留 |

### 4.3 判定流程

```
should_keep(current_metrics, history_rows)
  │
  ├─ aux_guards 检查（辅助指标不能退步超过阈值）
  │   └─ 失败 → DISCARD "auxiliary guard 未通过"
  │
  ├─ 无历史行 → KEEP "无历史 TSV 可比"
  │
  ├─ improve_mode ∈ {any_primary, all_primary}
  │   ├─ 对每个 metric_key：查历史最佳 → 比较（mode + primary_delta）
  │   ├─ 支持 near_best_abs 容差
  │   └─ any: 任一通过 / all: 全部通过
  │
  ├─ improve_mode == any_metric
  │   └─ 遍历 metric_keys + auxiliary_keys 全部 key，任一严格改善或接近最佳
  │
  └─ improve_mode == primary（单指标 fallback）
      └─ 仅比较 metric_key
```

### 4.4 mode: relative vs absolute

- **`relative`**（默认）：改善量 = `(当前 - 最佳) / |最佳|`，与指标量纲无关。
  - `primary_delta: 0.005` = 相对改善 0.5%
- **`absolute`**：改善量 = `当前 - 最佳`（maximize）或 `最佳 - 当前`（minimize）。
  - 适用于指标值接近零的场景（relative 会爆炸）。

### 4.5 near_best_abs

绝对容差。当主指标未达 `primary_delta` 但与历史最佳差距在 `near_best_abs` 以内时，
仍判定为 KEEP。默认 `0.0`（关闭）。

---

## 5. `history_experiment_substr`（**已废弃**）

先前允许在 contract 设置 `history_experiment_substr`，使 `should_keep` 只对照 `experiment`
列包含该子串的历史行。**模板已实现强制 `scenario_id` 分池**：KEEP 仅以 TSV **`scenario_id`**
列过滤历史；**请勿**依赖或新增 `history_experiment_substr`（遗留 override 可由 `nn-doctor` 告警直至 Modify-Scenario-complete 清除）。

---

## 6. 迁移检查清单

迁移项目时，以下检查必须通过：

```bash
# 互斥 + 非空
python3 -c "
from contract import create_contract; c = create_contract({})
assert c.metric_keys, 'metric_keys 不能为空'
overlap = set(c.metric_keys) & set(c.auxiliary_keys)
assert not overlap, f'重叠: {overlap}'
"

# TSV 列覆盖所有 key
python3 -c "
from contract import create_contract; c = create_contract({})
cols = c._default_tsv_columns()
all_keys = set(c.metric_keys) | set(c.auxiliary_keys)
missing = all_keys - set(cols)
assert not missing, f'TSV 缺列: {missing}'
"
```

---

## 7. 与 profiles.yaml 的关系

`profiles.yaml` 中每个 profile 的 `contract` 方法列表必须包含 `metric_keys` 和 `auxiliary_keys`。
`preflight_check()` 的 G-范式 检查会验证 contract 门面类实现了 profile 要求的全部方法。

---

## 8. explore 模式下的 KEEP（objective_mode: explore）

**默认 `optimize`** 时本章 §4–§5 完全适用。显式开启 **explore** 后，`should_keep` 在 **不放宽 aux_guards** 的前提下追加 **OR 分支**（主指标未改善仍可 KEEP）。

| 规则 | 含义 |
|------|------|
| `scenario_debut` | 该 `scenario_id` 首条有效 TSV train 行 |
| `first_in_cell` | 该 `(tier 标记, scenario_id)` 在台账中首次出现 |
| `attested_novel` | TAM attested 证伪（探索链保留） |

- reason 前缀 **`explore:`**；keeper 更新路径与 optimize 相同（`saved/keepers.json[scenario_id]`）  
- **`metric_leader`** 仍独立按 TSV 计算；**不得**将 explore keeper 叙述为 SOTA  
- Run Context 双锚：`metric_leader=…` + `code_baseline=… (explore chain)`  

完整操作说明、HUMAN NOTE 格式、reflect R7、迁移/modify 前置见 **`explore-objective-mode.md`**。
