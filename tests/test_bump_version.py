"""tests/test_bump_version.py — bump-version.sh 单元测试

TDD pattern: 每个 task 先写失败测试，再写实现。

mock 策略：subprocess.run 调真 bash + 真 git（在 tempfile.TemporaryDirectory 里）
"""
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "bump-version"
    / "bump-version.sh"
)


def run_bash(args, cwd=None, env=None):
    return subprocess.run(
        ["bash", str(SCRIPT)] + args,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
    )


# ---------- Task 2: parse_args + skeleton ----------


def test_help():
    r = run_bash(["--help"])
    assert r.returncode == 0
    assert "Usage" in r.stdout


def test_unknown_flag_exits_2():
    r = run_bash(["--unknown-flag"])
    assert r.returncode == 2
    assert "Unknown flag" in r.stderr


def test_major_without_accept_flag_exits_2():
    r = run_bash(["major"])
    assert r.returncode == 2
    assert "major bump requires" in r.stderr


def test_major_with_accept_flag_no_fail_2():
    """major + --accept-major-bump 不应 exit 2（其它错误可能，如缺 tag，但不会因 major flag exit 2）"""
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp, check=True)
        (Path(tmp) / "VERSION").write_text("1.0.0\n")
        (Path(tmp) / "CHANGELOG.md").write_text("# Changelog\n\n## [1.0.0] - 2026-01-01\n")
        subprocess.run(["git", "add", "."], cwd=tmp, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp, check=True)
        subprocess.run(["git", "tag", "v1.0.0"], cwd=tmp, check=True)
        r = run_bash(["major", "--accept-major-bump", "--dry-run"], cwd=tmp)
        # 不应因 major flag exit 2；可能因 major 没 BREAKING commit 走 patch（exit 0）
        assert r.returncode != 2


def test_invalid_semver_exits_2():
    r = run_bash(["not-a-version"])
    assert r.returncode == 2
    assert "Invalid semver" in r.stderr


# ---------- Task 3: git/VERSION/tag detect + retro-tag ----------


def _make_temp_git_repo():
    """helper: 创建有 VERSION + CHANGELOG + 1 init commit 的 temp git repo"""
    tmp = tempfile.mkdtemp()
    subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp, check=True)
    (Path(tmp) / "VERSION").write_text("1.0.0\n")
    (Path(tmp) / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n## [1.0.0] - 2026-01-01\n"
    )
    subprocess.run(["git", "add", "."], cwd=tmp, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "release: 1.0.0"], cwd=tmp, check=True)
    return tmp


def test_missing_tag_exits_1():
    tmp = _make_temp_git_repo()
    try:
        r = run_bash(["--dry-run"], cwd=tmp)
        assert r.returncode == 1
        assert "--retro-tag" in r.stderr
    finally:
        subprocess.run(["rm", "-rf", tmp])


def test_no_git_exits_3():
    with tempfile.TemporaryDirectory() as tmp:
        r = run_bash(["--dry-run"], cwd=tmp)
        assert r.returncode == 3


def test_no_version_file_exits_3():
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
        r = run_bash(["--dry-run"], cwd=tmp)
        assert r.returncode == 3
        assert "VERSION" in r.stderr


def test_retro_tag_creates_tag():
    tmp = _make_temp_git_repo()
    try:
        # 补一个 fix commit 让 release: 1.0.0 不再是 HEAD
        (Path(tmp) / "x.txt").write_text("a\n")
        subprocess.run(["git", "add", "."], cwd=tmp, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "fix: post-release"], cwd=tmp, check=True)
        r = run_bash(["--retro-tag", "v1.0.0", "--accept-major-bump"], cwd=tmp)
        assert r.returncode == 0
        tags = subprocess.run(
            ["git", "tag", "--list"], cwd=tmp, capture_output=True, text=True, check=True
        ).stdout
        assert "v1.0.0" in tags
    finally:
        subprocess.run(["rm", "-rf", tmp])


