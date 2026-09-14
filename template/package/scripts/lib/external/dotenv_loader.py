"""Dotenv adapter: 加载 .env 文件 + 名字兼容。

解决的问题：
- 业务仓跑 reflect 时 SERPER_KEY / GITHUB_TOKEN 等在 ~/.env 文件里，
  但 os.environ 里没有（shell 没 export）
- 维护者/历史项目用 SERPER_KEY，新代码用 SERPER_API_KEY — 名字不匹配

设计：
- 自动找 ~/.env、~/.env.local、<repo>/.env、<repo>/.env.local
- 别名表：SERPER_API_KEY ← SERPER_KEY；GITHUB_TOKEN ← GH_TOKEN
- 不覆盖已设置的 env 变量（除非 override=True）
- 幂等：模块级 _LOADED 守卫，只 load 一次
- 副作用：导入时自动 load；调用方也可显式 load_dotenv()
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# 优先级（同名 canonical 取第一个非空）；每个 canonical 列候选名
_KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "SERPER_API_KEY": ("SERPER_API_KEY", "SERPER_KEY"),
    "GITHUB_TOKEN": ("GITHUB_TOKEN", "GH_TOKEN"),
    # 后续可加（OPENAI_API_KEY / ANTHROPIC_API_KEY / 等）
}

_GLOBAL_ENV_LOCATIONS: tuple[Path, ...] = (
    Path.home() / ".auto-nn" / ".keys",
    Path.home() / ".env",
    Path.home() / ".env.local",
)

_LOCAL_ENV_NAMES: tuple[str, ...] = (".env", ".env.local")

_LOADED: bool = False


def _parse_env_line(line: str) -> tuple[str, str] | None:
    """Parse ``KEY=VALUE`` (with optional quotes / comments)."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if "=" not in line:
        return None
    k, v = line.split("=", 1)
    k = k.strip()
    v = v.strip()
    if not k:
        return None
    # strip optional surrounding quotes
    if len(v) >= 2 and (
        (v[0] == v[-1] == '"') or (v[0] == v[-1] == "'")
    ):
        v = v[1:-1]
    # strip inline comment (only outside quotes — but we stripped quotes)
    if " #" in v:
        v = v.split(" #", 1)[0].rstrip()
    return (k, v)


def _read_env_file(path: Path) -> dict[str, str]:
    """Read a .env file → {KEY: VALUE} dict. Missing/empty file → {}."""
    if not path.is_file():
        return {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    out: dict[str, str] = {}
    for line in text.splitlines():
        kv = _parse_env_line(line)
        if kv:
            out[kv[0]] = kv[1]
    return out


def _resolve_canonical_keys(loaded: dict[str, str]) -> dict[str, str]:
    """对每个 canonical，遍历别名表取第一个非空值；同时保留非别名键。"""
    out: dict[str, str] = {}
    used: set[str] = set()
    for canonical, aliases in _KEY_ALIASES.items():
        for a in aliases:
            if a in loaded and loaded[a]:
                out[canonical] = loaded[a]
                used.add(a)
                break
    # 透传非别名键
    for k, v in loaded.items():
        if k not in used and k not in out:
            out[k] = v
    return out


def _candidate_paths(repo_root: Path | None) -> list[Path]:
    paths: list[Path] = list(_GLOBAL_ENV_LOCATIONS)
    if repo_root is not None:
        for name in _LOCAL_ENV_NAMES:
            p = repo_root / name
            if p not in paths:
                paths.append(p)
    return paths


def load_dotenv(repo_root: Path | None = None, *, override: bool = False) -> dict[str, str]:
    """Load .env files into os.environ；返回归一化后的 dict（供调用方检查）。

    Args:
        repo_root: 业务仓根（None 时只查 ~/.env 与 ~/.env.local）
        override: True 时覆盖已存在的 os.environ（同 key 优先文件）
                  False 时只填缺失的（默认；不破坏 shell 已设的值）

    Returns:
        归一化后的 {canonical_or_passthrough_key: value} dict。
    """
    global _LOADED
    merged: dict[str, str] = {}
    for p in _candidate_paths(repo_root):
        merged.update(_read_env_file(p))
    merged = _resolve_canonical_keys(merged)

    for k, v in merged.items():
        if override or k not in os.environ:
            os.environ[k] = v
    _LOADED = True
    return merged


def is_loaded() -> bool:
    return _LOADED


def reset_for_tests() -> None:
    """测试用：清空 _LOADED 标志（不影响 os.environ）。"""
    global _LOADED
    _LOADED = False


__all__ = [
    "load_dotenv",
    "is_loaded",
    "reset_for_tests",
    "_KEY_ALIASES",
    "_parse_env_line",
    "_read_env_file",
    "_resolve_canonical_keys",
]
