"""隔离副本预演：正仓合同不动，成绩表记 rehearsal_score，同一主张只跑一次。"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

PKG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PKG / "scripts"))

from lib.e_feedback_store import append_event, load_records  # noqa: E402

SCRIPT = PKG / "scripts" / "rehearse_e.py"
PROPOSED = "改官方测试"
WHY = "A-D 扫不动官方测试口径"
ASK = "开闸改主指标"
TSV_HEADER = "experiment\tscenario_id\tsgcs\texploration_space\tuntrained\n"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(tmp_path: Path) -> tuple[Path, bytes]:
    repo = tmp_path / "repo"
    (repo / "contract").mkdir(parents=True)
    runtime = repo / "contract" / "runtime.py"
    runtime.write_text("# runtime\n", encoding="utf-8")
    runs = repo / "_runs"
    runs.mkdir()
    (runs / "results.tsv").write_text(TSV_HEADER, encoding="utf-8")
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "init")
    append_event(
        repo,
        kind="shout",
        proposed=PROPOSED,
        why_abcd_insufficient=WHY,
        ask=ASK,
        quote="",
        experiment="",
        source="test",
        round_hint=None,
        e_type="information_visibility",
        headline="允许解码端记住上一帧",
    )
    return repo, runtime.read_bytes()


def _patch_from_worktree(repo: Path, rel: str, new_text: str, dest: Path) -> None:
    path = repo / rel
    original = path.read_bytes()
    path.write_text(new_text, encoding="utf-8")
    diff = subprocess.run(
        ["git", "diff", "--", rel],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    path.write_bytes(original)
    assert diff.strip()
    dest.write_text(diff, encoding="utf-8")


def _train_cmd(tmp_path: Path) -> str:
    script = tmp_path / "fake_train.py"
    script.write_text(
        "import json\n"
        "from pathlib import Path\n"
        "p = Path('_runs') / 'analysis'\n"
        "p.mkdir(parents=True, exist_ok=True)\n"
        "(p / 'rehearsal_metric.json').write_text(\n"
        "    json.dumps({'metric_key': 'sgcs', 'metric': 0.9}),\n"
        "    encoding='utf-8',\n"
        ")\n",
        encoding="utf-8",
    )
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}"


def _run(
    repo: Path,
    patch: Path,
    train_cmd: str,
    *,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("NN_RELAUNCH", None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--repo-root",
            str(repo),
            "--proposed",
            PROPOSED,
            "--why",
            WHY,
            "--ask",
            ASK,
            "--e-type",
            "information_visibility",
            "--headline",
            "允许解码端记住上一帧",
            "--patch",
            str(patch),
            "--train-cmd",
            train_cmd,
        ],
        env=env,
        capture_output=True,
        text=True,
    )


def _tsv(repo: Path) -> tuple[list[str], list[dict[str, str]]]:
    lines = (repo / "_runs" / "results.tsv").read_text(encoding="utf-8").splitlines()
    header = lines[0].split("\t")
    rows: list[dict[str, str]] = []
    for ln in lines[1:]:
        if not ln.strip():
            continue
        cells = ln.split("\t")
        if len(cells) < len(header):
            cells.extend([""] * (len(header) - len(cells)))
        rows.append(dict(zip(header, cells)))
    return header, rows


def _rehearse_dirs() -> set[Path]:
    root = Path(tempfile.gettempdir())
    return {p for p in root.glob("e_rehearse_*") if p.is_dir()}


def test_rehearse_books_score_without_touching_live_contract(tmp_path: Path):
    repo, runtime_bytes = _init_repo(tmp_path)
    patch = tmp_path / "contract.patch"
    _patch_from_worktree(repo, "contract/runtime.py", "# runtime changed\n", patch)
    assert (repo / "contract" / "runtime.py").read_bytes() == runtime_bytes
    before_dirs = _rehearse_dirs()
    train = _train_cmd(tmp_path)

    proc = _run(repo, patch, train)
    assert proc.returncode == 0, proc.stderr + proc.stdout

    assert (repo / "contract" / "runtime.py").read_bytes() == runtime_bytes
    header, rows = _tsv(repo)
    assert header.index("rehearsal_score") == header.index("exploration_space") + 1
    assert len(rows) == 1
    assert rows[0]["sgcs"] == ""
    assert rows[0]["rehearsal_score"] == "0.9"
    assert rows[0]["exploration_space"] == "E-rehearsal"
    assert rows[0]["scenario_id"] == "default"
    assert rows[0]["experiment"].startswith("e_rehearsal_")

    rec = load_records(repo)[0]
    assert rec["resolution"]["status"] == "pending"
    rehearsal = rec["rehearsal"]
    assert rehearsal["status"] == "ok"
    assert rehearsal["metric"] == 0.9
    assert rehearsal["metric_key"] == "sgcs"
    assert rehearsal["tree_deleted"] is True
    assert rehearsal["live_contract_clean"] is True
    assert str(rehearsal["tsv_experiment"]).startswith("e_rehearsal_")
    assert rehearsal["tsv_experiment"] == rows[0]["experiment"]
    assert rehearsal["error"] == ""
    assert rehearsal["leader_metric"] is None
    assert rehearsal["delta_vs_leader"] is None
    assert "contract/runtime.py" in rehearsal["patch_files"]
    assert rehearsal["ts"]
    assert _rehearse_dirs() <= before_dirs

    again = _run(repo, patch, train)
    assert again.returncode == 2, again.stderr + again.stdout
    _, rows_again = _tsv(repo)
    assert len(rows_again) == 1


def test_parent_nn_relaunch_exits_without_booking(tmp_path: Path):
    repo, _runtime = _init_repo(tmp_path)
    patch = tmp_path / "contract.patch"
    _patch_from_worktree(repo, "contract/runtime.py", "# runtime changed\n", patch)
    tsv_before = (repo / "_runs" / "results.tsv").read_bytes()

    proc = _run(
        repo,
        patch,
        _train_cmd(tmp_path),
        extra_env={"NN_RELAUNCH": "1"},
    )
    assert proc.returncode == 3, proc.stderr + proc.stdout
    assert (repo / "_runs" / "results.tsv").read_bytes() == tsv_before
    _, rows = _tsv(repo)
    assert rows == []
    rec = load_records(repo)[0]
    assert "rehearsal" not in rec


def test_patch_outside_contract_books_fail_without_tsv(tmp_path: Path):
    repo, runtime_bytes = _init_repo(tmp_path)
    readme = repo / "README"
    readme.write_text("hello\n", encoding="utf-8")
    _git(repo, "add", "README")
    _git(repo, "commit", "-m", "readme")
    patch = tmp_path / "readme.patch"
    _patch_from_worktree(repo, "README", "hello changed\n", patch)
    tsv_before = (repo / "_runs" / "results.tsv").read_bytes()
    before_dirs = _rehearse_dirs()

    proc = _run(repo, patch, _train_cmd(tmp_path))
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert (repo / "contract" / "runtime.py").read_bytes() == runtime_bytes
    assert (repo / "_runs" / "results.tsv").read_bytes() == tsv_before
    _, rows = _tsv(repo)
    assert rows == []
    rehearsal = load_records(repo)[0]["rehearsal"]
    assert rehearsal["status"] == "fail"
    assert rehearsal["metric"] is None
    assert rehearsal["tree_deleted"] is True
    assert rehearsal["tsv_experiment"] is None
    assert rehearsal["live_contract_clean"] is True
    assert any(not str(p).startswith("contract/") for p in rehearsal["patch_files"])
    assert _rehearse_dirs() <= before_dirs
