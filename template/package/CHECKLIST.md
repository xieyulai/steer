# CHECKLIST.md — 模板完成判据

本文件是 **迁入业务项目**的收尾标准（由 `new-project.sh` 安装为 `<project_root>/CHECKLIST.md`）。  
模板维护仓以仓库根 `.template-maintainer` 标记；正文仅本文件一份。

> **不承诺**：目标环境 PyTorch/Poetry、数据集与业务逻辑正确性；以下仅覆盖 **仓库结构、守门与训跑验收**。

> **模板治理（范式级扩展）**：本 CHECKLIST **禁止**按单项目增删条款。仅允许 **§通用** + **`### 仅 profile=<name>`**（范式边界见 `profiles.yaml` 与 `PROTOCOL.md`）。

---

## 0. 对外完成判据（唯一门禁）

**向用户或 PR 声明「迁移/立项收尾完成」之前，只允许以下三条（缺一不可）：**

| # | 命令 / 章节 | 要求 |
|---|-------------|------|
| **A** | `bash scripts/verify-migration-complete.sh` | **退出码 0**（§2–§4 大部分项由此脚本覆盖） |
| **B** | `bash scripts/nn-doctor.sh` | **0 FAIL**（WARN 不阻断；init 时若干 WARN 预期。0 FAIL 时写 `saved/doctor_last.txt` 作 `/auto-nn-analyse` 首基线） |
| **C** | 下文 **§5 训跑 smoke** | 须**真实执行**并满足 §5 勾选项 |

**不算完成：** 仅提交 contract/workspace 改动、仅通过 G-评估、或未跑 verify 就回复「迁完了」。  
**说明书门禁：** `references/manual/abcde-manual.md` 必须存在——`new-project` 缺则立项 **exit ≠ 0**；§0-A verify 与 §0-B doctor（`abcde_manual`）缺则 **FAIL**（非「事后手动即可算完成」）。  
**HARD-GATE（F1-signoff）** = 改代码前的**口径签核表**（仅 H/E/D/T/O 决定）；**§0-A/B/C** = 改代码后的**唯一完成门禁**。  
HARD-GATE 在**改代码之前**；本节在**改代码之后**。

**如何勾选：** 读取 `nn-config.yaml` 的 `profile` → **迁入项目先** `bash <template_root>/scripts/governance-sync.sh`（同步 `profiles.yaml`、`verify`、`smoke-check`、`wait-train` 等，写入 `.auto-nn/governance-rev`）→ 再跑 **§0-A**（含 **auto-nn-run 配套** 硬检）→ 对照 **§2–§4** → 必跑 **§5**。

---

## 1. 先选入口

| 场景 | 入口 | 说明 |
|------|------|------|
| **空目录新项目** | [`scripts/new-project.sh`](scripts/new-project.sh) | 复制业务骨架（**不含** `docs/`、`skills/`）；HARD-GATE 见模板根 SKILL；收尾 §0 + §5 |
| **已有仓库迁入模板** | 模板根 [`skills/maintainer/auto-nn-init/SKILL.md`](skills/maintainer/auto-nn-init/SKILL.md) 入口 A | **禁止原地改旧仓**；见下「双路径 + git」 |

**入口 A — 双路径（禁止原地迁移）**

| 路径 | 含义 |
|------|------|
| `source_root` | 旧项目，阶段 0～1 **只读** |
| `target_root` | 迁后目录，**≠ source**；推荐 `new-project.sh`（含 **git init**） |

阶段 2 起只改 `target_root`；根目录写 `.auto-nn/migration-source`（一行绝对路径指向 `source_root`）。`verify` 会检查 git 仓库且路径不等。

**阶段 0 分析（对旧仓，改代码前）**

```bash
bash <template_root>/scripts/migration-compare.sh \
  --template-root <template_root> --project-root <source_root>
```

**迁后验收（只对 target_root）**

```bash
cd <target_root> && bash scripts/verify-migration-complete.sh   # §0-A，exit 0
cd <target_root> && bash scripts/nn-doctor.sh                   # §0-B，0 FAIL（FAIL 阻断；0 FAIL 写 saved/doctor_last.txt）
```

**探索期（optional）**：验收通过并删除/归档 `CHECKLIST.md` 后，方可在 HUMAN NOTE 或 `nn-config` 启用 `objective_mode: explore`（迁移中 doctor WARN）。

**迁移口径汇总**：`target_root/.auto-nn/migration-summary.md`（`new-project.sh` 带占位；用户 **F1-contract=①** 后 Agent 用完整 F1 汇总表覆盖；阶段 2 前须非空。**迁移留档**，运行时不读；场景权威见 README `SCENARIO_POLICY`）。

业务仓**无** `docs/`；勿读模板仓 `docs/`（仅供人维护）。

---

