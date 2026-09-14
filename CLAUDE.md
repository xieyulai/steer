# CLAUDE.md — auto-nn 模板维护者入口

**Language / 对人说话：** Match the user's latest message. English in → English out. Chinese in → Chinese out. Do not mix. Slash names and `config.json` keys stay as written. Script tables (doctor / analyse) stay Chinese; prepend one sentence in the user's language. See `.cursor/rules/skills-plain-language.mdc`.

## 这是什么
- 模板维护仓，不是业务仓。`template/package/` 是唯一真源；governance-sync
  cp 到业务仓后，模板仓自身不感知沙箱设施——沙箱另行独立装。
- 使用者入口见 `README.md`（English，默认）/ `README-zh.md`（中文）；维护者细则见
  `README-maintainer.md`。
- 业务仓侧规则（train.py / workspace / keep_threshold / ExperimentBase）见
  `template/package/CLAUDE.md`——本文件**不**抄录。

## 分层
| 层 | 路径 | 谁会读 |
|----|------|--------|
| 模板真源 | `template/package/` | 业务仓 governance-sync |
| 维护者文档 | `docs/AUTO-NN-whitepaper.md`、`docs/AUTO-NN-package-docs-checklist.md`、`docs/maintainer/` | 模板维护者 |
| 技能配套文档 | `docs/nn-doctor/`、`docs/nn-modify/`、`docs/nn-literature/`、`docs/archive/`（被技能 / 脚本点名读取） | 技能执行时的 Agent |

注：根级 CLAUDE.md / README.md / nn-config.yaml 等是**有意保留**的物理副本，
不与 `template/package/*` 形成镜像。

## 沙箱在哪

沙箱测试设施是**可选**的独立仓 **`sandbox-auto-nn`**（模板仓不持有，也不依赖）。
要装 `/sandbox-init` / `/sandbox-run` / `/sandbox-register`：

```bash
git clone <sandbox-auto-nn-url> ~/sandbox-auto-nn
cd ~/sandbox-auto-nn && bash install.sh
```

没有沙箱时，用 `template/package/scripts/new-project.sh` 在临时目录立一个业务仓副本、
跑 smoke 验证即可（见 `README-maintainer.md` §1）。

## 维护工作流
- 改 `template/package/*` → 在业务仓副本里验证（沙箱设施或临时 new-project）→ 通过 → 用
  version gate（`template/package/scripts/check_template_version.py`）stamp + bump → push →
  业务仓 `/auto-nn-update`
- **发版** → 跑 `/bump-version`（详见 `skills/bump-version/SKILL.md`）：
  - `/bump-version` 自动从 git log 推断 bump type（推荐先 `--dry-run` 看 preview）
  - `/bump-version patch|minor|major` 强制类型（major 需 `--accept-major-bump`）
  - `/bump-version 1.2.0` 显式指定目标版本
  - `/bump-version --retro-tag v1.0.0 --accept-major-bump` 补历史 tag（如 `v1.0.0` 漏打）
  - 默认**不** push；`--push` 显式 opt-in
- 镜像 / 单一真源机制见 `docs/maintainer/mirror-mechanism.md`；发版门禁细则见 `template/package/scripts/release-check.sh` 头注与 `CONTRIBUTING.md` §4。

## 白皮书同步（每次更新必检）
- `docs/AUTO-NN-whitepaper.md` = 体系总览 living doc（三阶段 / 17 技能定位 / 机制基线），是其余 docs / README 的对照基准。
- **每次模板或机制更新后必检**：改了 `template/package/*` 技能职责、分层、版本演进、init/沙箱流程任一项 → 回看白皮书对应章节是否仍准确，该改即改。
- 改名/移动白皮书后须全局修引用（README / skills/README.md / docs/README.md 均链向它，死链不可留）。

## 包文档同步（每次更新必检）
- `docs/AUTO-NN-package-docs-checklist.md` = PROTOCOL/CLAUDE 维护视角 living doc，
  讲「改了哪类 `template/package` 代码 → 翻 PROTOCOL/CLAUDE 哪几节 → 机械 lint」。
- **每次模板运行时代码更新后必检**：改了 `template/package/**/*.{py,sh}`（非纯格式）→
  翻清单触发 E → 必要时改 `PROTOCOL.md` / `CLAUDE.md` / `docs/nn-routing/intent-map.md` →
  跑 `bash template/package/scripts/check_package_docs_contract.sh`（FAIL 必须处理；
  改代码未动文档的 WARN 须对照触发表确认是否误报）。
- 发版经 `release-check` Step 7 强制 FAIL=0。
- 改名/移动本清单后须全局修引用。

## Agent 协作约定

- 公开问题走 Gitee Issues；Agent 的本地草稿 / 工单放 `.scratch/<feature-slug>/`（已 gitignore，不入库）。
- 领域术语真源：`template/package/PROTOCOL.md`、`template/package/CLAUDE.md`、`docs/skill-glossary.md`。
- 设计过程稿（brainstorm → spec → plan）不随本仓发布，代码 / 文档里也不引注它们；现行接口以
  白皮书、`PROTOCOL.md`、各 `SKILL.md` 和代码为准。

## 不要
- 不要往根目录放"业务仓镜像"（`scripts/`、`experiment.py` 等）。
- 不要在主仓硬塞"experiment.py 不可改"等业务仓侧铁律。
- 根级 `nn-config.yaml` **仅可修改 `ledger:` 段**；其余字段随 `template/package/CLAUDE.md` 同级冻结。

## 缩略语
- HARD-GATE = 沙箱 init 流程中的强制门禁检查（详见沙箱仓 `CLAUDE.md`）
- slash 技能 = 以 `/` 开头的斜杠命令技能（如 `/sandbox-init`）
- 沙箱仓 = 独立仓库 `sandbox-auto-nn`，持三个 sandbox-* skill
- governance-sync = 模板仓 → 业务仓的 cp 治理同步脚本