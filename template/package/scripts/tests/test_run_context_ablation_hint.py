"""体系级插入式扩展 · 改动三 路线A：KEEP 且严格改善时注入组件归因消融引导句。

设计要点：
- 落点：format_run_context_md（抄 PDH 段，单点插入）
- 触发条件：KEEP 且 improvement > delta（=should_keep 的严格改善路径，
  reason 含「提升满足阈值/严格改善/↑」）
- 复用 OVAT 通道，不新增技能

本测试锁定 _emit_ablation_hint 触发逻辑：KEEP+严格改善 → 注入；near_best /
无历史 / discard / explore keep → 不注入；格式漂移 → 静默 None（降级，非崩）。
build-run-context.py 是连字符脚本名（不能普通 import）→ importlib 按 path 加载。
"""
import importlib.util
import json
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "_build_run_context_under_test", _SCRIPTS / "build-run-context.py"
)
brc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(brc)


def _write_round_decision(repo_root: Path, payload: dict) -> None:
    runs = repo_root / "_runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "round_decision.json").write_text(json.dumps(payload), encoding="utf-8")


def _ctx(repo_root: Path) -> dict:
    return {"repo_root": repo_root}


# ---- 触发：KEEP + 严格改善 ----

def test_trigger_primary_strict_improvement(tmp_path):
    """主指标路径严格改善（reason 含「提升满足阈值」）→ 注入，含指标值。"""
    _write_round_decision(tmp_path, {
        "keep_suggestion": True,
        "reason": "主指标较历史最佳提升满足阈值：当前 0.8600，历史最佳 0.8200，diff=0.0400 (mode=relative, delta=0.001)",
        "primary_metric": {"key": "val_acc", "value": 0.86, "direction": "maximize"},
    })
    out = brc._emit_ablation_hint(_ctx(tmp_path))
    assert out is not None
    assert "ablation-hint" in out
    assert "0.8600" in out
    assert "val_acc" in out


def test_trigger_any_primary_strict(tmp_path):
    """any_primary 严格改善（reason 含「严格改善」）→ 注入。"""
    _write_round_decision(tmp_path, {
        "keep_suggestion": True,
        "reason": "任一主指标达标: 严格改善: val_acc",
        "primary_metric": {"key": "val_acc", "value": 0.9, "direction": "maximize"},
    })
    assert brc._emit_ablation_hint(_ctx(tmp_path)) is not None


def test_trigger_all_primary_arrow(tmp_path):
    """all_primary 严格改善（reason ok_parts 用「↑」）→ 注入。"""
    _write_round_decision(tmp_path, {
        "keep_suggestion": True,
        "reason": "全部主指标达标: val_acc↑, map↑",
        "primary_metric": {"key": "val_acc", "value": 0.7, "direction": "maximize"},
    })
    assert brc._emit_ablation_hint(_ctx(tmp_path)) is not None


def test_trigger_dict_keep_suggestion(tmp_path):
    """keep_suggestion 为 dict（decision=keep）→ 视作 KEEP → 注入。"""
    _write_round_decision(tmp_path, {
        "keep_suggestion": {"decision": "keep", "action": "keep"},
        "reason": "严格改善: val_acc",
        "primary_metric": {"key": "val_acc", "value": 0.8, "direction": "maximize"},
    })
    assert brc._emit_ablation_hint(_ctx(tmp_path)) is not None


def test_strict_but_missing_value_still_fires(tmp_path):
    """严格改善但 primary_metric.value 缺失 → 仍注入（只是不带数字）。"""
    _write_round_decision(tmp_path, {
        "keep_suggestion": True,
        "reason": "严格改善: val_acc",
        "primary_metric": {"key": "val_acc", "direction": "maximize"},
    })
    out = brc._emit_ablation_hint(_ctx(tmp_path))
    assert out is not None
    assert "ablation-hint" in out


# ---- 不触发：KEEP 但非严格改善 / 非 KEEP ----

