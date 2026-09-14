#!/usr/bin/env python3
"""README ``<!-- INFO_PERM -->`` 块 ↔ ``contract/runtime.py::INFO_PERM`` 对账。

块格式（立项三问落盘）：
    TRAIN_CONSUMES: A|B|C <一句>     # 问①：训练可用材料
    OFFICIAL_PATH:  A|B|C <一句>     # 问②：A 整网 / B 受限路径 / C 固定评测态
    OTHER_RULES:    均无 | <逐行>     # 问③
    ENFORCE:        yes|no           # 与 INFO_PERM["enforce"] 一致

退出码：0 一致；1 不一致 / 合同无登记 / 登记非法（verify FAIL）；2 块缺失或未填（verify WARN）。
用法：python3 scripts/info_perm_gate.py [repo_root]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.info_perm import InfoPermError, load_info_perm  # noqa: E402

_BLOCK = re.compile(r"<!--\s*INFO_PERM\s*-->(.*?)<!--\s*/INFO_PERM\s*-->", re.S)
_LETTER_TO_PATH = {"A": "full_model", "B": "restricted", "C": "eval_mode_locked"}
_YES = ("yes", "y", "true", "1", "是", "开")
_NO = ("no", "n", "false", "0", "否", "关")
_TAG = "[info-perm-gate]"


def parse_block(text: str) -> dict[str, str]:
    kv: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" in line:
            k, v = line.split(":", 1)
            kv[k.strip().upper()] = v.strip()
    return kv


def main(argv: list[str]) -> int:
    root = Path(argv[1] if len(argv) > 1 else ".").resolve()
    readme = root / "README.md"
    if not readme.is_file():
        print(f"{_TAG} 缺 README.md")
        return 2
    m = _BLOCK.search(readme.read_text(encoding="utf-8"))
    if not m:
        print(f"{_TAG} README 缺 <!-- INFO_PERM --> 块（立项三问未落盘）")
        return 2
    kv = parse_block(m.group(1))
    if not (kv.get("TRAIN_CONSUMES") and kv.get("OFFICIAL_PATH") and kv.get("ENFORCE")):
        print(f"{_TAG} INFO_PERM 块存在但 TRAIN_CONSUMES / OFFICIAL_PATH / ENFORCE 未填")
        return 2
    try:
        perm = load_info_perm(root)
    except InfoPermError as exc:
        print(f"{_TAG} contract/runtime.py INFO_PERM 非法：{exc}")
        return 1
    if perm is None:
        print(f"{_TAG} README 有 INFO_PERM 块但 contract/runtime.py 无 INFO_PERM 登记")
        return 1
    rc = 0
    letter = kv["OFFICIAL_PATH"].strip()[:1].upper()
    want = _LETTER_TO_PATH.get(letter)
    if want is None:
        print(f"{_TAG} OFFICIAL_PATH 须以 A/B/C 开头，得到 {kv['OFFICIAL_PATH']!r}")
        rc = 1
    elif want != perm.official_path:
        print(f"{_TAG} OFFICIAL_PATH={letter}（{want}）≠ 合同 official_path={perm.official_path!r}")
        rc = 1
    e = kv["ENFORCE"].strip().lower()
    if e in _YES:
        e_bool = True
    elif e in _NO:
        e_bool = False
    else:
        print(f"{_TAG} ENFORCE 须为 yes/no，得到 {kv['ENFORCE']!r}")
        return 1
    if e_bool != perm.enforce:
        print(f"{_TAG} ENFORCE={kv['ENFORCE']} ≠ 合同 enforce={perm.enforce}")
        rc = 1
    if rc == 0:
        print(f"{_TAG} OK：README INFO_PERM 块与 contract/runtime.py INFO_PERM 一致")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
