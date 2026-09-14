---
name: auto-nn-check
description: >-
  选行选列查看 _runs/results.tsv：默认先报参照（当前最好/尺子 tag、场景清单、目标、
  当前关注场景），再按列子集、行过滤、scenario glob、每 scenario 取 best、tail N，
  tsv/csv/table 三种格式。不改文件、不可写、纯只读查看。Agent 据上下文智能聚焦——
  按意图自动选列、筛行、适配屏幕宽度；用户也可手动组命令。
  （吸收 VIDEO 仓 filter_tsv.py 的 --best / --scenario glob / elapsed_sec m/h 显示）
  NL: 看台账|筛几行|view runs|filter tsv. NOT: 分析原因→analyse.
---

# auto-nn-check — 选行列查看台账

**问题：** `_runs/results.tsv` 列多（10-30+ 列）、行多（百行起）、cell 宽（description / exp_dir 经常超 100 字符）——`cat` 一行超屏，截断，Tail 看不清。打开表前也不知道「当前最好 / 尺子 / 场景 / 目标 / 关注点」在哪。

**解法：**
1. **`scripts/check_brief.py`** — 每次进入本技能**必跑**的默认参照摘要（只读）。
2. **`scripts/view_runs.py`**（std lib only，**不**引入 `tabulate` / `pandas`）— 按意图选行列出表。

本技能 = 二者的用户手册：先报参照，再按需出表。

**台账行语义：** TSV 每行 = 一次实验（槽位），不是一轮编排。用户说「最近 N 轮」时，`--last N` 取的是 **N 条实验行**；编排轮次看 `saved/round_decision.json` / EXPERIENCE / `_sXofN_` 组——**勿**把行数当轮数。

## Code Contract（pilot，2026-07-15）

> `scripts/check_skill_contract.sh` 自动对账本段与 `template/package/*` 实际符号。
> 失败 → release-check 第 6 步门禁拦截。
> **强检字段**（对账失败即拦截）：`calls_scripts` / `reads_cfg_keys` / `env_vars_consumed`；其余（`pluggable_symbols` / `referenced_gates` 等）为 informational，release-check 不强检。

```yaml
calls_scripts:
  - scripts/check_brief.py                 # 默认参照（focus/场景/goal/尺子/keeper）
  - scripts/view_runs.py                   # 选行列查 TSV（std lib only）
  - scripts/append-skill-activity.py      # 活动日志

reads_cfg_keys:
  - agent                                  # 父键（含 scenario_* / skill_activity_log）
  - agent.skill_activity_log               # 活动日志开关（默认 true）
  - agent.scenario_default                 # 当前关注场景（focus）
  - agent.scenario_active                  # 活跃场景子集
  - goal                                   # 实验目标段（target / per_scenario / policy）
```

## 何时使用

- 「给我看最近 5 次实验 / 5 条台账行」（用户常说「N 轮」，实为 N 行槽位）「只看主指标列」「什么场景跑得最好」「LR < 0.005 的有几条」
- 用户只说「看看台账 / check」——**仍先报默认参照**，再按意图（或默认最近几行）出表
- 不改文件、不动台账——**纯只读**查看
- **不要**用于：看趋势 / 升成熟度档 / 找撞墙（→ `/auto-nn-analyse`）；手改 TSV（禁止；改口径请人处理，人可开 `/auto-nn-modify` L2）

## 默认参照（必报，用户不用说）

> **硬规则：** 每次执行本技能，**先**跑 `python3 scripts/check_brief.py`，把各段（含改题待办）翻译成说人话贴在回复最前；**再**按意图跑 `view_runs.py`。禁止跳过 brief 直接贴表。用户只要「筛几行」也一样——参照是读表坐标系，不是可选彩蛋。

```bash
python3 scripts/check_brief.py          # cwd=业务仓根
```

| brief 键 | 人话怎么报 | 缺件时 |
|----------|------------|--------|
| `focus` | **当前关注场景**是 … | 「未设关注场景」 |
| `scenarios` | **场景清单** …；**活跃子集** … | 清单空 → 点名；active 未设 → 说「未限制，跟清单一致」 |
| `goal` / `goal_matrix` | **实验目标** …（目标值 / 当前最好 / 差多少 / 是否达标） | `NO_GOAL` → 「未设实验目标」 |
| `baseline` / `baseline_missing` | **尺子**：朴素下界（plain）有无、公开对照（reference）有无、台账 tag 列有无 | 缺则**点名缺口**（补尺子走手跑 / analyse，本技能不判策略） |
| `keeper` | **当前最好**（分场景；关注场景带标记） | 无指针 / 仅台账最优 / 空 → 用人话说清，不说内部状态码 |
| `audit` | **审查卡片**：有则路径+一句结论；无则说还没审查 | 「还没审查」 |
| `e_feedback` | **待审改题** N 条（有 deferred 可顺带说「另有以后再说 M 条」）；无则「无改题待办」 | 「无改题待办」；**不问**决议、不判趋势 |

