"""abcde_modifier_derive.py — 已退役占位（2026-07 config-minimal）。

历史：曾用于从 abcde-boundaries.yaml 派生 modifier examples。
现在由 contract/metrics.py + workspace/__init__.py 直接实现 modifier 语义，
本模块保留为 governance-sync 的同步目标（dest 仍 expect 此文件存在）。
"""
from __future__ import annotations


def derive_modifiers(*args, **kwargs):  # pragma: no cover
    raise NotImplementedError("abcde_modifier_derive 已退役；modifier 由 contract/workspace 直接实现。")