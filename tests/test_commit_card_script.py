"""tests/test_commit_card_script.py — E 卡回填提交脚本的回归测试（模板 4.1.1 修 ③）

太史慈判定第 ③ 条：
  1. commit_card.sh 只 stage 本次回填目标文件，禁止整工作区 git add；
  2. commit message 按**实际** decisions 路径（含 part1/part2）写，
     不许硬编码 decisions/<仓名>.json。

本测试用 tmp 目录造假环境：把 AUTO_RESEARCH 根目录指到 tmp（脚本支持 NNF_BASE 覆盖），
真跑 bash + 真 git，验证提交内容与提交信息。
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

    # 仓里另有一处未提交改动（模拟别人的 WIP / 业务卡）
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
    # 台账在 init 之后才被改动 ⇒ 脚本才有东西可提交
    (repo / LEDGER).write_text('{"shout_id": "s1"}\n', encoding="utf-8")
    # 别人的 WIP：init 之后再改 ⇒ 处于「已跟踪但未提交」状态
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
    """只提交台账一个文件；仓里其它改动不得被夹带（禁整工作区 git add）。"""
    base, repo = _fixture(tmp_path)
    proc = _run(base, REPO)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    files = _git(repo, "show", "--name-only", "--pretty=format:", "HEAD").split()
    assert files == [LEDGER], files
    # 业务卡仍是未提交状态
    assert "business_card.txt" in _git(repo, "status", "--porcelain")


def test_commit_message_lists_actual_part_files(tmp_path):
    """commit message 必须写出真实的 part1/part2 路径，不能是硬编码的 <仓名>.json。"""
    base, repo = _fixture(tmp_path)
    proc = _run(base, REPO)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    msg = _git(repo, "log", "-1", "--pretty=format:%B")
    assert f"decisions/{REPO}.part1.json" in msg, msg
    assert f"decisions/{REPO}.part2.json" in msg, msg
    # 硬编码路径不该出现（那个文件压根不存在）
    assert f"decisions/{REPO}.json" not in msg, msg
    # 人工回填必须自报家门
    assert "人工判定回填，非软件自动回填" in msg, msg


def test_single_file_repo_uses_plain_decision_path(tmp_path):
    """只有一个判定文件的仓：message 写那个真实路径。"""
    base, repo = _fixture(tmp_path, parts=False)
    proc = _run(base, REPO)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    msg = _git(repo, "log", "-1", "--pretty=format:%B")
    assert f"decisions/{REPO}.json" in msg, msg
    assert ".part1.json" not in msg, msg


def test_aborts_when_index_contains_other_files(tmp_path):
    """暂存区里混进别的文件 ⇒ 中止不提交（防夹带）。"""
    base, repo = _fixture(tmp_path)
    _git(repo, "add", "business_card.txt")
    proc = _run(base, REPO)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert "暂存区含非本次回填文件" in proc.stderr, proc.stderr
    # 没有新提交
    assert "init" in _git(repo, "log", "-1", "--pretty=format:%s")


def test_explicit_decision_files_argument_is_used(tmp_path):
    """显式传入判定文件时，message 用传入的真实路径。"""
    base, repo = _fixture(tmp_path, parts=False)
    extra = base / "e-card-backfill" / "decisions" / f"{REPO}.part9.json"
    extra.write_text("{}", encoding="utf-8")
    proc = _run(base, REPO, str(extra))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    msg = _git(repo, "log", "-1", "--pretty=format:%B")
    assert f"decisions/{REPO}.part9.json" in msg, msg


if __name__ == "__main__":
    raise SystemExit(subprocess.call(["python3", "-m", "pytest", __file__, "-v"]))
