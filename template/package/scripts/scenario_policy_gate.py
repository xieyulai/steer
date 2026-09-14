#!/usr/bin/env python3
"""场景策略门禁：README SCENARIO_POLICY / AGENT_BOUNDARY 块（二期）。

迁后 / verify 硬检（业务仓）；模板根跳过。
触发：D2 中 EVAL_SCENARIO 非 default/na/空，或 SCENARIO_POLICY 块内 SCENARIO_AXIS 非 na。
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

_MARKER_D2_START = "<!-- D2_DATA_SPLIT -->"
_MARKER_D2_END = "<!-- /D2_DATA_SPLIT -->"
_MARKER_SCENARIO_START = "<!-- SCENARIO_POLICY -->"
_MARKER_SCENARIO_END = "<!-- /SCENARIO_POLICY -->"
_MARKER_BOUNDARY_START = "<!-- AGENT_BOUNDARY -->"
_MARKER_BOUNDARY_END = "<!-- /AGENT_BOUNDARY -->"

_SCENARIO_REQUIRED = (
    "SCENARIO_AXIS",
    "ACTIVE_SCENARIOS",
    "SCENARIO_POLICY",
    "DEFAULT_SCENARIO",
    "KEEP_HISTORY_FILTER",
    "TRAIN_BINDS",
)
_SCENARIO_POLICIES = frozenset({"focus", "rotate", "multi_eval_one_train"})
_BOUNDARY_REQUIRED = (
    "CONTRACT_IMMUTABLE",
    "WORKSPACE_MUTABLE",
    "ENV_OVERRIDES_OK",
    "REFERENCE_ONLY",
)
_NA_VALUES = frozenset({"", "none", "na", "default"})


def _load_profile(repo_root: Path) -> str:
    p = repo_root / "nn-config.yaml"
    if not p.is_file():
        return ""
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return str(data.get("profile", "")).strip()


def _parse_block(text: str, start_marker: str, end_marker: str) -> dict[str, str]:
    start = text.find(start_marker)
    if start < 0:
        return {}
    start += len(start_marker)
    end = text.find(end_marker, start)
    body = text[start:end] if end >= 0 else text[start:]
    out: dict[str, str] = {}
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        if key:
            out[key] = val
    return out


def _axis_is_active(axis: str) -> bool:
    return axis.strip().lower() not in _NA_VALUES


def _needs_scenario_block(fields_d2: dict[str, str], scenario_fields: dict[str, str]) -> bool:
    if scenario_fields:
        axis = scenario_fields.get("SCENARIO_AXIS", "").strip()
        if axis and _axis_is_active(axis):
            return True
    eval_scenario = fields_d2.get("EVAL_SCENARIO", "").strip()
    return bool(eval_scenario) and _axis_is_active(eval_scenario)


def check(repo_root: str | Path) -> list[dict[str, str]]:
    root = Path(repo_root).resolve()
    readme = root / "README.md"
    if not readme.is_file():
        return [{"rule": "SCENARIO", "detail": "缺少 README.md", "fix": "创建 README"}]

    text = readme.read_text(encoding="utf-8")
    fields_d2 = _parse_block(text, _MARKER_D2_START, _MARKER_D2_END)
    scenario_fields = _parse_block(text, _MARKER_SCENARIO_START, _MARKER_SCENARIO_END)
    boundary_fields = _parse_block(text, _MARKER_BOUNDARY_START, _MARKER_BOUNDARY_END)

    violations: list[dict[str, str]] = []

    if _MARKER_BOUNDARY_START in text:
        for key in _BOUNDARY_REQUIRED:
            if not boundary_fields.get(key, "").strip():
                violations.append({
                    "rule": "SCENARIO",
                    "detail": f"AGENT_BOUNDARY 缺少或为空: {key}",
                    "fix": "补全 README 中 AGENT_BOUNDARY 块",
                })

    if not _needs_scenario_block(fields_d2, scenario_fields):
        return violations

    if not scenario_fields:
        violations.append({
            "rule": "SCENARIO",
            "detail": "已声明场景轴（D2 EVAL_SCENARIO 或需多场景策略）但缺少 SCENARIO_POLICY 块",
            "fix": f"在 README 增加 {_MARKER_SCENARIO_START} … {_MARKER_SCENARIO_END}",
        })
        return violations

    for key in _SCENARIO_REQUIRED:
        if key not in scenario_fields:
            violations.append({
                "rule": "SCENARIO",
                "detail": f"SCENARIO_POLICY 缺少键: {key}",
                "fix": "补全 SCENARIO_POLICY 块",
            })
        elif not scenario_fields.get(key, "").strip() and key != "KEEP_HISTORY_FILTER":
            violations.append({
                "rule": "SCENARIO",
                "detail": f"SCENARIO_POLICY 键为空: {key}",
                "fix": "填写该键（KEEP_HISTORY_FILTER 无 substr 时可留空）",
            })

    policy = scenario_fields.get("SCENARIO_POLICY", "").strip().lower()
    if policy and policy not in _SCENARIO_POLICIES:
        violations.append({
            "rule": "SCENARIO",
            "detail": f"SCENARIO_POLICY={policy!r} 无效；须 focus | rotate | multi_eval_one_train",
            "fix": "修正 SCENARIO_POLICY",
        })

    train_binds = scenario_fields.get("TRAIN_BINDS", "").strip().lower()
    if train_binds and train_binds not in ("single", "multi"):
        violations.append({
            "rule": "SCENARIO",
            "detail": f"TRAIN_BINDS={train_binds!r} 须为 single 或 multi",
            "fix": "修正 TRAIN_BINDS",
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
