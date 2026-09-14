"""T9/ADR-9：github 检索从 metadata 扩到抓代码（raw content），P3+ 寻找启用。

AC1：github 检索扩到 raw content（不止 metadata）。
AC2：仅 P3+（aggressive / 寻找 forced-P3）启用，默认关——非 P3+ 行为不变。
AC3：①P3+ 能抓代码喂寻找 ②默认（非 P3+）行为不变。

分两层测：
- fetch_repo_code（github_impl）：raw 代码拉取自身（mock urlopen，不触网）。
- _run_github_code（executor）：P3+ 门控 + 取 top impl_candidate + 写 linked_code。
"""
import io
import json
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.external import github_impl
from lib.external import executor as executor_mod
from lib.external.executor import _run_github_code
from lib.external.models import ExternalPlan, ToolResult


# ── fetch_repo_code：raw 代码拉取（mock urlopen）──────────────────────────────
class _FakeResp:
    """模拟 urlopen 返回的 context manager。"""

    def __init__(self, payload: bytes):
        self._p = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._p


def _make_fake_urlopen(contents_json, raw_texts):
    """contents 路径返回 listing JSON；raw 路径按 path 命中返回文本。"""

    def fake(req, timeout=None):
        url = req.full_url
        if "raw.githubusercontent.com" not in url and url.endswith("/contents"):
            return _FakeResp(json.dumps(contents_json).encode("utf-8"))
        for path, text in raw_texts.items():
            if path in url:
                return _FakeResp(text.encode("utf-8"))
        return _FakeResp(b"")

    return fake


def test_fetch_repo_code_happy_path(monkeypatch):
    """listing + README + 1 个 .py raw → hits 带 content_excerpt，http_calls=3。"""
    contents = [
        {"name": "README.md", "size": 100, "type": "file"},
        {"name": "model.py", "size": 200, "type": "file"},
        {"name": "logo.png", "size": 5000, "type": "file"},
    ]
    raw_texts = {
        "README.md": "# Foo\nimpl notes here",
        "model.py": "import torch\nclass Foo(nn.Module): pass",
    }
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _make_fake_urlopen(contents, raw_texts),
    )
    tr = github_impl.fetch_repo_code("owner/repo", max_files=2)
    assert tr.status == "ok"
    assert tr.provider == "github_code"
    assert tr.http_calls == 3  # 1 listing + 2 raw
    paths = [h["path"] for h in tr.hits]
    assert "README.md" in paths and "model.py" in paths
    assert "logo.png" not in paths  # png 不抓
    readme_hit = next(h for h in tr.hits if h["path"] == "README.md")
    assert readme_hit["repo"] == "owner/repo"
    assert "impl notes" in readme_hit["content_excerpt"]
    assert readme_hit["bytes"] == len("# Foo\nimpl notes here")
    assert readme_hit["url"].startswith("https://raw.githubusercontent.com/owner/repo/")


def test_fetch_repo_code_truncates_long_file(monkeypatch):
    """单文件超 max_bytes_per_file → content_excerpt 截断（bytes 仍记原始长度）。"""
    contents = [{"name": "README.md", "size": 10, "type": "file"}]
    long_text = "x" * 200
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _make_fake_urlopen(contents, {"README.md": long_text}),
    )
    tr = github_impl.fetch_repo_code("o/r", max_files=1, max_bytes_per_file=50)
    assert tr.status == "ok"
    assert len(tr.hits[0]["content_excerpt"]) == 50
    assert tr.hits[0]["bytes"] == 200


def test_fetch_repo_code_empty_repo_skips(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _make_fake_urlopen([], {}),
    )
    tr = github_impl.fetch_repo_code("owner/repo")
    assert tr.status == "skipped"
    assert tr.hits == []


def test_fetch_repo_code_404_skips(monkeypatch):
    def boom(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 404, "Not Found", {}, io.BytesIO(b"{}")
        )

    monkeypatch.setattr("urllib.request.urlopen", boom)
    tr = github_impl.fetch_repo_code("owner/missing")
    assert tr.status == "skipped"  # 404 → repo_not_found，非 error


def test_fetch_repo_code_network_skips(monkeypatch):
    def boom(req, timeout=None):
        raise OSError("network down")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    tr = github_impl.fetch_repo_code("owner/repo")
    assert tr.status == "skipped"


def test_fetch_repo_code_invalid_repo_skips():
    assert github_impl.fetch_repo_code("").status == "skipped"
    assert github_impl.fetch_repo_code("no-slash").status == "skipped"


def test_fetch_repo_code_no_source_files_skips(monkeypatch):
    """顶层只有 png（无 README / .py）→ no_source_files。"""
    contents = [{"name": "logo.png", "size": 100, "type": "file"}]
    monkeypatch.setattr(
        "urllib.request.urlopen", _make_fake_urlopen(contents, {})
    )
    tr = github_impl.fetch_repo_code("owner/repo")
    assert tr.status == "skipped"


# ── _run_github_code：P3+ 门控 + 取 top impl_candidate + 写 linked_code ────────
def _make_plan(*, paper_depth="P3", github_impl_flag=True, budget=10) -> ExternalPlan:
    return ExternalPlan(
        schema_version=1,
        round_state={"round": 1},
        paper_depth=paper_depth,
        paper_hits_cap=5,
        docs_depth="D2",
        github_impl=github_impl_flag,
        github_ecosystem=True,
        budget_max_http=budget,
        queries={},
    )


def _ok_code(*args, **kwargs):
    """fetch_repo_code 替身：返回 1 条 hit。"""
    from lib.external.models import ToolResult

    return ToolResult.ok(
        "github_code",
        [{"repo": "owner/repo", "path": "README.md",
          "url": "u", "content_excerpt": "notes", "bytes": 5}],
        http_calls=3,
    )