对人话禁裸抛：`keeper`→「当前最好」、`KEEP'd`→「已立当前最好」、`stale`→「指针失效」、`best-only`→「只有台账最优、尚未立指针」、`baseline_tag`/`plain`/`reference`→「尺子标签 / 朴素下界 / 公开对照」、`focus`→「当前关注场景」、`e_feedback`/`pending`→「改题待办 / 待审改题」。

**brief ≠ analyse：** 只陈述事实坐标；不判趋势、不建议升档、不替用户做保留决策；**不**问改题三选一（决议走 `/auto-nn-analyse`）。

## Agent 智能聚焦（按意图组命令）

> **原则：** `check_brief` 给坐标系；`view_runs.py` 仍是被动工具——**筛表智能留在 Agent 这边**。Agent 据上下文（意图）自动选列、筛行、适配屏幕宽度，用户也可手动组命令。

### 意图 → 命令模板

| 意图 | 命令模板 | 何时用 |
|------|----------|--------|
| **默认（用户没细说）** | brief 后 `--last 8 --ensure-baseline-col --cols <exp>,scenario_id,<主指标>,baseline_tag`（有列才带） | "看看台账"、"check 一下" |
| **看尺子（优先）** | brief 已含 baseline；表侧再 `--baseline-tags plain,reference --cols baseline_tag,experiment,scenario_id,<主指标> --last N` | "有没有 plain/reference"、"尺子轮" |
| **看最近 N 条实验行** | `--last N --ensure-baseline-col --cols <exp>,scenario_id,<主指标>,<关键参数 2-3 个>` | "看最近"、"刚跑得怎样"（`--last N`=N 行槽位，非轮数；有 `baseline_tag` 列必带上） |
| **看某 scenario 历史** | `--scenario "<pattern>" --last N --ensure-baseline-col --cols <exp>,scenario_id,<主指标>` | "X 场景跑过啥" |
| **看每 scenario 最佳** | `--best-by <主指标> --best-direction higher\|lower --cols scenario_id,<主指标>,<关键参数>` | "各场景最高分" |
| **筛阈值** | `--where "<主指标><op><阈值>" --last N` | "test_rmse_avg<0.05 的" |
| **找相关行** | `--where "scenario_id=<X>" --where "<关键参数>=<Y>"` | "同场景同架构" |
| **导出给外部** | `--format csv\|tsv --no-header --last N` | "导出去排序/分析" |

### 主指标识别

1. 先 `python scripts/view_runs.py --show-cols` 查列名
2. 主指标候选 = `test_*` 开头列（多个时取第一个；是否保留去 `/auto-nn-analyse` 确认）
3. 关键参数 = `MODEL_ARCH` / `LR` / `EPOCHS` / `BATCH_SIZE` 等实验字段（业务仓具体列名以 `--show-cols` 为准）

### 屏幕宽度自适配

- `tput cols` 取终端宽度；`<80` 列 → 选 ≤5 列；`80-120` → 6-7 列；`>120` → ≤10 列
- 长 cell（`exp_dir` / `description`）一律截断，看完整用 `--format tsv | less -S`

### 调用流程（6 步）

1. 收到用户意图（原话；哪怕只说「check」）
2. **必跑** `python3 scripts/check_brief.py` → 各段译成人话（含「待审改题 N 条」），作为回复开头「参照」
3. `--show-cols` 拿列名 + `tput cols` 拿终端宽度（brief 已含尺子概况；表侧仍可按意图加 `--baseline-tags`）
4. 决策：选哪个意图模板 + 主指标是哪一列 + 选哪几列（默认 `--ensure-baseline-col`；用户没细说 → 用「默认」模板）
5. 组 `view_runs.py` 命令 + 跑
6. 表前**一句人话点重点**（不擅判保留）；若 brief 显示缺朴素下界/公开对照，**点名缺口**并提示去 `/auto-nn-analyse` 或手跑补尺子；表后向用户解释列含义用人话

