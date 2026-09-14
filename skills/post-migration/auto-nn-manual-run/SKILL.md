---
name: auto-nn-manual-run
description: >-
  手跑单/多轮 NN 实验（PROTOCOL §6）：读 HUMAN_GUIDANCE 路线图、REFLECT_INDEX、
  场景（scenario_id / scenario_bindings）、改 train/workspace、train、wait-train、
  KEEP/discard。支持多实验并行（多槽多结构同时训练）。
  未使用 auto-nn-run.sh 时用本技能。
  NL: 手跑|单轮|train once|hand-run. NOT: 多轮→auto-run.
---

# auto-nn-manual-run — 手跑单轮实验

> ⚠️ **Agent 必读：改实验参数前，先写 config.json！**
>
> **Config-Only 原则**：所有实验参数（LR、MODEL_ARCH、EPOCHS、SEED、scenario_id 等）**必须**先写入 `config.json`，然后 `poetry run python train.py --config config.json`。
>
> - ❌ 禁止：直接改 train.py 常量，或用 `NN_LR=0.001` 环境变量
> - ❌ 禁止：在代码中 `os.environ.get("NN_XXX")` 读取实验参数
> - ✅ 正确：`cat > config.json << EOF ... EOF && poetry run python train.py --config config.json`
>
> **常见错误**：Agent 改了 train.py 的 `LR = 0.001`，但忘了写 config.json，导致实验结果无法复现。

> **实验轮改 `train.py` / `workspace/`**：直接改，守 PROTOCOL §0.1；**不**要求先开 `/auto-nn-modify`。
> **人**要改题面/metric/场景/立项式能力：走 `/auto-nn-modify`（[track-catalog](../../../docs/nn-modify/track-catalog.md) + [post-change](../../../docs/nn-modify/post-change.md)）。
> **改实验参数** → `config.json` / `modify-config.py`（见上 Config-Only）。
>
> **运行时**：训前 preflight 仍扫本仓 `train.py`/`workspace/` 改动结果（`G-cfg-no-defaults` FAIL / `G-no-fallback` WARN；`nn-doctor` 同规则为 FAIL）—— 运行时门禁，非 manual-run 自定边界。

权威规则：`PROTOCOL.md` §6（含场景分池）。

## Code Contract（pilot，2026-07-15）

> `scripts/check_skill_contract.sh` 自动对账本段与 `template/package/*` 实际符号。
> 失败 → release-check 第 6 步门禁拦截。
> **强检字段**（对账失败即拦截）：`calls_scripts` / `reads_cfg_keys` / `env_vars_consumed`；其余（`pluggable_symbols` / `referenced_gates` 等）为 informational，release-check 不强检。

