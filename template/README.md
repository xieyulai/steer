# template/ — 业务安装包与维护者工具

| 子目录 | 用途 | 是否 rsync 到业务仓 |
|--------|------|---------------------|
| **`package/`** | 业务运行时完整包（`new-project.sh` 唯一 rsync 源） | 是 → `<project_root>/` |
| **`maintainer/`** | 立项骨架、`generate-profile-locks`、profile lock 文件 | 否 |

- 业务 Agent 入口：`package/CLAUDE.md`（安装后为项目根 `CLAUDE.md`）
- 维护仓 Agent 入口：仓库根 `CLAUDE.md`
- 立项 / 迁入流程：`../skills/maintainer/auto-nn-init/SKILL.md`

```bash
# 维护仓根
bash template/package/scripts/new-project.sh ../my-project my-project --profile supervised
cd template/package && poetry install && poetry run python train.py
bash template/maintainer/scripts/generate-profile-locks.sh
```
