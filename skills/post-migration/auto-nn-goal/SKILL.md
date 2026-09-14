---
name: auto-nn-goal
description: >-
  设置/调整/清除/查看实验目标值（goal）与实验模式（mode）：全局默认 + 按场景覆盖；
  goal.policy（主场景停批 focus / 多场景全达标停批 strict；v3→v4 映射 focus_only↔focus, all_in_scope↔strict）；
  6 档 mode（careful/optimize/innovate/aggressive/explore/auto）切换 loop 行为。
  set 走 scripts/manage_goal.py；show --all 全矩阵；mode 走 manage_goal.py mode（set_experiment_mode 写 exploration_mode 单旋钮；runtime 行为由 resolve_exploration 读时派生）。
  clear 删 goal.target 或 per_scenario override。auto-nn-run loop 达标即停（explore 除外）。
  NL: 目标值|实验模式|goal|target|升级|迁移|v3→v4|改成新格式|多 metric goal|多 metric 停批. NOT: 改路线图→human-guidance.
---

# auto-nn-goal — 实验目标值（goal）

**单一职责：** 管理 `nn-config.yaml` 的 `goal` 段（v4 schema：`goal.target` 全局默认 + `goal.per_scenario` 按场景覆盖 + `goal.policy` 停批范围）与 `agent.goal_spec`（多 metric × 多 scenario 复合门槛；`parse_goal_spec(agent)` 读路径，存在时优先于单值 v4 字段）及实验模式（`exploration_mode` 6 档单旋钮 careful/optimize/innovate/aggressive/explore/auto；runtime 行为〔skip_goal_stop / innovate_prompt_boost / tier_start / keep·reflect·external 等〕由 `resolve_exploration` 读时从 `default_for_mode` 派生，不写死 yaml）。explore 有效时跳过 goal 硬停。

权威：`PROTOCOL.md` §7.2.1；判定：`scripts/check_goal.py`；改配置：`scripts/manage_goal.py`。

## Code Contract（pilot，2026-07-15）

> `scripts/check_skill_contract.sh` 自动对账本段与 `template/package/*` 实际符号。
> 失败 → release-check 第 6 步门禁拦截。
> **强检字段**（对账失败即拦截）：`calls_scripts` / `reads_cfg_keys` / `env_vars_consumed`；其余（`pluggable_symbols` / `referenced_gates` 等）为 informational，release-check 不强检。

```yaml
calls_scripts:
  - scripts/manage_goal.py                # set/clear/show/mode/upgrade 主入口
  - scripts/check_goal.py                 # 达标停批判定（show）
  - scripts/append-skill-activity.py      # 活动日志（agent.skill_activity_log）

reads_cfg_keys:
  - goal                                   # goal.target / per_scenario / policy
  - agent                                  # 父键（含 .skill_activity_log）
  - agent.goal_spec                        # 多 metric 复合门槛（parse_goal_spec(agent)；PROTOCOL §7.2.1a）
  - agent.skill_activity_log               # 活动日志开关
  - exploration_mode                       # 6 档 mode 单旋钮（set_experiment_mode / resolve_exploration）
```

## 何时使用

- 用户要 **定目标**：「目标定 0.95」「主指标要到 0.9」
- 用户要 **改目标**：「把目标调到 0.97」
- 用户要 **问达标**：「达标没」「还差多少」「跑到哪了」
- 用户要 **取消目标**：「不要 goal 了」「跑满 N 轮」
- 用户要 **切实验模式**：「进入探索期」「改回 optimize」「innovate 模式」
- 用户要 **问当前模式**：「现在什么模式」「explore 生效没」
- **不要**用于：改主指标本身 / direction（→ `/auto-nn-modify`，contract 侧）；看完整趋势（→ `/auto-nn-analyse`）

## 高频代号（人话见 glossary）

| 内部码 | 对用户怎么说 |
|--------|--------------|
| `goal.target` | 全局默认目标 / 主指标要到多少（未单独写的场景共享） |
| `goal.per_scenario` | 按场景覆盖目标（如 `{"128b": 0.75}`）；键=scenario_id，null = 该场景豁免 |
| `goal.policy` | 停批范围：`focus`（只盯主场景停批） / `strict`（active 里有 goal 的全达标才停） |
| `agent.goal_spec` | 多 metric × 多 scenario 复合门槛（predicate 列表；`parse_goal_spec(agent)`；详见 PROTOCOL §7.2.1a） |
| `goal.metric` | 用哪个指标当目标（默认 = focus 主指标） |
| `goal.op` | 比较方向（`>=` / `<=`；默认按 metric_direction） |
| `check_goal.py` exit 0/1/2 | 达标 / 未达标 / 没设目标（explore 时 exit 2 + `GOAL_SKIPPED_EXPLORE`） |
| `GOAL_MET_ALL` | 多场景 strict 全达标 |
| `exploration_mode` | 6 档实验模式单旋钮（careful / optimize / innovate / aggressive / explore / auto） |
| `resolve_exploration()` | 读时解析：exploration_mode → bundle（keep/reflect/external/...）+ runtime 旗标（skip_goal_stop / innovate_prompt_boost / tier_start）。auto 时 resolved_mode = `auto.effective_mode` |
| `skip_goal_stop` | resolved_mode==explore 时 loop 不 goal 硬停（check_goal 读 resolve_exploration） |
| `scenario_default` | focus 场景（达标判定用这个场景的最新行） |

