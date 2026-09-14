# nn-doctor WARN/FAIL 路由表

> **Agent 技能副本**：[`skills/post-migration/auto-nn-doctor/SKILL.md`](../../skills/post-migration/auto-nn-doctor/SKILL.md) §FAIL → 推荐  
> **本表为 docs 权威副本**；改路由时 **同步更新 SKILL**。  

doctor **只推荐**下一步，**不**自动 governance-sync、不 apply 清理、不改 contract/train。

---

## FAIL → 推荐

| 失败项 | 建议 |
|--------|------|
| `layout` / 缺脚本 | `bash <template>/scripts/governance-sync.sh --template-root … --project-root .`（业务仓跑 `/auto-nn-update`） |
| `governance_rev` / `auto_run_bundle` / `shell_syntax` | 同上 governance-sync |
| `git_repo` / `migration_summary` | 迁后 git init + `.auto-nn/migration-summary.md`（CHECKLIST §0） |
| `abcde_manual` | 补生成：`python3 scripts/init_o3_abcde.py …` / `abcde_migrate.py`；或 `/auto-nn-update` 后按 CHECKLIST；**勿**只建空 `manual/` 目录 |
| `baseline_start_intent` | 写 `saved/baseline_start_intent.json`（`write_baseline_start_intent.py`）或显式 `.auto-nn/baseline-intent-skipped` |
| `init_align`（坏文件） | 删坏卡后重对齐写入，或 `init_align.py write --amend`（禁静默手编） |
| `shared_context_contract` | `/auto-nn-modify`：从 train/workspace/contract 去掉袋内 contract 读写 |
| `fw_binding_*` | 补/修 `contract/framework_binding.yaml`；framework 仓对照 PROTOCOL §3.0.2b |
| `contract_layout` / `train_encapsulation` / `train_exp_dir` / `profile_facade` / `test_authority` | `/auto-nn-modify`（Modify-L/T）或对照 CHECKLIST；`train_encapsulation`：改 `train.py` 为只调 `ws.*`，子模块逻辑留在 `workspace/` |
| `contract_demo_metrics` | `/auto-nn-modify`（Modify-L2 · 台账·指标列） |
| `tsv_header` / `tsv_header_pending` | `/auto-nn-modify`（Modify-L + `regen_results_tsv.py`） |
| `readme` | 重写 README 首行与 test/evaluate 说明 |
| `template_residuals` | 删 `skills/`、`scripts/new-project.sh`；保留全局技能 |
| `git_bad_logs` | `git rm --cached` + `.gitignore` |
| `scenario_completeness` FAIL | `backfill-scenario-tsv.sh --apply` 或 `/auto-nn-modify`（Modify-Scenario-complete） |
| `reflect_index` FAIL | `repair-reflect-index.sh --apply` 或人工修 REFLECT_INDEX |
| `smoke_check` / `verify_migration_complete` | 看日志；改训练 → `/auto-nn-modify`（Modify-T）；再 `/auto-nn-manual-run` |
| `exploration_space_stamp` | 查最近一轮是否未开训（墙钟不足 1 秒允许空格）；正式训完须有 A–D 格子、禁止 `E-`。缺脚本或发版戳 → 业务仓 `/auto-nn-update` 后重跑 doctor。**不要**用论文脚本回填历史空格 |
| `e_feedback_schema` | 修 `_runs/analysis/e_feedback.jsonl` 坏行（须 object + `id`/`kind`/`resolution.status`）；勿手改决议字段以外结构 |

---

## WARN → 推荐（常见）

| 警告项 | 建议 |
|--------|------|
| `human_guidance_gate`（G-HUMAN 文件缺失） | `governance-sync.sh`；**勿**仅信 `governance_rev PASS` |
| `human_guidance_gate`（baseline drift） | 停 `./auto-nn-run.sh` → `git checkout <baseline.git_head> -- HUMAN_GUIDANCE.md`；**禁止** refresh `--apply` |
| `human_guidance_gate`（无 baseline） | 正常若未开 batch；开 batch 后 auto-run 会 `write-baseline` |
| `auto_run_bundle`（缺 g-human 脚本） | 同上 sync |
| `ledger_row_sync` | `python3 scripts/sync_ledger.py --apply`（≠ Modify-L1 加列） |
| `ledger_git` | PROTOCOL §6 步骤 10：commit 台账 |
| `scenario_completeness` WARN | 首次 KEEP 写 keepers；或 `write-keeper --scenario-id` |
| `project_docs` | **人工判断**是否保留 docs/ 目录 |
| `legacy_runs_keep` / `legacy_saved_keep` | `/auto-nn-clear`（用户 apply） |
| `journal_missing_with_tsv` | 补 journal 或跑 analyse 相关 migrate（见 `experiment-journal-and-analyse.md`） |
| `legacy_progress_file` | `migrate-drop-progress.sh` 或删除 `progress.txt` |
| `init_align`（缺文件） | 近版立项应有对齐卡；老仓可忽略或补写；**不**阻断训练 |
| `init_align`（profile 不一致） | 核对 `nn-config.yaml` profile 与 `.auto-nn/init-align.json`；有意改范式则 `write --amend` 或接受 WARN |
| `abcde_manual_hygiene` | 重生成手册或人工删退役旧名 / 对齐头注释与正文默认对象类型 |
| `exploration_space_stamp`（历史空格） | 发版戳前空格可忽略或自愿 `sync_exploration_ledger.py --backfill-all`；**不**作为 update 默认步 |

---

## 结构已健康、问指标

→ **`/auto-nn-analyse`**

---

## 再体检

→ **`/auto-nn-doctor`**
