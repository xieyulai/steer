#!/usr/bin/env python3
"""立项「信息权限」三问落表：改写 ``contract/runtime.py::INFO_PERM`` 字面量 + README ``<!-- INFO_PERM -->`` 块。

用法：
  python3 scripts/init_info_perm.py write --repo-root <target> \
      --consumes B --eval-only-assets data/x.npy --eval-only-readers contract/test.py \
      --official-path B --official-path-impl _reconstruct --official-path-rule "先压成 ≤64 bit 码，再只凭码还原" \
      --other-rules 均无 [--train-batch-keys x --train-batch-keys y] [--enforce yes|no] [--dry-run]
  python3 scripts/init_info_perm.py write --repo-root <target> --from-resolved <target>/.auto-nn/init-answers.resolved.json
  python3 scripts/init_info_perm.py show  --repo-root <target>

写后自动跑 scripts/info_perm_gate.py 对账；对账非 0 → 回滚两文件并返回 1。
只在立项阶段 2 / 二次初始化用（合同 G-契约：动 contract/ 须 NN_RELAUNCH=1 的语境）；运行时不调用。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.info_perm import InfoPermError, load_info_perm  # noqa: E402

_TAG = "[init-info-perm]"
_LETTER_TO_PATH = {"A": "full_model", "B": "restricted", "C": "eval_mode_locked"}
_LETTER_TO_CONSUMES = {"A": "全部数据都能训", "B": "只有训练份", "C": "无数据文件（样本由代码生成）"}
_LITERAL = re.compile(r"^INFO_PERM\s*=\s*\{.*?^\}\n?", re.S | re.M)
_BLOCK = re.compile(r"<!--\s*INFO_PERM\s*-->.*?<!--\s*/INFO_PERM\s*-->", re.S)
_SECTION_HEAD = re.compile(r"^### 3\.2b .*$", re.M)


def _tuple_literal(items: list[str]) -> str:
    if not items:
        return "()"
    return "(" + ", ".join(repr(x) for x in items) + ("," if len(items) == 1 else "") + ")"


def render_literal(a: argparse.Namespace) -> str:
    strict = bool(a.strict_no_train_files or a.consumes == "C")
    impl = a.official_path_impl if a.official_path in ("B", "C") else None
    keys = list(a.train_batch_keys or [])
    return (
        "INFO_PERM = {\n"
        f"    \"enforce\": {a.enforce == 'yes'},\n"
        f"    \"official_path\": {_LETTER_TO_PATH[a.official_path]!r},"
        "        # full_model | restricted | eval_mode_locked（问②）\n"
        f"    \"official_path_impl\": {impl!r},           # restricted / eval_mode_locked 时 run() 必须调用的函数名\n"
        "    \"official_path_switch\": \"_official_path_enabled\",   # 交卷开关函数名；存在则须单条 return True/False\n"
        f"    \"eval_only_assets\": {_tuple_literal(list(a.eval_only_assets))},"
        "               # 问①：只评资产——路径 glob，或 contract. 开头的读取函数名\n"
        f"    \"eval_only_readers\": {_tuple_literal(list(a.eval_only_readers))},"
        "          # 允许打开只评资产的文件（仓根相对路径）\n"
        f"    \"train_batch_keys\": {_tuple_literal(keys) if keys else None},"
        "             # 训练首 batch 键白名单（dict 键 / tuple 项数）；None 不校\n"
        f"    \"strict_no_train_files\": {strict},"
        "       # D2 TRAIN 为「无数据文件」时置 True：工作区不得读任何数据文件\n"
        "}\n"
    )


def render_block(a: argparse.Namespace) -> str:
    assets = ", ".join(a.eval_only_assets) or "无"
    readers = ", ".join(a.eval_only_readers)
    consumes = f"{a.consumes} {_LETTER_TO_CONSUMES[a.consumes]}"
    if a.consumes in ("B", "C"):
        consumes += f"；只评：{assets}（读者：{readers}）"
    path_names = {"A": "整网前向", "B": "受限路径", "C": "固定评测态"}
    official = f"{a.official_path} {path_names[a.official_path]}"
    if a.official_path in ("B", "C"):
        official += f"（{a.official_path_impl}）"
        if a.official_path_rule:
            official += f"：{a.official_path_rule}"
    rules = (a.other_rules or "均无").strip() or "均无"
    if a.train_batch_keys:
        rules += f"（机器管：训练 batch 键 {','.join(a.train_batch_keys)}）"
    return (
        "<!-- INFO_PERM -->\n"
        f"TRAIN_CONSUMES: {consumes}\n"
        f"OFFICIAL_PATH: {official}\n"
        f"OTHER_RULES: {rules}\n"
        f"ENFORCE: {a.enforce}\n"
        "<!-- /INFO_PERM -->"
    )


def _apply_readme(text: str, block: str) -> str:
    if _BLOCK.search(text):
        return _BLOCK.sub(lambda _m: block, text, count=1)
    m = _SECTION_HEAD.search(text)
    if m:
        return text[: m.end()] + "\n\n" + block + text[m.end():]
    return text.rstrip("\n") + "\n\n### 3.2b 信息权限（立项三问落盘；须与 `contract/runtime.py` 的 `INFO_PERM` 一致）\n\n" + block + "\n"


def _reject_template_pkg(root: Path) -> bool:
    if "template/package" in str(root.resolve()):
        print(f"{_TAG} ERROR: --repo-root 指向 template/package（{root}）；禁止改模板真源", file=sys.stderr)
        return True
    return False


def _flags_from_resolved(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not data.get("ok", False):
        raise SystemExit(f"{_TAG} resolved 清单有错误（ok=false），先修清单：{path}")
    flags = data.get("info_perm_flags") or []
    if not flags:
        raise SystemExit(f"{_TAG} resolved 清单不含信息权限三问（info_perm_flags 空）：{path}")
    return [str(f) for f in flags]


def _validate(a: argparse.Namespace) -> list[str]:
    errs: list[str] = []
    if a.consumes not in _LETTER_TO_CONSUMES:
        errs.append("--consumes 须为 A/B/C")
    if a.official_path not in _LETTER_TO_PATH:
        errs.append("--official-path 须为 A/B/C")
    if a.consumes == "B" and not a.eval_only_assets:
        errs.append("--consumes B 必须给 --eval-only-assets（哪些只评）")
    if a.official_path in ("B", "C") and not a.official_path_impl:
        errs.append("--official-path B/C 必须给 --official-path-impl（run() 必调的手续函数名）")
    if a.official_path_impl and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", a.official_path_impl):
        errs.append(f"--official-path-impl 须为合法函数名：{a.official_path_impl!r}")
    if a.enforce not in ("yes", "no"):
        errs.append("--enforce 须为 yes/no")
    if a.enforce == "no" and a.consumes == "C":
        errs.append("C-DL1：常见可试 data-loss 开时 --consumes 不能是 C（训练须能读场）")
    return errs


def cmd_write(a: argparse.Namespace) -> int:
    root = Path(a.repo_root).resolve()
    if _reject_template_pkg(root):
        return 2
    if a.from_resolved:
        parser = _write_parser(argparse.ArgumentParser(add_help=False))
        extra = parser.parse_args(_flags_from_resolved(Path(a.from_resolved)))
        for k, v in vars(extra).items():
            if k in ("repo_root", "from_resolved", "dry_run"):
                continue
            default = parser.get_default(k)
            if v != default:
                setattr(a, k, v)
    if not a.eval_only_readers:
        a.eval_only_readers = ["contract/test.py"]
    errs = _validate(a)
    if errs:
        for e in errs:
            print(f"{_TAG} ERROR {e}", file=sys.stderr)
        return 2

    runtime, readme = root / "contract" / "runtime.py", root / "README.md"
    if not runtime.is_file():
        print(f"{_TAG} 缺 {runtime}", file=sys.stderr)
        return 2
    if not readme.is_file():
        print(f"{_TAG} 缺 {readme}", file=sys.stderr)
        return 2
    old_rt, old_md = runtime.read_text(encoding="utf-8"), readme.read_text(encoding="utf-8")
    literal, block = render_literal(a), render_block(a)
    if _LITERAL.search(old_rt):
        new_rt = _LITERAL.sub(lambda _m: literal, old_rt, count=1)
    else:
        # 存量业务仓（模板 INFO_PERM 之前迁入）：二次初始化时补登记，追加到文件末尾
        print(f"{_TAG} 注意：{runtime.relative_to(root)} 原无 INFO_PERM 字面量，已追加到文件末尾")
        new_rt = old_rt.rstrip("\n") + "\n\n# 信息权限登记表（立项三问落表；spec 20260905_1755 / 20260905_1845）\n" + literal
    new_md = _apply_readme(old_md, block)
    if a.dry_run:
        print(literal.rstrip())
        print(block)
        print(f"{_TAG} dry-run：未写文件")
        return 0
    runtime.write_text(new_rt, encoding="utf-8")
    readme.write_text(new_md, encoding="utf-8")
    from info_perm_gate import main as gate_main  # noqa: E402

    rc = gate_main(["info_perm_gate.py", str(root)])
    if rc != 0:
        runtime.write_text(old_rt, encoding="utf-8")
        readme.write_text(old_md, encoding="utf-8")
        print(f"{_TAG} 对账失败（rc={rc}），已回滚 contract/runtime.py 与 README.md", file=sys.stderr)
        return 1
    print(f"{_TAG} 已写 {runtime.relative_to(root)} INFO_PERM 与 README INFO_PERM 块（对账 OK）")
    return 0


def cmd_show(a: argparse.Namespace) -> int:
    root = Path(a.repo_root).resolve()
    try:
        perm = load_info_perm(root)
    except InfoPermError as exc:
        print(f"{_TAG} INFO_PERM 非法：{exc}")
        return 1
    if perm is None:
        print(f"{_TAG} contract/runtime.py 无 INFO_PERM 登记")
        return 1
    for k, v in vars(perm).items():
        print(f"{k:<24} {v!r}")
    readme = root / "README.md"
    m = _BLOCK.search(readme.read_text(encoding="utf-8")) if readme.is_file() else None
    print(m.group(0) if m else f"{_TAG} README 无 INFO_PERM 块")
    return 0


def _write_parser(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
    p.add_argument("--repo-root", default=".")
    p.add_argument("--from-resolved", default=None, help="init_answers.py validate --write-resolved 的 JSON；其 info_perm_flags 作为参数")
    p.add_argument("--consumes", default="A", help="问①：A 全部 / B 只有训练份 / C 无数据文件")
    p.add_argument("--eval-only-assets", action="append", default=[], help="只评资产（glob 或 contract. 开头函数名），可重复")
    p.add_argument("--eval-only-readers", action="append", default=[], help="允许读只评资产的合同文件，可重复；默认 contract/test.py")
    p.add_argument("--strict-no-train-files", action="store_true", help="工作区不得读任何数据文件（consumes=C 自动置）")
    p.add_argument("--official-path", default="A", help="问②：A 整网前向 / B 受限路径 / C 固定评测态")
    p.add_argument("--official-path-impl", default=None, help="B/C 时 run() 必调的手续函数名")
    p.add_argument("--official-path-rule", default="", help="B/C 时一句手续（只进 README）")
    p.add_argument("--other-rules", default="均无", help="问③：均无 / 以；分隔的逐条规则")
    p.add_argument("--train-batch-keys", action="append", default=[], help="训练 batch 键白名单，可重复")
    p.add_argument("--enforce", default="yes", help="yes / no（T1 常见可试 data-loss 开→no，关→yes；立项默认 yes）")
    p.add_argument("--dry-run", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="立项信息权限三问落表")
    sub = p.add_subparsers(dest="cmd", required=True)
    _write_parser(sub.add_parser("write", help="写 INFO_PERM 字面量 + README 块并对账"))
    ps = sub.add_parser("show", help="打印当前登记与 README 块")
    ps.add_argument("--repo-root", default=".")
    a = p.parse_args(argv)
    return cmd_write(a) if a.cmd == "write" else cmd_show(a)


if __name__ == "__main__":
    sys.exit(main())