def test_no_trigger_near_best(tmp_path):
    """KEEP 但 near_best（reason 含「接近最佳」，无严格改善标记）→ 不注入。"""
    _write_round_decision(tmp_path, {
        "keep_suggestion": True,
        "reason": "主指标未达 primary_delta，但在 near_best_abs=0.01 内接近历史最佳：当前 0.8195",
        "primary_metric": {"key": "val_acc", "value": 0.8195, "direction": "maximize"},
    })
    assert brc._emit_ablation_hint(_ctx(tmp_path)) is None


def test_no_trigger_no_history(tmp_path):
    """KEEP 但无历史可比（首轮）→ 不注入（非真改善）。"""
    _write_round_decision(tmp_path, {
        "keep_suggestion": True,
        "reason": "无历史 TSV 可比，默认可 keep",
        "primary_metric": {"key": "val_acc", "value": 0.5, "direction": "maximize"},
    })
    assert brc._emit_ablation_hint(_ctx(tmp_path)) is None


def test_no_trigger_discard(tmp_path):
    """discard（keep_suggestion=False）→ 不注入。"""
    _write_round_decision(tmp_path, {
        "keep_suggestion": False,
        "reason": "严格改善: val_acc",  # 即便 reason 含标记，discard 也不注入
        "primary_metric": {"key": "val_acc", "value": 0.8, "direction": "maximize"},
    })
    assert brc._emit_ablation_hint(_ctx(tmp_path)) is None


# ---- 降级：缺文件 / 损坏 ----

def test_no_file_returns_none(tmp_path):
    """无 round_decision.json → None。"""
    assert brc._emit_ablation_hint(_ctx(tmp_path)) is None


def test_corrupt_json_returns_none(tmp_path):
    """损坏 JSON → None 不崩（best-effort，与 paper_hint 同型）。"""
    runs = tmp_path / "_runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "round_decision.json").write_text("{ not json", encoding="utf-8")
    assert brc._emit_ablation_hint(_ctx(tmp_path)) is None


def test_no_repo_root_returns_none():
    """ctx 无 repo_root（或非 Path）→ None。"""
    assert brc._emit_ablation_hint({}) is None
    assert brc._emit_ablation_hint({"repo_root": "not-a-path"}) is None


# ---- evaluation_result.json 兜底 ----

def test_reads_evaluation_result_json_fallback(tmp_path):
    """无 round_decision.json 但有 evaluation_result.json → 读它（与 round_decision 同优先级兜底）。"""
    runs = tmp_path / "_runs"
    runs.mkdir(parents=True, exist_ok=True)
    (runs / "evaluation_result.json").write_text(json.dumps({
        "keep_suggestion": True,
        "reason": "严格改善: val_acc",
        "primary_metric": {"key": "val_acc", "value": 0.9, "direction": "maximize"},
    }), encoding="utf-8")
    assert brc._emit_ablation_hint(_ctx(tmp_path)) is not None


# ---- format_run_context_md 渲染 ----

def test_md_renders_ablation_hint(tmp_path):
    """KEEP+严格改善 → md 出现 ### ablation-hint 段。"""
    _write_round_decision(tmp_path, {
        "keep_suggestion": True,
        "reason": "主指标较历史最佳提升满足阈值：当前 0.8600，历史最佳 0.8200",
        "primary_metric": {"key": "val_acc", "value": 0.86, "direction": "maximize"},
    })
    md = brc.format_run_context_md({"repo_root": tmp_path})
    assert "### ablation-hint" in md
    assert "0.8600" in md


def test_md_omits_ablation_hint_when_discard(tmp_path):
    """discard → md 无该段。"""
    _write_round_decision(tmp_path, {
        "keep_suggestion": False,
        "reason": "主指标未达阈值",
        "primary_metric": {"key": "val_acc", "value": 0.1, "direction": "maximize"},
    })
    md = brc.format_run_context_md({"repo_root": tmp_path})
    assert "### ablation-hint" not in md
