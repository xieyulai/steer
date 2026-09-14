---
name: auto-nn-update
description: >-
  业务仓一键拉模板：cwd=项目根 bash scripts/auto-nn-update.sh → governance-sync
  + reflect/gpu 硬门禁 + verify/doctor。前提：模板维护仓已 git pull。
  NL: 拉模板|sync template|governance|update. NOT: 业务分析→analyse.
---

# auto-nn-update — 业务仓一键拉模板

**单一职责：** 在 **业务仓根目录** 跑 **`bash scripts/auto-nn-update.sh`**，一次完成 governance-sync、硬门禁、验收。**Agent 必须执行脚本，不要拆成手敲多步。**

权威：`PROTOCOL.md`（governance）；真源：`template/package/scripts/auto-nn-update.sh`（经 governance-sync 下发到业务仓 `scripts/`）。

## Code Contract（pilot，2026-07-15）

> `scripts/check_skill_contract.sh` 自动对账本段与 `template/package/*` 实际符号。
> 失败 → release-check 第 6 步门禁拦截。
> **强检字段**（对账失败即拦截）：`calls_scripts` / `reads_cfg_keys` / `env_vars_consumed`；其余（`pluggable_symbols` / `referenced_gates` 等）为 informational，release-check 不强检。

```yaml
calls_scripts:
  - scripts/auto-nn-update.sh                 # 主入口（业务仓根目录执行）
  - scripts/_check_template_version.sh        # 版本 gate（步骤 4）
  - scripts/governance-sync.sh                # 全量下发（步骤 5）
  - scripts/regen_results_tsv.py              # 已有成绩表：sync 末对齐表头（步骤 5）
  - scripts/lib/migrate_agent_keys.py         # agent.* → 顶层 additive（步骤 5）
  - scripts/lib/migrate_goal_schema.py        # v3→v4 goal schema（步骤 5/6）
  - scripts/manage_goal.py                    # goal 升级提示（步骤 6）
  - scripts/check_reflect_runtime.py          # reflect 依赖 + import（步骤 7）
  - scripts/verify-migration-complete.sh      # verify（步骤 8）
  - scripts/nn-doctor.sh                      # doctor 校验（步骤 8）
  - scripts/merge-readme-template-blocks.py   # README 模板区 merge（同步范围）
  - scripts/build-run-context.py              # run_context（同步范围）
  - scripts/gpu_snapshot.py                   # GPU 快照（同步范围）
  - scripts/compress-experience.py            # 压缩/外部证据（同步范围）
  - scripts/backfill_scenario_tsv.py          # Agent 轮末：scenario_id 空行补全
  - scripts/sync_ledger.py                    # Agent 轮末：TSV/jsonl 一致性
  - scripts/mark-reflect-consumed.sh          # Agent 轮末：pending 反思归档
  - scripts/append-skill-activity.py          # 活动日志（skill_activity_log）

env_vars_consumed:
  - NN_TEMPLATE_ROOT                          # template-root 解析（步骤 2）
```

## 何时使用

- 用户要 **拉最新模板** / **update** / **governance-sync**
- **doctor 报治理版本漂移**（governance-rev）
- 模板维护者已在维护仓 **git pull** 后，要在业务仓对齐

## 前提（必守）

1. **模板维护仓已更新**：维护者 `git pull`（或远端已 push 且本机 template-root 指向的目录已 pull）
2. **cwd = 业务仓根**（含 `scripts/governance-sync.sh` 或 `_runs/`）

**不要**从模板维护仓根目录发起 update；update 是业务仓自助操作。

## 怎么跑（Agent 必执行；用户只说 `/auto-nn-update`）

**用户侧：** 在业务仓对话里输入 **`/auto-nn-update`**（或「拉模板 / update」）即可。**不要**让用户手敲 `bash scripts/...` 或多步 sync。

**Agent 侧：** 在业务仓根目录执行（一条脚本，禁止拆成手敲 governance-sync + verify 多步）：

```bash
bash scripts/auto-nn-update.sh
```

同机且模板仓可能尚未 pull 时，Agent 加 `--pull-template`（用户无需知道参数名）。

**版本 gate flag（major bump / 严格降级）：**

```bash
bash scripts/auto-nn-update.sh --accept-major-bump   # 接受 major 版本升级（默认阻断）
bash scripts/auto-nn-update.sh --strict-version      # 拒绝降级（默认仅 WARN + 仍 sync）
```

首次更新（业务仓无 `.auto-nn/version`）无 flag 即可。

**脚本自动完成：**