```yaml
calls_scripts:
  - scripts/summarize-runs.py              # 路线图 status（开始前·1）
  - scripts/scenario_completeness_gate.py  # 场景补完门禁（开始前·4）
  - scripts/check_goal.py                  # goal 进度（开始前·5）
  - scripts/human_guidance_gate.py         # G-HUMAN 检查（手跑前）
  - scripts/modify-config.py               # 单键改 config（执行·方式2）
  - scripts/wait-train.sh                  # 单/多槽 wait（执行 + 并行·4）
  - scripts/journal_append.py              # 训后 journal（执行·步骤 9）
  - scripts/append-skill-activity.py       # 活动 log（活动 log 段）

reads_cfg_keys:
  - scenario_id                            # config.json 场景轴
  - scenario_active                        # 场景·切换策略（嵌套 agent_cfg）
  - agent.scenario_default                 # 默认场景（嵌套 cfg.get('agent')）
  - agent.scenario_bindings                # 场景→env 绑定白名单
  - goal.target                            # goal 目标值（v4；全局默认）
  - agent.skill_activity_log               # 活动 log 开关
  - goal                                   # goal.target / per_scenario / policy
  - keep                                   # keep.improve_mode / primary_delta 等（嵌套 keep_cfg）
  - LR                                     # 训练·学习率（Config-Only 强读）
  - EPOCHS                                 # 训练·epoch（Config-Only 强读）
  - MODEL_ARCH                             # 训练·backbone（Config-Only 强读）
  - GAMMA                                  # 训练·scheduler γ（Config-Only 强读）

# 备注：以下不是 cfg.get 键，而是代码内常量 / 标记 / 文档键，下移到 informational 段
#   SCENARIO_POLICY       → README HTML 标记 + Python 标识符（见 set-scenario-policy.py）
#   _sXofY_               → slot 实验目录命名约定（train.py / experiment.py）
#   finalize-round / finalize_round → CLI 命令 + ExperimentBase 方法
#   ledger_context_keys   → 文档键（场景轴参数清单），非 cfg.get

env_vars_consumed:
  - NN_SLOT                                # 实验槽位（多实验并行·4 + §硬约束 CLI 表）
  - NN_PARALLEL_TOTAL                      # 并行槽位总数（同上）
  - NN_SMOKE                               # 系统参数（硬约束·系统参数段）
  - NN_DEVICE                              # 设备（硬约束·系统参数段）
  - NN_EXPERIMENT                          # 实验目录名（CLI 替代）
  - NN_EXPERIMENT_DESC                     # 实验描述（CLI 替代）
  - NN_AUTO_FINALIZE_ROUND                 # 单槽自动 finalize_round 开关
  - NN_MANUAL_RUN_STRICT                   # =1 时手跑改 workspace/train → scope FAIL（P2）

pluggable_symbols:                         # 仅 informational，lint 不强检
  - <!-- SCENARIO_POLICY -->                # README HTML 标记
  - _sXofY_                                # slot 实验目录命名
  - finalize-round                         # CLI 命令（多槽聚合）
  - finalize_round                         # ExperimentBase 方法
  - resolve_scenario_id                    # 训前 dry-run 解析
  - ExperimentBase                         # 基类（§硬约束 引用）

referenced_gates:                          # 仅 informational，lint 不强检
  - G-cfg-no-defaults                      # 改码三原则·config-only
  - G-no-fallback                          # 改码三原则·no-fallback
  - G-repro-env                            # 改码三原则·repro
  - G-repro-cli                            # 改码三原则·repro
  - G-HUMAN                                # human_guidance_gate 门禁
```

## 高频代号（人话见 glossary）

| 内部码 | 对用户怎么说 |
|--------|--------------|
| `scenario_id` | 实验场景（不同场景成绩不能混着比） |
| `KEEP` / `discard` | 把这轮存为最好 / 不如最好就丢弃 |
| `keeper` | 当前最好的那个结果 |
| `Tier` | 实验成熟度档位（现为二维矩阵：A–E × routine/extend/novel） |
| `innovation_depth` | routine（经典现成）/ extend（论文级）/ novel（研究性） |
| `finalize` | 收尾结算这轮成绩 |

### 启动前意图判别（必读）

**改能力 ≠ 改参数 — 先判别再动手。** 只调实验参数（LR/EPOCHS/SEED/scenario_id 等）→ manual-run 直接改 `config.json`。**实验轮**改 `train.py`/`workspace/`（如加 backbone、试 loss 变体）→ **直接改**，守改码三原则（PROTOCOL §0.1），**不**暂停等 Modify。**人在对话里**明确提出改题面/台账口径/场景模型 → 走 **`/auto-nn-modify`**（[track-catalog](../../../docs/nn-modify/track-catalog.md) + [post-change](../../../docs/nn-modify/post-change.md)）。能力级改动速查见下表：

| 触发语示例 | 归类 | 推荐路由 |
|------------|------|----------|
| "加参数列"、"新超参记入台账"、"watchlist" | **台账同步**（非 Modify） | 改 `nn-config.yaml` → `ledger.watchlist`，再 `python3 scripts/regen_results_tsv.py --repo-root .` |
| "加 metric 列"、"新 metric"、"加指标" | Modify-L2 | **人**开会话 → `/auto-nn-modify` |
| "改 KEEP"、"改 keep 规则" | Modify-L3 | **人**开会话 → `/auto-nn-modify` |
| "换模型"、"换 backbone"、"加网络" | 视语境 | **人**在对话里提改能力 → Modify-T1 + `/auto-nn-modify`；**实验轮**加 backbone → 直接改 `workspace/`，守 §0.1，勿暂停 Modify |
| "改 loss"、"改训练目标"、"换损失" | Modify-T2 | **人**开会话 → `/auto-nn-modify`；实验轮试 loss 变体 → 直接改 `workspace/` |
| "改数据"、"Dataset"、"换数据"、"env" | Modify-T3 | **人**开会话 → `/auto-nn-modify` |
| "补 scenario_id"、"场景补完" | Modify-Scenario-complete | **人**开会话 → `/auto-nn-modify` |
| "新场景"、"新增 Scenario ID"、"扩场景" | Modify-Scenario-expand | **人**开会话 → `/auto-nn-modify` |

