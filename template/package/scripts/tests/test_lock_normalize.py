"""P0-2 第二阶段：lock 三态 normalize 测试。"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib import lock_normalize as LN


# ── 三态 case ──────────────────────────────────────────────────────

def test_already_structured_returns_as_is():
    """嵌套编码（T1.HARD=X）原样返回，warns=[]。"""
    text = "T1.HARD=CrossEntropyLoss; T1.TUNABLE=LR,BS"
    norm, warns = LN.normalize_lock(text, slug="F1")
    assert norm == text, f"already-structured should pass through; got {norm!r}"
    assert warns == [], f"already-structured should not warn; got {warns!r}"


def test_human_template_S1_normalizes_to_HARD():
    """'T1=主 loss 锁 CrossEntropyLoss' → 'T1.HARD=CrossEntropyLoss'"""
    text = "T1=主 loss 锁 CrossEntropyLoss"
    norm, warns = LN.normalize_lock(text, slug="F1")
    assert norm == "T1.HARD=CrossEntropyLoss", f"got {norm!r}"
    assert warns == []


def test_unrecognized_returns_with_warn():
    """纯叙述（mammoth 风格自由文本）原样返回 + warn。"""
    text = "3-layer loop (task→epoch→batch); contract exposes train_one_task/eval_after_task/end_all_tasks; no mid-task eval"
    norm, warns = LN.normalize_lock(text, slug="F1")
    assert norm == text, f"unrecognized should be kept as-is; got {norm!r}"
    assert "unrecognized_template" in warns, f"expected warn; got {warns!r}"


# ── 5-6 模板 case ──────────────────────────────────────────────────

def test_S1_KV_lock_to_HARD():
    """T1=主 loss 锁 X → T1.HARD=X"""
    norm, _ = LN.normalize_lock("T1=主 loss 锁 CrossEntropyLoss", slug="T1")
    assert norm == "T1.HARD=CrossEntropyLoss"


def test_S2_KV_passthrough_already_coded():
    """O2=gpus=[2,3]; max_parallel=2 （半结构化）：原样落（已是编码）"""
    text = "O2=gpus=[2,3]; max_parallel=2"
    norm, warns = LN.normalize_lock(text, slug="O2")
    assert norm == text
    assert warns == []


def test_S3_ALLOWED_to_list():
    """'其余（optimizer/scheduler/weight decay）允许 Agent 调' → 'T1.ALLOWED=[optimizer,scheduler,weight_decay]'"""
    norm, _ = LN.normalize_lock("其余（optimizer/scheduler/weight decay）允许 Agent 调", slug="T1")
    assert norm == "T1.ALLOWED=[optimizer,scheduler,weight_decay]"


def test_S4_mammoth_separate_terminology():
    """mammoth 风格 'agent.exploration_style=aggressive; keep mammoth aug pipeline'：
    agent.exploration_style 不在 LOCK_FIELDS 词汇库 → 仅识别 keep mammoth aug pipeline 后的部分；
    简化处理：K=v 形式按 LOCK_FIELDS 集识别 → 仅识别 K 在 LOCK_FIELDS 的。
    """
    text = "agent.exploration_style=aggressive; keep mammoth aug pipeline"
    norm, warns = LN.normalize_lock(text, slug="E6")
    # 期望：KV 已识别部分 + 余下（不在 LOCK_FIELDS 的）原样保留 + warn
    assert "agent.exploration_style=aggressive" in norm
    assert "keep mammoth aug pipeline" in norm
    assert "unrecognized_template" in warns or warns == [], f"got {warns!r}"


def test_S5_csi_brief_split():
    """'scenario: scenario_id; metrics: test_acc/val_acc' → 'SCENARIO=scenario_id; METRICS=[test_acc,val_acc]'"""
    norm, _ = LN.normalize_lock("scenario: scenario_id; metrics: test_acc/val_acc", slug="E1")
    assert "SCENARIO=scenario_id" in norm
    assert "METRICS=[test_acc,val_acc]" in norm


def test_S6_KV_with_note_stripped():
    """'target: 0.95（用户确认）' → 'TARGET=0.95'（括号注忽略）"""
    norm, _ = LN.normalize_lock("target: 0.95（用户确认）", slug="G2")
    assert "TARGET=0.95" in norm


# ── Task 2：warn 双写 + 边界 case ───────────────────────────────

def test_warn_log_writes_csv_line():
    """warn 落 .lock_normalize_warnings.log 为 CSV：timestamp,slug,reason,text"""
    text = "3-layer loop (task→epoch→batch); contract exposes train_one_task"
    _, warns = LN.normalize_lock(text, slug="T1")
    assert "unrecognized_template" in warns

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        log_path = os.path.join(td, ".auto-nn/lock_normalize_warnings.log")
        LN.write_warn_log(slug="T1", text=text, reason="unrecognized_template", log_path=log_path)
        content = open(log_path, encoding="utf-8").read()
        assert "T1" in content
        assert "unrecognized_template" in content
        assert "3-layer loop" in content


def test_empty_string_returns_empty():
    """空字符串 → ("", [])"""
    norm, warns = LN.normalize_lock("", slug="T1")
    assert norm == ""
    assert warns == []


def test_whitespace_only_normalized():
    """全空白 → ("", [])"""
    norm, warns = LN.normalize_lock("   \n  \t  ", slug="T1")
    assert norm == ""
    assert warns == []


def test_norm_warns_appended_to_existing_log():
    """多次写入 append-only：log 文件累积多行"""
    text1 = "3-layer loop (task→epoch→batch)"
    text2 = "complex nested architecture with skip connections"
    with tempfile.TemporaryDirectory() as td:
        log_path = os.path.join(td, ".auto-nn/lock_normalize_warnings.log")
        LN.write_warn_log("T1", text1, "unrecognized_template", log_path)
        LN.write_warn_log("E6", text2, "unrecognized_template", log_path)
        lines = open(log_path, encoding="utf-8").read().strip().splitlines()
        assert len(lines) == 2
        assert "T1" in lines[0]
        assert "E6" in lines[1]