1. **assert 业务仓**：`_assert_business_repo`（cwd 须含 `scripts/auto-nn-update.sh` 且非模板维护仓 `.template-maintainer`；否则 exit 1）
2. 解析 template-root（`$NN_TEMPLATE_ROOT` > skills symlink > `.auto-nn/template-root`）
3. 可选 `--pull-template`：先对模板仓 `git pull --ff-only`
4. **version gate**：`_check_template_version.sh`（在 governance-sync 之前；major bump 需 `--accept-major-bump` 放行，否则 exit 1 阻断）
5. `governance-sync.sh` 全量下发（reflect、gpu_snapshot、nn-config merge、**README 模板区 merge**、experience_ack、auto-nn-update.sh、…）；内含 `migrate_agent_keys.py`（agent.* → 顶层 additive）+ `migrate_goal_schema.py`（v3→v4 goal schema），均在 nn-config merge 之前跑
6. **旧 goal schema 升级提示**：检测到 v2/v3 goal 配置 → 提示 `manage_goal.py upgrade`（v4 已 no-op，`load_nn_config` 读时自动迁移；亦可手动 `migrate_goal_schema.py --write`）
7. **硬门禁**：`py_compile reflect.py`、gpu 脚本存在、治理版本对齐、**`check_reflect_runtime.py`（reflect 依赖文件 + import）**
8. `verify-migration-complete.sh` + **`nn-doctor.sh`（默认必跑；任一 FAIL → update exit 1）**（调试可用 `--skip-verify`）

**Agent 轮末可选收尾（doctor 报 WARN/FAIL 且属治理台账时，同一技能内继续，仍不让用户手敲）：**

- `scenario_id` 空行 → `python3 scripts/backfill_scenario_tsv.py --apply`
- TSV/jsonl 行数不一致 → `python3 scripts/sync_ledger.py --apply`
- pending 反思 + EXPERIENCE 已有有效 `reflect_ack` → `bash scripts/mark-reflect-consumed.sh "<摘要>"`

**不自动：** 业务仓 `git commit`（审 diff 后用户或 Agent 按用户要求提交）。

**sync 提交后首训**：须 `export NN_RELAUNCH=1`（或跑 `scripts/smoke-check.sh`，已自带 relaunch）；否则 G-框架/G-契约/G-治理文档 三源 diff 硬拦 preflight 与 doctor。

## 同步范围（与 governance-sync 真源一致）

| 组 | 内容 |
|----|------|
| 核心 | `experiment.py`、`auto-nn-run.sh`、`reflect.py`、`PROTOCOL.md`、… |
| 配置 | `nn-config.yaml` **只 merge 缺失键** |
| README | **`merge-readme-template-blocks.py`**：只更新 `NN_TEMPLATE:*` 模板区，**保留 §3/§4** |
| 分析/GPU | `build-run-context.py`、`gpu_snapshot.py`、… |
| 压缩/外部证据 | `compress-experience`、`scripts/lib/external/*`、… |
| 状态 | `.auto-nn/governance-rev`、`.auto-nn/version` |

**不带（整文件覆盖）：** `workspace/`、`contract/`（除 `__main__.py`）、`_runs/`、`EXPERIENCE.md` 正文。  
**例外（手术式 migrate，非整文件覆盖）：** 根级 `train.py` 在 `prepare_data` 后插入 `ws.wrap_train_loader(...)`（`migrate_wrap_train_loader.py`），以启用 D 档 `DATA_SAMPLER` 钩子。

## 对用户怎么说

| 用户问 | 答 |
|--------|----|
| 「update / 拉模板」 | 「好，我直接在业务仓跑 update：同步脚本和 reflect 等；**含 reflect 运行时验收**；README 里技能说明会自动对齐模板，你的 §3 指标和 §4 笔记不会动。」 |
| 「开 batch 前要对齐吗？」 | 「模板有更新时须先 `/auto-nn-update`（可加 `--pull-template`）；否则 auto-run 会 WARN governance_drift，reflect 可能缺 lib。」 |
| 「模板刚改了，怎么对齐？」 | 「你在项目里说 `/auto-nn-update` 就行，我来拉齐，不用你手敲 sync。」 |

**坏**：「请先在业务仓 bash governance-sync.sh，再 verify-migration-complete，最后 doctor。」  
**好**：「我直接跑 update：脚本和技能说明会对齐模板，§3 指标和 §4 笔记不动；有 WARN 我在同一次里帮你收尾。」

## 边界

- 不动业务逻辑与实验产物（见上表）
- layout FAIL → `/auto-nn-modify`
- 分析进度 → `/auto-nn-analyse`

## 活动 log

通过后 append：`python3 scripts/append-skill-activity.py append --skill auto-nn-update --phase end --summary "rev 前→后"`。
