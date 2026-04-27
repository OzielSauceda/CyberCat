"""Unit tests for the EventBus."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.streaming.bus import EventBus


def _make_pmessage(data: str) -> dict:
    return {"type": "pmessage", "pattern": "cybercat:stream:*", "channel": "cybercat:stream:incidents", "data": data}


@pytest.mark.asyncio
async def test_register_returns_fresh_queue():
    bus = EventBus()
    q1 = bus.register()
    q2 = bus.register()
    assert q1 is not q2
    assert bus.queue_count == 2
    bus.unregister(q1)
    bus.unregister(q2)


@pytest.mark.asyncio
async def test_unregister_removes_queue():
    bus = EventBus()
    q = bus.register()
    assert bus.queue_count == 1
    bus.unregister(q)
    assert bus.queue_count == 0


@pytest.mark.asyncio
async def test_consumer_forwards_pmessage_to_all_queues():
    """Simulate _consume receiving a message and fan-out to registered queues."""
    bus = EventBus()
    q1 = bus.register()
    q2 = bus.register()

    payload = json.dumps({"type": "incident.created", "topic": "incidents", "id": "x", "ts": "2026-01-01T00:00:00Z", "data": {}})
    message = _make_pmessage(payload)

    # Drive _consume with a single message then cancel
    async def fake_listen():
        yield message
        await asyncio.sleep(999)  # stall so we can cancel

    fake_pubsub = AsyncMock()
    fake_pubsub.listen = fake_listen
    bus._pubsub = fake_pubsub

    task = asyncio.create_task(bus._consume())
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert not q1.empty()
    assert not q2.empty()
    assert q1.get_nowait() == payload
    assert q2.get_nowait() == payload

    bus.unregister(q1)
    bus.unregister(q2)


@pytest.mark.asyncio
async def test_unregister_stops_delivery():
    bus = EventBus()
    q = bus.register()
    bus.unregister(q)

    payload = "some-event"
    message = _make_pmessage(payload)

    async def fake_listen():
        yield message
        await asyncio.sleep(999)

    fake_pubsub = AsyncMock()
    fake_pubsub.listen = fake_listen
    bus._pubsub = fake_pubsub

    task = asyncio.create_task(bus._consume())
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert q.empty()
