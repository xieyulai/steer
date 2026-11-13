"""tests/test_commit_card_script.py — regression tests for the E-card backfill commit
script (template 4.1.1 fix ③).

Taishici adjudication, item ③:
  1. commit_card.sh stages only this backfill's target file; it must never
     `git add` the whole working tree;
  2. the commit message is written from the **actual** decisions paths (including
     part1/part2); the hardcoded decisions/<repo>.json must not be used.

This test fakes the environment in a tmp directory: it points the AUTO_RESEARCH
root at tmp (the script supports a NNF_BASE override), runs real bash + real git,
and verifies both the committed content and the commit message.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1] / "tools" / "e-card-backfill" / "commit_card.sh"
)

REPO = "csi-compress-0001-20261015"
LEDGER = "_runs/analysis/e_feedback.jsonl"


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return proc.stdout


def _make_env(base: Path) -> dict:
    env = dict(os.environ)
    env.update(
        NNF_BASE=str(base),
        GIT_AUTHOR_NAME="test",
        GIT_AUTHOR_EMAIL="test@example.com",
        GIT_COMMITTER_NAME="test",
        GIT_COMMITTER_EMAIL="test@example.com",
    )
    return env


def _fixture(tmp_path: Path, *, parts: bool = True) -> tuple[Path, Path]:
    base = tmp_path / "AUTO_RESEARCH"
    repo = base / "auto-nn-factory-projects" / REPO
    (repo / "_runs" / "analysis").mkdir(parents=True)
    dec = base / "e-card-backfill" / "decisions"
    dec.mkdir(parents=True)

    # Another uncommitted change in the repo (simulates someone else's WIP / a business card)
    (repo / "business_card.txt").write_text("dirty\n", encoding="utf-8")

    if parts:
        (dec / f"{REPO}.part1.json").write_text("{}", encoding="utf-8")
        (dec / f"{REPO}.part2.json").write_text("{}", encoding="utf-8")
    else:
        (dec / f"{REPO}.json").write_text("{}", encoding="utf-8")

    _git(repo, "init", "-q")
    _git(repo, "config", "user.name", "test")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "init")
    # The ledger is modified only after init ⇒ the script has something to commit
    (repo / LEDGER).write_text('{"shout_id": "s1"}\n', encoding="utf-8")
    # Someone else's WIP: modified after init ⇒ it is tracked but uncommitted
    (repo / "business_card.txt").write_text("dirty\nmore\n", encoding="utf-8")
    return base, repo


def _run(base: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=_make_env(base),
        check=False,
    )


def test_commits_only_the_ledger_file(tmp_path):
    """Only the ledger file is committed; other changes in the repo must not be
    smuggled in (no whole-working-tree `git add`)."""
    base, repo = _fixture(tmp_path)
    proc = _run(base, REPO)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    files = _git(repo, "show", "--name-only", "--pretty=format:", "HEAD").split()
    assert files == [LEDGER], files
    # The business card is still uncommitted
    assert "business_card.txt" in _git(repo, "status", "--porcelain")


def test_commit_message_lists_actual_part_files(tmp_path):
    """The commit message must name the real part1/part2 paths, not the hardcoded
    <repo>.json."""
    base, repo = _fixture(tmp_path)
    proc = _run(base, REPO)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    msg = _git(repo, "log", "-1", "--pretty=format:%B")
    assert f"decisions/{REPO}.part1.json" in msg, msg
    assert f"decisions/{REPO}.part2.json" in msg, msg
    # The hardcoded path must not appear (that file does not exist at all)
    assert f"decisions/{REPO}.json" not in msg, msg
    # The manual backfill must identify itself
    assert "人工判定回填，非软件自动回填" in msg, msg


def test_single_file_repo_uses_plain_decision_path(tmp_path):
    """Repo with a single decision file: the message names that real path."""
    base, repo = _fixture(tmp_path, parts=False)
    proc = _run(base, REPO)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    msg = _git(repo, "log", "-1", "--pretty=format:%B")
    assert f"decisions/{REPO}.json" in msg, msg
    assert ".part1.json" not in msg, msg


def test_aborts_when_index_contains_other_files(tmp_path):
    """Other files mixed into the index ⇒ abort without committing; unstage ledger only."""
    base, repo = _fixture(tmp_path)
    _git(repo, "add", "business_card.txt")
    proc = _run(base, REPO)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "暂存区含非本次回填文件" in proc.stderr, proc.stderr
    # No new commit
    assert "init" in _git(repo, "log", "-1", "--pretty=format:%s")
    cached = _git(repo, "diff", "--cached", "--name-only").split()
    assert LEDGER not in cached, cached
    assert "business_card.txt" in cached


def test_explicit_decision_files_argument_is_used(tmp_path):
    """Explicit paths appear in the message as AUTO_RESEARCH/.../basename, not abs paths."""
    base, repo = _fixture(tmp_path, parts=False)
    extra = base / "e-card-backfill" / "decisions" / f"{REPO}.part9.json"
    extra.write_text("{}", encoding="utf-8")
    proc = _run(base, REPO, str(extra))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    msg = _git(repo, "log", "-1", "--pretty=format:%B")
    assert f"decisions/{REPO}.part9.json" in msg, msg
    assert str(extra) not in msg, msg


def test_aborts_when_no_decision_files(tmp_path):
    """Auto-infer finds nothing ⇒ exit 2, no commit."""
    base, repo = _fixture(tmp_path)
    dec = base / "e-card-backfill" / "decisions"
    for p in dec.glob(f"{REPO}*"):
        p.unlink()
    proc = _run(base, REPO)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "未找到判定文件" in proc.stderr, proc.stderr
    assert "init" in _git(repo, "log", "-1", "--pretty=format:%s")


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))