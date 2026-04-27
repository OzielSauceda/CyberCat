"""Integration tests for the identity_endpoint_chain correlator.

Requires docker compose stack (Postgres + Redis) to be running.
Run: pytest backend/tests/integration/test_identity_endpoint_chain.py
"""
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _post_auth_failed(client, user: str, source_ip: str, index: int) -> None:
    r = await client.post("/v1/events/raw", json={
        "kind": "auth.failed",
        "source": "seeder",
        "occurred_at": f"2026-04-23T08:5{index}:00Z",
        "raw": {},
        "normalized": {"user": user, "source_ip": source_ip, "auth_type": "Password"},
        "dedupe_key": f"chain-test-failed-{user}-{index}",
    })
    assert r.status_code == 201, r.text


async def _post_auth_succeeded(client, user: str, source_ip: str, tag: str = "001") -> None:
    r = await client.post("/v1/events/raw", json={
        "kind": "auth.succeeded",
        "source": "seeder",
        "occurred_at": "2026-04-23T08:56:00Z",
        "raw": {},
        "normalized": {"user": user, "source_ip": source_ip, "auth_type": "Password"},
        "dedupe_key": f"chain-test-success-{tag}",
    })
    assert r.status_code == 201, r.text


async def _post_process(client, user: str, host: str, tag: str = "001") -> None:
    r = await client.post("/v1/events/raw", json={
        "kind": "process.created",
        "source": "seeder",
        "occurred_at": "2026-04-23T08:57:00Z",
        "raw": {},
        "normalized": {
            "host": host,
            "user": user,
            "pid": 9999,
            "ppid": 1,
            "image": "C:\\Windows\\System32\\powershell.exe",
            "cmdline": "powershell -enc SQBuAHYAbwBrAGUALQBXAGUAYgBSAGUAcQB1AGUAcwB0AA==",
        },
        "dedupe_key": f"chain-test-process-{tag}",
    })
    assert r.status_code == 201, r.text


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chain_incident_opens_when_identity_precedes_endpoint(client, truncate_tables):
    """auth burst + auth.succeeded → identity_compromise; then process.created → identity_endpoint_chain."""
    user = "alice@example.com"
    source_ip = "203.0.113.42"
    host = "workstation-42"

    # Brute-force burst (4 failures)
    for i in range(4):
        await _post_auth_failed(client, user, source_ip, i)

    # Successful login from same new IP → identity_compromise opens
    await _post_auth_succeeded(client, user, source_ip)

    # Suspicious process on same user's host → chain should open
    await _post_process(client, user, host)

    r = await client.get("/v1/incidents")
    all_incidents = r.json()["items"]
    kinds = [i["kind"] for i in all_incidents]

    assert "identity_compromise" in kinds, f"Expected identity_compromise, got kinds={kinds}"
    assert "identity_endpoint_chain" in kinds, f"Expected identity_endpoint_chain, got kinds={kinds}"
    assert "endpoint_compromise" not in kinds, (
        f"Standalone should not fire when chain fires, got kinds={kinds}"
    )

    chain_inc = next(i for i in all_incidents if i["kind"] == "identity_endpoint_chain")
    # auto_actions elevates severity from high → critical immediately on creation
    assert chain_inc["severity"] == "critical"
    assert float(chain_inc["confidence"]) == pytest.approx(0.85, abs=0.01)
    assert user in chain_inc["title"]
    assert host in chain_inc["title"]


@pytest.mark.asyncio
async def test_chain_dedup_no_second_incident(client, truncate_tables):
    """Re-firing the process event in the same hour bucket does not open a second chain incident."""
    user = "alice@example.com"
    source_ip = "203.0.113.42"
    host = "workstation-42"

    for i in range(4):
        await _post_auth_failed(client, user, source_ip, i)
    await _post_auth_succeeded(client, user, source_ip)
    await _post_process(client, user, host, tag="dedup-001")

    # Second process event — different dedupe_key but same user+host+hour bucket
    await _post_process(client, user, host, tag="dedup-002")

    r = await client.get("/v1/incidents")
    chain_incidents = [i for i in r.json()["items"] if i["kind"] == "identity_endpoint_chain"]
    assert len(chain_incidents) == 1, f"Dedup failed — got {len(chain_incidents)} chain incidents"


@pytest.mark.asyncio
async def test_no_chain_without_prior_identity_incident(client, truncate_tables):
    """process.created with no prior identity activity → chain does NOT fire; standalone does."""
    await _post_process(client, "bob@example.com", "workstation-99", tag="no-identity")

    r = await client.get("/v1/incidents")
    kinds = [i["kind"] for i in r.json()["items"]]

    assert "identity_endpoint_chain" not in kinds, (
        f"Chain should not fire without prior identity incident, got kinds={kinds}"
    )
    assert "endpoint_compromise" in kinds, (
        f"Standalone should fire when there is no identity incident, got kinds={kinds}"
    )


@pytest.mark.asyncio
async def test_no_chain_when_identity_incident_is_for_different_user(client, truncate_tables):
    """identity_compromise for user A + process.created for user B → chain does NOT fire for B."""
    source_ip = "203.0.113.42"

    # Build identity incident for user A
    for i in range(4):
        await _post_auth_failed(client, "alice@example.com", source_ip, i)
    await _post_auth_succeeded(client, "alice@example.com", source_ip, tag="userA")

    # Process event on user B's host — chain must not activate (no identity incident for B)
    await _post_process(client, "bob@example.com", "workstation-bob", tag="userB")

    r = await client.get("/v1/incidents")
    all_incidents = r.json()["items"]
    kinds = [i["kind"] for i in all_incidents]

    assert "identity_endpoint_chain" not in kinds, (
        f"Chain should not fire for user B when only user A has an identity incident, "
        f"got kinds={kinds}"
    )
    assert "identity_compromise" in kinds, "User A's identity_compromise should still be present"
    # Standalone fires for user B's host
    assert "endpoint_compromise" in kinds, (
        f"Standalone should fire for user B's unlinked process event, got kinds={kinds}"
    )
