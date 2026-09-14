"""reflect.py 训练过程 loss 细节读链单测（③-ii）。

覆盖：
- _load_train_dynamics：读 <exp_dir>/train_dynamics.json 摘要（有 anomaly / 无 anomaly / 缺失 / 损坏）
- _dynamics_compact_for_phase0：tail 渲染（混合 / 仅 tail / 全跳过 / 空 rows）
- _phase0_prompt：dynamics 段（有则注入 / 无则省略）

跑法: cd template/package && PYTHONPATH=scripts pytest scripts/tests/test_reflect_train_dynamics.py -v
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# bootstrap template/package 到 path，使 `import reflect` 可用
# (reflect.py 自身再把 scripts/ 加进 path 以解析 lib.external.*)
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

import reflect  # noqa: E402


# ---------- Task A: _load_train_dynamics ----------

def _write_dynamics(exp_dir: Path, payload: dict) -> Path:
    exp_dir.mkdir(parents=True, exist_ok=True)
    p = exp_dir / "train_dynamics.json"
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return p


def test_load_train_dynamics_with_anomaly(tmp_path):
    exp = tmp_path / "exp_anom"
    _write_dynamics(exp, {
        "anomalies": ["loss_divergence"],
        "train_loss": {"trend": "increasing", "first": 1.0, "last": 2.5},
        "train_val_gap": {"trend": "worsening", "available": True},
        "plateau": {"detected": False, "since_step": None},
        "stop": {"reason": "early_stop", "stopped_early": True},
    })
    out = reflect._load_train_dynamics(exp)
    assert out == {
        "anomalies": ["loss_divergence"],
        "train_loss": "increasing",
        "train_val_gap": "worsening",
        "plateau": False,
        "stop_reason": "early_stop",
    }


def test_load_train_dynamics_no_anomaly(tmp_path):
    exp = tmp_path / "exp_ok"
    _write_dynamics(exp, {
        "anomalies": [],
        "train_loss": {"trend": "decreasing"},
        "train_val_gap": {"trend": "stable", "available": True},
        "plateau": {"detected": True},
        "stop": {"reason": "epoch_done", "stopped_early": False},
    })
    out = reflect._load_train_dynamics(exp)
    assert out["anomalies"] == []
    assert out["train_loss"] == "decreasing"
    assert out["train_val_gap"] == "stable"
    assert out["plateau"] is True
    assert out["stop_reason"] == "epoch_done"


def test_load_train_dynamics_missing(tmp_path):
    # 目录存在但无 train_dynamics.json → None
    exp = tmp_path / "exp_empty"
    exp.mkdir()
    assert reflect._load_train_dynamics(exp) is None


def test_load_train_dynamics_corrupt(tmp_path):
    exp = tmp_path / "exp_bad"
    _write_dynamics(exp, {})  # 先建占位再覆盖成坏 json
    (exp / "train_dynamics.json").write_text("{not valid json", encoding="utf-8")
    assert reflect._load_train_dynamics(exp) is None


# ---------- Task B: _dynamics_compact_for_phase0 ----------

def _make_row(experiment: str, exp_dir: Path) -> dict:
    return {"experiment": experiment, "exp_dir": str(exp_dir)}


def _dyn_payload(anomalies=None, trend="flat", gap=None, plateau=False, stop="epoch_done"):
    return {
        "anomalies": anomalies or [],
        "train_loss": {"trend": trend},
        "train_val_gap": {"trend": gap} if gap else {"available": False},
        "plateau": {"detected": plateau},
        "stop": {"reason": stop},
    }


def test_dynamics_compact_mixed(tmp_path):
    # e1 有 anomaly；e2 正常但 plateau；e3 无 dynamics；e4 无 exp_dir
    e1, e2, e3 = (tmp_path / "e1"), (tmp_path / "e2"), (tmp_path / "e3")
    _write_dynamics(e1, _dyn_payload(["loss_divergence"], "increasing", "worsening", False, "early_stop"))
    _write_dynamics(e2, _dyn_payload([], "decreasing", "stable", True, "epoch_done"))
    e3.mkdir()
    rows = [
        _make_row("e1", e1),
        _make_row("e2", e2),
        _make_row("e3", e3),
        {"experiment": "e4"},  # 无 exp_dir
    ]
    out = reflect._dynamics_compact_for_phase0(rows, tmp_path, len(rows))
    lines = out.splitlines()
    assert len(lines) == 2  # e3（无 dynamics）/ e4（无 exp_dir）跳过
    assert lines[0].startswith("- e1: ")
    assert "anomalies=[loss_divergence]" in lines[0]
    assert "train_loss=increasing" in lines[0]
    assert "gap=worsening" in lines[0]
    assert lines[1].startswith("- e2: ")
    assert "anomalies" not in lines[1]  # 无 anomaly 不显空数组
    assert "train_loss=decreasing" in lines[1]
    assert "gap=stable" in lines[1]
    assert "plateau=True" in lines[1]
    assert "stop=epoch_done" in lines[1]


def test_dynamics_compact_tail_only(tmp_path):
    # tail_rows 只取尾部 N 行（与 _ledger_compact_for_phase0 同口径）
    e1, e2 = (tmp_path / "e1"), (tmp_path / "e2")
    _write_dynamics(e1, _dyn_payload([], "flat", stop="epoch_done"))
    _write_dynamics(e2, _dyn_payload([], "flat", stop="epoch_done"))
    rows = [_make_row("e1", e1), _make_row("e2", e2)]
    out = reflect._dynamics_compact_for_phase0(rows, tmp_path, 1)  # 只取尾部 1 行
    assert "e2" in out
    assert "e1" not in out


def test_dynamics_compact_relative_exp_dir(tmp_path):
    # exp_dir 为相对路径时，按 repo_root 解析
    repo = tmp_path / "repo"
    repo.mkdir()
    exp_rel = repo / "_runs" / "exp" / "rel1"
    _write_dynamics(exp_rel, _dyn_payload([], "flat", stop="epoch_done"))
    rows = [{"experiment": "rel1", "exp_dir": "_runs/exp/rel1"}]  # 相对
    out = reflect._dynamics_compact_for_phase0(rows, repo, 1)
    assert "rel1" in out


def test_dynamics_compact_all_skip(tmp_path):
    e1 = tmp_path / "e1"
    e1.mkdir()  # 无 dynamics
    rows = [_make_row("e1", e1)]
    assert reflect._dynamics_compact_for_phase0(rows, tmp_path, 1) == ""


def test_dynamics_compact_empty_rows():
    assert reflect._dynamics_compact_for_phase0([], Path("/tmp"), 5) == ""


# ---------- Task C: _phase0_prompt dynamics 段 ----------

def _base_phase0_kwargs(**overrides):
    kw = dict(
        experience_body="exp body",
        protocol_body="proto body",
        jsonl_compact="e1\t0.85\tdesc",
        dynamics_compact="",
        metric_key="accuracy",
        metric_direction="max",
        out_max_chars=2000,
    )
    kw.update(overrides)
    return kw


def test_phase0_prompt_with_dynamics():
    p0 = reflect._phase0_prompt(**_base_phase0_kwargs(
        dynamics_compact="- e1: anomalies=[loss_divergence] · train_loss=increasing · stop=early_stop",
    ))
    assert "### 训练过程 loss 细节" in p0
    assert "anomalies=[loss_divergence]" in p0
    # 段位置：在 jsonl tail 之后、metric_key 之前
    assert p0.index("训练过程 loss 细节") > p0.index("results.jsonl")


def test_phase0_prompt_without_dynamics():
    p0 = reflect._phase0_prompt(**_base_phase0_kwargs(dynamics_compact=""))
    assert "### 训练过程 loss 细节" not in p0
    # 空时不留残段标题
    assert "train_dynamics" not in p0


def test_phase0_prompt_dynamics_default_empty():
    # 不传 dynamics_compact → 默认 "" → 段省略（向后兼容既有调用语义）
    p0 = reflect._phase0_prompt(
        experience_body="x", protocol_body="y", jsonl_compact="e1\t1.0\td",
        metric_key="acc", metric_direction="max", out_max_chars=1000,
    )
    assert "### 训练过程 loss 细节" not in p0
