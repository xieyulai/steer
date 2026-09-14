# EXPERIENCE — 实验经验记录

> **Agent 读法：** `## 精华摘要` → `## 信息索引` → **`## Tier 状态`** → `## 近期实验`（**近 5 轮要点**）；Tier **语义**见 **PROTOCOL §7.5.1**。详情按索引 **按需 Read**（`REFLECT_INDEX`、`saved/`、`_runs/exp/`、`archive_*`）；**默认不读** archive 全文。新轮 **append 在** `<!-- experience-log-start -->` **之后**；禁止 prepend 到精华之前；**禁止**在正文贴 arxiv url（走 reflect 外部证据 → `saved/`）。

## 精华摘要（滚动，compress 维护）

（首次 `compress-experience.py --apply` 后由脚本规则生成；metric 须来自 TSV。）

## 信息索引（按需 Read，默认不展开）

| 类型 | 路径 |
|------|------|
| 反思 pending / 历史 | `references/REFLECT_INDEX.md` → `references/auto/` |
| 外部证据 | `saved/evidence_bundle.json`、`saved/external_evidence/pdfs/` |
| 实验证据包 | `saved/reflect_evidence.json` |
| 台账 / SOTA | `_runs/results.tsv` |
| keeper 配方 | `saved/keepers.json` + keeper `config.json` |
| 压缩归档 | `references/experience/archive_*.md` |
| 单 run 详情 | `_runs/exp/<dir>/train_dynamics.md`, `config.json` |

## 场景与 KEEP 约定（滚动更新）

> 表行 **EVAL_SCENARIO** 须与 F1「场景清单」中的场景 ID 一致；KEEP substr 列与清单 KEEP 列一致。

| EVAL_SCENARIO | 主指标键 | 当前最佳 | 最佳 experiment | KEEP 对照 substr | 下一轮计划 |
|---------------|----------|----------|-----------------|------------------|------------|
| default | （与 contract.metric_key 一致） | | | （空=全表） | |

**策略（人话一行）：**（例：集中优化 default；或按场景轮流扫）

## Tier 状态（滚动，每轮必更新）

> 二维矩阵（A–E × routine/extend/novel）；定义见 **PROTOCOL §7.5.1**。单格 **≤80 字**（超长细节写 `[反思]` 或 archive，勿堆格内）。
>
> **plain(P) 列（PDH v2,2026-07-06）：** 仅在 **触发轮**（RUN CONTEXT 含 `### plain-anchor-init` 或 `### plain-anchor-check`）必填；非触发轮不校验、留 `-`。**单格 ≤200 字**（WARN 不 FAIL；溢出请缩短 plain_why）。必填字段 4 项：`plain_anchor_value` / `plain_recipe` / `plain_budget` / `plain_why`。

| Tier | routine | extend | novel | plain(P) |
|------|---------|--------|-------|----------|
| A    | 未试    | 未试   | 未试  | -        |
| B    | 未试    | 未试   | 未试  | -        |
| C    | 未试    | 未试   | 未试  | -        |
| D    | 未试    | 未试   | 未试  | -        |
| E    | 未试    | 未试   | 未试  | -        |

格内状态词：`未试` | `浅尝` | `进行中` | `已穷尽` | `假升档`

## 近期实验（保留最近 5 轮要点）

标题：`## [Round N] YYYY-MM-DD HH:MM — 一行结论`（或 `## YYYY-MM-DD HH:MM — …`）

**每轮必填（≤40 行；禁止论文 url 与 train_dynamics 长抄）：**

```markdown
- **tier_this_round** / **tier_change** / **tier_verdict** / **innovation_depth** / **innovation_rationale**
- **paradigm_fit:** OK | WATCH | MISMATCH（范式契合自评：框架 R8 宽判决命中→自动标 MISMATCH；agent 每轮判 OK/WATCH。MISMATCH 时可附 `e_subtype: contract|paradigm` 建议换 test / 换范式——**切范式决策权在 human**，agent 仅产出信号 + 建议）
- **reflect_ack:** （仅有 pending 时）一行：采纳 / 推迟 / 冲突
- **结论:** KEEP|DISCARD · Δ · 单变量 · `exp_dir`
- **详:** _runs/exp/<dir>/train_dynamics.md
```

撞墙升档：具体格子标「已穷尽」且 plateau 触发 → reflect 或升档；禁止同格子 grid sweep。

<!-- experience-log-start -->
