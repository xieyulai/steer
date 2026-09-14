---
name: auto-nn-doctor
description: >-
  迁后结构体检：layout、governance rev 对齐、contract/门面/G-封装/G-评估、TSV、auto-run 配套、
  shell 语法、全局技能 rev、gate、遗留路径（默认轻量；--deep 含 verify+smoke）。
  轻量档含 train_encapsulation + hardcoded_params（静态扫描；hardcoded_params 命中才提示）。
  Agent 代跑 nn-doctor.sh。不改代码、不 apply 清理。
  NL: 体检|结构检查|health check|layout. NOT: 看成绩→check.
---

# auto-nn-doctor — 迁后结构体检

权威：`PROTOCOL.md`、CHECKLIST §0/§5；**文档体系** [`docs/nn-doctor/README.md`](../../../docs/nn-doctor/README.md)（检查项 [check-catalog](../../../docs/nn-doctor/check-catalog.md)、路由 [fail-routing](../../../docs/nn-doctor/fail-routing.md)）。

**本技能回答：「这个仓还能不能正常跑？」** 不回答「指标好不好」（→ `/auto-nn-analyse`）。

## Code Contract（pilot，2026-07-15）

> `scripts/check_skill_contract.sh` 自动对账本段与 `template/package/*` 实际符号。
> 失败 → release-check 第 6 步门禁拦截。
> **强检字段**（对账失败即拦截）：`calls_scripts` / `reads_cfg_keys` / `env_vars_consumed`；其余（`pluggable_symbols` / `referenced_gates` 等）为 informational，release-check 不强检。

```yaml
calls_scripts:
  - scripts/nn-doctor.sh                  # 主入口（代跑）
  - scripts/scan_no_fallback.py           # G-no-fallback 静态扫描
  - scripts/analyze_hardcoded_params.py   # 轻量档硬编码扫描（nn-doctor.sh 1c 段自动调用）
  - scripts/build-run-context.py          # run_context 检查（v1.26.1 FAIL）
  - scripts/manual-run-scope-check.sh     # §8 manual_run_scope_check + immutable_path_guard 子检查
  - scripts/append-skill-activity.py      # 活动日志（agent.skill_activity_log）
  - scripts/check-env.sh                  # env_runtime FAIL 提示

reads_cfg_keys:
  - agent                                  # 父键（含 .skill_activity_log / .exploration_*）
  - agent.skill_activity_log               # 活动日志开关
  - exploration_mode                       # 6 档 mode 值校验（v1.26.1）
  - ledger                                 # 台账（governance_rev 检查）

env_vars_consumed:
  - NN_SMOKE                               # smoke 档位（PROTOCOL §0.1）
  - NN_NOTES                               # 轮次备注（PROTOCOL §6）

referenced_gates:                          # 仅 informational，lint 不强检
  - G-cfg-no-defaults
  - G-no-fallback
  - G-repro-env
  - G-repro-cli
  - immutable_path_guard                 # IMMUTABLE 桶：experiment.py/contract/治理文档；FAIL 计入 exit 1
```

**`immutable_path_guard`**：无 `NN_RELAUNCH` 时三源 diff 命中破坏路径 → **FAIL**（与 preflight G-框架/G-契约/G-治理文档 同级硬锁）。

## 高频代号（人话见 glossary）

| 内部码 | 对用户怎么说 |
|--------|--------------|
| `PASS / WARN / FAIL` | 通过 / 提醒 / 不通过 |
| `layout` | 目录结构是否规范 |
| `governance_rev` | 模板版本是否对齐 |
| `tsv_header` | 记录表表头是否正确 |
| `G-封装` / `G-评估` | 训练封装 / 评估口径是否合规 |
| `env_runtime` | 运行环境（Poetry/torch/CUDA；换机后常见须 `poetry install`） |
| `human_guidance_gate` | 路线图保护检查 |
| `exploration_space_stamp` | 探索格子是否已打（正式训完须有 A–D；禁 E-；坏改题待办 schema 同检） |

## 对用户怎么说（人话）

