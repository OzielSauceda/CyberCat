"""Integration test: identity_compromise auto-proposes request_evidence (suggest_only).

Requires docker compose stack (Postgres + Redis) to be running.
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_identity_compromise_auto_proposes_evidence_request(client, truncate_tables):
    """Opening an identity_compromise incident should auto-create a triage_log evidence request."""
    # Trigger an identity_compromise incident via brute force burst + anomalous success
    for i in range(5):
        await client.post("/v1/events/raw", json={
            "source": "seeder",
            "kind": "auth.failed",
            "occurred_at": "2026-04-22T12:00:00Z",
            "raw": {},
            "normalized": {"user": "ivan", "source_ip": "10.3.3.3", "auth_type": "ssh"},
            "dedupe_key": f"auto-er-burst-{i}",
        })
    await client.post("/v1/events/raw", json={
        "source": "seeder",
        "kind": "auth.succeeded",
        "occurred_at": "2026-04-22T12:00:01Z",
        "raw": {},
        "normalized": {"user": "ivan", "source_ip": "10.3.3.3", "auth_type": "ssh"},
        "dedupe_key": "auto-er-success",
    })

    incidents = (await client.get("/v1/incidents?limit=10")).json()
    ic_incidents = [i for i in incidents["items"] if i["kind"] == "identity_compromise"]
    assert len(ic_incidents) >= 1, "Expected at least one identity_compromise incident"
    inc_id = ic_incidents[0]["id"]

    ers = (await client.get(f"/v1/evidence-requests?incident_id={inc_id}")).json()

    triage_requests = [er for er in ers["items"] if er["kind"] == "triage_log"]
    assert len(triage_requests) >= 1, (
        f"Expected auto-proposed triage_log evidence request, got: {[er['kind'] for er in ers['items']]}"
    )
    assert triage_requests[0]["status"] == "open"

    incident_detail = (await client.get(f"/v1/incidents/{inc_id}")).json()
    actions = incident_detail.get("actions", [])
    re_actions = [a for a in actions if a["kind"] == "request_evidence"]
    assert len(re_actions) >= 1, "Expected request_evidence action in incident detail"
    assert re_actions[0]["proposed_by"] == "system"
