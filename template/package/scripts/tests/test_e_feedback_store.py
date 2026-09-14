"""e_feedback_store：缺字段不写、resolve、pending、summarize、id/去重。"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

PKG = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PKG / "scripts"))

from lib.e_feedback_store import (  # noqa: E402
    append_event,
    contract_changed,
    contract_file_map,
    format_shout_resolution_hint,
    pending_count,
    resolve,
    shout_fields_from_reflect_payload,
    shout_proposed_for_status,
    summarize,
    try_append_executed_on_relaunch,
    try_append_shout_from_reflect,
)


def _path(root: Path) -> Path:
    return root / "_runs" / "analysis" / "e_feedback.jsonl"


def _shout_kwargs(**over):
    base = dict(
        kind="shout",
        proposed="改主指标定义",
        why_abcd_insufficient="A-D 扫不动官方测试口径",
        ask="开闸改主指标",
        quote="建议改题面主指标",
        experiment="exp_demo",
        source="reflect",
        round_hint=3,
    )
    base.update(over)
    return base


def test_incomplete_shout_does_not_write_file(tmp_path: Path):
    out = append_event(tmp_path, **_shout_kwargs(proposed="  "))
    assert out == {"skipped": "incomplete"}
    assert not _path(tmp_path).exists()

    out2 = append_event(tmp_path, **_shout_kwargs(why_abcd_insufficient=""))
    assert out2 == {"skipped": "incomplete"}
    assert not _path(tmp_path).exists()

    out3 = append_event(tmp_path, **_shout_kwargs(ask="\t"))
    assert out3 == {"skipped": "incomplete"}
    assert not _path(tmp_path).exists()


def test_append_shout_writes_record_shape_and_id(tmp_path: Path):
    rec = append_event(tmp_path, **_shout_kwargs())
    assert "skipped" not in rec
    assert re.fullmatch(r"E\d{8}_\d{3}", rec["id"])
    assert rec["kind"] == "shout"
    assert rec["experiment"] == "exp_demo"
    assert rec["round_hint"] == 3
    assert rec["proposed"] == "改主指标定义"
    assert rec["why_abcd_insufficient"] == "A-D 扫不动官方测试口径"
    assert rec["ask"] == "开闸改主指标"
    assert rec["quote"] == "建议改题面主指标"
    assert rec["source"] == "reflect"
    assert "ts" in rec and rec["ts"]
    assert rec["resolution"] == {
        "status": "pending",
        "by": None,
        "ts": None,
        "note": None,
    }
    p = _path(tmp_path)
    assert p.is_file()
    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    loaded = json.loads(lines[0])
    assert loaded["id"] == rec["id"]
    assert loaded["resolution"]["status"] == "pending"


def test_same_day_id_increments(tmp_path: Path):
    a = append_event(tmp_path, **_shout_kwargs(proposed="改A"))
    b = append_event(tmp_path, **_shout_kwargs(proposed="改B"))
    day = datetime.now().astimezone().strftime("%Y%m%d")
    assert a["id"] == f"E{day}_001"
    assert b["id"] == f"E{day}_002"


def test_dedup_updates_last_seen_ts_no_new_id(tmp_path: Path):
    first = append_event(tmp_path, **_shout_kwargs())
    second = append_event(
        tmp_path,
        **_shout_kwargs(proposed="  改主指标定义  ", quote="第二次看到"),
    )
    assert second["id"] == first["id"]
    assert "last_seen_ts" in second
    lines = [ln for ln in _path(tmp_path).read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    loaded = json.loads(lines[0])
    assert loaded["id"] == first["id"]
    assert loaded["last_seen_ts"] == second["last_seen_ts"]


def test_resolve_changes_status(tmp_path: Path):
    rec = append_event(tmp_path, **_shout_kwargs())
    assert pending_count(tmp_path) == 1
    updated = resolve(
        tmp_path,
        rec["id"],
        "rejected",
        note="暂不改题",
        by="human",
    )
    assert updated["resolution"]["status"] == "rejected"
    assert updated["resolution"]["by"] == "human"
    assert updated["resolution"]["note"] == "暂不改题"
    assert updated["resolution"]["ts"]
    assert pending_count(tmp_path) == 0
    loaded = json.loads(_path(tmp_path).read_text(encoding="utf-8").strip())
    assert loaded["resolution"]["status"] == "rejected"


def test_rejected_same_proposed_does_not_reopen(tmp_path: Path):
    rec = append_event(tmp_path, **_shout_kwargs())
    resolve(tmp_path, rec["id"], "rejected", note="驳回")
    again = append_event(tmp_path, **_shout_kwargs(quote="再提一次"))
    assert again.get("skipped") == "rejected"
    assert again.get("id") == rec["id"]
    lines = [ln for ln in _path(tmp_path).read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["resolution"]["status"] == "rejected"


def test_adopted_same_proposed_does_not_reopen(tmp_path: Path):
    rec = append_event(tmp_path, **_shout_kwargs())
    resolve(tmp_path, rec["id"], "adopted", note="留下当建议")
    again = append_event(tmp_path, **_shout_kwargs())
    assert again.get("skipped") == "adopted"
    assert pending_count(tmp_path) == 0
    lines = [ln for ln in _path(tmp_path).read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 1


def test_deferred_same_proposed_opens_new_pending(tmp_path: Path):
    rec = append_event(tmp_path, **_shout_kwargs())
    resolve(tmp_path, rec["id"], "deferred", note="搁置")
    again = append_event(tmp_path, **_shout_kwargs(quote="下次再提"))
    assert "skipped" not in again
    assert again["id"] != rec["id"]
    assert again["resolution"]["status"] == "pending"
    assert pending_count(tmp_path) == 1
    lines = [ln for ln in _path(tmp_path).read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2


def test_format_shout_resolution_hint_lists_statuses(tmp_path: Path):
    a = append_event(tmp_path, **_shout_kwargs(proposed="改指标"))
    b = append_event(tmp_path, **_shout_kwargs(proposed="改场景"))
    resolve(tmp_path, a["id"], "rejected")
    resolve(tmp_path, b["id"], "deferred")
    hint = format_shout_resolution_hint(tmp_path)
    assert "已驳回" in hint and "改指标" in hint
    assert "已搁置" in hint and "改场景" in hint
    assert shout_proposed_for_status(tmp_path, "rejected") == ["改指标"]


def test_pending_count_only_pending(tmp_path: Path):
    a = append_event(tmp_path, **_shout_kwargs(proposed="p1"))
    append_event(tmp_path, **_shout_kwargs(proposed="p2"))
    resolve(tmp_path, a["id"], "deferred", note="以后")
    assert pending_count(tmp_path) == 1


def test_summarize_exact_format(tmp_path: Path):
    assert summarize(tmp_path) == "e_feedback: (无)"
    a = append_event(tmp_path, **_shout_kwargs(proposed="p1"))
    append_event(tmp_path, **_shout_kwargs(proposed="p2"))
    assert summarize(tmp_path) == "e_feedback: pending=2 deferred=0"
    resolve(tmp_path, a["id"], "deferred", note="later")
    assert summarize(tmp_path) == "e_feedback: pending=1 deferred=1"


def test_tempfile_replace_keeps_valid_jsonl(tmp_path: Path):
    rec = append_event(tmp_path, **_shout_kwargs())
    resolve(tmp_path, rec["id"], "adopted", note="ok")
    p = _path(tmp_path)
    assert not list(p.parent.glob("*.tmp"))
    body = p.read_text(encoding="utf-8")
    assert body.endswith("\n")
    row = json.loads(body.strip())
    assert row["resolution"]["status"] == "adopted"


def test_executed_writes_without_shout_triple(tmp_path: Path):
    rec = append_event(
        tmp_path,
        kind="executed",
        proposed="contract diff",
        why_abcd_insufficient="relaunch",
        ask="already",
        quote="",
        experiment="exp_x",
        source="finalize",
        round_hint=None,
    )
    assert rec["kind"] == "executed"
    assert pending_count(tmp_path) == 1


def test_shout_fields_from_reflect_payload_keys_and_missing():
    assert shout_fields_from_reflect_payload({}) == ("", "", "")
    assert shout_fields_from_reflect_payload(
        {"e_proposed": "改指标", "e_why_abcd": "A-D 不够", "e_ask": "开闸"}
    ) == ("改指标", "A-D 不够", "开闸")
    # 散文 Tier E 不得被本 helper 当成三条字段
    p, w, a = shout_fields_from_reflect_payload(
        {"key_insight": "应升 Tier E 改题", "phase2_focus": "Tier E"}
    )
    assert p == "" and w == "" and a == ""


def test_try_append_shout_from_reflect_incomplete_skips(tmp_path: Path):
    out = try_append_shout_from_reflect(
        tmp_path,
        {"e_proposed": "x", "e_why_abcd": "", "e_ask": "y"},
        experiment="e1",
        round_hint=1,
    )
    assert out == {"skipped": "incomplete"}
    assert not _path(tmp_path).exists()


def test_try_append_shout_from_reflect_writes(tmp_path: Path):
    rec = try_append_shout_from_reflect(
        tmp_path,
        {
            "e_proposed": "改官方测试",
            "e_why_abcd": "扫不动测试口径",
            "e_ask": "开闸改 test",
            "key_insight": "需要改题",
        },
        experiment="e2",
        round_hint=2,
        quote="需要改题",
    )
    assert rec["kind"] == "shout"
    assert rec["proposed"] == "改官方测试"
    assert pending_count(tmp_path) == 1


def test_contract_file_map_and_changed(tmp_path: Path):
    prev = tmp_path / "prev"
    cur = tmp_path / "cur"
    (prev / "code_snapshot" / "contract").mkdir(parents=True)
    (cur / "code_snapshot" / "contract").mkdir(parents=True)
    (prev / "code_snapshot" / "contract" / "metrics.py").write_text("a=1\n", encoding="utf-8")
    (cur / "code_snapshot" / "contract" / "metrics.py").write_text("a=1\n", encoding="utf-8")
    assert contract_changed(prev, cur) is False
    (cur / "code_snapshot" / "contract" / "metrics.py").write_text("a=2\n", encoding="utf-8")
    assert contract_changed(prev, cur) is True
    m = contract_file_map(cur / "code_snapshot" / "contract")
    assert m["metrics.py"] == "a=2\n"


def test_contract_changed_falls_back_to_live(tmp_path: Path):
    prev = tmp_path / "prev"
    cur = tmp_path / "cur"
    live = tmp_path / "contract"
    (prev / "code_snapshot" / "contract").mkdir(parents=True)
    cur.mkdir()
    live.mkdir()
    (prev / "code_snapshot" / "contract" / "x.py").write_text("old\n", encoding="utf-8")
    (live / "x.py").write_text("new\n", encoding="utf-8")
    assert contract_changed(prev, cur, live_contract=live) is True


def test_contract_changed_false_when_prev_has_no_snapshot(tmp_path: Path):
    """升级后首轮：上一轮无 contract 快照、本轮有 → 证据不足，不算 changed。"""
    prev = tmp_path / "prev"
    cur = tmp_path / "cur"
    prev.mkdir()
    (cur / "code_snapshot" / "contract").mkdir(parents=True)
    (cur / "code_snapshot" / "contract" / "metrics.py").write_text("a=1\n", encoding="utf-8")
    assert contract_changed(prev, cur) is False


def test_try_append_executed_skips_when_prev_has_no_snapshot(tmp_path: Path):
    """prev 无 contract 快照时即使 NN_RELAUNCH=1 也不写 executed。"""
    prev = tmp_path / "prev"
    cur = tmp_path / "cur"
    prev.mkdir()
    (cur / "code_snapshot" / "contract").mkdir(parents=True)
    (cur / "code_snapshot" / "contract" / "a.py").write_text("1\n", encoding="utf-8")
    assert (
        try_append_executed_on_relaunch(
            tmp_path,
            relaunch_env="1",
            prev_exp_dir=prev,
            cur_exp_dir=cur,
            experiment="c1",
        )
        is None
    )
    assert not _path(tmp_path).exists()


def test_try_append_executed_requires_relaunch_and_diff(tmp_path: Path):
    prev = tmp_path / "prev"
    cur = tmp_path / "cur"
    (prev / "code_snapshot" / "contract").mkdir(parents=True)
    (cur / "code_snapshot" / "contract").mkdir(parents=True)
    (prev / "code_snapshot" / "contract" / "a.py").write_text("1\n", encoding="utf-8")
    (cur / "code_snapshot" / "contract" / "a.py").write_text("2\n", encoding="utf-8")

    assert (
        try_append_executed_on_relaunch(
            tmp_path,
            relaunch_env="",
            prev_exp_dir=prev,
            cur_exp_dir=cur,
            experiment="c1",
        )
        is None
    )
    assert not _path(tmp_path).exists()

    (cur / "code_snapshot" / "contract" / "a.py").write_text("1\n", encoding="utf-8")
    assert (
        try_append_executed_on_relaunch(
            tmp_path,
            relaunch_env="1",
            prev_exp_dir=prev,
            cur_exp_dir=cur,
            experiment="c1",
        )
        is None
    )

    (cur / "code_snapshot" / "contract" / "a.py").write_text("2\n", encoding="utf-8")
    rec = try_append_executed_on_relaunch(
        tmp_path,
        relaunch_env="1",
        prev_exp_dir=prev,
        cur_exp_dir=cur,
        experiment="c1",
        round_hint=9,
    )
    assert rec is not None
    assert rec["kind"] == "executed"
    assert rec["proposed"] == "contract diff"
    assert rec["why_abcd_insufficient"] == "relaunch"
    assert rec["ask"] == "already"
    assert rec["source"] == "reflect"
