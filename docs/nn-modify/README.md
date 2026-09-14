# auto-nn-modify（迁后能力修改）

> **读者**：迁后实验者、维护者、**人**（或人开的改能力会话）  
> **技能入口**：[`skills/post-migration/auto-nn-modify/SKILL.md`](../../skills/post-migration/auto-nn-modify/SKILL.md)  
> **术语真源**：业务仓根 `CLAUDE.md` §Modify Track（模板真源 `template/package/CLAUDE.md`）

---

## 1. 一句话

**迁后改能力**：改 contract / workspace / 训练实现 / 场景轨，扩展或补全台账与场景模型；**不替代** `/auto-nn-clear`、单轮训练的 `/auto-nn-manual-run`、或只读分析的 `/auto-nn-analyse` 与结构性 `/auto-nn-doctor`。

**人类路线图**：**`/auto-nn-human-guidance`** 负责编写与维护 `HUMAN_GUIDANCE.md`；**`/auto-nn-modify` 不编辑该文件**。改完指标 / 场景后若还要继续探索，由人走 human-guidance 补 NOTE。

---

## 2. 八轨速查

| 人话 | Modify-代号 | 触发语示例 |
|------|-------------|-----------|
| 台账·参数字段 | **Modify-L1** | 新超参记入台账 parameters；变更不再入 Modify Track（见下注） |
| 台账·指标列 | **Modify-L2** | 新 metric / 改 KEEP 键 |
| 台账·KEEP 口径 | **Modify-L3** | keep 规则 / 阈值口径 |
| 训练·模型 | **Modify-T1** | 换 backbone / `build_learner` |
| 训练·目标 | **Modify-T2** | 改 loss / reward |
| 训练·数据 | **Modify-T3** | Dataset / env / `prepare_data` |
| 场景·补完 | **Modify-Scenario-complete** | TSV 缺合法 `scenario_id`、keeper 未分池、需 backfill |
| 场景·扩充 | **Modify-Scenario-expand** | F1 **新增** Scenario ID、`scenario_active` |

权威触及列见 CONTEXT 表；误判（regen / 同步台账 ≠ L1）见 [track-catalog.md](track-catalog.md)。

> **Modify-L1 退役**：台账参数字段 → 改 `nn-config.yaml` 的 `ledger.watchlist` + `regen_results_tsv.py`（台账同步）。**不再**作为 Modify Track 正式轨；技能入口勿把「加参数列」路由到 `/auto-nn-modify`。Modify Track 保留 **L2/L3 / T1–T3 / Scenario-***。

---

## 3. 与其它技能分工

| 技能 / 入口 | 分工（一行） |
|-------------|--------------|
| **doctor**（`/auto-nn-doctor`） | 迁后结构体检：**只诊断** layout、governance、contract 门面、台账头、场景完整性等；**不改**能力与代码。 |
| **analyse**（`/auto-nn-analyse`） | 台账只读策略、plateau、Tier、EXPERIENCE；内置可静默拉起 doctor；**不改**能力与 HUMAN。 |
| **clear**（`/auto-nn-clear`） | **运行态与整仓清理**（junk、runs、reflect 就绪等）；**不是** modify 的子集。 |
| **human-guidance**（`/auto-nn-human-guidance`） | 编写 / 清空 **`HUMAN_GUIDANCE.md`** 人类路线图；modify **不替代**此项。 |
| **manual-run**（`/auto-nn-manual-run`） | **单轮** PROTOCOL §6：`train`、`wait-train`、`KEEP`/discard；**不重写**契约与场景模型。 |
| **modify**（本技能） | **改能力**：L/T/Scenario 触及 contract、`workspace`、`nn-config`、README 区块等；改后命令链见 [post-change.md](post-change.md)。 |
| **batch 真跑** | **tmux** 里 `bash auto-nn-run.sh N`；见 ../nn-run-skills/batch-ops.md（**不要** IDE 前台长挂 N 轮）。 |

---

## 4. 文档地图（本目录）

| 文档 | 内容 |
|------|------|
| **[track-catalog.md](track-catalog.md)** | 八轨：信号 → 代号 → 可改路径 → `NN_RELAUNCH` → README 区块；误判与 Scenario 顺序 |
| **[post-change.md](post-change.md)** | 改后 bash 链权威（各轨；与 readme-sync、`readme_consistency_gate` 等对账） |

---

## 5. Agent 工作流（摘要）

1. **判定轨**：用人话 + `Modify-*` 代号对齐 [track-catalog.md](track-catalog.md)； Scenario 时注意 **先 expand 后 complete**。  
2. **填计划**：按 [`SKILL.md`](../../skills/post-migration/auto-nn-modify/SKILL.md) 改前 checklist（触及文件、`NN_RELAUNCH`、README 计划、Scenario 专属项）。  
3. **改代码**：遵守硬边界与子目录约定（如新 `.py` 进 `workspace/`）。  
4. **跑改后链**：执行 [post-change.md](post-change.md) 中与本轨匹配的命令序列；细颗粒规则见 [`readme-sync-after-modify.md`](../archive/readme-sync-after-modify.md) 与 SKILL 内嵌摘要。  
5. **收口**：`/auto-nn-doctor` 或 `--quiet` 前置、按需 smoke；回复末尾至少推荐一个 `/auto-nn-*` 下一步。

---

## 6. 硬边界

- **禁止**修改 `experiment.py`（迁移期协议脚本；不作为迁后日常改能力的入口）。
- **禁止**手编辑 `_runs/results.tsv` / `_runs/results.jsonl`；对齐须用 **`regen_results_tsv.py`、合法 backfill、`backfill-scenario-tsv.sh` 等脚本** `--apply`。  
- **运行态清理、整仓 runs、reflect 就绪绿场等** → **`/auto-nn-clear`**，**不属于**本技能。  
- **Modify-Scenario-expand**：**必须先停** `./auto-nn-run.sh`（及同类 batch）；禁止在 auto-run 运行中改 F1 场景清单。

---

## 7. 相关索引（仓内）

| 链接 | 说明 |
|------|------|
| [`docs/archive/metric-and-keep-system.md`](../archive/metric-and-keep-system.md) | metric / KEEP / TSV 四区与 KEEP 语义 |
| [`docs/nn-doctor/fail-routing.md`](../nn-doctor/fail-routing.md) | doctor 项 → 推荐技能或命令 |
| [`docs/archive/readme-sync-after-modify.md`](../archive/readme-sync-after-modify.md) | README 块与 prose 同步（改后整条命令仍以 [post-change.md](post-change.md) 为准） |

---

## 8. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-05-24 | 新建 `docs/nn-modify/`：README 枢纽 + `track-catalog` 八轨目录（对齐 `docs/nn-doctor/` 信息架构）。 |
