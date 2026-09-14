# AUTO-NN 包文档维护检查清单

> **定位**：PROTOCOL / CLAUDE（及包内 intent-map）维护视角 living doc，与白皮书 / 流程图 /
> 探索空间 / 技能维护检查清单并列。讲清「改了哪类 `template/package` 代码 → 去翻哪几节文档
> → 靠什么机械校验」——只做索引 + 门禁，不抄 PROTOCOL/CLAUDE 正文。
>
> **边界**：本清单只管包文档（`PROTOCOL.md` / `CLAUDE.md` / `docs/nn-routing/intent-map.md`）。
> 技能 `SKILL.md` Code Contract 仍归 `AUTO-NN-技能维护检查清单.md`。
>
> **一句话**：改代码后先翻本表，再跑
> `bash template/package/scripts/check_package_docs_contract.sh`。

---

## 三个机制

| 机制 | 怎么做 |
|------|--------|
| ① 指针型，不抄内容 | 只写查什么 + 真源路径 |
| ② 按触发组织 | 触发 E=改运行时代码；触发 F=发版前 |
| ③ 🔧 机械兜底 | `check_package_docs_contract.sh`（经 release-check Step 7） |

---

## 触发 E — 改了 `template/package` 运行时代码

| # | 你改了… | 必查 | 机械校验 |
|---|---------|------|----------|
| E1 | `scripts/lib/experiment_mode.py` / presets / auto-run mode 注入 | PROTOCOL §5.1 / §7.2.1；CLAUDE `exploration_mode` | 🔧 docs contract |
| E2 | `goal_spec` / `check_goal` / `manage_goal` | PROTOCOL §7.2.1 / §7.2.1a；intent-map goal 句 | 🔧 docs contract |
| E3 | KEEP / `should_keep` / `primary_delta*` | PROTOCOL §2.1；CLAUDE keep 段 | 🔧 `primary_delta_rel` required |
| E4 | `experiment.py` 门禁 / 边界 / finalize | PROTOCOL §0.1 / §3 / §6；CLAUDE 两态与硬规则；**finalize 打格**（`exploration_space` A–D 必打） | — 人查 |
| E4b | `scripts/lib/info_perm.py` / `_guard_info_perm` 只评材料拦法 | PROTOCOL 守门表 G-信息权限 | 🔧 `tests/test_info_perm.py` + `tests/test_info_perm_runtime.py` |
| E5 | contract 场景号 / metric 题面常量 | PROTOCOL 场景号归属段 | — 人查 |
| E6 | `train.py` dispatcher（评估侧 `metrics_shape` / 训练侧 `training_mech`） | PROTOCOL §3.0.2 / §3.0.3 | — 人查 |
| E6b | `scripts/lib/framework_binding.py` / doctor·smoke 总表消费 | PROTOCOL §3.0.2b；CLAUDE contract 行 | — 人查 |
| E7 | `build-run-context` / Run Context 段 | PROTOCOL §7.4；CLAUDE Run Context 列表 | — 人查 |
| E7c | `nn_baseline.py` / `lib/baseline_stamp.py` / `lib/source_calibration.py` 立尺贴签、满 10 轮注入、文献尺原仓校准门禁 | PROTOCOL §6 写入权 + 原仓校准段；intent-map plain/reference | 🔧 `tests/test_source_calibration.py` + `tests/test_baseline_stamp.py`；— 人查 PROTOCOL 一句 |
| E8 | `auto-nn-setup.py` 的 `gpus` 写逻辑 / 顶层字段可写语义 | CLAUDE 全局配置段（`gpus` 例外三处：字段表 / 冻结铁律 / 两态） | — 人查 |
| E9 | `new-project` / doctor / verify 的 **abcde-manual 存在性**闸 | PROTOCOL 完成门禁 / references 段；CHECKLIST §0 | 🔧 doctor 夹具 + docs contract |
| E10 | `time_budget` 取值 / 守卫 / smoke 墙钟 / **执行粒度**（epoch 边界 + `optimizer.step` 入口、满预算停、超时入账） | PROTOCOL §2.3 时限冻结注记 + §7.3 墙钟两条；CHECKLIST §5 通用 smoke 判据 | 🔧 `tests/test_time_budget_guard.py` + `tests/test_time_guard_step_boundary.py` + `check_time_budget_audit.py` |

---

## 触发 F — 发版前

| # | 检查要点 | 机械校验 |
|---|----------|----------|
| F1 | docs contract FAIL=0 | 🔧 `check_package_docs_contract.sh`（release-check Step 7） |
| F2 | 本版 diff 命中的触发 E 行已人工回看 | — 人查 |

---

## 说人话

改模板里的训练/目标/模式代码时，协议书和操作入口不会自动跟着改。这张表告诉你该翻哪几节；发版前脚本会拦「还在教人走已删 API」这类硬漂。改了代码却没动文档只会警告，不会替你改文档。

---

## 缩略语

- **PROTOCOL** = `template/package/PROTOCOL.md` 规则真源
- **CLAUDE**（包内）= `template/package/CLAUDE.md` 操作入口
- **banned_primary_path** = 禁止当作现行主路径出现的符号写法
- **required_mentions** = PROTOCOL 中必须出现的权威字段名
- **living doc** = 随体系演进维护的对照基准（本稿为包文档维护视角）
