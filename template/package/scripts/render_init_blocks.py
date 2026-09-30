#!/usr/bin/env python3
"""render_init_blocks.py — 把 resolved lock 渲染成产物形态（headless 立项的落位层）。

口径层（init_answers → resolved.json）只存 lock 文本；本脚本做「resolved → 产物」：
  1. README 配置块：D2_DATA_SPLIT / SCENARIO_POLICY / AGENT_BOUNDARY（F2）+ 场景清单表
  2. saved/baseline_start_intent.json：O3.PLAIN / O3.REFERENCE → 起步尺子 intent（F1）

通用约定（与领域无关，steer 不含业务内容）：
  - 答卷 lock 文本里的 ``KEY=VALUE`` 对（``;`` 分隔）按已知键名映射进 README 块；
  - ``D2.SPLIT=TRAIN…/VAL…/TEST…`` 分段映射 TRAIN/VAL/TEST 行；
  - ``NORM=fitX`` → NORMALIZE_FIT_ON: X；
  - ``SCENARIO_IDS=id[:角色],…`` → 「### 场景清单」markdown 表（F1 唯一权威；
    当前目标列由 E1.PRIMARY + 机读题目标值合成，缺则留空）。
  未覆盖的键保持模板原样——门禁该报还报，不代答（诚实原则）。
  results.tsv 表头不由本脚本写：唯一事实源是 contract（regen_results_tsv.py 派生）。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# README 块标记（与 d2_data_split_gate / scenario_policy_gate 对齐）
_BLOCKS: dict[str, tuple[str, str]] = {
    "D2_DATA_SPLIT": ("<!-- D2_DATA_SPLIT -->", "<!-- /D2_DATA_SPLIT -->"),
    "SCENARIO_POLICY": ("<!-- SCENARIO_POLICY -->", "<!-- /SCENARIO_POLICY -->"),
    "AGENT_BOUNDARY": ("<!-- AGENT_BOUNDARY -->", "<!-- /AGENT_BOUNDARY -->"),
}

# AGENT_BOUNDARY 框架标准四键（每个项目同值，属框架约定非领域内容）
_AGENT_BOUNDARY_LINES = [
    "CONTRACT_IMMUTABLE: contract/    # 不可改；核改须 NN_RELAUNCH=1 或走 Modify 轨",
    "WORKSPACE_MUTABLE: workspace/    # 会话/训练可改",
    "ENV_OVERRIDES_OK: NN_DEVICE      # 会话可改环境变量白名单",
    "REFERENCE_ONLY: references/      # 只读参考区（含 references/legacy）",
]

_D2_SPLIT_RE = re.compile(r"\bD2\.SPLIT=([^;]+)")
_SEG_RE = re.compile(r"^(TRAIN|VAL|TEST|GUARD)(.*)$")
_NORM_RE = re.compile(r"\bNORM=fit([A-Za-z0-9_]+)")
_SCEN_IDS_RE = re.compile(r"\bSCENARIO_IDS=([^;]+)")
_PRIMARY_RE = re.compile(r"\bE1\.PRIMARY=([A-Za-z0-9_]+)\((max|min)\)")
_PLAIN_RE = re.compile(r"\bO3\.PLAIN=")
_REFERENCE_RE = re.compile(r"\bO3\.REFERENCE=")
_DEFAULT_RE = re.compile(r"\bDEFAULT=([^;]+)")


def _kv(lock: str, key: str) -> str:
    """lock 文本里取 ``KEY=VALUE``（分号截断）；无则空串。"""
    m = re.search(rf"\b{re.escape(key)}=([^;]+)", lock)
    return m.group(1).strip() if m else ""


def _load_locks(resolved_path: Path) -> dict[str, str]:
    """resolved.json → {slug: lock 文本}（freeform 题的 fields.lock）。"""
    return _load_resolved(resolved_path)[0]


def _load_resolved(resolved_path: Path) -> tuple[dict[str, str], dict[str, dict]]:
    """resolved.json → (locks, machine)。locks=freeform lock 文本；machine=机读题 fields。"""
    data = json.loads(resolved_path.read_text(encoding="utf-8"))
    resolved = data.get("resolved") or {}
    locks: dict[str, str] = {}
    machine: dict[str, dict] = {}
    for slug, item in resolved.items():
        fields = (item or {}).get("fields", {}) or {}
        if fields.get("lock"):
            locks[str(slug)] = str(fields["lock"])
        machine[str(slug)] = {k: v for k, v in fields.items() if k != "lock"}
    return locks, machine


def _d2_fields(lock: str) -> dict[str, str]:
    """D2 lock → README D2 块字段（只产有把握的键，缺的留给模板/门禁）。"""
    out: dict[str, str] = {}
    for key in ("DATA_ROOT", "SPLIT_KIND", "EVAL_USES", "TEST_USES",
                "E3_EVAL_FOR_KEEP", "VAL_TEST_SAME_DISTRIBUTION"):
        v = _kv(lock, key)
        if v:
            out[key] = v
    if not out.get("SPLIT_KIND"):
        m = _D2_SPLIT_RE.search(lock)
        if m and all(f"{seg}" in m.group(1) for seg in ("TRAIN", "VAL", "TEST")):
            out["SPLIT_KIND"] = "train_val_test"  # 由声明的划分形状推导
    if not out.get("DATA_ROOT"):
        out["DATA_ROOT"] = "data/"  # 框架默认挂载点（答卷声明可覆盖）
    m = _NORM_RE.search(lock)
    if m:
        out["NORMALIZE_FIT_ON"] = m.group(1)
    m = _D2_SPLIT_RE.search(lock)
    if m:
        for seg in m.group(1).split("/"):
            sm = _SEG_RE.match(seg.strip())
            if sm and sm.group(1) != "GUARD":
                out[sm.group(1)] = seg.strip()
    return out


def _scenario_fields(locks: dict[str, str]) -> dict[str, str]:
    """D1/E6 lock → SCENARIO_POLICY 块字段。"""
    d1 = locks.get("D1-scenario-inventory", "")
    out: dict[str, str] = {}
    for key in ("SCENARIO_AXIS", "SCENARIO_POLICY"):
        for lock in (d1, locks.get("E6-scenario", "")):
            v = _kv(lock, key)
            if v:
                out[key] = v
                break
    # ACTIVE_SCENARIOS 必须是场景 ID（readme_consistency R3 与 F1 场景清单对账）：
    # 优先 SCENARIO_IDS= 的 ID 列；无则退回 SCENARIOS= 简写（该形态过不了 R3，交迁移向导）
    m = _SCEN_IDS_RE.search(d1)
    if m:
        ids = ",".join(
            item.strip().partition(":")[0].strip()
            for item in m.group(1).split(",") if item.strip()
        )
        if ids:
            out["ACTIVE_SCENARIOS"] = ids
    else:
        m = re.search(r"\bSCENARIOS=([^;]+)", d1)
        if m:
            out["ACTIVE_SCENARIOS"] = m.group(1).strip()
    m = _DEFAULT_RE.search(d1)
    if m:
        out["DEFAULT_SCENARIO"] = m.group(1).strip()
    return out


def _render_block(text: str, start: str, end: str, fields: dict[str, str],
                  *, replace_all: bool = False) -> str:
    """替换标记块内已知键的值；块内没有的键追加到块尾；其余行原样保留。"""
    s = text.find(start)
    if s < 0:
        return text  # 模板无此块（如 full_copy 老仓）：不注入，交由门禁/迁移向导提示
    e = text.find(end, s + len(start))
    if e < 0:
        return text
    body = text[s + len(start):e]
    lines = body.splitlines()
    done: set[str] = set()
    out: list[str] = []
    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("<!--") or not stripped or ":" not in stripped:
            out.append(line)
            continue
        key = stripped.split(":", 1)[0].strip()
        if not replace_all and key in fields:
            out.append(f"{key}: {fields[key]}")
            done.add(key)
        else:
            out.append(line)
    if replace_all:
        out = list(fields.values())
    else:
        pending = [f"{k}: {v}" for k, v in fields.items() if k not in done]
        if pending:
            while out and not out[-1].strip():
                out.pop()
            out += pending
    return text[: s + len(start)] + "\n" + "\n".join(out) + "\n" + text[e:]


def render_readme(repo_root: Path, locks: dict[str, str]) -> list[str]:
    readme = repo_root / "README.md"
    if not readme.is_file():
        return ["README.md 缺失，跳过渲染"]
    text = readme.read_text(encoding="utf-8")
    notes: list[str] = []
    s, e = _BLOCKS["D2_DATA_SPLIT"]
    text = _render_block(text, s, e, _d2_fields(locks.get("D2-data-split", "")))
    s, e = _BLOCKS["SCENARIO_POLICY"]
    text = _render_block(text, s, e, _scenario_fields(locks))
    s, e = _BLOCKS["AGENT_BOUNDARY"]
    text = _render_block(text, s, e,
                         {"BOUNDARY": "\n".join(_AGENT_BOUNDARY_LINES)},
                         replace_all=True)
    readme.write_text(text, encoding="utf-8")
    notes.append(f"README 配置块已按 resolved 渲染（{readme}）")
    return notes


def render_scenario_table(repo_root: Path, locks: dict[str, str],
                          machine: dict[str, dict]) -> list[str]:
    """D1 lock 的 ``SCENARIO_IDS=id[:角色],…`` → 「### 场景清单」markdown 表（F1）。

    表紧跟 SCENARIO_POLICY 块后插入（无该块则不动——老仓交迁移向导）；
    当前目标列由 E1.PRIMARY=name(dir) 与机读题 G2 目标值合成（框架通用语法，
    领域词全部来自答卷）；无机读目标值则留空。已渲染过（含标题）不重复插。
    """
    text = repo_root / "README.md"
    if not text.is_file():
        return []
    raw = text.read_text(encoding="utf-8")
    m = _SCEN_IDS_RE.search(locks.get("D1-scenario-inventory", ""))
    if not m:
        return []  # 答卷未给机读清单：不代答，scenario_completeness 门禁该报还报
    if "### 场景清单" in raw:
        return []  # 已有清单（重跑幂等）
    rows: list[tuple[str, str]] = []
    for item in m.group(1).split(","):
        item = item.strip()
        if not item:
            continue
        sid, _, role = item.partition(":")
        rows.append((sid.strip(), role.strip()))
    if not rows:
        return []
    e1 = _PRIMARY_RE.search(locks.get("E1-metrics", ""))
    g2 = machine.get("G2-goal-value", {}).get("value")
    goal_cell = ""
    if e1 and isinstance(g2, (int, float)):
        op = "≥" if e1.group(2) == "max" else "≤"
        goal_cell = f"{e1.group(1)} {op} {g2}"
    lines = ["", "### 场景清单", "", "| 场景 ID | 角色 | 当前目标 |", "| --- | --- | --- |"]
    lines += [f"| {sid} | {role} | {goal_cell} |" for sid, role in rows]
    lines.append("")
    s = raw.find(_BLOCKS["SCENARIO_POLICY"][1])
    if s < 0:
        return ["警告: README 无 SCENARIO_POLICY 块，场景清单表未插入（交迁移向导）"]
    e = s + len(_BLOCKS["SCENARIO_POLICY"][1])
    text.write_text(raw[:e] + "\n".join(lines) + raw[e:], encoding="utf-8")
    return [f"场景清单表已渲染（{len(rows)} 个场景，F1 权威）"]


def render_nn_config(repo_root: Path, locks: dict[str, str],
                     machine: dict[str, dict]) -> list[str]:
    """机读题 → nn-config.yaml 对齐（发现⑨：scaffold 只 sed profile/gpus，答卷全不落盘）。

    G2.value→goal.target；E1.PRIMARY 名→goal.metric（op 留空按合同方向）；
    O1.seconds→time_budget；O2→gpus/max_parallel；O4.seed→seed；
    D1.DEFAULT→agent.scenario_default。写路径走 lib/nn_config（唯一权威）；
    缺哪项就不写哪项——不代答。
    """
    path = repo_root / "nn-config.yaml"
    if not path.is_file():
        return ["警告: nn-config.yaml 缺失，机读题对齐跳过"]
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from lib.nn_config import load_nn_config, save_nn_config  # noqa: WPS433
    except ImportError as exc:
        return [f"警告: lib/nn_config 不可用（{exc}），机读题对齐跳过"]
    cfg = load_nn_config(repo_root)
    goal = cfg.setdefault("goal", {})
    agent = cfg.setdefault("agent", {})
    done: list[str] = []
    g2 = machine.get("G2-goal-value", {}).get("value")
    if isinstance(g2, (int, float)):
        goal["target"] = g2
        done.append("goal.target")
    e1 = _PRIMARY_RE.search(locks.get("E1-metrics", ""))
    if e1:
        goal["metric"] = e1.group(1)
        done.append("goal.metric")
    o1 = machine.get("O1-time-budget", {}).get("seconds")
    if isinstance(o1, (int, float)) and o1 > 0:
        cfg["time_budget"] = int(o1)
        done.append("time_budget")
    o2 = machine.get("O2-gpus-parallel", {})
    if isinstance(o2.get("gpus"), list) and o2["gpus"]:
        cfg["gpus"] = o2["gpus"]
        done.append("gpus")
    mp = o2.get("max_parallel")
    if isinstance(mp, (int, float)) and mp > 0:
        cfg["max_parallel"] = int(mp)
        done.append("max_parallel")
    o4 = machine.get("O4-repro-determinism", {}).get("seed")
    if isinstance(o4, (int, float)):
        cfg["seed"] = int(o4)
        done.append("seed")
    default = _DEFAULT_RE.search(locks.get("D1-scenario-inventory", ""))
    if default:
        agent["scenario_default"] = default.group(1).strip()
        done.append("agent.scenario_default")
    if not done:
        return ["机读题对齐：无可落盘字段（答卷无机读答案），跳过"]
    save_nn_config(repo_root, cfg)
    return [f"nn-config 已按机读题对齐: {', '.join(done)}"]


def write_intent(repo_root: Path, locks: dict[str, str]) -> list[str]:
    """O3 lock 有 PLAIN/REFERENCE → 落盘起步尺子 intent；都无 → 写 skipped 标记（F1）。

    start_runs 取值：plain / reference / plain+reference（读侧
    _intent_wants_plain 与 _intent_wants_reference_run 均按子串判定，
    与既有 intent schema（reference_run/reference_method）对齐。
    """
    here = Path(__file__).resolve().parent
    o3 = locks.get("O3-baseline-anchors", "")
    marker = repo_root / ".auto-nn" / "baseline-intent-skipped"
    if not o3:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("resolved 无 O3-baseline-anchors；无起步尺子可落盘\n", encoding="utf-8")
        return ["无 O3 lock：已写 .auto-nn/baseline-intent-skipped"]
    wants_plain = bool(_PLAIN_RE.search(o3))
    wants_ref = bool(_REFERENCE_RE.search(o3))
    if not wants_plain and not wants_ref:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(f"O3 lock 无 PLAIN/REFERENCE 起步尺子声明：{o3}\n", encoding="utf-8")
        return ["O3 无 PLAIN/REFERENCE 声明：已写 .auto-nn/baseline-intent-skipped"]
    scenario_id = _DEFAULT_RE.search(locks.get("D1-scenario-inventory", ""))
    if wants_plain and wants_ref:
        start_runs = "plain+reference"
    else:
        start_runs = "plain" if wants_plain else "reference"
    intent: dict = {
        "schema_version": 1,
        "start_runs": start_runs,
        "scenario_id": scenario_id.group(1).strip() if scenario_id else None,
    }
    # plain_recipe / reference_method 是 build-run-context FIRST-ROUND 提示的
    # hint 来源；取 O3 键的值（答卷声明，领域词在值里），缺则不带
    m = re.search(r"\bO3\.PLAIN=([^;]+)", o3)
    if m:
        intent["plain_recipe"] = m.group(1).strip()
    m = re.search(r"\bO3\.REFERENCE=([^;]+)", o3)
    if m:
        intent["reference_run"] = True
        intent["reference_method"] = m.group(1).strip()
    payload = json.dumps(intent, ensure_ascii=False)
    proc = subprocess.run(
        ["python3", str(here / "write_baseline_start_intent.py"),
         "--repo-root", str(repo_root), "--json", payload, "--force"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return [f"警告: intent 落盘失败: {proc.stderr.strip()}"]
    return [f"起步尺子 intent 已落盘: {proc.stdout.strip()}"]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repo-root", required=True)
    p.add_argument("--resolved", required=True, help="init-answers.resolved.json")
    p.add_argument("--skip-intent", action="store_true", help="跳过起步尺子落盘")
    a = p.parse_args()
    repo_root = Path(a.repo_root)
    locks, machine = _load_resolved(Path(a.resolved))
    notes: list[str] = []
    notes += render_readme(repo_root, locks)
    notes += render_scenario_table(repo_root, locks, machine)
    notes += render_nn_config(repo_root, locks, machine)
    if not a.skip_intent:
        notes += write_intent(repo_root, locks)
    for n in notes:
        print(f"=== {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
