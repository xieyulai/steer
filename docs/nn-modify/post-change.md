# Modify 改后收尾：权威 Bash 命令链

迁后业务能力变更（`/auto-nn-modify`，Modify-L2/L3 / Modify-T / Modify-Scenario）完成后，按需执行下列 **整块**（不要半截复制）。括号内为语义说明。

> **推荐入口（P1）**：`bash scripts/modify-post-change.sh --track L|T|Scenario-complete|Scenario-expand|ledger-sync`  
> 只改 `ledger.watchlist`（加参数列）→ `--track ledger-sync`（台账同步，**不是**改能力）。

---

## §L 轨（Modify-L2/L3 — contract / metric / KEEP 触及）

契约或能力定义变更须在收尾前注入重跑标记，并走完 README／TSV／场景门禁与体检。

```bash
export NN_RELAUNCH=1
bash scripts/readme-modify-gate.sh .
python3 scripts/readme_consistency_gate.py . --strict
python3 scripts/regen_results_tsv.py --repo-root .
rm -f _runs/.tsv-header-pending
python3 scripts/d2_data_split_gate.py .
python3 scripts/scenario_policy_gate.py .
bash scripts/nn-doctor.sh
bash scripts/smoke-check.sh
```

---

## Modify-Scenario-complete

补齐 `scenario_id` 等与分池／台账一致性的收尾；backfill **须 dry-run → 人审 → apply**。

```bash
bash scripts/readme-modify-gate.sh .
python3 scripts/readme_consistency_gate.py . --strict
bash scripts/backfill-scenario-tsv.sh --dry-run .
# 人审通过后：
bash scripts/backfill-scenario-tsv.sh --apply .
export NN_RELAUNCH=1   # 若改了 contract
python3 scripts/regen_results_tsv.py --repo-root .
rm -f _runs/.tsv-header-pending
python3 scripts/d2_data_split_gate.py .
python3 scripts/scenario_policy_gate.py .
bash scripts/nn-doctor.sh
poetry run python -m contract sanity
bash scripts/smoke-check.sh
```

---

## Modify-Scenario-expand

扩场景／策略收口：先 readme 与 scenario 门禁、体检；仅在 **S_data / metric 变化触达 contract** 时再 regen、d2、`NN_RELAUNCH`。

```bash
bash scripts/readme-modify-gate.sh .
python3 scripts/readme_consistency_gate.py . --strict
python3 scripts/scenario_policy_gate.py .
bash scripts/nn-doctor.sh
# 若 S_data/metric 变（触达 contract）：
export NN_RELAUNCH=1
python3 scripts/regen_results_tsv.py --repo-root .
rm -f _runs/.tsv-header-pending
python3 scripts/d2_data_split_gate.py .
bash scripts/smoke-check.sh
```

---

## Modify-T

Train/workspace 侧的纯改码路径：以 contract sanity + smoke 为硬收尾；readme 门禁通常可跳过（见脚注）。

```bash
poetry run python -m contract sanity
bash scripts/smoke-check.sh
# 可选：bash scripts/nn-doctor.sh
```

---

## 脚注

- **§跳过 readme gate**：Modify-L1 与 **纯 Modify-T** 可走「跳过 readme 门禁」语义；与各轨组合方式见 [readme-sync-after-modify.md § 表格](../archive/readme-sync-after-modify.md)。
- **§NN_MODIFY_TRACK**：对 `readme-modify-gate.sh` 声明本次修改轨，便于门禁选择提示，例如：`export NN_MODIFY_TRACK=L`、`export NN_MODIFY_TRACK=Scenario`（取值以脚本与路线图约定为准）。
