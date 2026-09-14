# auto-nn-modify · 八轨判定目录

> **读者**：需要做迁后改路由的 Agent / 维护者  
> **总入口**：[`README.md`](README.md)

本篇按 CONTEXT.md §Modify Track 代号 八条 Canonical 代号展开：**信号 → 代号 → 可改路径 → `NN_RELAUNCH` → README 区块**。「可改路径」为典型清单，**不以**穷尽所有业务仓特例为目标。

---

## 误判：这些不是 Modify-L2/改能力

下列操作是 **台账同步 / 修复**，**不等于**改能力：

| 操作 / 话术 | ≠ 代号 | 实际归类 |
|-------------|--------|----------|
| 只改 `ledger.watchlist` + `regen_results_tsv.py` | ≠ **Modify-***（历史误称 L1） | **台账同步** |
| `python3 scripts/regen_results_tsv.py --repo-root .` **仅**对齐 TSV 与 jsonl | ≠ 改能力 | 同上 |
| 「同步账本」`sync_ledger` 类：**只**回填已有字段 | ≠ 改能力 | 同上 |
| **`backfill-scenario-tsv.sh`** / 场景 **`scenario_id` 补写** | — | **`Modify-Scenario-complete`** |

~~**Modify-L1**~~（退役）：旧指 parameters 区新键；现行一律走 watchlist + regen。

---

## Scenario 判定：complete vs expand

| 情境 | 模式 |
|------|------|
| F1 **已有** Scenario ID，但历史 TSV **无合法** `scenario_id`、keeper **未按场景分池**、仍存在 `history_experiment_substr` 等substr 分池 | **Modify-Scenario-complete** |
| 要在场景清单 **F1 新增一行** Scenario ID（expansion）；常伴随 `scenario_active`、README `SCENARIO_POLICY`（权威；`.auto-nn/migration-summary.md` 留档） | **Modify-Scenario-expand** |
| **二者同时需要** | **先 Modify-Scenario-expand**（清单与人工签批）→ **再 Modify-Scenario-complete**（backfill / keeper / 去 substr） |

**顺序原则**：必须先有可列入账的「新场景 ID」（expand），再回到历史行补录与 keeper 拓扑（complete）。

---

## 与其它域代号的区分

同字母在不同语境含义不同：**禁止**在对话里裸抛 `L1` / `T2`。**域冲突与对照表**以 `modify-track-naming.md` §3 · 与其它域的区分为准（Knowledge-L1、Evidence-L1、Migration-L*、Gate-T* 等与 **Modify-***）。

---

## ~~Modify-L1~~ · 台账·参数字段（退役）

| 典型信号 | 现行做法 | 备注 |
|---------|----------|------|
| 新超参要进 TSV parameters 区 | 改 `nn-config.yaml` → `ledger.watchlist` + `regen_results_tsv.py` | **台账同步**；不入 Modify Track；勿 `NN_RELAUNCH`（除非同时动了 contract） |

---

## Modify-L2 · 台账·指标列

| 典型信号 | 代号 | 可改路径（示例） | `NN_RELAUNCH` | README 区块 |
|---------|------|------------------|---------------|-------------|
| 新增 metric / auxiliary 键、METRIC_KEYS 与 KEEP 可读列发生变化 | **Modify-L2** | `metric_keys` / `auxiliary_keys`、契约测试、可能影响 `contract_demo_metrics` | **要** | **`METRICS_SNAPSHOT` / METRIC_KEYS、`readme_consistency_gate` 对账区块** |

---

## Modify-L3 · 台账·KEEP 口径

| 典型信号 | 代号 | 可改路径（示例） | `NN_RELAUNCH` | README 区块 |
|---------|------|------------------|---------------|-------------|
| 改 KEEP 阈值、规则、语义（非场景 ID 列本身） | **Modify-L3** | `keep_threshold`、`contract` KEEP 语义、门面与相关测试 | **要** | 与 KEEP / Tier 叙事相关的 **块与 prose**，按 [`readme-sync-after-modify.md`](../archive/readme-sync-after-modify.md) |

---

## Modify-T1 · 训练·模型

| 典型信号 | 代号 | 可改路径（示例） | `NN_RELAUNCH` | README 区块 |
|---------|------|------------------|---------------|-------------|
| 换 backbone、改 `build_learner`、结构超参不写进台账键 | **Modify-T1** | `workspace/`（模型）、训练入口侧的组装 | **若不**触碰 contract facade / fixture metric **可不** | **常与纯 T 同属「无需整块」档位**；若影响对外指标叙事则补 prose |

---

## Modify-T2 · 训练·目标

| 典型信号 | 代号 | 可改路径（示例） | `NN_RELAUNCH` | README 区块 |
|---------|------|------------------|---------------|-------------|
| 换 loss / reward / 正则组合 | **Modify-T2** | `workspace/`、loss 模块；若 loss 写入契约 metric → 可能升级为 L2 | 仅实现变 **可不**；**若**增减契约 metric → **同步 L2 + 要** | 同上；牵涉 metric 时对齐 **METRICS** 块 |

