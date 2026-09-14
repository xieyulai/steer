"""T-A2: append-init-qa-log.py 防漂移到 template/package。

L4 fashionmnist-raw debug 暴露的真实 bug：
cd 到模板仓后调 append-init-qa-log.py，args.repo_root 默认 Path.cwd()，
结果 init-qa-log.md 写到模板仓而非业务仓副本。

修复：3 道防线（spec T-A2）
1. --repo-root 默认 None（不传时与 cwd 不一致则 warn + 拒绝）
2. 拒绝 template/package 路径：SystemExit
3. template/package/.gitignore 加 .auto-nn/ 兜底
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
SCRIPT = SCRIPTS / "append-init-qa-log.py"


def _run(*args, expect_ok=True, cwd=None):
    """调脚本，capture stdout/stderr/returncode。"""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, cwd=cwd or str(SCRIPTS),
    )
    return result


# === A2 防线 1: cwd 是 template/package 时拒绝 ===

def test_reject_template_package_repo_root():
    """A2 spec: --repo-root 显式指向 template/package 时必须 SystemExit。"""
    tmpl = SCRIPTS  # template/package/scripts 即 template/package 的一部分
    # 解析到 template/package 根（scripts 的 parent）
    tmpl_root = SCRIPTS.parent
    # 验证：str 路径里含 'template/package'
    assert "template/package" in str(tmpl_root.resolve())
    result = _run("init-header", "--repo-root", str(tmpl_root), "--workflow", "migrate",
                  "--target-root", "/tmp/dummy_target_root")
    assert result.returncode != 0, (
        f"应 SystemExit 拒绝 template/package 路径，实际 rc={result.returncode}\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    # 错误信息应提示 template/package
    combined = result.stdout + result.stderr
    assert "template/package" in combined or "ERROR" in combined.upper(), (
        f"错误信息应含 template/package 或 ERROR，实际:\n{combined}"
    )


def test_reject_template_package_via_cwd():
    """A2 spec: cwd 是 template/package/scripts 时不传 --repo-root 也应拒绝。"""
    # cwd = template/package/scripts
    result = _run("init-header", "--workflow", "migrate", "--target-root", "/tmp/dummy_target_root")
    # 不传 --repo-root → 默认 Path.cwd() = template/package/scripts（属于 template/package）
    # spec: 应 SystemExit
    assert result.returncode != 0, (
        f"应 SystemExit 拒绝 cwd=template/package 路径，实际 rc={result.returncode}\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )


# === A2 防线 2: 正常路径正常工作 ===

def test_normal_path_works(tmp_path):
    """A2 spec: --repo-root 指向业务仓（不含 template/package）时正常写 init-qa-log.md。"""
    # tmp_path 显然不含 template/package
    assert "template/package" not in str(tmp_path)
    result = _run("init-header", "--repo-root", str(tmp_path), "--workflow", "migrate",
                  "--target-root", str(tmp_path))
    assert result.returncode == 0, (
        f"正常路径应成功，实际 rc={result.returncode}\n"
        f"stdout={result.stdout!r}\nstderr={result.stderr!r}"
    )
    log_file = tmp_path / ".auto-nn" / "init-qa-log.md"
    assert log_file.is_file(), f"应生成 {log_file}"


# === A2 防线 3: .gitignore 兜底 ===

def test_template_package_gitignore_exists():
    """A2 spec: template/package/.gitignore 必须存在并忽略 .auto-nn/。"""
    gitignore = SCRIPTS.parent / ".gitignore"
    assert gitignore.is_file(), f"应有 {gitignore}"
    content = gitignore.read_text(encoding="utf-8")
    assert ".auto-nn/" in content, f".gitignore 应含 .auto-nn/ 兜底:\n{content}"


# === A2 regression: append/close 同样拒绝 ===

def test_reject_template_package_on_append():
    """A2 spec: append 子命令也拒绝 template/package 路径。"""
    tmpl_root = SCRIPTS.parent
    result = _run("append", "--repo-root", str(tmpl_root),
                  "--step", "0", "--slug", "test", "--theme", "t",
                  "--ask", "a", "--user", "u", "--lock", "ok")
    assert result.returncode != 0


def test_reject_template_package_on_close():
    """A2 spec: close 子命令也拒绝 template/package 路径。"""
    tmpl_root = SCRIPTS.parent
    result = _run("close", "--repo-root", str(tmpl_root), "--user", "u")
    assert result.returncode != 0