## 2. 根目录与契约文件（§0-A 未覆盖时对照本表）

> **优先跑** `bash scripts/verify-migration-complete.sh`（含 `verify_project_layout.py`：根目录白名单、禁止整包拷贝残留、manifest 必备）。本节保留 verify **未覆盖** 的项（文案改写、部分手工清理）。

在 **`<project_root>`** 执行（将 `TEMPLATE` 设为 **`<template_root>/template`**，即模板维护仓内的业务安装包）：

```bash
TEMPLATE="<template_root 绝对路径>/template"
PROJ="$(pwd)"

manifest=(
  README.md
  PROTOCOL.md
  CLAUDE.md
  EXPERIENCE.md
  CHECKLIST.md
  pyproject.toml
  contract/__main__.py
  profiles.yaml
  train.py
  experiment.py
  nn-config.yaml
  auto-nn-run.sh
  reflect.py
  scripts/claude_stream_summarize.py
  scripts/regen_results_tsv.py
  scripts/wait-train.sh
  _runs/logs/README.md
  _runs/agent/README.md
)
missing=0
for f in "${manifest[@]}"; do
  if [[ ! -e "$PROJ/$f" ]]; then
    echo "[缺] $f  ← 从模板复制: cp \"$TEMPLATE/$f\" \"$PROJ/$f\" 后按任务改 README/contract 等"
    missing=1
  fi
done
[[ "$missing" -eq 0 ]] || echo "存在缺项：补全后再做 §4–§5"
```

- **`CHECKLIST.md`**：迁入项目可将模板根本文件 **复制**到目标仓库，便于目标仓库内自检；亦可始终打开 `<template_root>/CHECKLIST.md` 对照（不必复制）。
- **`contract/__main__.py`**：`python -m contract` / `finalize-round` / `sanity`。
- 若目标项目**坚持用 pip**：须在 `README.md` 写明依赖；SKILL 示例里的 `poetry run` 需改为等价命令。
- **清理模板特有文件**（`docs/` 为模板仓维护文档，**与业务仓无关**；立项不复制 `docs/`、`skills/`）：
  - [ ] 已删除（若存在）：`docs/`、`skills/`、`.claude/`（含历史 `.claude/skills/`）、`skeletons/`、`scripts/init.sh`、`scripts/generate-profile-locks.sh`、`scripts/new-project.sh`、根目录 **`automation-logs-nn/`**、**`NN_PROFILE`**、历史名 **`run-nn-agent.sh`**（已废止，统一为 `auto-nn-run.sh`）。**须保留**：`auto-nn-run.sh`、`reflect.py`、`scripts/claude_stream_summarize.py`、`scripts/regen_results_tsv.py`、`scripts/verify-migration-complete.sh`、可选 `scripts/validate-human-guidance.sh`。
  - [ ] **全局技能**：维护者/实验者已在模板仓执行 `install.sh`（业务仓 **不** 含 `auto-nn-*` 技能副本）。
  - [ ] **`CHECKLIST.md`**：业务仓库迁移完成后应删除（对照时用模板根本文件）。
- **模板文本替换**（`new-project.sh` 复制的模板文件仍含占位内容，Agent **必须**改写）：
  - [ ] **`README.md`**：标题/引用不再是 `auto-nn-experiment`；**init 只改**首行标题 + **`§3 立项口径`** + 可选 **`§4 PROJECT_NOTES`**；**禁止**删改 `<!-- NN_TEMPLATE:* -->` / `<!-- SKILLS_* -->`；**须保留** `NN_TEMPLATE:SKILLS` 结构（与 `template/package/README.md` 一致）；**§3** 含 `§3.1` 评估 prose + `D2_DATA_SPLIT` / `SCENARIO_POLICY` / `METRICS_SNAPSHOT` / 可选 `AGENT_BOUNDARY`；**`/auto-nn-update`** 时 `merge-readme-template-blocks.py` 只更新模板区、不覆盖 §3/§4。
  - [ ] **`README.md` 含 `<!-- D2_DATA_SPLIT -->` … `<!-- /D2_DATA_SPLIT -->` 块**（profile 必填键齐全）；`python3 scripts/d2_data_split_gate.py .` exit 0。
  - [ ] **多场景项目**：`README` 含 `SCENARIO_POLICY` 块（或 `SCENARIO_AXIS: none` / D2 无 `EVAL_SCENARIO`）；`python3 scripts/scenario_policy_gate.py .` exit 0（`governance-sync` 已同步该脚本）。
  - [ ] **`.gitignore`**：已从 `template/package/.gitignore` 复制（`governance-sync` 会自动同步）；**禁止** `_runs/` 整目录忽略（须保留 `_runs/results.tsv` 入库）；若 `__pycache__` 等曾被 commit，执行 `git rm -r --cached` 后重提。
  - [ ] **`data/README.md`**：已创建，写明数据文件名 + 形状（shape）+ 来源（`.gitignore` 白名单 `!data/README.md` 需此文件才生效）。
  - [ ] **`pyproject.toml`**：`name` / `description` / `authors` 已从模板占位改为目标项目文案（依赖块不动，除非有额外依赖）。
  - [ ] **`build_learner` 从 train_loader 首个 batch 推断输入形状**（模板 `_infer_image_shape`）：`workspace.build_learner` 不再读 `SMOKE_*` 形状参数（dummy smoke 已移除）；若业务模型需要形状信息，须从 `source`（真 DataLoader batch）推导，否则不同数据形状下 forward 路径未被验证。
  - [ ] **`_runs/results.tsv` 表头**：迁 contract 后 `python3 scripts/regen_results_tsv.py --repo-root .` 并 `rm -f _runs/.tsv-header-pending`（**§0-A 会校验表头**）。
  - [ ] **`_runs/round_decision.json`**（旧名 `evaluation_result.json`）：正式训练前不应有残留。
  - [ ] **仓库根无 `logs/` / `run*.log`**：smoke 或旧流程可能在根目录遗留 `logs/`、`run.log`、`run2.log`，已清理；单槽/多槽训练日志**一律**在 `_runs/logs/`（单槽默认 `_runs/logs/run.log`）。

