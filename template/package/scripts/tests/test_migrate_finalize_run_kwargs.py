"""migrate_finalize_run_kwargs：根级 train.py 去掉 finalize_run(best_metrics=)。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

DIRTY = '''\
def f():
    contract.finalize_run(
        repo_root=root,
        cfg=cfg,
        best_metrics=dummy,
        precomputed_official_metrics=official,
    )
'''

DIRTY_ONLY_BEST = '''\
def f():
    contract.finalize_run(repo_root=root, cfg=cfg, best_metrics=dummy)
'''

CLEAN = '''\
def f():
    contract.finalize_run(
        repo_root=root,
        cfg=cfg,
        precomputed_official_metrics=official,
    )
'''

UNPARSEABLE = '''\
def f():
    contract.finalize_run(best_metrics=x, **kwargs)
'''


def test_scan_finds_best_metrics(tmp_path):
    from lib.migrate_finalize_run_kwargs import scan_train_py
    p = tmp_path / "train.py"
    p.write_text(DIRTY, encoding="utf-8")
    hits = scan_train_py(p)
    assert hits and any("best_metrics" in h for h in hits)


def test_scan_clean(tmp_path):
    from lib.migrate_finalize_run_kwargs import scan_train_py
    p = tmp_path / "train.py"
    p.write_text(CLEAN, encoding="utf-8")
    assert scan_train_py(p) == []


def test_apply_removes_best_keeps_precomputed(tmp_path):
    from lib.migrate_finalize_run_kwargs import apply_train_py, scan_train_py
    p = tmp_path / "train.py"
    p.write_text(DIRTY, encoding="utf-8")
    apply_train_py(p, backup=True)
    assert (tmp_path / "train.py.bak").is_file()
    text = p.read_text(encoding="utf-8")
    assert "best_metrics" not in text
    assert "precomputed_official_metrics" in text
    assert scan_train_py(p) == []


def test_apply_renames_best_to_precomputed(tmp_path):
    from lib.migrate_finalize_run_kwargs import apply_train_py, scan_train_py
    p = tmp_path / "train.py"
    p.write_text(DIRTY_ONLY_BEST, encoding="utf-8")
    apply_train_py(p, backup=False)
    text = p.read_text(encoding="utf-8")
    assert "best_metrics" not in text
    assert "precomputed_official_metrics=dummy" in text.replace(" ", "")
    assert scan_train_py(p) == []


def test_apply_unparseable_raises_no_half_write(tmp_path):
    from lib.migrate_finalize_run_kwargs import apply_train_py
    p = tmp_path / "train.py"
    p.write_text(UNPARSEABLE, encoding="utf-8")
    before = p.read_text(encoding="utf-8")
    with pytest.raises(Exception):
        apply_train_py(p, backup=True)
    assert p.read_text(encoding="utf-8") == before


def test_main_scan_exit_codes(tmp_path):
    from lib.migrate_finalize_run_kwargs import main
    root = tmp_path
    (root / "train.py").write_text(DIRTY, encoding="utf-8")
    assert main([str(root)]) == 1
    (root / "train.py").write_text(CLEAN, encoding="utf-8")
    assert main([str(root)]) == 0
