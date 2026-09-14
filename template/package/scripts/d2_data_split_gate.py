#!/usr/bin/env python3
"""D2 数据划分门禁：README 须含 ``<!-- D2_DATA_SPLIT -->`` … ``<!-- /D2_DATA_SPLIT -->`` 块。

迁后 / verify 硬检；模板根跳过。profile 不同必填键不同。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

_MARKER_START = "<!-- D2_DATA_SPLIT -->"
_MARKER_END = "<!-- /D2_DATA_SPLIT -->"

# 各 profile 必填键（值非空）
_REQUIRED: dict[str, tuple[str, ...]] = {
    # PROFILE 不列：自动从 nn-config.yaml 推导，模板可留空（init 阶段 gate 跳过）
    "supervised": (
        "DATA_ROOT",
        "SPLIT_KIND",
        "TRAIN",
        "VAL",
        "TEST",
        "NORMALIZE_FIT_ON",
        "EVAL_USES",
        "TEST_USES",
        "E3_EVAL_FOR_KEEP",
        "VAL_TEST_SAME_DISTRIBUTION",
    ),
    "rl": (
        "DATA_ROOT",
        "SPLIT_KIND",
        "TRAIN_DATA_SOURCE",
        "OFFICIAL_EVAL",
        "NO_CLASSIC_SPLIT",
    ),
    "physical": (
        "DATA_ROOT",
        "SPLIT_KIND",
        "TRAIN",
        "VAL",
        "TRAIN_SAMPLING",
        "SAMPLING_TUNABLE",
        "EVAL_USES",
        "OFFICIAL_TEST",
        "E3_EVAL_FOR_KEEP",
        "VAL_TEST_SAME_DISTRIBUTION",
    ),
}

# physical：TRAIN_SAMPLING 须为语义句，禁止仅写函数调用
_TRAIN_SAMPLING_FUNC_ONLY = re.compile(
    r"^[a-zA-Z_][\w.]*\s*\([^)]*\)\s*$",
)
_TRAIN_SAMPLING_SEMANTIC_HINTS = (
    "语义",
    "配点",
    "实时",
    "无固定",
    "collocation",
    "none",
    "train/val",
    "train_val",
    "PDE",
    "pde",
)

_SPLIT_KIND_SUPERVISED = frozenset({
    "train_val_test",
    "train_holdout_no_val",
    "train_val_holdout_test",
    "custom",
})

# DATA_ROOT 路径后常见说明分隔（中英文括号、分号、空格+注释）
_DATA_ROOT_SUFFIX_SEPS = ("（", "(", "；", ";", " ", "\t")


def _data_root_path(raw: str) -> str:
    """从 D2 行值提取用于校验的相对路径（须 ``data/`` 前缀）。"""
    s = raw.strip()
    if not s:
        return ""
    for sep in _DATA_ROOT_SUFFIX_SEPS:
        if sep in s:
            s = s.split(sep, 1)[0].strip()
    return s


def _check_data_root_prefix(fields: dict[str, str]) -> list[str]:
    raw = fields.get("DATA_ROOT", "").strip()
    if not raw:
        return []
    path = _data_root_path(raw)
    if not path.startswith("data/"):
        return [
            f"DATA_ROOT={raw!r} 须以 data/ 开头（相对仓库根）；"
            "勿写 {{repo_root}}/、绝对路径或仓库外数据根",
        ]
    return []


def _load_profile(repo_root: Path) -> str:
    p = repo_root / "nn-config.yaml"
    if not p.is_file():
        return ""
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return str(data.get("profile", "")).strip()


def _parse_block(text: str) -> dict[str, str]:
    """解析 D2 块；按行剥除行尾 ``# …`` 注释（不剥引号内 #；本块语义简单不引）。"""
    start = text.find(_MARKER_START)
    if start < 0:
        return {}
    start += len(_MARKER_START)
    end = text.find(_MARKER_END, start)
    body = text[start:end] if end >= 0 else text[start:]
    out: dict[str, str] = {}
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        # 剥行尾 # 注释（fix 07：模板 D2 字段行尾带 "# xxx" 会污染 value）
        if " #" in val:
            val = val.split(" #", 1)[0].rstrip()
        if "  #" in val:
            val = val.split("  #", 1)[0].rstrip()
        if "	#" in val:
            val = val.split("	#", 1)[0].rstrip()
        if key:
            out[key] = val
    return out


