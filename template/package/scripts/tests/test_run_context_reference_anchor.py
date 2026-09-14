"""③-i: _state_reference_anchor_value 三态 + 靶子段 reference 行渲染。

镜像 test_run_context_baseline_anchors.py 的 importlib 载入范式（build-run-context.py 文件名含连字符）。
anchors_dict 契约：返回 {"metric_leader": {"value": X}}（② 靶子段读 ml.value）。
"""
import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parent.parent
BRC_PATH = SCRIPTS / "build-run-context.py"


def _load_brc():
    spec = importlib.util.spec_from_file_location("brc_ref", BRC_PATH)
    brc = importlib.util.module_from_spec(spec)
    sys.modules["brc_ref"] = brc
    spec.loader.exec_module(brc)
    return brc


_REF_SECTION = """## 基线锚点（external reference，init 探测，固定）

> 仅 init 探测轮填一次；novel 任务或无公开参照时留空（null）。

- reference_anchor_value: 0.9850
- reference_source: README · CIFAR-10 基准段
- reference_ref: README.md（"公开最好 0.985，基于 Smith et al. 2024"）
"""


def test_reference_from_experience_section(tmp_path):
    """EXPERIENCE「基线锚点」段有值 → 读出 float。"""
    (tmp_path / "EXPERIENCE.md").write_text(_REF_SECTION, encoding="utf-8")
    brc = _load_brc()
    v = brc._state_reference_anchor_value({"repo_root": tmp_path})
    assert v == 0.9850


def test_reference_section_absent_returns_none(tmp_path):
    """EXPERIENCE 无「基线锚点」段 → None（novel 常态）。"""
    (tmp_path / "EXPERIENCE.md").write_text(
        "## Tier 状态\n| Tier | routine |\n|---|---|\n| A | x |\n", encoding="utf-8")
    brc = _load_brc()
    v = brc._state_reference_anchor_value({"repo_root": tmp_path})
    assert v is None


def test_reference_json_takes_precedence(tmp_path):
    """saved/reference_anchor.json 存在 → 优先于 EXPERIENCE（与 plain :195 同优先级）。"""
    saved = tmp_path / "saved"
    saved.mkdir()
    (saved / "reference_anchor.json").write_text(
        '{"reference_anchor_value": 0.91}', encoding="utf-8")
    (tmp_path / "EXPERIENCE.md").write_text(_REF_SECTION, encoding="utf-8")  # 0.9850
    brc = _load_brc()
    v = brc._state_reference_anchor_value({"repo_root": tmp_path})
    assert v == 0.91  # json 优先


def test_reference_non_path_root_returns_none():
    """repo_root 非 Path → None（防御）。"""
    brc = _load_brc()
    assert brc._state_reference_anchor_value({"repo_root": "/not/a/path"}) is None
    assert brc._state_reference_anchor_value({}) is None


def test_emit_reference_row_with_value(tmp_path, monkeypatch):
    """reference 有值 → 靶子段 reference 行含值 +「还差」（gap=cur-ref，负→还差，对齐 _gap_tag）。"""
    (tmp_path / "EXPERIENCE.md").write_text(_REF_SECTION, encoding="utf-8")  # ref=0.9850
    brc = _load_brc()
    # 当前最佳 = 0.8200（anchors_dict 契约：metric_leader.value）
    monkeypatch.setattr(brc, "anchors_dict", lambda repo_root: {"metric_leader": {"value": 0.8200}})
    ctx = {"repo_root": tmp_path}
    block = brc._emit_baseline_anchors(ctx)
    assert "reference" in block
    assert "0.985" in block or "0.9850" in block
    # cur=0.82 < ref=0.985 → _gap_tag 走负分支「还差」0.1650
    assert "还差" in block


def test_emit_reference_row_none_shows_novel(tmp_path, monkeypatch):
    """reference None（novel/无公开参照）→ 不再写「待 ③-i」，改写「novel/无公开参照」。"""
    # 无 EXPERIENCE 段 → ref=None
    (tmp_path / "EXPERIENCE.md").write_text("## Tier 状态\n", encoding="utf-8")
    brc = _load_brc()
    monkeypatch.setattr(brc, "anchors_dict", lambda repo_root: {"metric_leader": {"value": 0.8200}})
    ctx = {"repo_root": tmp_path}
    block = brc._emit_baseline_anchors(ctx)
    assert "未标定" in block
    assert "novel/无公开参照" in block
    assert "待 ③-i" not in block  # 旧占位串必须消失
