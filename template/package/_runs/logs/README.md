# 训练与试跑 stdout 日志（`_runs/logs/`）

与台账目录 **`_runs/exp/`**、编排目录 **[`_runs/agent/`](../agent/README.md)** 并列：此处放 **所有** `train.py` 控制台重定向日志（单槽与多槽），**不是** Agent 会话日志，也**不是** `finalize_round` 写入的 `results.json` / `keep_suggestion.json`（单槽在 `exp/` 下；汇总在 `_runs/round_decision.json`）。

**勿在仓库根** 写 `run.log`、`run2.log` 等（根目录 `/run*.log` 仅作历史兼容忽略，见 `.gitignore`）。

| 场景 | 路径 |
|------|------|
| **单槽（默认）** | `_runs/logs/run.log` — `mkdir -p _runs/logs && poetry run python train.py > _runs/logs/run.log 2>&1` |
| **多槽并行** | `_runs/logs/run_slot${NN_SLOT}.log`（或带时间戳的短名） |
| **多份试跑对比** | `_runs/logs/<short_name>.log`（如 `transformer_iter2.log`） |

`scripts/wait-train.sh` 默认 `--log _runs/logs/run.log`（单槽）。

本目录下 `*.log` 默认不提交（见根 `.gitignore`）；仅保留本 `README.md`。