### `baseline_tag` 铁律（check 侧）

| 值（盘内） | 给人看（table） | 人话 |
|------------|-----------------|------|
| `plain` | `plain` | 朴素下界轮 |
| `reference` | `reference` | 公开对照轮 |
| `none` / 空 | **`-`** | 普通实验轮 |

- 盘内仍可用 `none`；**table 展示**把 `none`/空显示成 `-`（tsv/csv 管道仍原样，不改文件）。
- 用户说「最近几轮」、实为看最近几条实验行时：**有列必展示**，勿默默丢掉该 flag。
- 用户问「基线/对照/尺子」→ 优先 `--baseline-tags plain,reference`，不要只 Tail 全表。
- 对人话小结里不要说「none」，说「普通轮」或指出表上是 `-`。

### 不擅越的边界

- "高分实验" ≠ "建议保留"（→ `/auto-nn-analyse`）
- "相关行" ≠ "建议同参数继续"（→ `/auto-nn-manual-run` 或 `/auto-nn-auto-run`）
- "最佳" 列展示 ≠ "最佳策略推荐"（→ `/auto-nn-analyse`）
- **默认参照只陈述，不替用户做策略**——与 analyse 的「结论 / 下一步」分工
- **任何写 TSV 都属 Modify-L2**——本技能**永不可**写盘

## 快速命令

```bash
# 0. 默认参照（每次必跑）
python3 scripts/check_brief.py

# 1. 不知道有哪些列：先看列名 + 序号
python scripts/view_runs.py --show-cols

# 2. 尺子体检 + 只看 plain/reference 轮
python scripts/view_runs.py --baseline-summary
python scripts/view_runs.py --baseline-tags plain,reference --last 20 \
  --cols baseline_tag,experiment,scenario_id,test_rmse_avg

# 3. 全部 + 最近 5（默认 table；有 baseline_tag 时带上）
python scripts/view_runs.py --last 5 --ensure-baseline-col

# 4. 选列
python scripts/view_runs.py --last 10 --ensure-baseline-col \
  --cols experiment,scenario_id,test_rmse_avg,MODEL_ARCH,LR,EPOCHS,git_commit

# 4. 行过滤（注意引号：< > 是 shell 重定向）
python scripts/view_runs.py --where "scenario_id=12week_price_pred" --last 10
python scripts/view_runs.py --where "LR<0.005" --where "EPOCHS>=30"
python scripts/view_runs.py --where "notes~repro"          # 正则
python scripts/view_runs.py --where "model_arch~transformer" --last 5

# 5. scenario glob（fnmatch，比正则更易记）
python scripts/view_runs.py --scenario "*_1pct" --last 10
python scripts/view_runs.py --scenario "sample_*" --cols scenario_id,test_val_acc1,test_val_acc5

# 6. 每 scenario 取 best（吸收 VIDEO 仓 filter_tsv.py --best）
python scripts/view_runs.py --best-by test_val_acc1 --best-direction higher --cols scenario_id,test_val_acc1
python scripts/view_runs.py --best-by rsrp_loss --best-direction lower --cols scenario_id,rsrp_loss,model_arch

# 7. 管道：tsv/csv 给其他工具
python scripts/view_runs.py --no-header --format tsv --cols experiment,test_rmse_avg | sort -t$'\t' -k2 -n
python scripts/view_runs.py --no-header --format csv --last 3 > /tmp/last3.csv
```

## 必知约定

| 项 | 约定 |
|----|------|
| **--where 操作符** | `=` 字符串相等 / `~` 正则 / `< > <= >=` 数值（不可转 float 时退化为字符串） |
| **--where 多次** | AND 关系（`--where LR<0.005 --where EPOCHS>=30`） |
| **--scenario** | scenario_id 列 fnmatch glob（`"*"`, `"*_1pct"`, `"sample_*"`） |
| **--best-by / --best-direction** | 按 scenario 分组取最优行；`higher`/`lower` 二选一，缺一报错 |
| **--cols 模糊匹配** | 列名完整优先 → 前缀唯一 → 子串唯一；模糊到 0 / >1 报错并提示用 `--show-cols` |
| **--cols 数字** | `--cols 0,1,8` 用列号 |
| **--format table** | 默认；按本批最大值等宽对齐；cell > 40 字符截断加 `…`；多行 cell 折成 1 行；**elapsed_sec 列自动转 m/h** |
| **--format tsv/csv** | 管道友好；加 `--no-header` 纯数据行；elapsed 不格式化（保原始数值） |
| **--last N** | 过滤后取末尾 N **实验行**（1 行=1 槽；不是轮数，也不是「全表末尾 N」） |
| **stderr 末尾** | 打印 `N rows × M cols` 小计，**不**进 stdout 污染管道 |

