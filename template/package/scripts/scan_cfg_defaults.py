#!/usr/bin/env python3
"""scan_cfg_defaults.py — 扫描代码中 cfg.get/setdefault 默认值模式（Config-Only 门禁）

用法：
  python scripts/scan_cfg_defaults.py [ROOT] [--allow-system]
  ROOT 默认为当前目录。--allow-system 抑制 SYSTEM_KEYS 的 WARN（仍 WARN 不 FAIL）。

严格规则（无需维护 EXPERIMENT_KEYS 名单，自动捕获新键）：
  对每个 cfg.get(KEY, default) / cfg.setdefault(KEY, default) / cfg.get("KEY") 匹配：
    - KEY 非全大写（not key.isupper()）→ 允许（config-section 访问，如 cfg.get("agent")）。
    - KEY in SYSTEM_KEYS         → WARN（系统参数默认；--allow-system 抑制）。
    - 否则（全大写且不在名单）：
        * cfg.get("KEY", default) / cfg.setdefault("KEY", default) → FAIL（实验参数带默认，禁止）。
        * cfg.get("KEY") 无默认 → WARN（隐式 None fallback；返回 None 绕过 KeyError）。

扫描范围：experiment.py + workspace/**/*.py + contract/**/*.py（确定性排序）。

输出：
  - FAIL：实验参数 cfg.get/setdefault 带默认值（须改 cfg["X"]）
  - WARN：系统参数默认值；或实验参数 cfg.get 无默认（隐式 None）
"""
import argparse
import re
import sys
from pathlib import Path

# 系统参数：框架/运行态相关，非实验调参。可保留默认值（WARN 不阻断）。
# 注意：BATCH_SIZE 是实验参数 → 不在此名单 → 默认即 FAIL。
SYSTEM_KEYS = (
    "SMOKE_CHANNELS", "SMOKE_SPATIAL", "SMOKE_BATCH", "SMOKE_EPOCHS",
    "CHECKPOINT_POLICY", "CHECKPOINT_KIND",
    "EVAL_START_FRAC", "EVAL_EVERY_N",
    "NUM_WORKERS",          # datataloader 系统参数
    "SCENARIO_ID",          # 场景解析（框架侧，标识 scenario binding；非调参）
)

# 匹配 cfg.get(KEY, default)：KEY 可含小写（config-section 访问）。
# 分类交给 key.isupper()，故此处捕获宽松、判断严格。
CFG_GET_PATTERN = re.compile(
    r'cfg\.get\(["\']([A-Za-z_][A-Za-z0-9_]*)["\']\s*,\s*([^)]+)\)'
)

# cfg.get("UPPERCASE_KEY") 无默认（单参数）→ 返回 None（隐式 fallback）。
# 仅匹配大写键（无逗号），区分于 CFG_GET_PATTERN。小写键交给 key.isupper() 放行。
CFG_GET_NO_DEFAULT = re.compile(
    r'cfg\.get\(["\']([A-Z_][A-Z0-9_]*)["\']\s*\)'
)

# cfg.setdefault("UPPERCASE_KEY", default)：效果同 cfg.get 默认（隐式兜底）。
# 仅匹配大写键。
CFG_SETDEFAULT = re.compile(
    r'cfg\.setdefault\(["\']([A-Z_][A-Z0-9_]*)["\']\s*,\s*([^)]+)\)'
)


def _scan_files(root: Path) -> list[Path]:
    """experiment.py + workspace/**/*.py + contract/**/*.py，确定性排序。"""
    files: list[Path] = []
    exp = root / "experiment.py"
    if exp.is_file():
        files.append(exp)
    files.extend(sorted((root / "workspace").rglob("*.py")))
    files.extend(sorted((root / "contract").rglob("*.py")))
    # 去重（experiment.py 不会被 rglob 命中，但稳妥起见）
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in files:
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        unique.append(p)
    return unique


def scan(root: Path, allow_system: bool) -> int:
    fails = 0
    warns = 0
    for p in _scan_files(root):
        text = p.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            # (1) cfg.get(KEY, default)：大写实验参数带默认 → FAIL；SYSTEM_KEYS → WARN
            for m in CFG_GET_PATTERN.finditer(line):
                key, default = m.group(1), m.group(2).strip()
                if not key.isupper():
                    continue  # config-section 访问（小写键），允许
                if key in SYSTEM_KEYS:
                    if not allow_system:
                        print(f"[WARN] {p}:{i}: 系统参数 cfg.get({key!r}, {default}) — 如确需保留请加注释说明")
                        warns += 1
                    continue
                print(f"[FAIL] {p}:{i}: 实验参数 cfg.get({key!r}, {default}) 应改为 cfg[{key!r}]")
                fails += 1
            # (2) cfg.get("UPPERCASE_KEY") 无默认 → 隐式 None fallback → WARN
            for m in CFG_GET_NO_DEFAULT.finditer(line):
                key = m.group(1)
                if key in SYSTEM_KEYS:
                    if not allow_system:
                        print(f"[WARN] {p}:{i}: 系统参数 cfg.get({key!r}) 无默认值 — 如确需保留请加注释说明")
                        warns += 1
                    continue
                print(f"[WARN] {p}:{i}: 实验参数 cfg.get({key!r}) 无默认值（返回 None）— 应改 cfg[{key!r}] 强读")
                warns += 1
            # (3) cfg.setdefault("UPPERCASE_KEY", default) → 同 cfg.get 带默认 → FAIL
            for m in CFG_SETDEFAULT.finditer(line):
                key, default = m.group(1), m.group(2).strip()
                if key in SYSTEM_KEYS:
                    if not allow_system:
                        print(f"[WARN] {p}:{i}: 系统参数 cfg.setdefault({key!r}, {default}) — 如确需保留请加注释说明")
                        warns += 1
                    continue
                print(f"[FAIL] {p}:{i}: 实验参数 cfg.setdefault({key!r}, {default}) — 应改 cfg[{key!r}] 强读")
                fails += 1
    if fails:
        print(f"\n[scan_cfg_defaults] FAIL: {fails} 个实验参数默认值需移除")
        return 1
    print(f"\n[scan_cfg_defaults] OK: 0 实验参数默认值（{warns} 个系统参数 WARN）")
    return 0


def main():
    p = argparse.ArgumentParser(description="扫描 cfg.get 默认值（严格：全大写键默认→FAIL）")
    p.add_argument("root", nargs="?", default=".", help="项目根目录")
    p.add_argument("--allow-system", action="store_true", help="抑制 SYSTEM_KEYS 的 WARN")
    args = p.parse_args()
    sys.exit(scan(Path(args.root).resolve(), args.allow_system))


if __name__ == "__main__":
    main()