**触发动作（人在对话里提改能力）**：命中 Modify-* → 主动回复「这听起来像 `<Modify-XX>(<人话>)`，请走 `/auto-nn-modify` 改能力，改完再来 manual-run 验证」并暂停，等用户确认。  
**触发动作（实验轮）**：加 backbone / 试 workspace 变体 → 直接改代码开训，**不要**嵌套 `/auto-nn-modify`。  
**触发动作（台账同步）**：说明改 watchlist + regen，**不要**推 `/auto-nn-modify`。

**兜底**：即使对话层漏判，运行时 nn-doctor §8 的 `manual_run_scope_check` 会扫 `git diff`：仅改 `ledger.watchlist` → PASS；改 `contract/` 等能力范围默认 WARN（不阻断）；`NN_MANUAL_RUN_STRICT=1` 时改 `workspace/`/`train.py` → FAIL。

**manual-run 边界**：
- **直接做**：改 `config.json` 实验参数（LR / EPOCHS / SEED / `scenario_id` 等）；实验轮改 `train.py`/`workspace/`（守 PROTOCOL §0.1 改码三原则）。
- **走 `/auto-nn-modify`**（**人**开会话；[track-catalog](../../../docs/nn-modify/track-catalog.md) + [post-change](../../../docs/nn-modify/post-change.md)）：动 `contract/`（metric 列 / KEEP 口径 / 场景）、立项式能力扩展。动 contract/metric/scenario → `NN_RELAUNCH=1`。
- **绝不做**：改 `experiment.py`、改题面源文件（`SCENARIO_ID`/`METRIC_KEYS`）、手改 `_runs/results.tsv`/`results.jsonl`。

## 开始前

- [ ] **1.** `Read HUMAN_GUIDANCE.md` — 先守文首 **`## 公平约束`**（若有，全程比较口径）；有路线图则再 `python3 scripts/summarize-runs.py --roadmap-status`，只守 **inferred_phase** 的 NOTE；空路线图则阶段全自主（仍守公平约束）
  - HTML 注释内 `### 阶段` 不计入阶段数（与台账 `inferred_phase` 一致）
- [ ] **2.** `Read references/REFLECT_INDEX.md`（pending 若有；优先级低于路线图）
- [ ] **3.** Read 台账、`EXPERIENCE.md`、`contract/`、`workspace/`
- [ ] **4. 场景核对**（多场景仓 **必做**；单场景也确认 default ∈ F1 清单）：
  - Read README `SCENARIO_POLICY` **场景清单** + `nn-config.yaml` → `agent.scenario_default` / `scenario_active` / `scenario_policy` / **`scenario_bindings`**
  - 明确 **本轮目标 `scenario_id`**（路线图 NOTE、用户指令、或 focus 默认）
  - `python3 scripts/scenario_completeness_gate.py .` 或 `nn-doctor` 场景项有 FAIL → 先 **`/auto-nn-modify`（Modify-Scenario-complete）**，勿开训
- [ ] **5. goal 进度**（`nn-config.yaml` 配了 `goal.target`（或 `goal.per_scenario`）才看；**explore 有效时跳过 goal 硬停**，`check_goal.py` 仍可能输出 `GOAL_SKIPPED_EXPLORE`）：
  - `python3 scripts/check_goal.py .`（exit 0=达标 / 1=未达 / 2=未配或 explore 跳过）
  - 达标且非 explore 跳过 → **停止实验**（loop 即停；手跑也别再开训）；未达 → 正常开训；未配 goal → 跳过本项
  - 实验模式 / 底线护栏 → `/auto-nn-goal mode show` 或 doctor `experiment_mode_status` / `metric_floor_status`
- [ ] **立尺**：仅当用户明确要求「朴素下界 / plain」或「公开对照 / reference」时本轮设 `baseline_tag`；否则 `none`（`--from-template` 已默认清标签）。

## 场景与改参（训前）

KEEP / keeper / metric_leader **只认 TSV `scenario_id` 分池**，不认 `experiment` 子串。

