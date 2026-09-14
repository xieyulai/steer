#!/usr/bin/env python3
"""
Analyze train.py hyperparameters section AND workspace build methods using AST parsing.
Used by nn-doctor.sh DEEP mode.
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path
from typing import NamedTuple


class ParamAdvice(NamedTuple):
    name: str
    current_value: str
    suggested_env: str
    category: str
    reason: str
    source: str  # "train.py" or "workspace/__init__.py"


CRITICAL_PARAMS = {
    "LR", "BATCH_SIZE", "EPOCHS", "D_MODEL", "NHEAD", "NUM_LAYERS",
    "WEIGHT_DECAY", "DROPOUT", "GRAD_CLIP",
    "MODEL_ARCH", "PATCH_LEN", "STRIDE",
    "NET_ARCH", "LEARNING_RATE", "HIDDEN_DIM",
}
EXTENDABLE_PARAMS = {
    "SCHEDULER", "ETA_MIN", "WARMUP_EPOCHS",
    "SAM_MODE", "SAM_RHO",
    "SWA_MODE", "SWA_START", "SWA_LR",
    "SNAPSHOT_ENSEMBLE_MODE",
    "MIXUP_ALPHA", "CUTMIX_ALPHA", "TEMPORAL_MIXUP_ALPHA",
    "QUANTILE_MODE", "AUX_TASK", "AUX_WEIGHT",
    "VOLATILITY_TASK", "INPUT_NOISE_STD", "TARGET_NOISE_STD",
    "MSE_LOSS", "HUBER_BETA", "CHARBONNIER_LOSS",
    "STEP_DECAY_ALPHA",
    "POLICY_KWARGS", "ACTIVATION_FN",
}
INTERNAL_PARAMS = {
    "EVAL_EVERY", "TARGET_MODE", "EVAL_MODE",
    "CHANNEL_AGGREGATION", "HIDDEN_SIZE", "BRANCH_HIDDEN",
    "SMOKE_BATCH", "SMOKE_SEQ_LEN", "SMOKE_FEATURES",
}


def find_hyperparams_section_lines(content: str) -> tuple[int, int] | None:
    """Return (start_line, end_line) 0-indexed for HYPERPARAMETERS section."""
    lines = content.split("\n")
    start = None
    end = None
    for i, line in enumerate(lines):
        if "HYPERPARAMETERS" in line and "—" in line:
            start = i
        if start is not None and line.startswith("def build_cfg"):
            end = i
            break
    if start is None or end is None:
        return None
    return start, end


def _parse_nn_env_to_cfg(content: str) -> set[str]:
    """Extract parameter names from _NN_ENV_TO_CFG mapping.

    _NN_ENV_TO_CFG is a tuple of ("NN_*", "PARAM_NAME") pairs — the second
    element is the global variable name that already has NN_* env override.
    """
    env_cfg_names: set[str] = set()
    for node in ast.walk(ast.parse(content)):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "_NN_ENV_TO_CFG":
                # node.value is a ast.Tuple of ast.Tuple pairs
                if isinstance(node.value, (ast.Tuple, ast.List)):
                    for elt in node.value.elts:
                        if isinstance(elt, (ast.Tuple, ast.List)) and len(elt.elts) >= 2:
                            param_node = elt.elts[1]
                            if isinstance(param_node, ast.Constant):
                                env_cfg_names.add(str(param_node.value))
                break
    return env_cfg_names


def analyze_hyperparameters(content: str):
    """AST analysis of HYPERPARAMETERS section. Returns (hardcoded_params, configurable_names, env_covered_names) or None."""
    section = find_hyperparams_section_lines(content)
    if section is None:
        return None

    start_line, end_line = section

    tree = ast.parse(content)
    hardcoded = {}
    configurable = set()

    # Parameters covered by _NN_ENV_TO_CFG (have NN_* override via _apply_nn_env_overrides)
    env_covered = _parse_nn_env_to_cfg(content)

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        if not hasattr(node, "lineno"):
            continue
        # Only consider nodes within the HYPERPARAMETERS section
        if not (start_line < node.lineno <= end_line):
            continue

        if isinstance(node, ast.Assign):
            targets = node.targets
            value_node = node.value
        else:
            targets = [node.target]
            value_node = node.value

        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            name = target.id
            if not name.isupper() or name.startswith("_"):
                continue

            # Check if it's a _ev() call
            if isinstance(value_node, ast.Call):
                if isinstance(value_node.func, ast.Name) and value_node.func.id == "_ev":
                    configurable.add(name)
                    continue
                # It's a constant reference like SEQUENCE_LENGTH
                if isinstance(value_node.func, ast.Name):
                    configurable.add(value_node.func.id)
                    continue
            elif isinstance(value_node, ast.Name):
                # Referencing another constant (e.g. SMOKE_SEQ_LEN = SEQUENCE_LENGTH)
                configurable.add(value_node.id)  # referenced constant
                configurable.add(name)            # current var also references it
                continue

            # Already covered by _NN_ENV_TO_CFG → not truly hardcoded
            if name in env_covered:
                configurable.add(name)
                continue

            # Hardcoded value
            try:
                val = ast.unparse(value_node)
            except Exception:
                val = "<complex>"
            hardcoded[name] = val

    return hardcoded, configurable, env_covered


def _extract_env_reads_in_build(content: str) -> set[str]:
    """Find os.environ.get("NN_XXX") calls in workspace code; return the param names."""
    covered: set[str] = set()
    tree = ast.parse(content)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # Match os.environ.get("NN_XXX", ...)
        if not (isinstance(node.func, ast.Attribute) and node.func.attr == "get"):
            continue
        obj = node.func.value
        if not (isinstance(obj, ast.Attribute) and obj.attr == "environ"):
            continue
        if not isinstance(obj.value, ast.Name) or obj.value.id != "os":
            continue
        if node.args and isinstance(node.args[0], ast.Constant):
            env_name = str(node.args[0].value)
            if env_name.startswith("NN_"):
                covered.add(env_name[3:])  # strip NN_ prefix
    return covered


def _find_build_methods(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Find build_* method definitions in the AST."""
    methods: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("build_") or "build" in node.name.lower():
                methods.append(node)
    return methods


