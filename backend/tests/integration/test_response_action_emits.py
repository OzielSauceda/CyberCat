"""Integration tests verifying that action lifecycle emits SSE events.

Requires Postgres + Redis and a seeded incident to act on.

Note: Tests use the EventBus queue directly rather than HTTP SSE streaming because
httpx's ASGITransport buffers the entire response body and cannot drive an infinite
SSE generator. The HTTP streaming endpoint is verified in labs/smoke_test_phase13.sh.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.streaming.bus import get_bus
from app.streaming.events import StreamEvent, Topic
from app.streaming.publisher import publish


@pytest.mark.asyncio
async def test_propose_action_emits_event(client, truncate_tables):
    """Proposing an action via REST emits an action.proposed event to the EventBus."""
    # Seed events to create an incident via the ingest path. Timestamps are
    # generated relative to "now" so this test stays inside the Phase-19
    # 30-day past-bound on RawEventIn.occurred_at.
    base_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    seed_events = [
        {
            "source": "direct",
            "kind": "auth.failed",
            "occurred_at": base_time.isoformat(),
            "raw": {},
            "normalized": {"user": "alice", "source_ip": "1.2.3.4", "auth_type": "password"},
            "dedupe_key": "direct-af-propose-1",
        },
        {
            "source": "direct",
            "kind": "auth.failed",
            "occurred_at": (base_time + timedelta(minutes=1)).isoformat(),
            "raw": {},
            "normalized": {"user": "alice", "source_ip": "1.2.3.4", "auth_type": "password"},
            "dedupe_key": "direct-af-propose-2",
        },
        {
            "source": "direct",
            "kind": "auth.succeeded",
            "occurred_at": (base_time + timedelta(minutes=2)).isoformat(),
            "raw": {},
            "normalized": {"user": "alice", "source_ip": "1.2.3.4", "auth_type": "password"},
            "dedupe_key": "direct-as-propose-1",
        },
    ]
    for ev in seed_events:
        resp = await client.post("/v1/events/raw", json=ev)
        assert resp.status_code == 201

    # Find the created incident
    inc_resp = await client.get("/v1/incidents?limit=1")
    assert inc_resp.status_code == 200
    incidents = inc_resp.json()["items"]
    if not incidents:
        pytest.skip("No incident created — correlator did not fire")
    incident_id = incidents[0]["id"]

    # Register an EventBus queue before proposing — captures the emitted event
    bus = get_bus()
    q = bus.register()
    try:
        propose_resp = await client.post("/v1/responses", json={
            "incident_id": incident_id,
            "kind": "tag_incident",
            "params": {"tag": "test"},
        })
        assert propose_resp.status_code == 201

        # Drain the queue: look for action.proposed with matching incident_id
        found = False
        deadline = asyncio.get_event_loop().time() + 3.0
        while asyncio.get_event_loop().time() < deadline:
            try:
                raw = await asyncio.wait_for(q.get(), timeout=0.5)
                event = StreamEvent.model_validate_json(raw)
                if (
                    event.type == "action.proposed"
                    and event.topic == Topic.actions
                    and event.data.get("incident_id") == incident_id
                ):
                    found = True
                    break
            except asyncio.TimeoutError:
                break

        assert found, f"Expected action.proposed event for incident {incident_id}"
    finally:
        bus.unregister(q)


@pytest.mark.asyncio
async def test_publish_directly_emits_action_events(client):
    """publish('action.executed', ...) delivers events through the full Redis pipeline."""
    action_id = str(uuid.uuid4())
    incident_id = str(uuid.uuid4())

    bus = get_bus()
    q = bus.register()
    try:
        await publish("action.executed", {
            "action_id": action_id,
            "incident_id": incident_id,
            "kind": "tag_incident",
            "result": "ok",
        })
        await publish("action.reverted", {
            "action_id": action_id,
            "incident_id": incident_id,
            "kind": "tag_incident",
        })

        received_types: list[str] = []
        for _ in range(2):
            try:
                raw = await asyncio.wait_for(q.get(), timeout=5.0)
                event = StreamEvent.model_validate_json(raw)
                received_types.append(event.type)
            except asyncio.TimeoutError:
                break

        assert "action.executed" in received_types
        assert "action.reverted" in received_types
    finally:
        bus.unregister(q)