| 你要做的 | Agent 必须 |
|----------|------------|
| 只调 LR、结构等同场景超参 | 不动场景轴；`scenario_id` 应与上轮相同 |
| 改 **场景轴**（PINN：`N_SIP`/`MODE`/`GAMMA`；BM：`model_arch`；等） | **视同换场景** — 见下表 |
| 路线图写「验证 2sip causal」 | 目标 ID 须为清单中的 **`…_2sip`**（非 default 1sip） |

**写对 `scenario_id` 的方式（Config-Only）：**

```bash
# 实验配置统一放在 _runs/configs/ 目录，命名与实验目录一致
mkdir -p _runs/configs
cat > _runs/configs/20260530_lr_sweep_baseline.json << 'EOF'
{
  "scenario_id": "lp01_lp11_kerr_2sip",
  "SEED": 42,
  "LR": 0.001
}
EOF
poetry run python train.py --config _runs/configs/20260530_lr_sweep_baseline.json
```

改 `train.py` 里 `N_SIP=2` 但 **未**在 config.json 写 `scenario_id` → 台账可能仍记 **`scenario_default`（错池）**。

**手跑推荐（切场景时与 config 同步）：**

```bash
cat > _runs/configs/20260530_2sip.json << 'EOF'
{
  "scenario_id": "lp01_lp11_kerr_2sip",
  "MODE": "lp01_lp11",
  "GAMMA": 8.2e-7,
  "N_SIP": 2
}
EOF
poetry run python train.py --config _runs/configs/20260530_2sip.json

# 或训前 dry-run 解析（不改盘）
python3 -c "
import sys; sys.path.insert(0,'scripts')
from pathlib import Path
from lib.scenario_inventory import resolve_scenario_id
cfg={'MODE':'lp01_lp11','GAMMA':8.2e-7,'N_SIP':2}  # 与 train.py 一致
print(resolve_scenario_id(Path('.'), cfg))
"
```

## G-HUMAN（手跑）

- Agent **禁止** Write/Edit `HUMAN_GUIDANCE.md`；改路线图 → **`/auto-nn-human-guidance`**（停 batch / 训练后再改）
- 若存在 `saved/.human-guidance-baseline.json`（曾跑 auto-run）：开训前

```bash
python3 scripts/human_guidance_gate.py check --repo-root .
```

  FAIL → `git checkout $(jq -r .git_head saved/.human-guidance-baseline.json) -- HUMAN_GUIDANCE.md`（或备份恢复），**禁止** `refresh-human-guidance-baseline.sh --apply`
- 无 baseline（纯手跑、未开 batch）→ check 常 WARN「无 baseline」，可继续

## 执行（一轮）

（同 PROTOCOL §6：改 config / train·workspace → train → wait-train → KEEP/discard → EXPERIENCE → **训后 commit 台账**）

**实验参数生成**：
```bash
# 实验配置统一放在 _runs/configs/ 目录

# 方式 1：手动写（完整配置）
cat > _runs/configs/20260530_my_experiment.json << 'EOF'
{
  "SEED": 42,
  "LR": 0.001,
  "EPOCHS": 100,
  "GRAD_CLIP": 1.0
}
EOF

# 方式 2：快速修改参数（推荐）
# 从已有配置复制并修改部分参数
python scripts/modify-config.py _runs/configs/20260530_lr003.json \
    --from-template _runs/configs/20260530_my_experiment.json \
    --set LR=0.003

# 执行训练
poetry run python train.py --config _runs/configs/20260530_my_experiment.json
```

后台+日志+wait 标准形态（PROTOCOL §6，免受编排 SIGHUP）：

```bash
mkdir -p _runs/logs && CUDA_VISIBLE_DEVICES=0 setsid poetry run python train.py --config _runs/configs/20260530_my_experiment.json > _runs/logs/run.log 2>&1 < /dev/null & echo PID=$!
./scripts/wait-train.sh
```

- [ ] 改 **`ledger_context_keys` 中的场景轴参数** 时，同步确认 §场景与改参
- [ ] KEEP：`finalize_round` 已自动 write-keeper 时见 stderr `saved_keeper:` → 跳过手动 write-keeper（**须为当轮 `scenario_id` 键**）
- [ ] **训后场景验收**（写入 TSV 前/后各看一次）：
  - 末行 `scenario_id` == 本轮目标；`N_SIP` 等 parameters 与 cfg 一致
  - `keep_suggestion` / `_runs/round_decision.json` 的对比池为 **同 scenario_id 历史**，禁止跨场景当 SOTA
  - KEEP 后 `saved/keepers.json` 更新的是 **该 scenario 键**，不是全局单指针
