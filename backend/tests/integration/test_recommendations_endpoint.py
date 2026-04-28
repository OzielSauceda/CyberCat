"""Integration tests for GET /v1/incidents/{id}/recommended-actions (Phase 15.1).

Requires docker compose stack (Postgres + Redis) to be running.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.auth.dependencies import get_current_user, require_user
from app.auth.models import UserRole
from app.db.redis import close_redis, init_redis
from app.db.session import AsyncSessionLocal
from app.main import app
from app.streaming.bus import close_bus, init_bus


# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------

async def _raise_401() -> None:
    raise HTTPException(status_code=401, detail="Authentication required")


_FIXED_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest_asyncio.fixture()
async def _anon_client():
    app.dependency_overrides[get_current_user] = _raise_401
    await init_redis()
    await init_bus()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    await close_bus()
    await close_redis()
    app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_anonymous_returns_401(_anon_client):
    r = await _anon_client.get(f"/v1/incidents/{_FIXED_ID}/recommended-actions")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_readonly_user_returns_200(readonly_client, truncate_tables):
    """read_only role can read the recommendations endpoint (GET = no mutation)."""
    r = await readonly_client.get(f"/v1/incidents/{_FIXED_ID}/recommended-actions")
    # 404 is fine — incident doesn't exist, but auth succeeded
    assert r.status_code in (200, 404)


@pytest.mark.asyncio
async def test_unknown_incident_id_returns_404(authed_client, truncate_tables):
    r = await authed_client.get(f"/v1/incidents/{_FIXED_ID}/recommended-actions")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_real_incident_returns_recommendations(authed_client, truncate_tables):
    """Fire the identity_compromise scenario via events/raw and assert recommendations."""
    user = "alice"
    source_ip = "203.0.113.42"

    # Trigger auth burst → identity_compromise incident
    for i in range(5):
        r = await authed_client.post("/v1/events/raw", json={
            "source": "seeder",
            "kind": "auth.failed",
            "occurred_at": "2026-04-28T10:00:00Z",
            "raw": {},
            "normalized": {"user": user, "source_ip": source_ip, "auth_type": "ssh"},
            "dedupe_key": f"rec-test-fail-{i}",
        })
        assert r.status_code == 201, r.text

    r = await authed_client.post("/v1/events/raw", json={
        "source": "seeder",
        "kind": "auth.succeeded",
        "occurred_at": "2026-04-28T10:00:01Z",
        "raw": {},
        "normalized": {"user": user, "source_ip": source_ip, "auth_type": "ssh"},
        "dedupe_key": "rec-test-success",
    })
    assert r.status_code == 201, r.text

    # Find the incident
    incidents_r = await authed_client.get("/v1/incidents?limit=10")
    assert incidents_r.status_code == 200
    items = incidents_r.json()["items"]
    assert len(items) >= 1, "Expected at least one incident after auth burst"
    inc_id = items[0]["id"]

    # Fetch recommendations
    rec_r = await authed_client.get(f"/v1/incidents/{inc_id}/recommended-actions")
    assert rec_r.status_code == 200, rec_r.text

    recs = rec_r.json()
    assert isinstance(recs, list)
    assert len(recs) >= 1

    # Validate shape of each recommendation
    for rec in recs:
        assert "kind" in rec
        assert "params" in rec
        assert "rationale" in rec
        assert "classification" in rec
        assert "classification_reason" in rec
        assert isinstance(rec["priority"], int)
        assert "target_summary" in rec

    # Priorities should be strictly ascending (1, 2, 3, ...)
    priorities = [r["priority"] for r in recs]
    assert priorities == list(range(1, len(recs) + 1))

    # Excluded kinds must never appear
    kinds = [r["kind"] for r in recs]
    assert "tag_incident" not in kinds
    assert "elevate_severity" not in kinds
    assert "kill_process_lab" not in kinds

    # block_observable on source IP should be present and first (identity_compromise + source_ip)
    block_recs = [r for r in recs if r["kind"] == "block_observable"]
    assert len(block_recs) >= 1
    assert block_recs[0]["params"]["value"] == source_ip
    assert recs[0]["kind"] == "block_observable"
