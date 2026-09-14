# auto-nn-doctor（迁后结构体检）

> **读者**：迁后实验者、维护者、使用 `/auto-nn-doctor` 的 Agent  
> **技能入口**：[`skills/post-migration/auto-nn-doctor/SKILL.md`](../../skills/post-migration/auto-nn-doctor/SKILL.md)  
> **实现脚本**：业务仓 `scripts/nn-doctor.sh`（模板 `template/package/scripts/nn-doctor.sh`）

---

## 1. 一句话

**`nn-doctor` 回答「这个仓还能不能正常跑？」** — 布局、governance 对齐、contract/门面、台账、auto-run 配套、场景完整性等 **机械健康**。

**不回答**「指标好不好、该不该改方向」→ 用 `/auto-nn-analyse` 与 MA 块。

---

## 2. 命令与档位

| 档位 | 命令 | 用途 |
|------|------|------|
| **轻量（默认）** | `bash scripts/nn-doctor.sh` | 全量检查项；不跑 smoke |
| **静默轻量** | `bash scripts/nn-doctor.sh --quiet` | 仅 WARN/FAIL；`/auto-nn-analyse` 开场自动调用 |
| **深度** | `bash scripts/nn-doctor.sh --deep` | 轻量 + `verify-migration-complete.sh` + `smoke-check.sh` |

**输出格式：**

```text
[nn-doctor] <检查项>    PASS|WARN|FAIL|SKIP    <说明>
```

**退出码：** 任一 FAIL → `1`；仅 PASS/WARN/SKIP → `0`。

---

## 3. 与其它机制的分工

| 机制 | 分工 |
|------|------|
| **preflight G-*** | 每轮 `train.py` 启动时硬/软门（见 `guard-and-governance.md`） |
| **nn-doctor 轻量** | 迁后日常静态体检；**G-封装**（`train_encapsulation`）、**G-评估**（`test_authority`）与 preflight 同规则、**不训** |
| **verify-migration-complete** | 迁完 **一次性** 硬门禁（深度 doctor 可对齐，但不替代人显式迁完验收） |
| **governance-sync** | 推送脚本与 PROTOCOL；**不**自动跑 doctor（业务仓用 `/auto-nn-update`） |
| **nn-doctor** | 迁后 **日常** 结构体检；Agent 可代跑，**不**改代码、**不** apply 清理 |
| **analyse** | 台账策略、plateau、Tier；内置 `nn-doctor --quiet` 作静默前置 |

---

## 4. 文档地图（本目录）

| 文档 | 内容 |
|------|------|
| **[check-catalog.md](check-catalog.md)** | 全部检查项、分组、典型 PASS/WARN/FAIL |
| **[fail-routing.md](fail-routing.md)** | WARN/FAIL → 推荐技能或维护命令 |

---

## 5. Agent 工作流（摘要）

1. 确认在 **业务仓根**（`train.py`、`contract/`、`_runs/`）。
2. 默认轻量；用户说「深度 / 含 smoke / 迁完验收」→ `--deep`。
3. 代跑 doctor，按输出填 **《体检报告》**（模板见 SKILL）。
4. 每项 WARN/FAIL → 查 [fail-routing.md](fail-routing.md)；**不**自动 governance-sync、不 apply 清理。
5. 回复末尾至少推荐一个 `/auto-nn-*` 下一步。

---

## 6. 硬边界

- **禁止**改 `train.py` / `workspace/` / `contract/` / `experiment.py`（doctor 技能内）
- **禁止**手改 `_runs/results.tsv` / `jsonl`
- **禁止** `govern-runs.sh clear --apply`、`rm -rf`（→ `/auto-nn-clear`）
- **禁止**默认 `--deep`（含 smoke，耗资源）
- **`__pycache__` / `.pyc`**：不参与 layout；报告勿列为 FAIL

---

## 7. 相关索引（仓外）

| 链接 | 说明 |
|------|------|
| `guard-and-governance.md` §3 | 治理同步、verify、doctor 在治理栈中的位置 |
| [`AUTO-NN-whitepaper.md`](../AUTO-NN-whitepaper.md) | 三阶段定位与 doctor/analyse 关系 |
| `human-guidance-roadmap.md` | HUMAN 路线图与 G-HUMAN 运行时门禁 |
| `nn-run-skills/README.md` | manual-run / auto-run / human-guidance 与 G-HUMAN 对齐 |
| `template-sync-methodology.md` | sync 后建议 `nn-doctor --quiet` |
| `PROTOCOL.md` §结构体检 | 业务仓协议一句 |

---

## 8. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-05-24 | 独立文档体系：`docs/nn-doctor/`；G-HUMAN install + auto_run_bundle 对齐 |