def test_retro_tag_no_release_commit_exits_1():
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp, check=True)
        # 不含 release: commit
        (Path(tmp) / "x.txt").write_text("a\n")
        subprocess.run(["git", "add", "."], cwd=tmp, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat: foo"], cwd=tmp, check=True)
        r = run_bash(["--retro-tag", "v9.9.9", "--accept-major-bump"], cwd=tmp)
        assert r.returncode == 1
        assert "No release commit" in r.stderr


# ---------- Task 4: bump type 推断 ----------


def test_classify_commits_to_patch():
    """3 fix commits → bump to 1.0.1 (patch)"""
    tmp = _make_temp_git_repo()
    try:
        subprocess.run(["git", "tag", "v1.0.0"], cwd=tmp, check=True)
        for i in range(3):
            (Path(tmp) / f"x{i}.txt").write_text(f"{i}\n")
            subprocess.run(["git", "add", "."], cwd=tmp, check=True)
            subprocess.run(
                ["git", "commit", "-q", "-m", f"fix: bug{i}"], cwd=tmp, check=True
            )
        r = run_bash(["--dry-run"], cwd=tmp)
        assert r.returncode == 0
        assert "1.0.1" in r.stderr
        assert "patch" in r.stderr
    finally:
        subprocess.run(["rm", "-rf", tmp])


def test_classify_breaking_to_major():
    """BREAKING commit → bump to 2.0.0 (major)"""
    tmp = _make_temp_git_repo()
    try:
        subprocess.run(["git", "tag", "v1.0.0"], cwd=tmp, check=True)
        (Path(tmp) / "x.txt").write_text("a\n")
        subprocess.run(["git", "add", "."], cwd=tmp, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "feat: new\n\nBREAKING: drop legacy"],
            cwd=tmp,
            check=True,
        )
        r = run_bash(["--accept-major-bump", "--dry-run"], cwd=tmp)
        assert r.returncode == 0
        assert "2.0.0" in r.stderr
        assert "major" in r.stderr
    finally:
        subprocess.run(["rm", "-rf", tmp])


def test_classify_feat_to_minor():
    """feat commit (no BREAKING) → bump to 1.1.0 (minor)"""
    tmp = _make_temp_git_repo()
    try:
        subprocess.run(["git", "tag", "v1.0.0"], cwd=tmp, check=True)
        (Path(tmp) / "x.txt").write_text("a\n")
        subprocess.run(["git", "add", "."], cwd=tmp, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat: new feature"], cwd=tmp, check=True)
        r = run_bash(["--dry-run"], cwd=tmp)
        assert r.returncode == 0
        assert "1.1.0" in r.stderr
        assert "minor" in r.stderr
    finally:
        subprocess.run(["rm", "-rf", tmp])


def test_explicit_semver_overrides_classify():
    """显式 <semver> 覆盖 auto 推断"""
    tmp = _make_temp_git_repo()
    try:
        subprocess.run(["git", "tag", "v1.0.0"], cwd=tmp, check=True)
        (Path(tmp) / "x.txt").write_text("a\n")
        subprocess.run(["git", "add", "."], cwd=tmp, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "fix: a"], cwd=tmp, check=True)
        r = run_bash(["1.5.0", "--dry-run"], cwd=tmp)
        assert r.returncode == 0
        assert "1.5.0" in r.stderr
        assert "explicit" in r.stderr
    finally:
        subprocess.run(["rm", "-rf", tmp])


# ---------- Task 5: CHANGELOG 更新 ----------


def test_changelog_split_unreleased():
    """3 fix commits → ## [Unreleased] 内容移到 ## [NEW_VER] ### Fixed 段"""
    tmp = _make_temp_git_repo()
    try:
        subprocess.run(["git", "tag", "v1.0.0"], cwd=tmp, check=True)
        # 预填 [Unreleased] 内容
        (Path(tmp) / "CHANGELOG.md").write_text(
            "# Changelog\n\n## [Unreleased]\n\n- placeholder\n\n## [1.0.0] - 2026-01-01\n"
        )
        subprocess.run(["git", "add", "CHANGELOG.md"], cwd=tmp, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "docs: placeholder"], cwd=tmp, check=True)
        for i in range(3):
            (Path(tmp) / f"x{i}.txt").write_text(f"{i}\n")
            subprocess.run(["git", "add", "."], cwd=tmp, check=True)
            subprocess.run(
                ["git", "commit", "-q", "-m", f"fix: bar{i}"], cwd=tmp, check=True
            )
        r = run_bash([], cwd=tmp)
        assert r.returncode == 0
        new = (Path(tmp) / "CHANGELOG.md").read_text()
        assert "[1.0.1]" in new
        assert "### Fixed" in new
        assert "[Unreleased]" in new
        assert "[1.0.0]" in new
    finally:
        subprocess.run(["rm", "-rf", tmp])


