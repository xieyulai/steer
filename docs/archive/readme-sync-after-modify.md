# modify 后 README 同步速查

> **技能：** `/auto-nn-modify`（Modify Track；代号见 `CONTEXT.md` §Modify Track）

> **改后命令权威链：** 完整 bash 序列以 [`docs/nn-modify/post-change.md`](../nn-modify/post-change.md) 为准：`§L`（Modify-L*）、**Modify-Scenario-complete**、**Modify-Scenario-expand** 及文末 **Modify-T** 按需整段执行。

---

## 要不要改 README？

| 你改了… | README（`SCENARIO_POLICY` 为场景权威） | `.auto-nn/migration-summary`（留档） |
|---------|--------|----------------------|
| 只换模型 / loss / 超参（**Modify-T1/T2**） | **否** | 否 |
| 只加 TSV 参数字段（**Modify-L1** · 台账·参数字段） | **否** | 否 |
| metric / test / KEEP 口径（**Modify-L2** · 台账·指标列） | **是**（块 + 评估与指标；P3+ `METRICS_SNAPSHOT`） | Tier E 时重签 F1 |
| 场景策略 / 场景 ID（**Modify-L3** / **Modify-Scenario-complete** / **Modify-Scenario-expand**） | **是**（`SCENARIO_POLICY` + 场景表） | **Modify-Scenario-expand** 新增行 |
| 数据划分 / `prepare_data`（**Modify-T3** · 训练·数据） | **是**（`D2_DATA_SPLIT`） | D2 语义变时更新 |
| Agent 硬边界（H3 类） | **是**（`AGENT_BOUNDARY`） | F1 记录 |

---

## 改后命令（Modify-L / Modify-Scenario-*；`governance-sync` 后业务仓可用）

1. **`NN_RELAUNCH` / `NN_MODIFY_TRACK` + readme 双门禁 + regen**：触及 contract 台账头时用 `NN_RELAUNCH=1`；声明 `NN_MODIFY_TRACK=L` 或 `Scenario`；跑 `readme-modify-gate` 与 `readme_consistency_gate --strict`，再按轨 `regen_results_tsv` 与场景/D2 门禁 — **顺序与删减**见 [post-change.md §L](../nn-modify/post-change.md#l-轨modify-l1l2l3--contract-触及) 与各 **Modify-Scenario-*** 节。
2. **收尾体检与 smoke：** `nn-doctor`、`smoke-check`（及 Scenario-complete 时的 `sanity`）均在 [post-change.md](../nn-modify/post-change.md) 对应段落内；勿在此页半截复制。
3. **纯 Modify-T：** 通常仅需 `contract sanity` + `smoke-check` — 见 [post-change **Modify-T**](../nn-modify/post-change.md#modify-t)。

维护者本地紧急跳过防漏（**不**跳过语义对账除非你也清楚后果）：

```bash
export README_SYNC_SKIP=1
export README_SYNC_SKIP_REASON="说明原因"
bash scripts/readme-modify-gate.sh .
```

---

## README 块速记

| 块 | 何时更新 |
|----|----------|
| `<!-- D2_DATA_SPLIT -->` | 划分、`DATA_ROOT`、KEEP 评估路径 |
| `<!-- SCENARIO_POLICY -->` | 多场景 / `scenario_active` |
| `<!-- AGENT_BOUNDARY -->` | 不可变约定 |
| `<!-- METRICS_SNAPSHOT -->` | **Modify-L2** 改 `METRIC_KEYS`（Phase 3） |

日常 **manual-run / auto-run** 不更新 README。
