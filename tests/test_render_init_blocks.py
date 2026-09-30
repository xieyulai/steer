"""tests/test_render_init_blocks.py — render_init_blocks.py 单元测试

覆盖：lock 键值提取 → README 三块渲染 / 场景清单表 / nn-config 机读题对齐 /
起步尺子 intent；TSV 表头唯一事实源是 contract（regen_results_tsv.py 派生），
渲染器不碰 _runs/results.tsv。无标记块的仓原样跳过（full_copy 老仓不注入）。
全部用临时目录，无领域内容。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "template" / "package" / "scripts"))

import yaml  # noqa: E402
from render_init_blocks import (  # noqa: E402
    _d2_fields,
    _load_locks,
    _scenario_fields,
    render_nn_config,
    render_readme,
    render_scenario_table,
    write_intent,
)

SCRIPTS = Path(__file__).resolve().parents[1] / "template" / "package" / "scripts"

README_TMPL = """# Demo
<!-- D2_DATA_SPLIT -->
PROFILE: supervised
DATA_ROOT: {DATA_ROOT}
SPLIT_KIND: {SPLIT_KIND}
TRAIN: {TRAIN_DESC}
VAL: {VAL_DESC}
TEST: {TEST_DESC}
<!-- /D2_DATA_SPLIT -->
<!-- SCENARIO_POLICY -->
SCENARIO_AXIS: {SCENARIO_AXIS}
ACTIVE_SCENARIOS: {ACTIVE_SCENARIOS}
SCENARIO_POLICY: {SCENARIO_POLICY}
DEFAULT_SCENARIO: {DEFAULT_SCENARIO}
<!-- /SCENARIO_POLICY -->
<!-- AGENT_BOUNDARY -->
OLD_LINE: keep-or-replace
<!-- /AGENT_BOUNDARY -->
"""

LOCKS = {
    "D1-scenario-inventory": (
        "D1.SCENARIOS=demo×2tier; DEFAULT=demo_ref; "
        "SCENARIO_AXIS=demo; SCENARIO_POLICY=focus; "
        "SCENARIO_IDS=demo_ref:reference,demo_auto:automatic"
    ),
    "D2-data-split": (
        "D2.SPLIT=TRAIN80UE(19120)/VAL3200/TEST20UE(5980,frozen)/GUARD1600; "
        "NORM=fitTRAIN; DATA_ROOT=data/; SPLIT_KIND=train_val_test; "
        "EVAL_USES=val(only-eval); TEST_USES=test(once); "
        "E3_EVAL_FOR_KEEP=contract.test; VAL_TEST_SAME_DISTRIBUTION=no"
    ),
    "E1-metrics": "E1.PRIMARY=test_top1(max); AUX=demo_loss(guard_only)",
    "E5-tsv-columns": "E5.COLS=[baseline_tag,scenario,tier,test_top1]",
    "O3-baseline-anchors": "O3.PLAIN=non_ai(argmax); NO_MEASURED_VALUES=首轮自证",
}

# 机读题（resolved.json fields 非 lock 部分）
MACHINE = {
    "G2-goal-value": {"value": 0.66},
    "O1-time-budget": {"seconds": 7777},
    "O2-gpus-parallel": {"gpus": [3], "max_parallel": 2},
    "O4-repro-determinism": {"seed": 42},
    "G1-experiment-mode": {},
}


def _make_repo(tmp_path: Path, readme: str = README_TMPL) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "README.md").write_text(readme, encoding="utf-8")
    (tmp_path / "_runs").mkdir(exist_ok=True)
    return tmp_path


def _write_resolved(tmp_path: Path, locks: dict) -> Path:
    p = tmp_path / ".auto-nn" / "init-answers.resolved.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"resolved": {k: {"fields": {"lock": v}} for k, v in locks.items()}},
                   ensure_ascii=False),
        encoding="utf-8",
    )
    return p


def test_d2_fields_segment_mapping():
    f = _d2_fields(LOCKS["D2-data-split"])
    assert f["SPLIT_KIND"] == "train_val_test"
    assert f["TRAIN"] == "TRAIN80UE(19120)"      # 段含数字也能切开（非 \b 边界）
    assert f["TEST"] == "TEST20UE(5980,frozen)"
    assert "GUARD" not in f                       # GUARD 不进 README 块
    assert f["NORMALIZE_FIT_ON"] == "TRAIN"
    assert f["VAL_TEST_SAME_DISTRIBUTION"] == "no"


def test_scenario_fields_priority():
    f = _scenario_fields(LOCKS)
    assert f["SCENARIO_AXIS"] == "demo"
    assert f["SCENARIO_POLICY"] == "focus"
    # ACTIVE_SCENARIOS 必须是场景 ID（R3 与 F1 场景清单对账）：有 SCENARIO_IDS 用 ID 列
    assert f["ACTIVE_SCENARIOS"] == "demo_ref,demo_auto"
    assert f["DEFAULT_SCENARIO"] == "demo_ref"


def test_scenario_fields_fallback_to_shorthand():
    """无 SCENARIO_IDS 才退回 SCENARIOS= 简写（该形态 R3 会报，交迁移向导补机读清单）。"""
    no_ids = {k: v for k, v in LOCKS.items() if k != "D1-scenario-inventory"}
    no_ids["D1-scenario-inventory"] = (
        "D1.SCENARIOS=demo×2tier(reference/automatic); DEFAULT=demo_ref; "
        "SCENARIO_AXIS=demo; SCENARIO_POLICY=focus"
    )
    f = _scenario_fields(no_ids)
    assert f["ACTIVE_SCENARIOS"] == "demo×2tier(reference/automatic)"


def test_load_locks_reads_freeform_lock(tmp_path):
    p = _write_resolved(tmp_path, LOCKS)
    assert _load_locks(p)["D2-data-split"].startswith("D2.SPLIT=")


def test_render_readme_fills_and_replaces_boundary(tmp_path):
    repo = _make_repo(tmp_path)
    notes = render_readme(repo, LOCKS)
    assert any("README" in n for n in notes)
    text = (repo / "README.md").read_text(encoding="utf-8")
    assert "{SPLIT_KIND}" not in text and "{TRAIN_DESC}" not in text
    assert "TRAIN: TRAIN80UE(19120)" in text
    assert "SCENARIO_POLICY: focus" in text
    assert "CONTRACT_IMMUTABLE: contract/" in text   # AGENT_BOUNDARY 整体替换
    assert "OLD_LINE" not in text


def test_render_readme_skips_when_no_markers(tmp_path):
    repo = _make_repo(tmp_path, readme="# plain old repo\nno blocks here\n")
    render_readme(repo, LOCKS)
    assert (repo / "README.md").read_text(encoding="utf-8").startswith("# plain old repo")


def test_render_scenario_table_goal_and_idempotent(tmp_path):
    repo = _make_repo(tmp_path)
    notes = render_scenario_table(repo, LOCKS, MACHINE)
    assert any("场景清单" in n for n in notes)
    text = (repo / "README.md").read_text(encoding="utf-8")
    assert text.count("### 场景清单") == 1
    # 当前目标列 = E1.PRIMARY + 机读 G2 目标值合成
    assert "| demo_ref | reference | test_top1 ≥ 0.66 |" in text
    assert "| demo_auto | automatic | test_top1 ≥ 0.66 |" in text
    # 重跑幂等：不重复插
    render_scenario_table(repo, LOCKS, MACHINE)
    assert (repo / "README.md").read_text(
        encoding="utf-8").count("### 场景清单") == 1


def test_render_scenario_table_skips_without_ids_or_block(tmp_path):
    repo = _make_repo(tmp_path)
    no_ids = {k: v for k, v in LOCKS.items() if k != "D1-scenario-inventory"}
    notes = render_scenario_table(repo, no_ids, MACHINE)   # 答卷无机读清单：不代答
    assert notes == []
    assert "### 场景清单" not in (repo / "README.md").read_text(encoding="utf-8")
    repo2 = _make_repo(tmp_path / "noblock", readme="# no policy block\n")
    notes2 = render_scenario_table(repo2, LOCKS, MACHINE)  # 无 SCENARIO_POLICY 块：警告不插
    assert any("警告" in n for n in notes2)
    assert "### 场景清单" not in (repo2 / "README.md").read_text(encoding="utf-8")


def test_render_nn_config_writes_machine_answers(tmp_path):
    repo = _make_repo(tmp_path)
    (repo / "nn-config.yaml").write_text(
        "agent:\n  scenario_default: old_scn\n", encoding="utf-8")
    notes = render_nn_config(repo, LOCKS, MACHINE)
    assert any("goal.target" in n for n in notes)
    cfg = yaml.safe_load((repo / "nn-config.yaml").read_text(encoding="utf-8"))
    assert cfg["goal"]["target"] == 0.66
    assert cfg["goal"]["metric"] == "test_top1"       # E1.PRIMARY 名
    assert cfg["time_budget"] == 7777                 # O1
    assert cfg["gpus"] == [3] and cfg["max_parallel"] == 2   # O2
    assert cfg["seed"] == 42                          # O4
    assert cfg["agent"]["scenario_default"] == "demo_ref"    # D1.DEFAULT（agent 段留置）


def test_render_nn_config_skips_missing_fields(tmp_path):
    repo = _make_repo(tmp_path)
    (repo / "nn-config.yaml").write_text("agent:\n  scenario_default: old_scn\n",
                                         encoding="utf-8")
    notes = render_nn_config(repo, {}, {})            # 答卷无机读答案：不代答
    assert any("无可落盘字段" in n for n in notes)
    cfg = yaml.safe_load((repo / "nn-config.yaml").read_text(encoding="utf-8"))
    assert cfg["agent"]["scenario_default"] == "old_scn"  # 原值未动


def test_renderer_does_not_touch_results_tsv(tmp_path):
    """TSV 表头唯一事实源 = contract（regen_results_tsv.py）；渲染器零接触。"""
    repo = _make_repo(tmp_path)
    tsv = repo / "_runs" / "results.tsv"
    tsv.write_text("experiment\told\nrow\tkept\n", encoding="utf-8")
    render_readme(repo, LOCKS)
    render_scenario_table(repo, LOCKS, MACHINE)
    render_nn_config(repo, LOCKS, MACHINE)
    assert tsv.read_text(encoding="utf-8") == "experiment\told\nrow\tkept\n"


def test_write_intent_plain_and_skip(tmp_path):
    repo = _make_repo(tmp_path)
    notes = write_intent(repo, LOCKS)               # O3 有 PLAIN → 落盘 intent
    assert any("intent 已落盘" in n for n in notes)
    intent = json.loads((repo / "saved" / "baseline_start_intent.json").read_text())
    assert intent["start_runs"] == "plain"
    assert intent["scenario_id"] == "demo_ref"
    assert intent["plain_recipe"] == "non_ai(argmax)"   # O3.PLAIN= 值进 recipe hint
    repo2 = _make_repo(tmp_path / "no_plain")
    locks2 = dict(LOCKS, **{"O3-baseline-anchors": "O3.ANCHOR=Adam1e-3"})
    write_intent(repo2, locks2)                     # O3 无 PLAIN → skipped 标记
    assert (repo2 / ".auto-nn" / "baseline-intent-skipped").is_file()


def test_write_intent_no_o3(tmp_path):
    repo = _make_repo(tmp_path)
    notes = write_intent(repo, {k: v for k, v in LOCKS.items() if not k.startswith("O3")})
    assert (repo / ".auto-nn" / "baseline-intent-skipped").is_file()