- [ ] **训后 journal（finalize 成功、TSV 已追加后、ledger commit 之前）**：
  ```bash
  python3 scripts/journal_append.py --event round --apply [--note "…"]
  ```
  （finalize 失败或未追加 TSV 行 → **不** append）
- [ ] **训后（步骤 10）**：更新 EXPERIENCE 时，**必须**在该轮块内填写：
  - `tier_this_round` / `tier_change` / `tier_verdict`
  - `innovation_depth`: routine | extend | novel
  - `innovation_rationale`: 一句（例如 `torchvision.resnet50` / 按 FNO 论文 / 自研 physics block）
  - 同时更新 `## Tier 状态` 二维矩阵对应格子。
  然后 `git add -f saved/experiment_journal.json`（若已 append）+ `_runs/results.tsv _runs/results.jsonl`（及 `round_decision.json` / `EXPERIENCE.md` / `keepers.json` 若有变更）→ `git commit -m "ledger: …"`

## 多实验并行（默认并行，非例外）

**OVAT ≠ 串行**：每槽改一个变量（可归因），多个独立单变量候选应并行探索。手跑每轮也先**枚举独立 OVAT 候选**；`≥2 独立 ∧ max_parallel≥2` → **默认并行** `min(max_parallel, 候选数)` 槽；串行须理由（候选有依赖 / C-D 深单变量 / 结构大改 / E 预研 / max_parallel=1）。规则与 PROTOCOL §6 / auto-nn-run.sh 一致（本技能不重述，冲突以 PROTOCOL §6 为准）。

### slot 机制（实验槽位）

多实验并行用**实验槽位**：`NN_SLOT=0..N-1` + `NN_PARALLEL_TOTAL=N`，每槽一个独立实验（不同 config/超参），exp 目录标 `_s<slot>of<total>_`，全部结束后一次 `finalize-round` 聚合。与 `train.py`（`_sXofY_` 标记）、`experiment.py`（解析槽位）、`PROTOCOL §6`、`auto-nn-run.sh` 一致。

> **`NN_SLOT`/`NN_PARALLEL_TOTAL` = 实验槽位**（每槽一个独立实验），**不是**「单实验多卡数据并行」。框架的单实验多卡数据并行（若有）是 in-process 机制（DataParallel/DDP），不经这些 env。

**slot ≠ GPU**（与物理 GPU 数无关）：`free_gpus ≥ 槽数` → 各槽不同 `CUDA_VISIBLE_DEVICES`（分散）；`free_gpus < 槽数` → 多槽共享同卡（多个槽设同一 `CUDA_VISIBLE_DEVICES`，受显存约束，勿超额）。**单卡机器 max_parallel≥2 → 多 slot 共享单卡，天然并行**。若家目录有允许用的显卡名单（`~/.gpus`），指定的卡号必须在名单内；没建该文件则不限制占用。

### recipe（copy-paste 可跑）

1. **Seed 稳健性**（KEEP 后）：复制 base config × K seed → K 槽（多卡分散 / 单卡共享）→ `finalize-round` → mean±std。
2. **Tier A HPO sweep**（未穷尽档）：LR×WD 网格 → ceil(N/max_parallel) 批 → 每批 `finalize-round`。
3. **升档首探**（≥2 独立候选）：2 槽 → `finalize-round`。

### 执行步骤（slot 版）

- [ ] **1. 枚举独立 OVAT 候选**（同 auto-run step 3a）：列候选 + 独立性说明。
- [ ] **2. 训前 commit**：`git add -A && git commit -m "experiment: parallel N-slot setup"`。
- [ ] **3. 起 `min(max_parallel, 候选数)` 槽**：各槽 `NN_SLOT` 不同、`NN_PARALLEL_TOTAL=N` 相同；`CUDA_VISIBLE_DEVICES` 按 `free_gpus` 分散（free≥N）或共享（free<N）。示例（4 槽分散 4 卡）：

