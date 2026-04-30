from __future__ import annotations

import redis.asyncio as aioredis

from app.config import settings
from app.db.redis_state import RedisUnavailable

_client: aioredis.Redis | None = None


async def init_redis() -> None:
    global _client
    # Phase 19 A1.1: bound socket-level waits so a dead Redis (DNS NXDOMAIN,
    # killed container, network partition) cannot stall the ingest path. The
    # read timeout is sized at 2s — comfortably above any healthy command
    # round-trip but tight enough that an outage surfaces quickly. The outer
    # `safe_redis` further bounds each op via asyncio.wait_for and trips a
    # short-lived circuit breaker on the first failure.
    _client = aioredis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=0.5,
        socket_timeout=2.0,
        retry_on_timeout=False,
    )


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_redis() -> aioredis.Redis:
    if _client is None:
        raise RedisUnavailable("Redis client not initialised — check lifespan")
    return _client
