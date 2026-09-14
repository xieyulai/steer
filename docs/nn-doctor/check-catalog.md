# nn-doctor 检查项目录

> **权威实现**：[`template/package/scripts/nn-doctor.sh`](../../template/package/scripts/nn-doctor.sh)  
> **路由**：WARN/FAIL 处理见 [fail-routing.md](fail-routing.md)

业务仓（`IS_TEMPLATE_ROOT=0`）跑轻量档时的检查项。模板维护仓（`.template-maintainer`）跳过部分业务仓专属项。

---

## 1. 布局与迁后文档

| 检查项 | 典型结果 | 说明 |
|--------|----------|------|
| `layout` | FAIL | `verify_project_layout.py`：根目录白名单、脚本集合、禁止整包拷贝残留 |
| `project_docs` | WARN | 存在 `docs/`、`doc/`、`documentation/` — 可能是领域文档，**人工**判断是否保留 |
| `git_repo` | FAIL | 非 git 仓库（迁后须 init） |
| `migration_summary` | FAIL | 缺少或非空 `.auto-nn/migration-summary.md`（迁移留档；场景权威见 README `SCENARIO_POLICY`） |
| `init_qa_log` | PASS/WARN | 立项问答 log 闭合校验；缺校验脚本 → WARN |
| `init_template_version` | PASS/WARN | `.auto-nn/init-template-version` 立项原始模板戳（只写一次）；旧仓缺戳 → WARN |
| `init_align` | PASS/WARN/FAIL | `.auto-nn/init-align.json`：缺 → WARN；坏 JSON/schema → FAIL；与 `nn-config` profile 不一致 → WARN |
| `abcde_manual` | FAIL | 缺 `references/manual/abcde-manual.md` |
| `abcde_manual_hygiene` | WARN/PASS | 手册存在时：退役旧名 / 头身对象类型冲突 → WARN（不替代存在性 FAIL） |
| `baseline_start_intent` | FAIL/PASS | init-qa-log 闭合后缺 `saved/baseline_start_intent.json` 且无 skip 标记 → FAIL |

---

## 2. 台账与场景

| 检查项 | 典型结果 | 说明 |
|--------|----------|------|
| `tsv_header` | FAIL/WARN | 表头 vs `regen_results_tsv.py --header-only` |
| `tsv_header_pending` | FAIL | 仍存在 `_runs/.tsv-header-pending` |
| `scenario_completeness` | FAIL/WARN | F1 清单、`scenario_default`、TSV `scenario_id`、`keepers.json` 对齐 |
| `results_tsv` / `results_jsonl` | WARN/FAIL | 台账文件存在与行数 |
| `baseline_tag` | WARN/PASS | E5：`config.json` / TSV `baseline_tag` 列（plain/reference/none） |
| `adapter_baseline_tag` | WARN/PASS | adapter 路径基线角色列 |
| `baseline_reference` | WARN/PASS | EXPERIENCE「基线锚点」`reference_anchor_value` 合法性 |
| `ledger_row_sync` | WARN | TSV 数据行数 ≠ jsonl 行数 |
| `ledger_git` | WARN | 台账未 track 或有未 commit 变更（PROTOCOL §6 步骤 10） |
| `legacy_progress_file` | WARN | 遗留 `progress.txt`（已废弃） |
| `journal_missing_with_tsv` | WARN | TSV 有数据行但无 `saved/experiment_journal.json` |
| `experience_ledger_audit` | WARN | EXPERIENCE 精华/Tier 表声称「已试/穷尽」的技术 token 在 TSV experiment/description 无留痕（`experience_ledger_audit.py`） |
| `exploration_space_stamp` | FAIL/WARN/PASS | TSV `exploration_space`：禁 `E-`；合法 A–D×RDDN 或空；已训空格：发版戳前 WARN、戳后 FAIL；无 `.auto-nn/exploration-stamp-since` → WARN；`e_feedback.jsonl` schema（若存在）并入本项同一脚本汇总，无独立 doctor 行（`check_exploration_stamp.py --check`） |
| `unregistered_config_keys` | WARN/PASS | 最近两行已训 `config.json` 相对变化的键不在 catalog `primary_keys`∪`scalar_keys`∪`ignore_config_keys` → WARN（`--check-unregistered`；缺对照/catalog → PASS） |

---

## 3. 治理与配置

| 检查项 | 典型结果 | 说明 |
|--------|----------|------|
| `governance_rev` | FAIL | `.auto-nn/governance-rev` 与模板不一致，或 profiles/wait-train/nn-doctor/verify 漂移 |
| `nn_config` | FAIL | 缺少或无法解析 `nn-config.yaml` profile |

**注意：** `governance_rev PASS` **不**表示人类路线图脚本已 sync 到业务仓（见 [fail-routing.md](fail-routing.md) 的 `human_guidance_gate`）。

---

## 4. Contract 与 profile

