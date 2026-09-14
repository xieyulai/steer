"""query.py 方法名 token 抽取单测（修未收录方法查询词 0 hit）。

probe 实证：原始名 coordatt_se_cnn（下划线连写）全 provider 0 hit；
拆出的单辨识 token `coordatt` → scholar 10 / arxiv 1 / github 3（命中原论文）。
故 fingerprint 无 catalog_hit 时，从 new_register / MODEL_ARCH 抽辨识 token 做查询。
"""
from __future__ import annotations

import sys, os
_PKG = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PKG not in sys.path:
    sys.path.insert(0, _PKG)

from types import SimpleNamespace

from lib.external.query import (
    _method_tokens_from_fingerprint,
    build_paper_query,
)


def _ctx(fingerprint, task_domain="auto-nn-fmnist-v2 — FashionMNIST 监督图像分类"):
    return SimpleNamespace(rationale="", phase2_focus="", fingerprint=fingerprint, task_domain=task_domain)


# --- _method_tokens_from_fingerprint ---

def test_new_register_extracts_distinctive_token():
    fp = {"reasons": ["new_register:learner:coordatt_se_cnn"], "catalog_hits": []}
    assert _method_tokens_from_fingerprint(fp) == "coordatt"


def test_model_arch_extracts_distinctive_token():
    fp = {"primary_keys_changed": {"MODEL_ARCH": ["coordconv_cnn"]}, "reasons": []}
    assert _method_tokens_from_fingerprint(fp) == "coordconv"


def test_all_generic_tokens_returns_empty():
    # 全被停用表滤掉 → 返回 ""（走原 task_domain 兜底，不吐垃圾）
    fp = {"reasons": ["new_register:learner:custom_net_v2"], "catalog_hits": []}
    assert _method_tokens_from_fingerprint(fp) == ""


def test_short_tokens_filtered():
    # se/cnn/v2 等短/通用 token 不应单独成为查询词
    fp = {"reasons": ["new_register:learner:se_cnn"]}
    assert _method_tokens_from_fingerprint(fp) == ""


def test_none_fingerprint_returns_empty():
    assert _method_tokens_from_fingerprint(None) == ""


# --- build_paper_query 集成 ---

def test_build_query_uses_method_token_not_project_desc():
    # 无 catalog_hit 但有 new_register → 查询词是辨识 token，不是整段项目描述
    fp = {"reasons": ["new_register:learner:coordatt_se_cnn"], "catalog_hits": []}
    q = build_paper_query(_ctx(fp))
    assert "coordatt" in q
    assert "fmnist" not in q.lower()  # 不再退回项目描述


def test_catalog_hit_still_wins():
    # catalog 命中优先级最高（已知方法项目零影响）
    fp = {
        "catalog_hits": [{"paper_query": "timm efficient image model"}],
        "reasons": ["new_register:learner:coordatt_se_cnn"],
    }
    assert build_paper_query(_ctx(fp)) == "timm efficient image model"


def test_no_signal_falls_back_to_task_domain():
    # 既无 catalog_hit 也无方法 token → 走原 task_domain 兜底（不劣化）
    fp = {"reasons": ["unknown_key"], "catalog_hits": []}
    q = build_paper_query(_ctx(fp, task_domain="image classification"))
    assert q == "image classification"
