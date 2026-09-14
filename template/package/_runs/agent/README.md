# Agent 编排日志（`_runs/agent/`）

由 **`nn-auto-run.sh`** 写入：外层循环、Claude/Cursor 会话、反思轮。**不是** `train.py` 的训练 stdout（训练日志见 [`../logs/README.md`](../logs/README.md)）。

| 文件模式 | 含义 |
|----------|------|
| `YYYYMMDD_HHMMSS_batch.log` | 一次 `./nn-auto-run.sh N` 调用的批次心跳与 SUCCESS/ERROR |
| `YYYYMMDD_HHMMSS_agent-round-N.log` | 第 N 轮 Agent 会话元数据、prompt 摘要；无 stream-json 时亦 tee Agent stdout |
| `…_agent-round-N_stream.jsonl` | Claude `--output-format stream-json` 原始 NDJSON |
| `…_agent-round-N_claude-debug.txt` | Claude `--debug-file`（`NN_AGENT_CLAUDE_DEBUG` 默认开） |
| `YYYYMMDD_HHMMSS_reflect-N.log` | 第 N 轮后的 `reflect.py` 输出 |
| `manual_typescript.log` | 可选：`script -qfe _runs/agent/manual_typescript.log -- ./nn-auto-run.sh N` |

**勿与训练日志混淆：**

| 用途 | 路径 |
|------|------|
| 训练 stdout（单槽） | `_runs/logs/run.log` |
| 训练 stdout（多槽） | `_runs/logs/run_slot${NN_SLOT}.log` |
| 当次实验快照 | `_runs/exp/<tag>/` |

本目录下 `*.log` / `*.jsonl` / `*_claude-debug.txt` 默认不提交（见根 `.gitignore`）；仅保留本 `README.md`。

**v1 遗留目录**（`parallel_logs/`、`parallel_train_logs/` 等）已无主路径；编排日志统一在本目录。
