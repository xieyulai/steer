#!/usr/bin/env python3
"""README 块与 contract / nn-config / F1 清单语义对账（R1–R4）。

迁后 modify **Modify-L/Scenario-*** 收尾可用 ``--strict``；nn-doctor 默认 WARN 级。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from d2_data_split_gate import (  # noqa: E402
    _MARKER_END as D2_END,
    _MARKER_START as D2_START,
    _data_root_path,
    _load_profile,
    _parse_block as _parse_d2_block,
)
from scenario_policy_gate import (  # noqa: E402
    _MARKER_SCENARIO_END,
    _MARKER_SCENARIO_START,
    _NA_VALUES,
    _parse_block as _parse_marked_block,
    _axis_is_active,
)

_MARKER_METRICS_START = "<!-- METRICS_SNAPSHOT -->"
_MARKER_METRICS_END = "<!-- /METRICS_SNAPSHOT -->"

_DIR_MAX = "maximize"
_DIR_MIN = "minimize"
_SNAPSHOT_TO_CONTRACT = {"higher": _DIR_MAX, "lower": _DIR_MIN, "maximize": _DIR_MAX, "minimize": _DIR_MIN}


@dataclass
class Violation:
    rule: str
    severity: str  # FAIL | WARN
    detail: str
    fix: str

    def to_dict(self) -> dict[str, str]:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "detail": self.detail,
            "fix": self.fix,
        }


def _is_template_package_root(root: Path) -> bool:
    maintainer = root.parent.parent / ".template-maintainer"
    return maintainer.is_file() and (root / "experiment.py").is_file()


def _repo_relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def _parse_metrics_snapshot(text: str) -> dict[str, str]:
    start = text.find(_MARKER_METRICS_START)
    if start < 0:
        return {}
    start += len(_MARKER_METRICS_START)
    end = text.find(_MARKER_METRICS_END, start)
    body = text[start:end] if end >= 0 else text[start:]
    out: dict[str, str] = {}
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip().lower()
        if key:
            out[key] = val
    return out


def _parse_active_scenarios(raw: str) -> list[str]:
    raw = raw.strip()
    if not raw or raw.lower() in _NA_VALUES:
        return []
    parts = re.split(r"[,;\s]+", raw)
    return [p.strip() for p in parts if p.strip() and p.strip().lower() not in _NA_VALUES]


def _import_module_from_path(module_path: Path, qualname: str):
    import importlib.util, sys

    spec = importlib.util.spec_from_file_location(qualname, module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 {module_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[qualname] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_contract_metric_keys(root: Path) -> tuple[dict[str, str], dict[str, str]]:
    metrics_path = (root / "contract" / "metrics.py").resolve()
    if not metrics_path.is_file():
        raise ImportError(f"缺少 {metrics_path}")
    mod = _import_module_from_path(metrics_path, f"_readme_gate_metrics_{metrics_path.stat().st_ino}")
    return dict(mod.METRIC_KEYS), dict(mod.AUXILIARY_KEYS)


def _contract_data_dir(root: Path) -> str:
    root = root.resolve()
    exp_path = root / "experiment.py"
    init_path = root / "contract" / "__init__.py"
    if not init_path.is_file():
        raise ImportError("缺少 contract/__init__.py")
    # 隔离加载，避免 unittest 套件中其它用例污染 sys.modules['contract']
    exp_mod = _import_module_from_path(exp_path, f"_readme_gate_exp_{root.stat().st_ino}") if exp_path.is_file() else None
    metrics_mod = _import_module_from_path(
        root / "contract" / "metrics.py",
        f"_readme_gate_metrics2_{root.stat().st_ino}",
    )
    ns: dict[str, object] = {"__file__": str(init_path)}
    if exp_mod is not None:
        ns["ExperimentBase"] = exp_mod.ExperimentBase
    ns["METRIC_KEYS"] = metrics_mod.METRIC_KEYS
    # Ensure project root is on sys.path so `from contract import ...` resolves
    import sys as _sys
    _root_str = str(root)
    _added = False
    if _root_str not in _sys.path:
        _sys.path.insert(0, _root_str)
        _added = True
    try:
        exec(init_path.read_text(encoding="utf-8"), ns)  # noqa: S102
    finally:
        if _added:
            _sys.path.remove(_root_str)
    create = ns.get("create_contract")
    if not callable(create):
        raise ImportError("contract 无 create_contract")
    c = create({})
    return str(getattr(c, "data_dir", ""))


def _data_dirs_equivalent(d2_path: str, contract_dir: str, root: Path) -> bool:
    """D2 相对 data/ 路径与 contract.data_dir 等价（含迁后绝对路径后缀）。"""
    d2 = d2_path.strip().rstrip("/")
    if not d2:
        return True
    c_raw = contract_dir.strip().rstrip("/")
    if not c_raw:
        return False
    if d2 == c_raw:
        return True
    try:
        c_rel = _repo_relative(Path(c_raw).expanduser(), root).rstrip("/")
    except ValueError:
        c_rel = c_raw
    if d2 == c_rel:
        return True
    try:
        d2_res = (root / d2).resolve()
        c_res = Path(c_raw).expanduser().resolve()
        if d2_res == c_res:
            return True
    except OSError:
        pass
    c_norm = c_raw.replace("\\", "/").rstrip("/")
    d2_norm = d2.replace("\\", "/").rstrip("/")
    return c_norm.endswith(d2_norm) or c_norm.endswith(d2_norm.removeprefix("data/"))


def check(repo_root: str | Path, *, strict: bool = False) -> list[Violation]:
    root = Path(repo_root).resolve()
    if _is_template_package_root(root):
        return []

    readme = root / "README.md"
    if not readme.is_file():
        return [
            Violation("README", "FAIL", "缺少 README.md", "创建 README.md"),
        ]

    text = readme.read_text(encoding="utf-8")
    profile = _load_profile(root)
    d2 = _parse_d2_block(text) if D2_START in text else {}
    scenario = (
        _parse_marked_block(text, _MARKER_SCENARIO_START, _MARKER_SCENARIO_END)
        if _MARKER_SCENARIO_START in text
        else {}
    )
    metrics_snap = _parse_metrics_snapshot(text)

    violations: list[Violation] = []

    def add(rule: str, severity: str, detail: str, fix: str) -> None:
        sev = "FAIL" if strict and severity == "WARN" else severity
        violations.append(Violation(rule, sev, detail, fix))

    # R1 / R2 — 需要 D2 块
    if d2 and profile:
        d2_profile = d2.get("PROFILE", "").strip()
        if d2_profile and d2_profile != profile:
            add(
                "R1",
                "FAIL",
                f"D2 PROFILE={d2_profile!r} != nn-config profile={profile!r}",
                "对齐 README D2 PROFILE 与 nn-config.yaml",
            )
        data_root_raw = d2.get("DATA_ROOT", "").strip()
        if data_root_raw:
            d2_path = _data_root_path(data_root_raw)
            try:
                contract_dir = _contract_data_dir(root)
                c_rel = _repo_relative(Path(contract_dir).expanduser(), root)
                if not _data_dirs_equivalent(d2_path, contract_dir, root):
                    add(
                        "R2",
                        "FAIL",
                        f"D2 DATA_ROOT 路径 {d2_path!r} != contract.data_dir {c_rel!r}",
                        "对齐 D2 DATA_ROOT 与 contract 默认数据根",
                    )
            except Exception as exc:  # pragma: no cover
                add("R2", "WARN", f"无法读取 contract.data_dir: {exc}", "检查 contract 可导入")

    axis = scenario.get("SCENARIO_AXIS", "").strip()
    scenario_active = _axis_is_active(axis)

    # R3
    if scenario_active and scenario:
        try:
            from lib.scenario_inventory import load_scenario_ids  # noqa: WPS433

            f1_ids = set(load_scenario_ids(root))
        except Exception as exc:  # pragma: no cover
            add("R3", "WARN", f"无法加载 F1 场景清单: {exc}", "检查 README SCENARIO_POLICY 场景清单表")
            f1_ids = set()

        if f1_ids:
            active_raw = scenario.get("ACTIVE_SCENARIOS", "")
            active_ids = _parse_active_scenarios(active_raw)
            unknown = [sid for sid in active_ids if sid not in f1_ids]
            if unknown:
                add(
                    "R3",
                    "FAIL",
                    f"ACTIVE_SCENARIOS 含未登 F1 的 ID: {unknown}",
                    "更新 SCENARIO_POLICY 或 F1 场景清单",
                )

    # R4
    try:
        metric_keys, aux_keys = _load_contract_metric_keys(root)
    except Exception as exc:  # pragma: no cover
        add("R4", "WARN", f"无法加载 contract.metrics: {exc}", "检查 contract/")
        metric_keys, aux_keys = {}, {}

    if metric_keys:
        if not metrics_snap:
            add(
                "R4",
                "WARN",
                "缺少 METRICS_SNAPSHOT 块（contract 有 METRIC_KEYS）",
                "在 README 增加 <!-- METRICS_SNAPSHOT --> 并与 metric_keys 同步",
            )
        else:
            snap_keys = set(metrics_snap)
            contract_keys = set(metric_keys)
            missing = contract_keys - snap_keys
            extra = snap_keys - contract_keys - set(aux_keys)
            if missing:
                add(
                    "R4",
                    "FAIL",
                    f"METRICS_SNAPSHOT 缺少键: {sorted(missing)}",
                    "补全 METRICS_SNAPSHOT 行",
                )
            if extra:
                add(
                    "R4",
                    "WARN",
                    f"METRICS_SNAPSHOT 多余键（不在 METRIC_KEYS）: {sorted(extra)}",
                    "删除多余行或改 contract",
                )
            for key, direction in metrics_snap.items():
                if key not in metric_keys:
                    continue
                expected = metric_keys[key]
                got = _SNAPSHOT_TO_CONTRACT.get(direction, direction)
                if got != expected:
                    add(
                        "R4",
                        "FAIL",
                        f"METRICS_SNAPSHOT {key}: {direction!r} != contract {expected!r}",
                        "改为 higher/lower 与 maximize/minimize 对应",
                    )

    # R5 — README 场景清单「目标值」列 vs nn-config goal（可选列；WARN）
    try:
        from lib.nn_config import load_nn_config
        from lib.run_ledger_summary import effective_goal
        from lib.scenario_inventory import load_readme_scenario_goal_hints

        hints = load_readme_scenario_goal_hints(root)
        if hints:
            cfg = load_nn_config(root)
            goal = cfg.get("goal") if isinstance(cfg.get("goal"), dict) else {}
            for sid, hint in hints.items():
                eff = effective_goal(goal, sid)
                hint_norm = hint.strip().lower()
                if hint_norm in ("", "（默认）", "default", "—", "-", "na"):
                    if eff is None and goal.get("target") is not None:
                        continue  # inherits global, OK
                    continue
                try:
                    hint_val = float(hint)
                except ValueError:
                    continue
                if eff is None or abs(eff - hint_val) > 1e-9:
                    add(
                        "R5",
                        "WARN",
                        f"场景 {sid!r} README 目标值 {hint!r} != nn-config effective {eff}",
                        "对齐 README 目标值列与 agent.goal_value/scenario_goals",
                    )
    except Exception as exc:  # pragma: no cover
        add("R5", "WARN", f"goal 列对账跳过: {exc}", "检查 scenario_inventory / nn-config")

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="README 与 contract/nn-config 语义对账")
    parser.add_argument("repo_root", nargs="?", default=".")
    parser.add_argument("--strict", action="store_true", help="WARN 视为 FAIL")
    parser.add_argument("--json", action="store_true", help="JSON 输出 violations")
    args = parser.parse_args()

    violations = check(args.repo_root, strict=args.strict)
    fails = [v for v in violations if v.severity == "FAIL"]

    if args.json:
        print(json.dumps([v.to_dict() for v in violations], ensure_ascii=False, indent=2))
    else:
        for v in violations:
            print(
                f"[{v.rule}/{v.severity}] {v.detail} → {v.fix}",
                file=sys.stderr,
            )

    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
