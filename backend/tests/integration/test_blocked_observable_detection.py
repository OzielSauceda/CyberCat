"""Integration test: block an IP → ingest event referencing it → detection fires.

Requires docker compose stack (Postgres + Redis) to be running.
"""
from __future__ import annotations

import pytest


async def _open_incident(client, user: str, source_ip: str, dedupe_prefix: str) -> str:
    for i in range(5):
        await client.post("/v1/events/raw", json={
            "source": "seeder",
            "kind": "auth.failed",
            "occurred_at": "2026-04-22T11:00:00Z",
            "raw": {},
            "normalized": {"user": user, "source_ip": source_ip, "auth_type": "ssh"},
            "dedupe_key": f"{dedupe_prefix}-fail-{i}",
        })
    await client.post("/v1/events/raw", json={
        "source": "seeder",
        "kind": "auth.succeeded",
        "occurred_at": "2026-04-22T11:00:01Z",
        "raw": {},
        "normalized": {"user": user, "source_ip": source_ip, "auth_type": "ssh"},
        "dedupe_key": f"{dedupe_prefix}-success",
    })
    incidents = (await client.get("/v1/incidents?limit=10")).json()
    assert len(incidents["items"]) >= 1, f"Expected ≥1 incident for {user}"
    return incidents["items"][0]["id"]


@pytest.mark.asyncio
async def test_blocked_observable_detection_fires(client, truncate_tables):
    """Block an IP, ingest a network event with that src_ip → py.blocked_observable_match fires."""
    inc_id = await _open_incident(client, "greta", "10.1.1.1", "blocked-obs-setup")

    propose_r = await client.post("/v1/responses", json={
        "incident_id": inc_id,
        "kind": "block_observable",
        "params": {"kind": "ip", "value": "10.1.1.1"},
    })
    assert propose_r.status_code == 201
    action_id = propose_r.json()["action"]["id"]
    exec_r = await client.post(f"/v1/responses/{action_id}/execute")
    assert exec_r.json()["log"]["result"] == "ok"

    # Ingest an event that references the blocked IP as source_ip
    ingest_r = await client.post("/v1/events/raw", json={
        "source": "seeder",
        "kind": "auth.failed",
        "occurred_at": "2026-04-22T11:01:00Z",
        "raw": {},
        "normalized": {"user": "greta", "source_ip": "10.1.1.1", "auth_type": "ssh"},
        "dedupe_key": "blocked-obs-trigger-001",
    })
    assert ingest_r.status_code == 201
    body = ingest_r.json()
    assert "detections_fired" in body

    dets = (await client.get("/v1/detections?rule_id=py.blocked_observable_match&limit=10")).json()
    assert len(dets["items"]) >= 1, "Expected py.blocked_observable_match detection to fire"


@pytest.mark.asyncio
async def test_blocked_observable_no_match_after_revert(client, truncate_tables):
    """After reverting block_observable, subsequent events with that IP should NOT match."""
    inc_id = await _open_incident(client, "hana", "10.2.2.2", "block-revert-setup")

    propose_r = await client.post("/v1/responses", json={
        "incident_id": inc_id,
        "kind": "block_observable",
        "params": {"kind": "ip", "value": "10.2.2.2"},
    })
    action_id = propose_r.json()["action"]["id"]
    await client.post(f"/v1/responses/{action_id}/execute")

    revert_r = await client.post(f"/v1/responses/{action_id}/revert")
    assert revert_r.json()["log"]["result"] == "ok"

    # Ingest event after unblock — should NOT trigger blocked_observable_match
    await client.post("/v1/events/raw", json={
        "source": "seeder",
        "kind": "auth.failed",
        "occurred_at": "2026-04-22T11:05:00Z",
        "raw": {},
        "normalized": {"user": "hana", "source_ip": "10.2.2.2", "auth_type": "ssh"},
        "dedupe_key": "block-revert-after-001",
    })

    dets = (await client.get("/v1/detections?rule_id=py.blocked_observable_match&limit=50")).json()
    matches_for_ip = [
        d for d in dets["items"]
        if d.get("matched_fields", {}).get("matched_value") == "10.2.2.2"
    ]
    assert len(matches_for_ip) == 0, (
        "After unblock, no new blocked_observable_match detections expected"
    )