def test_run_github_code_p3_populates_linked_code(monkeypatch):
    """AC3①：P3 + 有 top impl_candidate → 抓代码喂 linked_code。"""
    monkeypatch.setattr(executor_mod, "fetch_repo_code", _ok_code)
    plan = _make_plan(paper_depth="P3")
    bundle = {"paper": {"impl_candidates": [{"full_name": "owner/repo"}]}}
    linked, http_used = _run_github_code(plan, bundle, http_used=0, skipped=[])
    assert len(linked) == 1
    assert linked[0]["path"] == "README.md"
    assert http_used == 3


def test_run_github_code_p2_no_fetch_default_off(monkeypatch):
    """AC3②：非 P3+（P2 innovate）→ 不抓代码，linked_code 留空，行为不变。"""
    called = {"n": 0}

    def sentinel(*a, **k):
        called["n"] += 1
        return _ok_code()

    monkeypatch.setattr(executor_mod, "fetch_repo_code", sentinel)
    plan = _make_plan(paper_depth="P2")
    bundle = {"paper": {"impl_candidates": [{"full_name": "owner/repo"}]}}
    linked, http_used = _run_github_code(plan, bundle, http_used=0, skipped=[])
    assert linked == []
    assert http_used == 0
    assert called["n"] == 0  # P3 门控短路，fetch_repo_code 根本没被调


def test_run_github_code_p3_no_candidates_no_fetch(monkeypatch):
    """P3 但无 impl_candidate（没 repo 可抓）→ 不抓，linked_code 空。"""
    called = {"n": 0}

    def sentinel(*a, **k):
        called["n"] += 1
        return _ok_code()

    monkeypatch.setattr(executor_mod, "fetch_repo_code", sentinel)
    plan = _make_plan(paper_depth="P3")
    bundle = {"paper": {"impl_candidates": []}}
    linked, http_used = _run_github_code(plan, bundle, http_used=0, skipped=[])
    assert linked == []
    assert called["n"] == 0


def test_run_github_code_p3_budget_exceeded_skips(monkeypatch):
    """P3 + 有 candidate 但预算耗尽 → skipped，不抓。"""
    called = {"n": 0}

    def sentinel(*a, **k):
        called["n"] += 1
        return _ok_code()

    monkeypatch.setattr(executor_mod, "fetch_repo_code", sentinel)
    plan = _make_plan(paper_depth="P3", budget=2)
    bundle = {"paper": {"impl_candidates": [{"full_name": "owner/repo"}]}}
    skipped: list[dict[str, str]] = []
    linked, http_used = _run_github_code(
        plan, bundle, http_used=2, skipped=skipped
    )
    assert linked == []
    assert called["n"] == 0
    assert any(s["provider"] == "github_code" for s in skipped)


def test_execute_plan_p3_populates_linked_code(monkeypatch):
    """端到端：execute_plan P3 + github_impl → 写 bundle['paper']['linked_code']。

    mock 论文源（返回 1 条无 arxiv_id 的 hit → 不触 PDF 下载）+ search_repos（返回
    top repo）+ fetch_repo_code（返回代码片段）。验证 _run_github_code 被接线进
    execute_plan，linked_code 落进 bundle（喂寻找反馈边的入口）。
    """
    monkeypatch.setattr(executor_mod, "fetch_repo_code", _ok_code)
    monkeypatch.setattr(
        executor_mod, "search_repos",
        lambda q, **k: ToolResult.ok(
            "github_impl",
            [{"full_name": "owner/repo", "url": "u", "stars": 1, "description": "d"}],
        ),
    )
    monkeypatch.setattr(
        executor_mod, "search_arxiv",
        lambda q, **k: [{"title": "FooNet", "url": "u", "abstract": "a"}],
    )
    monkeypatch.setattr(executor_mod, "search_openalex", lambda q, **k: [])
    plan = _make_plan(paper_depth="P3", github_impl_flag=True, budget=10)
    plan.queries = {"paper": "attention network"}
    bundle = executor_mod.execute_plan(plan, dry_run=False, has_serper=False)
    assert bundle["paper"]["impl_candidates"][0]["full_name"] == "owner/repo"
    assert len(bundle["paper"]["linked_code"]) == 1
    assert bundle["paper"]["linked_code"][0]["path"] == "README.md"


def test_execute_plan_p2_leaves_linked_code_empty(monkeypatch):
    """AC3② 端到端：非 P3+（P2）→ linked_code 留空，行为不变。"""
    called = {"n": 0}

    def sentinel(*a, **k):
        called["n"] += 1
        return _ok_code()

    monkeypatch.setattr(executor_mod, "fetch_repo_code", sentinel)
    monkeypatch.setattr(
        executor_mod, "search_repos",
        lambda q, **k: ToolResult.ok(
            "github_impl",
            [{"full_name": "owner/repo", "url": "u", "stars": 1, "description": "d"}],
        ),
    )
    monkeypatch.setattr(
        executor_mod, "search_arxiv",
        lambda q, **k: [{"title": "FooNet", "url": "u", "abstract": "a"}],
    )
    monkeypatch.setattr(executor_mod, "search_openalex", lambda q, **k: [])
    plan = _make_plan(paper_depth="P2", github_impl_flag=True, budget=10)
    plan.queries = {"paper": "attention network"}
    bundle = executor_mod.execute_plan(plan, dry_run=False, has_serper=False)
    # P2 仍走 search_repos（impl_candidates 有），但 fetch_repo_code 不被调 → linked_code 空
    assert bundle["paper"]["impl_candidates"][0]["full_name"] == "owner/repo"
    assert bundle["paper"]["linked_code"] == []
    assert called["n"] == 0
