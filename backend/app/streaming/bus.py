from __future__ import annotations

import asyncio
import logging

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_CHANNEL_PATTERN = "cybercat:stream:*"

_bus: "EventBus | None" = None


class EventBus:
    """One shared Redis subscriber per process; fans out to per-connection asyncio.Queues."""

    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[str]] = set()
        self._client: aioredis.Redis | None = None
        self._pubsub: aioredis.client.PubSub | None = None
        self._consumer_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._client = aioredis.from_url(settings.redis_url, decode_responses=True)
        self._pubsub = self._client.pubsub()
        await self._pubsub.psubscribe(_CHANNEL_PATTERN)
        self._consumer_task = asyncio.create_task(self._consume())
        logger.info("EventBus started, subscribed to %s", _CHANNEL_PATTERN)

    async def stop(self) -> None:
        if self._consumer_task is not None:
            self._consumer_task.cancel()
            try:
                await self._consumer_task
            except asyncio.CancelledError:
                pass
        if self._pubsub is not None:
            await self._pubsub.aclose()
        if self._client is not None:
            await self._client.aclose()
        logger.info("EventBus stopped")

    def register(self) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=256)
        self._queues.add(q)
        return q

    def unregister(self, q: asyncio.Queue[str]) -> None:
        self._queues.discard(q)

    @property
    def queue_count(self) -> int:
        return len(self._queues)

    async def _consume(self) -> None:
        assert self._pubsub is not None
        try:
            async for message in self._pubsub.listen():
                if message["type"] != "pmessage":
                    continue
                data: str = message["data"]
                dead: set[asyncio.Queue[str]] = set()
                for q in self._queues:
                    try:
                        q.put_nowait(data)
                    except asyncio.QueueFull:
                        dead.add(q)
                for q in dead:
                    self._queues.discard(q)
                    logger.warning("EventBus: dropped slow SSE client (queue full)")
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("EventBus consumer crashed: %s", exc)


async def init_bus() -> EventBus:
    global _bus
    _bus = EventBus()
    await _bus.start()
    return _bus


async def close_bus() -> None:
    global _bus
    if _bus is not None:
        await _bus.stop()
        _bus = None


def get_bus() -> EventBus:
    assert _bus is not None, "EventBus not initialized — check lifespan"
    return _bus
