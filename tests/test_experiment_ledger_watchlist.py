"""tests/test_experiment_ledger_watchlist.py — _load_ledger_watchlist() 单元测试"""
import sys
import pathlib
import pytest

# experiment.py lives in template/package/
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "template" / "package"))


@pytest.fixture
def tmp_repo_root(monkeypatch, tmp_path):
    """创建临时项目根，含 nn-config.yaml（可选）；返回 root"""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_load_returns_empty_when_no_yaml(tmp_repo_root):
    """无 nn-config.yaml → 返回 ()"""
    from experiment import _load_ledger_watchlist
    assert _load_ledger_watchlist() == ()


def test_load_returns_empty_when_no_ledger_section(tmp_repo_root):
    """有 yaml 但无 ledger 段 → 返回 ()"""
    (tmp_repo_root / "nn-config.yaml").write_text("profile: supervised\n")
    from experiment import _load_ledger_watchlist
    assert _load_ledger_watchlist() == ()


def test_load_returns_watchlist_from_yaml(tmp_repo_root):
    """有 yaml + ledger.watchlist → 返回 tuple"""
    (tmp_repo_root / "nn-config.yaml").write_text(
        "ledger:\n  watchlist:\n    - LR\n    - BATCH_SIZE\n"
    )
    from experiment import _load_ledger_watchlist
    assert _load_ledger_watchlist() == ("LR", "BATCH_SIZE")


def test_load_returns_empty_when_yaml_malformed(tmp_repo_root):
    """yaml 损坏 → 返回 ()（不抛异常）"""
    (tmp_repo_root / "nn-config.yaml").write_text(":\n  bad: [unclosed\n")
    from experiment import _load_ledger_watchlist
    assert _load_ledger_watchlist() == ()


def test_load_skips_non_list_watchlist(tmp_repo_root):
    """watchlist 不是 list → 返回 ()"""
    (tmp_repo_root / "nn-config.yaml").write_text('ledger:\n  watchlist: "LR"\n')
    from experiment import _load_ledger_watchlist
    assert _load_ledger_watchlist() == ()


def test_load_strips_whitespace_and_skips_empty(tmp_repo_root):
    """strip + skip empty"""
    (tmp_repo_root / "nn-config.yaml").write_text(
        'ledger:\n  watchlist:\n    - " LR "\n    - ""\n    - 42\n'
    )
    from experiment import _load_ledger_watchlist
    assert _load_ledger_watchlist() == ("LR", "42")