- **贴《体检报告》前**：一句整体结论（例：「43 项通过，2 项不通过，要先修吞错扫描命中那处」）。
- **FAIL 项**：人话 + 推荐技能（「改训练封装 → `/auto-nn-modify`」）；检查名「目录结构（layout）」式对照 **一次**。
- **`env_runtime` FAIL**：「Poetry 环境里缺 PyTorch，换机后请在项目根执行 `poetry install`」；若用户抱怨慢 → 提示 **换 PyPI/PyTorch 源** 或 **`poetry env list` / `poetry env use` 复用本机已有 torch**（见 `check-env.sh` 输出）。
- **WARN**：说明不阻断，可继续跑实验。
- **不**替用户解读指标趋势（→ `/auto-nn-analyse`）。

**坏**：「G-no-fallback FAIL；governance_rev WARN；请 governance-sync」  
**好**：「体检：结构基本正常，但有一处「不吞错」违规需要改代码；模板版本略旧，建议同步治理文件。」

## 何时使用

- 「体检一下」「verify 不过」「表头对不对」「要不要 governance-sync」
- 迁后日常卫生检查（**非**迁完唯一门禁；深度档可对齐迁完验收）
- **不要**用于：看撞墙/成熟度档 → `/auto-nn-analyse`；清运行态 → `/auto-nn-clear`

## 与其它技能

| 技能 | 分工 |
|------|------|
| **doctor** | 机械健康、脚本验收 |
| **analyse** | 台账策略与趋势 |
| **modify** | 改能力（Modify-L/T/Scenario）；[docs/nn-modify/](../../../docs/nn-modify/README.md)（migration **Track O · O 轨清理**旧表述已由本技能链与 `/auto-nn-clear` 分工取代；清理须用户 **`--apply`**） |
| **init**（`/auto-nn-init`） | 一次性立项 / 迁入 |
| **auto-run** | 批内轮末 round-doctor；本技能管**手工/深度**完整体检 |

## 改码三原则（doctor 扫描项）

Agent 改 `train.py` / `workspace/` / `contract/` 须遵守 PROTOCOL §0.1 三条。doctor **scanner 覆盖 2/3**：

| 原则 | doctor 检查项 | 典型结果 |
|------|---------------|----------|
| config-only | `G-cfg-no-defaults`、`G-repro-env`、`G-repro-cli` | FAIL |
| no-fallback | `G-no-fallback`（`scan_no_fallback.py`） | **FAIL**（训前 preflight 同规则为 WARN） |
| pluggable | — | **不扫描**；`auto-nn-run` 每轮 prompt 自检 |

合理 optional 路径：`except` 同行或上一行 `# optional:` 可豁免 `G-no-fallback`。

## doctor 三条反馈通道（协同）

| 通道 | 何时 | 产物 | 谁读 |
|------|------|------|------|
| **本技能（手工/深度）** | 用户 `/auto-nn-doctor` 或 init/update 验收 | 完整体检表 | 人 + Agent 报告 |
| **round-doctor** | `./auto-nn-run.sh` 每轮末 | `_runs/doctor_reports/R{n}.log` → 下轮 prompt | `/auto-nn-auto-run` |
| **analyse 静默前置** | `/auto-nn-analyse` 开场 | `doctor --quiet` vs `saved/doctor_last.txt` | `/auto-nn-analyse` |

init 阶段 4 **0 FAIL** 时写入 `saved/doctor_last.txt` 作 analyse 首基线；analyse 结束会**覆盖**该文件（与 round-doctor 日志独立）。

## Agent 必做清单

- [ ] **D-1** 确认在**业务仓根**（有 `train.py`、`contract/`、`_runs/`）
- [ ] **D-2** 判断档位：默认**轻量**；用户说「深度 / 含 smoke / 迁完验收」→ **`--deep`**
- [ ] **D-3** 代跑：`bash scripts/nn-doctor.sh` 或 `bash scripts/nn-doctor.sh --deep`
- [ ] **D-3b** **`/auto-nn-analyse` 会代跑** `bash scripts/nn-doctor.sh --quiet`（仅 WARN/FAIL；全 PASS 时无输出）。本技能回答完整体检表；analyse 只做静默前置。
- [ ] **D-3c** **硬编码参数检查（轻量档默认；nn-doctor.sh 1c 段已自动跑）**：
  1. 脚本层（自动）：`nn-doctor.sh` 轻量档已调 `analyze_hardcoded_params.py` 扫 train.py + workspace build，命中输出 `hardcoded_params` INFO（无命中静默 PASS）。Agent **无需手跑**脚本，直接读 doctor 输出即可。
  2. **Agent 通读 train.py**（脚本之外的研判，轻量档默认做）：脚本只能机械扫，以下需 Agent 看 HYPERPARAMETERS 区段判断：
     - 哪些参数虽然用了 `_ev()` 但默认值不合理（如 BATCH_SIZE 默认 0）
     - 哪些参数命名不符合 `NN_XXX` 前缀规范
     - 是否有遗漏的硬编码常量（脚本正则/AST 误漏）
     - 给出具体修改建议（怎么改、改成什么）
  - 两者合并，作为 `hardcoded_params` INFO 条目，仅提示不强制修复
