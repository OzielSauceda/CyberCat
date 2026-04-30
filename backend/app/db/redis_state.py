"""Redis availability handling for graceful detector degradation (Phase 19).

Detectors call Redis for windowing, dedup, and caches. If Redis is unreachable the
old behavior was to crash the ingest pipeline (`get_redis()` `assert`-ed and any
network failure raised `redis.ConnectionError`). After Phase 19 the ingest path
must survive Redis being down: events still land in Postgres, detectors that
depend on Redis state degrade safely (skip or fall back to a DB query), and a
single warning is emitted per (rule, op) per minute so the outage is observable
without log spam.

Use `safe_redis(awaitable, rule_id=..., op_name=..., default=...)` at every Redis
call site in the detector layer.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable
from typing import TypeVar

from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

T = TypeVar("T")

_LOG_THROTTLE_SEC = 60.0
# Per-op timeout. Sized to accommodate the slowest legitimate Redis call
# under pytest load (~hundreds of ms) while still bounding a stuck DNS
# lookup or dead socket. Anything below ~2s caused false positives during
# the integration suite where SETNX dedup checks occasionally exceed 500ms.
_OP_TIMEOUT_SEC = 3.0
# Circuit breaker: when Redis fails, open the breaker briefly so subsequent calls
# return their default without re-attempting the doomed DNS/TCP lookup. The
# breaker auto-closes after _BREAKER_OPEN_SEC and Redis is probed again. Without
# this, every detector call on every request burns its full timeout while Redis
# is down — for a multi-detector pipeline that quickly exhausts the httpx
# client timeout on the simulator/agent side.
_BREAKER_OPEN_SEC = 5.0
_last_logged: dict[tuple[str, str], float] = {}
_breaker_open_until: float = 0.0


class RedisUnavailable(RuntimeError):
    """Raised by `get_redis()` when the client has not been initialised.

    Treated identically to `redis.RedisError` by `safe_redis` — the caller falls
    back to its supplied default value.
    """


def _maybe_log(rule_id: str, op_name: str, exc: BaseException) -> None:
    key = (rule_id, op_name)
    now = time.monotonic()
    last = _last_logged.get(key, 0.0)
    if now - last < _LOG_THROTTLE_SEC:
        return
    _last_logged[key] = now
    logger.warning(
        "redis_degraded rule=%s op=%s err=%s — using fallback",
        rule_id,
        op_name,
        exc.__class__.__name__,
    )


def reset_throttle() -> None:
    """Test helper: clear the per-(rule, op) log-throttle map and circuit breaker."""
    global _breaker_open_until
    _last_logged.clear()
    _breaker_open_until = 0.0


async def safe_redis(
    awaitable: Awaitable[T],
    *,
    rule_id: str,
    op_name: str,
    default: T,
) -> T:
    """Await a Redis coroutine; on RedisError, RedisUnavailable, or timeout, log+return default.

    Pass an unstarted coroutine (e.g. `redis.incr(key)`) — it is awaited inside.
    The op is bounded by `_OP_TIMEOUT_SEC` so a hanging DNS lookup or stuck socket
    cannot stall the ingest path beyond a known ceiling. After a failure the
    breaker opens for `_BREAKER_OPEN_SEC` so concurrent calls during the outage
    return immediately instead of each burning their own timeout.
    """
    global _breaker_open_until
    now = time.monotonic()
    if now < _breaker_open_until:
        # Breaker is open — close the unstarted coroutine to avoid "coroutine
        # was never awaited" warnings, then return the default.
        if hasattr(awaitable, "close"):
            awaitable.close()  # type: ignore[union-attr]
        return default
    try:
        return await asyncio.wait_for(awaitable, timeout=_OP_TIMEOUT_SEC)
    except (RedisError, RedisUnavailable, TimeoutError) as exc:
        _breaker_open_until = time.monotonic() + _BREAKER_OPEN_SEC
        _maybe_log(rule_id, op_name, exc)
        return default
