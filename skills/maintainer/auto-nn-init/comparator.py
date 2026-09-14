"""Compare project contract/workspace methods against template profile boundaries."""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import TypedDict


class MethodInfo(TypedDict):
    name: str
    signature: str
    has_body: bool
    is_property: bool
    is_notimplemented: bool


def _maintainer_template_pkg() -> Path:
    """Path to installable template package inside the maintainer repo."""
    repo = Path(__file__).resolve().parents[2]
    if (repo / "template" / "package" / "experiment.py").is_file():
        return repo / "template" / "package"
    if (repo / "template" / "experiment.py").is_file():
        return repo / "template"
    return repo


class MethodComparison(TypedDict):
    method: str
    project_exists: bool
    project_implementation: str | None
    project_signature: str | None
    template_signature: str | None
    action: str


def extract_methods(file_path: str | Path) -> dict[str, MethodInfo]:
    """Extract all method definitions from a Python file."""
    code = Path(file_path).read_text(encoding="utf-8")
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return _extract_methods_regex(code)

    methods: dict[str, MethodInfo] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    is_property = any(
                        isinstance(dec, ast.Name) and dec.id == "property"
                        for dec in item.decorator_list
                    )
                    methods[item.name] = MethodInfo(
                        name=item.name,
                        signature=_get_signature(item),
                        has_body=len(item.body) > 0,
                        is_property=is_property,
                        is_notimplemented=_is_notimplemented(item),
                    )

    return methods


def _extract_methods_regex(code: str) -> dict[str, MethodInfo]:
    """Fallback regex extraction when AST parsing fails."""
    methods: dict[str, MethodInfo] = {}
    pattern = r'(@property\s+)?def\s+(\w+)\s*\([^)]*\)\s*(?:->\s*\w+)?\s*:\s*\.\.\.?'

    for m in re.finditer(pattern, code):
        is_property = m.group(1) is not None
        name = m.group(2)
        body_is_ellipsis = m.group(3) is not None
        methods[name] = MethodInfo(
            name=name,
            signature=m.group(0).split(":")[0] + ":",
            has_body=not body_is_ellipsis,
            is_property=is_property,
            is_notimplemented=body_is_ellipsis,
        )
    return methods


def _get_signature(node: ast.FunctionDef) -> str:
    args = [a.arg for a in node.args.args]
    return f"def {node.name}({', '.join(args)})"


def _is_notimplemented(node: ast.FunctionDef) -> bool:
    if len(node.body) == 1:
        if isinstance(node.body[0], ast.Expr):
            val = node.body[0].value
            if isinstance(val, ast.Constant) and val.value is ...:
                return True
            if isinstance(val, ast.Name) and val.id == "NotImplementedError":
                return True
    return False


def compare_side(
    project_methods: dict[str, MethodInfo],
    template_methods: list[str],
    template_class_code: str | None = None,
) -> list[MethodComparison]:
    """Compare project methods against template expected methods."""
    results: list[MethodComparison] = []

    for method_name in template_methods:
        proj = project_methods.get(method_name)

        if proj is None:
            results.append(MethodComparison(
                method=method_name,
                project_exists=False,
                project_implementation=None,
                project_signature=None,
                template_signature=None,
                action="新增",
            ))
        elif proj["is_notimplemented"]:
            results.append(MethodComparison(
                method=method_name,
                project_exists=True,
                project_implementation="替换",
                project_signature=proj["signature"],
                template_signature=None,
                action="替换",
            ))
        else:
            results.append(MethodComparison(
                method=method_name,
                project_exists=True,
                project_implementation="保留",
                project_signature=proj["signature"],
                template_signature=None,
                action="保留",
            ))

    return results


def check_train_encapsulation(train_py_path: str | Path) -> list[dict]:
    """检查 train.py 是否直接 import 了 workspace 内部模块（与 preflight G-封装 同规则）。"""
    import sys

    pkg = _maintainer_template_pkg()
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))
    from experiment import _check_train_encapsulation

    return _check_train_encapsulation(train_py_path)


def check_train_exp_dir_gate(repo_root: str | Path) -> list[dict]:
    """G-路径：train.py 须使用 _runs/exp。"""
    import sys

    pkg = _maintainer_template_pkg()
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))
    from experiment import check_train_exp_dir_layout

    return [
        {"rule": v.rule, "detail": v.detail, "fix": v.fix}
        for v in check_train_exp_dir_layout(repo_root)
    ]


def check_profile_facade_gate(repo_root: str | Path) -> list[dict]:
    """G-门面：profiles.yaml forbidden / 必填方法。"""
    import sys

    pkg = _maintainer_template_pkg()
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))
    from experiment import check_profile_facade

    return [
        {"rule": v.rule, "detail": v.detail, "fix": v.fix}
        for v in check_profile_facade(repo_root)
    ]


def check_test_authority_gate(repo_root: str | Path) -> list[dict]:
    """G-评估：contract.test 权威（与 preflight 同源）。"""
    import sys

    pkg = _maintainer_template_pkg()
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))
    from experiment import check_test_authority

    return [
        {"rule": v.rule, "detail": v.detail, "fix": v.fix}
        for v in check_test_authority(repo_root)
    ]