def _find_os_environ_defaults(content: str) -> dict[str, str]:
    """Find os.environ.get("NN_XXX", default_val) patterns; return {param_name: default_val}."""
    defaults: dict[str, str] = {}
    tree = ast.parse(content)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Attribute) and node.func.attr == "get"):
            continue
        obj = node.func.value
        if not (isinstance(obj, ast.Attribute) and obj.attr == "environ"):
            continue
        if not isinstance(obj.value, ast.Name) or obj.value.id != "os":
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        env_name = str(node.args[0].value)
        if not env_name.startswith("NN_"):
            continue
        # Get default value (second arg)
        if len(node.args) >= 2:
            try:
                default_val = ast.unparse(node.args[1])
            except Exception:
                default_val = "<complex>"
        else:
            default_val = "<no default>"
        param_name = env_name[3:]  # NN_NET_ARCH -> NET_ARCH
        defaults[param_name] = default_val
    return defaults


def _find_module_level_dicts(content: str) -> dict[str, str]:
    """Find module-level dict constants (e.g. POLICY_KWARGS = {...}) that may contain defaults."""
    dicts: dict[str, str] = {}
    tree = ast.parse(content)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.isupper() and isinstance(node.value, ast.Dict):
                try:
                    dicts[target.id] = ast.unparse(node.value)
                except Exception:
                    dicts[target.id] = "<complex>"
    return dicts