## sub-action

### `set <value>` 或 `set <scenario_id> <value>`

```bash
python3 scripts/manage_goal.py set 0.95              # 写 goal.target: 0.95（全局默认）
python3 scripts/manage_goal.py set 128b 0.75         # 写 goal.per_scenario.128b: 0.75（覆盖单场景）
python3 scripts/manage_goal.py stop-mode all_in_scope  # 写 goal.policy: strict（多场景全达标才停；v3→v4 映射）
```

### `clear` / `clear <scenario_id>`

```bash
python3 scripts/manage_goal.py clear                 # 删 goal.target
python3 scripts/manage_goal.py clear --overrides   # 删 goal.target + 整个 goal.per_scenario
python3 scripts/manage_goal.py clear 128b          # 删 goal.per_scenario.128b，回退全局 goal.target
```

### `show` / `show --all`

```bash
python3 scripts/check_goal.py .           # 停批判定（focus 或 strict）
python3 scripts/manage_goal.py show --all # 全场景矩阵 + policy
```

### `mode <6 选 1>`

**6 档定义**（unified-mode v1.5.6 起；详见 PROTOCOL §5.1）：

| `mode` | 类型 | 人话 | 起手档 | 实验目标 | goal 硬停 | 撞墙处理 |
|---|---|---|---|---|---|---|
| `careful` | 显式 | 啥都不动，照手册做 | A 标量 | optimize | ✅ | reflect 建议 |
| `optimize` ⭐ | 显式 | 参考下同行，标准干活 | A 标量 | optimize | ✅ | reflect 建议 |
| `innovate` | 显式 | 撞墙，翻同行代码 | B 结构 | innovate | ✅ | reflect 建议 |
| `aggressive` | 显式 | 论文+文档+实现+生态全查 | D 数据 | innovate | ✅ | reflect 建议 |
| `explore` | 显式 | 啥都试，不被指标卡 | B 结构 | explore | ❌ | reflect 建议 |
| **`auto`** | **auto** | **放手** | 跟随档 | 跟随档 | 跟随档 | **系统写 yaml 升档** |

**auto 档额外说明**（详见 PROTOCOL §7.2.1b）：
- 起步档 `auto.start_mode=optimize`，连续 `auto.promote_threshold=5` 轮撞墙触发升档
- 升档链：`optimize → innovate → aggressive`（不含 explore）
- `aggressive` 撞墙 → 不退
- yaml 写 `auto.effective_mode` 实际值（如 innovate），`exploration_mode` 保持 `auto`
- 撞墙处理双路径：5 显式档 → reflect 写建议到 `references/auto/`（**不动 yaml**）；auto 档 → 系统写 yaml 升档

`mode <M>` 走 `set_experiment_mode`（6 档统一入口；`manage_goal.py mode <M>` 真路径）：**仅写** `cfg["exploration_mode"]=M` 单旋钮（keep/reflect/external/early_stop/goal/tier_start 等由 `resolve_exploration` 读时从 `default_for_mode(M)` 派生，不钉死 yaml）。**不**自动清 `goal.target` / `metric_floor`。`mode auto` 走 `initialize_auto`（写 `exploration_mode="auto"` + auto 段 + 起步 optimize；升档链由 `finalize_round` 撞墙信号驱动；详见 PROTOCOL §7.2.1b）。

> 注：旧 `apply_experiment_mode`（3 档遗留）、`effective_experiment_mode`、`_resolve_mode` 已退役删除；运行时一律走 `resolve_exploration`。

```bash
MODE=optimize   # careful | optimize | innovate | aggressive | explore | auto
python3 scripts/manage_goal.py mode "$MODE"
# 输出：[mode] set exploration_mode=<M>
case "$MODE" in
  explore) echo "提示：explore 期 loop 不 goal 硬停；请确认 HUMAN 路线图" >&2 ;;
  auto)    echo "提示：auto 档撞墙自动升档；详见 PROTOCOL §7.2.1b" >&2 ;;
esac
```

（`MODE=` 由 Agent 按用户意图替换。）

### `mode show`

读 `resolve_exploration()`（exploration_mode + resolved_mode + skip_goal_stop + tier_start）。

```bash
python3 scripts/manage_goal.py mode show
# 输出：exploration_mode + resolved_mode + skip_goal_stop + tier_start
```

### `upgrade`