- [ ] **D-3d** **build 方法 metadata 返回签名检查**（轻量档默认）：
  - **Agent 直接读 `workspace/__init__.py`**（及其子模块如 `workspace/model.py` 等），检查所有 `build_learner` / `build_objective` / `build_optimizer` / `build_scheduler` / `build_transforms` 及委托的 `build_*_kwargs` 方法：
    - 返回值是否为 `tuple(obj, dict)` 形式（而非直接返回 obj）
    - 第二个元素是否为 `dict`（metadata 记录实际解析参数，无覆盖时返回 `{}`）
    - `train.py` 中调用处是否使用 `obj, _m = ws.build_*(...)` 解包 + `ExperimentBase.apply_build_meta(cfg, _m, "build_*")` 合并
  - **metadata 覆盖完整性**（关键！）：检查 build 方法体内的**硬编码默认值**是否出现在返回的 metadata 中：
    - 方法体内 `if/else` 分支选出的值（如 `net_arch` 根据 scenario 选择不同值）
    - `os.environ.get("NN_XXX", default)` 的 fallback 默认值
    - 直接硬编码的参数（如 `learning_rate=3e-4`、`POLICY_KWARGS` 里的默认值）
    - 这些值如果**不在 metadata 中返回**，则 config.json 无法记录实际使用的值 → 静默默认
  - 不满足时列为 `build_metadata_signatures` WARN 条目，给出具体修改建议（哪个方法缺哪个字段的 metadata）
- [ ] **D-3e** **复现性检查**（轻量档）：
  1. 检查 `experiment.py` 的 `build_repro_snapshot` 是否设 `config_only_mode: true`（**不**再扫 `NN_*` env）
  2. 检查 `train.py` 是否支持 `--config` 参数
  3. 可选：最新实验 `config.json` 是否含实验参数字段（非空 `LR`/`EPOCHS` 等）
  - 不满足 1–2：列为 `reproducibility` WARN 条目
- [ ] **D-3f** **Config-Only 检查**（轻量档）：
  1. G-repro-env：检查 train.py 是否读实验参数的 NN_* 环境变量
  2. G-repro-cli：检查 train.py 是否禁止 CLI 参数（除 --config 外）
  - 任一不满足：列为 FAIL 条目
- [ ] **D-3g** **数据体检（数据源类型 + 深度档基础统计）** — **规划中，当前 `nn-doctor.sh` 未实现**（下列为规格草案；轻量判类型 / 深度加统计）：
  1. **数据源类型**（轻量档默认）：Agent 读 `contract/`（`LOCKED_DATASET` / `DATASET_REGISTRY`）或 `workspace/prepare_data` 拿到数据根路径，判定：
     - `os.path.islink(path)` 真 → 标 `symlink`，附 `os.readlink(path)` 目标 → **复现性风险**（软链接换机易断，与 G-repro-env 同类）
     - 实存文件/目录 → `physical`
     - 路径不存在 / 远程缓存未下载 → `pending`
  2. **基础统计**（仅 `--deep` 或 init 锁契约前一次性；轻量档跳过）：加载 dataset 取样本数 / shape / 类别数 / 类别分布（max÷min 不平衡比）。**弱锁仓**（如硬编码 `datasets.FashionMNIST(...)` 无 contract 常量）尤其要做。
  - `symlink` 或 `pending` → 列为 `data_health` WARN 条目（附 readlink 目标 / 缺失路径）；不平衡比 > 10 → `data_health` WARN（提示类别加权/采样）；均无异常 → `data_health` PASS
- [ ] **D-4** 解析输出（`[nn-doctor] <项>\tPASS|WARN|FAIL\t<说明>`），填写 **《体检报告》**（下表）
- [ ] **D-4b** 若 **project_docs** 为 WARN：说明可能是**实验/领域记录文档**，请用户自行判断是否保留；**不**替用户删目录、**不**改 verify 规则
- [ ] **D-5** 每项 FAIL/WARN → **推荐** `/auto-nn-*` 或维护命令（**不**自动 governance-sync、不 apply prune）
- [ ] **D-6** 回复末尾**至少推荐一个**下一步技能

