"""package_docs_contract：banned / required / allow 上下文 / 退出码。"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from lib.package_docs_contract import load_contract, main, scan_docs

FIX_YAML = textwrap.dedent(
    """\
    version: 1
    scan_files:
      - PROTOCOL.md
      - CLAUDE.md
    allow_context_radius: 2
    allow_context_substrings:
      - 已退役
      - 不迁到
      - 不在
      - 勿再写
      - 旧 API
      - 取代已退役
    banned_primary_path:
      - id: B1
        pattern: effective_experiment_mode
      - id: B2
        pattern: goal\\.spec
      - id: B3
        pattern: sync_agent_experiment_mode
    required_mentions:
      - term: exploration_mode
        file: PROTOCOL.md
      - term: agent.goal_spec
        file: PROTOCOL.md
      - term: primary_delta_rel
        file: PROTOCOL.md
    """
)


@pytest.fixture
def pkg(tmp_path: Path) -> Path:
    (tmp_path / "scripts" / "lib").mkdir(parents=True)
    (tmp_path / "scripts" / "lib" / "package_docs_contract.yaml").write_text(
        FIX_YAML, encoding="utf-8"
    )
    (tmp_path / "PROTOCOL.md").write_text(
        textwrap.dedent(
            """\
            # PROTOCOL
            exploration_mode 是唯一旋钮。
            agent.goal_spec 为复合门槛。
            keep.primary_delta_rel 控制 KEEP。
            """
        ),
        encoding="utf-8",
    )
    (tmp_path / "CLAUDE.md").write_text("# CLAUDE\n", encoding="utf-8")
    return tmp_path


def test_clean_tree_no_fail(pkg: Path) -> None:
    contract = load_contract(pkg / "scripts" / "lib" / "package_docs_contract.yaml")
    fails, warns = scan_docs(pkg, contract)
    assert fails == []
    assert warns == []


def test_banned_primary_path_fails(pkg: Path) -> None:
    p = pkg / "PROTOCOL.md"
    p.write_text(
        p.read_text(encoding="utf-8") + "\n调用 `effective_experiment_mode()` 取档。\n",
        encoding="utf-8",
    )
    contract = load_contract(pkg / "scripts" / "lib" / "package_docs_contract.yaml")
    fails, _ = scan_docs(pkg, contract)
    assert any("B1" in f and "effective_experiment_mode" in f for f in fails)


def test_allow_context_skips_retired_mention(pkg: Path) -> None:
    p = pkg / "PROTOCOL.md"
    p.write_text(
        p.read_text(encoding="utf-8")
        + "\n旧 API（`effective_experiment_mode`）**已退役**，勿再写。\n",
        encoding="utf-8",
    )
    contract = load_contract(pkg / "scripts" / "lib" / "package_docs_contract.yaml")
    fails, _ = scan_docs(pkg, contract)
    assert not any("B1" in f for f in fails)


def test_goal_spec_banned_unless_allow(pkg: Path) -> None:
    p = pkg / "PROTOCOL.md"
    p.write_text(
        p.read_text(encoding="utf-8") + "\n请配置 `goal.spec` 复合门槛。\n",
        encoding="utf-8",
    )
    contract = load_contract(pkg / "scripts" / "lib" / "package_docs_contract.yaml")
    fails, _ = scan_docs(pkg, contract)
    assert any("B2" in f for f in fails)

    p.write_text(
        "# PROTOCOL\nexploration_mode\nagent.goal_spec\nprimary_delta_rel\n"
        "不迁到 `goal.spec`。\n",
        encoding="utf-8",
    )
    fails2, _ = scan_docs(pkg, contract)
    assert not any("B2" in f for f in fails2)


def test_missing_required_mention_fails(pkg: Path) -> None:
    (pkg / "PROTOCOL.md").write_text(
        "# PROTOCOL\nagent.goal_spec\nprimary_delta_rel\n",
        encoding="utf-8",
    )
    contract = load_contract(pkg / "scripts" / "lib" / "package_docs_contract.yaml")
    fails, _ = scan_docs(pkg, contract)
    assert any("exploration_mode" in f and "required" in f.lower() for f in fails)


def test_main_exit_codes(pkg: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(pkg)
    # main 需要能从 argv 指定 --package-root
    assert (
        main(
            [
                "--package-root",
                str(pkg),
                "--contract",
                str(pkg / "scripts" / "lib" / "package_docs_contract.yaml"),
                "--no-git",
            ]
        )
        == 0
    )
    (pkg / "PROTOCOL.md").write_text(
        (pkg / "PROTOCOL.md").read_text(encoding="utf-8")
        + "\nsync_agent_experiment_mode()\n",
        encoding="utf-8",
    )
    assert (
        main(
            [
                "--package-root",
                str(pkg),
                "--contract",
                str(pkg / "scripts" / "lib" / "package_docs_contract.yaml"),
                "--no-git",
            ]
        )
        == 1
    )