| 检查项 | 典型结果 | 说明 |
|--------|----------|------|
| `contract_layout` | FAIL | `check_contract_layout` |
| `train_encapsulation` | FAIL | G-封装：`train.py` 不得 `from workspace.<子模块> import`（`check_train_encapsulation`；与 preflight 同规则） |
| `cfg_no_defaults` | FAIL | G-cfg-no-defaults：实验参数不得使用 `cfg.get("KEY", default)`，须 `cfg["K"]` 强读（**严格：任何大写实验参数键带默认 → FAIL**；与 preflight 同规则） |
| `no_fallback` | FAIL | G-no-fallback：吞错 `except`（`except: pass` / `return 默认` 隐藏失败）；合理 optional 用 `# optional:` 豁免（scanner `scripts/scan_no_fallback.py`；三原则·no-fallback；**doctor 档 FAIL**，训前 preflight 同规则为 WARN） |
| `train_exp_dir` | FAIL | 训练 exp 目录布局 |
| `profile_facade` | FAIL | profile 门面 |
| `test_authority` | FAIL | G-评估：test 权威 |
| `contract_demo_metrics` | FAIL | profile 与演示指标冲突（如 physical 含 val_accuracy） |
| `shared_context_contract` | FAIL | train/workspace/contract 禁止 shared_context 承载/读取 contract 实例 |
| `fw_binding_decl` / `fw_binding_gaps` / `fw_binding_train_hooks` / `fw_binding_eval_hook` / `fw_binding_ckpt` | FAIL/WARN/PASS | `contract/framework_binding.yaml` 接入总表（`framework_binding_doctor`） |
| `env_runtime` | FAIL | `check-env.sh`：Poetry 虚拟环境、torch、CUDA/GPU 白名单（换机后常见 FAIL → `poetry install`） |
| `contract_sanity` | FAIL | `python -m contract sanity`（env 就绪后 Linear+MSE；env 未过则跳过） |
| `history_experiment_substr` | WARN | contract 仍 override 已废弃字段 |

---

## 5. README 与反思索引

| 检查项 | 典型结果 | 说明 |
|--------|----------|------|
| `readme` | FAIL | 缺 README 或仍为模板标题 |
| `readme_modify_sync` | WARN | 最近 commit 改 contract 未改 README |
| `readme_consistency` | WARN/FAIL | `readme_consistency_gate.py` R1–R5 |
| `reflect_index` | FAIL/WARN | REFLECT_INDEX 账本健康 |
| `reflect_index_repair` | WARN | 可试 `repair-reflect-index.sh --apply` |

---

## 6. auto-run 配套

| 检查项 | 典型结果 | 说明 |
|--------|----------|------|
| `auto_run_bundle` | FAIL | 缺 reflect/wait-train/claude_stream/**g-human**/journal 等脚本 |
| `auto_run_syntax` | FAIL | `auto-nn-run.sh` bash -n |
| `run_context` | WARN | `build-run-context.py --write` |
| `explore_objective` | WARN | 缺 lib 或迁移中误用 explore |
| `goal_status` | INFO/PASS | `nn-config goal.target` 设了吗、当前最好 vs goal（`check_goal.py`；达标 PASS / 未达 INFO / 未设 INFO「loop 跑满 N」）。设/改走 `/auto-nn-goal` |
| `goal_target_exclusive` | WARN | `goal.target` 与 `goal.targets` 互斥；同 yaml 里两个都在 → WARN（v4 schema 推荐 `target`，`targets` 仅作多 metric 复合用） |
| `goal_target_presence` | PASS/INFO | `goal.target=null` **仍视作设了 goal**（presence 用 `key in raw` 而非 `key is not None`）；未设 goal → INFO「loop 跑满 N」 |
| `goal_schema_consistency` | WARN | 4 组合（单/多场景 × 单/多 metric）的 `goal.target` / `goal.per_scenario` / `goal.spec` 表达一致（例：多场景单 metric 应写 `per_scenario` map；单场景多 metric 应写 `spec`） |
| `human_guidance_gate` | PASS/WARN/SKIP | install + baseline；详见 [fail-routing.md](fail-routing.md) |
| `shell_syntax` | FAIL | 关键 shell 脚本 bash -n |

**`auto_run_bundle` 必需文件（节选）：**  
`human_guidance_gate.py`、`lib/human_guidance_gate.py`、`lib/human_guidance_roadmap.py`、`refresh-human-guidance-baseline.sh`、`journal_append.py`、`auto-run-batch-tail.sh` 等。

---

## 7. 遗留与 Gate

| 检查项 | 典型结果 | 说明 |
|--------|----------|------|
| `template_residuals` | FAIL | 业务仓不得含 `skills/`、`new-project.sh` |
| `git_bad_logs` | FAIL | pipeline.log 等大日志被 track |
| `legacy_runs_keep` | WARN | `_runs/keep/` 遗留 |
| `legacy_saved_keep` | WARN | `saved/keep/*.pt` 遗留 |
| `scenario_policy_gate` | FAIL | README 有 SCENARIO_POLICY 块时 |
| `d2_data_split_gate` | FAIL | D2 数据划分 |
| `rl_workspace_gate` | FAIL | profile=rl |
| `train_dynamics_gate` | WARN | 训练动态 gate |
| `train_dynamics_hook` | WARN | supervised train.py 无 record hook |
| `train_dynamics_artifact` | WARN | 末轮 exp 缺 train_dynamics.json |
| `rl_make_eval_env` | FAIL | RL infer mode 传递 |
| `global_skills` | WARN | 未安装全局 auto-nn-* 技能 |

---

## 8. 深度档追加（`--deep`）

| 检查项 | 典型结果 | 说明 |
|--------|----------|------|
| `verify_migration_complete` | FAIL | `verify-migration-complete.sh` 迁完级验收 |
| `smoke_check` | FAIL | `smoke-check.sh` 训链烟雾 |

---

## 9. 解读噪音

以下 FAIL/WARN **常与 G-HUMAN 无关**，勿混读：

- `layout FAIL` — `.claude/`、`docs/` 等非白名单根目录
- `governance_rev FAIL` — 模板 HEAD 超前，需 `governance-sync.sh`
- `ledger_row_sync WARN` — TSV/jsonl 行数不一致
