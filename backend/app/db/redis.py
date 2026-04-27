from __future__ import annotations

import redis.asyncio as aioredis

from app.config import settings

_client: aioredis.Redis | None = None


async def init_redis() -> None:
    global _client
    _client = aioredis.from_url(settings.redis_url, decode_responses=True)


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_redis() -> aioredis.Redis:
    assert _client is not None, "Redis client not initialised — check lifespan"
    return _client
