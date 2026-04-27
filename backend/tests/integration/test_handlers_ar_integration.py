"""Integration tests for Phase 11: AR dispatch wiring in quarantine_host and kill_process.

Handler integration: dispatcher is mocked, DB state is verified, and partial result
is returned when dispatch fails. Requires docker compose stack (Postgres + Redis).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.response.dispatchers.wazuh_ar import DispatchResult


async def _open_incident(client, user: str, source_ip: str, dedupe_prefix: str) -> str:
    for i in range(5):
        await client.post("/v1/events/raw", json={
            "source": "seeder",
            "kind": "auth.failed",
            "occurred_at": "2026-04-22T12:00:00Z",
            "raw": {},
            "normalized": {"user": user, "source_ip": source_ip, "auth_type": "ssh"},
            "dedupe_key": f"{dedupe_prefix}-fail-{i}",
        })
    await client.post("/v1/events/raw", json={
        "source": "seeder",
        "kind": "auth.succeeded",
        "occurred_at": "2026-04-22T12:00:01Z",
        "raw": {},
        "normalized": {"user": user, "source_ip": source_ip, "auth_type": "ssh"},
        "dedupe_key": f"{dedupe_prefix}-success",
    })
    incidents = (await client.get("/v1/incidents?limit=10")).json()
    assert len(incidents["items"]) >= 1
    return incidents["items"][0]["id"]


# ---------------------------------------------------------------------------
# quarantine_host: AR flag OFF (existing Phase 9A behaviour unchanged)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_quarantine_ar_disabled_returns_ok(client, truncate_tables):
    r = await client.post("/v1/lab/assets", json={"kind": "host", "natural_key": "lab-ar-q-01"})
    assert r.status_code == 201

    inc_id = await _open_incident(client, "carol", "10.1.0.1", "ar-q-off")

    prop = await client.post("/v1/responses", json={
        "incident_id": inc_id,
        "kind": "quarantine_host_lab",
        "params": {"host": "lab-ar-q-01"},
    })
    assert prop.status_code == 201
    action_id = prop.json()["action"]["id"]

    # Flag off (default) — should return ok
    with patch("app.response.handlers.quarantine_host.settings", wazuh_ar_enabled=False):
        exec_r = await client.post(f"/v1/responses/{action_id}/execute")

    assert exec_r.status_code == 200
    body = exec_r.json()
    assert body["log"]["result"] == "ok"
    ri = body["log"]["reversal_info"]
    assert ri["ar_dispatch_status"] == "disabled"


# ---------------------------------------------------------------------------
# quarantine_host: AR enabled + dispatch success → ok
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_quarantine_ar_enabled_dispatch_ok(client, truncate_tables):
    r = await client.post("/v1/lab/assets", json={"kind": "host", "natural_key": "lab-ar-q-02"})
    assert r.status_code == 201

    inc_id = await _open_incident(client, "dave", "10.1.0.2", "ar-q-ok")

    prop = await client.post("/v1/responses", json={
        "incident_id": inc_id,
        "kind": "quarantine_host_lab",
        "params": {"host": "lab-ar-q-02"},
    })
    assert prop.status_code == 201
    action_id = prop.json()["action"]["id"]

    mock_dispatch = AsyncMock(return_value=DispatchResult(
        status="dispatched", wazuh_command_id="cmd-99", response={"ok": True}
    ))
    mock_agent_id = AsyncMock(return_value="002")

    with (
        patch("app.response.handlers.quarantine_host.settings", wazuh_ar_enabled=True),
        patch("app.response.handlers.quarantine_host.dispatch_ar", mock_dispatch),
        patch("app.response.handlers.quarantine_host.agent_id_for_host", mock_agent_id),
    ):
        exec_r = await client.post(f"/v1/responses/{action_id}/execute")

    assert exec_r.status_code == 200
    body = exec_r.json()
    assert body["log"]["result"] == "ok"
    assert body["action"]["status"] == "executed"
    ri = body["log"]["reversal_info"]
    assert ri["ar_dispatch_status"] == "dispatched"
    assert ri["wazuh_command_id"] == "cmd-99"


# ---------------------------------------------------------------------------
# quarantine_host: AR enabled + dispatch failure → partial, DB state persisted
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_quarantine_ar_enabled_dispatch_fails_returns_partial(client, truncate_tables):
    r = await client.post("/v1/lab/assets", json={"kind": "host", "natural_key": "lab-ar-q-03"})
    assert r.status_code == 201

    inc_id = await _open_incident(client, "eve", "10.1.0.3", "ar-q-fail")

    prop = await client.post("/v1/responses", json={
        "incident_id": inc_id,
        "kind": "quarantine_host_lab",
        "params": {"host": "lab-ar-q-03"},
    })
    assert prop.status_code == 201
    action_id = prop.json()["action"]["id"]

    mock_dispatch = AsyncMock(return_value=DispatchResult(
        status="failed", error="HTTP 503"
    ))
    mock_agent_id = AsyncMock(return_value="003")

    with (
        patch("app.response.handlers.quarantine_host.settings", wazuh_ar_enabled=True),
        patch("app.response.handlers.quarantine_host.dispatch_ar", mock_dispatch),
        patch("app.response.handlers.quarantine_host.agent_id_for_host", mock_agent_id),
    ):
        exec_r = await client.post(f"/v1/responses/{action_id}/execute")

    assert exec_r.status_code == 200
    body = exec_r.json()
    assert body["log"]["result"] == "partial"
    assert body["action"]["status"] == "partial"
    ri = body["log"]["reversal_info"]
    assert ri["ar_dispatch_status"] == "failed"
    assert ri["error"] == "HTTP 503"

    # DB state (quarantine marker) must still be persisted
    assets = (await client.get("/v1/lab/assets")).json()
    q_asset = next((a for a in assets if a["natural_key"] == "lab-ar-q-03"), None)
    assert q_asset is not None
    assert "[quarantined:" in (q_asset["notes"] or ""), "DB state must be written even on AR failure"


# ---------------------------------------------------------------------------
# kill_process: AR enabled + dispatch success → ok, reversal_info shaped correctly
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kill_process_ar_dispatch_ok(client, truncate_tables):
    r = await client.post("/v1/lab/assets", json={"kind": "host", "natural_key": "lab-ar-kp-01"})
    assert r.status_code == 201

    inc_id = await _open_incident(client, "frank", "10.1.0.4", "ar-kp-ok")

    prop = await client.post("/v1/responses", json={
        "incident_id": inc_id,
        "kind": "kill_process_lab",
        "params": {"host": "lab-ar-kp-01", "pid": 1234, "process_name": "evil"},
    })
    assert prop.status_code == 201
    action_id = prop.json()["action"]["id"]

    mock_dispatch = AsyncMock(return_value=DispatchResult(
        status="dispatched", wazuh_command_id="cmd-kp-1", response={"ok": True}
    ))
    mock_agent_id = AsyncMock(return_value="004")

    with (
        patch("app.response.handlers.kill_process.settings", wazuh_ar_enabled=True),
        patch("app.response.handlers.kill_process.dispatch_ar", mock_dispatch),
        patch("app.response.handlers.kill_process.agent_id_for_host", mock_agent_id),
    ):
        exec_r = await client.post(f"/v1/responses/{action_id}/execute")

    assert exec_r.status_code == 200
    body = exec_r.json()
    assert body["log"]["result"] == "ok"
    ri = body["log"]["reversal_info"]
    assert ri["ar_dispatch_status"] == "dispatched"
    assert ri["host"] == "lab-ar-kp-01"
    assert ri["pid"] == 1234


# ---------------------------------------------------------------------------
# kill_process: agent not enrolled → partial
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_kill_process_agent_not_enrolled(client, truncate_tables):
    r = await client.post("/v1/lab/assets", json={"kind": "host", "natural_key": "lab-ar-kp-02"})
    assert r.status_code == 201

    inc_id = await _open_incident(client, "grace", "10.1.0.5", "ar-kp-noagent")

    prop = await client.post("/v1/responses", json={
        "incident_id": inc_id,
        "kind": "kill_process_lab",
        "params": {"host": "lab-ar-kp-02", "pid": 5678, "process_name": "badproc"},
    })
    assert prop.status_code == 201
    action_id = prop.json()["action"]["id"]

    mock_agent_id = AsyncMock(return_value=None)

    with (
        patch("app.response.handlers.kill_process.settings", wazuh_ar_enabled=True),
        patch("app.response.handlers.kill_process.agent_id_for_host", mock_agent_id),
    ):
        exec_r = await client.post(f"/v1/responses/{action_id}/execute")

    assert exec_r.status_code == 200
    body = exec_r.json()
    assert body["log"]["result"] == "partial"
    assert body["action"]["status"] == "partial"
