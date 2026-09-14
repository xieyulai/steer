"""立尺：每场景一把 plain / reference；中点挑行；贴签写 config + TSV + 锚点 json。

不改 keepers.json。
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.baseline_anchors_status import has_reference_baseline_tag
from lib.source_calibration import enforce_before_stamp
from lib.run_ledger_summary import (
    _best_row_for_scenario,
    _float_cell,
    load_keepers,
    metric_direction,
    metric_key,
    tsv_rows,
)

REFERENCE_AUTO_AFTER_ROUNDS = 10
_SLOT_RE = re.compile(r"_s\d+of\d+")
_VALID_TAGS = ("plain", "reference", "none")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _norm_path(p: str) -> str:
    return Path(str(p).strip()).as_posix().rstrip("/")


def paths_match(a: str, b: str) -> bool:
    na, nb = _norm_path(a), _norm_path(b)
    if na == nb:
        return True
    return na.endswith("/" + nb) or nb.endswith("/" + na) or na.endswith(nb) or nb.endswith(na)


def _rel_exp(repo_root: Path, exp_dir: str) -> str:
    root = repo_root.resolve()
    p = Path(exp_dir)
    if not p.is_absolute():
        p = root / p
    p = p.resolve()
    try:
        return str(p.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")


def _is_junk_row(row: dict[str, str]) -> bool:
    exp = str(row.get("experiment") or "").strip()
    if exp == "preflight_check":
        return True
    if exp.startswith("audit_"):
        return True
    return False


def _round_key(row: dict[str, str]) -> str:
    exp = str(row.get("experiment") or "").strip()
    if exp:
        return _SLOT_RE.sub("", exp)
    return _SLOT_RE.sub("", str(row.get("exp_dir") or "").strip())


def tagged_rows(
    repo_root: Path | str,
    scenario_id: str,
    tag: str,
) -> list[dict[str, str]]:
    root = Path(repo_root).resolve()
    sid = (scenario_id or "").strip()
    want = tag.strip().lower()
    out: list[dict[str, str]] = []
    for row in tsv_rows(root):
        if _is_junk_row(row):
            continue
        if sid and str(row.get("scenario_id") or "").strip() != sid:
            continue
        if str(row.get("baseline_tag") or "").strip().lower() != want:
            continue
        out.append(row)
    return out


def completed_experiment_rounds(
    repo_root: Path | str,
    scenario_id: str | None = None,
) -> int:
    """关注场景已完成实验轮。优先日记 kind=round；截断则按成绩表去槽位计数。"""
    root = Path(repo_root).resolve()
    sid = (scenario_id or "").strip()
    n_journal = _journal_round_count(root, sid or None)
    n_tsv = _tsv_round_count(root, sid or None)
    from lib.experiment_journal import read_journal, journal_path, _journal_max_entries

    journal = read_journal(journal_path(root))
    entries = journal.get("entries") or []
    cap = _journal_max_entries(root)
    facts = journal.get("facts") or {}
    tsv_fact = int(facts.get("tsv_row_count") or 0)
    truncated = len(entries) >= cap or (tsv_fact > 0 and tsv_fact > len(entries) + 2)
    if n_journal > 0 and not truncated:
        return n_journal
    return max(n_journal, n_tsv)


def _journal_round_count(root: Path, scenario_id: str | None) -> int:
    from lib.experiment_journal import journal_path, read_journal

    journal = read_journal(journal_path(root))
    n = 0
    any_sid = False
    for e in journal.get("entries") or []:
        if not isinstance(e, dict):
            continue
        if str(e.get("kind") or "") != "round":
            continue
        esid = str(e.get("scenario_id") or "").strip()
        if esid:
            any_sid = True
        if scenario_id and esid and esid != scenario_id:
            continue
        n += 1
    if scenario_id and not any_sid:
        return n
    return n


def _tsv_round_count(root: Path, scenario_id: str | None) -> int:
    keys: set[str] = set()
    for row in tsv_rows(root):
        if _is_junk_row(row):
            continue
        if scenario_id and str(row.get("scenario_id") or "").strip() != scenario_id:
            continue
        keys.add(_round_key(row) or f"row-{len(keys)}")
    return len(keys)


def _keeper_info(root: Path, scenario_id: str) -> tuple[str, float | None]:
    keepers = load_keepers(root)
    entry = keepers.get(scenario_id) or {}
    kdir = str(entry.get("keeper_exp_dir") or "").strip()
    kval: float | None = None
    mk = metric_key(root)
    if kdir:
        for row in tsv_rows(root):
            exp = str(row.get("exp_dir") or "").strip()
            if exp and paths_match(exp, kdir):
                kval = _float_cell(row, mk)
                break
        if kval is None:
            res = root / kdir / "results.json" if not Path(kdir).is_absolute() else Path(kdir) / "results.json"
            if not res.is_file() and not Path(kdir).is_absolute():
                res = root / kdir / "results.json"
            if res.is_file():
                try:
                    data = json.loads(res.read_text(encoding="utf-8"))
                    from lib.audit_core import primary_from_results

                    kval = float(primary_from_results(data, mk))
                except Exception:
                    kval = None
        return kdir, kval
    best = _best_row_for_scenario(root, scenario_id, mk, metric_direction(root))
    if not best:
        return "", None
    return str(best.get("exp_dir") or "").strip(), _float_cell(best, mk)


def pick_midpoint_reference(
    repo_root: Path | str,
    scenario_id: str,
    *,
    metric_key_name: str | None = None,
    direction: str | None = None,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    sid = (scenario_id or "").strip()
    mk = metric_key_name or metric_key(root)
    md = direction or metric_direction(root)
    plains = tagged_rows(root, sid, "plain")
    if not plains:
        raise ValueError("无朴素下界，算不了中点；请先 /auto-nn-plain")
    plain_row = plains[0]
    plain_dir = str(plain_row.get("exp_dir") or "").strip()
    p_val = _float_cell(plain_row, mk)
    if p_val is None:
        raise ValueError("朴素下界行没有主分")
    kdir, k_val = _keeper_info(root, sid)
    if k_val is None:
        raise ValueError("没有当前最好主分，算不了中点")
    target = (float(k_val) + float(p_val)) / 2.0
    best_row: dict[str, str] | None = None
    best_dist: float | None = None
    for row in tsv_rows(root):
        if _is_junk_row(row):
            continue
        if str(row.get("scenario_id") or "").strip() != sid:
            continue
        tag = str(row.get("baseline_tag") or "").strip().lower()
        if tag == "plain":
            continue
        exp = str(row.get("exp_dir") or "").strip()
        if not exp:
            continue
        if kdir and paths_match(exp, kdir):
            continue
        v = _float_cell(row, mk)
        if v is None:
            continue
        dist = abs(float(v) - target)
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_row = row
    if best_row is None:
        raise ValueError("没有可当公开对照的已有成绩（排除当前最好与朴素下界后为空）")
    return {
        "exp_dir": str(best_row.get("exp_dir") or "").strip(),
        "experiment": str(best_row.get("experiment") or "").strip(),
        "primary": _float_cell(best_row, mk),
        "target": target,
        "keeper_primary": k_val,
        "plain_primary": p_val,
        "keeper_exp_dir": kdir,
        "plain_exp_dir": plain_dir,
        "metric_key": mk,
        "metric_direction": md,
        "source": "ledger_midpoint",
    }


def _read_tsv_table(root: Path) -> tuple[list[str], list[list[str]]]:
    p = root / "_runs" / "results.tsv"
    if not p.is_file():
        raise FileNotFoundError("缺少 _runs/results.tsv")
    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        raise ValueError("成绩表为空")
    headers = lines[0].split("\t")
    rows = [ln.split("\t") for ln in lines[1:]]
    for r in rows:
        if len(r) < len(headers):
            r.extend([""] * (len(headers) - len(r)))
    return headers, rows


def _write_tsv_table(root: Path, headers: list[str], rows: list[list[str]]) -> None:
    p = root / "_runs" / "results.tsv"
    p.parent.mkdir(parents=True, exist_ok=True)
    body = "\t".join(headers) + "\n"
    for r in rows:
        if len(r) < len(headers):
            r = r + [""] * (len(headers) - len(r))
        body += "\t".join(r[: len(headers)]) + "\n"
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, p)


def _ensure_tag_col(headers: list[str], rows: list[list[str]]) -> tuple[list[str], list[list[str]], int]:
    if "baseline_tag" in headers:
        return headers, rows, headers.index("baseline_tag")
    headers = list(headers) + ["baseline_tag"]
    rows = [list(r) + ["none"] for r in rows]
    return headers, rows, len(headers) - 1


def _exp_col(headers: list[str]) -> int | None:
    if "exp_dir" in headers:
        return headers.index("exp_dir")
    return None


def _sid_col(headers: list[str]) -> int | None:
    if "scenario_id" in headers:
        return headers.index("scenario_id")
    return None


def _set_config_tag(root: Path, rel: str, tag: str) -> None:
    d = root / rel
    cfgp = d / "config.json"
    if not cfgp.is_file():
        raise FileNotFoundError(f"缺少 config.json: {rel}")
    cfg = json.loads(cfgp.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict):
        raise ValueError(f"config.json 非 dict: {rel}")
    cfg["baseline_tag"] = tag
    cfgp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_anchor(
    root: Path,
    *,
    tag: str,
    value: float | None,
    exp_dir: str,
    scenario_id: str,
    source: str,
) -> None:
    saved = root / "saved"
    saved.mkdir(parents=True, exist_ok=True)
    if tag == "plain":
        payload = {
            "plain_anchor_value": value,
            "exp_dir": exp_dir,
            "scenario_id": scenario_id,
            "updated_at": _utc_now(),
        }
        (saved / "plain_anchor.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return
    payload = {
        "reference_anchor_value": value,
        "exp_dir": exp_dir,
        "scenario_id": scenario_id,
        "source": source or "literature",
        "updated_at": _utc_now(),
    }
    (saved / "reference_anchor.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def stamp_tag(
    repo_root: Path | str,
    *,
    exp_dir: str,
    tag: str,
    replace: bool = False,
    source: str = "",
    scenario_id: str | None = None,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    want = tag.strip().lower()
    if want not in ("plain", "reference"):
        raise ValueError("tag 只能是 plain 或 reference")
    rel = _rel_exp(root, exp_dir)
    cfgp = root / rel / "config.json"
    if not cfgp.is_file():
        raise FileNotFoundError(f"缺少 config.json: {rel}")
    cfg = json.loads(cfgp.read_text(encoding="utf-8"))
    sid = (scenario_id or str(cfg.get("SCENARIO_ID") or cfg.get("scenario_id") or "")).strip()
    headers, rows = _read_tsv_table(root)
    headers, rows, ti = _ensure_tag_col(headers, rows)
    ei = _exp_col(headers)
    si = _sid_col(headers)
    if ei is None:
        raise ValueError("成绩表没有 exp_dir 列，无法贴签")
    # infer scenario from matching TSV row
    if not sid:
        for r in rows:
            if ei < len(r) and paths_match(r[ei], rel):
                if si is not None and si < len(r):
                    sid = r[si].strip()
                break
    if not sid:
        sid = "default"

    kdir, _ = _keeper_info(root, sid)
    if want == "reference" and kdir and paths_match(rel, kdir):
        raise ValueError("不能把当前最好贴成公开对照（自己比自己）")

    existing: list[int] = []
    self_idx: int | None = None
    self_old = ""
    for i, r in enumerate(rows):
        exp = r[ei] if ei < len(r) else ""
        row_sid = r[si].strip() if si is not None and si < len(r) else sid
        if si is not None and row_sid != sid:
            continue
        if paths_match(exp, rel):
            self_idx = i
            self_old = (r[ti] if ti < len(r) else "").strip().lower()
        if (r[ti] if ti < len(r) else "").strip().lower() == want:
            if not paths_match(exp, rel):
                existing.append(i)
    if self_idx is None:
        raise ValueError(f"成绩表找不到 {rel}")
    if self_old == "plain" and want == "reference":
        raise ValueError("不能把已是朴素下界的那一行贴成公开对照")
    if existing and not replace:
        other = rows[existing[0]][ei]
        raise ValueError(
            f"场景 {sid} 已有 {want}（{other}）。留下则不要再贴；换成这次候选请 --replace"
        )
    mk = metric_key(root)
    rowd = {h: (rows[self_idx][j] if j < len(rows[self_idx]) else "") for j, h in enumerate(headers)}
    primary = _float_cell(rowd, mk)
    if want == "reference":
        enforce_before_stamp(
            root,
            tag=want,
            source=source or "",
            port_value=primary,
            port_exp_dir=rel,
        )

    destamped: list[str] = []
    if existing and replace:
        for i in existing:
            old_rel = rows[i][ei]
            rows[i][ti] = "none"
            try:
                _set_config_tag(root, _rel_exp(root, old_rel), "none")
            except FileNotFoundError:
                pass
            destamped.append(old_rel)

    rows[self_idx][ti] = want
    _set_config_tag(root, rel, want)
    _write_tsv_table(root, headers, rows)

    _write_anchor(
        root,
        tag=want,
        value=primary,
        exp_dir=rel,
        scenario_id=sid,
        source=source if want == "reference" else "",
    )
    return {
        "ok": True,
        "tag": want,
        "exp_dir": rel,
        "scenario_id": sid,
        "primary": primary,
        "replaced": destamped,
        "source": source if want == "reference" else "",
    }


def should_emit_reference_start(repo_root: Path | str, scenario_id: str | None = None) -> bool:
    root = Path(repo_root).resolve()
    sid = (scenario_id or "").strip() or None
    if sid in ("", "default"):
        sid = None
    if has_reference_baseline_tag(root, scenario_id=sid):
        return False
    ref_json = root / "saved" / "reference_anchor.json"
    if ref_json.is_file():
        try:
            d = json.loads(ref_json.read_text(encoding="utf-8"))
            if isinstance(d, dict) and d.get("reference_anchor_value") is not None:
                return False
        except Exception:
            pass
    n = completed_experiment_rounds(root, sid)
    return n >= REFERENCE_AUTO_AFTER_ROUNDS
