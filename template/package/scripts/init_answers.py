#!/usr/bin/env python3
"""立项答案清单（/auto-nn-init --answers）校验 / 示例 / 单题锁文本 / 题序 / 草稿识别 / 从问答记录导出。

用法：
  python3 scripts/init_answers.py validate --answers 答卷.yaml --workflow migrate \
      [--repo-root <target>] [--write-resolved] [--json]
  python3 scripts/init_answers.py classify --answers 文件.yaml|.md|.txt
  python3 scripts/init_answers.py export --repo-root <target> [--workflow migrate] [--out 路径]
  python3 scripts/init_answers.py template --workflow build
  python3 scripts/init_answers.py lock --slug I1-train-consumes --choice B \
      --field eval_only_assets=data/x.npy --field eval_only_readers=contract/test.py,contract/prepare_data.py
  python3 scripts/init_answers.py steps --workflow migrate

退出码：0 通过（可有警告）；1 清单有错误；2 文件 / 题库缺失或参数错。
产物（--write-resolved）：<repo_root>/.auto-nn/init-answers.resolved.json —— 立项 Agent 每步查表用；
产物（export）：<repo_root>/.auto-nn/init-answers.yaml —— 下次 --answers 可复用；**不是**口径汇总。
**不是**问答记录，不替代 append-init-qa-log。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.init_answers import (  # noqa: E402
    EXPORT_REL,
    RESOLVED_REL,
    AnswersError,
    Resolved,
    dump_answers_yaml,
    export_from_qa_log,
    load_answers_file,
    load_registry,
    normalize_answer,
    peek_answers_kind,
    render_lock,
    render_template,
    steps_for,
    validate_answers,
)
from lib.init_qa_log import log_path  # noqa: E402

_TAG = "[init-answers]"


def _report(res: Resolved) -> str:
    lines = [f"{_TAG} workflow={res.workflow} 入口={res.entry} 清单={res.answers_file or '-'}"]
    for e in res.errors:
        lines.append(f"  ERROR  {e}")
    for w in res.warnings:
        lines.append(f"  WARN   {w}")
    if res.resolved:
        lines.append("  已解析（按步序）：")
        for item in sorted(res.resolved.values(), key=lambda x: (x.step is None, x.step or 0)):
            ui = "跳卡" if item.skip_ui else ("改回确认" if item.confirm_required else "照问")
            step = f"第 {item.step} 步" if item.step is not None else "-"
            choice = f" choice={item.choice}" if item.choice else ""
            lines.append(f"    {step:<8} {item.slug:<24} {item.key:<8} {ui}{choice}  lock={item.lock}")
    if res.reference_only:
        lines.append("  仅作参考（照问）：" + ", ".join(res.reference_only))
    if res.unknown_keys:
        lines.append("  未知键：" + ", ".join(res.unknown_keys))
    if res.info_perm_flags:
        lines.append(
            "  INFO_PERM 落表参数：python3 scripts/init_info_perm.py write --repo-root <target> "
            + " ".join(_q(f) for f in res.info_perm_flags)
        )
    skippable = sum(1 for i in res.resolved.values() if i.skip_ui)
    if res.confirm_only:
        lines.append("  confirm_only：对人只出口径汇总签字（F1 不可代签）")
    lines.append(f"{_TAG} {'OK' if res.ok else 'FAIL'}：错误 {len(res.errors)} / 警告 {len(res.warnings)} / 可跳 {skippable} 题")
    return "\n".join(lines)


def _q(s: str) -> str:
    return s if s and all(c.isalnum() or c in "-_./,:=" for c in s) else json.dumps(s, ensure_ascii=False)


def _reject_template_pkg(root: Path) -> bool:
    if "template/package" in str(root.resolve()):
        print(f"{_TAG} ERROR: --repo-root 指向 template/package（{root}）；禁止向模板仓写 .auto-nn/", file=sys.stderr)
        return True
    return False


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="立项答案清单工具")
    p.add_argument("--registry", type=Path, default=None, help="题库路径（默认 docs/init/init-question-registry.yaml）")
    sub = p.add_subparsers(dest="cmd", required=True)

    pv = sub.add_parser("validate", help="校验清单并产出 resolved JSON")
    pv.add_argument("--answers", type=Path, required=True)
    pv.add_argument("--workflow", choices=("build", "migrate", "update"), required=True)
    pv.add_argument("--repo-root", type=Path, default=None, help="目标业务仓根（--write-resolved 时必填）")
    pv.add_argument("--write-resolved", action="store_true", help="写 <repo_root>/.auto-nn/init-answers.resolved.json")
    pv.add_argument("--json", action="store_true", help="stdout 输出 JSON 而非人读报告")

    pt = sub.add_parser("template", help="输出示例清单（只含允许跳问的题）")
    pt.add_argument("--workflow", choices=("build", "migrate", "update"), required=True)

    pl = sub.add_parser("lock", help="单题锁文本（现场一问一答也可用）")
    pl.add_argument("--slug", required=True)
    pl.add_argument("--choice", default=None)
    pl.add_argument("--field", action="append", default=[], help="k=v；列表用逗号分隔")

    ps = sub.add_parser("steps", help="打印该 workflow 的计步题序（与 reference 编号速查一致）")
    ps.add_argument("--workflow", choices=("build", "migrate", "update"), required=True)

    pc = sub.add_parser("classify", help="识别标准答卷 vs md/txt 草稿")
    pc.add_argument("--answers", type=Path, required=True)

    pe = sub.add_parser("export", help="从问答记录导出下次可复用的标准答卷")
    pe.add_argument("--repo-root", type=Path, required=True)
    pe.add_argument("--workflow", choices=("build", "migrate", "update"), default=None)
    pe.add_argument("--out", type=Path, default=None, help="默认 <repo>/.auto-nn/init-answers.yaml")

    args = p.parse_args(argv)
    try:
        registry = load_registry(args.registry)
    except AnswersError as exc:
        print(f"{_TAG} {exc}", file=sys.stderr)
        return 2

    try:
        if args.cmd == "template":
            sys.stdout.write(render_template(registry, args.workflow))
            return 0
        if args.cmd == "steps":
            for i, slug in enumerate(steps_for(registry, args.workflow), 1):
                print(f"{i}\t{slug}")
            return 0
        if args.cmd == "lock":
            q = registry.find(args.slug)
            if q is None:
                print(f"{_TAG} 题库无此题：{args.slug}", file=sys.stderr)
                return 2
            raw: dict = {}
            for kv in args.field:
                if "=" not in kv:
                    print(f"{_TAG} --field 须为 k=v：{kv}", file=sys.stderr)
                    return 2
                k, v = kv.split("=", 1)
                raw[k.strip()] = v
            if q.kind == "choice":
                raw["choice"] = args.choice
            choice, fields, errs = normalize_answer(q, raw)
            if errs:
                for e in errs:
                    print(f"{_TAG} ERROR {e}", file=sys.stderr)
                return 1
            print(render_lock(q, choice, fields))
            return 0
        if args.cmd == "classify":
            kind = peek_answers_kind(args.answers)
            print(kind)
            return 0
        if args.cmd == "export":
            if _reject_template_pkg(args.repo_root):
                return 2
            qa = log_path(args.repo_root)
            if not qa.is_file():
                print(f"{_TAG} 问答记录不存在：{qa}", file=sys.stderr)
                return 2
            doc = export_from_qa_log(
                registry,
                qa_text=qa.read_text(encoding="utf-8"),
                workflow=args.workflow,
            )
            out = args.out or (args.repo_root.resolve() / EXPORT_REL)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(dump_answers_yaml(doc), encoding="utf-8")
            missing = doc.get("_missing") or []
            if missing:
                print(f"{_TAG} WARN 问答记录缺题，未标完整表：{', '.join(missing)}")
            print(f"{_TAG} 已导出 {out}  confirm_only={doc.get('confirm_only')}  题数={len(doc.get('answers') or {})}")
            return 0

        doc = load_answers_file(args.answers)
        res = validate_answers(registry, doc, workflow=args.workflow, answers_file=str(args.answers))
    except AnswersError as exc:
        print(f"{_TAG} {exc}", file=sys.stderr)
        return 2

    if args.write_resolved:
        if args.repo_root is None:
            print(f"{_TAG} --write-resolved 需要 --repo-root <目标仓>", file=sys.stderr)
            return 2
        if _reject_template_pkg(args.repo_root):
            return 2
        out = args.repo_root.resolve() / RESOLVED_REL
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(res.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        res.warnings.append(f"已写 {out}")
    if args.json:
        print(json.dumps(res.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(_report(res))
    return 0 if res.ok else 1


if __name__ == "__main__":
    sys.exit(main())
