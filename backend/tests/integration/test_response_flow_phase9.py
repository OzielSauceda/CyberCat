"""Integration tests for Phase 9A response handler end-to-end flow.

Propose → execute → revert via the HTTP API for each new action kind.
Requires docker compose stack (Postgres + Redis) to be running.
"""
from __future__ import annotations

import pytest


async def _open_incident(client, user: str, source_ip: str, dedupe_prefix: str) -> str:
    """Burst 5 auth.failed then auth.succeeded to create an identity_compromise incident.
    Returns the incident id."""
    for i in range(5):
        await client.post("/v1/events/raw", json={
            "source": "seeder",
            "kind": "auth.failed",
            "occurred_at": "2026-04-22T10:00:00Z",
            "raw": {},
            "normalized": {"user": user, "source_ip": source_ip, "auth_type": "ssh"},
            "dedupe_key": f"{dedupe_prefix}-fail-{i}",
        })
    await client.post("/v1/events/raw", json={
        "source": "seeder",
        "kind": "auth.succeeded",
        "occurred_at": "2026-04-22T10:00:01Z",
        "raw": {},
        "normalized": {"user": user, "source_ip": source_ip, "auth_type": "ssh"},
        "dedupe_key": f"{dedupe_prefix}-success",
    })
    incidents = (await client.get("/v1/incidents?limit=10")).json()
    assert len(incidents["items"]) >= 1, f"Expected ≥1 incident after burst for {user}"
    return incidents["items"][0]["id"]


@pytest.mark.asyncio
async def test_quarantine_host_propose_execute(client, truncate_tables):
    """quarantine_host_lab: propose + execute → LabAsset.notes contains quarantine marker."""
    r = await client.post("/v1/lab/assets", json={"kind": "host", "natural_key": "lab-q-01"})
    assert r.status_code == 201, r.text

    inc_id = await _open_incident(client, "bob", "10.0.0.1", "phase9-q")

    propose_r = await client.post("/v1/responses", json={
        "incident_id": inc_id,
        "kind": "quarantine_host_lab",
        "params": {"host": "lab-q-01"},
    })
    assert propose_r.status_code == 201, propose_r.text
    action_id = propose_r.json()["action"]["id"]

    exec_r = await client.post(f"/v1/responses/{action_id}/execute")
    assert exec_r.status_code == 200, exec_r.text
    assert exec_r.json()["log"]["result"] == "ok"

    assets = (await client.get("/v1/lab/assets")).json()
    q_asset = next((a for a in assets if a["natural_key"] == "lab-q-01"), None)
    assert q_asset is not None
    assert "[quarantined:" in (q_asset["notes"] or ""), "Expected quarantine marker in notes"


@pytest.mark.asyncio
async def test_block_observable_propose_execute_revert(client, truncate_tables):
    """block_observable: propose + execute → active row; revert → active=false."""
    inc_id = await _open_incident(client, "charlie", "10.0.0.2", "phase9-block")

    propose_r = await client.post("/v1/responses", json={
        "incident_id": inc_id,
        "kind": "block_observable",
        "params": {"kind": "ip", "value": "192.168.55.99"},
    })
    assert propose_r.status_code == 201, propose_r.text
    action_id = propose_r.json()["action"]["id"]

    exec_r = await client.post(f"/v1/responses/{action_id}/execute")
    assert exec_r.status_code == 200, exec_r.text
    assert exec_r.json()["log"]["result"] == "ok"

    bos = (await client.get("/v1/blocked-observables?active=true")).json()
    match = [bo for bo in bos["items"] if bo["value"] == "192.168.55.99"]
    assert len(match) == 1 and match[0]["active"] is True

    revert_r = await client.post(f"/v1/responses/{action_id}/revert")
    assert revert_r.status_code == 200, revert_r.text

    bos_after = (await client.get("/v1/blocked-observables?active=false")).json()
    match_after = [bo for bo in bos_after["items"] if bo["value"] == "192.168.55.99"]
    assert len(match_after) == 1 and match_after[0]["active"] is False


@pytest.mark.asyncio
async def test_invalidate_session_propose_execute_revert(client, truncate_tables):
    """invalidate_lab_session: propose + execute + revert → invalidated_at set then unset."""
    await client.post("/v1/lab/assets", json={"kind": "user", "natural_key": "dave"})
    await client.post("/v1/lab/assets", json={"kind": "host", "natural_key": "lab-is-01"})

    # session.started creates user entity "dave" and host entity "lab-is-01"
    # and a LabSession linking them (both are registered lab assets)
    await client.post("/v1/events/raw", json={
        "source": "seeder",
        "kind": "session.started",
        "occurred_at": "2026-04-22T10:00:00Z",
        "raw": {},
        "normalized": {"user": "dave", "host": "lab-is-01", "session_id": "sess-dave-001"},
        "dedupe_key": "phase9-is-session-001",
    })

    # Open incident: burst from a fresh IP (no prior successes) → anomalous success
    inc_id = await _open_incident(client, "dave", "10.0.0.99", "phase9-is")

    propose_r = await client.post("/v1/responses", json={
        "incident_id": inc_id,
        "kind": "invalidate_lab_session",
        "params": {"user": "dave", "host": "lab-is-01"},
    })
    assert propose_r.status_code == 201, propose_r.text
    action_id = propose_r.json()["action"]["id"]

    exec_r = await client.post(f"/v1/responses/{action_id}/execute")
    assert exec_r.status_code == 200, exec_r.text
    assert exec_r.json()["log"]["result"] == "ok"

    revert_r = await client.post(f"/v1/responses/{action_id}/revert")
    assert revert_r.status_code == 200, revert_r.text
    assert revert_r.json()["log"]["result"] == "ok"


@pytest.mark.asyncio
async def test_request_evidence_propose_execute_list(client, truncate_tables):
    """request_evidence: propose + execute → evidence_request row; list via GET."""
    inc_id = await _open_incident(client, "eve", "10.0.0.4", "phase9-re")

    propose_r = await client.post("/v1/responses", json={
        "incident_id": inc_id,
        "kind": "request_evidence",
        "params": {"evidence_kind": "process_list"},
    })
    assert propose_r.status_code == 201, propose_r.text
    action_id = propose_r.json()["action"]["id"]

    exec_r = await client.post(f"/v1/responses/{action_id}/execute")
    assert exec_r.status_code == 200, exec_r.text

    ers = (await client.get(f"/v1/evidence-requests?incident_id={inc_id}")).json()
    assert len(ers["items"]) >= 1
    er = ers["items"][0]
    assert er["kind"] == "process_list"
    assert er["status"] == "open"

    collect_r = await client.post(f"/v1/evidence-requests/{er['id']}/collect")
    assert collect_r.status_code == 200
    assert collect_r.json()["status"] == "collected"


@pytest.mark.asyncio
async def test_disruptive_revert_rejected(client, truncate_tables):
    """Revert on a disruptive action must return 409 with not_reversible code."""
    await client.post("/v1/lab/assets", json={"kind": "host", "natural_key": "lab-dr-01"})

    inc_id = await _open_incident(client, "frank", "10.0.0.5", "phase9-dr")

    propose_r = await client.post("/v1/responses", json={
        "incident_id": inc_id,
        "kind": "quarantine_host_lab",
        "params": {"host": "lab-dr-01"},
    })
    action_id = propose_r.json()["action"]["id"]
    await client.post(f"/v1/responses/{action_id}/execute")

    revert_r = await client.post(f"/v1/responses/{action_id}/revert")
    assert revert_r.status_code == 409
    detail = revert_r.json()
    assert "not_reversible" in str(detail)
