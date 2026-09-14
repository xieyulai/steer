"""scenario_bindings 正向/逆向：cfg/env ↔ scenario_id 匹配（供 scenario_inventory 与 experiment 共用）。"""
from __future__ import annotations

import os
import re
from typing import Any

_SIP_TAIL_RE = re.compile(r"(\d+(?:\.\d+)?)\s*sip\s*$", re.IGNORECASE)


def normalize_scenario_binding(spec: Any) -> dict[str, Any]:
    if not isinstance(spec, dict):
        raise ValueError(f"scenario_bindings 项须为 dict，得到: {type(spec).__name__}")
    env_var = str(spec.get("env_var", "") or "").strip()
    if not env_var:
        raise ValueError("scenario_bindings 项缺少 env_var")
    cfg_key = str(spec.get("cfg_key", "") or "").strip()
    if not cfg_key and env_var.startswith("NN_"):
        cfg_key = env_var[3:]
    return {
        "env_var": env_var,
        "cfg_key": cfg_key,
        "parser": str(spec.get("parser", "literal") or "literal").strip().lower(),
        "value_key": str(spec.get("value_key", "value") or "value").strip(),
        "skip_if_set": bool(spec.get("skip_if_set", True)),
        "from": str(spec.get("from", "default") or "default").strip().lower(),
    }


def binding_cfg_key(binding: dict[str, Any]) -> str:
    ck = str(binding.get("cfg_key", "") or "").strip()
    if ck:
        return ck
    ev = str(binding.get("env_var", "") or "").strip()
    if ev.startswith("NN_"):
        return ev[3:]
    return ev


def _env_get(env: dict[str, str] | os._Environ[str] | None, key: str) -> str:
    if env is None:
        return str(os.environ.get(key, "") or "").strip()
    return str(env.get(key, "") or "").strip()


def read_binding_actual(
    binding: dict[str, Any],
    cfg: dict[str, Any] | None,
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
) -> Any:
    """从 cfg 或 env 读取 binding 对应的运行值。"""
    cfg = cfg or {}
    ck = binding_cfg_key(binding)
    if ck in cfg and cfg[ck] not in (None, ""):
        return cfg[ck]
    raw = _env_get(env, binding["env_var"])
    if raw:
        return raw
    return None


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _values_equal(expected: Any, actual: Any, *, rel_tol: float = 1e-9) -> bool:
    ef = _coerce_float(expected)
    af = _coerce_float(actual)
    if ef is not None and af is not None:
        if ef == 0.0 and af == 0.0:
            return True
        scale = max(1.0, abs(ef), abs(af))
        return abs(ef - af) <= rel_tol * scale
    return str(expected).strip().lower() == str(actual).strip().lower()


def _parse_sip_numeric(scenario_id: str) -> float | None:
    s = (scenario_id or "").strip().lower()
    if not s:
        return None
    m = _SIP_TAIL_RE.search(s)
    if m:
        return _coerce_float(m.group(1))
    body = s[:-3] if s.endswith("sip") else s
    body = body.rsplit("_", 1)[-1].strip()
    if not body:
        return None
    if "p" in body and "." not in body:
        body = body.replace("p", ".", 1)
    return _coerce_float(body)


def scenario_id_matches_binding(scenario_id: str, binding: dict[str, Any], actual: Any) -> bool:
    """判断 scenario_id 是否与 cfg/env 中该 binding 的实际值一致。"""
    if actual is None or actual == "":
        return False
    sid = (scenario_id or "").strip()
    sid_l = sid.lower()
    parser = str(binding.get("parser", "literal") or "literal").strip().lower()

    if parser == "sip":
        expected = _parse_sip_numeric(sid)
        return expected is not None and _values_equal(expected, actual)

    if parser in ("mode_prefix", "prefix"):
        mode = str(actual).strip().lower()
        return sid_l.startswith(mode + "_") or sid_l == mode

    if parser == "gamma_kerr_linear":
        gamma = _coerce_float(actual)
        if gamma is None:
            return False
        if abs(gamma) < 1e-15:
            return "_linear_" in sid_l
        return "_kerr_" in sid_l

    if parser == "literal":
        val = str(actual).strip().lower()
        return sid_l.startswith(val + "_") or sid_l == val

    if parser in ("float", "int"):
        return _values_equal(actual, binding.get("value_key", "value"))

    return False


def infer_scenario_id_from_bindings(
    candidates: list[str],
    bindings: list[dict[str, Any]],
    cfg: dict[str, Any] | None,
    *,
    env: dict[str, str] | os._Environ[str] | None = None,
) -> str | None:
    """从 bindings + cfg/env 在 candidates 中唯一匹配 scenario_id；歧义或无匹配返回 None。"""
    if not bindings or not candidates:
        return None
    actuals = [read_binding_actual(b, cfg, env=env) for b in bindings]
    if any(a is None or a == "" for a in actuals):
        return None

    matches: list[str] = []
    for sid in candidates:
        if all(scenario_id_matches_binding(sid, b, a) for b, a in zip(bindings, actuals)):
            matches.append(sid)

    if len(matches) == 1:
        return matches[0]
    return None
