"""Integration：routed loaders 直接读顶层 block（无 agent 回填）。"""
from __future__ import annotations

from pathlib import Path
import textwrap

import yaml


def _write_minimal_yaml(root: Path):
    """Yaml with ONLY top-level blocks + stay-in-agent keys (NO migrated agent.* aliases)."""
    (root / "nn-config.yaml").write_text(textwrap.dedent("""\
        profile: supervised
        exploration:
          mode: aggressive
        external:
          enabled: false
          max_http_per_reflect: 9
          paper_hits_default: 7
          paper_hits_deepen: 11
          pdf_enabled: false
          serper_key_env: MY_KEY
          task_domain: "test domain"
        gpu:
          mem_reserve_gb: 3.5
          busy_util_min: 95
          colocate_on_single: false
        agent:
          plateau_rounds: 7
          scenario_policy: focus
        """), encoding="utf-8")


def test_load_external_config_backfills_from_top_level(tmp_path):
    _write_minimal_yaml(tmp_path)
    from lib.external.config import load_external_config

    cfg = load_external_config(tmp_path)
    # external_* aliases absent from agent; values come from top-level external block via backfill
    assert cfg.enabled is False
    assert cfg.max_http_per_reflect == 9
    assert cfg.paper_hits_default == 7
    assert cfg.paper_hits_deepen == 11
    assert cfg.pdf_enabled is False
    assert cfg.serper_key_env == "MY_KEY"


def test_load_gpu_agent_config_backfills_from_top_level(tmp_path):
    _write_minimal_yaml(tmp_path)
    from lib.gpu_snapshot import load_gpu_agent_config

    cfg = load_gpu_agent_config(tmp_path)
    # gpu_* aliases absent from agent; backfilled from top-level gpu block
    assert cfg["gpu_mem_reserve_gb"] == 3.5
    assert cfg["gpu_busy_util_min"] == 95
    assert cfg["gpu_colocate_on_single"] is False


def test_plateau_rounds_still_readable_from_agent(tmp_path):
    _write_minimal_yaml(tmp_path)
    from lib.nn_config import load_nn_config

    raw = load_nn_config(tmp_path)
    assert raw["agent"]["plateau_rounds"] == 7  # stay-in-agent key preserved


def test_innovation_fingerprint_backfills_from_top_level(tmp_path):
    """顶层 innovation block 回填进 agent.innovation_fingerprint_*。"""
    (tmp_path / "nn-config.yaml").write_text(textwrap.dedent("""\
        innovation:
          audit_enabled: false
          fingerprint_enabled: false
          fingerprint_authoritative: false
        """), encoding="utf-8")
    from lib.innovation_fingerprint import load_fingerprint_config

    cfg = load_fingerprint_config(tmp_path)
    assert cfg.enabled is False
    assert cfg.authoritative is False


def test_innovation_audit_backfills_from_top_level(tmp_path):
    (tmp_path / "nn-config.yaml").write_text(textwrap.dedent("""\
        innovation:
          audit_enabled: false
        """), encoding="utf-8")
    from lib.innovation_audit import load_innovation_config

    cfg = load_innovation_config(tmp_path)
    assert cfg.enabled is False


def test_experience_auto_compress_backfills_from_top_level(tmp_path):
    (tmp_path / "nn-config.yaml").write_text(textwrap.dedent("""\
        compress:
          experience_auto_compress: after_round
          experience_compress_keep_n: 9
        """), encoding="utf-8")
    from lib.experience_auto_compress import compress_config

    cfg = compress_config(tmp_path)
    assert cfg["mode"] == "after_round"
    assert cfg["keep_n"] == 9


def test_run_ledger_summary_agent_config_backfills_reflect_interval(tmp_path):
    (tmp_path / "nn-config.yaml").write_text(textwrap.dedent("""\
        reflect:
          interval: 5
        """), encoding="utf-8")
    from lib.run_ledger_summary import agent_config

    _plateau_n, interval = agent_config(tmp_path)
    assert interval == 5  # 直接读 reflect.interval


def test_metric_analysis_backfills_analyse_keys(tmp_path):
    (tmp_path / "nn-config.yaml").write_text(textwrap.dedent("""\
        analyse:
          recent_rows: 42
          aux_max: 8
        """), encoding="utf-8")
    from lib.metric_analysis import analyse_agent_config

    cfg = analyse_agent_config(tmp_path)
    assert cfg["analyse_recent_rows"] == 42
    assert cfg["analyse_aux_max"] == 8


def test_experiment_mode_backfills_objective_mode(tmp_path):
    (tmp_path / "nn-config.yaml").write_text(textwrap.dedent("""\
        exploration:
          mode: explore
          objective_mode: explore
        """), encoding="utf-8")
    from lib.explore_objective import objective_mode_from_config

    assert objective_mode_from_config(tmp_path) == "explore"
