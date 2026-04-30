"""Phase 19 — EventBus supervisor reconnect + queue-cleanup tests.

Asserts:
- A crash in `_consume_once` does NOT kill the supervisor; it reconnects.
- Stop signals (`_stopping=True`) cancel the supervisor cleanly without spinning.
- Queue registration / unregistration is symmetric — registering N then
  unregistering N times leaves the bus with zero queues.
- Slow client (full queue) gets dropped; fast clients stay registered.

Tests use mocked pubsub objects so we don't need a real Redis or to actually
hold a TCP connection open.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.streaming.bus import EventBus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakePubSub:
    """A pubsub stand-in whose `listen()` is fed from a controllable queue."""

    def __init__(self):
        self.in_q: asyncio.Queue = asyncio.Queue()
        self.psubscribed: list[str] = []
        self.closed = False

    async def psubscribe(self, pattern: str) -> None:
        self.psubscribed.append(pattern)

    async def aclose(self) -> None:
        self.closed = True
        # signal end-of-stream to any active listen() loop
        await self.in_q.put({"_end": True})

    async def listen(self):
        while True:
            msg = await self.in_q.get()
            if msg.get("_end"):
                return
            if msg.get("_raise"):
                raise msg["_raise"]
            yield msg


class _FakeRedisClient:
    def __init__(self):
        self.pubsubs: list[_FakePubSub] = []
        self.closed = False

    def pubsub(self) -> _FakePubSub:
        ps = _FakePubSub()
        self.pubsubs.append(ps)
        return ps

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def fake_redis_client():
    return _FakeRedisClient()


@pytest.fixture
async def bus(fake_redis_client):
    """A started EventBus wired to fakes; auto-stopped after the test."""
    with patch("app.streaming.bus.aioredis.from_url", return_value=fake_redis_client):
        b = EventBus()
        # Shorten reconnect backoff so tests don't sleep needlessly.
        with patch("app.streaming.bus._RECONNECT_BACKOFF_SEC", 0.05):
            await b.start()
            yield b
            await b.stop()


# ---------------------------------------------------------------------------
# Queue registration symmetry
# ---------------------------------------------------------------------------

class TestQueueRegistration:
    async def test_register_unregister_symmetric(self, bus):
        assert bus.queue_count == 0
        queues = [bus.register() for _ in range(50)]
        assert bus.queue_count == 50
        for q in queues:
            bus.unregister(q)
        assert bus.queue_count == 0

    async def test_unregister_idempotent(self, bus):
        q = bus.register()
        bus.unregister(q)
        bus.unregister(q)  # must not raise
        assert bus.queue_count == 0


# ---------------------------------------------------------------------------
# Supervisor reconnect
# ---------------------------------------------------------------------------

class TestSupervisorReconnect:
    async def test_supervisor_reconnects_after_consumer_crash(
        self, bus, fake_redis_client
    ):
        # First pubsub is the one start() opened
        first = fake_redis_client.pubsubs[0]

        # Inject a crash into the active consumer
        await first.in_q.put({"_raise": RuntimeError("simulated pubsub disconnect")})

        # Wait until the supervisor opens a SECOND pubsub (proves reconnect).
        for _ in range(40):  # up to ~2s
            if len(fake_redis_client.pubsubs) >= 2:
                break
            await asyncio.sleep(0.05)
        assert len(fake_redis_client.pubsubs) >= 2, "supervisor did not reconnect"

        # The new pubsub is psubscribed to the same pattern
        second = fake_redis_client.pubsubs[-1]
        assert "cybercat:stream:*" in second.psubscribed

        # Old pubsub was closed during reconnect cleanup
        assert first.closed is True

    async def test_supervisor_keeps_running_across_multiple_crashes(
        self, bus, fake_redis_client
    ):
        for _ in range(3):
            active = fake_redis_client.pubsubs[-1]
            await active.in_q.put({"_raise": RuntimeError("flap")})
            for _ in range(40):
                if fake_redis_client.pubsubs[-1] is not active:
                    break
                await asyncio.sleep(0.05)
            else:
                pytest.fail("supervisor failed to reconnect on one of the iterations")
        # Three crashes → at least four pubsub instances total (start + 3 reconnects)
        assert len(fake_redis_client.pubsubs) >= 4


# ---------------------------------------------------------------------------
# Slow-client backpressure
# ---------------------------------------------------------------------------

class TestSlowClientDrop:
    async def test_full_queue_consumer_dropped(self, bus, fake_redis_client):
        # Register a queue and fill it past capacity.
        q = bus.register()
        for _ in range(256):
            q.put_nowait("preload")

        # Send one more event — the active consumer should detect the full queue
        # and discard it from the bus.
        active = fake_redis_client.pubsubs[-1]
        await active.in_q.put({"type": "pmessage", "data": "{}"})

        # Wait for the consumer task to process and drop the queue
        for _ in range(40):
            if bus.queue_count == 0:
                break
            await asyncio.sleep(0.05)
        assert bus.queue_count == 0, "slow client should have been dropped"


# ---------------------------------------------------------------------------
# Stop is clean
# ---------------------------------------------------------------------------

class TestStop:
    async def test_stop_does_not_hang(self, fake_redis_client):
        with patch("app.streaming.bus.aioredis.from_url", return_value=fake_redis_client), \
             patch("app.streaming.bus._RECONNECT_BACKOFF_SEC", 0.05):
            b = EventBus()
            await b.start()
            # Stop should complete quickly even if listen() is mid-await.
            await asyncio.wait_for(b.stop(), timeout=2.0)
            assert fake_redis_client.closed is True
