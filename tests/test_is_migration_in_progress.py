"""tests/test_is_migration_in_progress.py — 迁移未完成 ⇔ 根有 CHECKLIST.md"""
import sys
import pathlib

import pytest

# explore_objective.py 在 template/package/scripts/lib/ 下
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "template" / "package" / "scripts"))
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "template" / "package" / "scripts" / "lib"))


def test_returns_true_when_checklist_md_exists(tmp_path):
    """CHECKLIST.md 存在 → True（旧约定）"""
    from explore_objective import is_migration_in_progress
    (tmp_path / "CHECKLIST.md").write_text("# migration\n")
    assert is_migration_in_progress(tmp_path) is True


def test_returns_false_when_completed_checklist_glob(tmp_path):
    """migration-completed-checklist-<ts>.md 存在（根无 CHECKLIST.md）→ False。
    完成信号件 = 迁移已完成 → 不在迁移中（spec §2.2）；纠正 764816d 的反向读取。"""
    from explore_objective import is_migration_in_progress
    auto_nn = tmp_path / ".auto-nn"
    auto_nn.mkdir()
    (auto_nn / "migration-completed-checklist-20260706-120000.md").write_text("# done\n")
    assert is_migration_in_progress(tmp_path) is False


def test_returns_false_when_neither(tmp_path):
    """两者都无 → False（典型迁后项目）"""
    from explore_objective import is_migration_in_progress
    assert is_migration_in_progress(tmp_path) is False


def test_returns_false_when_only_unrelated_files(tmp_path):
    """.auto-nn/ 存在但无 migration-completed-checklist-*.md → False"""
    from explore_objective import is_migration_in_progress
    auto_nn = tmp_path / ".auto-nn"
    auto_nn.mkdir()
    (auto_nn / "abcde-guidance.yaml").write_text("a: b\n")
    assert is_migration_in_progress(tmp_path) is False


def test_any_completed_checklist_glob_means_done(tmp_path):
    """完成信号件多 ts 共存 → 仍视为已完成（False）；glob 命中即完成，不在迁移中。"""
    from explore_objective import is_migration_in_progress
    auto_nn = tmp_path / ".auto-nn"
    auto_nn.mkdir()
    (auto_nn / "migration-completed-checklist-20260701-100000.md").write_text("a")
    (auto_nn / "migration-completed-checklist-20260705-150000.md").write_text("b")
    (auto_nn / "other-file.md").write_text("c")
    assert is_migration_in_progress(tmp_path) is False
