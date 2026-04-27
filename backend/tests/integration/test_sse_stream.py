"""Integration tests for the SSE streaming layer.

Tests the full publish → Redis → EventBus → queue pipeline against a real
Redis instance. HTTP-endpoint smoke tests (content-type, heartbeat, curl) are
in labs/smoke_test_phase13.sh because httpx's ASGITransport buffers the entire
response body and cannot drive an infinite SSE generator.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from app.streaming.bus import get_bus
from app.streaming.events import StreamEvent, Topic
from app.streaming.publisher import publish


@pytest.mark.asyncio
async def test_invalid_topic_returns_400(client):
    """400 is returned synchronously before any streaming starts — works with ASGI transport."""
    resp = await client.get("/v1/stream?topics=bogus_topic_xyz")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_publish_delivers_event_to_bus_queue(client):
    """Full pipeline: publish() → Redis pub/sub → EventBus → registered queue."""
    bus = get_bus()
    q = bus.register()
    try:
        await publish("incident.created", {
            "incident_id": "bus-deliver-test",
            "kind": "identity_compromise",
            "severity": "high",
        })
        try:
            raw = await asyncio.wait_for(q.get(), timeout=5.0)
        except asyncio.TimeoutError:
            pytest.fail("EventBus queue did not receive event within 5s")

        event = StreamEvent.model_validate_json(raw)
        assert event.type == "incident.created"
        assert event.topic == Topic.incidents
        assert event.data["incident_id"] == "bus-deliver-test"
        assert event.id  # non-empty sortable ID
        assert event.ts.tzinfo is not None
    finally:
        bus.unregister(q)


@pytest.mark.asyncio
async def test_event_bus_fan_out_to_multiple_queues(client):
    """Publish one event; all registered queues receive it."""
    bus = get_bus()
    q1 = bus.register()
    q2 = bus.register()
    try:
        await publish("detection.fired", {
            "detection_id": "det-fanout-bus",
            "rule_id": "py.test",
            "incident_id": None,
            "severity": "low",
        })
        for q in (q1, q2):
            try:
                raw = await asyncio.wait_for(q.get(), timeout=5.0)
            except asyncio.TimeoutError:
                pytest.fail("Fan-out: queue did not receive event within 5s")
            event = StreamEvent.model_validate_json(raw)
            assert event.data.get("detection_id") == "det-fanout-bus"
    finally:
        bus.unregister(q1)
        bus.unregister(q2)


@pytest.mark.asyncio
async def test_topic_routing_in_events(client):
    """Events carry the correct topic derived from their type."""
    bus = get_bus()
    q = bus.register()
    try:
        await publish("action.executed", {
            "action_id": "act-topic-test",
            "incident_id": "inc-x",
            "kind": "tag_incident",
            "result": "ok",
        })
        try:
            raw = await asyncio.wait_for(q.get(), timeout=5.0)
        except asyncio.TimeoutError:
            pytest.fail("EventBus did not deliver action.executed within 5s")
        event = StreamEvent.model_validate_json(raw)
        assert event.topic == Topic.actions
        assert event.type == "action.executed"
    finally:
        bus.unregister(q)


@pytest.mark.asyncio
async def test_unregistered_queue_misses_subsequent_events(client):
    """A queue unregistered before publish does not receive the event."""
    bus = get_bus()
    q = bus.register()
    bus.unregister(q)

    await publish("evidence.opened", {
        "evidence_request_id": "er-miss-test",
        "incident_id": "inc-y",
        "kind": "process_list",
    })
    await asyncio.sleep(0.3)

    assert q.empty(), "Unregistered queue must not receive events"


@pytest.mark.asyncio
async def test_multiple_event_types_arrive_in_order(client):
    """Sequential publishes arrive in publish order within a single queue."""
    bus = get_bus()
    q = bus.register()
    try:
        await publish("incident.created", {"incident_id": "seq-1", "kind": "k", "severity": "high"})
        await publish("incident.updated", {"incident_id": "seq-1", "change": "extended"})

        events = []
        for _ in range(2):
            try:
                raw = await asyncio.wait_for(q.get(), timeout=5.0)
                events.append(StreamEvent.model_validate_json(raw))
            except asyncio.TimeoutError:
                pytest.fail("EventBus did not deliver both events within 5s")

        assert events[0].type == "incident.created"
        assert events[1].type == "incident.updated"
        # IDs are sortable — later event has lexicographically greater id
        assert events[0].id < events[1].id
    finally:
        bus.unregister(q)
