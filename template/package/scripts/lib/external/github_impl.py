"""GitHub repository search for paper implementation candidates."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from lib.external.models import ToolResult

GITHUB_SEARCH_API = "https://api.github.com/search/repositories"
_GITHUB_CONTENTS_API = "https://api.github.com/repos/{repo}/contents"
_RAW_BASE = "https://raw.githubusercontent.com/{repo}/HEAD/{path}"
_USER_AGENT = "auto-nn-literature/1.0"


def _github_token() -> str:
    return (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()


def _repo_to_hit(item: dict[str, Any]) -> dict[str, Any] | None:
    full_name = str(item.get("full_name") or "").strip()
    if not full_name:
        return None
    url = str(item.get("html_url") or f"https://github.com/{full_name}").strip()
    description = str(item.get("description") or "").strip()
    stars = item.get("stargazers_count")
    try:
        stars_int = int(stars) if stars is not None else 0
    except (TypeError, ValueError):
        stars_int = 0
    return {
        "full_name": full_name,
        "url": url,
        "stars": stars_int,
        "description": description,
    }


def search_repos(
    query: str,
    *,
    max_results: int = 3,
    timeout_sec: float = 30.0,
) -> ToolResult:
    """GET GitHub /search/repositories; GITHUB_TOKEN optional."""
    q = " ".join(str(query or "").split()).strip()
    if not q:
        return ToolResult.skipped("github_impl", "empty_query")

    per_page = max(1, min(int(max_results), 10))
    params = {
        "q": q,
        "sort": "stars",
        "order": "desc",
        "per_page": str(per_page),
    }
    url = f"{GITHUB_SEARCH_API}?{urllib.parse.urlencode(params)}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": _USER_AGENT,
    }
    token = _github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            return ToolResult.skipped("github_impl", "rate_limit")
        return ToolResult(
            status="error",
            provider="github_impl",
            error=f"HTTP {exc.code}",
            http_calls=1,
        )
    except OSError as exc:
        return ToolResult.skipped("github_impl", f"no_network: {exc}")

    items = data.get("items") if isinstance(data, dict) else None
    hits: list[dict[str, Any]] = []
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            hit = _repo_to_hit(item)
            if hit:
                hits.append(hit)
    return ToolResult.ok("github_impl", hits[:per_page], http_calls=1)


def _fetch_raw(path: str, repo: str, *, timeout_sec: float) -> str | None:
    """raw.githubusercontent.com 单文件拉取；失败返回 None（非致命，由调用方跳过）。"""
    url = _RAW_BASE.format(repo=repo, path=urllib.parse.quote(path, safe="/"))
    headers = {"User-Agent": _USER_AGENT}
    token = _github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.HTTPError, OSError):
        return None


def fetch_repo_code(
    repo_full_name: str,
    *,
    max_files: int = 2,
    max_bytes_per_file: int = 4000,
    timeout_sec: float = 30.0,
) -> ToolResult:
    """T9/ADR-9：拉 repo 的 README + 少量源码片段（raw content），喂寻找反馈边。

    github 检索从 metadata 扩到实际代码：列顶层 contents（1 call）→ 选 README + 少量
    *.py（按 max_files 配额）→ raw 拉取（每文件 1 call）→ 截断成 content_excerpt。
    纯 urllib、非致命、token 可选。git clone --depth 1 / code-search 为备选机制
    （本实现取 raw：无 git 二进制依赖、可单测、与 search_repos 同 urllib 风格）。
    返回 hits=[{repo, path, url, content_excerpt, bytes}]。空仓库/404/断网 → skipped。
    """
    repo = " ".join(str(repo_full_name or "").split()).strip()
    if not repo or "/" not in repo:
        return ToolResult.skipped("github_code", "invalid_repo")

    # 1) 列顶层 contents
    list_url = _GITHUB_CONTENTS_API.format(repo=repo)
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": _USER_AGENT,
    }
    token = _github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(list_url, headers=headers)
    http_calls = 1
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            items = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            return ToolResult.skipped("github_code", "rate_limit")
        if exc.code == 404:
            return ToolResult.skipped("github_code", "repo_not_found")
        return ToolResult(
            status="error", provider="github_code", error=f"HTTP {exc.code}", http_calls=1,
        )
    except OSError as exc:
        return ToolResult.skipped("github_code", f"no_network: {exc}")

    if not isinstance(items, list) or not items:
        return ToolResult.skipped("github_code", "empty_repo")

    # 2) 选 README + 少量 *.py（跳过大文件，按 listing 的 size 预判）
    size_cap = max_bytes_per_file * 4
    readme = ""
    py_files: list[str] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name") or "").strip()
        if not name:
            continue
        size = it.get("size")
        try:
            size_int = int(size) if size is not None else 0
        except (TypeError, ValueError):
            size_int = 0
        if size_int > size_cap:
            continue
        low = name.lower()
        if not readme and (low == "readme" or low.startswith("readme.")):
            readme = name
        elif name.endswith(".py"):
            py_files.append(name)
    py_cap = max(0, max_files - (1 if readme else 0))
    targets = ([readme] if readme else []) + py_files[:py_cap]
    if not targets:
        return ToolResult.skipped("github_code", "no_source_files")

    # 3) raw 拉取 + 截断
    hits: list[dict[str, Any]] = []
    for path in targets:
        text = _fetch_raw(path, repo, timeout_sec=timeout_sec)
        http_calls += 1
        if text is None:
            continue
        hits.append({
            "repo": repo,
            "path": path,
            "url": _RAW_BASE.format(repo=repo, path=urllib.parse.quote(path, safe="/")),
            "content_excerpt": text[:max_bytes_per_file],
            "bytes": len(text),
        })
    if not hits:
        return ToolResult.skipped("github_code", "all_files_unreachable")
    return ToolResult.ok("github_code", hits, http_calls=http_calls)