def check_rl_workspace_gate(repo_root: str | Path) -> list[dict]:
    """RL：D2 prepare_data、E3 evaluate→contract.test（见 scripts/rl_workspace_gate.py）。"""
    import subprocess
    import sys

    script = Path(repo_root) / "scripts" / "rl_workspace_gate.py"
    if not script.is_file():
        script = _maintainer_template_pkg() / "scripts" / "rl_workspace_gate.py"
    if not script.is_file():
        return [{"rule": "D2", "detail": "缺少 rl_workspace_gate.py", "fix": "governance-sync.sh"}]

    r = subprocess.run(
        [sys.executable, str(script), str(Path(repo_root).resolve())],
        capture_output=True,
        text=True,
    )
    if r.returncode == 0:
        return []
    violations: list[dict] = []
    for line in (r.stderr or "").splitlines():
        m = re.match(r"\[(D2|E3)\] (.+) → (.+)$", line.strip())
        if m:
            violations.append({"rule": m.group(1), "detail": m.group(2), "fix": m.group(3)})
    if not violations:
        violations.append({"rule": "E3", "detail": r.stderr or "RL workspace gate failed", "fix": "python3 scripts/rl_workspace_gate.py ."})
    return violations


def check_root_py_layout(repo_root: str | Path) -> list[str]:
    """根目录非白名单 .py（与 preflight G-布局 同规则，返回文件名列表）。"""
    import sys

    pkg = _maintainer_template_pkg()
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))
    from experiment import _list_unexpected_root_py

    return _list_unexpected_root_py(Path(repo_root))


def _append_rule_violation_table(
    lines: list[str],
    title: str,
    violations: list[dict],
) -> None:
    """渲染 rule/detail/fix 形违规（G-路径、G-门面、G-评估）。"""
    lines.append(title)
    lines.append("| 规则 | 问题 | 修复 |")
    lines.append("|------|------|------|")
    for v in violations:
        lines.append(f"| {v['rule']} | {v['detail']} | {v['fix']} |")


def build_comparison_table(
    contract_comparison: list[MethodComparison],
    workspace_comparison: list[MethodComparison],
    experiment_injections: list[str],
    train_violations: list[dict] | None = None,
    exp_dir_violations: list[dict] | None = None,
    facade_violations: list[dict] | None = None,
    root_py_unexpected: list[str] | None = None,
    test_authority_violations: list[dict] | None = None,
) -> str:
    """Build a markdown comparison table."""
    lines: list[str] = []

    lines.append("## contract/ 方法对照\n")
    lines.append("| 方法 | 项目现有 | 模板对应 | 操作 |")
    lines.append("|------|---------|---------|------|")
    for c in contract_comparison:
        impl = c["project_implementation"] or "—"
        lines.append(f"| `{c['method']}` | {impl} | raise NotImplementedError | {c['action']} |")

    lines.append("\n## workspace/ 方法对照\n")
    lines.append("| 方法 | 项目现有 | 模板对应 | 操作 |")
    lines.append("|------|---------|---------|------|")
    for c in workspace_comparison:
        impl = c["project_implementation"] or "—"
        lines.append(f"| `{c['method']}` | {impl} | raise NotImplementedError | {c['action']} |")

    if experiment_injections:
        lines.append("\n## experiment.py 需要注入的方法\n")
        for m in experiment_injections:
            lines.append(f"- `{m}`")

    if train_violations:
        encap = [v for v in train_violations if "line" in v]
        other = [v for v in train_violations if "line" not in v and "rule" in v]
        if encap:
            lines.append("\n## ⚠️ train.py 封装违规（G-封装）\n")
            lines.append("| 行 | 违规代码 | 子模块 | 修复建议 |")
            lines.append("|---|---------|------|---------|")
            for v in encap:
                lines.append(f"| {v['line']} | ``{v['text']}`` | `{v['module']}` | {v['fix']} |")
        if other:
            _append_rule_violation_table(
                lines,
                "\n## ⚠️ train.py 其它硬门禁\n",
                other,
            )

    if exp_dir_violations:
        _append_rule_violation_table(
            lines,
            "\n## ❌ train.py 实验目录（G-路径，硬失败）\n",
            exp_dir_violations,
        )

    if facade_violations:
        _append_rule_violation_table(
            lines,
            "\n## ❌ 门面契约（G-门面，硬失败）\n",
            facade_violations,
        )

    if root_py_unexpected:
        lines.append("\n## ⚠️ 根目录 .py 布局（G-布局，建议）\n")
        lines.append("以下文件不在根目录白名单内，应移到 `workspace/scripts/` 或删除：\n")
        for name in root_py_unexpected:
            lines.append(f"- `{name}`")

    if test_authority_violations:
        _append_rule_violation_table(
            lines,
            "\n## ❌ contract.test 权威（G-评估，硬失败）\n",
            test_authority_violations,
        )

    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    print(
        "Deprecated: use migration-compare.py or scripts/migration-compare.sh\n"
        "  python3 migration-compare.py --template-root <T> --project-root <P>",
        file=sys.stderr,
    )
    if len(sys.argv) < 3:
        sys.exit(1)

    contract_methods = extract_methods(sys.argv[1])
    workspace_methods = extract_methods(sys.argv[2])

    print("contract methods:", list(contract_methods.keys()))
    print("workspace methods:", list(workspace_methods.keys()))