```bash
mkdir -p _runs/logs _runs/configs
# 每槽独立 config（Config-Only）；NN_SLOT 不同，NN_PARALLEL_TOTAL 相同
CUDA_VISIBLE_DEVICES=0 NN_SLOT=0 NN_PARALLEL_TOTAL=4 setsid poetry run python train.py --config _runs/configs/cfg0.json > _runs/logs/run_slot0.log 2>&1 < /dev/null &
CUDA_VISIBLE_DEVICES=1 NN_SLOT=1 NN_PARALLEL_TOTAL=4 setsid poetry run python train.py --config _runs/configs/cfg1.json > _runs/logs/run_slot1.log 2>&1 < /dev/null &
# 单卡共享时：四槽都 CUDA_VISIBLE_DEVICES=0
```

- [ ] **4. 等待**：`wait` 或 `./scripts/wait-train.sh --parallel-total N`。
- [ ] **5. 一次 finalize**：`poetry run python -m contract finalize-round _runs/exp/*_s*of${N}_*`（`_sXofY_` 标记的目录）。
- [ ] **6. KEEP/discard + EXPERIENCE + 训后 commit 台账**（同单轮步骤 10）。

### 注意

- `NN_SLOT`/`NN_PARALLEL_TOTAL` = **实验槽位**，非单实验多卡数据并行（那是 in-process 机制，不经这些 env）。
- slot 共享单卡受显存约束；`max_parallel` 须按显存设，勿超额（框架无 OOM preflight）。
- 多 slot 由 `finalize-round` 聚合；KEEP 基于**同 scenario_id 历史**，各槽独立比较，禁止跨槽当 SOTA。
- 仅「已穷尽档∧plateau」禁同变量 grid；独立单变量并行 + 未穷尽 HPO 不受限。

## 复现实验（Config-Only）

从已有实验的 `config.json` 直接复现训练：

```bash
# 直接使用已有实验的 config.json
poetry run python train.py --config _runs/exp/<experiment_dir>/config.json
```

见 PROTOCOL §2.5。

## 硬约束

**Config-Only**：实验参数（LR、MODEL_ARCH、EPOCHS、SEED 等）**必须**通过 `--config config.json` 传入：

- ❌ 禁止：`NN_LR=0.001 poetry run python train.py`
- ❌ 禁止：`poetry run python train.py --lr 0.001`
- ✅ 必须：`poetry run python train.py --config config.json`

**系统参数**（NN_SMOKE、NN_DEVICE 等）允许通过环境变量。

**train.py CLI flag**（`--config` 除外，均可用环境变量替代）：

| flag | 环境变量 | 说明 |
|------|----------|------|
| `--experiment <name>` | `NN_EXPERIMENT` | 实验目录名 |
| `--experiment-desc <text>` | `NN_EXPERIMENT_DESC` | 实验描述 |
| `--slot <int>` | `NN_SLOT` | 实验槽位（与 `--parallel-total` 联用） |
| `--parallel-total <int>` | `NN_PARALLEL_TOTAL` | 并行槽位总数 |
| `--device auto\|cpu\|cuda\|gpu` | `NN_DEVICE` | 设备（cuda/gpu 同义） |
| `--no-auto-finalize-round` | `NN_AUTO_FINALIZE_ROUND=0` | 单槽也不自动 finalize_round |

## 下一步常见推荐

分析阶段进度 → **`/auto-nn-analyse`**；改路线图 → **`/auto-nn-human-guidance`**；场景补完 → **`/auto-nn-modify`**；多轮 → **`/auto-nn-auto-run`**。完整串联图见 [`skills/post-migration/README.md`](../README.md)。

## 对用户怎么说（人话）

- **一轮结果**：「保留/作废 + 主指标 + 是否刷新最好」；禁裸 `KEEP`/`discard`/`keeper`。
- **场景**：「这轮跑的是 X 场景」；写 config 时内部用 `scenario_id`，对用户说场景名。
- **并行多槽**：「N 路同时在训，各自独立比最好」；禁跨场景称 SOTA。
- **训后 commit**：对用户只说「成绩表/日记已提交」；不必列 `keepers.json` 等文件名除非用户问。

**坏**：「finalize_round 后 saved_keeper: lp01… KEEP 成功」  
**好**：「这轮保留了：测试准确率 0.91，刷新了该场景的历史最好。」

## 活动 log

轮末 commit 提醒后 **须** append：`python3 scripts/append-skill-activity.py append --skill auto-nn-manual-run --phase end --summary "KEEP|DISCARD …"`（与 `journal_append round` 并存）。开关 `agent.skill_activity_log`（默认 true）。