## 与其它技能

| 技能 | 分工 |
|------|------|
| **check** | 选行列只看表，**不**算指标（plateau、趋势、reflect 门禁） |
| **analyse** | 算指标 / 找 keeper / 升 Tier；**不**改台账 |
| **modify** | 改 TSV 结构 / 列 / 行；本技能不动它 |
| **doctor** | 仓结构健康（不读 TSV 内容） |

## 硬边界

- **禁止**写 `_runs/results.tsv` / `_runs/results.jsonl`（任何"顺手修复""补 0"都禁止手改；改口径请人处理，人可开 `/auto-nn-modify` L2）
- **禁止**用本技能做 KEEP 决策（→ `/auto-nn-analyse`）
- **禁止**默认渲染 100+ 行——加 `--last` 限缩
- **不要**为"省事"把 view 当 analyse 用——你看到的是"样子"不是"策略"
- **向用户解释列含义 / 结论时用人话**（如 `test_rmse_avg` → 「测试集均方根误差」、`elapsed_sec` → 「耗时」）；表本身按用户要求原样展示，但表前用一句人话点出要看的重点。完整对照见 [`docs/skill-glossary.md`](../../../docs/skill-glossary.md)。

## 常见陷阱

| 现象 | 原因 |
|------|------|
| `--where LR<0.005` 报 `0.005: No such file or directory` | shell 重定向；用引号 `"LR<0.005"` |
| `--where scenario_id=foo` 0 行 | 字符串严格相等，scenario_id 可能含隐藏 tab/空格；先用 `--where "scenario_id~foo"` 正则试探 |
| 列名拼错报"未知列" | 用 `--show-cols` 查实际列名（大小写敏感：BM 用 `lr` 不是 `LR`） |
| `cell 太长看不清` | `--format table` 默认 40 字符截断；用 `--format tsv \| less -S` 看完整 |

## 对用户怎么说（人话）

本技能是**只读查看**——先参照、再数据表，所以"说人话"指：

- **先参照后人话**：把 `check_brief` 各段译成短列表（关注场景 / 场景清单 / 目标 / 尺子 / 当前最好 / 审查 / **待审改题**），再出表。
- **列名用人话**：表头能用中文/通用名就用（`test_rmse_avg` → 「测试集均方根误差」、`elapsed_sec` → 「耗时」、`scenario_id` → 「场景」），首次可「人话（原列名）」一次。
- **不抛过程码**：列名/小结里不裸用 `KEEP`/`discard`/`Tier`/`keeper` 等代号（→ 「保留」/「作废」/「成熟度档」/「当前最好」）。
- **表前一句点重点**：表本身按用户要的原样给（行列不篡改），但表前用一句话人话点出"这批要看的重点是什么"。
- 用户要"看看就行" → **参照 + 默认最近几行** + 一句小结；要解读/判趋势 → 不在本技能，转 `/auto-nn-analyse`。

**坏**：「scenario_id=reference 最近 5 行 KEEP 键 test_acc 最高 0.91」  
**好**：「参照：当前关注 seq；目标 0.9 还差 …；朴素下界有、公开对照缺。下表是最近实验行——测试准确率最高到 0.91。是否保留须看 analyse，我这里只列数据。」

## 附录

```bash
python scripts/view_runs.py --help
```

## 活动 log

查询结束后 **须** append 一行：`--skill auto-nn-check --phase end --summary "查看台账 …"`。开关 `agent.skill_activity_log`（默认 true）；见 [`README.md`](../README.md)。

## Watchlist 建议

`build-run-context.py` 渲染时若 `_render_watchlist_suggestion()` 返回非空，会在末尾自动追加 `### 📋 Watchlist 建议` 段（top-5 推荐）。
Agent 在 SKILL 输出末尾展示此段；用户采纳 → `vim nn-config.yaml` 改 `ledger.watchlist` → 调 `regen_results_tsv.py --sync-jsonl`。
用户说"不要建议" → 当前无 CLI flag；agent 直接**不展示**该段（建议仍渲染进 run_context.md，仅不在回复末尾贴出）。
