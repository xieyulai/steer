"""TDD tests for B1 seed_repos lookup — universal framework/task theme mapping.

约束：
- 不绑业务：no mammoth / fashionmnist / cifar fixtures anywhere。
- Universal mock fingerprint/rationale only — 只读 JSON 数据 + _seed_repos_lookup 启发式。
- 只验通用语义：framework 命中 / task_domain 命中 / 都不命中 / 5 项封顶 / JSON 结构。
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.lib.external import executor

_DATA_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "seed_repos.json"
)


def _ctx(**kw):
    base = {
        "fingerprint": {"MODEL_ARCH": "", "task_domain": ""},
        "rationale": "",
    }
    base.update(kw)
    if "fingerprint" in kw and isinstance(kw["fingerprint"], dict):
        fp = dict(base["fingerprint"])
        fp.update(kw["fingerprint"])
        base["fingerprint"] = fp
    return base


def test_seed_repos_lookup_by_framework_token():
    """rationale 含 'timm' → 返回 huggingface/pytorch-image-models。"""
    ctx = _ctx(rationale="use timm for image classification backbones")
    result = executor._seed_repos_lookup(ctx)
    assert isinstance(result, list)
    assert "huggingface/pytorch-image-models" in result


def test_seed_repos_lookup_by_fingerprint_model_arch():
    """fingerprint.MODEL_ARCH == 'transformers' → 返回 huggingface/transformers。"""
    ctx = _ctx(
        fingerprint={"MODEL_ARCH": "transformers", "task_domain": ""},
        rationale="",
    )
    result = executor._seed_repos_lookup(ctx)
    assert "huggingface/transformers" in result


def test_seed_repos_lookup_by_task_domain():
    """fingerprint.task_domain == 'semantic-segmentation' → 命中 vision/monai/kornia。"""
    ctx = _ctx(
        fingerprint={"MODEL_ARCH": "", "task_domain": "semantic-segmentation"},
        rationale="",
    )
    result = executor._seed_repos_lookup(ctx)
    assert any(
        "MONAI" in r or "kornia" in r or "vision" in r for r in result
    )


def test_seed_repos_lookup_combined_framework_plus_task():
    """framework + task 双命中 → union，去重，不超 5。"""
    ctx = _ctx(
        fingerprint={
            "MODEL_ARCH": "torch",
            "task_domain": "object-detection",
        },
        rationale="",
    )
    result = executor._seed_repos_lookup(ctx)
    # pytorch/pytorch (framework) + pytorch/vision (framework+task)
    assert "pytorch/pytorch" in result
    assert "pytorch/vision" in result
    # 去重
    assert len(result) == len(set(result))
    # 5 项封顶
    assert len(result) <= 5


def test_seed_repos_lookup_no_match_returns_empty():
    """空 ctx/无命中 token → 返回 []（不抛错）。"""
    assert executor._seed_repos_lookup(None) == []
    assert executor._seed_repos_lookup({}) == []
    assert executor._seed_repos_lookup(
        _ctx(fingerprint={"MODEL_ARCH": "nonsense_xyz_unknown"})
    ) == []
    assert executor._seed_repos_lookup(
        _ctx(rationale="this rationale mentions nothing relevant")
    ) == []


def test_seed_repos_lookup_cap_5():
    """rationale 同时含多 framework/task → 5 项封顶 + 去重。"""
    ctx = _ctx(
        rationale=(
            "pytorch timm huggingface transformers lightgbm stable-baselines3 "
            "image-classification object-detection semantic-segmentation "
            "tabular reinforcement-learning"
        )
    )
    result = executor._seed_repos_lookup(ctx)
    assert len(result) <= 5
    assert len(result) >= 1
    assert len(result) == len(set(result))


def test_seed_repos_lookup_handles_missing_fingerprint():
    """ctx 无 fingerprint 字段 → safe fallback to empty list。"""
    result = executor._seed_repos_lookup({"rationale": "pytorch timm"})
    assert isinstance(result, list)
    assert "huggingface/pytorch-image-models" in result


def test_seed_repos_lookup_handles_non_dict_fingerprint():
    """fingerprint 非 dict（None/str/list）→ safe fallback，不抛。"""
    for bad in (None, "string", ["list"], 42):
        result = executor._seed_repos_lookup({"fingerprint": bad})
        assert isinstance(result, list)


def test_seed_repos_json_loadable():
    """JSON 数据文件存在 + schema 合规（v / frameworks / task_themes）。"""
    assert _DATA_PATH.exists(), f"missing seed_repos.json at {_DATA_PATH}"
    data = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    assert data["v"] == 1
    assert isinstance(data["frameworks"], dict)
    assert isinstance(data["task_themes"], dict)
    for k, v in data["frameworks"].items():
        assert isinstance(k, str) and k
        assert isinstance(v, list)
        assert all(isinstance(x, str) and "/" in x for x in v)
    for k, v in data["task_themes"].items():
        assert isinstance(k, str) and k
        assert isinstance(v, list)
        assert all(isinstance(x, str) and "/" in x for x in v)


def test_seed_repos_lookup_cache_is_stable():
    """_load_seed_repos() 缓存：多次调用结果一致（同 module 内）。"""
    a = executor._seed_repos_lookup(_ctx(rationale="pytorch"))
    b = executor._seed_repos_lookup(_ctx(rationale="pytorch"))
    assert a == b