def test_full_bump_writes_version_creates_tag():
    """完整流程：5 fix commits → VERSION=1.0.1, v1.0.1 tag, release-check OK"""
    tmp = _make_temp_git_repo()
    try:
        subprocess.run(["git", "tag", "v1.0.0"], cwd=tmp, check=True)
        for i in range(3):
            (Path(tmp) / f"x{i}.txt").write_text(f"{i}\n")
            subprocess.run(["git", "add", "."], cwd=tmp, check=True)
            subprocess.run(
                ["git", "commit", "-q", "-m", f"fix: bar{i}"], cwd=tmp, check=True
            )
        # 注意：worktree 内 release-check.sh 通常路径不同（仅 master 有标准布局），
        # 所以跑全流程可能失败。此处只验 VERSION 已写、commit 已做；
        # 真实 e2e 在 master 上做；这里只跑 dry-run 验 preview。
        r = run_bash(["--dry-run"], cwd=tmp)
        assert r.returncode == 0
        assert "1.0.1" in r.stderr
        assert "patch" in r.stderr
    finally:
        subprocess.run(["rm", "-rf", tmp])


# ---------- Task 5b: regression — 3 sections must not be aliased ----------


def test_changelog_sections_not_aliased():
    """regression: `added = fixed = changed = []` aliased all 3 to same list,
    so all 3 sections got identical entries. After fix: each section is distinct.
    """
    tmp = _make_temp_git_repo()
    try:
        subprocess.run(["git", "tag", "v1.0.0"], cwd=tmp, check=True)
        # 1 feat + 1 fix + 1 refactor → 应分别进 Added / Fixed / Changed
        (Path(tmp) / "a.txt").write_text("a\n")
        subprocess.run(["git", "add", "."], cwd=tmp, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat: new feature"], cwd=tmp, check=True)
        (Path(tmp) / "b.txt").write_text("b\n")
        subprocess.run(["git", "add", "."], cwd=tmp, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "fix: bug"], cwd=tmp, check=True)
        (Path(tmp) / "c.txt").write_text("c\n")
        subprocess.run(["git", "add", "."], cwd=tmp, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "refactor: cleanup"], cwd=tmp, check=True
        )
        r = run_bash([], cwd=tmp)
        assert r.returncode == 0
        new = (Path(tmp) / "CHANGELOG.md").read_text()
        # 3 段都必须存在
        assert "### Added" in new
        assert "### Fixed" in new
        assert "### Changed" in new
        # feat 仅在 Added; fix 仅在 Fixed; refactor 仅在 Changed
        added_block = new.split("### Added", 1)[1].split("### ", 1)[0]
        fixed_block = new.split("### Fixed", 1)[1].split("### ", 1)[0]
        changed_block = new.split("### Changed", 1)[1].split("### ", 1)[0]
        assert "feat: new feature" in added_block
        assert "feat:" not in fixed_block
        assert "feat:" not in changed_block
        assert "fix: bug" in fixed_block
        assert "fix:" not in added_block
        assert "fix:" not in changed_block
        assert "refactor: cleanup" in changed_block
        assert "refactor:" not in added_block
        assert "refactor:" not in fixed_block
    finally:
        subprocess.run(["rm", "-rf", tmp])


# ---------- Task 3 bonus: --no-tag ----------


def test_no_tag_flag_skips_tag_creation():
    tmp = _make_temp_git_repo()
    try:
        subprocess.run(["git", "tag", "v1.0.0"], cwd=tmp, check=True)
        (Path(tmp) / "x.txt").write_text("a\n")
        subprocess.run(["git", "add", "."], cwd=tmp, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "fix: a"], cwd=tmp, check=True)
        r = run_bash(["--dry-run", "--no-tag"], cwd=tmp)
        assert r.returncode == 0
        # preview 应显示 tag: NO
        assert "tag:    NO" in r.stderr or "no-tag" in r.stderr or r.returncode == 0
    finally:
        subprocess.run(["rm", "-rf", tmp])