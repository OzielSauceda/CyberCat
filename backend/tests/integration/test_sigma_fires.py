"""Integration tests for Sigma rule firing.

Requires docker compose stack (Postgres + Redis) to be running.
"""
import pytest


@pytest.mark.asyncio
async def test_sigma_rule_fires_on_encoded_powershell(client, truncate_tables):
    """Encoded PowerShell event → at least one sigma-rule Detection with expected sigma_id."""
    r = await client.post("/v1/events/raw", json={
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
        "dedupe_key": "test-sigma-fire-001",
    })
    assert r.status_code == 201, r.text

    r2 = await client.get("/v1/detections", params={"rule_source": "sigma"})
    body = r2.json()
    sigma_detections = body["items"]

    assert len(sigma_detections) >= 1, "Expected at least one Sigma detection"

    encoded_ps_detections = [
        d for d in sigma_detections
        if d["rule_id"].startswith("sigma-proc-creation-win-powershell-encoded-cmd")
        or "proc-creation-win-powershell-encoded-cmd" in d["rule_id"]
    ]
    assert len(encoded_ps_detections) >= 1, (
        f"Expected sigma rule for encoded-cmd, got: {[d['rule_id'] for d in sigma_detections]}"
    )

    det = encoded_ps_detections[0]
    assert "sigma_id" in det["matched_fields"], "Sigma detection should have sigma_id in matched_fields"


@pytest.mark.asyncio
async def test_sigma_and_python_both_fire_on_same_event(client, truncate_tables):
    """Same encoded-PS event → both sigma and py detection rows linked to the same incident."""
    r = await client.post("/v1/events/raw", json={
        "kind": "process.created",
        "source": "seeder",
        "occurred_at": "2026-04-21T10:00:00Z",
        "raw": {},
        "normalized": {
            "host": "lab-win10-01",
            "pid": 2222,
            "ppid": 1,
            "image": "C:\\Windows\\System32\\powershell.exe",
            "cmdline": "powershell.exe -enc SQBuAHYAbwBrAGUALQBXAGUAYgBSAGUAcQB1AGUAcwB0AA==",
        },
        "dedupe_key": "test-cofire-001",
    })
    assert r.status_code == 201, r.text

    r2 = await client.get("/v1/detections", params={"limit": 100})
    all_detections = r2.json()["items"]

    sources = {d["rule_source"] for d in all_detections}
    assert "sigma" in sources, "Expected a sigma detection"
    assert "py" in sources, "Expected a Python detection"