def _semantic_checks(profile: str, fields: dict[str, str]) -> list[str]:
    errs: list[str] = []
    keep = fields.get("E3_EVAL_FOR_KEEP", "")
    if profile in ("supervised", "physical") and "contract.test" not in keep.replace(" ", ""):
        errs.append("E3_EVAL_FOR_KEEP 须写明台账仅 contract.test（勿用 ws.evaluate 做 KEEP）")

    vtsd = fields.get("VAL_TEST_SAME_DISTRIBUTION", "").lower()
    if profile == "supervised":
        if vtsd not in ("yes", "no", "na"):
            errs.append("VAL_TEST_SAME_DISTRIBUTION 须为 yes / no / na")
        sk = fields.get("SPLIT_KIND", "")
        if sk and sk not in _SPLIT_KIND_SUPERVISED:
            errs.append(
                f"SPLIT_KIND={sk!r} 未知；建议 train_val_test | train_holdout_no_val | "
                "train_val_holdout_test | custom",
            )
    if profile == "rl":
        ncs = fields.get("NO_CLASSIC_SPLIT", "").lower()
        if ncs not in ("yes", "true", "1"):
            errs.append("RL 须 NO_CLASSIC_SPLIT: yes（无经典 train/val/test 划分）")
        sk = fields.get("SPLIT_KIND", "").lower()
        if sk and sk not in ("none", "no_split", "rl_benchmark"):
            errs.append("RL 建议 SPLIT_KIND: none 或 rl_benchmark")
    if profile == "physical":
        ts = fields.get("TRAIN_SAMPLING", "").strip()
        if ts and _TRAIN_SAMPLING_FUNC_ONLY.match(ts):
            errs.append(
                "TRAIN_SAMPLING 禁止仅写函数调用（如 importance_sample(...)）；"
                "须写语义句，见 SKILL「physical D2 问话包」",
            )
        elif ts and not any(h in ts for h in _TRAIN_SAMPLING_SEMANTIC_HINTS):
            errs.append(
                "TRAIN_SAMPLING 须说明划分语义（建议含：语义/配点/实时/无固定 train 等），"
                "勿把采样实现当数据契约",
            )
        tunable = fields.get("SAMPLING_TUNABLE", "").lower()
        if tunable not in ("yes", "true", "1"):
            errs.append(
                "physical 须 SAMPLING_TUNABLE: yes（配点策略在 workspace 可调，不视为改 D2）",
            )
        vtsd = fields.get("VAL_TEST_SAME_DISTRIBUTION", "").lower()
        if vtsd not in ("na", "n/a", "none", ""):
            if vtsd not in ("yes", "no"):
                errs.append("physical 建议 VAL_TEST_SAME_DISTRIBUTION: na")
    return errs


def check(repo_root: str | Path) -> list[dict[str, str]]:
    root = Path(repo_root).resolve()
    readme = root / "README.md"
    if not readme.is_file():
        return [{"rule": "D2", "detail": "缺少 README.md", "fix": "创建 README 并写入 D2_DATA_SPLIT 块"}]

    profile = _load_profile(root)
    if not profile:
        return [{"rule": "D2", "detail": "无法从 nn-config.yaml 读取 profile", "fix": "修复 nn-config.yaml"}]

    fields = _parse_block(readme.read_text(encoding="utf-8"))
    if not fields:
        return [{
            "rule": "D2",
            "detail": f"README 缺少 {_MARKER_START} … {_MARKER_END} 数据划分块",
            "fix": "按 skills/maintainer/auto-nn-template-migration/SKILL.md「D2 数据划分确认表」写入 README",
        }]

    violations: list[dict[str, str]] = []
    # PROFILE 空：模板占位 / init 还没填 → 跳过校验（不让占位文被字面比较触发误报）
    # 真正值不匹配时仍然 FAIL
    profile_val = fields.get("PROFILE", "").strip()
    if profile_val and profile_val != profile:
        violations.append({
            "rule": "D2",
            "detail": f"块内 PROFILE={profile_val!r} 与 nn-config.yaml profile={profile!r} 不一致",
            "fix": "对齐 PROFILE 或改 nn-config.yaml",
        })

    for key in _REQUIRED.get(profile, ()):
        if not fields.get(key, "").strip():
            violations.append({
                "rule": "D2",
                "detail": f"缺少或为空: {key}（profile={profile}）",
                "fix": "补全 README 中 D2_DATA_SPLIT 块",
            })

    for msg in _semantic_checks(profile, fields):
        violations.append({"rule": "D2", "detail": msg, "fix": "修正 D2_DATA_SPLIT 块或与用户重新确认 D2"})

    for msg in _check_data_root_prefix(fields):
        violations.append({
            "rule": "D2",
            "detail": msg,
            "fix": "将数据迁至 data/ 下并改写 DATA_ROOT；symlink 可选，须在 data/README.md 说明",
        })

    return violations


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    v = check(root)
    if not v:
        return 0
    for item in v:
        print(f"[{item['rule']}] {item['detail']} → {item['fix']}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
