from __future__ import annotations

import asyncio
import logging

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_CHANNEL_PATTERN = "cybercat:stream:*"
# Phase 19: gap between supervisor reconnect attempts. Short enough that
# streaming recovers within a few seconds of a Redis blip; long enough that
# we don't hammer Redis during a sustained outage.
_RECONNECT_BACKOFF_SEC = 2.0

_bus: EventBus | None = None


class EventBus:
    """One shared Redis subscriber per process; fans out to per-connection asyncio.Queues.

    Phase 19: a supervisor wraps the pub/sub listen loop so a Redis disconnect
    no longer silently kills streaming. On exception the supervisor closes the
    pub/sub handle, sleeps briefly, re-subscribes, and resumes. SSE consumers
    that registered queues stay registered across reconnects — they just see
    no events during the outage.
    """

    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[str]] = set()
        self._client: aioredis.Redis | None = None
        self._pubsub: aioredis.client.PubSub | None = None
        self._supervisor_task: asyncio.Task[None] | None = None
        self._stopping = False

    async def start(self) -> None:
        # Phase 19 A1.1: bound the connect-side socket wait so a Redis outage
        # does not produce ~5s DNS-driven hangs on every reconnect attempt.
        # We deliberately do NOT set socket_timeout — pubsub.listen() blocks
        # indefinitely waiting for messages and a small read timeout would
        # turn every idle period into a "consumer crashed → reconnect" cycle.
        self._client = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=0.5,
            retry_on_timeout=False,
        )
        await self._open_pubsub()
        self._supervisor_task = asyncio.create_task(self._supervisor())
        logger.info("EventBus started, subscribed to %s", _CHANNEL_PATTERN)

    async def stop(self) -> None:
        self._stopping = True
        if self._supervisor_task is not None:
            self._supervisor_task.cancel()
            try:
                await self._supervisor_task
            except asyncio.CancelledError:
                pass
        await self._close_pubsub_quietly()
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

    # ------------------------------------------------------------------
    # Internal: pub/sub lifecycle
    # ------------------------------------------------------------------

    async def _open_pubsub(self) -> None:
        assert self._client is not None
        self._pubsub = self._client.pubsub()
        await self._pubsub.psubscribe(_CHANNEL_PATTERN)

    async def _close_pubsub_quietly(self) -> None:
        if self._pubsub is None:
            return
        try:
            await self._pubsub.aclose()
        except Exception as exc:
            logger.debug("EventBus pubsub close raised %s — ignoring", exc)
        self._pubsub = None

    async def _supervisor(self) -> None:
        """Run `_consume_once` in a loop; on crash, reconnect with backoff."""
        while not self._stopping:
            try:
                await self._consume_once()
            except asyncio.CancelledError:
                return
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "EventBus consumer crashed: %s — reconnecting in %.0fs",
                    exc, _RECONNECT_BACKOFF_SEC,
                )
                await self._close_pubsub_quietly()
                try:
                    await asyncio.sleep(_RECONNECT_BACKOFF_SEC)
                    if self._stopping:
                        return
                    await self._open_pubsub()
                    logger.info("EventBus consumer reconnected")
                except asyncio.CancelledError:
                    return
                except Exception as reconnect_exc:  # noqa: BLE001
                    logger.error(
                        "EventBus reconnect failed: %s — will retry", reconnect_exc,
                    )
                    # Loop back; next iteration tries again.
                    continue

    async def _consume_once(self) -> None:
        """Single-pass listen loop. Returns when listen() yields no more messages
        or raises. The supervisor decides whether to restart."""
        assert self._pubsub is not None
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