def analyze_workspace(repo_root: Path, train_env_covered: set[str]) -> dict[str, str]:
    """Scan workspace/__init__.py and workspace/*.py for hardcoded defaults in build methods.

    Returns {param_name: default_value} for defaults not already covered by train.py config.
    """
    ws_init = repo_root / "workspace" / "__init__.py"
    if not ws_init.exists():
        return {}

    content = ws_init.read_text(encoding="utf-8")
    env_reads = _extract_env_reads_in_build(content)

    # Also scan workspace submodules that build methods might delegate to
    ws_dir = repo_root / "workspace"
    for py_file in ws_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        try:
            sub_content = py_file.read_text(encoding="utf-8")
            env_reads |= _extract_env_reads_in_build(sub_content)
        except Exception:
            pass

    # Find os.environ.get defaults
    all_defaults: dict[str, str] = {}
    # Scan workspace/__init__.py
    all_defaults.update(_find_os_environ_defaults(content))
    # Scan submodules
    for py_file in ws_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        try:
            all_defaults.update(_find_os_environ_defaults(py_file.read_text(encoding="utf-8")))
        except Exception:
            pass

    # Filter: only report params NOT already covered in train.py
    uncovered = {}
    for name, default_val in all_defaults.items():
        if name in train_env_covered or name in env_reads:
            # Already handled — the param has env override AND the build method reads it
            # But still report if default_val is non-trivial (agent should verify metadata return)
            pass
        uncovered[name] = default_val

    # Also scan function signature defaults (config-only: these should be cfg["X"], not hardcoded)
    sig_defaults = _find_function_signature_defaults(content)
    for py_file in ws_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        try:
            sig_defaults.update(_find_function_signature_defaults(py_file.read_text(encoding="utf-8")))
        except Exception:
            pass
    for name, default_val in sig_defaults.items():
        if name not in uncovered and name not in train_env_covered:
            uncovered[name] = default_val

    return uncovered


def _find_function_signature_defaults(content: str) -> dict[str, str]:
    """Scan function signatures for hardcoded default values (config-only violation).

    Finds patterns like:
        def __init__(self, latent_dim: int = 16, dropout: float = 0.1):
        def from_cfg(cls, cfg: dict, *, c: int, h: int) -> ...:

    Returns {param_name: default_value} for params with numeric/string defaults.
    Skips: self, cls, cfg, *args, **kwargs, params without defaults, trivial defaults (0/1/None/True/False).
    """
    defaults: dict[str, str] = {}
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return defaults

    SKIP_NAMES = frozenset({"self", "cls", "cfg", "args", "kwargs", "shared_context", "source"})

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # Only scan build_*/from_cfg/train_step/predict/evaluate methods
        if not any(kw in node.name for kw in ("build", "from_cfg", "train_step", "predict", "evaluate", "__init__")):
            continue
        args = node.args
        all_args = args.args + args.posonlyargs + args.kwonlyargs
        defaults_list = args.defaults + args.kw_defaults
        # defaults align to the END of all_args
        n_no_default = len(all_args) - len(defaults_list)
        for i, arg in enumerate(all_args):
            if arg.arg in SKIP_NAMES:
                continue
            default_idx = i - n_no_default
            if default_idx < 0:
                continue  # no default
            default_node = defaults_list[default_idx]
            if default_node is None:
                continue
            # Only report numeric/string defaults (not complex expressions)
            if isinstance(default_node, ast.Constant):
                val = repr(default_node.value)
                # Skip trivial defaults (0, 1, None, True, False, empty string)
                if default_node.value in (0, 1, None, True, False, ""):
                    continue
                defaults[arg.arg.upper()] = val
            elif isinstance(default_node, ast.UnaryOp) and isinstance(default_node.op, (ast.USub, ast.UAdd)):
                # Negative numbers: -0.1, -1, etc.
                if isinstance(default_node.operand, ast.Constant):
                    val = repr(default_node.operand.value)
                    if isinstance(default_node.operand.value, (int, float)):
                        defaults[arg.arg.upper()] = f"-{val}" if isinstance(default_node.op, ast.USub) else val

    return defaults


def categorize(name: str, value: str, source: str = "train.py") -> ParamAdvice:
    if name in CRITICAL_PARAMS:
        return ParamAdvice(name, value, f"NN_{name}", "重要实验参数",
                           "对实验结果影响大，建议暴露为环境变量", source)
    if name in EXTENDABLE_PARAMS:
        return ParamAdvice(name, value, f"NN_{name}", "可能扩展的参数",
                           "将来可能需要调优，建议暴露为环境变量", source)
    if name in INTERNAL_PARAMS:
        return ParamAdvice(name, value, "—", "不建议参数化的内部细节",
                           "内部细节或运行时常量，参数化收益低", source)
    return ParamAdvice(name, value, f"NN_{name}", "可能扩展的参数",
                       "未分类参数，建议按可能扩展处理", source)


