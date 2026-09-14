"""轻量 HTTP retry 工具（paper search 各 provider 共用）。

设计：
- max_retries=2 → 最多 3 次调用（1 + 2 重试）
- 默认 backoff: 1.0s, 2.0s, 4.0s（exponential 2x）
- 可重试异常：HTTPError(code in 429/5xx)、URLError、TimeoutError、OSError
- 不重试 ValueError / KeyError 等参数错（不重试）
- 不重试 401/403 / 其他 4xx（认证/客户端错，重试无用）

使用：
    from lib.external.retry import with_retry
    return with_retry(lambda: search_scholar(q), max_retries=2)
"""
from __future__ import annotations

import time
import urllib.error
from typing import Callable, TypeVar

T = TypeVar("T")

DEFAULT_BACKOFF_BASE = 1.0
DEFAULT_BACKOFF_FACTOR = 2.0
DEFAULT_MAX_RETRIES = 2


def is_retryable(exc: BaseException) -> bool:
    """判断异常是否可重试（429/5xx/网络/timeout）。"""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code == 429 or exc.code >= 500
    if isinstance(exc, (urllib.error.URLError, TimeoutError, OSError)):
        return True
    return False


def backoff_delay(
    attempt: int,
    *,
    base: float = DEFAULT_BACKOFF_BASE,
    factor: float = DEFAULT_BACKOFF_FACTOR,
) -> float:
    """attempt=0 → base；attempt=1 → base*factor；..."""
    return base * (factor ** attempt)


def with_retry(
    fn: Callable[[], T],
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base: float = DEFAULT_BACKOFF_BASE,
    factor: float = DEFAULT_BACKOFF_FACTOR,
    on_retry: Callable[[int, BaseException], None] | None = None,
) -> T:
    """调用 fn；可重试异常时按指数 backoff 重试；不可重试或重试耗尽则 raise。

    Args:
        fn: 0-arg callable（不传参；要参数请用 lambda / functools.partial 闭包）
        max_retries: 失败后重试次数（不含首次）= 共 1+max_retries 次调用
        base: 首次 backoff 秒数
        factor: 每次乘数
        on_retry: 每次重试前调 (attempt_idx_1_based, exc)；用于 logging
    """
    for attempt in range(max_retries + 1):
        try:
            return fn()
        except BaseException as exc:
            if not is_retryable(exc):
                raise
            if attempt >= max_retries:
                raise
            if on_retry is not None:
                try:
                    on_retry(attempt + 1, exc)
                except Exception:  # noqa: BLE001
                    # on_retry 自身出错不应影响主流程
                    pass
            time.sleep(backoff_delay(attempt, base=base, factor=factor))
    # unreachable，但 type-checker 友好
    raise RuntimeError("with_retry: unreachable")


__all__ = [
    "DEFAULT_BACKOFF_BASE",
    "DEFAULT_BACKOFF_FACTOR",
    "DEFAULT_MAX_RETRIES",
    "is_retryable",
    "backoff_delay",
    "with_retry",
]
