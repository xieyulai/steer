"""本机原仓校准门禁：文献尺须用原仓校准分校对复现分。

校准跑不进成绩表。尺子锚值永远是本仓复现分。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lib.audit_core import repro_tolerance

CALIBRATION_REL = "saved/source_calibration.json"
CHECK_REL = "saved/source_cal_check.json"
INTENT_REL = "saved/baseline_start_intent.json"
MIGRATION_SOURCE_REL = ".auto-nn/migration-source"

_GREENFIELD = frozenset(
    {
        "",
        "-",
        "none",
        "# greenfield",
        "# entry-b",
        "# entry-b greenfield",
    }
)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_intent(root: Path) -> dict[str, Any] | None:
    return _read_json(Path(root) / INTENT_REL)


def _migration_source_line(root: Path) -> str:
    p = Path(root) / MIGRATION_SOURCE_REL
    if not p.is_file():
        return ""
    raw = p.read_text(encoding="utf-8").strip()
    for line in raw.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line
    return raw.splitlines()[0].strip() if raw else ""


def resolve_source_repo(root: Path) -> Path | None:
    """命中即停：migration-source 真目录 → intent.source_repo_path。"""
    root = Path(root)
    line = _migration_source_line(root)
    norm = line.lower().strip()
    raw_file = root / MIGRATION_SOURCE_REL
    if raw_file.is_file():
        raw_all = raw_file.read_text(encoding="utf-8").strip()
        marker = raw_all.lower().strip() if raw_all.startswith("#") else norm
        if marker not in _GREENFIELD and line and Path(line).is_dir():
            return Path(line).resolve()
    intent = load_intent(root)
    if intent:
        cand = str(intent.get("source_repo_path") or "").strip()
        if cand and Path(cand).is_dir():
            return Path(cand).resolve()
    return None


def source_cal_skip_why(root: Path) -> str | None:
    intent = load_intent(root)
    if not intent:
        return None
    why = str(intent.get("source_cal_skip_why") or "").strip()
    return why or None


def gate_applies(root: Path, *, tag: str, source: str) -> bool:
    if str(tag).strip().lower() != "reference":
        return False
    if str(source).strip().lower() != "literature":
        return False
    if source_cal_skip_why(root):
        return False
    return resolve_source_repo(root) is not None


def load_calibration(root: Path) -> dict[str, Any] | None:
    return _read_json(Path(root) / CALIBRATION_REL)


def _near_best_abs(root: Path) -> float:
    cfg_path = Path(root) / "nn-config.yaml"
    if not cfg_path.is_file():
        return 0.0
    try:
        import yaml

        raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        keep = (raw.get("keep") or {}) if isinstance(raw, dict) else {}
        return float(keep.get("near_best_abs") or 0.0)
    except Exception:
        return 0.0


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v


def evaluate_check(
    *,
    port_value: float,
    source_cal_value: float,
    near_best_abs: float,
) -> dict[str, Any]:
    tol = repro_tolerance(float(source_cal_value), float(near_best_abs))
    delta = abs(float(port_value) - float(source_cal_value))
    if delta <= tol:
        verdict = "pass"
        next_action = "可以对上，可贴公开对照；尺子用本仓复现分，校准分只作旁证。"
    else:
        verdict = "fail"
        next_action = (
            "差超过容差，禁止贴尺。先改本仓配方或调度后再只重跑本仓对照，"
            "不要把论文分数写进尺子。"
        )
    return {
        "port_value": float(port_value),
        "source_cal_value": float(source_cal_value),
        "delta": delta,
        "tolerance": tol,
        "verdict": verdict,
        "next_action": next_action,
    }


def write_check(root: Path, payload: dict[str, Any]) -> Path:
    path = Path(root) / CHECK_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def _raise_blocked(check: dict[str, Any]) -> None:
    verdict = str(check.get("verdict") or "")
    delta = check.get("delta")
    tol = check.get("tolerance")
    bits = [f"原仓校准未过（{verdict}）"]
    if delta is not None and tol is not None:
        bits.append(f"差={delta} 容差={tol}")
    bits.append(f"见 {CHECK_REL}")
    next_action = str(check.get("next_action") or "").strip()
    if next_action:
        bits.append(next_action)
    raise ValueError("；".join(bits))


def enforce_before_stamp(
    root: Path,
    *,
    tag: str,
    source: str,
    port_value: float | None,
    port_exp_dir: str = "",
) -> dict[str, Any] | None:
    """需要门禁且未达标则 ValueError；不需要则 None；达标返回 check dict。"""
    root = Path(root)
    if not gate_applies(root, tag=tag, source=source):
        return None

    def _blocked(payload: dict[str, Any]) -> None:
        if port_exp_dir and "port_exp_dir" not in payload:
            payload = {**payload, "port_exp_dir": port_exp_dir}
        write_check(root, payload)
        _raise_blocked(payload)

    cal = load_calibration(root)
    cal_val = _as_float((cal or {}).get("source_cal_value")) if cal else None
    if cal is None or cal_val is None:
        _blocked(
            {
                "port_exp_dir": port_exp_dir,
                "port_value": port_value,
                "source_cal_value": None,
                "delta": None,
                "tolerance": None,
                "verdict": "incomplete",
                "next_action": (
                    "还没有本机原仓校准分，禁止贴尺。"
                    "先用原仓入口跑完并写入校准记录，不要把论文分数当尺子。"
                ),
            }
        )

    status = str((cal or {}).get("source_cal_status") or "").strip().lower()
    if status in ("incomparable", "incomplete"):
        next_map = {
            "incomparable": (
                "测条件对不齐，禁止贴文献尺。改走中点代用或请用户给同条件对照，"
                "不要把论文分数写进尺子。"
            ),
            "incomplete": (
                "校准跑没跑完或解析不到主分，禁止贴尺。先修好原仓调用再重跑校准，"
                "不要改原仓代码、不要把论文分数当尺子。"
            ),
        }
        _blocked(
            {
                "port_exp_dir": port_exp_dir,
                "port_value": port_value,
                "source_cal_value": cal_val,
                "delta": None,
                "tolerance": None,
                "verdict": status,
                "next_action": next_map[status],
            }
        )

    if port_value is None:
        _blocked(
            {
                "port_exp_dir": port_exp_dir,
                "port_value": None,
                "source_cal_value": cal_val,
                "delta": None,
                "tolerance": None,
                "verdict": "incomplete",
                "next_action": (
                    "本仓对照没有主分，禁止贴尺。先把复现跑完再校对，"
                    "不要把论文分数当尺子。"
                ),
            }
        )

    check = evaluate_check(
        port_value=float(port_value),
        source_cal_value=float(cal_val),
        near_best_abs=_near_best_abs(root),
    )
    if port_exp_dir:
        check["port_exp_dir"] = port_exp_dir
    write_check(root, check)
    if check["verdict"] != "pass":
        _raise_blocked(check)
    return check
