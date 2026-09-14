"""Framework 接入总表 — contract/framework_binding.yaml 读校验与 eval 对账。

总表是 Discovery 落盘，被 doctor/smoke 消费；dispatch_training / dispatch_test_call 不读本表。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

BINDING_REL = "contract/framework_binding.yaml"
SECTIONS = ("data", "train", "eval", "train_log", "checkpoint")
_VALID_STATUS = frozenset({"bound", "unavailable"})
_VALID_MECH = frozenset({"native", "in_process", "subprocess"})
_VALID_EVAL_KIND = frozenset({"api", "artifact", "stdout", "unavailable"})
_VALID_TRAIN_LOG_MODE = frozenset(
    {"direct", "dual_stream", "callback", "post_hoc_files", "unavailable"}
)
_FRAMEWORK_NEEDLES = (
    "对象类型=framework",
    "对象类型: **framework**",
    "对象类型：**framework**",
    "object_type=framework",
)


def load_framework_binding(repo_root: Path) -> dict[str, Any] | None:
    path = Path(repo_root) / BINDING_REL
    if not path.is_file():
        return None
    import yaml

    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if doc is None:
        return {}
    if not isinstance(doc, dict):
        raise ValueError(f"{BINDING_REL} 根须为 mapping，得到 {type(doc).__name__}")
    return doc


def is_framework_object_repo(repo_root: Path) -> bool:
    """启发式：文档里出现 framework 对象类型标记。"""
    root = Path(repo_root)
    candidates: list[Path] = []
    for rel in (
        "EXPERIENCE.md",
        "HUMAN_GUIDANCE.md",
        ".auto-nn/migration-summary.md",
    ):
        p = root / rel
        if p.is_file():
            candidates.append(p)
    manual = root / "references" / "manual"
    if manual.is_dir():
        candidates.extend(sorted(manual.rglob("*.md")))

    for p in candidates:
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if any(n in text for n in _FRAMEWORK_NEEDLES):
            return True
    return False


def validate_framework_binding(doc: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    if not isinstance(doc, dict):
        return ["root must be mapping"]

    for sec in SECTIONS:
        block = doc.get(sec)
        if not isinstance(block, dict):
            errs.append(f"missing section: {sec}")
            continue
        st = block.get("status")
        if st not in _VALID_STATUS:
            errs.append(f"{sec}.status must be bound|unavailable")
            continue
        if st == "unavailable" and not str(block.get("reason") or "").strip():
            errs.append(f"{sec}: unavailable requires reason")

    train = doc.get("train")
    if isinstance(train, dict) and train.get("status") == "bound":
        mech = train.get("mech")
        if mech not in _VALID_MECH:
            errs.append("train.mech must be native|in_process|subprocess when bound")

    ev = doc.get("eval")
    if isinstance(ev, dict) and ev.get("status") == "bound":
        kind = ev.get("kind")
        if kind not in _VALID_EVAL_KIND or kind == "unavailable":
            errs.append("eval.kind must be api|artifact|stdout when bound")
        for key in ("primary_raw_key", "ledger_primary_key"):
            if not str(ev.get(key) or "").strip():
                errs.append(f"eval.{key} required when bound")
        if kind == "api" and not str(ev.get("callable") or "").strip():
            errs.append("eval.callable required when kind=api")
        if kind == "artifact" and not str(ev.get("path_template") or "").strip():
            errs.append("eval.path_template required when kind=artifact")
        if kind == "stdout" and not str(ev.get("pattern_name") or "").strip():
            errs.append("eval.pattern_name required when kind=stdout")

    tl = doc.get("train_log")
    if isinstance(tl, dict) and tl.get("status") == "bound":
        mode = tl.get("mode")
        if mode not in _VALID_TRAIN_LOG_MODE or mode == "unavailable":
            errs.append(
                "train_log.mode must be direct|dual_stream|callback|post_hoc_files when bound"
            )

    return errs


def assert_eval_binding(
    raw: dict[str, Any],
    ledger: dict[str, Any],
    eval_section: dict[str, Any],
    *,
    atol: float = 1e-6,
) -> None:
    pk = eval_section.get("primary_raw_key")
    lk = eval_section.get("ledger_primary_key")
    if not pk or not lk:
        raise ValueError("eval_section missing primary_raw_key or ledger_primary_key")
    if pk not in raw:
        raise ValueError(f"raw missing primary_raw_key={pk!r}")
    if lk not in ledger or ledger[lk] is None:
        raise ValueError(f"ledger missing {lk!r}")
    try:
        rv = float(raw[pk])
        lv = float(ledger[lk])
    except (TypeError, ValueError) as e:
        raise ValueError(f"non-numeric binding values raw[{pk}] / ledger[{lk}]") from e
    if abs(rv - lv) > atol:
        raise ValueError(
            f"eval binding mismatch: raw[{pk}]={rv} vs ledger[{lk}]={lv} (atol={atol})"
        )


def write_eval_export_raw(exp_dir: Path, raw: dict[str, Any]) -> Path:
    out = Path(exp_dir) / "eval_export_raw.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _workspace_has_callable(repo_root: Path, name: str) -> bool:
    """静态：workspace/__init__.py 含 def name 或 name =；或可 import 后 hasattr。"""
    init_py = Path(repo_root) / "workspace" / "__init__.py"
    if init_py.is_file():
        text = init_py.read_text(encoding="utf-8", errors="ignore")
        if re.search(rf"^\s*def\s+{re.escape(name)}\s*\(", text, re.M):
            return True
        if re.search(rf"^\s*{re.escape(name)}\s*=", text, re.M):
            return True
    try:
        import importlib
        import sys

        root_s = str(Path(repo_root).resolve())
        if root_s not in sys.path:
            sys.path.insert(0, root_s)
        ws = importlib.import_module("workspace")
        return callable(getattr(ws, name, None))
    except Exception:
        return False


def _nn_checkpoint_policy(repo_root: Path) -> str | None:
    try:
        from lib.nn_config import load_nn_config

        cfg = load_nn_config(Path(repo_root)) or {}
        v = cfg.get("checkpoint")
        return None if v is None else str(v).strip().lower()
    except Exception:
        return None


def framework_binding_doctor(repo_root: Path) -> list[tuple[str, str, str]]:
    """返回 (row_name, status, msg) 列表；无事且应跳过时返回 []."""
    root = Path(repo_root).resolve()
    rows: list[tuple[str, str, str]] = []
    try:
        doc = load_framework_binding(root)
    except ValueError as e:
        return [("fw_binding_decl", "FAIL", str(e))]

    if doc is None:
        if is_framework_object_repo(root):
            rows.append(
                (
                    "fw_binding_decl",
                    "FAIL",
                    "framework 仓缺少 contract/framework_binding.yaml",
                )
            )
        return rows

    errs = validate_framework_binding(doc)
    if errs:
        rows.append(("fw_binding_decl", "FAIL", "; ".join(errs)))
        return rows
    rows.append(("fw_binding_decl", "PASS", "framework_binding.yaml schema OK"))

    gaps = [
        f"{sec}:{doc[sec].get('reason', '')}"
        for sec in SECTIONS
        if isinstance(doc.get(sec), dict) and doc[sec].get("status") == "unavailable"
    ]
    if gaps:
        rows.append(("fw_binding_gaps", "WARN", "unavailable: " + "; ".join(gaps)))

    train = doc.get("train") or {}
    if train.get("status") == "bound":
        hooks = train.get("hooks") or []
        if not hooks:
            rows.append(
                (
                    "fw_binding_train_hooks",
                    "WARN",
                    "train.status=bound 但 hooks 为空；建议声明 framework_* 钩子",
                )
            )

    ev = doc.get("eval") or {}
    if ev.get("status") == "bound" and ev.get("kind") == "api":
        name = str(ev.get("callable") or "").strip()
        if name and not _workspace_has_callable(root, name):
            rows.append(
                (
                    "fw_binding_eval_hook",
                    "FAIL",
                    f"eval.callable={name!r} 在 workspace 未找到可调用实现",
                )
            )
        elif name:
            rows.append(("fw_binding_eval_hook", "PASS", f"eval.callable={name} 可见"))

    ck = doc.get("checkpoint") or {}
    if ck.get("status") == "unavailable":
        pol = _nn_checkpoint_policy(root)
        if pol and pol != "none":
            rows.append(
                (
                    "fw_binding_ckpt",
                    "WARN",
                    f"checkpoint 节 unavailable 但 nn-config.checkpoint={pol!r}；建议设为 none",
                )
            )

    return rows


def _load_ledger_metrics(exp_dir: Path, ledger_key: str) -> dict[str, Any] | None:
    """从 results.json 等取台账主分。"""
    for name in ("results.json", "keep_suggestion.json"):
        p = exp_dir / name
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if ledger_key in data:
            return data
        metrics = data.get("metrics")
        if isinstance(metrics, dict) and ledger_key in metrics:
            return metrics
        official = data.get("official_metrics") or data.get("precomputed_official_metrics")
        if isinstance(official, dict) and ledger_key in official:
            return official
    return None


def check_eval_binding_smoke(repo_root: Path) -> None:
    """有总表且 eval.bound 时：最近 eval_export_raw.json ↔ 同目录台账主分。无表则 no-op。"""
    root = Path(repo_root).resolve()
    doc = load_framework_binding(root)
    if doc is None:
        return
    errs = validate_framework_binding(doc)
    if errs:
        raise ValueError("framework_binding invalid: " + "; ".join(errs))
    ev = doc.get("eval") or {}
    if ev.get("status") != "bound":
        return

    exp_root = root / "_runs" / "exp"
    raw_files = (
        sorted(
            exp_root.glob("*/eval_export_raw.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if exp_root.is_dir()
        else []
    )
    if not raw_files:
        raise ValueError(
            "eval.status=bound 但未找到 _runs/exp/*/eval_export_raw.json；"
            "contract.test 路径须 write_eval_export_raw"
        )
    raw_path = raw_files[0]
    exp_dir = raw_path.parent
    try:
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"bad eval_export_raw.json: {raw_path}") from e
    if not isinstance(raw, dict):
        raise ValueError("eval_export_raw.json root must be object")

    lk = str(ev.get("ledger_primary_key") or "")
    ledger = _load_ledger_metrics(exp_dir, lk)
    if ledger is None:
        raise ValueError(
            f"无法在 {exp_dir} 的 results.json 等文件中找到台账键 {lk!r}"
        )
    assert_eval_binding(raw, ledger, ev)


__all__ = [
    "BINDING_REL",
    "SECTIONS",
    "load_framework_binding",
    "validate_framework_binding",
    "is_framework_object_repo",
    "assert_eval_binding",
    "write_eval_export_raw",
    "framework_binding_doctor",
    "check_eval_binding_smoke",
]
