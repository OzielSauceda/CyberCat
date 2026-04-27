"""Integration tests for the standalone endpoint_compromise correlator.

Requires docker compose stack (Postgres + Redis) to be running.
Run: pytest backend/tests/integration/test_endpoint_standalone.py
"""
import pytest


@pytest.mark.asyncio
async def test_standalone_opens_medium_incident(client, truncate_tables):
    """process.created with no prior auth events → one endpoint_compromise incident at medium."""
    event_payload = {
        "kind": "process.created",
        "source": "seeder",
        "occurred_at": "2026-04-21T10:00:00Z",
        "raw": {},
        "normalized": {
            "host": "lab-win10-01",
            "pid": 1234,
            "ppid": 456,
            "image": "C:\\Windows\\System32\\powershell.exe",
            "cmdline": "powershell.exe -enc SQBuAHYAbwBrAGUALQBXAGUAYgBSAGUAcQB1AGUAcwB0AA==",
        },
        "dedupe_key": "test-standalone-001",
    }

    r = await client.post("/v1/events/raw", json=event_payload)
    assert r.status_code == 201, r.text

    r2 = await client.get("/v1/incidents")
    body = r2.json()
    incidents = body["items"]

    endpoint_incidents = [i for i in incidents if i["kind"] == "endpoint_compromise"]
    assert len(endpoint_incidents) == 1, f"Expected 1 endpoint_compromise incident, got {len(endpoint_incidents)}"

    inc = endpoint_incidents[0]
    assert inc["severity"] == "medium"
    assert float(inc["confidence"]) == pytest.approx(0.60, abs=0.01)


@pytest.mark.asyncio
async def test_standalone_dedup_no_second_incident(client, truncate_tables):
    """Re-posting the same process event inside the same hour does not open a second incident."""
    base_payload = {
        "kind": "process.created",
        "source": "seeder",
        "occurred_at": "2026-04-21T10:00:00Z",
        "raw": {},
        "normalized": {
            "host": "lab-win10-02",
            "pid": 5678,
            "ppid": 100,
            "image": "C:\\Windows\\System32\\powershell.exe",
            "cmdline": "powershell.exe -enc SQBuAHYAbwBrAGUALQBXAGUAYgBSAGUAcQB1AGUAcwB0AA==",
        },
        "dedupe_key": "test-dedup-001",
    }

    r1 = await client.post("/v1/events/raw", json=base_payload)
    assert r1.status_code == 201

    # Second post with different dedupe key (same host, same hour bucket)
    payload2 = {**base_payload, "dedupe_key": "test-dedup-002"}
    r2 = await client.post("/v1/events/raw", json=payload2)
    assert r2.status_code == 201

    r3 = await client.get("/v1/incidents")
    incidents = [i for i in r3.json()["items"] if i["kind"] == "endpoint_compromise"]
    assert len(incidents) == 1, f"Dedup failed — got {len(incidents)} incidents"


@pytest.mark.asyncio
async def test_join_wins_over_standalone(client, truncate_tables):
    """Identity chain followed by process event → one identity_compromise, no standalone endpoint."""
    # Seed 4 auth.failed + 1 auth.succeeded (triggers identity_compromise correlator)
    for i in range(4):
        r = await client.post("/v1/events/raw", json={
            "kind": "auth.failed",
            "source": "seeder",
            "occurred_at": f"2026-04-21T09:5{i}:00Z",
            "raw": {},
            "normalized": {"user": "alice@example.com", "source_ip": "10.0.0.99", "auth_type": "Password"},
            "dedupe_key": f"test-join-failed-{i}",
        })
        assert r.status_code == 201

    r = await client.post("/v1/events/raw", json={
        "kind": "auth.succeeded",
        "source": "seeder",
        "occurred_at": "2026-04-21T09:55:00Z",
        "raw": {},
        "normalized": {"user": "alice@example.com", "source_ip": "10.0.0.99", "auth_type": "Password"},
        "dedupe_key": "test-join-success-001",
    })
    assert r.status_code == 201

    # Now process event for the same user's host
    r = await client.post("/v1/events/raw", json={
        "kind": "process.created",
        "source": "seeder",
        "occurred_at": "2026-04-21T09:56:00Z",
        "raw": {},
        "normalized": {
            "host": "lab-win10-01",
            "pid": 9999,
            "ppid": 1,
            "image": "C:\\Windows\\System32\\powershell.exe",
            "cmdline": "powershell.exe -enc SQBuAHYAbwBrAGUALQBXAGUAYgBSAGUAcQB1AGUAcwB0AA==",
            "user": "alice@example.com",
        },
        "dedupe_key": "test-join-process-001",
    })
    assert r.status_code == 201

    r_inc = await client.get("/v1/incidents")
    all_incidents = r_inc.json()["items"]
    kinds = [i["kind"] for i in all_incidents]

    assert "identity_compromise" in kinds, "Expected identity_compromise incident"
    assert "endpoint_compromise" not in kinds, (
        "Standalone correlator should not fire when join correlator succeeds"
    )
