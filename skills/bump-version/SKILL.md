---
name: bump-version
description: 模板仓版本 bump 一条龙：检测 git tag → 推断 bump type → dry-run preview → y/N 确认 → 写 VERSION/CHANGELOG.md → git commit → 跑 release-check 5 步门禁 → git tag。NL: 升级版本|bump|新版本|发版。NOT: 业务仓操作|auto-nn-* 域。
---

# bump-version — 模板仓发版

> 这是**维护者侧**工具，**不**分发到业务仓（`install.sh` glob `auto-nn-*` 不命中本目录）。

## 何时用

- 累积了一批 `fix:` / `feat:` / `BREAKING:` commit，需要发版
- 历史上某次 release commit 漏打了 tag（如 `v1.0.0`）
- 想看当前累积该 bump 什么版本（dry-run 模式）

## 一句话用法

```bash
/bump-version                              # 自动从 git log 推断 bump type（推荐）
/bump-version patch                        # 强制 patch（1.0.0 → 1.0.1）
/bump-version minor                        # 强制 minor（1.0.0 → 1.1.0）
/bump-version major --accept-major-bump   # 强制 major（1.0.0 → 2.0.0）
/bump-version 1.2.0                        # 显式指定目标版本
/bump-version --retro-tag v1.0.0 --accept-major-bump   # 补历史 tag
/bump-version --dry-run                    # 只预览，不改任何文件
/bump-version --no-tag                     # bump + commit 但不打 tag
```

## 流程

1. `git tag --list` 检测 `v<CURRENT_VER>` 是否存在（缺 → 提示 `--retro-tag`）
2. `git log v<CURRENT_VER>..HEAD` 取 commit 范围
3. 调 `template/package/scripts/check_template_version.classify` 推断 bump type
4. dry-run 渲染 preview 到 stderr（commits + CHANGELOG 草稿 + tag 名 + push 状态）
5. y/N 确认（默认 N，Ctrl-C 安全）
6. 写 `VERSION` + `CHANGELOG.md` → `git commit -m "release: <NEW_VER>"`
7. `bash scripts/release-check.sh`（5 步门禁）
8. `git tag v<NEW_VER>`
9. 默认不 push；`--push` 显式 opt-in

## 与 release-check 的关系

`scripts/release-check.sh` 5 步门禁**不被绕过**：

| 门禁 | 失败时 bump-version 行为 |
|------|--------------------------|
| git dirty | 不打 tag、不 push；提示先 commit |
| VERSION 非 semver | 不打 tag；exit 3 |
| 未 bump | 不打 tag；exit 3 |
| major 缺 CHANGELOG 段 | 不打 tag；提示补段 |
| 日期 > today | 不打 tag；提示 |

bump-version **依赖** release-check 作为最后一道闸。失败 → 不打 tag / 不 push（commit 已落，可用 `git reset --soft HEAD~1` 撤回）。

## 错误码

| 退出码 | 含义 |
|--------|------|
| 0 | 成功 |
| 1 | 缺 tag（提示先 `--retro-tag`） |
| 2 | major bump 未带 `--accept-major-bump` 或参数无效 |
| 3 | 不是 git 仓 / 无 `VERSION` / VERSION 非 semver |

## 自动化 vs 自动 push

`/bump-version` 是**谨慎默认**：
- 默认跑 dry-run 之外的全流程（写盘 + commit + tag），但**不** push
- `--push` 显式 opt-in 才 `git push --follow-tags`

理由：commit + tag 错了 `git tag -d` / `git reset --soft HEAD~1` 可撤回；push 错了需要 force-with-lease。

## CHANGELOG 自动分类

| commit 类型 | CHANGELOG 段 |
|-------------|--------------|
| `feat:` | `### Added` |
| `fix:` | `### Fixed` |
| `refactor:` | `### Changed` |
| `BREAKING:` (任意行) | `### Changed` (含 BREAKING 标记) |
| `docs:` / `test:` / `chore:` / `perf:` | **跳过**（噪音） |

格式遵循 [Keep-a-Changelog 1.1.0](https://keepachangelog.com/zh-CN/1.1.0/)；日期自动填今天。

## 范围

仅本仓：业务仓不动 template 版本号（跨版本兼容由 `_check_template_version.sh` 处理）。跨仓通用技能不在范围。

## 故障排查

| 现象 | 原因 | 解决 |
|------|------|------|
| `Tag v1.0.0 missing. First run: bump-version --retro-tag v1.0.0` | 历史 commit 没打 tag | 先 `--retro-tag` 补 |
| `release-check FAIL` 后无 tag | 5 步门禁拦截 | 看 stderr，commit 可 `git reset --soft HEAD~1` 撤回 |
| `Not a git repo` | 跑错目录 | `cd` 到仓库根 |
| major bump 拒绝 | 缺 `--accept-major-bump` flag | 显式加 |

## 反模式（不要做）

- ❌ 不在 master 分支跑（先 `git checkout -b release/v1.0.1`）
- ❌ 不带 `--dry-run` 就跑（先用 dry-run 验 preview）
- ❌ 在工作区脏时跑（先 `git stash` 或 commit）
- ❌ `bump-version --push` 直接推到 master（先用 dry-run + 手动 push 复核）
- ❌ 改 `template/package/scripts/release-check.sh`（已是 5 步门禁真源，不应被绕）

## 相关文件

- 真源脚本：`skills/bump-version/bump-version.sh`（同行同住，便于 Claude Code auto-discover）
- 调用的分类逻辑：`template/package/scripts/check_template_version.py`（parse / classify / bump）
- 5 步门禁：`scripts/release-check.sh`
- 跨版本兼容（业务仓侧）：`template/package/scripts/_check_template_version.sh`

## 缩略语

- **bump** = 升版本号（semver 三段 major.minor.patch 中的某段 +1）
- **conventional commits** = `feat:` / `fix:` / `BREAKING:` 等 commit 类型约定
- **retro-tag** = 补历史 commit 的 git tag（用于 v1.0.0 已 commit 但无 tag）
- **DUAL policy** = patch/minor 自动 accept，major 需 `--accept-major-bump`（与 `_check_template_version.sh` 一致）
- **Keep-a-Changelog 1.1.0** = CHANGELOG 格式规范；本 skill 自动遵守