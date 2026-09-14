# auto-nn（维护者）

> 读者:模板维护者(改模板 / 治理仓库本身)。**使用者请看 [`README.md`](README.md)（English，默认）/ [`README-zh.md`](README-zh.md)（中文）**。

---

## 读者分工

| 读者 | 看哪 |
|---|---|
| 业务仓使用者 | [`README.md`](README.md) · [`README-zh.md`](README-zh.md) |
| 维护者 | 本文件 |

---

## §1 改完模板后严格按 4 步

```bash
# 1. 测试（根级 + 包内；需 pytest、pyyaml；含 torch 的用例在无 torch 环境下会跳过/报错）
python3 -m pytest tests -q                                  # needs pytest, pyyaml, numpy, torch, torchvision
python3 -m pytest template/package/scripts/tests -q          # run separately: same filenames in both trees
# 2. 提交
git add ... && git commit
# 3. 本机重装全局技能(安装 A)
./install.sh
# 4. 通知业务仓:运维者跑 /auto-nn-update(或 bash $NN_TEMPLATE_ROOT/template/package/scripts/governance-sync.sh)
```

> **为什么没有"维护者批量下发"?** 模板改完 push 即收尾;各业务仓日常 `git pull` 自己的 `$NN_TEMPLATE_ROOT` 克隆,然后由业务仓 Agent 跑 `/auto-nn-update` 触发 `template/package/scripts/governance-sync.sh`。模板仓 **不** 维护业务仓登记,也不批量推。业务仓不在 7 个以内的情况由业务仓自助对齐(自己跑 `governance-sync`)。

---

## §2 维护侧 1 技能

| 技能 | 一句 | 何时用 |
|---|---|---|
| [`/auto-nn-init`](skills/maintainer/auto-nn-init/SKILL.md) | 项目初始化：立项 / 迁入五阶段 0→4 | 使用者入口见 README Quick start（CIFAR 迁入闭环）；二十几问对照表在 [README-zh 附录](README-zh.md#init-qa) / [README appendix](README.md#init-qa) |

**业务仓日常技能**(`analyse` / `manual-run` / `auto-run` / `reflect` / `modify` / `clear` / `human-guidance` / `compress` / `doctor` / `check` / `update`)**不在本仓使用**;它们装在 `~/.cursor/skills/`,在业务仓根 `CLAUDE.md` 调。

---

## §3 目录速查

| 路径 | 用途 |
|---|---|
| [`template/package/`](template/package/) | rsync 唯一源 → 业务仓(`new-project.sh` 安装) |
| [`template/maintainer/`](template/maintainer/) | 立项骨架、profile lock(**不**进业务仓) |
| [`skills/post-migration/`](skills/post-migration/) | 日常技能真源(安装 A 链到全局) |
| [`skills/maintainer/`](skills/maintainer/) | 维护技能真源(目前仅 `auto-nn-init`) |
| [`template/package/scripts/`](template/package/scripts/) | `new-project.sh` / `governance-sync.sh` / `migration-compare.sh` 等(`install.sh` 在仓库根) |
| [`docs/`](docs/) | 必要文档：白皮书 / 术语表 / 技能执行时读取的配套文档（见 [`docs/README.md`](docs/README.md)）；设计存档不随仓发布 |
| [`docs/AUTO-NN-whitepaper.md`](docs/AUTO-NN-whitepaper.md) | **体系完整总结**（build / governance / experiment 三阶段；改技能职责时同步） |
| [`docs/init-conversation-guide.md`](docs/init-conversation-guide.md) | init 对话人读规范（进度、四段式、好/坏示例）；**逐题对照表在 README**；改 SKILL 交互时同步 |

---

## §4 禁止项

- 不复制 `skills/` 进业务仓(走 symlink)
- 不在 `~/.cursor/skills/` 放 `scripts/` / `reflect.py`
- 不依赖 `docs/` 做业务决策(模板仓自留)
- **不**在模板仓维护已迁业务仓登记 / 路径(业务仓自管 `NN_TEMPLATE_ROOT` + `.auto-nn/template-root`)
- `README.md`(本仓)只面向使用者;**维护者内容在本文件**,不要回头加到主 README