---

## 3. `contract/` 门面与 profile（§0-A + 本表；通用 + 按范式）

> `check_contract_layout`、`check_test_authority`、profile 演示指标冲突等由 **§0-A** 检查。本节为 **verify 未覆盖** 的细项与 profile 专条。

### 3.1 通用（所有 profile）

- [ ] **`contract/`** 下除 `__init__.py`、`__main__.py`、`metrics.py`、`runtime.py`、`prepare_data.py`、`test.py` 等**确有引用**的文件外，无孤立模块（未被门面或 `train.py` 引用的 `.py` 应删除或接入明确路径）。
- [ ] **`nn-config.yaml`** 存在且 `profile` 字段为 `profiles.yaml` 中已有 profile（`supervised` | `rl` | `physical`）。
- [ ] **迁入/新建项目**：`time_budget`、`gpus`、`max_parallel`、`exploration_mode` 已与 HARD-GATE **O1/O2/G1** 一致（O2 默认 `max_parallel: 1`；有 GPU 时 `gpus` 为显式 `[0,…,N-1]`，除非 O2 选 ②）；**O3-baseline-anchors** 已写 `saved/baseline_start_intent.json`（推荐 `start_runs=plain+reference`；测条件对齐；找不到请用户给；弱化跳过则写 `.auto-nn/baseline-intent-skipped`）。近版须有 `.auto-nn/init-align.json`。**入口 B 亦须 O 签字**，不因 `new-project.sh` 预填而跳过。
- [ ] **profiles.yaml** 中该 profile 的 `contract` / `workspace` 方法列表均在对应 `__init__.py` 门面类上实现或继承自 `ExperimentBase`。
- [ ] **contract 四文件 + G-评估**：见 **§0-A**（`check_contract_layout` / `check_test_authority`）。
- [ ] **`metric_keys` 与 `auxiliary_keys` 互斥且非空**：`set(metric_keys) ∩ set(auxiliary_keys) == ∅`，`metric_keys` 至少一个键。验证：`python3 -c "from contract import create_contract; c=create_contract({}); assert c.metric_keys; overlap=set(c.metric_keys)&set(c.auxiliary_keys); assert not overlap, f'重叠:{overlap}'"`。
- [ ] **TSV 列覆盖所有 `metric_keys` + `auxiliary_keys`**：`_default_tsv_columns()` 返回的列表包含两个 dict 中每个键。验证：`python3 -c "from contract import create_contract; c=create_contract({}); cols=c._default_tsv_columns(); all_keys=set(c.metric_keys)|set(c.auxiliary_keys); missing=all_keys-set(cols); assert not missing, f'TSV缺列:{missing}'"`。

### 3.2 仅 profile=supervised

（无额外模板条款；任务/数据/指标说明写在项目 `README.md`。）

### 3.3 仅 profile=rl

- [ ] **Preflight 编排**（见 **PROTOCOL §3.0.1**）：`train.py` 训前 `contract.preflight_check()`（仅静态守门）+ `ws.preflight_env_check()`；**不要**要求出现 supervised 的 `loss OK`。
- [ ] workspace 门面类实现了 **`preflight_env_check`**（`profiles.yaml` → rl.workspace）。
- [ ] contract 门面类的 **`should_keep`** 若有 `history_experiment_substr` 逻辑已正确覆盖或提升到模板。
- [ ] **contract 瘦身**：`contract/` 下除 `__init__.py`、`metrics.py`、`runtime.py`、`prepare_data.py`、`test.py` 外，无框架残留文件（`checkpoint.py`、`evaluation.py`、`workflow.py`、`data.py`、`nn_sanity.py` 等已删除）。

