#!/usr/bin/env python3
"""Append HARD-GATE 问答条目到 `.auto-nn/init-qa-log.md`。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lib.init_qa_log import append_entry, close_log, init_header
from lib.lock_normalize import (
    emit_stderr_warning,
    normalize_lock,
    write_warn_log,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Append init HARD-GATE Q&A log")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init-header", help="阶段 1 开始前写元数据")
    p_init.add_argument("--repo-root", type=Path, default=None,
                        help="业务仓根（spec T-A2: 显式传；不传则用 Path.cwd() 并 warn）")
    p_init.add_argument("--workflow", choices=("build", "migrate", "update"), required=True)
    p_init.add_argument("--target-root", required=True)
    p_init.add_argument("--source-root", default="")

    p_append = sub.add_parser("append", help="用户确认某编号后追加一条")
    p_append.add_argument("--repo-root", type=Path, default=None,
                          help="业务仓根（spec T-A2: 显式传；不传则用 Path.cwd() 并 warn）")
    p_append.add_argument("--step", required=True, help="如 11 或 准备 或 0")
    p_append.add_argument("--total", type=int, default=0, help="入口 A=27 B=24（含信息权限 I1–I3）；特殊步可 0")
    p_append.add_argument("--slug", required=True)
    p_append.add_argument("--theme", required=True)
    p_append.add_argument("--ask", required=True)
    p_append.add_argument("--options", default="")
    p_append.add_argument("--user", required=True)
    p_append.add_argument("--lock", required=True)

    p_close = sub.add_parser("close", help="F1 签字后闭合")
    p_close.add_argument("--repo-root", type=Path, default=None,
                         help="业务仓根（spec T-A2: 显式传；不传则用 Path.cwd() 并 warn）")
    p_close.add_argument("--user", required=True)
    p_close.add_argument("--contradiction-fail", type=int, default=0)
    p_close.add_argument("--note", default="")

    args = parser.parse_args()
    # spec T-A2 防线 0: 未传 --repo-root 时 fallback 到 Path.cwd()
    # 并 warn（向后兼容：让旧 in-tree 调用仍能工作）
    if args.repo_root is None:
        args.repo_root = Path.cwd()
        print(
            f"⚠ append-init-qa-log: --repo-root 未指定，fallback 到 cwd={args.repo_root}；"
            f"建议显式传 --repo-root <业务仓根>（spec T-A2）",
            file=sys.stderr,
        )
    root = args.repo_root.resolve()

    # spec T-A2 防线 1: 拒绝 template/package 路径（防漂移到模板仓）
    if "template/package" in str(root):
        print(
            f"ERROR: --repo-root 指向 template/package 路径 ({root})；"
            f"禁止向模板仓写 .auto-nn/init-qa-log.md（spec T-A2）。"
            f"请传 --repo-root <业务仓根>，例如 --repo-root /path/to/your/project",
            file=sys.stderr,
        )
        return 1

    if args.cmd == "init-header":
        init_header(
            root,
            workflow=args.workflow,
            target_root=args.target_root,
            source_root=args.source_root or None,
        )
    elif args.cmd == "append":
        # T6.5: 三态 normalize lock，让 derive 端拿可结构化编码
        normalized_lock, warns = normalize_lock(args.lock, slug=args.slug)
        if warns:
            # 双写：persist + 人可见
            _warn_log = root / ".auto-nn" / "lock_normalize_warnings.log"
            for _reason in warns:
                write_warn_log(slug=args.slug, text=args.lock, reason=_reason, log_path=_warn_log)
                emit_stderr_warning(slug=args.slug, text=args.lock, reason=_reason)
        append_entry(
            root,
            step=str(args.step),
            total=args.total or None,
            slug=args.slug,
            theme=args.theme,
            ask=args.ask,
            options=args.options,
            user=args.user,
            lock=normalized_lock,
        )
    elif args.cmd == "close":
        close_log(
            root,
            user=args.user,
            contradiction_fail=args.contradiction_fail,
            note=args.note,
        )
    print(f"OK: updated {root / '.auto-nn' / 'init-qa-log.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
