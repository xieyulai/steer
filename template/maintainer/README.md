# template/maintainer/ — 仅模板维护仓使用

**永不**经 `new-project.sh` 复制到业务项目。

| 路径 | 说明 |
|------|------|
| `skeletons/{rl,physical}/` | `--skeleton` 时拷贝四文件到 `contract/` |
| `scripts/generate-profile-locks.sh` | 读 `../package/profiles.yaml`，写 `profiles/*/poetry.lock` |
| `scripts/init.sh` | 可选环境检查（历史） |
| `profiles/*/poetry.lock` | 各 profile 预生成 lock |

```bash
# 在维护仓根执行
bash template/maintainer/scripts/generate-profile-locks.sh
```
