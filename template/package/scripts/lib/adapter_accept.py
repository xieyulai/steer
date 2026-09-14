"""runner 出分验收（EVALUATE_RUNNER）— CLI / 辅指标 / baseline_tag helper。

历史文件名 ``adapter_accept``：立项 ADAPTER 场景已退役（v1.22.0）。本模块只服务
``metrics_shape=EVALUATE_RUNNER``（runner 出分），不是 object_type，也不是已死场景名。

- 空串/空白 cfg 值不追加 CLI flag
- 0 / False / "0" 视为有效值
- 自写透传若 argv 含 `--flag` + 空串 value → 硬 raise
- 合同声明的辅指标须有真值（0 合法；缺/None/非数值 → raise）
- ``is_evaluate_runner_repo``：doctor 硬门触发（``is_adapter_repo`` 为兼容别名）
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path
from types import ModuleType


def is_empty_cli_value(v) -> bool:
    """None、空串、纯空白 → True；0 / False / \"0\" → False。"""
    if v is None:
        return True
    if isinstance(v, bool):
        return False
    if isinstance(v, str):
        return not v.strip()
    return False


def append_cfg_cli(args: list, cfg: dict, mapping: dict[str, str]) -> None:
    """按 mapping[cfg_key]=cli_name 追加 --cli_name value；缺键与 empty 跳过，不 raise。"""
    for cfg_key, cli_name in mapping.items():
        if cfg_key not in cfg:
            continue
        value = cfg[cfg_key]
        if is_empty_cli_value(value):
            continue
        args.append(f"--{cli_name}")
        args.append(str(value))


def assert_cli_argv_no_empty_values(argv: list[str]) -> None:
    """任一 --flag 的下一 token 为 \"\" → ValueError。"""
    for i, token in enumerate(argv):
        if not token.startswith("--") or token == "--":
            continue
        if i + 1 >= len(argv):
            continue
        if argv[i + 1] == "":
            raise ValueError(f"empty CLI flag value after {token!r}")


