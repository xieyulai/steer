# docs/ — 文档地图 · Document map

> 本目录只放**必要**文档：被技能 / 脚本点名读取的，或人理解体系必须的那几份。设计过程稿不在这里。
> Only documents that a skill, a script or a first-time reader actually needs. Design drafts are not shipped.

## 读者向 · For readers

| 文档 | 内容 | Content |
|---|---|---|
| [`AUTO-NN-whitepaper.md`](AUTO-NN-whitepaper.md) | 体系总览：三阶段、17 技能定位、探索空间与 6 mode、机制基线、版本演进 | Whitepaper: three phases, the 17 skills, exploration space & modes, mechanism baselines |
| [`skill-glossary.md`](skill-glossary.md) | 术语表：每个内部代号的人话说法（技能对人输出的真源） | Glossary: plain-language names for every internal term |
| [`init-conversation-guide.md`](init-conversation-guide.md) | `/auto-nn-init` 对话进度、好/坏示例（逐题对照表在 README 附录） | How onboarding talks; per-question table is the README appendix |
| [`../template/package/PROTOCOL.md`](../template/package/PROTOCOL.md) | 业务仓每轮都遵守的运行协议 | The protocol every business project runs under |

## 技能执行时读取 · Read by skills at run time

| 目录 / 文件 | 谁读它 |
|---|---|
| [`nn-doctor/`](nn-doctor/) | `/auto-nn-doctor` — 检查目录（check-catalog）、失败路由（fail-routing） |
| [`nn-modify/`](nn-modify/) | `/auto-nn-modify` · `/auto-nn-manual-run` — 轨道目录、改后整轨命令链（post-change）、doctor 路由 |
| [`nn-literature/atomic-tools.md`](nn-literature/atomic-tools.md) | `/auto-nn-reflect` — `scripts/external_tool.py` 文献原子工具手册 |
| [`archive/metric-and-keep-system.md`](archive/metric-and-keep-system.md) | `/auto-nn-modify`、`/auto-nn-init` — 台账 TSV 四区与 KEEP 口径 |
| [`archive/readme-sync-after-modify.md`](archive/readme-sync-after-modify.md) | `scripts/readme-modify-gate.sh` — 改能力后 README 同步计划 |
| [`maintainer/mirror-mechanism.md`](maintainer/mirror-mechanism.md) | migrate workflow（`scenarios/migrate.yaml`）— contract / workspace 分工与单一真源 |
| [`examples/adapter-mammoth/`](examples/adapter-mammoth/) | `/auto-nn-init` 框架接入 overlay、`PROTOCOL.md` §3.0.2b、`tests/` — 外部框架（Mammoth）接入的参考实例 |

## 维护者 · Maintainers

| 文档 | 内容 |
|---|---|
| [`AUTO-NN-package-docs-checklist.md`](AUTO-NN-package-docs-checklist.md) | 改了哪类 `template/package` 代码 → 翻 PROTOCOL / CLAUDE 哪几节 → `check_package_docs_contract.sh`（lint 的 WARN 会让你翻这张表） |
| [`../CLAUDE.md`](../CLAUDE.md) · [`../README-maintainer.md`](../README-maintainer.md) · [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | 维护工作流、发版门禁、贡献流程 |

## 设计存档 · Design archive

设计过程稿（brainstorm → spec → plan，约 300 篇）不随本仓发布，代码与文档里也不再引注它们；现行接口以白皮书、`PROTOCOL.md`、各 `SKILL.md` 和代码为准。需要某个决策的来龙去脉时在 Issue 里提。

The maintainers' design archive (≈300 brainstorm → spec → plan drafts) is not shipped and is no longer cited from code or docs; the whitepaper, `PROTOCOL.md`, the `SKILL.md` files and the code are the current interface. Ask in an Issue if you need the rationale behind a decision.