## 《体检报告》模板

```markdown
## 体检报告（auto-nn-doctor）

- **档位**：轻量 | 深度
- **总览**：PASS n / WARN w / FAIL f

| 检查项 | 结果 | 说明 |
|--------|------|------|
| layout | … | … |
| tsv_header | … | … |
| governance_rev | … | … |
| human_guidance_gate | PASS/WARN/SKIP | … |
| project_docs | WARN（若有 docs/doc/documentation/） | 可能是实验/领域记录，提醒用户自行判断是否保留 |
| build_metadata_signatures | PASS/WARN | build_* 方法是否返回 (obj, dict) 且 train.py 解包+apply |
| hardcoded_params | INFO | train.py 超参 + workspace build 硬编码常量分析（轻量档默认；仅提示不强制修复） |
| reproducibility | PASS/WARN | 轻量: config_only_mode、train.py --config、config.json 实验参数字段 |
| data_health | （规划中） | 数据源类型（symlink/physical/pending）+ 深度档基础统计（样本数/shape/类别/不平衡比）；`nn-doctor.sh` 未实现 |
| G-cfg-no-defaults | PASS/FAIL | G-cfg-no-defaults（三原则·config-only） |
| G-no-fallback | PASS/FAIL | G-no-fallback（三原则·no-fallback；doctor 档 FAIL） |
| exploration_space_stamp | PASS/WARN/FAIL | 探索格子：正式训完须 A–D×RDDN；禁 E-；发版戳前后空格口径见 fail-routing |
| … | … | … |

### 建议下一步
- （按 FAIL 路由表填写）
```

## FAIL → 推荐（固定）

完整路由表见 [`docs/nn-doctor/fail-routing.md`](../../../docs/nn-doctor/fail-routing.md)。摘要：

| 失败项 | 建议 |
|--------|------|
| layout / governance_rev / auto_run_bundle / shell_syntax | `governance-sync`（或 `/auto-nn-update`） |
| abcde_manual / baseline_start_intent | 补说明书 / 写尺子意图或 skip 标记（见 fail-routing） |
| init_align（坏卡 FAIL） | 重写对齐卡 `init_align.py write --amend` |
| shared_context_contract / fw_binding_* | `/auto-nn-modify` 或补 framework_binding（见 fail-routing） |
| G-cfg-no-defaults / G-no-fallback / G-repro-* | `/auto-nn-modify` 修代码 → `/auto-nn-doctor` 复检 |
| exploration_space_stamp | 正式训空格/禁 E-：查 finalize 与 update；历史空格见 fail-routing；坏改题待办修 jsonl |
| human_guidance_gate / auto_run_bundle（人类路线图） | 见 fail-routing 的 WARN 表 |
| contract / tsv / scenario / ledger / readme / smoke | 见 fail-routing 全文 |
| 结构已健康、问指标 | `/auto-nn-analyse` |

## 硬边界

- **禁止**改 `train.py` / `workspace/` / `contract/` / `experiment.py`
- **禁止**手改 `_runs/results.tsv` / `jsonl`
- **禁止** `govern-runs.sh clear --apply`、`rm -rf`（清理 → `/auto-nn-clear`）
- **禁止**默认 `--deep`（含 smoke，耗资源）；须用户明确要求
- **`__pycache__` / `.pyc`**：不参与 layout 判断；体检报告**勿**列为 FAIL 或建议删除

## 附录（落盘实现，非主入口）

```bash
bash scripts/nn-doctor.sh
bash scripts/nn-doctor.sh --quiet    # 仅 WARN/FAIL；供 /auto-nn-analyse 静默前置
bash scripts/nn-doctor.sh --deep
bash scripts/nn-doctor.sh --quiet --deep
```

## 下一步常见推荐

看趋势/撞墙 → **`/auto-nn-analyse`**；清理/绿场 → **`/auto-nn-clear`**；跑一轮验证 → **`/auto-nn-manual-run`**。完整串联图见 [`skills/post-migration/README.md`](../README.md)。

## 活动 log

完整体检报告后 **须** append：`--skill auto-nn-doctor --phase end --summary "N FAIL M WARN"`（`--deep` 同理）。开关 `agent.skill_activity_log`（默认 true）。
