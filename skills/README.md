# skills/ — NN Agent 技能真源

与 **`template/package/`**（PROTOCOL、auto-run、经 governance-sync 装进业务仓）分离。技能 **不** 复制进业务仓；与 **Superpowers** 一样 **全局安装**。

**读者向完整说明**：[`docs/AUTO-NN-whitepaper.md`](../docs/AUTO-NN-whitepaper.md)

## 安装

```bash
# 在本仓根目录
./install.sh
```

安装到 `~/.cursor/skills/auto-nn-*/`（及 `~/.claude/skills/` 若存在）。

## 命名

统一前缀 **`auto-nn-`**。Cursor 对话中用斜杠：**`/auto-nn-manual-run`** 等（勿写 `@`）。

## 目录

| 目录 | 内容 |
|------|------|
| `post-migration/auto-nn-*` | 迁后日常技能 + `README.md` |
| `maintainer/auto-nn-init/` | 项目初始化（立项 + 迁入；SKILL + migration-compare 等） |

业务 Agent **cwd = 业务仓根**；技能读该目录下 `PROTOCOL.md`、`HUMAN_GUIDANCE.md` 等。维护脚本在 **`NN_TEMPLATE_ROOT`**（本仓库克隆）。

## 说人话规范

所有 `auto-nn-*` 技能（**含 init**）对用户输出**先说人话，代号只在括号补充**。术语真源：
[`docs/skill-glossary.md`](../docs/skill-glossary.md)（§迁后日常 + §项目初始化）；
全局规则：`.cursor/rules/skills-plain-language.mdc`；init 的 4 问自检规则在 [`skills/maintainer/auto-nn-init/SKILL.md`](maintainer/auto-nn-init/SKILL.md) §一轮一问 / 4 问自检（自包含，无独立 Cursor 规则）；迁后各技能含 `## 对用户怎么说` 摘录小节。