---

## Modify-T3 · 训练·数据

| 典型信号 | 代号 | 可改路径（示例） | `NN_RELAUNCH` | README 区块 |
|---------|------|------------------|---------------|-------------|
| Dataset / env / `prepare_data`、数据划分描述与契约对齐 | **Modify-T3** | `workspace/`、数据管线；触 `D2`/split facade 时需跑对应 gate | 未改 contract **可不**；动 split 契约或 scenario 数据源 → **要**并跑 **d2/scenario gate** | `D2_DATA_SPLIT` / 数据章节 prose |

---

## Modify-T · 可插拔构建原则（共用节）

所有 `build_*` 方法（`build_learner` / `build_objective` / `build_optimizer` / `build_scheduler`）遵循同一设计模板。

### 原则

单一 cfg 参数选择实现变体，方法返回 `(obj, metadata_dict)`，通过 `ExperimentBase.apply_build_meta()` 合并进 cfg，确保 TSV 记录实际值。

### 签名规范

```python
obj, meta = ws.build_learner(cfg)      # 返回元组
ExperimentBase.apply_build_meta(cfg, meta, "build_learner")  # 合并并打印
```

`metadata_dict` 记录实际解析的参数（如被 scenario_id 覆盖后的结构名、调整后的 loss 参数），无覆盖时返回 `{}`。

### L1 边界判定

| 情况 | 触发 | NN_RELAUNCH |
|------|-------|-------------|
| cfg 参数（如 `MODEL_ARCH`）已存在于 `ledger_context_keys` | 纯 Modify-T | 可不需要 |
| cfg 参数**不在** watchlist，需要进入 TSV parameters 区 | Modify-T + **台账同步**（改 watchlist + regen） | 仅同步通常**不需要** relaunch |

### Env var 配合（仅系统参数）

**Config-Only**：实验参数必须通过 `config.json` 传入。env var 仅用于系统控制：
- `NN_DEVICE` — GPU 选择
- `NN_SMOKE` — smoke-check 开关
- `NN_SEED` — 随机种子（框架控制）
- 其他系统参数见 PROTOCOL.md §2.3

### 示例：Modify-T2 可插拔 loss

```python
def build_objective(self, cfg):
    loss_type = cfg.get("LOSS_TYPE", "mse")
    meta = {"LOSS_TYPE": loss_type}
    if loss_type == "mse":
        return nn.MSELoss(), meta
    elif loss_type == "smooth_l1":
        return nn.SmoothL1Loss(), meta
    elif loss_type == "huber":
        return nn.HuberLoss(delta=cfg.get("HUBER_DELTA", 1.0)), meta
    raise ValueError(f"未知 LOSS_TYPE={loss_type}")
```

（Modify-T1 的 `build_learner` 模式同理，见 BM `workspace/__init__.py` `build_learner` 方法，展示了 `MODEL_ARCH` 参数切 7+ 种网络结构。）

### 设计检查清单（Agent 每次 Modify-T 改码前勾）

- [ ] `build_*` 方法读单一 cfg 参数选择变体
- [ ] 返回 `(obj, metadata_dict)` 元组
- [ ] 调用方执行 `apply_build_meta(cfg, meta, "build_xxx")`
- [ ] 参数是否已在 `ledger.watchlist`？决定是否做台账同步（regen）；勿再称 Modify-L1

---

## Modify-Scenario-complete · 场景·补完

| 典型信号 | 代号 | 可改路径（示例） | `NN_RELAUNCH` | README 区块 |
|---------|------|------------------|---------------|-------------|
| TSV 缺 `scenario_id`、单体 `keeper.json`、substr 分池未完成迁移 | **Modify-Scenario-complete** | `nn-config`（`agent.scenario_*`）、`saved/keepers.json` map、`scripts/backfill-scenario-tsv.sh`、`contract`（删除 `history_experiment_substr` 等） | **仅** nn-config + backfill **且未**改 contract **可不**；**删 substr / 改 contract 语义** → **要** | `SCENARIO_POLICY`、场景清单、`.auto-nn/migration-summary`（留档）对齐 |

---

## Modify-Scenario-expand · 场景·扩充

| 典型信号 | 代号 | 可改路径（示例） | `NN_RELAUNCH` | README 区块 |
|---------|------|------------------|---------------|-------------|
| F1 **新增** Scenario ID、开启/切换 `scenario_active` | **Modify-Scenario-expand** | `.auto-nn/migration-summary`（留档）、README `SCENARIO_POLICY`（权威）、`nn-config`、`contract`/`test`/metric **若主 metric / S_data 变更** | **触达 contract / test / metric** → **要** | **清单与场景块必选**；与 [`readme-sync-after-modify.md`](../archive/readme-sync-after-modify.md) 一致 |

**硬约束**：**须先停止** `./auto-nn-run.sh` 等批量实验，再改 F1 清单与契约相关内容。

---

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-05-24 | 初版：八轨表格 + 误判表 + Scenario 顺序 + `modify-track-naming` §3 链 |
