---
name: auto-nn-setup
description: >-
  换机/重装系统/依赖损坏后一条命令把运行环境拉到「smoke 可过」：自动检测驱动
  CUDA→torch 源重映射（cu124/cu121/cu118/cpu）、依赖安装（慢自动换清华源）、
  GPU 白名单按 `~/.gpus ∩ 本机实际 GPU` 收敛（没建 `~/.gpus` 则跳过收紧）、跑 smoke 验收；失败自动回滚
  pyproject/lock。改显卡白名单（`gpus` 字段）属本技能专属破例。
  NL: 换机|重装|环境跑不起来|装依赖|torch 装不上|换机后 setup. NOT: 看台账→check.
---

# auto-nn-setup — 换机/重装环境一键拉起

**问题：** 项目从机器 A cp 到机器 B（或重装系统后），环境往往跑不起来——`nn-config.yaml`
的 `gpus:` 还指着 A 的卡、torch 装的版本和 B 的驱动 CUDA 对不上、依赖没装。现成
`check-env.sh` 只报不修，人得逐条敲。开训会再读家目录 `~/.gpus`（有文件才限制占用）。

**解法：** `scripts/auto-nn-setup.py`（系统 python3 直接跑、零第三方依赖——venv 还没建好时
它来建）。一条命令：检测 → 自动修复 → smoke 验收，失败自动回滚。

## Code Contract

> `scripts/check_skill_contract.sh` 自动对账本段与 `template/package/*` 实际符号；
> 失败 → release-check 第 6 步门禁拦截。**强检字段**：`calls_scripts` / `reads_cfg_keys` /
> `env_vars_consumed`。

```yaml
calls_scripts:
  - scripts/auto-nn-setup.py      # 核心：检测+修复+smoke 验收
  - scripts/smoke-check.sh        # 验收入口（L33 内嵌 check-env，§8）

reads_cfg_keys:
  - gpus                          # 顶层 GPU 白名单（本技能专属可写，破 CLAUDE:124 铁律）

env_vars_consumed:
  - POETRY_PYPI_MIRROR            # 失败重试时设清华源（仅本次子进程，不改全局 poetry config）
  - POETRY_HTTP_TIMEOUT           # 同上重试超时
```

## 何时使用

- 换机器 / cp 项目到新机器 / 重装系统后环境跑不起来
- torch 装不上（CUDA 版不匹配）/ 依赖损坏 / `.venv` 丢了
- **不要**用于：每轮实验（→ `/auto-nn-auto-run`）；看台账（→ `/auto-nn-check`）；
  环境体检（→ `/auto-nn-doctor`，只报不修）；init（→ `/auto-nn-init`）

## 用法

```bash
# 1. 预览（只检测报告，不改盘）
python3 scripts/auto-nn-setup.py --dry-run --project-root .

# 2. 一键修复 + smoke 验收（默认全自动）
python3 scripts/auto-nn-setup.py --project-root .
```

## 它做什么（自动）

1. **CUDA→torch 源映射**：解析 `nvidia-smi` 驱动 CUDA 版，自动选 wheel
   （≥12.4→cu124 / 12.1-12.3→cu121 / 11.8-12.0→cu118 / 无 GPU→cpu / <11.8→FAIL 升级驱动），
   改 `pyproject.toml` + 重 lock。
2. **依赖安装**：`poetry install`；首次失败自动切清华 TUNA 源重试（不改全局配置）。
3. **GPU 白名单收敛**：若有 `~/.gpus`，则 `nn-config.yaml` 的 `gpus:` = `~/.gpus ∩ 本机实际 GPU`
   （硬上限，绝不越界；**没建该文件则跳过收紧、不失败**。空文件 / 交集空仍 FAIL）。
   开训时同样：有文件才限制占用，没建也能训。
4. **常见动态库**：`import torch` 因缺 `.so`（如 cusparseLt）失败时，对 CUDA 12.x
   best-effort `poetry add nvidia-*-cu12`（不装系统 apt 库）。
5. **smoke 验收**：跑 `smoke-check.sh`（它 L33 内嵌 `check-env.sh` 兜环境就绪，再判能不能训）；
   不过 = 回滚 pyproject/lock + 报失败（重装不算成功）。

## 硬边界

- **改 `gpus` 字段** = 本技能专属破例（CLAUDE:124「常规仅改 `ledger:` 段」铁律）；
  常规迭代仍冻结 `gpus`。
- **不改 `experiment.py`**（基类不可变）；诊断不调 `check-env.sh`（接口不匹配，验收由
  smoke-check 内嵌它兜底）。
- **零第三方依赖**：仅 Python 标准库（系统裸 python3 跑得起来）；toml/yaml 改写靠针对性正则。
- **系统 pyyaml**：smoke-check 用系统 `python3 -c "import yaml"` 读 profile，setup 会检测
  并缺时装系统 pyyaml（系统层，非 venv、非"严禁 pip install"铁律范围）。

## 对用户怎么说（人话）

「这台机器显卡驱动支持 CUDA X.X，已把 torch 装成匹配的 cuXXX 档；如果你家目录有允许用的显卡名单，
就按那份名单和这台机器实际有的卡取交集写成项目名单；没建这份名单就不动项目里的卡名单（开训也不限制占用）。
装完跑了一轮 smoke，能训。/ 跑不起来，已还原配置，问题是 …」