### 3.4 仅 profile=physical

（无额外模板条款；PDE/物理约束细节写在项目 `README.md` 与 workspace 实现。）

---

## 4. 布局守门（§0-A 未覆盖；与 preflight 同源）

在 `<project_root>` 且 `PYTHONPATH` 含 `<template_root>` 与 `skills/maintainer/auto-nn-init`（迁入项目无 `skills/` 时用模板根路径）：

```bash
poetry run python -c "
from pathlib import Path
from comparator import check_train_encapsulation, check_root_py_layout
assert check_train_encapsulation('train.py') == [], check_train_encapsulation('train.py')
assert check_root_py_layout('.') == [], check_root_py_layout('.')
print('G-封装/G-布局 OK')
"
```

- [ ] **G-封装**：`train.py` 无 `from workspace.<子模块> import`。
- [ ] **G-路径**：`train.py` 使用 `experiment.allocate_exp_dir` 或 `/_runs/exp/`（禁止仅根目录 `exp/`）。验证：`PYTHONPATH=. python3 -c "from experiment import check_train_exp_dir_layout; assert not check_train_exp_dir_layout('.')"`.
- [ ] **G-门面**：rl/supervised 的 `Workspace` 无 `prepare_data`（仅 `contract.prepare_data`）。验证：`PYTHONPATH=. python3 -c "from experiment import check_profile_facade; assert not check_profile_facade('.')"`.
- [ ] **G-布局**：根目录无非白名单探针 `.py`（或已列入 `NN_ROOT_PY_ALLOWLIST`）。

---

## 5. 训跑 smoke（§0 门禁 B — 必须执行）

在 **`<project_root>`**（**统一用脚本**，勿手写 grep；RL 与 supervised 判据不同）：

```bash
bash scripts/check-env.sh          # 换机 / clone 后先跑；FAIL → poetry install（慢则换源，见脚本提示）
poetry install                     # 可先 poetry env list / python3 -c "import torch" 看能否复用本机环境
bash scripts/smoke-check.sh
# 若已跑过训练、只校验日志：
# bash scripts/smoke-check.sh --log _runs/logs/migration_smoke.log
```

**§5 勾选项**（与 §0-A 一起构成对外完成判据）：

- [ ] **§0-A 已通过**（`bash scripts/verify-migration-complete.sh` 退出码 0）。
- [ ] **`bash scripts/check-env.sh` 退出码 0**（Poetry 虚拟环境 + torch 就绪；换机后常见需先 `poetry install`）。
- [ ] `poetry install` 成功（或项目文档声明的等价环境已就绪）。
- [ ] **`bash scripts/smoke-check.sh` 退出码 0**（脚本内 `NN_RELAUNCH=1 NN_SMOKE=1`；**supervised 另注入 `NN_EPOCHS=2`**，避免跑满业务 `EPOCHS`；日志默认 `_runs/logs/migration_smoke.log`）。

### 5.1 各 profile 脚本内判据（供对照，不必手跑 grep）

| profile | 日志须含 | 产物须含 |
|---------|----------|----------|
| **supervised** | `静态守门 OK`、`loss OK` | `_runs/round_decision.json` 非空 |
| **rl** | `静态守门 OK` | `_runs/exp/*/results.json` 非空 + `_runs/round_decision.json` 非空 |
| **physical** | `静态守门 OK` | 同上 |

**通用 smoke 判据（§5）：** 不再按 profile grep `smoke: OK` dummy 标记，不再检查 train_dynamics 遥测。硬验收 = `train.py` exit 0 + `_runs/round_decision.json` 非空 + **实质指标闸**（主分 `primary_metric` 有限；`_error`+主分 0 失败兜底 → FAIL）。supervised 的 `静态守门 OK`/`loss OK` 来自 preflight，仍信息性输出。smoke 时长由 `NN_SMOKE_BUDGET`（默认 120s）墙钟控制（TimeGuard 显式传参，到点 finalize）；`NN_TIME_BUDGET` 已冻结为 `nn-config.yaml:time_budget` 派生量（smoke 不再借用）。

- [ ] 已提醒用户：后续常规迭代可 `unset NN_RELAUNCH`，再跑训练确认 **G-契约** 不误报。

---

## 6. 与本仓库的关系

- 本文件位于 **`template/package/CHECKLIST.md`**；`skills/maintainer/auto-nn-init/CHECKLIST.md` 仅 **转发**至此，避免两处正文漂移。
- **init Skill**：代码改完后 **必须先 §0-A verify**；再 **§5 smoke**；不得在未通过前宣称完成。