def main():
    if len(sys.argv) < 2:
        print("用法: analyze_hardcoded_params.py <train.py路径> [repo_root]", file=sys.stderr)
        sys.exit(1)

    train_path = Path(sys.argv[1])
    if not train_path.exists():
        print(f"文件不存在: {train_path}", file=sys.stderr)
        sys.exit(1)

    # repo_root defaults to parent of train.py
    repo_root = Path(sys.argv[2]) if len(sys.argv) >= 3 else train_path.parent

    content = train_path.read_text(encoding="utf-8")
    result = analyze_hyperparameters(content)

    hardcoded: dict[str, str] = {}
    configurable: set[str] = set()
    env_covered: set[str] = set()

    if result is not None:
        hardcoded, configurable, env_covered = result
    else:
        print("未找到 train.py HYPERPARAMETERS 区段，仅扫描 workspace build 方法")

    # Scan workspace for build method defaults
    ws_defaults = analyze_workspace(repo_root, env_covered)

    print(f"\n{'='*60}")
    print("硬编码参数分析 (DEEP mode)")
    print(f"{'='*60}\n")

    if env_covered:
        print(f"train.py 已有 NN_* 覆盖（_NN_ENV_TO_CFG）: {len(env_covered)} 个")
        print()

    if not hardcoded and not ws_defaults:
        print("✅ 所有超参均已配置化（_ev() 或 _NN_ENV_TO_CFG），无硬编码常量发现。")
        if configurable:
            sorted_cfg = sorted(configurable)
            print(f"\n已配置化参数 ({len(sorted_cfg)} 个): {', '.join(sorted_cfg[:15])}" + (" ..." if len(sorted_cfg) > 15 else ""))
        sys.exit(0)

    critical, extendable, internal = [], [], []
    for name, value in sorted(hardcoded.items()):
        advice = categorize(name, value, "train.py")
        if advice.category == "重要实验参数":
            critical.append(advice)
        elif advice.category == "可能扩展的参数":
            extendable.append(advice)
        else:
            internal.append(advice)

    # Workspace build method defaults
    ws_items = []
    for name, value in sorted(ws_defaults.items()):
        advice = categorize(name, value, "workspace/")
        ws_items.append(advice)
        # Also categorize for summary
        if advice.category == "重要实验参数":
            critical.append(advice)
        elif advice.category == "可能扩展的参数":
            extendable.append(advice)
        else:
            internal.append(advice)

    def print_group(title: str, items: list[ParamAdvice]):
        if not items:
            return
        print(f"## {title}")
        print()
        for a in items:
            src_tag = f" ({a.source})" if a.source != "train.py" else ""
            print(f"  • {a.name} = {a.current_value}{src_tag}")
            if a.suggested_env != "—":
                print(f"    → 配置化: {a.suggested_env} (default={a.current_value})")
            else:
                print(f"    → 不建议参数化")
            print(f"    原因: {a.reason}")
            print()

    print_group("重要实验参数 — 建议立即配置化", critical)
    print_group("可能扩展的参数", extendable)
    print_group("不建议参数化的内部细节", internal)

    if ws_items:
        print("## workspace build 方法默认值（os.environ.get 的 fallback）")
        print()
        for a in ws_items:
            print(f"  • {a.name} = {a.current_value}")
            print(f"    → build 方法通过 os.environ.get('NN_{a.name}', ...) 读取，但默认值不记录到 config")
            print(f"    → 建议: 在 build 方法 metadata 中返回此值，或在 train.py 加入 _ev()")
            print()

    total = len(hardcoded) + len(ws_defaults)
    print(f"\n共发现 {total} 个硬编码常量/默认值：{len(critical)} 重要 / {len(extendable)} 可扩展 / {len(internal)} 内部")
    print(f"  train.py 硬编码: {len(hardcoded)} 个")
    print(f"  workspace 默认值: {len(ws_defaults)} 个")
    print(f"  已配置化参数: {len(configurable)} 个（含 _NN_ENV_TO_CFG 覆盖 {len(env_covered)} 个）")
    print("提示: 以上为基于规则的静态分析，仅供参考。")


if __name__ == "__main__":
    main()
