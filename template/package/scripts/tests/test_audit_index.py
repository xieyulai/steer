from pathlib import Path
import json
from lib.audit_core import injection_for_scenario, write_index_entry


def test_injection_current_then_superseded(tmp_path: Path):
    (tmp_path / "saved").mkdir()
    (tmp_path / "saved" / "keepers.json").write_text(
        json.dumps({"seq": {"keeper_exp_dir": "_runs/exp/best"}}), encoding="utf-8",
    )
    write_index_entry(
        tmp_path, scenario_id="seq", card_dir="saved/audit/t1_seq",
        audited_exp_dir="_runs/exp/best", config_sha256="aa",
    )
    cur = injection_for_scenario(tmp_path, "seq")
    assert cur["status"] == "current"
    (tmp_path / "saved" / "keepers.json").write_text(
        json.dumps({"seq": {"keeper_exp_dir": "_runs/exp/newer"}}), encoding="utf-8",
    )
    old = injection_for_scenario(tmp_path, "seq")
    assert old["status"] == "superseded"
    assert old["audited_exp_dir"].endswith("best")
