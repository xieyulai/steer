# Mirror 机制（真源 / 下发 / 例外）

> 面向模板维护者。业务仓侧不需要读这份——`template/package/` 的真源才是它该用的。

## 单一真源铁律

- **真源唯一**：`template/package/` 是分发给业务仓的唯一真源。
- **任何**在根目录出现的 `template/package/*` **同内容副本**，必须是
  **symlink**，**不是物理副本**；或（若业务仓与维护者侧均不引用根副本）
  直接删除根副本（commit `9ef43f7` 走的就是删除路径）。

## 根目录文件状态总表

> **历史注脚（2026-07-06，commit `9ef43f7`）**：根目录原先有 9 个 symlink +
> 3 个目录 symlink（`scripts/` `experiment.py` `auto-nn-run.sh` `reflect.py`
> `profiles.yaml` `docs/init/init-interaction-policy.yaml`
> `docs/nn-routing/{intent-map.md,README.md}`），Task 4 已**全部删除**。
> 业务仓直接引用 `template/package/` 真源，根副本从来不被业务仓 cp 走
> ——留 symlink 是冗余的物理展平，反而增加 drift 风险。

| 文件类型 | 根目录状态 | 物理位置 |
|----------|-----------|---------|
| **脚本 / 配置（自动下发）** | 无（已删除） | 全部在 `template/package/...`，业务仓治理走真源 |
| **文档 / 配置（根特有 vs 业务特有意图不同）** | 根 `CLAUDE.md` / 根 `README.md` / 根 `nn-config.yaml` | 物理副本（**有意为之**，下文说明） |

## 业务仓需要的文件怎么到达业务仓

- 通过 `bash template/package/scripts/governance-sync.sh --template-root <t>
  --project-root <p>` 触发。
- 治理三件套：`template/package/profiles.yaml` + `verify-migration-complete.sh` + 自身。
- 配置文件 merge / init 走 `template/package/scripts/merge-nn-config-keys.py` /
  `template/package/scripts/nn_config.py`。
- 自复制走 temp+mv（in-place cp 会截断）。

## 有意为之的例外（不在 mirror 范围内）

- **根 `CLAUDE.md`**：面向**模板维护者**（强调沙箱技能 + 维护者侧铁律）。
- **`template/package/CLAUDE.md`**：面向**业务仓**（强调 ExperimentBase +
  改码三原则）。
- 同理根 `README.md` vs `template/package/README.md`、根 `nn-config.yaml`
  vs `template/package/nn-config.yaml`。
- **`install.sh`、`docs/`、`skills/`、`README.md`、
  `CHANGELOG.md`**：均**不**下发，与维护仓同在。

这些**不是 mirror**——两份内容差异是设计意图（不同受众），不要 symlink。

## 发现 mirror candidate 的标准动作

发现根目录有同内容副本时，二选一：

### 路径 A：symlink 化（保留根入口）

适用于"维护者日常从根跑、但实际想跑真源"的场景：

1. `diff -q root_file template/package/root_file` — 若相同（或
   `template/package` 更新）→ **必须** symlink 化。
2. `git rm root_file && ln -s template/package/root_file root_file`。
3. 若 `root_file` 在子目录（如 `docs/init/`），symlink 目标须用相对路径
   （`../../template/package/...`）。

### 路径 B：删除根副本（真源已足）

适用于"业务仓只引用 `template/package/` 真源、根副本从来不被引用"的场景
（commit `9ef43f7` 删除 9 个根 symlink 即走此路径）：

1. `diff -q root_file template/package/root_file` — 确认根副本与真源一致。
2. `grep -rn 'root_file\|root_file/\|`<root_file>`' docs/ skills/ install.sh
   *.md` — 确认根目录与所有引用方都改走真源（更新 `scripts/X` →
   `template/package/scripts/X`）。
3. `git rm root_file`。
4. 更新所有文档与脚本中的引用路径。

> **判定**：根副本是否真的"被引用"？业务仓侧治理从真源 cp，根副本若仅是
> 物理展平（方便维护者从根 cwd 跑），走**路径 B** 即可（commit `9ef43f7`
> 验证可行）；若维护者侧脚本/工具依赖根副本路径（如 `bash scripts/X`），
> 改脚本到 `template/package/scripts/X` 后同样走**路径 B**。

## 违规代价

drift → 业务仓 cp 到旧版 → 用户硬性需求（如 ABCDE 脚本不生效）静默失败。

## 为什么历史上有过 mirror 反模式

在 mirror 机制根除之前（commit `834a2d0` 之前的版本），根目录 `scripts/`、
`experiment.py` 等是**物理副本**，与 `template/package/scripts/` 等平行存在。
后果是：

