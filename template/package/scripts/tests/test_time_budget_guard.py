"""时间预算取值点守卫（spec 20260826_1400 §4 验收 1-3）。

回归保证：NN_TIME_BUDGET 与 nn-config.yaml 不一致 → RuntimeError 拒启 +
_runs/time_budget_violations.log 留痕；一致 / 无 env → 放行返回 yaml 值。
唯一真值 = nn-config.yaml:time_budget（缺省 3600）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]  # scripts/tests/ → package 根
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from experiment import _resolve_time_budget  # noqa: E402


def _make_repo(tmp_path: Path, time_budget: int | None) -> Path:
    """最小 fixture 仓：一个 nn-config.yaml 即可（profile 等字段非守卫所需）。"""
    if time_budget is None:
        (tmp_path / "nn-config.yaml").write_text("profile: supervised\n", encoding="utf-8")
    else:
        (tmp_path / "nn-config.yaml").write_text(
            f"profile: supervised\ntime_budget: {time_budget}\n", encoding="utf-8"
        )
    return tmp_path


def _violations_lines(repo: Path) -> list[str]:
    f = repo / "_runs" / "time_budget_violations.log"
    if not f.exists():
        return []
    return [ln for ln in f.read_text(encoding="utf-8").splitlines() if ln.strip()]


# ── 验收 1：env ≠ yaml → 拒启 + 留痕 ───────────────────────────────

def test_env_mismatch_raises_and_logs(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path, time_budget=600)
    monkeypatch.setenv("NN_TIME_BUDGET", "7200")
    with pytest.raises(RuntimeError, match="Config-Only"):
        _resolve_time_budget(repo)
    lines = _violations_lines(repo)
    assert len(lines) == 1
    assert "7200" in lines[0] and "600" in lines[0]  # env 值与 yaml 值都留在行内


def test_env_non_integer_also_refused(tmp_path, monkeypatch):
    """非整数预置（如 '1h'）同样拒启——不静默回退 yaml。"""
    repo = _make_repo(tmp_path, time_budget=600)
    monkeypatch.setenv("NN_TIME_BUDGET", "1h")
    with pytest.raises(RuntimeError, match="Config-Only"):
        _resolve_time_budget(repo)
    assert len(_violations_lines(repo)) == 1


# ── 验收 2：env == yaml → 放行 ─────────────────────────────────────

def test_env_equal_yaml_passes(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path, time_budget=600)
    monkeypatch.setenv("NN_TIME_BUDGET", "600")
    assert _resolve_time_budget(repo) == 600
    assert _violations_lines(repo) == []


# ── 验收 3：无 env → 放行（默认路径） ──────────────────────────────

def test_no_env_returns_yaml_value(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path, time_budget=1800)
    monkeypatch.delenv("NN_TIME_BUDGET", raising=False)
    assert _resolve_time_budget(repo) == 1800
    assert _violations_lines(repo) == []


def test_yaml_missing_defaults_3600(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path, time_budget=None)
    monkeypatch.delenv("NN_TIME_BUDGET", raising=False)
    assert _resolve_time_budget(repo) == 3600
