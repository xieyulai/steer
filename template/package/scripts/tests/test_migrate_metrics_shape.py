"""v1.33.0 — migrate_metrics_shape.py 单测。"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.lib.migrate_metrics_shape import (
    migrate_file,
    migrate_repo,
    needs_migration,
    rewrite_text,
)


def test_rewrite_workspace_kind_supervised_to_metrics_shape():
    src = 'dispatch_test_call(workspace_kind="supervised", shared_context={})'
    expected = 'dispatch_test_call(metrics_shape="evaluate_learner", shared_context={})'
    assert rewrite_text(src) == expected


def test_rewrite_workspace_kind_adapter_to_metrics_shape():
    src = "dispatch_test_call(workspace_kind='adapter', shared_context={})"
    expected = "dispatch_test_call(metrics_shape='evaluate_runner', shared_context={})"
    assert rewrite_text(src) == expected


def test_rewrite_workspace_kind_mammoth_cl_to_evaluate_learner_with_note():
    src = 'dispatch_test_call(workspace_kind="mammoth_cl", shared_context={})'
    result = rewrite_text(src)
    assert 'metrics_shape="evaluate_learner"' in result
    assert "framework_kind=MAMMOTH" in result


def test_rewrite_yaml_kind_field():
    src = "workspace:\n  kind: supervised\n  device: cuda\n"
    result = rewrite_text(src)
    assert "metrics_shape: evaluate_learner" in result
    assert "kind: supervised" not in result


def test_rewrite_idempotent():
    already = 'dispatch_test_call(metrics_shape="evaluate_learner", shared_context={})'
    assert rewrite_text(already) == already


def test_needs_migration_true_for_supervised():
    assert needs_migration('x = workspace_kind="supervised"') is True


def test_needs_migration_true_for_yaml_kind():
    assert needs_migration("workspace:\n  kind: adapter\n") is True


def test_needs_migration_false_for_clean_file():
    assert needs_migration("metrics_shape = MetricsShape.EVALUATE_LEARNER\n") is False


def test_migrate_file_creates_backup(tmp_path):
    target = tmp_path / "train_branch.py"
    target.write_text('dispatch_test_call(workspace_kind="supervised", ws=ws)\n',
                      encoding="utf-8")
    modified = migrate_file(target, backup=True)
    assert modified is True
    assert target.with_suffix(target.suffix + ".bak").exists()
    assert 'metrics_shape="evaluate_learner"' in target.read_text(encoding="utf-8")


def test_migrate_file_no_backup_skips_bak(tmp_path):
    target = tmp_path / "train_branch.py"
    target.write_text('dispatch_test_call(workspace_kind="adapter", ws=ws)\n',
                      encoding="utf-8")
    modified = migrate_file(target, backup=False)
    assert modified is True
    assert not target.with_suffix(target.suffix + ".bak").exists()


def test_migrate_file_dry_run_does_not_write(tmp_path):
    target = tmp_path / "train_branch.py"
    original = 'dispatch_test_call(workspace_kind="supervised", ws=ws)\n'
    target.write_text(original, encoding="utf-8")
    modified = migrate_file(target, dry_run=True)
    assert modified is True
    assert target.read_text(encoding="utf-8") == original


def test_migrate_repo_processes_multiple_files(tmp_path):
    (tmp_path / "a.py").write_text('workspace_kind="supervised"\n', encoding="utf-8")
    (tmp_path / "b.py").write_text('workspace_kind="adapter"\n', encoding="utf-8")
    (tmp_path / "clean.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "nn-config.yaml").write_text("workspace:\n  kind: supervised\n",
                                              encoding="utf-8")
    count = migrate_repo(tmp_path, backup=False)
    assert count == 3