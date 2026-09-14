"""盘面稳定段 ### audit-card：有卡片才出现；当前最好换人后降为上一套。"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from lib.audit_core import write_index_entry

_SCRIPTS = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "_build_run_context_audit_card", _SCRIPTS / "build-run-context.py"
)
brc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(brc)


def _seed(repo: Path, *, keeper_dir: str, audited: str) -> None:
    (repo / "nn-config.yaml").write_text(
        "agent:\n  scenario_default: seq\n", encoding="utf-8"
    )
    saved = repo / "saved"
    saved.mkdir(exist_ok=True)
    (saved / "keepers.json").write_text(
        json.dumps({"seq": {"keeper_exp_dir": keeper_dir}}), encoding="utf-8"
    )
    card_dir = saved / "audit" / "t1_seq"
    card_dir.mkdir(parents=True)
    (card_dir / "card.md").write_text(
        "# 审查卡片\n"
        "审的是：场景 seq，实验目录 _runs/exp/best\n"
        "复现：对上\n"
        "多种子：n=3 均值 0.9 标准差 0.01\n"
        "新不新：搜索时声称 novel；本次审查 novel\n"
        "消融：计划 LOSS；已跑 是\n",
        encoding="utf-8",
    )
    (card_dir / "card.json").write_text(
        json.dumps(
            {
                "attested_depth": "novel",
                "repro_ok": True,
                "n_seeds": 3,
                "ablation_ran": True,
            }
        ),
        encoding="utf-8",
    )
    write_index_entry(
        repo,
        scenario_id="seq",
        card_dir=str(card_dir),
        audited_exp_dir=audited,
        config_sha256="aa",
    )


def _md(repo: Path) -> str:
    ctx = brc.build_run_context(repo)
    return brc.format_run_context_md(ctx)


def test_audit_card_current_when_keeper_matches(tmp_path: Path):
    _seed(tmp_path, keeper_dir="_runs/exp/best", audited="_runs/exp/best")
    md = _md(tmp_path)
    assert "### audit-card" in md
    assert "当前这套已审查" in md
    assert "上一套已审查" not in md
    assert md.index("### keeper-status") < md.index("### audit-card")


def test_audit_card_superseded_when_keeper_changes(tmp_path: Path):
    _seed(tmp_path, keeper_dir="_runs/exp/best", audited="_runs/exp/best")
    (tmp_path / "saved" / "keepers.json").write_text(
        json.dumps({"seq": {"keeper_exp_dir": "_runs/exp/newer"}}), encoding="utf-8"
    )
    md = _md(tmp_path)
    assert "### audit-card" in md
    assert "上一套已审查" in md
    assert "当前这套已审查" not in md
    assert "上一套：" in md
    section = md[md.index("### audit-card") :]
    assert "novel" in section
    prefix_at = section.index("上一套：")
    assert "novel" in section[prefix_at:]


def test_audit_card_omitted_when_no_index(tmp_path: Path):
    (tmp_path / "nn-config.yaml").write_text(
        "agent:\n  scenario_default: seq\n", encoding="utf-8"
    )
    md = _md(tmp_path)
    assert "### audit-card" not in md
    assert "当前这套已审查" not in md
    assert "上一套已审查" not in md