def _is_aux_metric_numeric(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def require_declared_aux_metrics(metrics: dict, declared) -> None:
    """declared 辅指标键须有真值；0/0.0 合法；未声明键不查；空 declared 为 no-op。"""
    for key in declared:
        if key not in metrics or metrics[key] is None:
            raise ValueError(f"declared auxiliary metric missing or None: {key!r}")
        if not _is_aux_metric_numeric(metrics[key]):
            raise ValueError(f"declared auxiliary metric non-numeric: {key!r}")


def _ensure_repo_paths(repo_root: Path) -> None:
    scripts = repo_root / "scripts"
    for path in (repo_root, scripts):
        s = str(path)
        if path.is_dir() and s not in sys.path:
            sys.path.insert(0, s)


def _normalize_metrics_shape(value):
    """归一 metrics_shape 配置/registry 值为 MetricsShape 或 None。"""
    from lib.train_branch_types import MetricsShape

    if value is None:
        return None
    if isinstance(value, MetricsShape):
        return value
    if isinstance(value, str):
        s = value.strip()
        if s in ("EVALUATE_RUNNER", "evaluate_runner", "adapter"):
            if s == "adapter":
                return MetricsShape.from_legacy("adapter")
            return MetricsShape.EVALUATE_RUNNER
        if s in ("EVALUATE_LEARNER", "evaluate_learner", "supervised", "mammoth_cl"):
            if s in ("EVALUATE_LEARNER", "evaluate_learner"):
                return MetricsShape.EVALUATE_LEARNER
            return MetricsShape.from_legacy(s)
        try:
            return MetricsShape[s]
        except KeyError:
            pass
        try:
            return MetricsShape(s)
        except ValueError:
            pass
        try:
            return MetricsShape.from_legacy(s)
        except ValueError:
            return None
    return None


def _registry_indicates_evaluate_runner(repo_root: Path) -> bool:
    if not (repo_root / "workspace").is_dir():
        return False
    _ensure_repo_paths(repo_root)
    try:
        from lib.train_branch_types import MetricsShape
        from workspace import _KIND_REGISTRY, get_workspace_kind
    except ImportError:
        return False
    if not _KIND_REGISTRY:
        return False
    return any(
        get_workspace_kind(name) is MetricsShape.EVALUATE_RUNNER for name in _KIND_REGISTRY
    )


def is_evaluate_runner_repo(repo_root: Path) -> bool:
    """是否为 runner 出分形态（``metrics_shape=EVALUATE_RUNNER``）。

    与 object_type（code/framework/data）无关；framework（如 Mammoth）默认 LEARNER，
    不会仅因框架身份而为 True。
    """
    repo_root = Path(repo_root).resolve()
    _ensure_repo_paths(repo_root)

    nn_cfg_path = repo_root / "nn-config.yaml"
    if nn_cfg_path.is_file():
        try:
            from lib.nn_config import load_nn_config

            cfg = load_nn_config(repo_root)
            ms = (cfg.get("workspace") or {}).get("metrics_shape")
            if ms is not None:
                normalized = _normalize_metrics_shape(ms)
                if normalized is not None:
                    from lib.train_branch_types import MetricsShape

                    return normalized is MetricsShape.EVALUATE_RUNNER
        except Exception:
            pass

    return _registry_indicates_evaluate_runner(repo_root)


def is_adapter_repo(repo_root: Path) -> bool:
    """兼容别名 → ``is_evaluate_runner_repo``（立项 ADAPTER 场景已退役）。"""
    return is_evaluate_runner_repo(repo_root)


def evaluate_runner_baseline_tag_doctor(repo_root: Path) -> tuple[str | None, str]:
    """nn-doctor：非 runner 出分 → (None,\"\")；否则 PASS/FAIL（watchlist + TSV 列）。"""
    repo_root = Path(repo_root).resolve()
    if not is_evaluate_runner_repo(repo_root):
        return None, ""

    reasons: list[str] = []
    try:
        from lib.nn_config import load_nn_config

        wl = (load_nn_config(repo_root).get("ledger") or {}).get("watchlist") or []
        if "baseline_tag" not in wl:
            reasons.append("ledger.watchlist 缺 baseline_tag")
    except Exception:
        reasons.append("无法读取 ledger.watchlist")

    tsv = repo_root / "_runs" / "results.tsv"
    if tsv.is_file():
        header = tsv.read_text(encoding="utf-8").splitlines()[:1]
        cols = header[0].split("\t") if header else []
        if "baseline_tag" not in cols:
            reasons.append("results.tsv 表头缺 baseline_tag 列")

    if reasons:
        return "FAIL", " ".join(reasons)
    return "PASS", "baseline_tag 列与 watchlist 齐（runner 出分）"


# build_command 探测时须保留有效值的 cfg 键（非空串探测）
_PROBE_SKIP_EMPTY_KEYS = frozenset(
    {
        "MAMMOTH_ROOT",
        "MAMMOTH_MODEL",
        "MAMMOTH_DATASET",
        "MAMMOTH_DATASET_CONFIG",
    }
)


def _offending_empty_cli_flags(argv: list[str]) -> list[str]:
    """返回 argv 中 value 为空串的 flag 名（不含 --）。"""
    flags: list[str] = []
    for i, token in enumerate(argv):
        if not token.startswith("--") or token == "--":
            continue
        if i + 1 < len(argv) and argv[i + 1] == "":
            flags.append(token[2:])
    return flags


def _build_probe_cfg(
    mapping: dict[str, str], exp_dir: Path, workspace_mod: ModuleType
) -> dict:
    """构造探测 cfg：mapping 内可空串键设为 \"\"，其余必填键给 stub。"""
    cfg: dict = {k: "" for k in mapping if k not in _PROBE_SKIP_EMPTY_KEYS}

    mammoth_root = exp_dir / "mammoth_stub"
    mammoth_root.mkdir(parents=True, exist_ok=True)
    (mammoth_root / "main.py").write_text("# probe stub\n", encoding="utf-8")

    if "MAMMOTH_ROOT" in mapping:
        cfg["MAMMOTH_ROOT"] = str(mammoth_root)
    if "MAMMOTH_MODEL" in mapping:
        reg = getattr(workspace_mod, "CLI_ADAPTER_REGISTRY", None)
        if isinstance(reg, dict) and reg:
            cfg["MAMMOTH_MODEL"] = next(iter(reg))
        else:
            cfg["MAMMOTH_MODEL"] = "__probe_model__"
    if "MAMMOTH_DATASET" in mapping:
        cfg.setdefault("MAMMOTH_DATASET", "probe-dataset")
    if "MAMMOTH_DATASET_CONFIG" in mapping:
        cfg.setdefault("MAMMOTH_DATASET_CONFIG", "default")

    return cfg


def probe_cfg_to_cli_empty_passthrough(workspace_mod: ModuleType) -> tuple[bool, list[str]]:
    """探测 build_command 是否把空串 cfg 透传为 CLI 空值。

    Returns:
        (probed, offending_flags): probed=False 表示无可探测模块或调用失败；
        offending_flags 为违规 CLI 名（不含 --）。
    """
    mapping = getattr(workspace_mod, "CFG_TO_CLI", None)
    build_command = getattr(workspace_mod, "build_command", None)
    if not mapping or not build_command:
        return False, []

    with tempfile.TemporaryDirectory(prefix="adapter-cli-probe-") as tmp:
        exp_dir = Path(tmp)
        probe_cfg = _build_probe_cfg(mapping, exp_dir, workspace_mod)
        try:
            argv = build_command(probe_cfg, exp_dir)
        except Exception:
            return False, []

        if not isinstance(argv, list):
            return False, []

        return True, _offending_empty_cli_flags(argv)


def static_scan_cfg_to_cli_empty_passthrough(workspace_init: Path) -> list[str]:
    """源码静态扫描：is-not-None 透传且未 import append_cfg_cli → 违规描述列表。"""
    if not workspace_init.is_file():
        return []
    text = workspace_init.read_text(encoding="utf-8", errors="replace")
    if "append_cfg_cli" in text:
        return []
    if "CFG_TO_CLI" not in text or "build_command" not in text:
        return []

    none_passthrough = bool(
        re.search(r"cfg\[[^\]]+\]\s*is\s+not\s+None", text)
        or re.search(r"cfg\.get\([^)]+\)\s*is\s+not\s+None", text)
    )
    cli_emit = bool(
        re.search(r'(?:extend|append)\(\[[^\]]*["\']--', text)
        or re.search(r'f"--\{', text)
        or re.search(r'str\s*\(\s*cfg\[', text)
    )
    if none_passthrough and cli_emit:
        return ["build_command 使用 is-not-None 透传且未 import append_cfg_cli"]
    return []


def adapter_cli_empty_doctor(repo_root: Path) -> tuple[str | None, str]:
    """nn-doctor adapter_cli_empty（行名遗留）：非 runner 出分 → (None, \"\")；否则 PASS/FAIL。"""
    repo_root = Path(repo_root).resolve()
    if not is_evaluate_runner_repo(repo_root):
        return None, ""

    ws_init = repo_root / "workspace" / "__init__.py"
    if not ws_init.is_file():
        return None, ""

    _ensure_repo_paths(repo_root)
    workspace_mod: ModuleType | None = None
    try:
        import workspace as workspace_mod  # type: ignore[no-redef]
    except ImportError:
        workspace_mod = None

    if workspace_mod is not None:
        probed, flags = probe_cfg_to_cli_empty_passthrough(workspace_mod)
        if probed:
            if flags:
                uniq = sorted(set(flags))
                return "FAIL", f"空串仍透传为 CLI 空值: {', '.join(uniq)}"
            return "PASS", "空串 CLI 已省略"

    static_hits = static_scan_cfg_to_cli_empty_passthrough(ws_init)
    if static_hits:
        return "FAIL", "; ".join(static_hits)

    if workspace_mod is None:
        return None, ""

    mapping = getattr(workspace_mod, "CFG_TO_CLI", None)
    build_fn = getattr(workspace_mod, "build_command", None)
    if not mapping or not build_fn:
        return None, ""

    return "PASS", "空串 CLI 已省略"
