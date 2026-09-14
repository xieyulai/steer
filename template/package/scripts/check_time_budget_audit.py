#!/usr/bin/env python3
"""time_budget 收工审计：扫 _runs/exp/*/config.json 对齐 nn-config.yaml。

config.json 的 time_budget 由 experiment.py 训末写「实际生效值」——
env 通道偏离（如 agent 会话内 export NN_TIME_BUDGET）只有这里可见
（快照扫描只看代码读没读 env，看不见调用时 env 的值）。

顺带报告 _runs/time_budget_violations.log 的存在（取值点守卫的拒启记录；
同 uid 下该文件理论上可被删——缺失本身即异常信号，人工核）。

exit code：
  0 = 全部一致（或无实验目录）
  1 = 存在偏离（列出实验名与值；供收工裁定披露，不作自动处置）

用法：python3 scripts/check_time_budget_audit.py [repo_root]   # 默认 cwd
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from lib.nn_config import load_nn_config  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    repo_root = Path(args[0]).resolve() if args else Path.cwd().resolve()

    expected = int(load_nn_config(repo_root).get("time_budget", 3600))

    violations_log = repo_root / "_runs" / "time_budget_violations.log"
    if violations_log.is_file():
        n = len(violations_log.read_text(encoding="utf-8").splitlines())
        print(f"WARN: 存在启动期违约日志 {violations_log}（{n} 条；取值点守卫拒启记录）")

    exp_root = repo_root / "_runs" / "exp"
    if not exp_root.is_dir():
        print(f"TB_AUDIT OK: 无实验目录（{exp_root} 不存在），预期 time_budget={expected}s")
        return 0

    mismatches: list[tuple[str, object, Path]] = []
    total = 0
    for cfg_json in sorted(exp_root.glob("*/config.json")):
        total += 1
        try:
            actual = int(json.loads(cfg_json.read_text(encoding="utf-8"))["time_budget"])
        except (KeyError, ValueError, TypeError, json.JSONDecodeError):
            mismatches.append((cfg_json.parent.name, "<缺失/非法>", cfg_json))
            continue
        if actual != expected:
            mismatches.append((cfg_json.parent.name, actual, cfg_json))

    if mismatches:
        print(f"TB_AUDIT FAIL: {len(mismatches)}/{total} 份 config.json time_budget 偏离（预期 {expected}s，来自 nn-config.yaml）：")
        for name, actual, path in mismatches:
            print(f"  {name}: time_budget={actual}s  ({path})")
        print("提示：偏离行进收工裁定披露（adjudication 先例）；smoke/复算等合法短墙钟不落 config.json（走 NN_SMOKE_BUDGET / 沙盒 yaml）。")
        return 1
    print(f"TB_AUDIT OK: {total} 份 config.json 全部 time_budget={expected}s（对齐 nn-config.yaml）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
