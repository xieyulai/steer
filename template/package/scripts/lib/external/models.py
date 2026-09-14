from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ToolResult:
    status: str  # ok | skipped | error
    provider: str
    hits: list[dict[str, Any]] = field(default_factory=list)
    excerpt: str | None = None
    # Ticket 01 (#02): PDF 全文确定性抽取的方法段 + 实现要点（喂入层外部证据包字段）。
    method_excerpt: str | None = None
    impl_hints: list[str] = field(default_factory=list)
    local_path: str | None = None  # repo-relative path when file persisted (e.g. PDF)
    skip_reason: str | None = None
    error: str | None = None
    http_calls: int = 0

    @classmethod
    def skipped(cls, provider: str, reason: str) -> ToolResult:
        return cls(status="skipped", provider=provider, skip_reason=reason)

    @classmethod
    def ok(
        cls, provider: str, hits: list[dict[str, Any]], *, http_calls: int = 1
    ) -> ToolResult:
        return cls(status="ok", provider=provider, hits=hits, http_calls=http_calls)


@dataclass
class ExternalPlan:
    schema_version: int
    round_state: dict[str, Any]
    paper_depth: str  # P0–P5
    paper_hits_cap: int
    docs_depth: str  # D0–D3
    github_impl: bool
    github_ecosystem: bool
    budget_max_http: int
    queries: dict[str, str] = field(default_factory=dict)

    def all_off(self) -> bool:
        return (
            self.paper_depth == "P0"
            and self.docs_depth == "D0"
            and not self.github_impl
            and not self.github_ecosystem
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def empty_bundle(
    *, plan: ExternalPlan, reflect_id: str = "", error: str | None = None
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "skipped": [],
        "http_calls_used": 0,
        "budget_max_http": plan.budget_max_http,
    }
    if error:
        meta["error"] = error
    bundle: dict[str, Any] = {
        "schema_version": 1,
        "reflect_id": reflect_id,
        "round_state": plan.round_state,
        "paper": {
            "depth": plan.paper_depth,
            "hits_cap": plan.paper_hits_cap,
            "hits": [],
            "excerpt": None,
            # Ticket 01 (#02): PDF 全文抽取的方法段 + 实现要点（喂入层外部证据包字段）。
            "method_excerpt": None,
            "impl_hints": [],
            "pdf_local_path": None,
            "pdf_arxiv_id": None,
            "impl_candidates": [],
            "linked_code": [],
            # Ticket 05 §11：可执行建议（method→slot→cfg_mapping→骨架）。reflect_hook
            # attach_executable_advice 写入；无方法时保持 None（注入侧据此跳过）。
            "executable_advice": None,
        },
        "code": {
            "routine_attestation": {
                "verdict": "inconclusive",
                "docs": [],
                "github_ecosystem": [],
            }
        },
        "meta": meta,
    }
    # P1-7: 落盘 bundle 须含 plan 全字段（防 reflect.py 落盘 paper_depth=None）。
    # single chokepoint — execute_plan 主路径/dry_run + reflect_hook disabled/except
    # 4 路径全经此函数。用 to_dict() 去 drift（ExternalPlan 加字段自动跟上）。
    bundle["plan"] = plan.to_dict() if hasattr(plan, "to_dict") else {}
    return bundle


@dataclass
class EvidenceBundle:
    data: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return self.data


# MODE_TO_EXTERNAL 5 档 mode → 3 源（paper / docs / github_impl / github_ecosystem）。
# 注意：`auto` 不在表里 — auto 模式下当前生效的档（effective_mode）由 T8 `lib/auto_mode.py`
# 跟踪，effective_mode 一定是 5 显式档之一，所以 `mode_to_external("auto")` 不应该被调用。
# 当前实现兜底返回 optimize 防 KeyError，但 cfg.effective_mode 走 load_external_config
# 的 5 显式档白名单过滤，'auto' 永远不会传入此函数。
MODE_TO_EXTERNAL: dict[str, dict[str, object]] = {
    "careful":    {"paper_depth": "P0", "docs_depth": "D0", "github_impl": False, "github_ecosystem": False},
    "optimize":   {"paper_depth": "P1", "docs_depth": "D1", "github_impl": False, "github_ecosystem": True},
    "innovate":   {"paper_depth": "P2", "docs_depth": "D2", "github_impl": True,  "github_ecosystem": True},
    "aggressive": {"paper_depth": "P3", "docs_depth": "D3", "github_impl": True,  "github_ecosystem": True},
    "explore":    {"paper_depth": "P2", "docs_depth": "D2", "github_impl": True,  "github_ecosystem": True},
}

# auto 起步档(无 effective_mode 时的兜底)
MODE_TO_EXTERNAL_AUTO_DEFAULT: str = "optimize"


def mode_to_external(mode: str) -> dict[str, object]:
    """按 mode 查 3 源配置;未知 mode → optimize 兜底(防 typo 静默走错档)。

    Returns:
        {paper_depth, docs_depth, github_impl, github_ecosystem}
    """
    return MODE_TO_EXTERNAL.get(
        (mode or "").strip().lower(),
        MODE_TO_EXTERNAL[MODE_TO_EXTERNAL_AUTO_DEFAULT],
    )
