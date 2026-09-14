"""scenario_inventory：F1 清单与 scenario_id 解析。"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

SCENARIO_ID_COLUMN = "scenario_id"
_ENV_SCENARIO_ID = "NN_SCENARIO_ID"
_SECTION_KEYWORD = "场景清单"
_HEADER_FIRST_COL = re.compile(r"场景\s*ID", re.IGNORECASE)
_SEPARATOR_CELL = re.compile(r"^:?-+:?$")


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _dedupe_preserve_order(ids: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for sid in ids:
        if sid in seen:
            continue
        seen.add(sid)
        out.append(sid)
    return out


def _is_table_separator_row(cells: list[str]) -> bool:
    if not cells:
        return True
    for cell in cells:
        c = cell.strip().replace(" ", "")
        if c and not _SEPARATOR_CELL.match(c):
            return False
    return True


def _is_header_first_col(first: str) -> bool:
    return bool(_HEADER_FIRST_COL.search(first.strip()))


_GOAL_HEADER = re.compile(r"目标\s*值?|goal", re.IGNORECASE)


def _parse_inventory_table_rows(text: str) -> list[list[str]]:
    """场景清单表各行 cells（不含表头/分隔行）。"""
    lines = text.splitlines()
    rows: list[list[str]] = []
    in_section = False
    in_table = False

    for line in lines:
        heading = re.match(r"^(#+)\s+(.+)$", line.strip())
        if heading:
            title = heading.group(2)
            if _SECTION_KEYWORD in title:
                in_section = True
                in_table = False
                continue
            if in_section:
                break
            continue
        if not in_section:
            continue
        stripped = line.strip()
        if not stripped.startswith("|"):
            if in_table and rows:
                break
            in_table = False
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not cells or _is_table_separator_row(cells):
            in_table = True
            continue
        first = cells[0].strip()
        if not first or _is_header_first_col(first):
            in_table = True
            continue
        in_table = True
        rows.append(cells)
    return rows


def _parse_inventory_from_text(text: str) -> list[str]:
    """解析含「场景清单」标题下的 Markdown 表第一列。"""
    return _dedupe_preserve_order([r[0].strip() for r in _parse_inventory_table_rows(text) if r])


def load_readme_scenario_goal_hints(repo_root: Path) -> dict[str, str]:
    """README 场景清单「目标值」列（若有）；空/（默认）→ 键存在值为 ''。"""
    text = _read_text(Path(repo_root).resolve() / "README.md")
    lines = text.splitlines()
    in_section = False
    goal_col: int | None = None
    out: dict[str, str] = {}

    for line in lines:
        heading = re.match(r"^(#+)\s+(.+)$", line.strip())
        if heading:
            title = heading.group(2)
            if _SECTION_KEYWORD in title:
                in_section = True
                goal_col = None
                continue
            if in_section:
                break
            continue
        if not in_section or not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cells or _is_table_separator_row(cells):
            continue
        if _is_header_first_col(cells[0]):
            for i, cell in enumerate(cells):
                if _GOAL_HEADER.search(cell):
                    goal_col = i
            continue
        if goal_col is None or goal_col >= len(cells):
            continue
        sid = cells[0].strip()
        if sid:
            out[sid] = cells[goal_col].strip()
    return out


def load_scenario_ids(repo_root: Path) -> list[str]:
    """从 README.md 的「场景清单」表读取第一列 ID（去重保序；唯一权威）。"""
    root = Path(repo_root).resolve()
    readme = root / "README.md"
    return _parse_inventory_from_text(_read_text(readme))


def _load_nn_config(repo_root: Path) -> dict:
    """真源：``lib.nn_config.load_nn_config``（回填 + preset；坏文件 raise）。"""
    from lib.nn_config import load_nn_config

    return load_nn_config(Path(repo_root).resolve())


def _agent_scenario_default(repo_root: Path) -> str:
    agent = _load_nn_config(repo_root).get("agent")
    if not isinstance(agent, dict):
        return ""
    return str(agent.get("scenario_default", "") or "").strip()


def _env_get(env: dict[str, str] | os._Environ[str] | None, key: str) -> str:
    if env is None:
        return str(os.environ.get(key, "") or "").strip()
    return str(env.get(key, "") or "").strip()


def _load_agent_bindings(repo_root: Path, scenario_bindings: list[dict] | None = None) -> list[dict]:
    if scenario_bindings is not None:
        from lib.scenario_bindings import normalize_scenario_binding

        return [normalize_scenario_binding(x) for x in scenario_bindings]
    agent = _load_nn_config(repo_root).get("agent")
    if not isinstance(agent, dict):
        return []
    raw = agent.get("scenario_bindings")
    if not isinstance(raw, list) or not raw:
        return []
    from lib.scenario_bindings import normalize_scenario_binding

    return [normalize_scenario_binding(x) for x in raw]


def resolve_scenario_id(
    repo_root: Path,
    cfg: dict | None = None,
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
    scenario_bindings: list[dict] | None = None,
) -> tuple[str, str]:
    """返回 (scenario_id, source_key)。

    优先级：cfg scenario_id/SCENARIO_ID → scenario_bindings 推断 → agent.scenario_default。
    Config-Only: 不再支持 NN_SCENARIO_ID 环境变量。
    """
    root = Path(repo_root).resolve()
    cfg = cfg or {}

    sid = str(cfg.get("scenario_id", "") or "").strip()
    if sid:
        return sid, "cfg.scenario_id"

    sid = str(cfg.get("SCENARIO_ID", "") or "").strip()
    if sid:
        return sid, "cfg.SCENARIO_ID"

    bindings = _load_agent_bindings(root, scenario_bindings)
    if bindings:
        from lib.scenario_bindings import infer_scenario_id_from_bindings

        inventory = load_scenario_ids(root)
        active = load_scenario_active(root)
        candidates = [s for s in active if s in inventory] if active else inventory
        inferred = infer_scenario_id_from_bindings(candidates, bindings, cfg, env=env)
        if inferred:
            return inferred, "agent.scenario_bindings"

    sid = _agent_scenario_default(root)
    if sid:
        return sid, "agent.scenario_default"

    return "", ""


def validate_scenario_id(repo_root: Path, scenario_id: str) -> None:
    """不在清单则 raise ValueError。"""
    sid = (scenario_id or "").strip()
    if not sid:
        raise ValueError("scenario_id 为空")
    allowed = load_scenario_ids(repo_root)
    if sid not in allowed:
        raise ValueError(f"scenario_id {sid!r} 不在 F1 场景清单 {allowed!r}")


def focus_scenario_id(
    repo_root: Path,
    env: dict[str, str] | os._Environ[str] | None = None,
) -> str:
    """agent.scenario_default；皆空则清单首 ID。Config-Only：不读 NN_SCENARIO_ID。"""
    root = Path(repo_root).resolve()
    sid = _agent_scenario_default(root)
    if sid:
        return sid
    ids = load_scenario_ids(root)
    if ids:
        return ids[0]
    return ""


def load_scenario_active(repo_root: Path) -> list[str]:
    """nn-config.agent.scenario_active，逗号/分号分隔。"""
    agent = _load_nn_config(repo_root).get("agent")
    if not isinstance(agent, dict):
        return []
    raw = str(agent.get("scenario_active", "") or "").strip()
    if not raw:
        return []
    parts = re.split(r"[,;]+", raw)
    return _dedupe_preserve_order([p.strip() for p in parts if p.strip()])


def _read_tsv_rows(tsv_path: Path) -> tuple[list[str], list[list[str]]]:
    if not tsv_path.is_file():
        return [], []
    lines = [ln for ln in tsv_path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    if not lines:
        return [], []
    header = lines[0].split("\t")
    rows = [ln.split("\t") for ln in lines[1:]]
    return header, rows


def audit_scenario_completeness(repo_root: Path) -> list[dict[str, str]]:
    """场景完整性审计。每项含 level（fail|warn）、detail、fix。"""
    root = Path(repo_root).resolve()
    out: list[dict[str, str]] = []
    inventory = load_scenario_ids(root)
    inv_set = set(inventory)

    if not inventory:
        out.append({
            "level": "fail",
            "detail": "F1 场景清单为空（README SCENARIO_POLICY 无「场景清单」表）",
            "fix": "补 README SCENARIO_POLICY 场景清单或 /auto-nn-modify（Modify-Scenario-complete）",
        })
        return out

    default = _agent_scenario_default(root)
    if not default:
        out.append({
            "level": "fail",
            "detail": "nn-config.agent.scenario_default 未设置",
            "fix": f"设为清单 ID 之一，如 {inventory[0]!r}",
        })
    elif default not in inv_set:
        out.append({
            "level": "fail",
            "detail": f"scenario_default={default!r} 不在 F1 清单 {inventory!r}",
            "fix": "修正 nn-config.yaml agent.scenario_default",
        })

    for sid in load_scenario_active(root):
        if sid not in inv_set:
            out.append({
                "level": "fail",
                "detail": f"scenario_active 含未知 ID {sid!r}",
                "fix": "修正 agent.scenario_active 或更新 F1 清单",
            })

    tsv = root / "_runs" / "results.tsv"
    header, rows = _read_tsv_rows(tsv)
    ids_in_tsv: set[str] = set()
    if not tsv.is_file():
        out.append({
            "level": "warn",
            "detail": "缺少 _runs/results.tsv",
            "fix": "跑 smoke 或 manual-run 生成台账",
        })
    elif SCENARIO_ID_COLUMN not in header:
        out.append({
            "level": "fail",
            "detail": "results.tsv 缺 scenario_id 列",
            "fix": "bash scripts/backfill-scenario-tsv.sh --apply .",
        })
    else:
        sid_idx = header.index(SCENARIO_ID_COLUMN)
        exp_idx = header.index("experiment") if "experiment" in header else 0
        empty_rows: list[str] = []
        invalid_rows: list[str] = []
        for row in rows:
            exp = row[exp_idx] if exp_idx < len(row) else "?"
            sid = row[sid_idx].strip() if sid_idx < len(row) else ""
            if not sid:
                empty_rows.append(exp)
                continue
            if sid not in inv_set:
                invalid_rows.append(f"{exp}→{sid}")
            else:
                ids_in_tsv.add(sid)
        if empty_rows:
            sample = ", ".join(empty_rows[:3])
            more = f" 等{len(empty_rows)}行" if len(empty_rows) > 3 else ""
            out.append({
                "level": "fail",
                "detail": f"TSV 有 {len(empty_rows)} 行 scenario_id 为空（如 {sample}{more}）",
                "fix": "backfill --apply 或 /auto-nn-modify（Modify-Scenario-complete）",
            })
        if invalid_rows:
            sample = ", ".join(invalid_rows[:3])
            out.append({
                "level": "fail",
                "detail": f"TSV 有 scenario_id 不在清单（如 {sample}）",
                "fix": "修正 backfill 映射或 F1 清单",
            })

    keepers_path = root / "saved" / "keepers.json"
    legacy_path = root / "saved" / "keeper.json"
    if legacy_path.is_file() and not keepers_path.is_file():
        out.append({
            "level": "warn",
            "detail": "saved/keeper.json 未迁移至 keepers.json",
            "fix": "bash scripts/backfill-scenario-tsv.sh --apply . 或 load_keepers",
        })
    keeper_keys: set[str] = set()
    if keepers_path.is_file():
        try:
            keepers = json.loads(keepers_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            keepers = {}
        if not isinstance(keepers, dict):
            keepers = {}
        keeper_keys = set(keepers.keys())
        for key in keeper_keys:
            if key not in inv_set:
                out.append({
                    "level": "fail",
                    "detail": f"keepers.json 含未知场景键 {key!r}",
                    "fix": "修正 keepers 或 re-write-keeper --scenario-id",
                })
    if ids_in_tsv:
        for sid in sorted(ids_in_tsv - keeper_keys):
            out.append({
                "level": "warn",
                "detail": f"场景 {sid!r} 有 TSV 行但 keepers.json 无条目",
                "fix": "首次 KEEP 后自动写入，或手动 write-keeper --scenario-id",
            })

    return out