- 业务仓 `governance-sync` 时只 cp 真源到业务仓；根副本从不流出。
- 维护者改完真源忘了同步根副本 → 根副本与真源 drift。
- 下一次 `governance-sync` 仍走真源 → drift 静默累积。
- 业务仓侧从不引用根副本，但根副本若被某些工具/CI 间接引用，drift 表现为
  「改了不生效」的鬼影问题。

根除方案：**所有同内容副本必须 symlink 到 `template/package/...`**，drift 物理上不可能
（`diff -q` 必然相同或 symlink 目标更新）。

## 反例（为何不需要 mirror）

模板维护仓**不**需要镜像业务仓 layout（`scripts/`、`experiment.py` 等）。
维护者从根跑 `governance-sync.sh` 时，真源已经在
`template/package/scripts/governance-sync.sh`，直接调真源即可；无需 root
副本或 symlink。历史上有过根 `scripts/` 是 symlink 的设计（commit `ffb66e5`
引入，commit `9ef43f7` 删除），目的是减少维护者从根 cwd 跑的路径书写
负担；但既然维护者侧文档都改成 `template/package/scripts/X`，symlink 也就
多余了。

## 子目录 symlink 的相对路径写法

`docs/init/` 下的文件 symlink 时，目标必须用相对路径（git 不存绝对路径）：

```bash
# docs/init/foo.yaml → ../../template/package/docs/init/foo.yaml
cd docs/init
git rm foo.yaml
ln -s ../../template/package/docs/init/foo.yaml foo.yaml
```

`readlink` 与 `git ls-files --stage` 都能验：

```bash
$ readlink docs/init/foo.yaml        # → ../../template/package/docs/init/foo.yaml
$ git ls-files --stage docs/init/foo.yaml
120000 ... ../../template/package/docs/init/foo.yaml   # mode 120000 = symlink blob
```

如果回显是绝对路径或 `./...` 形式，是历史遗留物理副本——必须按上面流程
symlink 化。

## 当 root_file "不是 mirror" 时（3 类有意例外）

判定一个根目录副本**不**算 mirror、可以保留物理副本，必须落在以下三类之一：

1. **受众不同**：根 `CLAUDE.md` / 根 `README.md` / 根 `nn-config.yaml` 三件套
   都属于"维护者侧 vs 业务仓侧"双受众场景。两份内容**注定**不一样（详见
   `template/package/CLAUDE.md` 与根 CLAUDE.md 对照），**不能** symlink。
2. **仓库级配置 / 文档骨架**：`install.sh`、`docs/`（子目录
   不计）、`skills/`、`README.md`、`CHANGELOG.md`——这些**只**服务于维护仓
   自己，不下发业务仓（governance-sync 不 cp），自然不存在 mirror 问题。
3. **运行时产物**：`_runs/` 等——不在治理同步路径上，与真源无关。

判定流程：`diff -q root_file template/package/root_file` 若**相同**，但 root_file
落不到上述三类例外 → 必是漏 symlink 的 mirror candidate，必须按上面"标准动作"
处理。

## git 对 symlink 的特殊处理（历史不会撒谎）

- `git add` 一个 symlink 写入的是 **blob with mode 120000**（不是内容 blob）。
- `git diff --follow <symlink>` 不会跨过 symlink 跟到目标；要看真实 diff 直接
  读 `template/package/...`。
- `git rm <symlink>` 只删 symlink 自身（mode 120000），不会动真源
  `template/package/...`。所以"误以为自己在删 root 副本、结果真源也被删"
  这类事故**不会**发生——前提是 symlink 化做对。
- `git log --diff-filter=A -- <symlink>` 可回溯每个 symlink 是何时从物理副本
  转成 symlink 的（如本仓 `scripts/` 转 symlink 的提交 `ffb66e5 refactor(template): root 镜像机制根除 — single source of truth`）。
- 跨工作树 clone：`git worktree add <path> master` 拿到的 symlink 与真源仍是
  一致链接，不会被"展平"为物理副本。

也就是说：**一旦 symlink 化，drift 在物理上不可能**——`diff -q` 必然相同（或 symlink 目标更新）。这是上一节根除方案"drift 物理上不可能"的 git 层依据。

## 与根 CLAUDE.md 的关系

- 根 `CLAUDE.md` 是入口与跳转枢纽（≤ 80 行），把维护者侧细节指向本目录三文件。
- 本文件是上一代根 CLAUDE.md §"单一真源铁律（mirror 机制禁止）" 表的
  完整搬迁 + 上下文补全，commit `834a2d0` 之前的版本可对照。
