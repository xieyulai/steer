#!/usr/bin/env python3
"""modify-config.py — 快速修改 config.json 参数（Config-Only 辅助）

用法：
  # 读取现有配置，修改参数后保存
  python scripts/modify-config.py _runs/configs/experiment.json --set LR=0.003 --set EPOCHS=200

  # 从模板复制并修改（模板不存在则报错）
  python scripts/modify-config.py _runs/configs/new_exp.json --from-template _runs/configs/base.json --set LR=0.005

  # 只打印结果，不写入
  python scripts/modify-config.py _runs/configs/experiment.json --set LR=0.003 --dry-run
"""
import argparse
import json
import sys
from pathlib import Path


def load_config(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def save_config(path: Path, cfg: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(cfg, f, indent=2)
    print(f"[modify-config] 已写入: {path}", file=sys.stderr)


def parse_set_arg(s: str) -> tuple[str, str | int | float | bool]:
    """解析 KEY=VALUE，返回 (key, value)"""
    if "=" not in s:
        raise ValueError(f"无效 --set 格式: {s}，应为 KEY=VALUE")
    key, raw_val = s.split("=", 1)
    key = key.strip()
    if not key:
        raise ValueError(f"无效 --set 格式: {s}，KEY 不能为空")

    # 自动类型转换
    if raw_val == "true":
        return (key, True)
    elif raw_val == "false":
        return (key, False)
    elif raw_val == "null":
        return (key, None)
    try:
        if "." in raw_val:
            return (key, float(raw_val))
        return (key, int(raw_val))
    except ValueError:
        return (key, str(raw_val))


def main():
    parser = argparse.ArgumentParser(
        description="快速修改 config.json 参数（Config-Only）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("output", help="输出 config.json 路径")
    parser.add_argument("--from-template", dest="template", help="从模板复制（不修改原始模板）")
    parser.add_argument("--set", action="append", dest="sets", default=[], help="设置参数 KEY=VALUE（可多次使用）")
    parser.add_argument("--dry-run", action="store_true", help="只打印结果，不写入文件")

    args = parser.parse_args()

    # 确定配置来源
    if args.template:
        cfg = load_config(Path(args.template))
        print(f"[modify-config] 从模板复制: {args.template}", file=sys.stderr)
    elif Path(args.output).exists():
        cfg = load_config(Path(args.output))
    else:
        print(f"[modify-config] 错误: {args.output} 不存在，且未指定 --from-template", file=sys.stderr)
        sys.exit(1)

    # 解析并应用修改
    explicit_baseline_tag = False
    for set_arg in args.sets:
        key, val = parse_set_arg(set_arg)
        if key == "baseline_tag":
            explicit_baseline_tag = True
        cfg[key] = val
        print(f"[modify-config] 设置 {key}={repr(val)}", file=sys.stderr)

    # --from-template 且未显式 --set baseline_tag=... 时，默认重置为 none
    if args.template and not explicit_baseline_tag:
        cfg["baseline_tag"] = "none"
        print(
            "[modify-config] --from-template: baseline_tag 重置为 none",
            file=sys.stderr,
        )

    # 输出
    if args.dry_run:
        print(json.dumps(cfg, indent=2))
    else:
        save_config(Path(args.output), cfg)


if __name__ == "__main__":
    main()