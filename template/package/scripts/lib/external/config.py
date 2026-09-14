from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from lib.external.dotenv_loader import load_dotenv  # noqa: E402  (side-effect import)
from lib.nn_config import load_nn_config

# D2: 启动 banner 检查的 4 个外部 key
# - SERPER_API_KEY: paper search via Serper(已有 resolve_serper_key / .env 别名 SERPER_KEY)
# - OPENAI_API_KEY / GITHUB_TOKEN / ANTHROPIC_API_KEY: 各自 os.environ 直读,
#   GITHUB_TOKEN 有 .env 别名 GH_TOKEN（dotenv_loader._KEY_ALIASES 自动归一化）
KEY_VARS: tuple[str, ...] = (
    "SERPER_API_KEY",
    "OPENAI_API_KEY",
    "GITHUB_TOKEN",
    "ANTHROPIC_API_KEY",
)

# exploration_mode(6档) → router escalation 词表(4值)；router 仍用 conservative/balanced/inductive/aggressive
_MODE_TO_ESCALATION = {
    "careful": "conservative",
    "optimize": "balanced",
    "innovate": "inductive",
    "aggressive": "aggressive",
    "explore": "balanced",
}


@dataclass
class ExternalEvidenceConfig:
    enabled: bool = True
    max_http_per_reflect: int = 6
    paper_hits_default: int = 3
    paper_hits_deepen: int = 5
    pdf_enabled: bool = True
    serper_key_env: str = "SERPER_API_KEY"
    serper_key_fallback_env: str = "SERPER_KEY"
    exploration: str = "conservative"   # conservative|balanced|inductive|aggressive
    # spec §5:auto 模式下当前生效的档 (paper/docs/github 跟 effective_mode 联动)。
    # T8 之前：兜底 "optimize"。任务 T8 lib/auto_mode.py 接管,这里只是 Io 字段。
    effective_mode: str = "optimize"


def _pick_external(ext: dict, key: str, default):
    """读顶层 external 段字段。"""
    if key in ext and ext[key] is not None:
        return ext[key]
    return default


def load_external_config(repo_root: Path) -> ExternalEvidenceConfig:
    cfg = ExternalEvidenceConfig()
    path = repo_root / "nn-config.yaml"
    if not path.is_file():
        return cfg
    try:
        raw = load_nn_config(repo_root)
        ext = raw.get("external") if isinstance(raw.get("external"), dict) else {}
        cfg.enabled = bool(_pick_external(ext, "enabled", cfg.enabled))
        cfg.max_http_per_reflect = int(
            _pick_external(ext, "max_http_per_reflect", cfg.max_http_per_reflect)
        )
        cfg.paper_hits_default = int(
            _pick_external(ext, "paper_hits_default", cfg.paper_hits_default)
        )
        cfg.paper_hits_deepen = int(
            _pick_external(ext, "paper_hits_deepen", cfg.paper_hits_deepen)
        )
        cfg.pdf_enabled = bool(_pick_external(ext, "pdf_enabled", cfg.pdf_enabled))
        cfg.serper_key_env = str(
            _pick_external(ext, "serper_key_env", cfg.serper_key_env)
        )
        # exploration_mode(6档) → router escalation 词表(4值)；router 仍用 conservative/balanced/inductive/aggressive
        mode = raw.get("exploration_mode")
        if isinstance(mode, str):
            m = mode.strip().lower()
            if m == "auto":
                # auto→effective_mode 解析：权威版在 resolve_exploration（strict）；
                # 此处为 router 宽松派生（无效值→balanced），与 resolve_exploration 行为收敛
                eff = str((raw.get("auto") or {}).get("effective_mode", "optimize")).strip().lower()
                raw_expl = _MODE_TO_ESCALATION.get(eff, "balanced")
            else:
                raw_expl = _MODE_TO_ESCALATION.get(m, "balanced")
        else:
            raw_expl = "balanced"
        cfg.exploration = raw_expl if raw_expl in ("conservative", "balanced", "inductive", "aggressive") else "conservative"
        # spec §5:读取 auto.effective_mode(yaml 写 auto.effective_mode: innovate)——
        # 跟踪"auto 当前升到哪一档"。T8 之前无 effective_mode 字段,这里是空读,不报错。
        auto_sec = raw.get("auto")
        if isinstance(auto_sec, dict):
            raw_eff = auto_sec.get("effective_mode")
            if isinstance(raw_eff, str):
                eff = raw_eff.strip().lower()
                # 6 档白名单;auto 自身不算(effective_mode 应该是跟随档,不能是 auto)
                if eff in ("careful", "optimize", "innovate", "aggressive", "explore"):
                    cfg.effective_mode = eff
    except Exception:
        pass
    return cfg


def resolve_serper_key(repo_root: Path | None = None) -> str | None:
    """读 SERPER key；自动从 ~/.env / 项目 .env 加载并归一化（SERPER_KEY → SERPER_API_KEY）。

    Args:
        repo_root: 业务仓根；提供时也查项目本地 .env
    """
    # 副作用：从 .env 加载（幂等；只 load 一次）
    load_dotenv(repo_root=repo_root)

    k = os.environ.get("SERPER_API_KEY") or os.environ.get("SERPER_KEY")
    return k.strip() if k and k.strip() else None


def check_external_keys(repo_root: Path | None = None) -> dict[str, bool]:
    """D2: 一次性检查 4 个外部 key 是否配齐。

    先按 repo_root load_dotenv（归一化 SERPER_KEY→SERPER_API_KEY / GH_TOKEN→GITHUB_TOKEN），
    再逐个判定存在性。SERPER 走 resolve_serper_key（兼容 .env 别名），
    其余 3 个直读 os.environ.strip()。

    Args:
        repo_root: 业务仓根；None 时只查 ~/.env 与 ~/.env.local（dotenv_loader 默认行为）。

    Returns:
        {key: True/False}；单个 key 解析异常被吞（记 False），不抛。
    """
    result: dict[str, bool] = {}
    load_dotenv(repo_root=repo_root)
    for var in KEY_VARS:
        try:
            if var == "SERPER_API_KEY":
                # resolve_serper_key 内部再做一次 load_dotenv（幂等）
                result[var] = bool(resolve_serper_key(repo_root))
            else:
                # OPENAI_API_KEY / GITHUB_TOKEN / ANTHROPIC_API_KEY 直读；
                # GITHUB_TOKEN 的 GH_TOKEN 别名已由 dotenv_loader 归一化填到 os.environ
                result[var] = bool(os.environ.get(var, "").strip())
        except Exception:
            result[var] = False
    return result