v4 起为 no-op：`load_nn_config` 读配置时已自动 v3 → v4 migrate，无需手动跑。

```bash
python3 scripts/manage_goal.py upgrade   # no-op；触发一次 load 让用户看到当前生效配置
```

## 边界

- **只管 `goal` 段与 `exploration_mode`**。多场景 override / policy 走 `manage_goal.py`。**不**改 `metric_key`（→ `/auto-nn-modify`）。
- **`mode` 不自动删 `goal.target`**；`clear` goal **不**改 `experiment_mode`。用户显式操作。
- explore 期仍建议不设 `goal.target`（doctor WARN）；底线护栏走 `agent.explore.metric_floor`（init G2，非本技能 set）。
- **不**改 `scenario_default`（focus 场景归属，走 `/auto-nn-modify` 或立项）。
- `goal.op` 默认从 `metric_direction` 推导（`maximize` → `>=`，`minimize` → `<=`）；如需反向（如 maximize 下设「不超过 0.95」）须直改 `nn-config.yaml` 的 `goal.op` 字段（manage_goal.py 无此 CLI 参数）。
- **不**代用户 `git commit`；写完 `nn-config.yaml` 提示用户 commit。
- Agent **不** Write/Edit `nn-config.yaml` 直改文本 —— 一律走上面 yaml-safe 脚本（Config-Only 精神）。
- **v3 → v4 兼容**：旧 yaml 里 `agent.goal_value` / `agent.scenario_goals` / `agent.goal_stop_mode` 字段会被 `migrate_goal_schema.py` 一次性迁移到 `goal.target` / `goal.per_scenario` / `goal.policy`；**`agent.goal_spec` 保留在 `agent` 段**（`parse_goal_spec(agent)` 读路径，**不**迁到 `goal.spec`）。单值 goal 走 v4 `goal.*`；复合门槛直写 `agent.goal_spec`。

## 对用户怎么说（人话）

| 用户问 | 答 |
|--------|----|
| 「目标定 0.95」 | 「好，目标设成主指标 0.95（maximize，越大越好）。loop 跑到 ≥0.95 就停。」（跑 `set 0.95`） |
| 「当前 0.93，达标没」 | 「还没。现在 0.93，目标 0.95，**还差 0.02**。」（跑 `show`；按 stdout 的人话转述，**不**背 exit code） |
| 「达标了？」 | 「达标了。主指标到 0.951，loop 会在这轮停。」 |
| 「目标调到 0.97」 | 「好，目标改成 0.97。」（跑 `set 0.97`） |
| 「不要 goal 了」 | 「好，删了目标。loop 改回跑满 N 轮。」（跑 `clear`） |
| 「进入探索期」 | 「好，实验模式切 explore。loop 不 goal 硬停，请确认路线图。」（跑 `mode explore`） |
| 「现在什么模式」 | 按 `mode show` 输出用人话：6 档之一 + 是否跳过 goal 硬停 + auto 档追加 effective_mode |

### `keep.primary_delta_rel`（相对值防误读）

**口径**：`primary_delta_rel` 是**相对值**（`best × (1 + delta)`），不是「best + delta」百分点。

| 起始 (best) | delta=0.005 | delta=0.01 |
|---|---|---|
| 0.5 (50%) | ≥ 0.5025 | ≥ 0.505 |
| 0.6 (60%) | ≥ 0.603 | ≥ 0.606 |
| 0.9 (90%) | ≥ 0.9045 | ≥ 0.909 |
| 0.95 (95%) | ≥ 0.95475 | ≥ 0.9595 |

**重要**：60% + 0.01 = 60.6%（**不是 61%**）。老 `primary_delta` 字段作 derived read-only（向后兼容）；新配置统一用 `keep.primary_delta_rel`。详见 PROTOCOL §7.2.1。

- **不**暴露 exit code / yaml key / 脚本名；按 stdout 数值用人话转述。
- 数值用与用户一致的精度（`0.93` 不说 `0.930000`）。

**坏**：「check_goal exit 1；exploration_mode=explore；skip_goal_stop=true」  
**好**：「还没达标：现在 0.93，目标 0.95，差 0.02。当前是探索模式，loop 不会因目标自动停。」

## 下一步

- `set` 后 → **`/auto-nn-auto-run`**（达标即停）或 **`/auto-nn-manual-run`**（手跑单轮验证）
- `show` 想看完整趋势 / 撞墙 / 升成熟度档 → **`/auto-nn-analyse`**
- `clear` 后 → **`/auto-nn-auto-run`**（跑满 N）
- 完整串联图见 [`../README.md`](../README.md)

## 活动 log

`set` / `clear` / `mode` 写盘成功后 **须** append：`--skill auto-nn-goal --phase end --summary "…" --lock "goal.target=…"` 或 `experiment_mode=…`。开关 `agent.skill_activity_log`（默认 true）。
