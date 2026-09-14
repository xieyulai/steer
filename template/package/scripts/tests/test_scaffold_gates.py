"""scenario_default 空 → FAIL；辅指标恒零 WARN；动态库 pip 映射。"""
from __future__ import annotations

from pathlib import Path

import yaml


def test_empty_scenario_default_is_fail(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "README.md").write_text(
        "## 场景清单\n\n| 场景 ID | 说明 |\n| --- | --- |\n| s1 | demo |\n",
        encoding="utf-8",
    )
    (tmp_path / "nn-config.yaml").write_text(
        yaml.dump(
            {"profile": "default", "agent": {"scenario_default": ""}},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    import sys

    scripts = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(scripts))
    from lib.scenario_inventory import audit_scenario_completeness

    items = audit_scenario_completeness(tmp_path)
    fails = [i for i in items if i["level"] == "fail" and "scenario_default" in i["detail"]]
    assert fails, items


def test_warn_aux_always_zero(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "contract").mkdir()
    (tmp_path / "contract" / "__init__.py").write_text("# stub\n", encoding="utf-8")
    (tmp_path / "contract" / "metrics.py").write_text(
        'METRIC_KEYS = {"acc": "maximize"}\n'
        'AUXILIARY_KEYS = {"forgetting": "minimize"}\n',
        encoding="utf-8",
    )
    (tmp_path / "nn-config.yaml").write_text(
        "profile: default\nagent:\n  scenario_default: s1\n",
        encoding="utf-8",
    )
    (tmp_path / "_runs").mkdir()
    (tmp_path / "_runs" / "results.tsv").write_text(
        "experiment\tscenario_id\tacc\tforgetting\n"
        "e1\ts1\t0.5\t0.0\n"
        "e2\ts1\t0.6\t0.0\n"
        "e3\ts1\t0.7\t0.0\n",
        encoding="utf-8",
    )
    import sys

    scripts = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(scripts))
    from lib.metric_analysis import warn_aux_metrics_always_zero

    ws = warn_aux_metrics_always_zero(tmp_path, min_rows=3)
    assert any("forgetting" in w for w in ws), ws
